from __future__ import annotations

import cv2
import numpy as np

from src.domain.config import BackgroundConfig, FaceEnhanceConfig, PersonCropConfig, SegmentationConfig
from src.pipeline.background import BackgroundProvider
from src.pipeline.bounds import BoundsTracker
from src.pipeline.composer import Composer
from src.pipeline.mask_processing import refine_mask
from src.pipeline.segmentation import build_segmenter
from src.utils.image import crop_and_resize


class FrameProcessor:
    def __init__(
        self,
        segmentation: SegmentationConfig,
        background: BackgroundConfig,
        crop: PersonCropConfig,
        face_enhance: FaceEnhanceConfig,
        output_width: int,
        output_height: int,
    ) -> None:
        self._seg_cfg = segmentation
        self._segmenter = build_segmenter(segmentation)
        self._background = BackgroundProvider(background, output_width, output_height)
        self._bounds = BoundsTracker(crop, output_width, output_height)
        self._composer = Composer()
        self._face_enhance = face_enhance
        self._output_width = output_width
        self._output_height = output_height
        self._low_mask_ratio_logged = False
        self._dark_fallback_warn_count = 0
        self._face_cascade = None
        self._face_warned = False
        if self._face_enhance.enabled or self._face_enhance.deidentifyEnabled:
            try:
                self._face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
                if self._face_cascade.empty():
                    self._face_cascade = None
            except Exception:
                self._face_cascade = None

    def process(self, frame: np.ndarray) -> np.ndarray:
        frame = self._apply_face_enhance(frame)
        raw_mask = self._segmenter.segment(frame)
        mask = refine_mask(
            raw_mask,
            self._seg_cfg.threshold,
            edge_smoothness=self._seg_cfg.edgeSmoothness,
            blend_feather=self._seg_cfg.blendFeather,
        )
        foreground_ratio = float((mask > 0).mean())
        if foreground_ratio < 0.05:
            if not self._low_mask_ratio_logged:
                print(
                    "[seg] warning: segmentation mask foreground ratio is very low "
                    f"({foreground_ratio:.3f}); passthrough source frame for visibility.",
                    flush=True,
                )
                self._low_mask_ratio_logged = True
            bounds = self._bounds.update(mask)
            output = crop_and_resize(
                frame,
                self._bounds.as_rect(bounds),
                self._output_width,
                self._output_height,
            )
            return self._apply_face_deidentify(output)

        bounds = self._bounds.update(mask)
        background = self._background.frame()
        composed = self._composer.compose(frame, mask, background)
        # Guardrail: avoid near-black output when segmentation is unstable.
        if foreground_ratio < 0.20:
            source_mean = float(frame.mean())
            composed_mean = float(composed.mean())
            if source_mean > 20.0 and composed_mean < 8.0:
                self._dark_fallback_warn_count += 1
                # Log only first and periodic events to avoid noisy runtime output.
                if self._dark_fallback_warn_count == 1 or self._dark_fallback_warn_count % 120 == 0:
                    print(
                        "[seg] warning: composed frame is too dark under low foreground ratio "
                        f"(fg={foreground_ratio:.3f}, src_mean={source_mean:.2f}, out_mean={composed_mean:.2f}); "
                        f"passthrough source frame (count={self._dark_fallback_warn_count}).",
                        flush=True,
                    )
                output = crop_and_resize(
                    frame,
                    self._bounds.as_rect(bounds),
                    self._output_width,
                    self._output_height,
                )
                return self._apply_face_deidentify(output)
        output = crop_and_resize(
            composed,
            self._bounds.as_rect(bounds),
            self._output_width,
            self._output_height,
        )
        return self._apply_face_deidentify(output)

    def _apply_face_enhance(self, frame: np.ndarray) -> np.ndarray:
        if not self._face_enhance.enabled:
            return frame
        if self._face_cascade is None:
            if not self._face_warned:
                print("[face] warning: face detector unavailable; skip face enhancement.", flush=True)
                self._face_warned = True
            return frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            return frame
        h, w = frame.shape[:2]
        min_size = int(min(h, w) * float(self._face_enhance.minRegionRatio))
        out = frame.copy()
        for x, y, fw, fh in faces:
            if fw < min_size or fh < min_size:
                continue
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w, x + fw)
            y1 = min(h, y + fh)
            if x1 <= x0 or y1 <= y0:
                continue
            roi = out[y0:y1, x0:x1]
            tuned = self._tune_roi(roi)
            blend = float(self._face_enhance.strength)
            alpha = self._build_face_alpha_mask(
                roi.shape[0],
                roi.shape[1],
                blend,
                float(self._face_enhance.edgeNoise),
                seed=(x0 * 73856093) ^ (y0 * 19349663) ^ (fw * 83492791) ^ (fh * 2971215073),
            )
            alpha_3 = alpha[:, :, None].astype(np.float32)
            blended = tuned.astype(np.float32) * alpha_3 + roi.astype(np.float32) * (1.0 - alpha_3)
            out[y0:y1, x0:x1] = np.clip(blended, 0.0, 255.0).astype(np.uint8)
        return out

    def _tune_roi(self, roi: np.ndarray) -> np.ndarray:
        f32 = roi.astype(np.float32) / 255.0
        gamma = max(0.5, min(1.8, float(self._face_enhance.gamma)))
        if abs(gamma - 1.0) > 1e-3:
            f32 = np.power(np.clip(f32, 0.0, 1.0), 1.0 / gamma).astype(np.float32)
        brightness = max(-80.0, min(80.0, float(self._face_enhance.offset))) / 255.0
        if abs(brightness) > 1e-4:
            f32 = np.clip(f32 + brightness, 0.0, 1.0)
        bgr = (f32 * 255.0).astype(np.uint8)
        sat = max(0.5, min(1.8, float(self._face_enhance.saturation)))
        if abs(sat - 1.0) > 1e-3:
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat, 0.0, 255.0)
            bgr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        return bgr

    def _build_face_alpha_mask(
        self,
        h: int,
        w: int,
        blend: float,
        edge_dither: float,
        seed: int,
    ) -> np.ndarray:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx = (w - 1) * 0.5
        cy = (h - 1) * 0.5
        rx = max(1.0, w * 0.55)
        ry = max(1.0, h * 0.60)
        dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        inner = 0.72
        outer = 1.0
        base = np.clip((outer - dist) / max(1e-6, (outer - inner)), 0.0, 1.0)
        transition = ((dist > inner) & (dist < outer)).astype(np.float32)
        if edge_dither > 0.0:
            rng = np.random.default_rng(seed & 0xFFFFFFFF)
            noise = rng.random((h, w), dtype=np.float32) - 0.5
            base = np.clip(base + noise * float(edge_dither) * 0.35 * transition, 0.0, 1.0)
        base = cv2.GaussianBlur(base, (0, 0), sigmaX=1.2, sigmaY=1.2)
        return np.clip(base * float(blend), 0.0, 1.0).astype(np.float32)

    def _apply_face_deidentify(self, frame: np.ndarray) -> np.ndarray:
        if not self._face_enhance.deidentifyEnabled:
            return frame
        if self._face_cascade is None:
            if not self._face_warned:
                print("[face] warning: face detector unavailable; skip deidentify.", flush=True)
                self._face_warned = True
            return frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            return frame
        out = frame.copy()
        h, w = out.shape[:2]
        for x, y, fw, fh in faces:
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w, x + fw)
            y1 = min(h, y + fh)
            if x1 <= x0 or y1 <= y0:
                continue
            eye_band_y0 = int(round(y0 + fh * 0.28))
            eye_band_y1 = int(round(y0 + fh * 0.52))
            eye_band_y0 = max(y0, min(eye_band_y0, y1 - 1))
            eye_band_y1 = max(eye_band_y0 + 1, min(eye_band_y1, y1))
            cv2.rectangle(out, (x0, eye_band_y0), (x1, eye_band_y1), (16, 16, 16), thickness=-1)
        return out

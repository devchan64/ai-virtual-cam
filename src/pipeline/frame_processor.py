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
        self._last_output_mask = np.zeros((output_height, output_width), dtype=np.uint8)
        self._last_face_alpha_input = np.zeros((1, 1), dtype=np.float32)
        self._last_face_enhance_mask = np.zeros((output_height, output_width), dtype=np.uint8)
        self._last_face_edge_mask_input = np.zeros((1, 1), dtype=np.uint8)
        self._last_face_enhance_edge_mask = np.zeros((output_height, output_width), dtype=np.uint8)
        self._last_deidentify_mask = np.zeros((output_height, output_width), dtype=np.uint8)
        if self._face_enhance.deidentifyEnabled:
            try:
                self._face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
                if self._face_cascade.empty():
                    self._face_cascade = None
            except Exception:
                self._face_cascade = None

    def process(self, frame: np.ndarray) -> np.ndarray:
        raw_mask = self._segmenter.segment(frame)
        mask = refine_mask(
            raw_mask,
            self._seg_cfg.threshold,
            edge_smoothness=self._seg_cfg.edgeSmoothness,
            blend_feather=self._seg_cfg.blendFeather,
        )
        frame = self._apply_face_enhance(frame, mask)
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
            self._last_output_mask = crop_and_resize(
                mask,
                self._bounds.as_rect(bounds),
                self._output_width,
                self._output_height,
            )
            self._last_face_enhance_mask = self._crop_face_alpha_to_output(self._bounds.as_rect(bounds))
            self._last_face_enhance_edge_mask = self._crop_face_edge_to_output(self._bounds.as_rect(bounds))
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
        self._last_output_mask = crop_and_resize(
            mask,
            self._bounds.as_rect(bounds),
            self._output_width,
            self._output_height,
        )
        self._last_face_enhance_mask = self._crop_face_alpha_to_output(self._bounds.as_rect(bounds))
        self._last_face_enhance_edge_mask = self._crop_face_edge_to_output(self._bounds.as_rect(bounds))
        return self._apply_face_deidentify(output)

    def last_output_mask(self) -> np.ndarray:
        return self._last_output_mask.copy()

    def last_face_enhance_mask(self) -> np.ndarray:
        return self._last_face_enhance_mask.copy()

    def last_face_enhance_edge_mask(self) -> np.ndarray:
        return self._last_face_enhance_edge_mask.copy()

    def last_deidentify_mask(self) -> np.ndarray:
        return self._last_deidentify_mask.copy()

    def _apply_face_enhance(self, frame: np.ndarray, segmentation_mask: np.ndarray) -> np.ndarray:
        if not self._face_enhance.enabled:
            self._last_face_alpha_input = np.zeros(frame.shape[:2], dtype=np.float32)
            self._last_face_edge_mask_input = np.zeros(frame.shape[:2], dtype=np.uint8)
            return frame
        if segmentation_mask.shape[:2] != frame.shape[:2]:
            segmentation_mask = cv2.resize(
                segmentation_mask,
                (frame.shape[1], frame.shape[0]),
                interpolation=cv2.INTER_LINEAR,
            )
        edge_band, edge_alpha = self._build_segmentation_enhance_alpha(segmentation_mask)
        self._last_face_edge_mask_input = edge_band
        self._last_face_alpha_input = edge_alpha
        if float(edge_alpha.max()) <= 0.0:
            return frame
        tuned = self._tune_roi(frame)
        alpha_3 = edge_alpha[:, :, None].astype(np.float32)
        blended = tuned.astype(np.float32) * alpha_3 + frame.astype(np.float32) * (1.0 - alpha_3)
        return np.clip(blended, 0.0, 255.0).astype(np.uint8)

    def _build_segmentation_enhance_alpha(self, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        binary = (mask >= 127).astype(np.uint8) * 255
        k = np.ones((3, 3), dtype=np.uint8)
        dilated = cv2.dilate(binary, k, iterations=2)
        eroded = cv2.erode(binary, k, iterations=2)
        edge_band = cv2.subtract(dilated, eroded)
        edge_soft = cv2.GaussianBlur(edge_band, (0, 0), sigmaX=1.2, sigmaY=1.2).astype(np.float32) / 255.0

        # Keep segmentation-edge-centric behavior, but blend some interior foreground weight
        # so gamma/brightness/saturation changes are visible in preview.
        fg_soft = cv2.GaussianBlur(binary, (0, 0), sigmaX=2.2, sigmaY=2.2).astype(np.float32) / 255.0
        base_alpha = np.clip(edge_soft * 0.70 + fg_soft * 0.30, 0.0, 1.0)
        strength = float(np.clip(self._face_enhance.strength, 0.0, 1.0))
        edge_alpha = np.clip(base_alpha * strength, 0.0, 1.0)
        return edge_band, edge_alpha

    def _crop_face_alpha_to_output(self, rect) -> np.ndarray:
        if self._last_face_alpha_input.size == 0:
            return np.zeros((self._output_height, self._output_width), dtype=np.uint8)
        alpha_u8 = np.clip(self._last_face_alpha_input * 255.0, 0.0, 255.0).astype(np.uint8)
        return crop_and_resize(alpha_u8, rect, self._output_width, self._output_height)

    def _crop_face_edge_to_output(self, rect) -> np.ndarray:
        if self._last_face_edge_mask_input.size == 0:
            return np.zeros((self._output_height, self._output_width), dtype=np.uint8)
        return crop_and_resize(self._last_face_edge_mask_input, rect, self._output_width, self._output_height)

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

    def _apply_face_deidentify(self, frame: np.ndarray) -> np.ndarray:
        if not self._face_enhance.deidentifyEnabled:
            self._last_deidentify_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            return frame
        if self._face_cascade is None:
            if not self._face_warned:
                print(
                    "[face] warning: deidentify enabled but face detector unavailable; skip deidentify.",
                    flush=True,
                )
                self._face_warned = True
            self._last_deidentify_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            return frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            self._last_deidentify_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            return frame
        out = frame.copy()
        h, w = out.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
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
            cv2.rectangle(mask, (x0, eye_band_y0), (x1, eye_band_y1), 255, thickness=-1)
        self._last_deidentify_mask = mask
        return out

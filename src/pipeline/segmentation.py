from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os

import cv2
import numpy as np

from src.domain.config import SegmentationConfig


class Segmenter:
    def segment(self, frame: np.ndarray) -> np.ndarray:
        raise NotImplementedError


@dataclass
class MockSegmenter(Segmenter):
    def segment(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.float32)
        center = (width // 2, height // 2)
        axes = (max(1, width // 4), max(1, height // 3))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
        return mask


@dataclass
class FaceSegmenter(Segmenter):
    min_size_ratio: float = 0.08
    last_box: Optional[tuple[int, int, int, int]] = None
    frame_index: int = 0
    detection_interval: int = 3
    detect_downscale: float = 0.5
    debug: bool = False
    edge_success_count: int = 0
    ellipse_fallback_count: int = 0
    face_fallback_count: int = 0
    no_detection_count: int = 0

    def __post_init__(self) -> None:
        self.debug = os.getenv("SEGMENTATION_DEBUG", "0") == "1"
        face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        upper_cascade_path = cv2.data.haarcascades + "haarcascade_upperbody.xml"
        self._face_cascade = cv2.CascadeClassifier(face_cascade_path)
        self._upper_cascade = cv2.CascadeClassifier(upper_cascade_path)
        if self._face_cascade.empty():
            raise RuntimeError(f"Failed to load face cascade: {face_cascade_path}")
        if self._upper_cascade.empty():
            raise RuntimeError(f"Failed to load upper-body cascade: {upper_cascade_path}")

    def segment(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.float32)
        self.frame_index += 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        min_side = max(24, int(min(width, height) * self.min_size_ratio))
        upper_bodies, faces = self._detect_boxes(gray, min_side)

        if len(upper_bodies) > 0:
            x, y, w, h = max(upper_bodies, key=lambda box: box[2] * box[3])
            self.last_box = (int(x), int(y), int(w), int(h))
            if self._mask_from_upperbody_edges(gray, mask, x, y, w, h):
                self.edge_success_count += 1
                self._maybe_debug_log()
                return mask
            self.ellipse_fallback_count += 1
            cx = x + w // 2
            cy = y + int(h * 0.55)
            axes_x = max(1, int(w * 0.62))
            axes_y = max(1, int(h * 0.62))
            cv2.ellipse(mask, (cx, cy), (axes_x, axes_y), 0, 0, 360, 1.0, -1)
            self._maybe_debug_log()
            return mask

        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
            self.last_box = (int(x), int(y), int(w), int(h))
            self.face_fallback_count += 1
        elif self.last_box is None:
            self.no_detection_count += 1
            self._maybe_debug_log()
            return mask

        x, y, w, h = self.last_box

        cx = x + w // 2
        cy = y + int(h * 1.7)
        axes_x = max(1, int(w * 1.3))
        axes_y = max(1, int(h * 2.6))

        cv2.ellipse(mask, (cx, cy), (axes_x, axes_y), 0, 0, 360, 1.0, -1)
        self._maybe_debug_log()
        return mask

    def _maybe_debug_log(self) -> None:
        if not self.debug:
            return
        if self.frame_index % 30 != 0:
            return
        print(
            "[seg-debug] "
            f"frame={self.frame_index} "
            f"edge_success={self.edge_success_count} "
            f"ellipse_fallback={self.ellipse_fallback_count} "
            f"face_fallback={self.face_fallback_count} "
            f"no_detection={self.no_detection_count}"
        )

    def _detect_boxes(self, gray: np.ndarray, min_side: int):
        # Skip expensive cascade scans on some frames and reuse previous ROI.
        if self.last_box is not None and (self.frame_index % self.detection_interval) != 0:
            return [], []

        if 0.2 < self.detect_downscale < 1.0:
            small = cv2.resize(
                gray,
                (int(gray.shape[1] * self.detect_downscale), int(gray.shape[0] * self.detect_downscale)),
                interpolation=cv2.INTER_AREA,
            )
            scale = 1.0 / self.detect_downscale
            min_side_small = max(16, int(min_side * self.detect_downscale))
            upper_small = self._upper_cascade.detectMultiScale(
                small,
                scaleFactor=1.08,
                minNeighbors=3,
                minSize=(min_side_small * 2, min_side_small * 2),
            )
            face_small = self._face_cascade.detectMultiScale(
                small,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(min_side_small, min_side_small),
            )
            upper = [(int(x * scale), int(y * scale), int(w * scale), int(h * scale)) for x, y, w, h in upper_small]
            faces = [(int(x * scale), int(y * scale), int(w * scale), int(h * scale)) for x, y, w, h in face_small]
            return upper, faces

        upper = self._upper_cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=3,
            minSize=(min_side * 2, min_side * 2),
        )
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(min_side, min_side),
        )
        return upper, faces

    def _mask_from_upperbody_edges(
        self,
        gray: np.ndarray,
        mask: np.ndarray,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> bool:
        roi = gray[y : y + h, x : x + w]
        if roi.size == 0:
            return False

        roi_blur = cv2.GaussianBlur(roi, (5, 5), 0)
        edges = cv2.Canny(roi_blur, 30, 90)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)
        edges = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False

        min_area = max(120, int(w * h * 0.02))
        filtered = [cnt for cnt in contours if cv2.contourArea(cnt) >= min_area]
        if not filtered:
            return False

        largest = max(filtered, key=cv2.contourArea)
        hull = cv2.convexHull(largest)
        hull = hull + np.array([[[x, y]]], dtype=hull.dtype)
        cv2.drawContours(mask, [hull], -1, 1.0, thickness=-1)
        return True


@dataclass
class UnsupportedSegmenter(Segmenter):
    backend: str

    def segment(self, frame: np.ndarray) -> np.ndarray:
        raise NotImplementedError(
            f"Segmentation backend '{self.backend}' is not implemented yet. "
            "Use 'mock' for pipeline smoke tests."
        )


def build_segmenter(config: SegmentationConfig) -> Segmenter:
    if config.backend == "mock":
        return MockSegmenter()
    if config.backend == "face":
        return FaceSegmenter()
    if config.backend in {"tensorrt", "onnxruntime"}:
        return UnsupportedSegmenter(config.backend)
    raise ValueError(f"Unsupported segmentation backend: {config.backend}")

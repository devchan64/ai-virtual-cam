from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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

    def __post_init__(self) -> None:
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

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        min_side = max(24, int(min(width, height) * self.min_size_ratio))
        upper_bodies = self._upper_cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(min_side * 2, min_side * 2),
        )
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(min_side, min_side),
        )

        if len(upper_bodies) > 0:
            x, y, w, h = max(upper_bodies, key=lambda box: box[2] * box[3])
            self.last_box = (int(x), int(y), int(w), int(h))
            cx = x + w // 2
            cy = y + int(h * 0.55)
            axes_x = max(1, int(w * 0.62))
            axes_y = max(1, int(h * 0.62))
            cv2.ellipse(mask, (cx, cy), (axes_x, axes_y), 0, 0, 360, 1.0, -1)
            return mask

        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
            self.last_box = (int(x), int(y), int(w), int(h))
        elif self.last_box is None:
            return mask

        x, y, w, h = self.last_box

        cx = x + w // 2
        cy = y + int(h * 1.7)
        axes_x = max(1, int(w * 1.3))
        axes_y = max(1, int(h * 2.6))

        cv2.ellipse(mask, (cx, cy), (axes_x, axes_y), 0, 0, 360, 1.0, -1)
        return mask


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

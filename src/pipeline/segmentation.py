from __future__ import annotations

from dataclasses import dataclass

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
    if config.backend in {"tensorrt", "onnxruntime"}:
        return UnsupportedSegmenter(config.backend)
    raise ValueError(f"Unsupported segmentation backend: {config.backend}")

from __future__ import annotations

from dataclasses import dataclass
import platform

import cv2
import numpy as np

from src.domain.config import SegmentationConfig
try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None


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
        if self.backend == "tensorrt" and platform.system() == "Darwin":
            raise NotImplementedError(
                "Segmentation backend 'tensorrt' is unavailable on macOS. "
                "Use 'selfie', 'onnxruntime', or 'mock'."
            )
        raise NotImplementedError(
            f"Segmentation backend '{self.backend}' is not implemented yet. "
            "Use 'mock' for pipeline smoke tests."
        )


class MediaPipeSelfieSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        print("[seg] selfie backend: checking mediapipe dependency...")
        if mp is None:
            raise RuntimeError(
                "mediapipe is not installed. Install dependencies to use segmentation.backend=selfie."
            )
        if not hasattr(mp, "solutions"):
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                "Installed mediapipe package is incompatible (missing mediapipe.solutions). "
                f"Detected version: {version}. "
                "Run './bin/avc setup' to install the pinned compatible version."
            )
        print("[seg] selfie backend: initializing MediaPipe SelfieSegmentation model...")
        self._segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(
            model_selection=int(config.selfieModelSelection)
        )
        self._warmup_done = False
        self._smoothing = float(config.selfieTemporalSmoothing)
        self._prev_mask: np.ndarray | None = None
        print("[seg] selfie backend: model initialized")

    def segment(self, frame: np.ndarray) -> np.ndarray:
        if not self._warmup_done:
            print("[seg] selfie backend: running first inference (warm-up)...")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._segmenter.process(rgb)
        if not self._warmup_done:
            self._warmup_done = True
            print("[seg] selfie backend: warm-up complete")
        if result.segmentation_mask is None:
            return np.zeros(frame.shape[:2], dtype=np.float32)
        mask = result.segmentation_mask.astype(np.float32)
        if self._prev_mask is not None and self._smoothing > 0.0:
            mask = cv2.addWeighted(mask, 1.0 - self._smoothing, self._prev_mask, self._smoothing, 0.0)
        self._prev_mask = mask
        return mask


class OnnxRuntimeCompatSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        print(
            "[seg] onnxruntime backend: ONNX model runtime is not wired yet. "
            "Using selfie-compatible segmentation path as fallback."
        )
        self._delegate = MediaPipeSelfieSegmenter(config)

    def segment(self, frame: np.ndarray) -> np.ndarray:
        return self._delegate.segment(frame)


def build_segmenter(config: SegmentationConfig) -> Segmenter:
    if config.backend == "selfie":
        return MediaPipeSelfieSegmenter(config)
    if config.backend == "onnxruntime":
        return OnnxRuntimeCompatSegmenter(config)
    if config.backend == "mock":
        return MockSegmenter()
    if config.backend in {"tensorrt"}:
        return UnsupportedSegmenter(config.backend)
    raise ValueError(f"Unsupported segmentation backend: {config.backend}")

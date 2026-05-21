from __future__ import annotations

from dataclasses import dataclass

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
        if "temporalAlpha" in config.engineOptions:
            try:
                self._smoothing = float(config.engineOptions["temporalAlpha"])
            except (TypeError, ValueError):
                pass
        self._opts = dict(config.engineOptions)
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
        mask = _apply_engine_options(mask, self._opts)
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


class MediaPipeSelfieEnsembleSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        print("[seg] selfie_ensemble backend: checking mediapipe dependency...")
        if mp is None:
            raise RuntimeError(
                "mediapipe is not installed. Install dependencies to use segmentation.backend=selfie_ensemble."
            )
        if not hasattr(mp, "solutions"):
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                "Installed mediapipe package is incompatible (missing mediapipe.solutions). "
                f"Detected version: {version}. "
                "Run './bin/avc setup' to install the pinned compatible version."
            )
        print("[seg] selfie_ensemble backend: initializing model_selection=0/1 pair...")
        self._segmenter0 = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0)
        self._segmenter1 = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        self._warmup_done = False
        self._smoothing = float(config.selfieTemporalSmoothing)
        if "temporalAlpha" in config.engineOptions:
            try:
                self._smoothing = float(config.engineOptions["temporalAlpha"])
            except (TypeError, ValueError):
                pass
        self._blend = 0.5
        if "modelBlend" in config.engineOptions:
            try:
                self._blend = float(config.engineOptions["modelBlend"])
            except (TypeError, ValueError):
                self._blend = 0.5
        self._blend = max(0.0, min(1.0, self._blend))
        self._opts = dict(config.engineOptions)
        self._prev_mask: np.ndarray | None = None
        print(f"[seg] selfie_ensemble backend: model initialized (blend={self._blend:.2f})")

    def segment(self, frame: np.ndarray) -> np.ndarray:
        if not self._warmup_done:
            print("[seg] selfie_ensemble backend: running first inference (warm-up)...")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res0 = self._segmenter0.process(rgb)
        res1 = self._segmenter1.process(rgb)
        if not self._warmup_done:
            self._warmup_done = True
            print("[seg] selfie_ensemble backend: warm-up complete")
        if res0.segmentation_mask is None or res1.segmentation_mask is None:
            return np.zeros(frame.shape[:2], dtype=np.float32)
        mask0 = res0.segmentation_mask.astype(np.float32)
        mask1 = res1.segmentation_mask.astype(np.float32)
        mask = cv2.addWeighted(mask0, 1.0 - self._blend, mask1, self._blend, 0.0)
        if self._prev_mask is not None and self._smoothing > 0.0:
            mask = cv2.addWeighted(mask, 1.0 - self._smoothing, self._prev_mask, self._smoothing, 0.0)
        mask = _apply_engine_options(mask, self._opts)
        self._prev_mask = mask
        return mask


def _to_int_option(options: dict[str, object], key: str, default: int = 0) -> int:
    raw = options.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _to_float_option(options: dict[str, object], key: str, default: float = 0.0) -> float:
    raw = options.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _apply_engine_options(mask: np.ndarray, options: dict[str, object]) -> np.ndarray:
    out = np.clip(mask, 0.0, 1.0).astype(np.float32)
    blur_kernel = _to_int_option(options, "maskBlur", 0)
    if blur_kernel > 0:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        out = cv2.GaussianBlur(out, (blur_kernel, blur_kernel), 0)
    morph_open = max(0, _to_int_option(options, "morphOpen", 0))
    morph_close = max(0, _to_int_option(options, "morphClose", 0))
    if morph_open > 0:
        k = np.ones((morph_open, morph_open), np.uint8)
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, k)
    if morph_close > 0:
        k = np.ones((morph_close, morph_close), np.uint8)
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, k)
    gamma = _to_float_option(options, "maskGamma", 1.0)
    if gamma > 0.01 and abs(gamma - 1.0) > 1e-3:
        out = np.power(np.clip(out, 0.0, 1.0), gamma).astype(np.float32)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def build_segmenter(config: SegmentationConfig) -> Segmenter:
    if config.backend == "selfie":
        return MediaPipeSelfieSegmenter(config)
    if config.backend == "selfie_ensemble":
        return MediaPipeSelfieEnsembleSegmenter(config)
    if config.backend == "onnxruntime":
        return OnnxRuntimeCompatSegmenter(config)
    if config.backend == "mock":
        return MockSegmenter()
    if config.backend in {"tensorrt"}:
        return UnsupportedSegmenter(config.backend)
    raise ValueError(f"Unsupported segmentation backend: {config.backend}")

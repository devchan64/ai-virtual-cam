from __future__ import annotations

import cv2
import numpy as np

from src.domain.config import InputCameraConfig


class OpenCVCapture:
    def __init__(self, config: InputCameraConfig) -> None:
        self._config = config
        source = _resolve_source(config.devicePath)
        print(f"[capture] opening source: {config.devicePath} (resolved={source})", flush=True)
        self._capture = cv2.VideoCapture(source)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        self._capture.set(cv2.CAP_PROP_FPS, config.fps)

        if not self._capture.isOpened():
            raise RuntimeError(f"Failed to open input camera: {config.devicePath}")
        print("[capture] input camera opened", flush=True)

    def read(self) -> np.ndarray:
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from capture device")

        crop = self._config.crop
        base = frame[crop.y : crop.y + crop.height, crop.x : crop.x + crop.width]
        if base.size == 0:
            raise RuntimeError("Configured input crop produced an empty frame")
        return _apply_software_zoom(base, self._config.softwareZoom)

    def release(self) -> None:
        self._capture.release()


def _resolve_source(device_path: str):
    normalized = device_path.strip()
    if normalized.isdigit():
        return int(normalized)
    return normalized


def _apply_software_zoom(frame: np.ndarray, zoom: float) -> np.ndarray:
    if zoom <= 1.001:
        return frame.copy()
    h, w = frame.shape[:2]
    zoom_w = max(1, int(round(w / zoom)))
    zoom_h = max(1, int(round(h / zoom)))
    x0 = max(0, (w - zoom_w) // 2)
    y0 = max(0, (h - zoom_h) // 2)
    roi = frame[y0 : y0 + zoom_h, x0 : x0 + zoom_w]
    if roi.size == 0:
        return frame.copy()
    return cv2.resize(roi, (w, h), interpolation=cv2.INTER_LINEAR)

from __future__ import annotations

import cv2
import numpy as np

from src.domain.config import InputCameraConfig


class OpenCVCapture:
    def __init__(self, config: InputCameraConfig) -> None:
        self._config = config
        self._capture = cv2.VideoCapture(config.devicePath)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        self._capture.set(cv2.CAP_PROP_FPS, config.fps)

        if not self._capture.isOpened():
            raise RuntimeError(f"Failed to open input camera: {config.devicePath}")

    def read(self) -> np.ndarray:
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from capture device")

        crop = self._config.crop
        return frame[crop.y : crop.y + crop.height, crop.x : crop.x + crop.width].copy()

    def release(self) -> None:
        self._capture.release()

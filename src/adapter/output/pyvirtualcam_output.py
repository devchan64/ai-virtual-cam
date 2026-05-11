from __future__ import annotations

import cv2
import numpy as np

from src.adapter.output.base import OutputSink
from src.domain.config import OutputCameraConfig

try:
    import pyvirtualcam
except ImportError:  # pragma: no cover
    pyvirtualcam = None


class PyVirtualCamOutput(OutputSink):
    def __init__(self, config: OutputCameraConfig) -> None:
        if pyvirtualcam is None:
            raise RuntimeError(
                "pyvirtualcam is not installed. Install requirements to use outputCamera.backend=pyvirtualcam."
            )
        self._config = config
        self._cam = pyvirtualcam.Camera(
            width=int(config.width),
            height=int(config.height),
            fps=int(config.fps),
        )

    def write(self, frame: np.ndarray) -> None:
        if frame.shape[1] != self._config.width or frame.shape[0] != self._config.height:
            frame = cv2.resize(
                frame,
                (self._config.width, self._config.height),
                interpolation=cv2.INTER_LINEAR,
            )
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._cam.send(rgb_frame)
        self._cam.sleep_until_next_frame()

    def release(self) -> None:
        self._cam.close()

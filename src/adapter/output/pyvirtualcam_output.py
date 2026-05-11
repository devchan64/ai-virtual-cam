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
                "pyvirtualcam is not installed. This backend is legacy on macOS.\n"
                "Use outputCamera.backend=cmio as the official OBS-free path, or install pyvirtualcam for temporary fallback."
            )
        self._config = config
        try:
            self._cam = pyvirtualcam.Camera(
                width=int(config.width),
                height=int(config.height),
                fps=int(config.fps),
            )
        except RuntimeError as exc:
            message = str(exc)
            if "OBS Virtual Camera is not installed" in message:
                raise RuntimeError(
                    "pyvirtualcam legacy backend requires OBS Virtual Camera on macOS.\n"
                    "Project direction is OBS-free via outputCamera.backend=cmio.\n"
                    "Until CMIO runtime is implemented, use outputCamera.backend=opencv for local output,"
                    " or keep pyvirtualcam+OBS as temporary fallback."
                ) from exc
            raise

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

from __future__ import annotations

import numpy as np

from src.adapter.output.base import OutputSink
from src.domain.config import OutputCameraConfig


class CmioOutput(OutputSink):
    def __init__(self, config: OutputCameraConfig) -> None:
        self._config = config
        raise RuntimeError(
            "outputCamera.backend=cmio is selected, but CMIO camera extension runtime is not implemented yet.\n"
            "This project is moving to OBS-free macOS virtual camera via CoreMediaIO.\n"
            "Current options:\n"
            "1) Use outputCamera.backend=opencv for local file sink.\n"
            "2) Use outputCamera.backend=pyvirtualcam only as temporary legacy fallback."
        )

    def write(self, frame: np.ndarray) -> None:
        raise RuntimeError("CMIO output is not available yet.")

    def release(self) -> None:
        return None

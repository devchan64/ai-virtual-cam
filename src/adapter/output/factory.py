from __future__ import annotations

from src.adapter.output.opencv_output import OpenCVOutput
from src.adapter.output.pyvirtualcam_output import PyVirtualCamOutput
from src.domain.config import OutputCameraConfig


def build_output(config: OutputCameraConfig):
    if config.backend == "opencv":
        return OpenCVOutput(config)
    if config.backend == "pyvirtualcam":
        return PyVirtualCamOutput(config)
    raise ValueError(f"Unsupported output backend: {config.backend}")

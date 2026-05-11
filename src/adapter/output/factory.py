from __future__ import annotations

from src.adapter.output.opencv_output import OpenCVOutput
from src.adapter.output.macos.pyvirtualcam_output import PyVirtualCamOutput
from src.adapter.output.linux.v4l2loopback_output import V4L2LoopbackOutput
from src.domain.config import OutputCameraConfig


def build_output(config: OutputCameraConfig):
    if config.backend == "opencv":
        return OpenCVOutput(config)
    if config.backend == "pyvirtualcam":
        return PyVirtualCamOutput(config)
    if config.backend == "v4l2loopback":
        return V4L2LoopbackOutput(config)
    raise ValueError(f"Unsupported output backend: {config.backend}")

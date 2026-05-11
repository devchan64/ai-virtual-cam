"""Output adapters for virtual camera and local preview sinks."""
from src.adapter.output.factory import build_output
from src.adapter.output.linux.v4l2loopback_output import V4L2LoopbackOutput
from src.adapter.output.macos.pyvirtualcam_output import PyVirtualCamOutput
from src.adapter.output.opencv_output import OpenCVOutput

__all__ = [
    "build_output",
    "OpenCVOutput",
    "PyVirtualCamOutput",
    "V4L2LoopbackOutput",
]

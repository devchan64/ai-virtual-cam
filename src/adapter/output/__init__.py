"""Output adapters for virtual camera and local preview sinks."""
from src.adapter.output.factory import build_output
from src.adapter.output.opencv_output import OpenCVOutput
from src.adapter.output.pyvirtualcam_output import PyVirtualCamOutput

__all__ = [
    "build_output",
    "OpenCVOutput",
    "PyVirtualCamOutput",
]

from __future__ import annotations

from src.adapter.output.opencv_output import OpenCVOutput
from src.domain.config import OutputCameraConfig


def build_output(config: OutputCameraConfig):
    if config.backend == "opencv":
        return OpenCVOutput(config)
    raise ValueError(f"Unsupported output backend: {config.backend}")

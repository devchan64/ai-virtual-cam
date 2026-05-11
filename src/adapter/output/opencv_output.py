from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.domain.config import OutputCameraConfig


class OpenCVOutput:
    def __init__(self, config: OutputCameraConfig) -> None:
        self._config = config
        self._writer = self._build_writer(config)

    def _build_writer(self, config: OutputCameraConfig) -> cv2.VideoWriter:
        path = Path(config.devicePath)
        path.parent.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(path),
            fourcc,
            float(config.fps),
            (int(config.width), int(config.height)),
        )
        if not writer.isOpened():
            raise RuntimeError(f"Failed to open output writer: {config.devicePath}")
        return writer

    def write(self, frame: np.ndarray) -> None:
        if frame.shape[1] != self._config.width or frame.shape[0] != self._config.height:
            frame = cv2.resize(
                frame,
                (self._config.width, self._config.height),
                interpolation=cv2.INTER_LINEAR,
            )
        self._writer.write(frame)

    def release(self) -> None:
        self._writer.release()

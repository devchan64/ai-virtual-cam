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
                "pyvirtualcam이 설치되어 있지 않습니다. macOS OBS 경로를 사용하려면 ./bin/avc setup을 실행하세요."
            )
        self._config = config
        try:
            self._cam = pyvirtualcam.Camera(
                width=int(config.width),
                height=int(config.height),
                fps=int(config.fps),
            )
        except RuntimeError as exc:
            raise RuntimeError(
                "OBS Virtual Camera가 준비되지 않았습니다.\n"
                "1) OBS Studio를 실행\n"
                "2) Virtual Camera를 한 번 시작\n"
                "3) 다시 ./bin/avc serve 실행"
            ) from exc

    def write(self, frame: np.ndarray) -> None:
        if frame.shape[1] != self._config.width or frame.shape[0] != self._config.height:
            frame = cv2.resize(frame, (self._config.width, self._config.height), interpolation=cv2.INTER_LINEAR)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._cam.send(rgb_frame)
        self._cam.sleep_until_next_frame()

    def release(self) -> None:
        self._cam.close()

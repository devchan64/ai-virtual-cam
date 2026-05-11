from __future__ import annotations

import cv2
import numpy as np
from importlib import metadata

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
        self._frames_sent = 0
        try:
            self._cam = pyvirtualcam.Camera(
                width=int(config.width),
                height=int(config.height),
                fps=int(config.fps),
            )
            backend_name = getattr(self._cam, "backend", "unknown")
            device_name = getattr(self._cam, "device", "unknown")
            print(
                f"[output] pyvirtualcam opened: {config.width}x{config.height}@{config.fps} backend={backend_name} device={device_name}",
                flush=True,
            )
        except RuntimeError as exc:
            try:
                pyvirtualcam_version = metadata.version("pyvirtualcam")
            except Exception:
                pyvirtualcam_version = "unknown"
            raise RuntimeError(
                "OBS Virtual Camera가 준비되지 않았습니다.\n"
                f"- pyvirtualcam 버전: {pyvirtualcam_version}\n"
                "1) OBS Studio를 실행\n"
                "2) Virtual Camera를 한 번 시작 후 중지\n"
                "3) OBS를 완전히 종료\n"
                "4) ./bin/avc setup 실행(호환 버전 재설치)\n"
                "5) 다시 ./bin/avc serve 실행"
            ) from exc

    def write(self, frame: np.ndarray) -> None:
        if frame.shape[1] != self._config.width or frame.shape[0] != self._config.height:
            frame = cv2.resize(frame, (self._config.width, self._config.height), interpolation=cv2.INTER_LINEAR)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._cam.send(rgb_frame)
        self._cam.sleep_until_next_frame()
        self._frames_sent += 1
        if self._frames_sent == 1:
            print("[output] first frame sent to virtual camera", flush=True)
        elif self._frames_sent % 120 == 0:
            print(f"[output] streaming ok: frames_sent={self._frames_sent}", flush=True)

    def release(self) -> None:
        self._cam.close()

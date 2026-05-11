from __future__ import annotations

import socket
from pathlib import Path

import cv2
import numpy as np

from src.adapter.output.base import OutputSink
from src.domain.config import OutputCameraConfig


class CmioOutput(OutputSink):
    def __init__(self, config: OutputCameraConfig) -> None:
        self._config = config
        self._socket_path = Path("/tmp/avc-cmio.sock")
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._connect_bridge()

    def _connect_bridge(self) -> None:
        if not self._socket_path.exists():
            raise RuntimeError(
                "CMIO host bridge socket not found: /tmp/avc-cmio.sock\n"
                "Run './bin/avc setup' first, then start CMIO host runtime (Xcode AVCVirtualCamHost scheme).\n"
                "If you only want pipeline test output, set outputCamera.backend=opencv."
            )
        try:
            self._sock.connect(str(self._socket_path))
        except OSError as exc:
            raise RuntimeError(
                "Failed to connect CMIO host bridge socket.\n"
                "Make sure CMIO host runtime is running and listening on /tmp/avc-cmio.sock."
            ) from exc

    def write(self, frame: np.ndarray) -> None:
        if frame.shape[1] != self._config.width or frame.shape[0] != self._config.height:
            frame = cv2.resize(
                frame,
                (self._config.width, self._config.height),
                interpolation=cv2.INTER_LINEAR,
            )
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise RuntimeError("Failed to encode CMIO frame.")
        payload = encoded.tobytes()
        header = len(payload).to_bytes(4, byteorder="big", signed=False)
        try:
            self._sock.sendall(header + payload)
        except OSError as exc:
            raise RuntimeError("CMIO bridge write failed. Host runtime may have stopped.") from exc

    def release(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

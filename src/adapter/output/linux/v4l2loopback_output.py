from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np

from src.adapter.output.base import OutputSink
from src.domain.config import OutputCameraConfig


def _read_v4l2_node_name(video_path: str) -> str:
    try:
        return (
            (Path("/sys/class/video4linux") / Path(video_path).name / "name")
            .read_text(encoding="utf-8")
            .strip()
        )
    except Exception:
        return ""


def _is_virtual_v4l2_node(video_path: str) -> bool:
    try:
        target = os.path.realpath(str(Path("/sys/class/video4linux") / Path(video_path).name / "device"))
        return "/virtual/" in target.lower()
    except Exception:
        return False


def _iter_v4l2_devices() -> list[str]:
    root = Path("/sys/class/video4linux")
    if not root.exists():
        return []
    devices: list[str] = []
    for entry in sorted(root.glob("video*")):
        if not entry.is_dir():
            continue
        dev_path = Path("/dev") / entry.name
        if dev_path.exists():
            devices.append(str(dev_path))
    return devices


def _resolve_v4l2_device(configured: str) -> str:
    configured_path = Path(configured)
    if configured_path.exists():
        return str(configured_path)

    candidates = _iter_v4l2_devices()
    if candidates:
        for candidate in candidates:
            if "ai-virtual-cam" in _read_v4l2_node_name(candidate).lower():
                print(
                    f"[output] configured v4l2 device not found: {configured} "
                    f"-> fallback labeled node: {candidate}",
                    flush=True,
                )
                return candidate

        for candidate in candidates:
            if _is_virtual_v4l2_node(candidate):
                print(
                    f"[output] configured v4l2 device not found: {configured} "
                    f"-> fallback virtual node: {candidate}",
                    flush=True,
                )
                return candidate

    default_fallback = "/dev/video10"
    if default_fallback in candidates:
        print(
            f"[output] configured v4l2 device not found: {configured} "
            f"-> fallback {default_fallback}",
            flush=True,
        )
        return default_fallback

    if candidates:
        print(
            f"[output] configured v4l2 device not found: {configured} "
            f"-> fallback first node: {candidates[0]}",
            flush=True,
        )
        return candidates[0]

    return configured


class V4L2LoopbackOutput(OutputSink):
    """Linux v4l2loopback output scaffold.

    This sends BGR frames to ffmpeg stdin and lets ffmpeg publish to a v4l2 device.
    """

    def __init__(self, config: OutputCameraConfig) -> None:
        self._config = config
        self._device_path = _resolve_v4l2_device(config.devicePath)
        if self._device_path != config.devicePath:
            print(
                f"[output] v4l2loopback resolved: configured={config.devicePath} -> {self._device_path}",
                flush=True,
            )
        self._proc = self._spawn_ffmpeg(config, self._device_path)
        self._frames_sent = 0
        print(
            f"[output] v4l2loopback opened: {config.width}x{config.height}@{config.fps} -> {config.devicePath}",
            flush=True,
        )
        print(f"[output] v4l2loopback actual device: {self._device_path}", flush=True)

    def _spawn_ffmpeg(
        self, config: OutputCameraConfig, device_path: str
    ) -> subprocess.Popen[bytes]:
        if os.name != "posix":
            raise RuntimeError("v4l2loopback backend is Linux-only.")
        if not os.path.exists(device_path):
            raise RuntimeError(
                f"v4l2 output device not found: {device_path}\n"
                "Run './bin/avc setup' and ensure v4l2loopback device is created."
            )
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg not found. Run './bin/avc setup' first.")

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{config.width}x{config.height}",
            "-r",
            str(config.fps),
            "-i",
            "-",
            "-an",
            "-f",
            "v4l2",
            "-pix_fmt",
            "yuv420p",
            device_path,
        ]
        try:
            return subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to start ffmpeg for v4l2 output: {exc}") from exc

    def write(self, frame: np.ndarray) -> None:
        if self._proc.stdin is None:
            raise RuntimeError("v4l2loopback ffmpeg stdin is not available.")
        if frame.shape[1] != self._config.width or frame.shape[0] != self._config.height:
            frame = cv2.resize(frame, (self._config.width, self._config.height), interpolation=cv2.INTER_LINEAR)
        try:
            self._proc.stdin.write(frame.tobytes())
            self._frames_sent += 1
            if self._frames_sent == 1:
                print("[output] first frame sent to v4l2loopback device", flush=True)
            elif self._frames_sent % 120 == 0:
                print(f"[output] streaming ok: frames_sent={self._frames_sent}", flush=True)
        except BrokenPipeError as exc:
            raise RuntimeError("ffmpeg pipe to v4l2loopback is broken.") from exc

    def release(self) -> None:
        if self._proc.stdin is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
        try:
            self._proc.wait(timeout=2)
        except Exception:
            self._proc.kill()

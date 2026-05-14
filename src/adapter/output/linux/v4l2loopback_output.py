from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

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
        self._ffmpeg_formats = ["yuv420p", "yuyv422", "nv12", "bgr24"]
        self._format_index = 0
        self._proc = self._spawn_ffmpeg(config, self._device_path)
        self._frames_sent = 0
        print(
            f"[output] v4l2loopback opened: {config.width}x{config.height}@{config.fps} -> {config.devicePath}",
            flush=True,
        )
        print(f"[output] v4l2loopback actual device: {self._device_path}", flush=True)

    def _make_ffmpeg_cmd(self, config: OutputCameraConfig, device_path: str, pixel_format: str) -> list[str]:
        return [
            "ffmpeg",
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
            "-vf",
            f"format={pixel_format}",
            "-f",
            "v4l2",
            "-pix_fmt",
            pixel_format,
            device_path,
        ]

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

        last_error = "not started"
        for idx, fmt in enumerate(self._ffmpeg_formats):
            cmd = self._make_ffmpeg_cmd(config, device_path, fmt)
            cmd[0] = ffmpeg
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            except Exception as exc:  # pragma: no cover
                last_error = f"spawn_failed format={fmt}: {exc}"
                continue

            time.sleep(0.2)
            if proc.poll() is not None:
                stderr_msg = ""
                if proc.stderr is not None:
                    try:
                        stderr_msg = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                    except Exception:
                        stderr_msg = ""
                last_error = f"format={fmt} exit_code={proc.returncode} err={stderr_msg}"
                try:
                    proc.kill()
                except Exception:
                    pass
                continue

            print(f"[output] v4l2loopback ffmpeg started with pix_fmt={fmt}", flush=True)
            self._format_index = idx
            return proc

        raise RuntimeError(f"Failed to start ffmpeg for v4l2 output. {last_error}")

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
            if self._format_index < len(self._ffmpeg_formats) - 1:
                retry_fmt = self._ffmpeg_formats[self._format_index + 1]
                print(
                    f"[output] v4l2loopback stream error; retrying with pix_fmt={retry_fmt}",
                    flush=True,
                )
                self._format_index += 1
                if self._proc is not None:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = self._spawn_ffmpeg(self._config, self._device_path)
                self._frames_sent = 0
                return self.write(frame)
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

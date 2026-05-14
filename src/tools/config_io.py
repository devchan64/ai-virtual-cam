from __future__ import annotations

import json
import platform
from pathlib import Path
from src.tools.camera_devices import (
    discover_camera_fps_options_linux,
    discover_camera_fps_options_macos,
    discover_camera_mode_options_linux,
    discover_camera_mode_options_macos,
    discover_camera_resolution_options_linux,
    discover_camera_resolution_options_macos,
    discover_cameras_linux,
    discover_cameras_macos,
)


def discover_cameras() -> list[dict[str, str]]:
    if platform.system() == "Darwin":
        return discover_cameras_macos()
    return discover_cameras_linux()


def write_config(output_path: str, config: dict) -> None:
    output_file = Path(output_path).expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def discover_camera_fps_options(device_path: str) -> list[str]:
    if platform.system() == "Darwin":
        return discover_camera_fps_options_macos(device_path)
    return discover_camera_fps_options_linux(device_path)


def discover_camera_resolution_options(device_path: str) -> list[tuple[int, int]]:
    if platform.system() == "Darwin":
        return discover_camera_resolution_options_macos(device_path)
    return discover_camera_resolution_options_linux(device_path)


def discover_camera_mode_options(device_path: str) -> list[tuple[int, int, str]]:
    if platform.system() == "Darwin":
        return discover_camera_mode_options_macos(device_path)
    return discover_camera_mode_options_linux(device_path)

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DEFAULT_FPS = ["15", "24", "30", "60"]
DEFAULT_RESOLUTIONS = [(1280, 720), (1920, 1080), (640, 480)]
DEFAULT_MODES = [(1280, 720, "30"), (1920, 1080, "30"), (640, 480, "30")]


def discover_cameras() -> list[dict[str, str]]:
    cameras: list[dict[str, str]] = []
    video_root = Path("/sys/class/video4linux")
    if not video_root.exists():
        return cameras

    for entry in sorted(video_root.iterdir()):
        device_path = Path("/dev") / entry.name
        name_path = entry / "name"
        label = entry.name
        if name_path.exists():
            label = name_path.read_text(encoding="utf-8").strip()
        cameras.append(
            {
                "name": entry.name,
                "devicePath": str(device_path),
                "label": label,
            }
        )
    return cameras


def discover_camera_fps_options(device_path: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return DEFAULT_FPS

    if proc.returncode != 0:
        return DEFAULT_FPS

    fps_values: set[str] = set()
    for match in re.finditer(r"\(([\d.]+)\s+fps\)", proc.stdout):
        raw = match.group(1)
        try:
            value = float(raw)
        except ValueError:
            continue
        if abs(value - round(value)) < 1e-6:
            fps_values.add(str(int(round(value))))
        else:
            fps_values.add(f"{value:.2f}".rstrip("0").rstrip("."))

    if not fps_values:
        return DEFAULT_FPS
    return sorted(fps_values, key=lambda v: float(v))


def discover_camera_resolution_options(device_path: str) -> list[tuple[int, int]]:
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return DEFAULT_RESOLUTIONS

    if proc.returncode != 0:
        return DEFAULT_RESOLUTIONS

    pairs: set[tuple[int, int]] = set()
    for m in re.finditer(r"Size:\s+Discrete\s+(\d+)x(\d+)", proc.stdout):
        w = int(m.group(1))
        h = int(m.group(2))
        if w > 0 and h > 0:
            pairs.add((w, h))

    if not pairs:
        return DEFAULT_RESOLUTIONS
    return sorted(pairs, key=lambda p: (p[0] * p[1], p[0], p[1]))


def discover_camera_mode_options(device_path: str) -> list[tuple[int, int, str]]:
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return DEFAULT_MODES
    if proc.returncode != 0:
        return DEFAULT_MODES

    modes: set[tuple[int, int, str]] = set()
    current_w = None
    current_h = None
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        m_size = re.search(r"Size:\s+Discrete\s+(\d+)x(\d+)", line)
        if m_size:
            current_w = int(m_size.group(1))
            current_h = int(m_size.group(2))
            continue
        m_fps = re.search(r"\(([\d.]+)\s+fps\)", line)
        if m_fps and current_w and current_h:
            value = float(m_fps.group(1))
            fps = str(int(round(value))) if abs(value - round(value)) < 1e-6 else f"{value:.2f}".rstrip("0").rstrip(".")
            modes.add((current_w, current_h, fps))

    if not modes:
        return DEFAULT_MODES
    return sorted(modes, key=lambda x: (x[0] * x[1], x[0], x[1], float(x[2])))

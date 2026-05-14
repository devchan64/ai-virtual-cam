from __future__ import annotations

DEFAULT_FPS = ["15", "24", "30", "60"]
DEFAULT_RESOLUTIONS = [(1280, 720), (1920, 1080), (640, 480)]
DEFAULT_MODES = [(1280, 720, "30"), (1920, 1080, "30"), (640, 480, "30")]


def discover_cameras() -> list[dict[str, str]]:
    return [
        {"name": f"cam{idx}", "devicePath": str(idx), "label": f"Camera Index {idx}"}
        for idx in range(4)
    ]


def discover_camera_fps_options(_device_path: str) -> list[str]:
    return DEFAULT_FPS


def discover_camera_resolution_options(_device_path: str) -> list[tuple[int, int]]:
    return DEFAULT_RESOLUTIONS


def discover_camera_mode_options(_device_path: str) -> list[tuple[int, int, str]]:
    return DEFAULT_MODES

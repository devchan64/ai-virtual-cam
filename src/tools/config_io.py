from __future__ import annotations

import json
import platform
from pathlib import Path


def discover_cameras() -> list[dict[str, str]]:
    if platform.system() == "Darwin":
        return [
            {"name": f"cam{idx}", "devicePath": str(idx), "label": f"Camera Index {idx}"}
            for idx in range(4)
        ]

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


def write_config(output_path: str, config: dict) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

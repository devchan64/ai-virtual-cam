from __future__ import annotations

import json
import re
from pathlib import Path

CONFIG_DEFAULT_WINDOW_GEOMETRY = "780x900"
DICTATION_AI_DEFAULT_WINDOW_GEOMETRY = "780x420"
WINDOW_GEOMETRY_FILE_NAME = "window-geometry.json"
MIN_WINDOW_WIDTH = 520
MIN_WINDOW_HEIGHT = 280

DEFAULT_WINDOW_GEOMETRY_META = {
    "windowGeometry": "780x900+0+0",
    "previewWindowGeometry": "640x480+80+80",
    "audioTuneWindowGeometry": "640x480+100+100",
    "audioGateTestWindowGeometry": "640x480+120+120",
    "inputMeterWindowGeometry": "640x480+140+140",
    "dictationAiInputMeterWindowGeometry": "640x480+180+180",
    "dictationAiWindowGeometry": "780x420+50+119",
    "dictationAiTranslationWindowGeometry": "780x420+860+119",
    "dictationAiSttStatusWindowGeometry": "780x420+50+560",
    "dictationAiModelDownloadWindowGeometry": "720x420+160+160",
}

_WINDOW_GEOMETRY_RE = re.compile(
    r"^(?P<width>\d+)x(?P<height>\d+)(?P<x_sign>[+-])(?P<x>\d+)(?P<y_sign>[+-])(?P<y>\d+)$"
)


def parse_window_geometry(geometry: object) -> dict[str, int] | None:
    if not isinstance(geometry, str):
        return None
    match = _WINDOW_GEOMETRY_RE.match(geometry.strip())
    if match is None:
        return None
    x = int(match.group("x"))
    y = int(match.group("y"))
    if match.group("x_sign") == "-":
        x = -x
    if match.group("y_sign") == "-":
        y = -y
    return {
        "width": int(match.group("width")),
        "height": int(match.group("height")),
        "x": x,
        "y": y,
    }


def format_window_geometry(parts: dict[str, int]) -> str:
    x = int(parts["x"])
    y = int(parts["y"])
    return f'{int(parts["width"])}x{int(parts["height"])}{x:+d}{y:+d}'


def window_restore_extent(root) -> tuple[int, int]:
    width = 0
    height = 0
    for width_name, height_name in (("winfo_vrootwidth", "winfo_vrootheight"), ("winfo_screenwidth", "winfo_screenheight")):
        try:
            width = max(width, int(getattr(root, width_name)()))
            height = max(height, int(getattr(root, height_name)()))
        except Exception:
            pass
    if width > 0:
        width *= 2
    if height > 0:
        height *= 2
    return width, height


def window_manager_geometry(window) -> str:
    try:
        geometry = window.geometry()
        if isinstance(geometry, str) and geometry.strip():
            return geometry
    except TypeError:
        pass
    except Exception:
        pass
    return window.winfo_geometry()


def sanitize_window_geometry(geometry: object, screen_width: int, screen_height: int) -> str | None:
    parts = parse_window_geometry(geometry)
    if parts is None:
        return None
    width = parts["width"]
    height = parts["height"]
    x = parts["x"]
    y = parts["y"]
    if width < MIN_WINDOW_WIDTH or height < MIN_WINDOW_HEIGHT:
        return None
    if screen_width <= 0 or screen_height <= 0:
        return format_window_geometry(parts)
    visible_margin = 80
    if x >= screen_width - visible_margin or y >= screen_height - visible_margin:
        return None
    if x + width <= visible_margin or y + height <= visible_margin:
        return None
    return format_window_geometry(parts)


def window_geometry_path(config_path: Path) -> Path:
    return config_path.expanduser().with_name(WINDOW_GEOMETRY_FILE_NAME)


def read_window_geometry_file(config_path: Path) -> dict[str, str]:
    geometry_path = window_geometry_path(config_path)
    if not geometry_path.exists():
        return {}
    raw = json.loads(geometry_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if str(key).endswith("Geometry") and isinstance(value, str)}


def write_window_geometry_file(config_path: Path, geometry: dict[str, str]) -> Path:
    geometry_path = window_geometry_path(config_path)
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        key: value
        for key, value in sorted(geometry.items())
        if str(key).endswith("Geometry") and isinstance(value, str)
    }
    geometry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return geometry_path


def read_legacy_window_geometry_meta(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return {}
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    meta = raw.get("meta") or {}
    if not isinstance(meta, dict):
        return {}
    return {str(key): value for key, value in meta.items() if str(key).endswith("Geometry") and isinstance(value, str)}

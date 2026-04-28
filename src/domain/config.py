from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_dict(cls, raw: dict) -> "Rect":
        rect = cls(
            x=int(raw["x"]),
            y=int(raw["y"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
        )
        rect.validate("rect")
        return rect

    def validate(self, label: str) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError(f"{label}: x and y must be >= 0")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"{label}: width and height must be > 0")


@dataclass(frozen=True)
class InputCameraConfig:
    devicePath: str
    width: int
    height: int
    fps: int
    crop: Rect

    @classmethod
    def from_dict(cls, raw: dict) -> "InputCameraConfig":
        config = cls(
            devicePath=str(raw["devicePath"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
            fps=int(raw["fps"]),
            crop=Rect.from_dict(raw.get("crop") or _default_rect(raw)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.devicePath:
            raise ValueError("inputCamera.devicePath is required")
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("inputCamera width/height/fps must be > 0")
        if self.crop.x + self.crop.width > self.width:
            raise ValueError("inputCamera.crop exceeds input width")
        if self.crop.y + self.crop.height > self.height:
            raise ValueError("inputCamera.crop exceeds input height")


@dataclass(frozen=True)
class OutputCameraConfig:
    devicePath: str
    width: int
    height: int
    fps: int

    @classmethod
    def from_dict(cls, raw: dict) -> "OutputCameraConfig":
        config = cls(
            devicePath=str(raw["devicePath"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
            fps=int(raw["fps"]),
        )
        if not config.devicePath:
            raise ValueError("outputCamera.devicePath is required")
        if config.width <= 0 or config.height <= 0 or config.fps <= 0:
            raise ValueError("outputCamera width/height/fps must be > 0")
        return config


@dataclass(frozen=True)
class SegmentationConfig:
    backend: str
    threshold: float

    @classmethod
    def from_dict(cls, raw: dict) -> "SegmentationConfig":
        config = cls(
            backend=str(raw["backend"]),
            threshold=float(raw["threshold"]),
        )
        if not 0.0 <= config.threshold <= 1.0:
            raise ValueError("segmentation.threshold must be between 0.0 and 1.0")
        return config


@dataclass(frozen=True)
class BackgroundConfig:
    mode: str
    chromaColor: tuple[int, int, int] | None
    imagePath: str | None
    crop: Rect | None

    @classmethod
    def from_dict(cls, raw: dict) -> "BackgroundConfig":
        mode = str(raw["mode"])
        chroma = raw.get("chromaColor")
        image_path = raw.get("imagePath")
        crop = Rect.from_dict(raw["crop"]) if raw.get("crop") else None

        config = cls(
            mode=mode,
            chromaColor=tuple(int(v) for v in chroma) if chroma else None,
            imagePath=str(image_path) if image_path else None,
            crop=crop,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode not in {"chroma", "image"}:
            raise ValueError("background.mode must be one of: chroma, image")
        if self.mode == "chroma":
            if self.chromaColor is None or len(self.chromaColor) != 3:
                raise ValueError("background.chromaColor must contain 3 values")
            if any(channel < 0 or channel > 255 for channel in self.chromaColor):
                raise ValueError("background.chromaColor must be in 0..255")
        if self.mode == "image":
            if not self.imagePath:
                raise ValueError("background.imagePath is required in image mode")
            if not Path(self.imagePath).exists():
                raise ValueError(f"background.imagePath not found: {self.imagePath}")


@dataclass(frozen=True)
class PersonCropConfig:
    margin: float
    smoothing: float

    @classmethod
    def from_dict(cls, raw: dict) -> "PersonCropConfig":
        config = cls(
            margin=float(raw["margin"]),
            smoothing=float(raw["smoothing"]),
        )
        if config.margin < 0.0:
            raise ValueError("crop.margin must be >= 0.0")
        if not 0.0 <= config.smoothing <= 1.0:
            raise ValueError("crop.smoothing must be between 0.0 and 1.0")
        return config


@dataclass(frozen=True)
class AppConfig:
    inputCamera: InputCameraConfig
    outputCamera: OutputCameraConfig
    segmentation: SegmentationConfig
    background: BackgroundConfig
    crop: PersonCropConfig

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            inputCamera=InputCameraConfig.from_dict(raw["inputCamera"]),
            outputCamera=OutputCameraConfig.from_dict(raw["outputCamera"]),
            segmentation=SegmentationConfig.from_dict(raw["segmentation"]),
            background=BackgroundConfig.from_dict(raw["background"]),
            crop=PersonCropConfig.from_dict(raw["crop"]),
        )


def _default_rect(raw: dict) -> dict:
    return {
        "x": 0,
        "y": 0,
        "width": int(raw["width"]),
        "height": int(raw["height"]),
    }

from __future__ import annotations

import json
import platform
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
    softwareZoom: float = 1.0

    @classmethod
    def from_dict(cls, raw: dict) -> "InputCameraConfig":
        config = cls(
            devicePath=str(raw["devicePath"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
            fps=int(raw["fps"]),
            crop=Rect.from_dict(raw.get("crop") or _default_rect(raw)),
            softwareZoom=float(raw.get("softwareZoom", 1.0)),
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
        if self.softwareZoom < 1.0 or self.softwareZoom > 4.0:
            raise ValueError("inputCamera.softwareZoom must be between 1.0 and 4.0")


@dataclass(frozen=True)
class OutputCameraConfig:
    devicePath: str
    width: int
    height: int
    fps: int
    backend: str = "opencv"

    @classmethod
    def from_dict(cls, raw: dict) -> "OutputCameraConfig":
        default_backend = "pyvirtualcam" if platform.system() == "Darwin" else "v4l2loopback"
        backend = str(raw.get("backend", default_backend))
        if platform.system() == "Darwin" and backend == "cmio":
            backend = "pyvirtualcam"
        config = cls(
            devicePath=str(raw["devicePath"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
            fps=int(raw["fps"]),
            backend=backend,
        )
        if not config.devicePath:
            raise ValueError("outputCamera.devicePath is required")
        if config.width <= 0 or config.height <= 0 or config.fps <= 0:
            raise ValueError("outputCamera width/height/fps must be > 0")
        if config.backend not in {"opencv", "pyvirtualcam", "v4l2loopback"}:
            raise ValueError("outputCamera.backend must be one of: opencv, pyvirtualcam, v4l2loopback")
        return config


@dataclass(frozen=True)
class SegmentationConfig:
    backend: str
    threshold: float
    selfieModelSelection: int = 1
    selfieTemporalSmoothing: float = 0.25
    edgeSmoothness: float = 0.5
    blendFeather: float = 0.35

    @classmethod
    def from_dict(cls, raw: dict) -> "SegmentationConfig":
        selfie = raw.get("selfie") or {}
        config = cls(
            backend=str(raw["backend"]),
            threshold=float(raw["threshold"]),
            selfieModelSelection=int(selfie.get("modelSelection", 1)),
            selfieTemporalSmoothing=float(selfie.get("temporalSmoothing", 0.25)),
            edgeSmoothness=float(raw.get("edgeSmoothness", 0.5)),
            blendFeather=float(raw.get("blendFeather", 0.35)),
        )
        if not 0.0 <= config.threshold <= 1.0:
            raise ValueError("segmentation.threshold must be between 0.0 and 1.0")
        if config.selfieModelSelection not in {0, 1}:
            raise ValueError("segmentation.selfie.modelSelection must be 0 or 1")
        if not 0.0 <= config.selfieTemporalSmoothing <= 0.95:
            raise ValueError("segmentation.selfie.temporalSmoothing must be between 0.0 and 0.95")
        if not 0.0 <= config.edgeSmoothness <= 1.0:
            raise ValueError("segmentation.edgeSmoothness must be between 0.0 and 1.0")
        if not 0.0 <= config.blendFeather <= 1.0:
            raise ValueError("segmentation.blendFeather must be between 0.0 and 1.0")
        return config


@dataclass(frozen=True)
class BackgroundConfig:
    mode: str
    chromaColor: tuple[int, int, int] | None
    imagePath: str | None
    crop: Rect | None
    colorBlendAlpha: float

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
            colorBlendAlpha=float(raw.get("colorBlendAlpha", 0.35)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode not in {"chroma", "image", "image_chroma"}:
            raise ValueError("background.mode must be one of: chroma, image, image_chroma")
        if self.mode in {"chroma", "image_chroma"}:
            if self.chromaColor is None or len(self.chromaColor) != 3:
                raise ValueError("background.chromaColor must contain 3 values")
            if any(channel < 0 or channel > 255 for channel in self.chromaColor):
                raise ValueError("background.chromaColor must be in 0..255")
        if self.mode in {"image", "image_chroma"}:
            if not self.imagePath:
                raise ValueError("background.imagePath is required in image/image_chroma mode")
            if not Path(self.imagePath).exists():
                raise ValueError(f"background.imagePath not found: {self.imagePath}")
        if not 0.0 <= self.colorBlendAlpha <= 1.0:
            raise ValueError("background.colorBlendAlpha must be between 0.0 and 1.0")


@dataclass(frozen=True)
class PersonCropConfig:
    margin: float
    panSmoothing: float
    tiltSmoothing: float
    upperBodyBias: float
    upperBodyRatio: float
    upperBodyEdgeSmoothing: float
    zoom: float
    zoomSmoothing: float
    panPidKp: float
    panPidKi: float
    panPidKd: float
    tiltPidKp: float
    tiltPidKi: float
    tiltPidKd: float
    panTargetOffsetX: float
    panTargetOffsetY: float

    @classmethod
    def from_dict(cls, raw: dict) -> "PersonCropConfig":
        pan_smoothing = raw.get("panSmoothing", raw.get("smoothing", 0.85))
        config = cls(
            margin=float(raw["margin"]),
            panSmoothing=float(pan_smoothing),
            tiltSmoothing=float(raw.get("tiltSmoothing", pan_smoothing)),
            upperBodyBias=float(raw.get("upperBodyBias", 0.0)),
            upperBodyRatio=float(raw.get("upperBodyRatio", 0.60)),
            upperBodyEdgeSmoothing=float(raw.get("upperBodyEdgeSmoothing", 0.35)),
            zoom=float(raw.get("zoom", 1.0)),
            zoomSmoothing=float(raw.get("zoomSmoothing", 0.80)),
            panPidKp=float(raw.get("panPidKp", 0.35)),
            panPidKi=float(raw.get("panPidKi", 0.01)),
            panPidKd=float(raw.get("panPidKd", 0.12)),
            tiltPidKp=float(raw.get("tiltPidKp", raw.get("panPidKp", 0.35))),
            tiltPidKi=float(raw.get("tiltPidKi", raw.get("panPidKi", 0.01))),
            tiltPidKd=float(raw.get("tiltPidKd", raw.get("panPidKd", 0.12))),
            panTargetOffsetX=float(raw.get("panTargetOffsetX", 0.0)),
            panTargetOffsetY=float(raw.get("panTargetOffsetY", 0.0)),
        )
        if config.margin < 0.0:
            raise ValueError("crop.margin must be >= 0.0")
        if not 0.0 <= config.panSmoothing <= 1.0:
            raise ValueError("crop.panSmoothing must be between 0.0 and 1.0")
        if not 0.0 <= config.tiltSmoothing <= 1.0:
            raise ValueError("crop.tiltSmoothing must be between 0.0 and 1.0")
        if not 0.0 <= config.upperBodyBias <= 1.0:
            raise ValueError("crop.upperBodyBias must be between 0.0 and 1.0")
        if not 0.2 <= config.upperBodyRatio <= 1.0:
            raise ValueError("crop.upperBodyRatio must be between 0.2 and 1.0")
        if not 0.0 <= config.upperBodyEdgeSmoothing <= 1.0:
            raise ValueError("crop.upperBodyEdgeSmoothing must be between 0.0 and 1.0")
        if not 1.0 <= config.zoom <= 4.0:
            raise ValueError("crop.zoom must be between 1.0 and 4.0")
        if not 0.0 <= config.zoomSmoothing <= 1.0:
            raise ValueError("crop.zoomSmoothing must be between 0.0 and 1.0")
        if config.panPidKp < 0.0 or config.panPidKi < 0.0 or config.panPidKd < 0.0:
            raise ValueError("crop.panPidKp/Ki/Kd must be >= 0.0")
        if config.tiltPidKp < 0.0 or config.tiltPidKi < 0.0 or config.tiltPidKd < 0.0:
            raise ValueError("crop.tiltPidKp/Ki/Kd must be >= 0.0")
        if not -1.0 <= config.panTargetOffsetX <= 1.0:
            raise ValueError("crop.panTargetOffsetX must be between -1.0 and 1.0")
        if not -1.0 <= config.panTargetOffsetY <= 1.0:
            raise ValueError("crop.panTargetOffsetY must be between -1.0 and 1.0")
        return config


@dataclass(frozen=True)
class AudioGateConfig:
    enabled: bool
    thresholdDb: float
    hysteresisDb: float
    attackMs: int
    holdMs: int
    releaseMs: int
    openGain: float
    closedGain: float
    minVoiceBandRatio: float

    @classmethod
    def from_dict(cls, raw: dict) -> "AudioGateConfig":
        config = cls(
            enabled=bool(raw.get("enabled", True)),
            thresholdDb=float(raw.get("thresholdDb", -42.0)),
            hysteresisDb=float(raw.get("hysteresisDb", 3.0)),
            attackMs=int(raw.get("attackMs", 20)),
            holdMs=int(raw.get("holdMs", 140)),
            releaseMs=int(raw.get("releaseMs", 220)),
            openGain=float(raw.get("openGain", 1.0)),
            closedGain=float(raw.get("closedGain", 0.0)),
            minVoiceBandRatio=float(raw.get("minVoiceBandRatio", 0.55)),
        )
        if config.attackMs < 0 or config.holdMs < 0 or config.releaseMs < 0:
            raise ValueError("audio.gate attack/hold/release must be >= 0")
        if config.openGain < 0.0 or config.closedGain < 0.0:
            raise ValueError("audio.gate openGain/closedGain must be >= 0.0")
        if config.minVoiceBandRatio < 0.0 or config.minVoiceBandRatio > 1.0:
            raise ValueError("audio.gate minVoiceBandRatio must be between 0.0 and 1.0")
        return config


@dataclass(frozen=True)
class AudioMixerConfig:
    enabled: bool
    inputDevice: str
    outputDevice: str
    sampleRate: int
    channels: int
    frameMs: int
    gate: AudioGateConfig

    @classmethod
    def from_dict(cls, raw: dict) -> "AudioMixerConfig":
        gate_raw = raw.get("gate") or {}
        config = cls(
            enabled=bool(raw.get("enabled", False)),
            inputDevice=str(raw.get("inputDevice", "default")),
            outputDevice=str(raw.get("outputDevice", "default")),
            sampleRate=int(raw.get("sampleRate", 48000)),
            channels=int(raw.get("channels", 1)),
            frameMs=int(raw.get("frameMs", 20)),
            gate=AudioGateConfig.from_dict(gate_raw),
        )
        if config.sampleRate <= 0:
            raise ValueError("audio.sampleRate must be > 0")
        if config.channels <= 0:
            raise ValueError("audio.channels must be > 0")
        if config.frameMs <= 0:
            raise ValueError("audio.frameMs must be > 0")
        return config


@dataclass(frozen=True)
class AppConfig:
    inputCamera: InputCameraConfig
    outputCamera: OutputCameraConfig
    segmentation: SegmentationConfig
    background: BackgroundConfig
    crop: PersonCropConfig
    audio: AudioMixerConfig | None = None

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        raw = json.loads(path.read_text(encoding="utf-8"))
        crop_cfg = PersonCropConfig.from_dict(raw["crop"])
        input_raw = dict(raw["inputCamera"])
        if "softwareZoom" not in input_raw:
            input_raw["softwareZoom"] = crop_cfg.zoom
        return cls(
            inputCamera=InputCameraConfig.from_dict(input_raw),
            outputCamera=OutputCameraConfig.from_dict(raw["outputCamera"]),
            segmentation=SegmentationConfig.from_dict(raw["segmentation"]),
            background=BackgroundConfig.from_dict(raw["background"]),
            crop=crop_cfg,
            audio=AudioMixerConfig.from_dict(raw["audio"]) if raw.get("audio") else None,
        )


def _default_rect(raw: dict) -> dict:
    return {
        "x": 0,
        "y": 0,
        "width": int(raw["width"]),
        "height": int(raw["height"]),
    }

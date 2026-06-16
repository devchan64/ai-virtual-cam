from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.domain.contracts.dictation_ai import (
    dictation_ai_spec,
    dictation_ai_stt_backends_for_language,
    dictation_ai_translation_backends_for_language,
    dictation_ai_translation_models_for_backend,
    dictation_ai_translation_targets_for_backend,
)
from src.domain.dictation_ai_defaults import dictation_ai_default


def _default_audio_output_device() -> str:
    if platform.system() != "Linux":
        return "default"
    try:
        import sounddevice as sd
    except Exception:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"

    # Prefer a PulseAudio sink name that is actually accepted by sounddevice.
    # In many environments, the virtual sink itself only appears as pactl short name,
    # while sounddevice sees `pulse` as the runtime endpoint.
    try:
        sound_devices = sd.query_devices()
        pulse_fallback: str | None = None
        first_non_default: str | None = None
        for d in sound_devices:
            dname = str(d.get("name", "")).strip()
            if not dname:
                continue
            if int(d.get("max_output_channels", 0)) <= 0:
                continue
            lowered = dname.lower()
            if "virtual" in lowered:
                return dname
            if lowered == "pulse":
                pulse_fallback = dname
            if first_non_default is None and "default" not in lowered:
                first_non_default = dname
            if pulse_fallback is None:
                pulse_fallback = first_non_default
        if pulse_fallback is not None:
            return pulse_fallback
    except Exception:
        pass

    try:
        proc = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        if proc.returncode == 0:
            default_name = proc.stdout.strip()
            if default_name and default_name.lower() != "default":
                return default_name
    except Exception:
        pass

    try:
        virtual_candidates: list[str] = []
        default_output_name: str | None = None
        index_output = sd.default.device[1] if sd.default.device is not None else None
        for device in sd.query_devices():
            name = str(device.get("name", ""))
            if int(device.get("max_output_channels", 0)) <= 0:
                continue
            lowered = name.lower()
            if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered:
                virtual_candidates.append(name)
            if (
                default_output_name is None
                and index_output is not None
                and isinstance(index_output, int)
                and sd.query_devices(index_output).get("name") == name
            ):
                default_output_name = name
        if virtual_candidates:
            return virtual_candidates[0]
        if (
            default_output_name is not None
            and "(hw:" not in default_output_name.lower()
            and "sof-hda" not in default_output_name.lower()
        ):
            return default_output_name
    except Exception:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"
    pactl_default = _pactl_default_audio_device("sink")
    if (
        pactl_default != "default"
        and "(hw:" not in pactl_default.lower()
        and "sof-hda" not in pactl_default.lower()
    ):
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    name = parts[1].strip()
                    lowered = name.lower()
                    if "virtual" in lowered or "ai-virtual-cam" in lowered:
                        if "(hw:" not in lowered and "sof-hda" not in lowered:
                            return name
        except Exception:
            pass
        return pactl_default
    return "pulse"


def _coerce_audio_output_device(device_name: str) -> str:
    def _monitor_to_sink(name: str) -> str:
        lowered = name.lower()
        if ".monitor" not in lowered:
            return name
        candidate = name[:-len(".monitor")] if lowered.endswith(".monitor") else name.split(".monitor", 1)[0]
        if not candidate:
            return name
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode == 0:
                sink_names = {
                    line.split()[1].strip()
                    for line in proc.stdout.splitlines()
                    if len(line.split()) >= 2
                }
                if candidate in sink_names:
                    return candidate
        except Exception:
            return candidate
        return name

    def _pick_virtual_output(names: list[str]) -> str | None:
        for candidate in names:
            lowered_candidate = candidate.lower()
            if "virtual" in lowered_candidate and "default" not in lowered_candidate:
                return candidate
        return None

    try:
        import sounddevice as sd
    except Exception:
        if str(device_name).strip() == "default":
            return "pulse"
        return _monitor_to_sink(device_name)

    if not isinstance(device_name, str):
        return device_name
    name = device_name.strip()
    if not name:
        return device_name

    lowered = name.lower()
    name = _monitor_to_sink(name)
    is_monitor = ".monitor" in lowered
    try:
        devices = sd.query_devices()
        names = [str(d.get("name", "")).strip() for d in devices if int(d.get("max_output_channels", 0)) > 0]
        if name in names:
            return name
        if is_monitor:
            return name
        if name == "default":
            virtual = _pick_virtual_output(names)
            if virtual is not None:
                return virtual
            if "pulse" in names:
                return "pulse"
            if names:
                return names[0]

        # If config uses PulseAudio short-name (e.g., ai-virtual-cam), force a safe default.
        if "ai-virtual-cam" in lowered or "virtual" in lowered:
            if "pulse" in names:
                return "pulse"
            virtual = _pick_virtual_output(names)
            if virtual is not None:
                return virtual
            if names:
                return names[0]

        # Fallback to explicit PulseAudio/PipeWire aggregate.
        if "pulse" in names and name == "pulse":
            return "pulse"
        if "pulse" in names:
            return "pulse"
    except Exception:
        pass
    return device_name


def _coerce_audio_input_device(device_name: str) -> str:
    try:
        import sounddevice as sd
    except Exception:
        return device_name

    if not isinstance(device_name, str):
        return device_name
    name = device_name.strip()
    if not name:
        return device_name

    lowered = name.lower()
    try:
        devices = sd.query_devices()
        names = [str(d.get("name", "")).strip() for d in devices if int(d.get("max_input_channels", 0)) > 0]
        names = [n for n in names if n]
        if not names:
            return device_name

        if name in names:
            return name

        if name == "default":
            if "default" in names:
                return "default"
            return names[0]

        if "pulse" in lowered and "pulse" in names:
            return "pulse"
        if "monitor" in lowered:
            for candidate in names:
                if "monitor" in candidate.lower():
                    return candidate
        if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered:
            for candidate in names:
                lower_candidate = candidate.lower()
                if "virtual" in lower_candidate or "monitor" in lower_candidate:
                    return candidate
            if "pulse" in names:
                return "pulse"

        return names[0]
    except Exception:
        pass
    return device_name


def _pactl_default_audio_device(kind: str) -> str:
    if platform.system() != "Linux" or kind not in {"source", "sink"}:
        return "default"
    try:
        proc = subprocess.run(
            ["pactl", f"get-default-{'source' if kind == 'source' else 'sink'}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except Exception:
        proc = None
    if proc is not None and proc.returncode == 0:
        default_name = proc.stdout.strip()
        if default_name:
            return default_name
    try:
        proc = subprocess.run(
            ["pactl", "list", "short", f"{kind}s"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                if not name:
                    continue
                lowered = name.lower()
                if "virtual" in lowered:
                    return name
                if "default" not in lowered:
                    return name
    except Exception:
        return "default"
    return "default"


def _default_audio_input_device() -> str:
    if platform.system() != "Linux":
        return "default"
    try:
        import sounddevice as sd
    except Exception:
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"

    try:
        default_input = sd.default.device[0] if sd.default.device is not None else None
        if isinstance(default_input, int):
            device = sd.query_devices(default_input)
            if device and int(device.get("max_input_channels", 0)) > 0:
                name = str(device.get("name", "")).strip()
                if name:
                    return name
    except Exception:
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"

    try:
        for device in sd.query_devices():
            if int(device.get("max_input_channels", 0)) <= 0:
                continue
            name = str(device.get("name", "")).strip()
            if not name:
                continue
            lowered = name.lower()
            if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered:
                return name
            if lowered not in {"default"}:
                return name
    except Exception:
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"
    pactl_default = _pactl_default_audio_device("source")
    return pactl_default if pactl_default != "default" else "default"


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
class CameraServerConfig:
    enabled: bool = True

    @classmethod
    def from_dict(cls, raw: dict | None) -> "CameraServerConfig":
        raw = raw or {}
        return cls(enabled=bool(raw.get("enabled", True)))


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
    enabled: bool
    backend: str
    threshold: float
    selfieModelSelection: int = 1
    selfieTemporalSmoothing: float = 0.25
    edgeSmoothness: float = 0.5
    blendFeather: float = 0.35
    engineOptions: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "SegmentationConfig":
        selfie = raw.get("selfie") or {}
        engine_options_all = raw.get("engineOptions") or {}
        backend = str(raw["backend"])
        selected_engine_options = {}
        if isinstance(engine_options_all, dict):
            raw_selected = engine_options_all.get(backend) or {}
            if isinstance(raw_selected, dict):
                selected_engine_options = dict(raw_selected)
        config = cls(
            enabled=bool(raw.get("enabled", True)),
            backend=backend,
            threshold=float(raw["threshold"]),
            selfieModelSelection=int(selfie.get("modelSelection", 1)),
            selfieTemporalSmoothing=float(selfie.get("temporalSmoothing", 0.25)),
            edgeSmoothness=float(raw.get("edgeSmoothness", 0.5)),
            blendFeather=float(raw.get("blendFeather", 0.35)),
            engineOptions=selected_engine_options,
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
        if not isinstance(config.engineOptions, dict):
            raise ValueError("segmentation.engineOptions.<backend> must be an object")
        for key, value in config.engineOptions.items():
            if not isinstance(key, str):
                raise ValueError("segmentation.engineOptions keys must be strings")
            if isinstance(value, (dict, list, tuple)):
                raise ValueError("segmentation.engineOptions values must be scalar types")
        return config


@dataclass(frozen=True)
class BackgroundConfig:
    enabled: bool
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
            enabled=bool(raw.get("enabled", True)),
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
        if not self.enabled:
            return
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
    enabled: bool
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
            enabled=bool(raw.get("enabled", True)),
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
            thresholdDb=float(raw.get("thresholdDb", -40.0)),
            hysteresisDb=float(raw.get("hysteresisDb", 4.0)),
            attackMs=int(raw.get("attackMs", 30)),
            holdMs=int(raw.get("holdMs", 160)),
            releaseMs=int(raw.get("releaseMs", 2000)),
            openGain=float(raw.get("openGain", 1.0)),
            closedGain=float(raw.get("closedGain", 0.0)),
            minVoiceBandRatio=float(raw.get("minVoiceBandRatio", 0.50)),
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
    denoiseEnabled: bool
    denoiseBackend: str
    denoiseStrength: float
    gate: AudioGateConfig

    @classmethod
    def from_dict(cls, raw: dict) -> "AudioMixerConfig":
        gate_raw = raw.get("gate") or {}
        input_device = str(raw.get("inputDevice", "default")).strip()
        if not input_device:
            input_device = _default_audio_input_device()
        output_device = str(raw.get("outputDevice", _default_audio_output_device())).strip()
        if not output_device:
            output_device = _default_audio_output_device()
        config = cls(
            enabled=bool(raw.get("enabled", True)),
            inputDevice=input_device,
            outputDevice=output_device,
            sampleRate=int(raw.get("sampleRate", 48000)),
            channels=int(raw.get("channels", 1)),
            frameMs=int(raw.get("frameMs", 20)),
            denoiseEnabled=bool((raw.get("denoise") or {}).get("enabled", True)),
            denoiseBackend=str((raw.get("denoise") or {}).get("backend", "none")),
            denoiseStrength=float((raw.get("denoise") or {}).get("strength", 0.5)),
            gate=AudioGateConfig.from_dict(gate_raw),
        )
        if config.sampleRate <= 0:
            raise ValueError("audio.sampleRate must be > 0")
        if config.channels <= 0:
            raise ValueError("audio.channels must be > 0")
        if config.frameMs <= 0:
            raise ValueError("audio.frameMs must be > 0")
        if platform.system() == "Darwin":
            allowed_denoise_backends = {"none", "rnnoise"}
            if config.denoiseBackend not in allowed_denoise_backends:
                raise ValueError("audio.denoise.backend must be one of: none, rnnoise (macOS)")
        else:
            allowed_denoise_backends = {"none", "rnnoise", "deepfilternet"}
            if config.denoiseBackend not in allowed_denoise_backends:
                raise ValueError("audio.denoise.backend must be one of: none, rnnoise, deepfilternet")
        if config.denoiseStrength < 0.0 or config.denoiseStrength > 1.0:
            raise ValueError("audio.denoise.strength must be between 0.0 and 1.0")
        return config


@dataclass(frozen=True)
class FaceEnhanceConfig:
    enabled: bool
    gamma: float
    offset: float
    saturation: float
    strength: float
    minRegionRatio: float
    edgeNoise: float
    deidentifyEnabled: bool

    @classmethod
    def from_dict(cls, raw: dict) -> "FaceEnhanceConfig":
        config = cls(
            enabled=bool(raw.get("enabled", False)),
            gamma=float(raw.get("gamma", 1.0)),
            offset=float(raw.get("offset", 0.0)),
            saturation=float(raw.get("saturation", 1.0)),
            strength=float(raw.get("strength", 0.65)),
            minRegionRatio=float(raw.get("minRegionRatio", 0.12)),
            edgeNoise=float(raw.get("edgeNoise", 0.25)),
            deidentifyEnabled=bool((raw.get("deidentify") or {}).get("enabled", False)),
        )
        if not 0.5 <= config.gamma <= 1.8:
            raise ValueError("faceEnhance.gamma must be between 0.5 and 1.8")
        if not -80.0 <= config.offset <= 80.0:
            raise ValueError("faceEnhance.offset must be between -80 and 80")
        if not 0.5 <= config.saturation <= 1.8:
            raise ValueError("faceEnhance.saturation must be between 0.5 and 1.8")
        if not 0.0 <= config.strength <= 1.0:
            raise ValueError("faceEnhance.strength must be between 0.0 and 1.0")
        if not 0.05 <= config.minRegionRatio <= 0.5:
            raise ValueError("faceEnhance.minRegionRatio must be between 0.05 and 0.5")
        if not 0.0 <= config.edgeNoise <= 1.0:
            raise ValueError("faceEnhance.edgeNoise must be between 0.0 and 1.0")
        return config


@dataclass(frozen=True)
class DictationAiConfig:
    enabled: bool
    inputDevice: str
    backend: str
    model: str
    sttBackendEn: str
    sttModelEn: str
    sttBackendKo: str
    sttModelKo: str
    sttBackendZh: str
    sttModelZh: str
    language: str
    task: str
    translationEnabled: bool
    showSttStatusWindow: bool
    translationTargetLanguage: str
    translationBackend: str
    translationModel: str
    translationDevice: str
    translationComputeType: str
    translationBeamSize: int
    translationMaxNewTokens: int
    translationBackendEn: str
    translationModelEn: str
    translationDeviceEn: str
    translationComputeTypeEn: str
    translationBeamSizeEn: int
    translationMaxNewTokensEn: int
    translationBackendKo: str
    translationModelKo: str
    translationDeviceKo: str
    translationComputeTypeKo: str
    translationBeamSizeKo: int
    translationMaxNewTokensKo: int
    translationBackendZh: str
    translationModelZh: str
    translationDeviceZh: str
    translationComputeTypeZh: str
    translationBeamSizeZh: int
    translationMaxNewTokensZh: int
    device: str
    computeType: str
    chunkSeconds: float
    stepSeconds: float
    windowSeconds: float
    sentenceFinalizeAge: int
    beamSize: int
    maxNewTokens: int
    temperature: float
    stepSecondsEn: float
    windowSecondsEn: float
    sentenceFinalizeAgeEn: int
    beamSizeEn: int
    maxNewTokensEn: int
    temperatureEn: float
    stepSecondsKo: float
    windowSecondsKo: float
    sentenceFinalizeAgeKo: int
    beamSizeKo: int
    maxNewTokensKo: int
    temperatureKo: float
    stepSecondsZh: float
    windowSecondsZh: float
    sentenceFinalizeAgeZh: int
    beamSizeZh: int
    maxNewTokensZh: int
    temperatureZh: float
    postProcessingProfile: str
    sentenceBoundaryBackend: str
    sentenceBoundaryModel: str
    sentenceBoundaryBackendEn: str
    sentenceBoundaryModelEn: str
    sentenceBoundaryBackendKo: str
    sentenceBoundaryModelKo: str
    sentenceBoundaryBackendZh: str
    sentenceBoundaryModelZh: str
    sentenceBoundaryDevice: str
    sentenceBoundaryComputeType: str

    @classmethod
    def from_dict(cls, raw: dict) -> "DictationAiConfig":
        legacy_translate_task = raw.get("task") == "translate"
        translation_backend_default = "whisper" if legacy_translate_task else dictation_ai_default("translationBackend")
        translation_target_default = "en" if legacy_translate_task else dictation_ai_default("translationTargetLanguage")
        language = str(raw.get("language", dictation_ai_default("language"))).strip()
        translation_target_language = str(raw.get("translationTargetLanguage", translation_target_default)).strip()

        def lang_key(base: str, lang: str) -> str:
            return f"{base}{lang.title()}"

        def lang_value(base: str, lang: str, legacy_key: str | None = None):
            key = lang_key(base, lang)
            if key in raw:
                return raw[key]
            if language == lang and legacy_key and legacy_key in raw:
                return raw[legacy_key]
            if language == lang and base == "windowSeconds" and "chunkSeconds" in raw:
                return raw["chunkSeconds"]
            return dictation_ai_default(key)

        step_seconds_en = float(lang_value("stepSeconds", "en", "stepSeconds"))
        window_seconds_en = float(lang_value("windowSeconds", "en", "windowSeconds"))
        sentence_finalize_age_en = int(lang_value("sentenceFinalizeAge", "en", "sentenceFinalizeAge"))
        beam_size_en = int(lang_value("beamSize", "en", "beamSize"))
        max_new_tokens_en = int(lang_value("maxNewTokens", "en", "maxNewTokens"))
        temperature_en = float(lang_value("temperature", "en", "temperature"))
        step_seconds_ko = float(lang_value("stepSeconds", "ko", "stepSeconds"))
        window_seconds_ko = float(lang_value("windowSeconds", "ko", "windowSeconds"))
        sentence_finalize_age_ko = int(lang_value("sentenceFinalizeAge", "ko", "sentenceFinalizeAge"))
        beam_size_ko = int(lang_value("beamSize", "ko", "beamSize"))
        max_new_tokens_ko = int(lang_value("maxNewTokens", "ko", "maxNewTokens"))
        temperature_ko = float(lang_value("temperature", "ko", "temperature"))
        step_seconds_zh = float(lang_value("stepSeconds", "zh", "stepSeconds"))
        window_seconds_zh = float(lang_value("windowSeconds", "zh", "windowSeconds"))
        sentence_finalize_age_zh = int(lang_value("sentenceFinalizeAge", "zh", "sentenceFinalizeAge"))
        beam_size_zh = int(lang_value("beamSize", "zh", "beamSize"))
        max_new_tokens_zh = int(lang_value("maxNewTokens", "zh", "maxNewTokens"))
        temperature_zh = float(lang_value("temperature", "zh", "temperature"))
        runtime_by_language = {
            "en": (
                step_seconds_en,
                window_seconds_en,
                sentence_finalize_age_en,
                beam_size_en,
                max_new_tokens_en,
                temperature_en,
            ),
            "ko": (
                step_seconds_ko,
                window_seconds_ko,
                sentence_finalize_age_ko,
                beam_size_ko,
                max_new_tokens_ko,
                temperature_ko,
            ),
            "zh": (
                step_seconds_zh,
                window_seconds_zh,
                sentence_finalize_age_zh,
                beam_size_zh,
                max_new_tokens_zh,
                temperature_zh,
            ),
        }
        selected_runtime = runtime_by_language.get(language, runtime_by_language["en"])

        def translation_value(base: str, target: str, legacy_key: str | None = None):
            key = lang_key(base, target)
            if key in raw:
                return raw[key]
            if translation_target_language == target and legacy_key and legacy_key in raw:
                return raw[legacy_key]
            return dictation_ai_default(key)

        translation_backend_en = str(translation_value("translationBackend", "en", "translationBackend")).strip()
        translation_model_en = str(translation_value("translationModel", "en", "translationModel")).strip()
        translation_device_en = str(translation_value("translationDevice", "en", "translationDevice")).strip()
        translation_compute_type_en = str(translation_value("translationComputeType", "en", "translationComputeType")).strip()
        translation_beam_size_en = int(translation_value("translationBeamSize", "en", "translationBeamSize"))
        translation_max_new_tokens_en = int(
            translation_value("translationMaxNewTokens", "en", "translationMaxNewTokens")
        )
        translation_backend_ko = str(translation_value("translationBackend", "ko", "translationBackend")).strip()
        translation_model_ko = str(translation_value("translationModel", "ko", "translationModel")).strip()
        translation_device_ko = str(translation_value("translationDevice", "ko", "translationDevice")).strip()
        translation_compute_type_ko = str(translation_value("translationComputeType", "ko", "translationComputeType")).strip()
        translation_beam_size_ko = int(translation_value("translationBeamSize", "ko", "translationBeamSize"))
        translation_max_new_tokens_ko = int(
            translation_value("translationMaxNewTokens", "ko", "translationMaxNewTokens")
        )
        translation_backend_zh = str(translation_value("translationBackend", "zh", "translationBackend")).strip()
        translation_model_zh = str(translation_value("translationModel", "zh", "translationModel")).strip()
        translation_device_zh = str(translation_value("translationDevice", "zh", "translationDevice")).strip()
        translation_compute_type_zh = str(translation_value("translationComputeType", "zh", "translationComputeType")).strip()
        translation_beam_size_zh = int(translation_value("translationBeamSize", "zh", "translationBeamSize"))
        translation_max_new_tokens_zh = int(
            translation_value("translationMaxNewTokens", "zh", "translationMaxNewTokens")
        )
        translation_by_target = {
            "en": (
                translation_backend_en,
                translation_model_en,
                translation_device_en,
                translation_compute_type_en,
                translation_beam_size_en,
                translation_max_new_tokens_en,
            ),
            "ko": (
                translation_backend_ko,
                translation_model_ko,
                translation_device_ko,
                translation_compute_type_ko,
                translation_beam_size_ko,
                translation_max_new_tokens_ko,
            ),
            "zh": (
                translation_backend_zh,
                translation_model_zh,
                translation_device_zh,
                translation_compute_type_zh,
                translation_beam_size_zh,
                translation_max_new_tokens_zh,
            ),
        }
        selected_translation = translation_by_target.get(translation_target_language, translation_by_target["ko"])
        config = cls(
            enabled=bool(raw.get("enabled", dictation_ai_default("enabled"))),
            inputDevice=str(raw.get("inputDevice", _default_audio_input_device())).strip(),
            backend=str(raw.get("backend", dictation_ai_default("backend"))).strip(),
            model=str(raw.get("model", dictation_ai_default("model"))).strip(),
            sttBackendEn=str(raw.get("sttBackendEn", dictation_ai_default("sttBackendEn"))).strip(),
            sttModelEn=str(raw.get("sttModelEn", dictation_ai_default("sttModelEn"))).strip(),
            sttBackendKo=str(raw.get("sttBackendKo", dictation_ai_default("sttBackendKo"))).strip(),
            sttModelKo=str(raw.get("sttModelKo", dictation_ai_default("sttModelKo"))).strip(),
            sttBackendZh=str(raw.get("sttBackendZh", dictation_ai_default("sttBackendZh"))).strip(),
            sttModelZh=str(raw.get("sttModelZh", dictation_ai_default("sttModelZh"))).strip(),
            language=language,
            task=str(raw.get("task", dictation_ai_default("task"))).strip(),
            translationEnabled=bool(raw.get("translationEnabled", raw.get("task") == "translate")),
            showSttStatusWindow=bool(raw.get("showSttStatusWindow", dictation_ai_default("showSttStatusWindow"))),
            translationTargetLanguage=translation_target_language,
            translationBackend=selected_translation[0],
            translationModel=selected_translation[1],
            translationDevice=selected_translation[2],
            translationComputeType=selected_translation[3],
            translationBeamSize=selected_translation[4],
            translationMaxNewTokens=selected_translation[5],
            translationBackendEn=translation_backend_en,
            translationModelEn=translation_model_en,
            translationDeviceEn=translation_device_en,
            translationComputeTypeEn=translation_compute_type_en,
            translationBeamSizeEn=translation_beam_size_en,
            translationMaxNewTokensEn=translation_max_new_tokens_en,
            translationBackendKo=translation_backend_ko,
            translationModelKo=translation_model_ko,
            translationDeviceKo=translation_device_ko,
            translationComputeTypeKo=translation_compute_type_ko,
            translationBeamSizeKo=translation_beam_size_ko,
            translationMaxNewTokensKo=translation_max_new_tokens_ko,
            translationBackendZh=translation_backend_zh,
            translationModelZh=translation_model_zh,
            translationDeviceZh=translation_device_zh,
            translationComputeTypeZh=translation_compute_type_zh,
            translationBeamSizeZh=translation_beam_size_zh,
            translationMaxNewTokensZh=translation_max_new_tokens_zh,
            device=str(raw.get("device", dictation_ai_default("device"))).strip(),
            computeType=str(raw.get("computeType", dictation_ai_default("computeType"))).strip(),
            chunkSeconds=selected_runtime[1],
            stepSeconds=selected_runtime[0],
            windowSeconds=selected_runtime[1],
            sentenceFinalizeAge=selected_runtime[2],
            beamSize=selected_runtime[3],
            maxNewTokens=selected_runtime[4],
            temperature=selected_runtime[5],
            stepSecondsEn=step_seconds_en,
            windowSecondsEn=window_seconds_en,
            sentenceFinalizeAgeEn=sentence_finalize_age_en,
            beamSizeEn=beam_size_en,
            maxNewTokensEn=max_new_tokens_en,
            temperatureEn=temperature_en,
            stepSecondsKo=step_seconds_ko,
            windowSecondsKo=window_seconds_ko,
            sentenceFinalizeAgeKo=sentence_finalize_age_ko,
            beamSizeKo=beam_size_ko,
            maxNewTokensKo=max_new_tokens_ko,
            temperatureKo=temperature_ko,
            stepSecondsZh=step_seconds_zh,
            windowSecondsZh=window_seconds_zh,
            sentenceFinalizeAgeZh=sentence_finalize_age_zh,
            beamSizeZh=beam_size_zh,
            maxNewTokensZh=max_new_tokens_zh,
            temperatureZh=temperature_zh,
            postProcessingProfile=str(raw.get("postProcessingProfile", dictation_ai_default("postProcessingProfile"))).strip(),
            sentenceBoundaryBackend=str(raw.get("sentenceBoundaryBackend", dictation_ai_default("sentenceBoundaryBackend"))).strip(),
            sentenceBoundaryModel=str(raw.get("sentenceBoundaryModel", dictation_ai_default("sentenceBoundaryModel"))).strip(),
            sentenceBoundaryBackendEn=str(raw.get("sentenceBoundaryBackendEn", dictation_ai_default("sentenceBoundaryBackendEn"))).strip(),
            sentenceBoundaryModelEn=str(raw.get("sentenceBoundaryModelEn", dictation_ai_default("sentenceBoundaryModelEn"))).strip(),
            sentenceBoundaryBackendKo=str(raw.get("sentenceBoundaryBackendKo", dictation_ai_default("sentenceBoundaryBackendKo"))).strip(),
            sentenceBoundaryModelKo=str(raw.get("sentenceBoundaryModelKo", dictation_ai_default("sentenceBoundaryModelKo"))).strip(),
            sentenceBoundaryBackendZh=str(raw.get("sentenceBoundaryBackendZh", dictation_ai_default("sentenceBoundaryBackendZh"))).strip(),
            sentenceBoundaryModelZh=str(raw.get("sentenceBoundaryModelZh", dictation_ai_default("sentenceBoundaryModelZh"))).strip(),
            sentenceBoundaryDevice=str(raw.get("sentenceBoundaryDevice", dictation_ai_default("sentenceBoundaryDevice"))).strip(),
            sentenceBoundaryComputeType=str(raw.get("sentenceBoundaryComputeType", dictation_ai_default("sentenceBoundaryComputeType"))).strip(),
        )
        dictation_ai_spec("backend").validate_allowed(config.backend, path="dictationAi.backend")
        for lang, backend_key, model_key, backend, model in (
            ("en", "sttBackendEn", "sttModelEn", config.sttBackendEn, config.sttModelEn),
            ("ko", "sttBackendKo", "sttModelKo", config.sttBackendKo, config.sttModelKo),
            ("zh", "sttBackendZh", "sttModelZh", config.sttBackendZh, config.sttModelZh),
        ):
            allowed_stt_backends = dictation_ai_stt_backends_for_language(lang)
            if backend not in allowed_stt_backends:
                allowed_values = ", ".join(allowed_stt_backends)
                raise ValueError(f"dictationAi.{backend_key} must be one of: {allowed_values}")
            if not model:
                raise ValueError(f"dictationAi.{model_key} is required")
        if not config.inputDevice:
            raise ValueError("dictationAi.inputDevice is required")
        if not config.model:
            raise ValueError("dictationAi.model is required")
        dictation_ai_spec("language").validate_allowed(config.language, path="dictationAi.language")
        dictation_ai_spec("task").validate_allowed(config.task, path="dictationAi.task")
        dictation_ai_spec("translationTargetLanguage").validate_allowed(
            config.translationTargetLanguage, path="dictationAi.translationTargetLanguage"
        )
        dictation_ai_spec("translationBackend").validate_allowed(config.translationBackend, path="dictationAi.translationBackend")
        if config.translationEnabled:
            allowed_translation_backends = dictation_ai_translation_backends_for_language(config.language)
            if config.translationBackend not in allowed_translation_backends:
                allowed_values = ", ".join(allowed_translation_backends)
                raise ValueError(
                    f"dictationAi.translationBackend must be one of for language={config.language}: {allowed_values}"
                )
            allowed_translation_targets = dictation_ai_translation_targets_for_backend(config.language, config.translationBackend)
            if config.translationTargetLanguage not in allowed_translation_targets:
                allowed_values = ", ".join(allowed_translation_targets)
                raise ValueError(
                    "dictationAi.translationTargetLanguage must be one of "
                    f"for language={config.language} backend={config.translationBackend}: {allowed_values}"
                )
            allowed_translation_models = dictation_ai_translation_models_for_backend(config.translationBackend)
            if allowed_translation_models and config.translationModel not in allowed_translation_models:
                allowed_values = ", ".join(allowed_translation_models)
                raise ValueError(
                    f"dictationAi.translationModel must be one of for backend={config.translationBackend}: {allowed_values}"
                )
        if config.translationEnabled and config.translationBackend == "whisper" and config.translationTargetLanguage != "en":
            raise ValueError("dictationAi.translationTargetLanguage must be en when dictationAi.translationBackend=whisper")
        if config.translationEnabled and config.translationBackend != "whisper" and config.task == "translate":
            raise ValueError("dictationAi.task must be transcribe when dictationAi.translationBackend is not whisper")
        if config.translationEnabled and config.translationBackend in {"nllb-transformers", "m2m100-transformers"} and not config.translationModel:
            raise ValueError(f"dictationAi.translationModel is required when dictationAi.translationBackend={config.translationBackend}")
        dictation_ai_spec("translationDevice").validate_allowed(config.translationDevice, path="dictationAi.translationDevice")
        dictation_ai_spec("translationComputeType").validate_allowed(config.translationComputeType, path="dictationAi.translationComputeType")
        dictation_ai_spec("translationBeamSize").validate_range(config.translationBeamSize, path="dictationAi.translationBeamSize")
        dictation_ai_spec("translationMaxNewTokens").validate_range(
            config.translationMaxNewTokens, path="dictationAi.translationMaxNewTokens"
        )
        for target, suffix, backend, model, device, compute_type, beam_size, max_new_tokens in (
            (
                "en",
                "En",
                config.translationBackendEn,
                config.translationModelEn,
                config.translationDeviceEn,
                config.translationComputeTypeEn,
                config.translationBeamSizeEn,
                config.translationMaxNewTokensEn,
            ),
            (
                "ko",
                "Ko",
                config.translationBackendKo,
                config.translationModelKo,
                config.translationDeviceKo,
                config.translationComputeTypeKo,
                config.translationBeamSizeKo,
                config.translationMaxNewTokensKo,
            ),
            (
                "zh",
                "Zh",
                config.translationBackendZh,
                config.translationModelZh,
                config.translationDeviceZh,
                config.translationComputeTypeZh,
                config.translationBeamSizeZh,
                config.translationMaxNewTokensZh,
            ),
        ):
            dictation_ai_spec(f"translationBackend{suffix}").validate_allowed(
                backend, path=f"dictationAi.translationBackend{suffix}"
            )
            dictation_ai_spec(f"translationDevice{suffix}").validate_allowed(
                device, path=f"dictationAi.translationDevice{suffix}"
            )
            dictation_ai_spec(f"translationComputeType{suffix}").validate_allowed(
                compute_type, path=f"dictationAi.translationComputeType{suffix}"
            )
            dictation_ai_spec(f"translationBeamSize{suffix}").validate_range(
                beam_size, path=f"dictationAi.translationBeamSize{suffix}"
            )
            dictation_ai_spec(f"translationMaxNewTokens{suffix}").validate_range(
                max_new_tokens, path=f"dictationAi.translationMaxNewTokens{suffix}"
            )
            if not config.translationEnabled:
                continue
            allowed_group_backends = tuple(
                allowed_backend
                for allowed_backend in dictation_ai_translation_backends_for_language(config.language)
                if target in dictation_ai_translation_targets_for_backend(config.language, allowed_backend)
            )
            if backend not in allowed_group_backends:
                allowed_values = ", ".join(allowed_group_backends)
                raise ValueError(
                    f"dictationAi.translationBackend{suffix} must be one of "
                    f"for language={config.language} target={target}: {allowed_values}"
                )
            allowed_group_models = dictation_ai_translation_models_for_backend(backend)
            if allowed_group_models and model not in allowed_group_models:
                allowed_values = ", ".join(allowed_group_models)
                raise ValueError(
                    f"dictationAi.translationModel{suffix} must be one of for backend={backend}: {allowed_values}"
                )
            if backend in {"nllb-transformers", "m2m100-transformers"}:
                if not model:
                    raise ValueError(f"dictationAi.translationModel{suffix} is required when dictationAi.translationBackend{suffix}={backend}")
                if device != "cuda":
                    raise ValueError(f"dictationAi.translationDevice{suffix} must be cuda when dictationAi.translationBackend{suffix}={backend}")
        if config.translationEnabled and config.translationBackend in {"nllb-transformers", "m2m100-transformers"} and config.translationDevice != "cuda":
            raise ValueError(f"dictationAi.translationDevice must be cuda when dictationAi.translationBackend={config.translationBackend}")
        if not config.device:
            raise ValueError("dictationAi.device is required")
        if not config.computeType:
            raise ValueError("dictationAi.computeType is required")
        if "windowSeconds" in raw:
            dictation_ai_spec("windowSeconds").validate_range(config.windowSeconds, path="dictationAi.windowSeconds")
        dictation_ai_spec("chunkSeconds").validate_range(config.chunkSeconds, path="dictationAi.chunkSeconds")
        dictation_ai_spec("stepSeconds").validate_range(config.stepSeconds, path="dictationAi.stepSeconds")
        dictation_ai_spec("windowSeconds").validate_range(config.windowSeconds, path="dictationAi.windowSeconds")
        if config.stepSeconds > config.windowSeconds:
            selected_suffix = config.language.title()
            if f"stepSeconds{selected_suffix}" in raw or f"windowSeconds{selected_suffix}" in raw:
                raise ValueError(
                    f"dictationAi.stepSeconds{selected_suffix} must be less than or equal to dictationAi.windowSeconds{selected_suffix}"
                )
            raise ValueError("dictationAi.stepSeconds must be less than or equal to dictationAi.windowSeconds")
        dictation_ai_spec("sentenceFinalizeAge").validate_range(
            config.sentenceFinalizeAge, path="dictationAi.sentenceFinalizeAge"
        )
        dictation_ai_spec("beamSize").validate_range(config.beamSize, path="dictationAi.beamSize")
        dictation_ai_spec("maxNewTokens").validate_range(config.maxNewTokens, path="dictationAi.maxNewTokens")
        dictation_ai_spec("temperature").validate_range(config.temperature, path="dictationAi.temperature")
        for lang, suffix in (("en", "En"), ("ko", "Ko"), ("zh", "Zh")):
            step = getattr(config, f"stepSeconds{suffix}")
            window = getattr(config, f"windowSeconds{suffix}")
            dictation_ai_spec(f"stepSeconds{suffix}").validate_range(step, path=f"dictationAi.stepSeconds{suffix}")
            dictation_ai_spec(f"windowSeconds{suffix}").validate_range(window, path=f"dictationAi.windowSeconds{suffix}")
            if step > window:
                raise ValueError(f"dictationAi.stepSeconds{suffix} must be less than or equal to dictationAi.windowSeconds{suffix}")
            dictation_ai_spec(f"sentenceFinalizeAge{suffix}").validate_range(
                getattr(config, f"sentenceFinalizeAge{suffix}"), path=f"dictationAi.sentenceFinalizeAge{suffix}"
            )
            dictation_ai_spec(f"beamSize{suffix}").validate_range(getattr(config, f"beamSize{suffix}"), path=f"dictationAi.beamSize{suffix}")
            dictation_ai_spec(f"maxNewTokens{suffix}").validate_range(
                getattr(config, f"maxNewTokens{suffix}"), path=f"dictationAi.maxNewTokens{suffix}"
            )
            dictation_ai_spec(f"temperature{suffix}").validate_range(
                getattr(config, f"temperature{suffix}"), path=f"dictationAi.temperature{suffix}"
            )
            del lang
        dictation_ai_spec("postProcessingProfile").validate_allowed(
            config.postProcessingProfile, path="dictationAi.postProcessingProfile"
        )
        dictation_ai_spec("sentenceBoundaryBackend").validate_allowed(
            config.sentenceBoundaryBackend, path="dictationAi.sentenceBoundaryBackend"
        )
        if not config.sentenceBoundaryModel:
            raise ValueError("dictationAi.sentenceBoundaryModel is required")
        for lang, backend_key, model_key, backend, model in (
            (
                "en",
                "sentenceBoundaryBackendEn",
                "sentenceBoundaryModelEn",
                config.sentenceBoundaryBackendEn,
                config.sentenceBoundaryModelEn,
            ),
            (
                "ko",
                "sentenceBoundaryBackendKo",
                "sentenceBoundaryModelKo",
                config.sentenceBoundaryBackendKo,
                config.sentenceBoundaryModelKo,
            ),
            (
                "zh",
                "sentenceBoundaryBackendZh",
                "sentenceBoundaryModelZh",
                config.sentenceBoundaryBackendZh,
                config.sentenceBoundaryModelZh,
            ),
        ):
            del lang
            dictation_ai_spec(backend_key).validate_allowed(backend, path=f"dictationAi.{backend_key}")
            if not model:
                raise ValueError(f"dictationAi.{model_key} is required")
        dictation_ai_spec("sentenceBoundaryDevice").validate_allowed(
            config.sentenceBoundaryDevice, path="dictationAi.sentenceBoundaryDevice"
        )
        dictation_ai_spec("sentenceBoundaryComputeType").validate_allowed(
            config.sentenceBoundaryComputeType, path="dictationAi.sentenceBoundaryComputeType"
        )
        if config.enabled:
            if platform.system() != "Linux":
                raise ValueError(
                    "받아쓰기 AI는 Linux + NVIDIA CUDA 전용입니다. "
                    "dictationAi.enabled=true requires Linux with NVIDIA CUDA. "
                    f"currentOS={platform.system()}"
                )
            for path, device in (
                ("dictationAi.device", config.device),
                ("dictationAi.sentenceBoundaryDevice", config.sentenceBoundaryDevice),
            ):
                if device != "cuda":
                    raise ValueError(f"{path} must be cuda when dictationAi.enabled=true")
            if config.translationEnabled:
                translation_device_fields = (
                    ("dictationAi.translationDevice", config.translationDevice),
                    ("dictationAi.translationDeviceEn", config.translationDeviceEn),
                    ("dictationAi.translationDeviceKo", config.translationDeviceKo),
                    ("dictationAi.translationDeviceZh", config.translationDeviceZh),
                )
                for path, device in translation_device_fields:
                    if device != "cuda":
                        raise ValueError(f"{path} must be cuda when dictationAi.enabled=true")
        return config


@dataclass(frozen=True)
class AppConfig:
    inputCamera: InputCameraConfig
    outputCamera: OutputCameraConfig
    segmentation: SegmentationConfig
    background: BackgroundConfig
    crop: PersonCropConfig
    cameraServer: CameraServerConfig = field(default_factory=lambda: CameraServerConfig.from_dict({}))
    audio: AudioMixerConfig | None = None
    faceEnhance: FaceEnhanceConfig = field(default_factory=lambda: FaceEnhanceConfig.from_dict({}))
    dictationAi: DictationAiConfig = field(default_factory=lambda: DictationAiConfig.from_dict({}))

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
            cameraServer=CameraServerConfig.from_dict(raw.get("cameraServer") or raw.get("camera")),
            audio=AudioMixerConfig.from_dict(raw["audio"]) if raw.get("audio") else None,
            faceEnhance=FaceEnhanceConfig.from_dict(raw.get("faceEnhance") or {}),
            dictationAi=DictationAiConfig.from_dict(raw.get("dictationAi") or {}),
        )


def _default_rect(raw: dict) -> dict:
    return {
        "x": 0,
        "y": 0,
        "width": int(raw["width"]),
        "height": int(raw["height"]),
    }

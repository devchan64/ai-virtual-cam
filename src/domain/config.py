from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


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
class WhisperConfig:
    enabled: bool
    inputDevice: str
    backend: str
    model: str
    language: str
    task: str
    translationEnabled: bool
    translationTargetLanguage: str
    translationBackend: str
    translationModel: str
    translationDevice: str
    translationComputeType: str
    device: str
    computeType: str
    vadFilter: bool
    chunkSeconds: float
    beamSize: int

    @classmethod
    def from_dict(cls, raw: dict) -> "WhisperConfig":
        config = cls(
            enabled=bool(raw.get("enabled", False)),
            inputDevice=str(raw.get("inputDevice", _default_audio_input_device())).strip(),
            backend=str(raw.get("backend", "faster-whisper")).strip(),
            model=str(raw.get("model", "large-v3")).strip(),
            language=str(raw.get("language", "ko")).strip(),
            task=str(raw.get("task", "transcribe")).strip(),
            translationEnabled=bool(raw.get("translationEnabled", raw.get("task") == "translate")),
            translationTargetLanguage=str(raw.get("translationTargetLanguage", "en")).strip(),
            translationBackend=str(raw.get("translationBackend", "whisper")).strip(),
            translationModel=str(raw.get("translationModel", "facebook/nllb-200-distilled-600M")).strip(),
            translationDevice=str(raw.get("translationDevice", "cuda")).strip(),
            translationComputeType=str(raw.get("translationComputeType", "float16")).strip(),
            device=str(raw.get("device", "cuda")).strip(),
            computeType=str(raw.get("computeType", "float16")).strip(),
            vadFilter=bool(raw.get("vadFilter", True)),
            chunkSeconds=float(raw.get("chunkSeconds", 5.0)),
            beamSize=int(raw.get("beamSize", 5)),
        )
        allowed_backends = {"faster-whisper", "openai-whisper", "whisper.cpp", "mock"}
        if config.backend not in allowed_backends:
            raise ValueError("whisper.backend must be one of: faster-whisper, openai-whisper, whisper.cpp, mock")
        if not config.inputDevice:
            raise ValueError("whisper.inputDevice is required")
        if not config.model:
            raise ValueError("whisper.model is required")
        if config.language not in {"auto", "ko", "en", "zh"}:
            raise ValueError("whisper.language must be one of: auto, ko, en, zh")
        if config.task not in {"transcribe", "translate"}:
            raise ValueError("whisper.task must be one of: transcribe, translate")
        if config.translationTargetLanguage not in {"en", "ko", "zh"}:
            raise ValueError("whisper.translationTargetLanguage must be one of: en, ko, zh")
        if config.translationBackend not in {"whisper", "nllb-transformers", "mock"}:
            raise ValueError("whisper.translationBackend must be one of: whisper, nllb-transformers, mock")
        if config.translationEnabled and config.translationBackend == "whisper" and config.translationTargetLanguage != "en":
            raise ValueError("whisper.translationTargetLanguage must be en when whisper.translationBackend=whisper")
        if config.translationEnabled and config.translationBackend != "whisper" and config.task == "translate":
            raise ValueError("whisper.task must be transcribe when whisper.translationBackend is not whisper")
        if config.translationEnabled and config.translationBackend == "nllb-transformers" and not config.translationModel:
            raise ValueError("whisper.translationModel is required when whisper.translationBackend=nllb-transformers")
        if config.translationDevice not in {"cuda", "cpu"}:
            raise ValueError("whisper.translationDevice must be one of: cuda, cpu")
        if config.translationComputeType not in {"float16", "float32"}:
            raise ValueError("whisper.translationComputeType must be one of: float16, float32")
        if config.translationEnabled and config.translationBackend == "nllb-transformers" and config.translationDevice != "cuda":
            raise ValueError("whisper.translationDevice must be cuda when whisper.translationBackend=nllb-transformers")
        if not config.device:
            raise ValueError("whisper.device is required")
        if not config.computeType:
            raise ValueError("whisper.computeType is required")
        if not 1.0 <= config.chunkSeconds <= 15.0:
            raise ValueError("whisper.chunkSeconds must be between 1.0 and 15.0")
        if not 1 <= config.beamSize <= 8:
            raise ValueError("whisper.beamSize must be between 1 and 8")
        return config


@dataclass(frozen=True)
class AppConfig:
    inputCamera: InputCameraConfig
    outputCamera: OutputCameraConfig
    segmentation: SegmentationConfig
    background: BackgroundConfig
    crop: PersonCropConfig
    audio: AudioMixerConfig | None = None
    faceEnhance: FaceEnhanceConfig = field(default_factory=lambda: FaceEnhanceConfig.from_dict({}))
    whisper: WhisperConfig = field(default_factory=lambda: WhisperConfig.from_dict({}))

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
            faceEnhance=FaceEnhanceConfig.from_dict(raw.get("faceEnhance") or {}),
            whisper=WhisperConfig.from_dict(raw.get("whisper") or {}),
        )


def _default_rect(raw: dict) -> dict:
    return {
        "x": 0,
        "y": 0,
        "width": int(raw["width"]),
        "height": int(raw["height"]),
    }

from __future__ import annotations

import platform
import subprocess


def _default_audio_output_device() -> str:
    if platform.system() != "Linux":
        return "default"
    try:
        import sounddevice as sd
    except Exception:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"

    try:
        output_names: list[str] = []
        for device in sd.query_devices():
            if int(device.get("max_output_channels", 0)) <= 0:
                continue
            name = str(device.get("name", "")).strip()
            if not name:
                continue
            output_names.append(name)
        if output_names:
            if "pulse" in output_names:
                return "pulse"
            for name in output_names:
                lowered = name.lower()
                if "virtual" in lowered and "default" not in lowered:
                    return name
            for name in output_names:
                lowered = name.lower()
                if "default" not in lowered:
                    return name
            return output_names[0]
    except Exception:
        pass

    try:
        proc = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        if proc.returncode == 0:
            lines = proc.stdout.splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                lowered = name.lower()
                if "(hw:" in lowered or "sof-hda" in lowered:
                    continue
                if "ai-virtual-cam" in lowered or "virtual" in lowered:
                    return name
            for line in lines:
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                lowered = name.lower()
                if "(hw:" in lowered or "sof-hda" in lowered:
                    continue
                if "default" not in lowered:
                    return name
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


def _pactl_default_audio_device(kind: str) -> str:
    if platform.system() != "Linux" or kind not in {"source", "sink"}:
        return "default"
    cmd = ["pactl", f"get-default-{'source' if kind == 'source' else 'sink'}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=1.5)
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

    def _preferred_monitor_source() -> str | None:
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode != 0:
                return None
            names = []
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                names.append(parts[1].strip())
            for candidate in names:
                if candidate == "ai-virtual-cam.monitor":
                    return candidate
            for candidate in names:
                if candidate.endswith(".monitor"):
                    return candidate
        except Exception:
            return None
        return None

    monitor = _preferred_monitor_source()
    if monitor is not None:
        return monitor

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
        names = [
            str(d.get("name", "")).strip()
            for d in sd.query_devices()
            if int(d.get("max_input_channels", 0)) > 0
        ]
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


def _coerce_audio_output_device(device_name: str) -> str:
    def _pick_virtual_output(names: list[str]) -> str | None:
        for candidate in names:
            lowered_candidate = candidate.lower()
            if "virtual" in lowered_candidate and "default" not in lowered_candidate:
                return candidate
        return None

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
        names = [
            str(device.get("name", "")).strip()
            for device in sd.query_devices()
            if int(device.get("max_output_channels", 0)) > 0
        ]
        names = [n for n in names if n]
        if not names:
            return device_name

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
            return names[0]

        if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered:
            if "pulse" in names:
                return "pulse"
            return names[0]

        if name == "pulse":
            if "pulse" in names:
                return "pulse"
            return names[0]
        if "pulse" in names:
            return "pulse"
    except Exception:
        pass
    return device_name


def build_config(
    *,
    input_device: str,
    input_width: int,
    input_height: int,
    input_fps: int,
    output_device: str,
    output_width: int,
    output_height: int,
    output_fps: int,
    output_backend: str = "opencv",
    segmentation_backend: str,
    segmentation_threshold: float,
    segmentation_selfie_model_selection: int = 1,
    segmentation_selfie_temporal_smoothing: float = 0.25,
    segmentation_edge_smoothness: float = 0.5,
    segmentation_blend_feather: float = 0.35,
    segmentation_engine_options: dict[str, object] | None = None,
    background: dict,
    crop_margin: float,
    crop_pan_smoothing: float,
    crop_tilt_smoothing: float | None = None,
    crop_upper_body_bias: float = 0.0,
    crop_upper_body_ratio: float = 0.60,
    crop_upper_body_edge_smoothing: float = 0.35,
    input_software_zoom: float = 1.0,
    crop_zoom_smoothing: float = 0.80,
    crop_pan_pid_kp: float = 0.35,
    crop_pan_pid_ki: float = 0.01,
    crop_pan_pid_kd: float = 0.12,
    crop_tilt_pid_kp: float | None = None,
    crop_tilt_pid_ki: float | None = None,
    crop_tilt_pid_kd: float | None = None,
    crop_pan_target_offset_x: float = 0.0,
    crop_pan_target_offset_y: float = 0.0,
    audio_enabled: bool = True,
    audio_input_device: str | None = None,
    audio_output_device: str | None = None,
    audio_sample_rate: int = 48000,
    audio_channels: int = 1,
    audio_frame_ms: int = 20,
    audio_denoise_enabled: bool = True,
    audio_denoise_backend: str = "none",
    audio_denoise_strength: float = 0.5,
    audio_gate_enabled: bool = True,
    audio_gate_threshold_db: float = -40.0,
    audio_gate_hysteresis_db: float = 4.0,
    audio_gate_attack_ms: int = 30,
    audio_gate_hold_ms: int = 160,
    audio_gate_release_ms: int = 2000,
    audio_gate_open_gain: float = 1.0,
    audio_gate_closed_gain: float = 0.0,
    audio_gate_min_voice_band_ratio: float = 0.50,
    face_enhance_enabled: bool = False,
    face_enhance_gamma: float = 1.0,
    face_enhance_brightness: float = 0.0,
    face_enhance_saturation: float = 1.0,
    face_enhance_blend: float = 0.65,
    face_enhance_min_size_ratio: float = 0.12,
    face_enhance_edge_dither: float = 0.25,
) -> dict:
    if audio_output_device is None:
        audio_output_device = _default_audio_output_device()
    if not audio_output_device:
        audio_output_device = _default_audio_output_device()
    else:
        audio_output_device = str(audio_output_device).strip()

    if not audio_input_device:
        audio_input_device = _default_audio_input_device()
    else:
        audio_input_device = str(audio_input_device).strip()

    tilt_smoothing = float(crop_pan_smoothing if crop_tilt_smoothing is None else crop_tilt_smoothing)
    tilt_kp = float(crop_pan_pid_kp if crop_tilt_pid_kp is None else crop_tilt_pid_kp)
    tilt_ki = float(crop_pan_pid_ki if crop_tilt_pid_ki is None else crop_tilt_pid_ki)
    tilt_kd = float(crop_pan_pid_kd if crop_tilt_pid_kd is None else crop_tilt_pid_kd)
    seg_engine_options = dict(segmentation_engine_options or {})
    return {
        "inputCamera": {
            "devicePath": input_device,
            "width": input_width,
            "height": input_height,
            "fps": input_fps,
            "crop": {"x": 0, "y": 0, "width": input_width, "height": input_height},
            "softwareZoom": float(input_software_zoom),
        },
        "outputCamera": {
            "devicePath": output_device,
            "width": output_width,
            "height": output_height,
            "fps": output_fps,
            "backend": output_backend,
        },
        "segmentation": {
            "backend": segmentation_backend,
            "threshold": segmentation_threshold,
            "edgeSmoothness": float(segmentation_edge_smoothness),
            "blendFeather": float(segmentation_blend_feather),
            "selfie": {
                "modelSelection": int(segmentation_selfie_model_selection),
                "temporalSmoothing": float(segmentation_selfie_temporal_smoothing),
            },
            "engineOptions": {str(segmentation_backend): seg_engine_options} if seg_engine_options else {},
        },
        "background": background,
        "crop": {
            "margin": crop_margin,
            "panSmoothing": crop_pan_smoothing,
            "tiltSmoothing": tilt_smoothing,
            "upperBodyBias": float(crop_upper_body_bias),
            "upperBodyRatio": float(crop_upper_body_ratio),
            "upperBodyEdgeSmoothing": float(crop_upper_body_edge_smoothing),
            "zoom": float(input_software_zoom),
            "zoomSmoothing": float(crop_zoom_smoothing),
            "panPidKp": float(crop_pan_pid_kp),
            "panPidKi": float(crop_pan_pid_ki),
            "panPidKd": float(crop_pan_pid_kd),
            "tiltPidKp": tilt_kp,
            "tiltPidKi": tilt_ki,
            "tiltPidKd": tilt_kd,
            "panTargetOffsetX": float(crop_pan_target_offset_x),
            "panTargetOffsetY": float(crop_pan_target_offset_y),
        },
        "audio": {
            "enabled": bool(audio_enabled),
            "inputDevice": audio_input_device,
            "outputDevice": audio_output_device,
            "sampleRate": int(audio_sample_rate),
            "channels": int(audio_channels),
            "frameMs": int(audio_frame_ms),
            "denoise": {
                "enabled": bool(audio_denoise_enabled),
                "backend": str(audio_denoise_backend),
                "strength": float(audio_denoise_strength),
            },
            "gate": {
                "enabled": bool(audio_gate_enabled),
                "thresholdDb": float(audio_gate_threshold_db),
                "hysteresisDb": float(audio_gate_hysteresis_db),
                "attackMs": int(audio_gate_attack_ms),
                "holdMs": int(audio_gate_hold_ms),
                "releaseMs": int(audio_gate_release_ms),
                "openGain": float(audio_gate_open_gain),
                "closedGain": float(audio_gate_closed_gain),
                "minVoiceBandRatio": float(audio_gate_min_voice_band_ratio),
            },
        },
        "faceEnhance": {
            "enabled": bool(face_enhance_enabled),
            "gamma": float(face_enhance_gamma),
            "offset": float(face_enhance_brightness),
            "saturation": float(face_enhance_saturation),
            "strength": float(face_enhance_blend),
            "minRegionRatio": float(face_enhance_min_size_ratio),
            "edgeNoise": float(face_enhance_edge_dither),
        },
    }

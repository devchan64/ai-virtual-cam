#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import traceback
from collections import deque
import sys
import signal
import time
import threading
import subprocess
from pathlib import Path
from typing import Callable
import cv2
import platform
from threading import Lock
import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    sd = None
    SOUNDDEVICE_IMPORT_ERROR = exc

try:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox, ttk
    TK_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    tk = None
    colorchooser = None
    filedialog = None
    messagebox = None
    ttk = None
    TK_IMPORT_ERROR = exc

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.tools.config_builder import build_config
from src.tools.config_io import discover_camera_mode_options, discover_cameras, write_config
from src.audio.gate import AudioGateConfig, NoiseGate


def _segmentation_backend_options():
    if platform.system() == "Darwin":
        return ["selfie", "selfie_ensemble", "mock", "onnxruntime"]
    return ["selfie", "selfie_ensemble", "mock", "onnxruntime", "tensorrt"]


SEG_ENGINE_OPTION_FIELDS: dict[str, tuple[str, ...]] = {
    "selfie": ("temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "selfie_ensemble": ("modelBlend", "temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "onnxruntime": ("temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "mock": (),
    "tensorrt": (),
}


def _output_backend_options():
    if platform.system() == "Darwin":
        return ["pyvirtualcam", "opencv"]
    return ["v4l2loopback", "opencv"]


def _audio_denoise_backend_options():
    if platform.system() == "Darwin":
        return ["none", "rnnoise"]
    return ["none", "rnnoise", "deepfilternet"]


AUDIO_VIRTUAL_SINK_NAME = "ai-virtual-cam"
VIRTUAL_CAMERA_LABEL = "ai-virtual-cam"
AUDIO_VIRTUAL_SOURCE_NAME = "ai-virtual-cam"
LANG_PACK_DIR = ROOT_DIR / "config" / "i18n"


def _log(msg: str) -> None:
    print(f"[avc] {msg}", flush=True)


def _read_flat_yaml(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        data[key] = value
    return data


def _load_language_pack(language: str) -> dict[str, str]:
    normalized = (language or "ko").strip().lower()
    if normalized not in {"ko", "en"}:
        normalized = "ko"
    fallback = _read_flat_yaml(LANG_PACK_DIR / "config-gui.en.yaml")
    selected = _read_flat_yaml(LANG_PACK_DIR / f"config-gui.{normalized}.yaml")
    merged = dict(fallback)
    merged.update(selected)
    return merged


def _run_cmd(cmd: list[str], *, check: bool = False, timeout: float | None = 1.5) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {cmd[0]}") from exc


def _run_avc_device(
    target: str,
    action: str,
    *,
    extra_env: dict[str, str] | None = None,
    timeout: float | None = 5.0,
) -> dict:
    cmd = [str(ROOT_DIR / "bin" / "avc"), "device", target, action]
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError(f"device command not found: {cmd[0]}") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    payload: dict = {}
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {}

    if proc.returncode != 0:
        reason = payload.get("reason") or stderr or stdout or f"exit code={proc.returncode}"
        action_hint = payload.get("action")
        if stderr:
            reason = f"{reason}\n--- stderr ---\n{stderr}"
        if action_hint:
            raise RuntimeError(f"{reason}\n권장 조치: {action_hint}")
        raise RuntimeError(reason)

    if payload and payload.get("ok") is False:
        reason = payload.get("reason") or "device command failed"
        action_hint = payload.get("action")
        if stderr:
            reason = f"{reason}\n--- stderr ---\n{stderr}"
        if action_hint:
            raise RuntimeError(f"{reason}\n권장 조치: {action_hint}")
        raise RuntimeError(reason)

    return payload


def _run_sudo_cmd_noninteractive(
    args: list[str],
    *,
    check: bool = False,
    timeout: float | None = 4.0,
) -> subprocess.CompletedProcess:
    """Run privileged command for GUI config.

    Priority:
    1) pkexec (GUI password prompt)
    2) sudo -n (non-interactive fallback)
    """
    if _is_container_runtime():
        raise RuntimeError(
            "docker config에서는 sudo/modprobe를 사용할 수 없습니다. "
            "호스트 ./bin/avc config에서 가상 장치를 생성한 뒤 다시 시도하세요."
        )

    if shutil.which("pkexec") is not None:
        proc = _run_cmd(["pkexec", *args], check=False, timeout=timeout)
        if check and proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or f"code={proc.returncode}"
            raise RuntimeError(f"pkexec 실행 실패: {err}")
        return proc

    if shutil.which("sudo") is not None:
        return _run_cmd(["sudo", "-n", *args], check=check, timeout=timeout)

    raise RuntimeError(
        "권한 상승 명령(pkexec/sudo)을 찾을 수 없습니다. "
        "호스트에서 설치 상태를 확인한 뒤 다시 시도하세요."
    )


def _is_container_runtime() -> bool:
    return Path("/.dockerenv").exists()


def _is_v4l2_capture_capable(device_path: str) -> tuple[bool | None, str]:
    """Return whether a v4l2 node exposes Video Capture capability."""
    def _has_capture(capability_text: str) -> bool:
        normalized = capability_text.lower()
        return "video capture" in normalized

    try:
        proc = _run_cmd(["v4l2-ctl", "--all", "-d", device_path], check=False, timeout=2.0)
    except Exception as exc:
        return None, f"v4l2-ctl 실행 실패: {exc}"
    stdout = (proc.stdout or "").lower()
    stderr = (proc.stderr or "").lower()
    combined = f"{stdout}\n{stderr}" if stderr else stdout
    if proc.returncode != 0 and not combined:
        return None, f"v4l2-ctl 실패(code={proc.returncode})로 캡처 capability 확인 불가"

    if _has_capture(combined) and "video output" in combined:
        return True, "video capture/output 동시 지원"
    if _has_capture(combined) and "video output" not in combined:
        return True, "video capture 전용 지원"
    if proc.returncode != 0:
        return None, "video capture capability 조회 결과가 불명확합니다"
    return False, "v4l2-ctl 결과에서 video capture capability를 확인하지 못함"


def _is_v4l2_output_capable(device_path: str) -> tuple[bool | None, str]:
    """Return whether a v4l2 node exposes Video Output capability."""
    def _has_output(capability_text: str) -> bool:
        normalized = capability_text.lower()
        return "video output" in normalized

    try:
        proc = _run_cmd(["v4l2-ctl", "--all", "-d", device_path], check=False, timeout=2.0)
    except Exception as exc:
        return None, f"v4l2-ctl 실행 실패: {exc}"
    stdout = (proc.stdout or "").lower()
    stderr = (proc.stderr or "").lower()
    combined = f"{stdout}\n{stderr}" if stderr else stdout
    if proc.returncode != 0 and not combined:
        return None, f"v4l2-ctl 실패(code={proc.returncode})로 출력 capability 확인 불가"

    if _has_output(combined):
        if "video capture" in combined:
            return True, "video capture/output 동시 지원"
        return True, "video output 전용 지원"
    if proc.returncode != 0:
        return None, "video output capability 조회 결과가 불명확합니다"
    return False, "v4l2-ctl 결과에서 video output capability를 확인하지 못함"


def _probe_v4l2_capture(
    device_path: str,
    *,
    retries: int = 5,
    delay_sec: float = 0.2,
    require_output: bool = False,
) -> tuple[bool, str]:
    if not Path(device_path).exists():
        return False, f"{device_path} not found"

    detail = "not ready"
    if require_output:
        def _check(path: str) -> tuple[bool, str]:
            output_capable, output_detail = _is_v4l2_output_capable(path)
            capture_capable, capture_detail = _is_v4l2_capture_capable(path)
            if output_capable is False:
                return False, f"output-capable check failed: {output_detail}"
            if capture_capable is False:
                return False, f"capture-capable check failed: {capture_detail}"
            return True, f"{output_detail}; {capture_detail}"
        check_fn = _check
    else:
        check_fn = _is_v4l2_capture_capable
    for _ in range(max(1, retries)):
        capable, detail = check_fn(device_path)
        if capable:
            return True, detail
        time.sleep(delay_sec)
    return False, detail


def _default_virtual_output_device(cameras: list[dict[str, str]]) -> str:
    def _is_loopback_candidate(path: str) -> bool:
        output_capable, output_detail = _is_v4l2_output_capable(path)
        capture_capable, capture_detail = _is_v4l2_capture_capable(path)
        if output_capable is False:
            _log(f"skip virtual output candidate due output check failed: {path}, {output_detail}")
            return False
        if capture_capable is False:
            _log(f"skip virtual output candidate due capture check failed: {path}, {capture_detail}")
            return False
        return True

    for camera in cameras:
        label = (camera.get("label") or camera.get("name", "") or "").lower()
        path = str(camera["devicePath"])
        if ("v4l2loopback" in label or "virtual" in label or "ai-virtual-cam" in label) and _is_loopback_candidate(path):
            return path

    video10_path = "/dev/video10"
    if Path(video10_path).exists() and _is_loopback_candidate(video10_path):
        return video10_path

    for camera in cameras:
        path = str(camera["devicePath"])
        if _is_loopback_candidate(path):
            return path

    if not cameras:
        return video10_path
    return str(cameras[0]["devicePath"])


def _audio_default_output_device() -> str:
    if platform.system() != "Linux":
        return "default"
    if sd is None:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"
    try:
        sound_names: list[str] = []
        for device in sd.query_devices():
            name = str(device.get("name", ""))
            if int(device.get("max_output_channels", 0)) <= 0:
                continue
            if not name.strip():
                continue
            sound_names.append(name)
        if sound_names:
            for name in sound_names:
                lowered = name.lower()
                if "virtual" in lowered and "default" not in lowered:
                    return name
            for name in sound_names:
                lowered = name.lower()
                if "default" not in lowered and "(hw:" not in lowered and "sof-hda" not in lowered:
                    return name
            if "pulse" in sound_names:
                return "pulse"
            return sound_names[0]
    except Exception:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"

    def _first_pulse_sink() -> str | None:
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1].strip()
            if not name:
                continue
            lowered = name.lower()
            if "(hw:" in lowered or "sof-hda" in lowered:
                continue
            if "ai-virtual-cam" in lowered or "virtual" in lowered:
                return name
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1].strip()
            if not name:
                continue
            lowered = name.lower()
            if "(hw:" in lowered or "sof-hda" in lowered:
                continue
            if "default" not in lowered:
                return name
        return None

    # Prefer explicitly virtual/ai-virtual-cam sink to avoid picking physical default sink.
    prefer_sink = _first_pulse_sink()
    if prefer_sink is not None:
        return prefer_sink
    pactl_default = _pactl_default_audio_device("sink")
    if pactl_default != "default" and "(hw:" not in pactl_default.lower() and "sof-hda" not in pactl_default.lower():
        return pactl_default
    return "pulse"


def _coerce_audio_output_device_for_sounddevice(device_name: str) -> str:
    def _pick_virtual_output(names: list[str]) -> str | None:
        for candidate in names:
            lowered_candidate = candidate.lower()
            if "virtual" in lowered_candidate and "default" not in lowered_candidate:
                return candidate
        return None

    if sd is None:
        return device_name
    name = str(device_name).strip()
    if not name:
        return name
    if name == "default":
        if sd is None:
            return "pulse"
        try:
            names = [
                str(d.get("name", "")).strip()
                for d in sd.query_devices()
                if int(d.get("max_output_channels", 0)) > 0
            ]
            names = [n for n in names if n]
            if not names:
                return "pulse"
            virtual = _pick_virtual_output(names)
            if virtual is not None:
                return virtual
            if "pulse" in names:
                return "pulse"
            return names[0]
        except Exception:
            return "pulse"
    lowered = name.lower()
    if ".monitor" in lowered:
        candidate = name[:-len(".monitor")] if lowered.endswith(".monitor") else name.split(".monitor", 1)[0]
        if candidate:
            name = candidate
        is_monitor = True
    else:
        is_monitor = False
    try:
        names = [
            str(d.get("name", "")).strip()
            for d in sd.query_devices()
            if int(d.get("max_output_channels", 0)) > 0
        ]
        names = [n for n in names if n]
        if not names:
            return name
        if name in names:
            return name
        if is_monitor:
            return name
        if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered or "monitor" in lowered:
            if "pulse" in names:
                return "pulse"
            return names[0]
        if name == "pulse" and names:
            if "pulse" in names:
                return "pulse"
            return names[0]
        if "pulse" in names:
            return "pulse"
    except Exception:
        return name
    return name


def _coerce_audio_input_device_for_sounddevice(device_name: str) -> str:
    if sd is None:
        return str(device_name).strip()
    name = str(device_name).strip()
    if not name:
        return name
    lowered = name.lower()
    if name.lower() == "default":
        try:
            default_pair = sd.default.device
            default_input_index = int(default_pair[0]) if default_pair and default_pair[0] is not None else -1
            if default_input_index >= 0:
                info = sd.query_devices(default_input_index, kind="input")
                resolved = str(info.get("name", "")).strip()
                if resolved:
                    return resolved
        except Exception:
            pass
        return "default"
    try:
        # 1) exact name first
        sd.query_devices(name, kind="input")
        return name
    except Exception:
        pass

    try:
        devices = [
            str(d.get("name", "")).strip()
            for d in sd.query_devices()
            if int(d.get("max_input_channels", 0)) > 0
        ]
        devices = [d for d in devices if d]
    except Exception:
        return name

    if not devices:
        return name

    # 2) resolve hw token to a concrete sounddevice name
    hw_match = __import__("re").search(r"\b(hw:[0-9]+,[0-9]+)\b", name)
    if hw_match is not None:
        hw_token = hw_match.group(1).lower()
        for candidate in devices:
            if hw_token in candidate.lower():
                return candidate

    # 2-1) map Pulse source ID (alsa_input...__source) to hw token when possible
    if lowered.startswith("alsa_input.") or lowered.startswith("alsa_output."):
        # Examples:
        # - alsa_input....__hw_sofhdadsp_6__source -> hw:0,6
        # - alsa_input....__hw_sofhdadsp__source   -> hw:0,0
        m_hw = __import__("re").search(r"__hw_[^_]+_([0-9]+)__source$", lowered)
        if m_hw is not None:
            hw_token = f"hw:0,{m_hw.group(1)}"
        else:
            m_hw = __import__("re").search(r"__hw_[^_]+__source$", lowered)
            hw_token = "hw:0,0" if m_hw is not None else None
        if hw_token is not None:
            for candidate in devices:
                if hw_token in candidate.lower():
                    return candidate

    # 3) no implicit fallback to pulse/default here: keep configured value
    return name


def _pactl_default_audio_device(kind: str) -> str:
    if platform.system() != "Linux":
        return "default"
    if kind not in {"source", "sink"}:
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
        proc_list = subprocess.run(
            ["pactl", "list", "short", f"{kind}s"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        if proc_list.returncode == 0:
            for line in proc_list.stdout.splitlines():
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


def _audio_default_input_device() -> str:
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

    if sd is None:
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
            name = str(device.get("name", ""))
            if not name:
                continue
            if int(device.get("max_input_channels", 0)) <= 0:
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


def _audio_device_candidates(kind: str) -> list[str]:
    print(f"[avc] 오디오 {kind} 디바이스 후보 수집 시작 (sd_imported={sd is not None})", flush=True)
    values: list[str] = ["default"]
    seen = {"default"}

    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    print(
        f"[avc] 오디오 {kind} 디바이스 채널키={channel_key}",
        flush=True,
    )
    if sd is not None:
        try:
            for device in sd.query_devices():
                name = str(device.get("name", "")).strip()
                if not name:
                    continue
                if int(device.get(channel_key, 0)) <= 0:
                    continue
                if name not in seen:
                    seen.add(name)
                    values.append(name)
                    print(f"[avc] 오디오 {kind} 후보(sounddevice): {name}", flush=True)
        except Exception:
            print(f"[avc] 오디오 {kind} sounddevice 조회 실패: 예외 발생", flush=True)
            pass

    if platform.system() == "Darwin":
        macos_virtual_candidates = ["BlackHole 2ch", "BlackHole 16ch", "BlackHole 64ch"]
        for candidate in macos_virtual_candidates:
            if candidate not in seen:
                seen.add(candidate)
                values.append(candidate)
                print(f"[avc] 오디오 {kind} 후보(macos-virtual): {candidate}", flush=True)

    if platform.system() == "Linux":
        pactl_kind = "source" if kind == "input" else "sink"
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", f"{pactl_kind}s"],
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
                    dev_id = parts[1].strip()
                    if not dev_id:
                        continue
                    if dev_id not in seen:
                        seen.add(dev_id)
                        values.append(dev_id)
                        print(f"[avc] 오디오 {kind} 후보(pactl): {dev_id}", flush=True)
            else:
                print(f"[avc] 오디오 {kind} pactl 조회 실패: rc={proc.returncode}", flush=True)
        except Exception:
            print(f"[avc] 오디오 {kind} pactl 조회 실패: 예외 발생", flush=True)

    if not values:
        values.append("default")
        print(f"[avc] 오디오 {kind} 후보가 비어 fallback 'default' 추가", flush=True)
    print(f"[avc] 오디오 {kind} 총 후보 수: {len(values)}", flush=True)
    return values


def _audio_input_device_candidates() -> list[str]:
    return _audio_device_candidates("input")


def _audio_output_device_candidates() -> list[str]:
    return _audio_device_candidates("output")


def _audio_device_description_map(kind: str) -> dict[str, str]:
    if platform.system() != "Linux":
        return {}
    if kind not in {"input", "output"}:
        return {}
    target = "sources" if kind == "input" else "sinks"
    try:
        env = dict(__import__("os").environ)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        proc = subprocess.run(
            ["pactl", "list", target],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.5,
            env=env,
        )
        if proc.returncode != 0:
            return {}
    except Exception:
        return {}

    mapping: dict[str, str] = {}
    current_name: str | None = None
    current_desc: str | None = None
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("Name:"):
            if current_name and current_desc:
                mapping[current_name] = current_desc
            current_name = line.split(":", 1)[1].strip()
            current_desc = None
            continue
        if line.startswith("Description:"):
            current_desc = line.split(":", 1)[1].strip()
            continue
        if not line and current_name and current_desc:
            mapping[current_name] = current_desc
            current_name = None
            current_desc = None
    if current_name and current_desc:
        mapping[current_name] = current_desc
    return mapping


def _audio_device_display_values(kind: str, raw_values: list[str]) -> tuple[list[str], dict[str, str]]:
    desc_map = _audio_device_description_map(kind)
    display_values: list[str] = []
    display_to_raw: dict[str, str] = {}
    for raw in raw_values:
        base = str(raw).strip()
        if not base:
            continue
        desc = desc_map.get(base, "")
        display = f"{desc} | {base}" if desc else base
        if display in display_to_raw:
            continue
        display_values.append(display)
        display_to_raw[display] = base
    return display_values, display_to_raw


def _audio_device_raw_from_display(value: str, mapping: dict[str, str]) -> str:
    key = str(value).strip()
    if not key:
        return key
    mapped = mapping.get(key)
    if mapped:
        return mapped
    if " | " in key:
        return key.rsplit(" | ", 1)[-1].strip()
    return key


def _parse_video_device_number(device_path: str) -> str | None:
    value = device_path.strip()
    if not value.startswith("/dev/video"):
        return None
    tail = value[len("/dev/video"):]
    if not tail.isdigit():
        return None
    return tail


def _pactl_short_entries(kind: str) -> list[tuple[str, str, str]]:
    if platform.system() != "Linux":
        return []
    try:
        proc = _run_cmd(["pactl", "list", "short", f"{kind}s"], check=False, timeout=1.5)
    except Exception as exc:
        _log(f"pactl list short {kind}s failed: {exc}")
        return []
    if proc.returncode != 0:
        return []
    items: list[tuple[str, str, str]] = []
    for raw in proc.stdout.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        items.append((parts[0], parts[1], " ".join(parts[2:])))
    return items


def _validate_pulse_runtime_device(kind: str, device_name: str) -> None:
    if platform.system() != "Linux":
        return
    name = str(device_name).strip()
    if not name or name.lower() == "default":
        raise ValueError(
            f"audio {kind} device는 Linux runtime에서 명시값이 필요합니다. "
            f"현재값='{device_name}'. config에서 실제 장치 ID를 선택하세요."
        )
    entries = _pactl_short_entries("source" if kind == "input" else "sink")
    if not entries:
        _log(
            f"audio {kind} device runtime validation skipped: "
            "pactl list short returned no entries"
        )
        return
    names = [entry_name for _idx, entry_name, _rest in entries if entry_name.strip()]
    if name not in names:
        raise ValueError(
            f"audio {kind} device가 Pulse runtime에 존재하지 않습니다: '{name}'. "
            f"config에서 Pulse 장치 ID(source/sink)를 다시 선택하세요."
        )


def _audio_sink_exists(name: str) -> bool:
    return any(sink_id == name for _, sink_id, _ in _pactl_short_entries("sink"))


def _audio_source_exists(name: str) -> bool:
    return any(source_id == name for _, source_id, _ in _pactl_short_entries("source"))


def _get_module_ids(module_name: str, arg_key: str, name: str) -> list[str]:
    ids: list[str] = []
    for mod_id, _module, args in _pactl_short_entries("module"):
        if not args:
            continue
        if module_name not in _module:
            continue
        if f"{arg_key}={name}" not in args:
            continue
        ids.append(mod_id)
    return ids


def _get_audio_sink_module_ids(name: str) -> list[str]:
    return _get_module_ids("module-null-sink", "sink_name", name)


def _get_audio_source_module_ids(name: str) -> list[str]:
    return _get_module_ids("module-remap-source", "source_name", name)


class ConfigGui:
    def __init__(self, root: tk.Tk, output_path: str, language: str = "ko") -> None:
        self.root = root
        self.output_path = output_path
        self._lang = (language or "ko").strip().lower()
        if self._lang not in {"ko", "en"}:
            self._lang = "ko"
        self._i18n = _load_language_pack(self._lang)
        self._localized_widgets: list[tuple[object, str, str]] = []
        self.root.title(self._tr("title.main", "ai-virtual-cam config GUI"))
        self.root.geometry("640x640")
        self.root.minsize(640, 480)
        self.root.resizable(True, True)
        self.vars: dict[str, tk.Variable] = {}
        self._preview_active = False
        self._preview_capture = None
        self._preview_processor = None
        self._preview_processing_signature = None
        self._preview_out_size = (0, 0)
        self._preview_starting = False
        self._preview_last_toggle_at = 0.0
        self._preview_window: tk.Toplevel | None = None
        self._preview_canvas: tk.Canvas | None = None
        self._preview_canvas_image_id: int | None = None
        self._preview_tk_image = None
        self._preview_face_cascade = None
        self._preview_face_edge_trace_enabled = True
        self._preview_segment_trace_enabled = True
        self._preview_deidentify_trace_enabled = True
        self._preview_window_name = self._tr(
            "window.preview_title",
            "ai-virtual-cam preview (press q or esc to close)",
        )
        self._widgets: dict[str, object] = {}
        self._input_modes: list[tuple[int, int, str]] = []
        self._output_modes: list[tuple[int, int, str]] = []
        self._slider_value_vars: dict[str, tk.StringVar] = {}
        self._slider_formatters: dict[str, Callable[[float], str]] = {}
        self._audio_gate_test_running = False
        self._audio_gate_test_lock: Lock = Lock()
        self._audio_gate_test_window: tk.Toplevel | None = None
        self._audio_gate_test_after_id: str | None = None
        self._audio_gate_test_stream = None
        self._audio_gate_test_gate: NoiseGate | None = None
        self._audio_gate_test_queue: deque[tuple[float, float, str, float, bool]] = deque(maxlen=120)
        self._audio_gate_test_error: str | None = None
        self._audio_gate_test_sample_count = 0
        self._audio_gate_test_pass_count = 0
        self._audio_gate_test_match_count = 0
        self._audio_gate_test_stream_pass_count = 0
        self._audio_gate_test_stream_open_count = 0
        self._audio_gate_test_stream_close_count = 0
        self._audio_gate_test_prev_stream_open = False
        self._audio_gate_test_started_at = 0.0
        self._audio_gate_test_threshold_db = -42.0
        self._audio_gate_test_threshold_db = -40.0
        self._audio_gate_test_min_ratio = 0.50
        self._audio_input_meter_running = False
        self._audio_input_meter_after_id: str | None = None
        self._audio_input_meter_stream = None
        self._audio_input_meter_queue: deque[float] = deque(maxlen=120)
        self._audio_input_meter_lock: Lock = Lock()
        self._audio_input_meter_window: tk.Toplevel | None = None
        self._audio_input_meter_error: str | None = None
        self._audio_input_meter_started_at = 0.0
        self._audio_tune_window: tk.Toplevel | None = None
        self._audio_tune_action_btn: ttk.Button | None = None
        self._audio_tune_running = False
        self._audio_tune_cancelled = False
        self._audio_tune_is_recording = False
        self._audio_tune_after_id: str | int | None = None
        self._audio_tune_step_var: tk.StringVar | None = None
        self._audio_tune_step_list_var: tk.StringVar | None = None
        self._audio_tune_timer_var: tk.StringVar | None = None
        self._audio_tune_status_var: tk.StringVar | None = None
        self._audio_tune_summary_var: tk.StringVar | None = None
        self._audio_tune_step: int = 0
        self._audio_tune_ambient = None
        self._audio_tune_step_deadline: float = 0.0
        self._audio_tune_error: str | None = None
        self._audio_tune_result_text: str = ""
        self._audio_tune_progress: str = ""
        self._audio_tune_done: bool = False
        self._serve_process: subprocess.Popen[str] | None = None
        self._serve_status_var = tk.StringVar(value=self._tr("status.serve_stopped", "Serve: stopped"))
        self._serve_status_key: str | None = "status.serve_stopped"
        self._serve_status_key_args: dict[str, object] = {}
        self._serve_status_fallback = self._tr("status.serve_stopped", "Serve: stopped")
        self._serve_start_btn: ttk.Button | None = None
        self._serve_stop_btn: ttk.Button | None = None
        self._serve_output_thread: threading.Thread | None = None
        self._serve_stop_requested = False
        self._language_var = tk.StringVar(value=self._lang)
        self._language_var.trace_add("write", lambda *_args: self._on_language_changed())
        self._language_label: ttk.Label | None = None
        self._notebook: ttk.Notebook | None = None
        self._scroll_canvas: tk.Canvas | None = None
        self._scrollbar: ttk.Scrollbar | None = None
        self._scroll_inner: ttk.Frame | None = None
        self._scroll_window: int | None = None
        self._scrollbar_update_after_id = None
        self._tab_meta: list[tuple[ttk.Frame, str, str]] = []
        self._input_device_label: ttk.Label | None = None
        self._output_device_label: ttk.Label | None = None
        self._camera_preview_btn: ttk.Button | None = None
        self._save_btn: ttk.Button | None = None
        self._preview_qt_check_done = False
        self._seg_engine_option_keys = (
            "seg_opt_model_blend",
            "seg_opt_temporal_alpha",
            "seg_opt_mask_blur",
            "seg_opt_morph_open",
            "seg_opt_morph_close",
            "seg_opt_mask_gamma",
        )
        self._build_form()
        self._load_existing_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _is_serve_running(self) -> bool:
        process = self._serve_process
        return process is not None and process.poll() is None

    def _build_serve_command(self, config_path: str) -> list[str]:
        avc_bin = str(ROOT_DIR / "bin" / "avc")
        if _is_container_runtime():
            if os.environ.get("AVC_HOST_AVC_PATH"):
                raise RuntimeError(
                    "Docker config 런타임에서는 config 창에서 serve를 직접 실행할 수 없습니다. "
                    "Host 터미널에서 `./bin/avc docker serve`를 실행하세요."
                )
            _log("Detected container runtime for serve control.")
        return [avc_bin, "serve", "--config", config_path]

    def _set_serve_status(
        self,
        message: str,
        running: bool,
        status_key: str | None = None,
        status_args: dict[str, object] | None = None,
    ) -> None:
        if status_key:
            self._serve_status_key = status_key
            self._serve_status_key_args = status_args or {}
            translated = self._tr(status_key, message)
            try:
                message = translated.format(**self._serve_status_key_args)
            except Exception:
                message = translated
            self._serve_status_fallback = message
        else:
            self._serve_status_key = None
            self._serve_status_key_args = status_args or {}
            self._serve_status_fallback = message
        self._serve_status_var.set(message)
        if self._serve_start_btn is not None:
            if running:
                self._serve_start_btn.state(["disabled"])
            else:
                self._serve_start_btn.state(["!disabled"])
        if self._serve_stop_btn is not None:
            if running:
                self._serve_stop_btn.state(["!disabled"])
            else:
                self._serve_stop_btn.state(["disabled"])
        self._sync_action_button_states(serve_running_hint=running)

    def _register_localized_widget(self, widget: object, key: str, default: str) -> None:
        if widget is None:
            return
        self._localized_widgets.append((widget, key, default))

    def _refresh_localized_texts(self) -> None:
        self.root.title(self._tr("title.main", "ai-virtual-cam config GUI"))
        if self._language_label is not None:
            self._language_label.config(text=self._tr("label.language", "Language"))
        for widget, key, default in self._localized_widgets:
            if hasattr(widget, "config"):
                try:
                    widget.config(text=self._tr(key, default))
                except Exception:
                    pass
        if self._notebook is not None:
            for tab, key, default in self._tab_meta:
                self._notebook.tab(tab, text=self._tr(key, default))
        if self._camera_preview_btn is not None:
            self._camera_preview_btn.config(text=self._tr("button.camera_preview", "Camera Preview"))
        if self._serve_start_btn is not None:
            self._serve_start_btn.config(text=self._tr("button.serve_start", "Start Serve"))
        if self._serve_stop_btn is not None:
            self._serve_stop_btn.config(text=self._tr("button.serve_stop", "Stop Serve"))
        if self._save_btn is not None:
            self._save_btn.config(text=self._tr("button.save", "Save JSON"))
        if self._serve_status_key:
            translated = self._tr(self._serve_status_key, self._serve_status_fallback)
            try:
                translated = translated.format(**self._serve_status_key_args)
            except Exception:
                pass
            self._serve_status_var.set(translated)
        if self._audio_tune_action_btn is not None:
            self._audio_tune_action_btn.config(text=self._tr("button.audio_tune_step_start", "Start Step 1"))
    def _sync_action_button_states(self, serve_running_hint: bool | None = None) -> None:
        serve_running = self._is_serve_running() if serve_running_hint is None else serve_running_hint
        if self._camera_preview_btn is not None:
            if serve_running:
                self._camera_preview_btn.state(["disabled"])
            else:
                self._camera_preview_btn.state(["!disabled"])

        if self._serve_start_btn is not None:
            if self._preview_active or serve_running:
                self._serve_start_btn.state(["disabled"])
            else:
                self._serve_start_btn.state(["!disabled"])

    def _on_language_changed(self) -> None:
        lang = self._language_var.get().strip().lower()
        if lang not in {"ko", "en"}:
            return
        if lang == self._lang and self._i18n:
            return
        self._lang = lang
        self._i18n = _load_language_pack(lang)
        self._refresh_localized_texts()

    def _serve_process_finished(self, return_code: int | None) -> None:
        stopped_by_user = self._serve_stop_requested
        self._serve_process = None
        self._serve_stop_requested = False
        self._serve_output_thread = None
        if return_code is None or return_code == 0:
            self._set_serve_status(
                self._tr("status.serve_stopped", "Serve: stopped"),
                running=False,
                status_key="status.serve_stopped",
            )
            return
        if stopped_by_user or return_code in (
            -signal.SIGINT,
            -signal.SIGTERM,
            -signal.SIGKILL,
            143,
        ):
            self._set_serve_status(
                self._tr("status.serve_stopped", "Serve: stopped"),
                running=False,
                status_key="status.serve_stopped",
            )
            return
        self._set_serve_status(
            self._tr("status.serve_error", "Serve exited with error (code={code})"),
            running=False,
            status_key="status.serve_error",
            status_args={"code": str(return_code)},
        )

    def _start_serve(self) -> None:
        if self._is_serve_running():
            return
        if self._preview_active:
            messagebox.showerror(
                self._tr("msg.serve_start_blocked_title", "Cannot Start Serve"),
                self._tr(
                    "msg.serve_start_blocked",
                    "Cannot start Serve while camera preview is running.",
                ),
            )
            return

        self._set_serve_status(
            self._tr("status.serve_starting", "Serve: starting..."),
            running=True,
            status_key="status.serve_starting",
        )

        config_path = str(Path(self.output_path).expanduser())
        try:
            config = self._build_config()
            write_config(config_path, config)
        except Exception as exc:
            _log(f"Validation error: {exc}")
            messagebox.showerror(self._tr("msg.validation_error.title", "Validation error"), str(exc))
            self._set_serve_status(
                self._tr("status.serve_error", "Serve exited with error (code={code})"),
                running=False,
                status_key="status.serve_error",
                status_args={"code": "validation"},
            )
            return

        try:
            cmd = self._build_serve_command(config_path)
        except Exception as exc:
            _log(f"Serve start blocked: {exc}")
            messagebox.showerror(
                self._tr("msg.serve_start_title", "Serve start failed"),
                str(exc),
            )
            return

        try:
            self._serve_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=dict(os.environ),
            )
        except Exception as exc:
            self._serve_process = None
            _log(f"Failed to start serve process: {exc}")
            messagebox.showerror(
                self._tr("msg.serve_start_title", "Serve start failed"),
                str(exc),
            )
            self._set_serve_status(
                self._tr("status.serve_error", "Serve exited with error (code={code})"),
                running=False,
                status_key="status.serve_error",
                status_args={"code": "start_failed"},
            )
            return

        self._serve_stop_requested = False
        self._set_serve_status(
            self._tr("status.serve_running", "Serve running (pid={pid})"),
            running=True,
            status_key="status.serve_running",
            status_args={"pid": str(self._serve_process.pid)},
        )
        self._serve_output_thread = threading.Thread(target=self._serve_output_worker, args=(self._serve_process,), daemon=True)
        self._serve_output_thread.start()

    def _serve_output_worker(self, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    print(line.rstrip("\n"), flush=True)
            return_code = process.wait()
        except Exception as exc:
            _log(f"Serve watcher failed: {exc}")
            return_code = process.returncode
        if not self.root.winfo_exists():
            self._serve_process = None
            self._serve_stop_requested = False
            self._serve_output_thread = None
            return
        self.root.after(0, lambda: self._serve_process_finished(return_code))

    def _stop_serve(self) -> None:
        process = self._serve_process
        if process is None or process.poll() is not None:
            self._serve_process_finished(process.returncode if process else 0)
            return

        self._serve_stop_requested = True
        self._set_serve_status(
            self._tr("status.serve_stopping", "Stopping Serve..."),
            running=True,
            status_key="status.serve_stopping",
        )
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            self._serve_process_finished(process.returncode)
            return
        except Exception:
            try:
                process.terminate()
            except Exception:
                self._serve_process_finished(process.returncode)
                return

        def _force_kill() -> None:
            if process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
        threading.Timer(1.5, _force_kill).start()

    def _on_close(self) -> None:
        if self._is_serve_running():
            self._stop_serve()
        if self._preview_active:
            self._stop_preview()
        self.root.destroy()

    def _tr(self, key: str, default: str) -> str:
        value = self._i18n.get(key)
        if value is None:
            return default
        return value

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(2, weight=0)

        self._scroll_canvas = tk.Canvas(frame, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scroll_canvas.grid(row=1, column=0, sticky="nsew")
        self._scrollbar.grid(row=1, column=1, sticky="ns")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)

        self._scroll_inner = ttk.Frame(self._scroll_canvas, padding=0)
        self._scroll_window = self._scroll_canvas.create_window((0, 0), window=self._scroll_inner, anchor="nw")
        self._scroll_inner.bind("<Configure>", self._on_scroll_inner_configure)
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mouse_wheel)
        self._scroll_canvas.bind_all("<Button-4>", self._on_mouse_wheel_linux)
        self._scroll_canvas.bind_all("<Button-5>", self._on_mouse_wheel_linux)

        language_frame = ttk.Frame(frame)
        language_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8), padx=(0, 0))
        language_frame.columnconfigure(0, weight=0)
        language_frame.columnconfigure(1, weight=1)
        self._language_label = ttk.Label(language_frame, text=self._tr("label.language", "Language"))
        self._language_label.grid(row=0, column=0, sticky="w", padx=4)
        self._register_localized_widget(self._language_label, "label.language", "Language")
        lang_combo = ttk.Combobox(
            language_frame,
            values=("ko", "en"),
            state="readonly",
            textvariable=self._language_var,
        )
        lang_combo.grid(row=0, column=1, sticky="ew", padx=4)

        self._notebook = ttk.Notebook(self._scroll_inner)
        notebook = self._notebook
        notebook.grid(row=0, column=0, sticky="nsew")
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._scroll_inner.columnconfigure(0, weight=1)
        self._scroll_inner.rowconfigure(0, weight=1)

        tab_io = ttk.Frame(notebook, padding=8)
        tab_seg = ttk.Frame(notebook, padding=8)
        tab_bg = ttk.Frame(notebook, padding=8)
        tab_crop = ttk.Frame(notebook, padding=8)
        tab_audio = ttk.Frame(notebook, padding=8)
        tab_face = ttk.Frame(notebook, padding=8)
        self._tab_meta = [
            (tab_io, "title.tab.io", "I/O"),
            (tab_seg, "title.tab.seg", "Segmentation"),
            (tab_bg, "title.tab.bg", "Background"),
            (tab_crop, "title.tab.crop", "Framing"),
            (tab_face, "title.tab.face", "Face"),
            (tab_audio, "title.tab.audio", "Audio"),
        ]
        for tab, key, default in self._tab_meta:
            notebook.add(tab, text=self._tr(key, default))
        for tab in (tab_io, tab_seg, tab_bg, tab_crop, tab_audio, tab_face):
            for col in range(4):
                tab.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        is_macos = platform.system() == "Darwin"
        cameras = discover_cameras()
        camera_values = [c["devicePath"] for c in cameras] or (["0"] if is_macos else ["/dev/video0"])

        row = 0
        self._input_device_label = self._add_combo(
            tab_io,
            row,
            "input_device",
            self._tr("label.input_device", "Input device"),
            camera_values,
            camera_values[0],
            readonly=True,
            label_key="label.input_device",
        )
        row += 1
        initial_modes = discover_camera_mode_options(camera_values[0]) if camera_values else [(1280, 720, "30")]
        width_values = sorted({str(w) for w, _h, _fps in initial_modes}, key=lambda v: int(v))
        default_w = width_values[0] if width_values else "1280"
        height_values = sorted({str(h) for w, h, _fps in initial_modes if str(w) == default_w}, key=lambda v: int(v))
        default_h = height_values[0] if height_values else "720"
        self._add_combo(
            tab_io,
            row,
            "input_width",
            self._tr("label.input_width", "Input width"),
            width_values,
            default_w,
            label_key="label.input_width",
        )
        row += 1
        self._add_combo(
            tab_io,
            row,
            "input_height",
            self._tr("label.input_height", "Input height"),
            height_values,
            default_h,
            label_key="label.input_height",
        )
        row += 1
        fps_values = sorted(
            {fps for w, h, fps in initial_modes if str(w) == default_w and str(h) == default_h},
            key=lambda v: float(v),
        ) or ["30"]
        self._add_combo(
            tab_io,
            row,
            "input_fps",
            self._tr("label.input_fps", "Input FPS"),
            fps_values,
            "30",
            label_key="label.input_fps",
        )
        row += 1
        self._add_slider(
            tab_io,
            row,
            "input_software_zoom",
            self._tr("label.input_sw_zoom", "Input SW zoom"),
            1.0,
            1.0,
            4.0,
            resolution=0.01,
            label_key="label.input_sw_zoom",
        )
        row += 1

        self._add_combo(
            tab_io,
            row,
            "output_backend",
            self._tr("label.output_backend", "Output backend"),
            _output_backend_options(),
            _output_backend_options()[0],
            label_key="label.output_backend",
        )
        row += 1
        default_output_device = (
            "virtual-cam" if is_macos else _default_virtual_output_device(discover_cameras())
        )
        initial_output_modes = discover_camera_mode_options(default_output_device)
        self._output_modes = initial_output_modes
        output_width_values = sorted({str(w) for w, _h, _fps in initial_output_modes}, key=lambda v: int(v))
        output_default_w = output_width_values[0] if output_width_values else "1280"
        output_height_values = sorted(
            {str(h) for w, h, _fps in initial_output_modes if str(w) == output_default_w},
            key=lambda v: int(v),
        )
        output_default_h = output_height_values[0] if output_height_values else "720"
        output_fps_values = sorted(
            {
                str(int(round(float(fps))))
                for w, h, fps in initial_output_modes
                if str(w) == output_default_w and str(h) == output_default_h
            },
            key=lambda v: int(v),
        )
        self._output_device_label = self._add_text(
            tab_io,
            row,
            "output_device",
            self._tr("label.output_path", "Output path"),
            default_output_device,
            label_key="label.output_path",
        )
        row += 1
        self._add_combo(
            tab_io,
            row,
            "output_width",
            self._tr("label.output_width", "Output width"),
            output_width_values or ["1280"],
            output_default_w,
            label_key="label.output_width",
        )
        row += 1
        self._add_combo(
            tab_io,
            row,
            "output_height",
            self._tr("label.output_height", "Output height"),
            output_height_values or ["720"],
            output_default_h,
            label_key="label.output_height",
        )
        row += 1
        self._add_combo(
            tab_io,
            row,
            "output_fps",
            self._tr("label.output_fps", "Output FPS"),
            output_fps_values or ["30"],
            output_fps_values[0] if output_fps_values else "30",
            label_key="label.output_fps",
        )
        row += 1
        if platform.system() == "Linux":
            create_cam_btn = ttk.Button(
                tab_io,
                text=self._tr("button.create_virtual_camera", "Create virtual camera"),
                command=self._create_virtual_camera,
            )
            self._register_localized_widget(create_cam_btn, "button.create_virtual_camera", "Create virtual camera")
            remove_cam_btn = ttk.Button(
                tab_io,
                text=self._tr("button.remove_virtual_camera", "Remove virtual camera"),
                command=self._remove_virtual_camera,
            )
            self._register_localized_widget(remove_cam_btn, "button.remove_virtual_camera", "Remove virtual camera")
            create_cam_btn.grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
            )
            remove_cam_btn.grid(
                row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
            )
            row += 1
        reset_io_btn = ttk.Button(
            tab_io,
            text=self._tr("button.reset_io_settings", "Restore IO defaults"),
            command=self._reset_io_settings,
        )
        self._register_localized_widget(reset_io_btn, "button.reset_io_settings", "Restore IO defaults")
        reset_io_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        row = 0
        self._add_combo(
            tab_seg,
            row,
            "seg_backend",
            self._tr("label.seg_backend", "Seg backend"),
            _segmentation_backend_options(),
            "selfie",
            label_key="label.seg_backend",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_threshold",
            self._tr("label.seg_threshold", "Seg threshold"),
            0.65,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.seg_threshold",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_edge_smoothness",
            self._tr("label.seg_edge_smoothness", "Edge smoothness"),
            0.50,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.seg_edge_smoothness",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_blend_feather",
            self._tr("label.seg_blend_feather", "Blend feather"),
            0.35,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.seg_blend_feather",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_selfie_model",
            self._tr("label.seg_selfie_model", "Selfie model selection"),
            1,
            0,
            1,
            resolution=1,
            label_key="label.seg_selfie_model",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_selfie_smoothing",
            self._tr("label.seg_selfie_smoothing", "Selfie temporal smoothing"),
            0.25,
            0.0,
            0.95,
            resolution=0.01,
            label_key="label.seg_selfie_smoothing",
        )
        row += 1
        seg_engine_label = ttk.Label(
            tab_seg,
            text=self._tr("label.engine_options", "Engine options"),
        )
        self._register_localized_widget(seg_engine_label, "label.engine_options", "Engine options")
        seg_engine_label.grid(row=row, column=0, sticky="w", padx=4, pady=(8, 0))
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_opt_model_blend",
            self._tr("label.seg_opt_model_blend", "Model blend"),
            0.60,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.seg_opt_model_blend",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_opt_temporal_alpha",
            self._tr("label.seg_opt_temporal_alpha", "Temporal alpha override"),
            0.55,
            0.0,
            0.95,
            resolution=0.01,
            label_key="label.seg_opt_temporal_alpha",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_opt_mask_blur",
            self._tr("label.seg_opt_mask_blur", "Mask blur kernel"),
            5,
            0,
            21,
            resolution=1,
            label_key="label.seg_opt_mask_blur",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_opt_morph_open",
            self._tr("label.seg_opt_morph_open", "Morph open kernel"),
            3,
            0,
            15,
            resolution=1,
            label_key="label.seg_opt_morph_open",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_opt_morph_close",
            self._tr("label.seg_opt_morph_close", "Morph close kernel"),
            5,
            0,
            15,
            resolution=1,
            label_key="label.seg_opt_morph_close",
        )
        row += 1
        self._add_slider(
            tab_seg,
            row,
            "seg_opt_mask_gamma",
            self._tr("label.seg_opt_mask_gamma", "Mask gamma"),
            0.90,
            0.5,
            1.5,
            resolution=0.01,
            label_key="label.seg_opt_mask_gamma",
        )
        row += 1
        seg_engine_hint = ttk.Label(
            tab_seg,
            text=self._tr(
                "hint.seg_engine_options",
                "Available options are limited by selected engine.",
            ),
            foreground="#666",
        )
        seg_engine_hint.grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 0))
        self._register_localized_widget(seg_engine_hint, "hint.seg_engine_options", "Available options are limited by selected engine.")
        row += 1
        reset_seg_btn = ttk.Button(
            tab_seg,
            text=self._tr("button.reset_segmentation_settings", "Restore segmentation defaults"),
            command=self._reset_seg_settings,
        )
        self._register_localized_widget(reset_seg_btn, "button.reset_segmentation_settings", "Restore segmentation defaults")
        reset_seg_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        row = 0
        self._add_combo(
            tab_bg,
            row,
            "bg_mode",
            self._tr("label.bg_mode", "Background mode"),
            ["chroma", "image", "image_chroma"],
            "chroma",
            label_key="label.bg_mode",
        )
        row += 1
        self._add_text(
            tab_bg,
            row,
            "bg_image",
            self._tr("label.bg_image", "Background image"),
            "",
            label_key="label.bg_image",
        )
        browse_bg_image_btn = ttk.Button(
            tab_bg,
            text=self._tr("button.browse", "Browse"),
            command=self._pick_bg_image,
        )
        self._register_localized_widget(browse_bg_image_btn, "button.browse", "Browse")
        browse_bg_image_btn.grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_int(
            tab_bg,
            row,
            "bg_r",
            self._tr("label.bg_chroma_r", "Chroma R"),
            0,
            label_key="label.bg_chroma_r",
        )
        self._add_int(
            tab_bg,
            row,
            "bg_g",
            self._tr("label.bg_chroma_g", "Chroma G"),
            0,
            col_offset=2,
            label_key="label.bg_chroma_g",
        )
        row += 1
        self._add_int(
            tab_bg,
            row,
            "bg_b",
            self._tr("label.bg_chroma_b", "Chroma B"),
            0,
            label_key="label.bg_chroma_b",
        )
        pick_color_btn = ttk.Button(
            tab_bg,
            text=self._tr("button.pick_color", "Pick Color"),
            command=self._pick_chroma_color,
        )
        self._register_localized_widget(pick_color_btn, "button.pick_color", "Pick Color")
        pick_color_btn.grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_slider(
            tab_bg,
            row,
            "bg_blend_alpha",
            self._tr("label.bg_blend_alpha", "Color blend alpha"),
            0.35,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.bg_blend_alpha",
        )
        row += 1
        reset_bg_btn = ttk.Button(
            tab_bg,
            text=self._tr("button.reset_background_settings", "Restore background defaults"),
            command=self._reset_bg_settings,
        )
        self._register_localized_widget(reset_bg_btn, "button.reset_background_settings", "Restore background defaults")
        reset_bg_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        row = 0
        self._add_slider(
            tab_crop,
            row,
            "crop_margin",
            self._tr("label.crop_margin", "Person crop margin"),
            0.25,
            0.0,
            2.0,
            resolution=0.01,
            label_key="label.crop_margin",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_pan_smoothing",
            self._tr("label.crop_pan_smoothing", "Pan smoothing"),
            0.85,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_pan_smoothing",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_tilt_smoothing",
            self._tr("label.crop_tilt_smoothing", "Tilt smoothing"),
            0.85,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_tilt_smoothing",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_zoom_smoothing",
            self._tr("label.crop_zoom_smoothing", "Zoom smoothing"),
            0.80,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_zoom_smoothing",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_upper_body_bias",
            self._tr("label.crop_upper_body_bias", "Upper body bias"),
            0.00,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_upper_body_bias",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_upper_body_ratio",
            self._tr("label.crop_upper_body_ratio", "Upper body ratio"),
            0.60,
            0.2,
            1.0,
            resolution=0.01,
            label_key="label.crop_upper_body_ratio",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_upper_body_edge_smoothing",
            self._tr("label.crop_upper_body_edge_smoothing", "Upper body edge smoothing"),
            0.35,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_upper_body_edge_smoothing",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_pan_pid_kp",
            self._tr("label.crop_pan_pid_kp", "Pan PID Kp"),
            0.35,
            0.0,
            2.0,
            resolution=0.01,
            label_key="label.crop_pan_pid_kp",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_pan_pid_ki",
            self._tr("label.crop_pan_pid_ki", "Pan PID Ki"),
            0.01,
            0.0,
            0.5,
            resolution=0.001,
            label_key="label.crop_pan_pid_ki",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_pan_pid_kd",
            self._tr("label.crop_pan_pid_kd", "Pan PID Kd"),
            0.12,
            0.0,
            2.0,
            resolution=0.01,
            label_key="label.crop_pan_pid_kd",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_tilt_pid_kp",
            self._tr("label.crop_tilt_pid_kp", "Tilt PID Kp"),
            0.35,
            0.0,
            2.0,
            resolution=0.01,
            label_key="label.crop_tilt_pid_kp",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_tilt_pid_ki",
            self._tr("label.crop_tilt_pid_ki", "Tilt PID Ki"),
            0.01,
            0.0,
            0.5,
            resolution=0.001,
            label_key="label.crop_tilt_pid_ki",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_tilt_pid_kd",
            self._tr("label.crop_tilt_pid_kd", "Tilt PID Kd"),
            0.12,
            0.0,
            2.0,
            resolution=0.01,
            label_key="label.crop_tilt_pid_kd",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_pan_target_offset_x",
            self._tr("label.crop_pan_target_offset_x", "Pan target offset X"),
            0.00,
            -1.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_pan_target_offset_x",
        )
        row += 1
        self._add_slider(
            tab_crop,
            row,
            "crop_pan_target_offset_y",
            self._tr("label.crop_pan_target_offset_y", "Pan target offset Y"),
            0.00,
            -1.0,
            1.0,
            resolution=0.01,
            label_key="label.crop_pan_target_offset_y",
        )
        row += 1
        reset_crop_btn = ttk.Button(
            tab_crop,
            text=self._tr("button.reset_crop_settings", "Restore framing defaults"),
            command=self._reset_crop_settings,
        )
        self._register_localized_widget(reset_crop_btn, "button.reset_crop_settings", "Restore framing defaults")
        reset_crop_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        row = 0
        self._add_bool_switch(
            tab_audio,
            row,
            "audio_enabled",
            self._tr("label.audio_enabled", "Audio mixer"),
            True,
            label_key="label.audio_enabled",
        )
        row += 1
        audio_input_candidates = _audio_input_device_candidates()
        audio_input_default = _audio_default_input_device()
        if audio_input_default not in audio_input_candidates:
            audio_input_candidates.append(audio_input_default)
        audio_input_display_values, self._audio_input_display_to_raw = _audio_device_display_values(
            "input", audio_input_candidates
        )
        audio_input_default_display = next(
            (k for k, v in self._audio_input_display_to_raw.items() if v == audio_input_default),
            audio_input_default,
        )
        self._add_combo(
            tab_audio,
            row,
            "audio_input_device",
            self._tr("label.audio_input_device", "Input device"),
            audio_input_display_values,
            audio_input_default_display,
            label_key="label.audio_input_device",
        )
        row += 1
        mic_input_meter_btn = ttk.Button(
            tab_audio,
            text=self._tr("button.audio_input_meter", "Input dB meter"),
            command=self._run_audio_input_meter,
        )
        self._register_localized_widget(mic_input_meter_btn, "button.audio_input_meter", "Input dB meter")
        mic_input_meter_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )
        row += 1
        audio_output_candidates = _audio_output_device_candidates()
        audio_output_default = _audio_default_output_device()
        if audio_output_default not in audio_output_candidates:
            audio_output_candidates.append(audio_output_default)
        audio_output_display_values, self._audio_output_display_to_raw = _audio_device_display_values(
            "output", audio_output_candidates
        )
        audio_output_default_display = next(
            (k for k, v in self._audio_output_display_to_raw.items() if v == audio_output_default),
            audio_output_default,
        )
        self._add_combo(
            tab_audio,
            row,
            "audio_output_device",
            self._tr("label.audio_output_device", "Output device"),
            audio_output_display_values,
            audio_output_default_display,
            label_key="label.audio_output_device",
        )
        row += 1
        if platform.system() == "Linux":
            create_mic_btn = ttk.Button(
                tab_audio,
                text=self._tr("button.create_virtual_mic", "Create virtual microphone"),
                command=self._create_virtual_speaker,
            )
            self._register_localized_widget(create_mic_btn, "button.create_virtual_mic", "Create virtual microphone")
            remove_mic_btn = ttk.Button(
                tab_audio,
                text=self._tr("button.remove_virtual_mic", "Remove virtual microphone"),
                command=self._remove_virtual_speaker,
            )
            self._register_localized_widget(remove_mic_btn, "button.remove_virtual_mic", "Remove virtual microphone")
            create_mic_btn.grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
            )
            remove_mic_btn.grid(
                row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
            )
            row += 1
        self._add_int(
            tab_audio,
            row,
            "audio_sample_rate",
            self._tr("label.audio_sample_rate", "Sample rate"),
            48000,
            label_key="label.audio_sample_rate",
        )
        self._add_int(
            tab_audio,
            row,
            "audio_channels",
            self._tr("label.audio_channels", "Channels"),
            1,
            col_offset=2,
            label_key="label.audio_channels",
        )
        row += 1
        self._add_int(
            tab_audio,
            row,
            "audio_frame_ms",
            self._tr("label.audio_frame_ms", "Frame ms"),
            20,
            label_key="label.audio_frame_ms",
        )
        row += 1
        self._add_bool_switch(
            tab_audio,
            row,
            "audio_denoise_enabled",
            self._tr("label.audio_denoise_enabled", "Noise cancel"),
            True,
            label_key="label.audio_denoise_enabled",
        )
        row += 1
        denoise_backends = _audio_denoise_backend_options()
        self._add_combo(
            tab_audio,
            row,
            "audio_denoise_backend",
            self._tr("label.audio_denoise_backend", "NC backend"),
            denoise_backends,
            denoise_backends[0],
            label_key="label.audio_denoise_backend",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_denoise_strength",
            self._tr("label.audio_denoise_strength", "NC strength"),
            0.50,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.audio_denoise_strength",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_threshold_db",
            self._tr("label.audio_gate_threshold_db", "Gate threshold dB"),
            -40.0,
            -80.0,
            0.0,
            resolution=0.5,
            label_key="label.audio_gate_threshold_db",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_hysteresis_db",
            self._tr("label.audio_gate_hysteresis_db", "Gate hysteresis dB"),
            4.0,
            0.0,
            20.0,
            resolution=0.5,
            label_key="label.audio_gate_hysteresis_db",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_min_voice_band_ratio",
            self._tr("label.audio_gate_min_voice_band_ratio", "Min voice band ratio"),
            0.50,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.audio_gate_min_voice_band_ratio",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_attack_ms",
            self._tr("label.audio_gate_attack_ms", "Gate attack ms"),
            30,
            0,
            500,
            resolution=1,
            label_key="label.audio_gate_attack_ms",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_hold_ms",
            self._tr("label.audio_gate_hold_ms", "Gate hold ms"),
            160,
            0,
            2000,
            resolution=1,
            label_key="label.audio_gate_hold_ms",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_release_ms",
            self._tr("label.audio_gate_release_ms", "Gate release ms"),
            2000,
            0,
            4000,
            resolution=1,
            label_key="label.audio_gate_release_ms",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_open_gain",
            self._tr("label.audio_gate_open_gain", "Gate open gain"),
            1.0,
            0.0,
            2.0,
            resolution=0.01,
            label_key="label.audio_gate_open_gain",
        )
        row += 1
        self._add_slider(
            tab_audio,
            row,
            "audio_gate_closed_gain",
            self._tr("label.audio_gate_closed_gain", "Gate closed gain"),
            0.0,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.audio_gate_closed_gain",
        )
        row += 1
        auto_tune_btn = ttk.Button(
            tab_audio,
            text=self._tr("button.auto_tune_audio_gate", "Auto tune audio gate"),
            command=self._auto_tune_audio_gate,
        )
        self._register_localized_widget(auto_tune_btn, "button.auto_tune_audio_gate", "Auto tune audio gate")
        auto_tune_btn.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        test_gate_btn = ttk.Button(
            tab_audio,
            text=self._tr("button.run_audio_gate_test", "Audio gate test"),
            command=self._run_audio_gate_test,
        )
        self._register_localized_widget(test_gate_btn, "button.run_audio_gate_test", "Audio gate test")
        test_gate_btn.grid(
            row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        row += 1
        reset_audio_btn = ttk.Button(
            tab_audio,
            text=self._tr("button.reset_audio_settings", "Restore audio defaults"),
            command=self._reset_audio_settings,
        )
        self._register_localized_widget(reset_audio_btn, "button.reset_audio_settings", "Restore audio defaults")
        reset_audio_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        row = 0
        self._add_bool_switch(
            tab_face,
            row,
            "face_enhance_enabled",
            self._tr("label.face_enhance_enabled", "Face quality enhancement"),
            False,
            label_key="label.face_enhance_enabled",
        )
        row += 1
        self._add_bool_switch(
            tab_face,
            row,
            "face_deidentify_enabled",
            self._tr("label.face_deidentify_enabled", "Face deidentify (eye mask)"),
            False,
            label_key="label.face_deidentify_enabled",
        )
        row += 1
        self._add_slider(
            tab_face,
            row,
            "face_enhance_gamma",
            self._tr("label.face_enhance_gamma", "Face gamma"),
            1.0,
            0.5,
            1.8,
            resolution=0.01,
            label_key="label.face_enhance_gamma",
        )
        row += 1
        self._add_slider(
            tab_face,
            row,
            "face_enhance_brightness",
            self._tr("label.face_enhance_brightness", "Face brightness"),
            0.0,
            -80.0,
            80.0,
            resolution=1,
            label_key="label.face_enhance_brightness",
        )
        row += 1
        self._add_slider(
            tab_face,
            row,
            "face_enhance_saturation",
            self._tr("label.face_enhance_saturation", "Face saturation"),
            1.0,
            0.5,
            1.8,
            resolution=0.01,
            label_key="label.face_enhance_saturation",
        )
        row += 1
        self._add_slider(
            tab_face,
            row,
            "face_enhance_blend",
            self._tr("label.face_enhance_blend", "Face enhancement strength"),
            0.65,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.face_enhance_blend",
        )
        row += 1
        self._add_slider(
            tab_face,
            row,
            "face_enhance_min_size_ratio",
            self._tr("label.face_enhance_min_size_ratio", "Minimum face size ratio"),
            0.12,
            0.05,
            0.50,
            resolution=0.01,
            label_key="label.face_enhance_min_size_ratio",
        )
        row += 1
        self._add_slider(
            tab_face,
            row,
            "face_enhance_edge_dither",
            self._tr("label.face_enhance_edge_dither", "Face edge dither"),
            0.25,
            0.0,
            1.0,
            resolution=0.01,
            label_key="label.face_enhance_edge_dither",
        )
        row += 1
        reset_face_btn = ttk.Button(
            tab_face,
            text=self._tr("button.reset_face_settings", "Restore face quality defaults"),
            command=self._reset_face_settings,
        )
        self._register_localized_widget(reset_face_btn, "button.reset_face_settings", "Restore face quality defaults")
        reset_face_btn.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        action_frame = ttk.Frame(frame)
        action_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        action_frame.columnconfigure(2, weight=1)
        action_frame.columnconfigure(3, weight=1)
        self._camera_preview_btn = ttk.Button(
            action_frame, text=self._tr("button.camera_preview", "Camera Preview"), command=self._preview
        )
        self._camera_preview_btn.grid(
            row=0, column=0, sticky="ew", padx=4
        )
        self._serve_start_btn = ttk.Button(
            action_frame,
            text=self._tr("button.serve_start", "Start Serve"),
            command=self._start_serve,
        )
        self._serve_start_btn.grid(row=0, column=1, sticky="ew", padx=4)
        self._serve_stop_btn = ttk.Button(
            action_frame,
            text=self._tr("button.serve_stop", "Stop Serve"),
            command=self._stop_serve,
        )
        self._serve_stop_btn.grid(row=0, column=2, sticky="ew", padx=4)
        self._serve_stop_btn.state(["disabled"])
        self._save_btn = ttk.Button(action_frame, text=self._tr("button.save", "Save JSON"), command=self._save)
        self._save_btn.grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Label(action_frame, textvariable=self._serve_status_var).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 0)
        )
        self._set_serve_status(self._tr("status.serve_stopped", "Serve: stopped"), running=False, status_key="status.serve_stopped")
        input_device_widget = self._widgets.get("input_device")
        if input_device_widget is not None:
            input_device_widget.bind("<<ComboboxSelected>>", self._on_input_device_changed)
        input_width_widget = self._widgets.get("input_width")
        if input_width_widget is not None:
            input_width_widget.bind("<<ComboboxSelected>>", self._on_input_width_changed)
        input_height_widget = self._widgets.get("input_height")
        if input_height_widget is not None:
            input_height_widget.bind("<<ComboboxSelected>>", self._on_input_height_changed)
        output_device_widget = self._widgets.get("output_device")
        if output_device_widget is not None:
            output_device_widget.bind("<FocusOut>", self._on_output_device_changed)
            output_device_widget.bind("<Return>", self._on_output_device_changed)
        output_width_widget = self._widgets.get("output_width")
        if output_width_widget is not None:
            output_width_widget.bind("<<ComboboxSelected>>", self._on_output_width_changed)
        output_height_widget = self._widgets.get("output_height")
        if output_height_widget is not None:
            output_height_widget.bind("<<ComboboxSelected>>", self._on_output_height_changed)
        seg_backend_widget = self._widgets.get("seg_backend")
        if seg_backend_widget is not None:
            seg_backend_widget.bind("<<ComboboxSelected>>", self._on_seg_backend_changed)
        self._on_seg_backend_changed()
        self._refresh_localized_texts()
        self._schedule_update_scrollbar_state()

    def _on_tab_changed(self, event) -> None:
        self._schedule_update_scrollbar_state()

    def _on_scroll_inner_configure(self, event) -> None:
        if not getattr(self, "_scroll_canvas", None) or self._scroll_window is None:
            return
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))
        self._schedule_update_scrollbar_state()

    def _on_scroll_canvas_configure(self, event) -> None:
        if not getattr(self, "_scroll_canvas", None) or self._scroll_window is None:
            return
        self._scroll_canvas.itemconfigure(self._scroll_window, width=event.width)
        self._schedule_update_scrollbar_state()

    def _schedule_update_scrollbar_state(self) -> None:
        if not getattr(self, "_scroll_canvas", None):
            return
        if self._scrollbar_update_after_id is not None:
            return
        self._scrollbar_update_after_id = self.root.after_idle(self._update_scrollbar_state)

    def _update_scrollbar_state(self) -> None:
        self._scrollbar_update_after_id = None
        if not getattr(self, "_scroll_canvas", None) or not getattr(self, "_scrollbar", None) or self._scroll_window is None:
            return
        content_bbox = self._scroll_canvas.bbox(self._scroll_window)
        if content_bbox is None:
            return
        content_height = content_bbox[3] - content_bbox[1]
        view_height = self._scroll_canvas.winfo_height()
        if content_height <= view_height:
            self._scrollbar.grid_remove()
            self._scroll_canvas.configure(yscrollcommand="")
            if self._scroll_canvas.yview()[0] != 0:
                self._scroll_canvas.yview_moveto(0)
        else:
            self._scrollbar.grid(row=1, column=1, sticky="ns")
            self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

    def _is_event_in_scroll_area(self, widget: object) -> bool:
        if not getattr(self, "_scroll_canvas", None):
            return False
        if not hasattr(widget, "winfo_parent"):
            return False
        target = self._scroll_canvas
        current = widget
        try:
            while current is not None:
                if current == target:
                    return True
                parent_name = current.winfo_parent()
                if not parent_name:
                    return False
                current = current._nametowidget(parent_name)
        except Exception:
            return False
        return False

    def _on_mouse_wheel(self, event) -> None:
        if not getattr(self, "_scroll_canvas", None):
            return
        if self._scrollbar is not None and not self._scrollbar.winfo_ismapped():
            return
        if not self._is_event_in_scroll_area(event.widget):
            return
        delta = -1 * int(event.delta / 120)
        self._scroll_canvas.yview_scroll(delta, "units")

    def _on_mouse_wheel_linux(self, event) -> None:
        if not getattr(self, "_scroll_canvas", None):
            return
        if self._scrollbar is not None and not self._scrollbar.winfo_ismapped():
            return
        if not self._is_event_in_scroll_area(event.widget):
            return
        if event.num == 4:
            self._scroll_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._scroll_canvas.yview_scroll(1, "units")

    def _add_text(self, parent, row, key, label, default, col_offset=0, readonly=False, label_key: str | None = None):
        label_text = self._tr(label_key or label, label)
        label_widget = ttk.Label(parent, text=label_text)
        if label_key is not None:
            self._register_localized_widget(label_widget, label_key, label)
        label_widget.grid(row=row, column=col_offset, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        entry = ttk.Entry(parent, textvariable=var)
        if readonly:
            entry.state(["disabled"])
        entry.grid(row=row, column=col_offset + 1, sticky="ew", padx=4)
        return label_widget

    def _add_int(self, parent, row, key, label, default, col_offset=0, readonly=False, label_key: str | None = None):
        return self._add_text(parent, row, key, label, str(default), col_offset, readonly=readonly, label_key=label_key)

    def _add_float(self, parent, row, key, label, default, col_offset=0, label_key: str | None = None):
        return self._add_text(parent, row, key, label, str(default), col_offset, label_key=label_key)

    def _add_slider(self, parent, row, key, label, default, min_value, max_value, resolution=0.01, label_key: str | None = None):
        label_text = self._tr(label_key or label, label)
        label_widget = ttk.Label(parent, text=label_text)
        if label_key is not None:
            self._register_localized_widget(label_widget, label_key, label)
        label_widget.grid(row=row, column=0, sticky="w")
        var = tk.DoubleVar(value=float(default))
        self.vars[key] = var
        value_var = tk.StringVar()

        def format_value(value: float) -> str:
            if resolution >= 1:
                return str(int(round(value)))
            return f"{value:.2f}"

        def on_change(raw):
            value_var.set(format_value(float(raw)))

        value_var.set(format_value(float(default)))
        scale = ttk.Scale(parent, from_=min_value, to=max_value, variable=var, command=on_change)

        def on_click(event):
            widget = event.widget
            width = max(1, widget.winfo_width())
            ratio = max(0.0, min(1.0, float(event.x) / float(width)))
            value = float(min_value) + ratio * (float(max_value) - float(min_value))
            var.set(value)
            value_var.set(format_value(value))
            return "break"

        scale.bind("<Button-1>", on_click)
        scale.grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=4
        )
        ttk.Label(parent, textvariable=value_var).grid(row=row, column=3, sticky="e")
        self._slider_value_vars[key] = value_var
        self._slider_formatters[key] = format_value
        self._widgets[key] = scale

    def _add_combo(self, parent, row, key, label, values, default, readonly=False, col_offset=0, label_key: str | None = None):
        label_text = self._tr(label_key or label, label)
        label_widget = ttk.Label(parent, text=label_text)
        if label_key is not None:
            self._register_localized_widget(label_widget, label_key, label)
        label_widget.grid(row=row, column=col_offset, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        state = "disabled" if readonly else "readonly"
        combo = ttk.Combobox(parent, textvariable=var, values=values, state=state)
        span = 3 if col_offset == 0 else 1
        combo.grid(row=row, column=col_offset + 1, columnspan=span, sticky="ew", padx=4)
        self._widgets[key] = combo
        return label_widget

    def _add_bool_switch(self, parent, row, key, label, default=False, label_key: str | None = None):
        var = tk.BooleanVar(value=bool(default))
        self.vars[key] = var
        label_text = self._tr(label_key or label, label)
        check_btn = ttk.Checkbutton(parent, text=label_text, variable=var)
        if label_key is not None:
            self._register_localized_widget(check_btn, label_key, label)
        check_btn.grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 2))
        self._widgets[key] = check_btn

    def _parse_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "on", "yes", "y"}

    def _on_input_device_changed(self, _event=None):
        device = self.vars["input_device"].get().strip()
        self._input_modes = discover_camera_mode_options(device)
        width_values = sorted({str(w) for w, _h, _fps in self._input_modes}, key=lambda v: int(v))
        width_combo = self._widgets.get("input_width")
        if width_combo is not None:
            width_combo["values"] = width_values
        if self.vars["input_width"].get().strip() not in width_values:
            self.vars["input_width"].set(width_values[0] if width_values else "1280")
        self._refresh_input_height_values()
        self._refresh_input_fps_values()

    def _on_input_width_changed(self, _event=None):
        self._refresh_input_height_values()
        self._refresh_input_fps_values()

    def _on_input_height_changed(self, _event=None):
        # If current pair is unsupported, snap to the first valid pair.
        try:
            w = int(self.vars["input_width"].get().strip())
            h = int(self.vars["input_height"].get().strip())
        except ValueError:
            return
        valid_pairs = {(ww, hh) for ww, hh, _fps in self._input_modes}
        if self._input_modes and (w, h) not in valid_pairs:
            w0, h0, _fps0 = self._input_modes[0]
            self.vars["input_width"].set(str(w0))
            self.vars["input_height"].set(str(h0))
            self._refresh_input_height_values()
        self._refresh_input_fps_values()

    def _refresh_input_height_values(self):
        width_raw = self.vars["input_width"].get().strip()
        try:
            w = int(width_raw)
        except ValueError:
            return
        heights = sorted({str(h) for ww, h, _fps in self._input_modes if ww == w}, key=lambda v: int(v))
        if not heights:
            heights = ["720"]
        height_combo = self._widgets.get("input_height")
        if height_combo is not None:
            height_combo["values"] = heights
        current_h = self.vars["input_height"].get().strip()
        if current_h not in heights:
            self.vars["input_height"].set(heights[0])

    def _refresh_input_fps_values(self):
        try:
            w = int(self.vars["input_width"].get().strip())
            h = int(self.vars["input_height"].get().strip())
        except ValueError:
            return
        fps_values = sorted({fps for ww, hh, fps in self._input_modes if ww == w and hh == h}, key=lambda v: float(v))
        if not fps_values:
            fps_values = ["30"]
        fps_combo = self._widgets.get("input_fps")
        if fps_combo is not None:
            fps_combo["values"] = fps_values
        current = self.vars["input_fps"].get().strip()
        if current not in fps_values:
            self.vars["input_fps"].set(fps_values[0])

    def _output_mode_options(self, device_path: str) -> list[tuple[int, int, str]]:
        if not device_path:
            return [(1280, 720, "30")]
        return discover_camera_mode_options(device_path) or [(1280, 720, "30")]

    def _refresh_output_height_values(self) -> None:
        width_raw = self.vars["output_width"].get().strip()
        try:
            w = int(width_raw)
        except ValueError:
            return
        heights = sorted(
            {str(h) for ww, h, _fps in self._output_modes if ww == w},
            key=lambda v: int(v),
        )
        if not heights:
            heights = ["720"]
        height_combo = self._widgets.get("output_height")
        if height_combo is not None:
            height_combo["values"] = heights
        current_h = self.vars["output_height"].get().strip()
        if current_h not in heights:
            self.vars["output_height"].set(heights[0])

    def _refresh_output_fps_values(self) -> None:
        try:
            w = int(self.vars["output_width"].get().strip())
            h = int(self.vars["output_height"].get().strip())
        except ValueError:
            return
        fps_values = sorted(
            {
                str(int(round(float(fps))))
                for ww, hh, fps in self._output_modes
                if ww == w and hh == h
            },
            key=lambda v: int(v),
        )
        if not fps_values:
            fps_values = ["30"]
        fps_combo = self._widgets.get("output_fps")
        if fps_combo is not None:
            fps_combo["values"] = fps_values
        current_fps = self.vars["output_fps"].get().strip()
        if current_fps not in fps_values:
            self.vars["output_fps"].set(fps_values[0])

    def _on_output_device_changed(self, _event=None) -> None:
        output_device = ""
        if self.vars.get("output_device") is not None:
            output_device = str(self.vars["output_device"].get()).strip()
        self._output_modes = self._output_mode_options(output_device)
        width_values = sorted({str(w) for w, _h, _fps in self._output_modes}, key=lambda v: int(v))
        width_combo = self._widgets.get("output_width")
        if width_combo is not None:
            width_combo["values"] = width_values
        current_w = self.vars["output_width"].get().strip()
        if current_w not in width_values:
            self.vars["output_width"].set(width_values[0] if width_values else "1280")
        self._refresh_output_height_values()
        self._refresh_output_fps_values()

    def _on_output_width_changed(self, _event=None) -> None:
        self._refresh_output_height_values()
        self._refresh_output_fps_values()

    def _on_output_height_changed(self, _event=None) -> None:
        try:
            w = int(self.vars["output_width"].get().strip())
            h = int(self.vars["output_height"].get().strip())
        except ValueError:
            return
        valid_pairs = {(ww, hh) for ww, hh, _fps in self._output_modes}
        if self._output_modes and (w, h) not in valid_pairs:
            w0, h0, _fps0 = self._output_modes[0]
            self.vars["output_width"].set(str(w0))
            self.vars["output_height"].set(str(h0))
            self._refresh_output_height_values()
        self._refresh_output_fps_values()

    def _pick_bg_image(self):
        selected = filedialog.askopenfilename(
            title=self._tr("title.select_background_image", "Select background image")
        )
        if selected:
            self.vars["bg_image"].set(selected)

    def _build_video_defaults(self) -> dict[str, float | int | str]:
        is_macos = platform.system() == "Darwin"
        cameras = discover_cameras()
        camera_values = [c["devicePath"] for c in cameras] or (["0"] if is_macos else ["/dev/video0"])
        input_device = camera_values[0]
        input_modes = discover_camera_mode_options(input_device) or [(1280, 720, "30")]
        input_width = int(input_modes[0][0])
        input_height = int(input_modes[0][1])
        input_fps = int(float(input_modes[0][2]))
        output_device = "virtual-cam" if is_macos else _default_virtual_output_device(cameras)
        output_modes = discover_camera_mode_options(output_device) or [(1280, 720, "30")]
        output_width = int(output_modes[0][0])
        output_height = int(output_modes[0][1])
        output_fps = int(float(output_modes[0][2]))

        return {
            "input_device": input_device,
            "input_width": input_width,
            "input_height": input_height,
            "input_fps": input_fps,
            "input_software_zoom": 1.0,
            "output_backend": _output_backend_options()[0],
            "output_device": output_device,
            "output_width": output_width,
            "output_height": output_height,
            "output_fps": output_fps,
            "seg_backend": "selfie",
            "seg_threshold": 0.65,
            "seg_edge_smoothness": 0.50,
            "seg_blend_feather": 0.35,
            "seg_selfie_model": 1,
            "seg_selfie_smoothing": 0.25,
            "seg_opt_model_blend": 0.60,
            "seg_opt_temporal_alpha": 0.55,
            "seg_opt_mask_blur": 5,
            "seg_opt_morph_open": 3,
            "seg_opt_morph_close": 5,
            "seg_opt_mask_gamma": 0.90,
            "bg_mode": "chroma",
            "bg_image": "",
            "bg_r": 0,
            "bg_g": 0,
            "bg_b": 0,
            "bg_blend_alpha": 0.35,
            "crop_margin": 0.25,
            "crop_pan_smoothing": 0.85,
            "crop_tilt_smoothing": 0.85,
            "crop_zoom_smoothing": 0.80,
            "crop_upper_body_bias": 0.00,
            "crop_upper_body_ratio": 0.60,
            "crop_upper_body_edge_smoothing": 0.35,
            "crop_pan_pid_kp": 0.35,
            "crop_pan_pid_ki": 0.01,
            "crop_pan_pid_kd": 0.12,
            "crop_tilt_pid_kp": 0.35,
            "crop_tilt_pid_ki": 0.01,
            "crop_tilt_pid_kd": 0.12,
            "crop_pan_target_offset_x": 0.00,
            "crop_pan_target_offset_y": 0.00,
            "face_enhance_enabled": False,
            "face_enhance_gamma": 1.0,
            "face_enhance_brightness": 0.0,
            "face_enhance_saturation": 1.0,
            "face_enhance_blend": 0.65,
            "face_enhance_min_size_ratio": 0.12,
            "face_enhance_edge_dither": 0.25,
            "face_deidentify_enabled": False,
        }

    def _create_virtual_camera(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror(
                self._tr("title.virtual_camera", "Virtual camera"),
                self._tr(
                    "msg.virtual_camera_only_linux",
                    "Linux only: virtual camera can be created on Linux.",
                ),
            )
            return

        backend = self.vars.get("output_backend").get() if self.vars.get("output_backend") else ""
        if backend != "v4l2loopback":
            messagebox.showerror(
                self._tr("title.virtual_camera", "Virtual camera"),
                self._tr(
                    "msg.virtual_camera_backend_required",
                    "output_backend must be v4l2loopback.",
                ),
            )
            return

        device = (self.vars.get("output_device").get() if self.vars.get("output_device") else "").strip()
        video_no = _parse_video_device_number(device)
        if not video_no:
            messagebox.showerror(
                self._tr("title.virtual_camera", "Virtual camera"),
                self._tr("msg.virtual_camera_invalid_output", "Output path is invalid: {device}").format(device=device),
            )
            return

        _log(f"Create virtual camera via avc-device: {device} label={VIRTUAL_CAMERA_LABEL}")
        try:
            _run_avc_device(
                "camera",
                "create",
                extra_env={
                    "AVC_OUTPUT_DEVICE": device,
                    "AVC_CAMERA_LABEL": VIRTUAL_CAMERA_LABEL,
                },
                timeout=8.0,
            )
        except Exception as exc:
            _log(f"가상 카메라 생성 실패: {exc}")
            messagebox.showerror(self._tr("title.virtual_camera", "Virtual camera"), str(exc))
            return

        ready, detail = _probe_v4l2_capture(
            device,
            retries=10,
            delay_sec=0.2,
            require_output=True,
        )
        if not ready:
            _log(f"가상 카메라 생성 후 상태 확인 실패: {detail}")
            messagebox.showerror(
                self._tr("title.virtual_camera", "Virtual camera"),
                self._tr(
                    "msg.virtual_camera_verify_failed",
                    "Virtual camera created, but state validation failed.\n{detail}",
                ).format(detail=detail),
            )
            return
        _log(f"Virtual camera webcam-capable confirmed on {device}: {detail}")
        messagebox.showinfo(
            self._tr("title.virtual_camera", "Virtual camera"),
            self._tr("msg.virtual_camera_created", "Virtual camera created: {device}").format(device=device),
        )

    def _remove_virtual_camera(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror(
                self._tr("title.virtual_camera", "Virtual camera"),
                self._tr(
                    "msg.virtual_camera_remove_only_linux",
                    "Linux only: virtual camera can be removed on Linux.",
                ),
            )
            return

        _log("Remove virtual camera via avc-device")
        try:
            _run_avc_device("camera", "delete", timeout=8.0)
        except Exception as exc:
            _log(f"가상 카메라 제거 실패: {exc}")
            messagebox.showerror(self._tr("title.virtual_camera", "Virtual camera"), str(exc))
            return
        _log("Virtual camera removed: modprobe -r v4l2loopback")
        messagebox.showinfo(
            self._tr("title.virtual_camera", "Virtual camera"),
            self._tr("msg.virtual_camera_removed", "Virtual camera module has been unloaded."),
        )

    def _build_audio_defaults(self) -> dict[str, float | int | str]:
        denoise_backends = _audio_denoise_backend_options()
        return {
            "audio_enabled": True,
            "audio_input_device": _audio_default_input_device(),
            "audio_output_device": _audio_default_output_device(),
            "audio_sample_rate": 48000,
            "audio_channels": 1,
            "audio_frame_ms": 20,
            "audio_denoise_enabled": True,
            "audio_denoise_backend": denoise_backends[0],
            "audio_denoise_strength": 0.5,
            "audio_gate_threshold_db": -40.0,
            "audio_gate_hysteresis_db": 4.0,
            "audio_gate_min_voice_band_ratio": 0.50,
            "audio_gate_attack_ms": 30,
            "audio_gate_hold_ms": 160,
            "audio_gate_release_ms": 2000,
            "audio_gate_open_gain": 1.0,
            "audio_gate_closed_gain": 0.0,
        }

    def _create_virtual_speaker(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror(
                self._tr("title.virtual_mic", "Virtual microphone"),
                self._tr(
                    "msg.virtual_mic_only_linux",
                    "Linux only: virtual microphone can be created on Linux.",
                ),
            )
            return

        _log(f"Create virtual microphone via avc-device: {AUDIO_VIRTUAL_SINK_NAME}")
        try:
            _run_avc_device(
                "audio",
                "create",
                extra_env={
                    "AVC_AUDIO_SINK_NAME": AUDIO_VIRTUAL_SINK_NAME,
                    "AVC_AUDIO_SINK_DESC": AUDIO_VIRTUAL_SINK_NAME,
                },
                timeout=25.0,
            )
        except Exception as exc:
            _log(f"가상 마이크 생성 실패: {exc}")
            messagebox.showerror(self._tr("title.virtual_mic", "Virtual microphone"), str(exc))
            return
        _log(f"Virtual microphone sink created: {AUDIO_VIRTUAL_SINK_NAME}")
        messagebox.showinfo(
            self._tr("title.virtual_mic", "Virtual microphone"),
            self._tr(
                "msg.virtual_mic_created",
                "Created virtual microphone sink: {name}. Use '{name}.monitor' in your meeting app input.",
            ).format(name=AUDIO_VIRTUAL_SINK_NAME),
        )

    def _remove_virtual_speaker(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror(
                self._tr("title.virtual_mic", "Virtual microphone"),
                self._tr(
                    "msg.virtual_mic_remove_only_linux",
                    "Linux only: virtual microphone can be removed on Linux.",
                ),
            )
            return

        try:
            _run_avc_device(
                "audio",
                "delete",
                extra_env={"AVC_AUDIO_SINK_NAME": AUDIO_VIRTUAL_SINK_NAME},
                timeout=25.0,
            )
        except Exception as exc:
            _log(f"가상 마이크 제거 실패: {exc}")
            messagebox.showerror(self._tr("title.virtual_mic", "Virtual microphone"), str(exc))
            return
        _log(f"Virtual microphone removed: {AUDIO_VIRTUAL_SINK_NAME}")
        messagebox.showinfo(
            self._tr("title.virtual_mic", "Virtual microphone"),
            self._tr("msg.virtual_mic_removed", "Virtual microphone module removed: {name}").format(
                name=AUDIO_VIRTUAL_SINK_NAME
            ),
        )

    def _reset_io_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key in (
            "input_device",
            "input_width",
            "input_height",
            "input_fps",
            "input_software_zoom",
            "output_backend",
            "output_device",
            "output_width",
            "output_height",
            "output_fps",
        ):
            self._set_var(key, defaults.get(key))
        self._on_input_device_changed()
        self._on_input_width_changed()
        self._on_output_device_changed()
        self._on_output_height_changed()

    def _reset_seg_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key in (
            "seg_backend",
            "seg_threshold",
            "seg_edge_smoothness",
            "seg_blend_feather",
            "seg_selfie_model",
            "seg_selfie_smoothing",
            "seg_opt_model_blend",
            "seg_opt_temporal_alpha",
            "seg_opt_mask_blur",
            "seg_opt_morph_open",
            "seg_opt_morph_close",
            "seg_opt_mask_gamma",
        ):
            self._set_var(key, defaults.get(key))
        self._on_seg_backend_changed()

    def _reset_bg_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key in ("bg_mode", "bg_image", "bg_r", "bg_g", "bg_b", "bg_blend_alpha"):
            value = defaults.get(key)
            self._set_var(key, value)

    def _reset_crop_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key in (
            "crop_margin",
            "crop_pan_smoothing",
            "crop_tilt_smoothing",
            "crop_zoom_smoothing",
            "crop_upper_body_bias",
            "crop_upper_body_ratio",
            "crop_upper_body_edge_smoothing",
            "crop_pan_pid_kp",
            "crop_pan_pid_ki",
            "crop_pan_pid_kd",
            "crop_tilt_pid_kp",
            "crop_tilt_pid_ki",
            "crop_tilt_pid_kd",
            "crop_pan_target_offset_x",
            "crop_pan_target_offset_y",
        ):
            self._set_var(key, defaults.get(key))

    def _reset_face_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key in (
            "face_enhance_enabled",
            "face_enhance_gamma",
            "face_enhance_brightness",
            "face_enhance_saturation",
            "face_enhance_blend",
            "face_enhance_min_size_ratio",
            "face_enhance_edge_dither",
            "face_deidentify_enabled",
        ):
            self._set_var(key, defaults.get(key))

    def _reset_audio_settings(self) -> None:
        defaults = self._build_audio_defaults()
        for key, value in defaults.items():
            self._set_var(key, value)

    def _load_existing_config(self):
        config_path = Path(self.output_path).expanduser()
        if not config_path.exists():
            return
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showwarning(
                self._tr("msg.load_warning.title", "Load warning"),
                self._tr("msg.load_warning.body", "Failed to parse config file:\n{path}\n\n{error}").format(
                    path=config_path,
                    error=exc,
                ),
            )
            return
        meta_cfg = raw.get("meta") or {}
        lang = str(meta_cfg.get("language", "")).strip().lower()
        if lang in {"ko", "en"}:
            self._language_var.set(lang)

        input_cfg = raw.get("inputCamera") or {}
        output_cfg = raw.get("outputCamera") or {}
        seg_cfg = raw.get("segmentation") or {}
        selfie_cfg = seg_cfg.get("selfie") or {}
        bg_cfg = raw.get("background") or {}
        crop_cfg = raw.get("crop") or {}
        audio_cfg = raw.get("audio") or {}
        face_cfg = raw.get("faceEnhance") or {}

        self._set_var("input_device", input_cfg.get("devicePath"))
        self._set_var("input_width", input_cfg.get("width"))
        self._set_var("input_height", input_cfg.get("height"))
        self._set_var("input_fps", input_cfg.get("fps"))
        self._set_var("input_software_zoom", input_cfg.get("softwareZoom"))

        self._set_var("output_backend", output_cfg.get("backend"))
        self._set_var("output_device", output_cfg.get("devicePath"))
        self._set_var("output_width", output_cfg.get("width"))
        self._set_var("output_height", output_cfg.get("height"))
        self._set_var("output_fps", output_cfg.get("fps"))

        self._set_var("seg_backend", seg_cfg.get("backend"))
        self._set_var("seg_threshold", seg_cfg.get("threshold"))
        self._set_var("seg_edge_smoothness", seg_cfg.get("edgeSmoothness"))
        self._set_var("seg_blend_feather", seg_cfg.get("blendFeather"))
        self._set_var("seg_selfie_model", selfie_cfg.get("modelSelection"))
        self._set_var("seg_selfie_smoothing", selfie_cfg.get("temporalSmoothing"))
        seg_backend = str(seg_cfg.get("backend", "")).strip()
        seg_engine_options = {}
        all_engine_options = seg_cfg.get("engineOptions") or {}
        if seg_backend and isinstance(all_engine_options, dict):
            candidate = all_engine_options.get(seg_backend) or {}
            if isinstance(candidate, dict):
                seg_engine_options = candidate
        self._apply_seg_engine_options_to_form(seg_engine_options)

        self._set_var("bg_mode", bg_cfg.get("mode"))
        chroma = bg_cfg.get("chromaColor") or []
        if len(chroma) == 3:
            self._set_var("bg_r", chroma[0])
            self._set_var("bg_g", chroma[1])
            self._set_var("bg_b", chroma[2])
        self._set_var("bg_image", bg_cfg.get("imagePath"))
        self._set_var("bg_blend_alpha", bg_cfg.get("colorBlendAlpha"))

        self._set_var("crop_margin", crop_cfg.get("margin"))
        self._set_var("crop_pan_smoothing", crop_cfg.get("panSmoothing", crop_cfg.get("smoothing")))
        self._set_var("crop_tilt_smoothing", crop_cfg.get("tiltSmoothing", crop_cfg.get("panSmoothing", crop_cfg.get("smoothing"))))
        self._set_var("crop_zoom_smoothing", crop_cfg.get("zoomSmoothing"))
        self._set_var("crop_upper_body_bias", crop_cfg.get("upperBodyBias"))
        self._set_var("crop_upper_body_ratio", crop_cfg.get("upperBodyRatio"))
        self._set_var("crop_upper_body_edge_smoothing", crop_cfg.get("upperBodyEdgeSmoothing"))
        self._set_var("crop_pan_pid_kp", crop_cfg.get("panPidKp"))
        self._set_var("crop_pan_pid_ki", crop_cfg.get("panPidKi"))
        self._set_var("crop_pan_pid_kd", crop_cfg.get("panPidKd"))
        self._set_var("crop_tilt_pid_kp", crop_cfg.get("tiltPidKp", crop_cfg.get("panPidKp")))
        self._set_var("crop_tilt_pid_ki", crop_cfg.get("tiltPidKi", crop_cfg.get("panPidKi")))
        self._set_var("crop_tilt_pid_kd", crop_cfg.get("tiltPidKd", crop_cfg.get("panPidKd")))
        self._set_var("crop_pan_target_offset_x", crop_cfg.get("panTargetOffsetX"))
        self._set_var("crop_pan_target_offset_y", crop_cfg.get("panTargetOffsetY"))
        self._set_var("face_enhance_enabled", face_cfg.get("enabled"))
        self._set_var("face_enhance_gamma", face_cfg.get("gamma"))
        self._set_var("face_enhance_brightness", face_cfg.get("offset"))
        self._set_var("face_enhance_saturation", face_cfg.get("saturation"))
        self._set_var("face_enhance_blend", face_cfg.get("strength"))
        self._set_var("face_enhance_min_size_ratio", face_cfg.get("minRegionRatio"))
        self._set_var("face_enhance_edge_dither", face_cfg.get("edgeNoise"))
        self._set_var("face_deidentify_enabled", (face_cfg.get("deidentify") or {}).get("enabled"))
        self._load_audio_settings_from_config(audio_cfg)
        self._on_input_device_changed()
        self._on_input_width_changed()
        self._on_output_device_changed()
        self._on_output_height_changed()

    def _load_audio_settings_from_config(self, audio_cfg: dict) -> None:
        defaults = self._build_audio_defaults()
        denoise_cfg = audio_cfg.get("denoise") or {}
        gate_cfg = audio_cfg.get("gate") or {}

        self._set_var("audio_enabled", audio_cfg.get("enabled", defaults["audio_enabled"]))
        raw_input_device = str(audio_cfg.get("inputDevice", "")).strip() if isinstance(audio_cfg.get("inputDevice"), str) else ""
        raw_output_device = (
            str(audio_cfg.get("outputDevice", "")).strip() if isinstance(audio_cfg.get("outputDevice"), str) else ""
        )
        resolved_input_device = defaults["audio_input_device"] if not raw_input_device else raw_input_device
        resolved_output_device = defaults["audio_output_device"] if not raw_output_device else raw_output_device
        self._set_var("audio_input_device", resolved_input_device)
        input_widget = self._widgets.get("audio_input_device")
        if isinstance(input_widget, ttk.Combobox):
            input_values = list(input_widget["values"])
            input_display = next(
                (k for k, v in getattr(self, "_audio_input_display_to_raw", {}).items() if v == resolved_input_device),
                resolved_input_device,
            )
            if input_display not in input_values:
                input_widget["values"] = tuple(input_values + [input_display])
                getattr(self, "_audio_input_display_to_raw", {})[input_display] = resolved_input_device
            self.vars["audio_input_device"].set(input_display)
        self._set_var("audio_output_device", resolved_output_device)
        output_widget = self._widgets.get("audio_output_device")
        if isinstance(output_widget, ttk.Combobox):
            output_values = list(output_widget["values"])
            output_display = next(
                (k for k, v in getattr(self, "_audio_output_display_to_raw", {}).items() if v == resolved_output_device),
                resolved_output_device,
            )
            if output_display not in output_values:
                output_widget["values"] = tuple(output_values + [output_display])
                getattr(self, "_audio_output_display_to_raw", {})[output_display] = resolved_output_device
            self.vars["audio_output_device"].set(output_display)
        self._set_var("audio_sample_rate", audio_cfg.get("sampleRate", defaults["audio_sample_rate"]))
        self._set_var("audio_channels", audio_cfg.get("channels", defaults["audio_channels"]))
        self._set_var("audio_frame_ms", audio_cfg.get("frameMs", defaults["audio_frame_ms"]))
        self._set_var("audio_denoise_enabled", denoise_cfg.get("enabled", defaults["audio_denoise_enabled"]))
        self._set_var("audio_denoise_backend", denoise_cfg.get("backend", defaults["audio_denoise_backend"]))
        self._set_var("audio_denoise_strength", denoise_cfg.get("strength", defaults["audio_denoise_strength"]))
        denoise_backend_widget = self._widgets.get("audio_denoise_backend")
        if denoise_backend_widget is not None:
            allowed = _audio_denoise_backend_options()
            denoise_backend_widget["values"] = allowed
            current_backend = self.vars["audio_denoise_backend"].get().strip()
            if current_backend not in allowed:
                self._set_var("audio_denoise_backend", allowed[0])

        self._set_var("audio_gate_threshold_db", gate_cfg.get("thresholdDb", defaults["audio_gate_threshold_db"]))
        self._set_var("audio_gate_hysteresis_db", gate_cfg.get("hysteresisDb", defaults["audio_gate_hysteresis_db"]))
        self._set_var(
            "audio_gate_min_voice_band_ratio",
            gate_cfg.get("minVoiceBandRatio", defaults["audio_gate_min_voice_band_ratio"]),
        )
        self._set_var("audio_gate_attack_ms", gate_cfg.get("attackMs", defaults["audio_gate_attack_ms"]))
        self._set_var("audio_gate_hold_ms", gate_cfg.get("holdMs", defaults["audio_gate_hold_ms"]))
        self._set_var("audio_gate_release_ms", gate_cfg.get("releaseMs", defaults["audio_gate_release_ms"]))
        self._set_var("audio_gate_open_gain", gate_cfg.get("openGain", defaults["audio_gate_open_gain"]))
        self._set_var("audio_gate_closed_gain", gate_cfg.get("closedGain", defaults["audio_gate_closed_gain"]))

    def _set_var(self, key: str, value):
        if value is None:
            return
        var = self.vars.get(key)
        if var is None:
            return
        if isinstance(var, tk.BooleanVar):
            var.set(self._parse_bool(value))
            return
        if isinstance(var, tk.DoubleVar):
            try:
                float_value = float(value)
            except (TypeError, ValueError):
                return
            var.set(float_value)
            value_var = self._slider_value_vars.get(key)
            if value_var is not None:
                formatter = self._slider_formatters.get(key)
                if formatter is not None:
                    value_var.set(formatter(float_value))
            return
        if isinstance(var, tk.IntVar):
            try:
                int_value = int(float(value))
            except (TypeError, ValueError):
                return
            var.set(int_value)
            value_var = self._slider_value_vars.get(key)
            if value_var is not None:
                formatter = self._slider_formatters.get(key)
                if formatter is not None:
                    value_var.set(formatter(float(int_value)))
            return
        var.set(str(value))

    def _pick_chroma_color(self):
        rgb_default = (
            int(self.vars["bg_r"].get()),
            int(self.vars["bg_g"].get()),
            int(self.vars["bg_b"].get()),
        )
        picked_rgb, _ = colorchooser.askcolor(
            color="#%02x%02x%02x" % rgb_default,
            title=self._tr("title.select_chroma_color", "Select chroma color"),
        )
        if picked_rgb is None:
            return
        r, g, b = (int(picked_rgb[0]), int(picked_rgb[1]), int(picked_rgb[2]))
        self.vars["bg_r"].set(str(r))
        self.vars["bg_g"].set(str(g))
        self.vars["bg_b"].set(str(b))

    def _save(self):
        try:
            config = self._build_config()
            config.setdefault("meta", {})["language"] = self._language_var.get().strip().lower() or self._lang
            write_config(self.output_path, config)
            messagebox.showinfo(
                self._tr("msg.saved.title", "Saved"),
                self._tr("msg.saved.body", "Config saved to {path}").format(path=self.output_path),
            )
        except Exception as exc:
            _log(f"Validation error: {exc}")
            messagebox.showerror(self._tr("msg.validation_error.title", "Validation error"), str(exc))

    def _auto_tune_audio_gate(self):
        if sd is None:
            messagebox.showerror(
                self._tr("title.audio_tune_error", "Audio tuning error"),
                self._tr("msg.audio_tune_sounddevice_missing", "sounddevice module is missing. Run ./bin/avc setup and try again."),
            )
            return
        if self._audio_tune_running:
            return
        try:
            sample_rate = int(self.vars["audio_sample_rate"].get())
            channels = int(self.vars["audio_channels"].get())
        except Exception:
            messagebox.showerror(
                self._tr("title.audio_tune_error", "Audio tuning error"),
                self._tr("msg.audio_tune_invalid_rate_channels", "audio sample rate/channels is invalid."),
            )
            return
        if channels <= 0:
            channels = 1

        if self._audio_tune_window is None or not self._audio_tune_window.winfo_exists():
            self._audio_tune_window = tk.Toplevel(self.root)
            self._audio_tune_window.title(self._tr("title.audio_tune", "Audio gate auto tuning"))
            self._audio_tune_window.geometry("560x260")
            self._audio_tune_window.resizable(False, False)
            self._audio_tune_window.grab_set()

            container = ttk.Frame(self._audio_tune_window, padding=12)
            container.grid(sticky="nsew")
            for c in range(1):
                container.columnconfigure(c, weight=1)

            self._audio_tune_step_var = tk.StringVar(value=self._tr("audio_tune.step_label_waiting", "Waiting"))
            self._audio_tune_step_list_var = tk.StringVar(value="")
            self._audio_tune_timer_var = tk.StringVar(value=self._tr("audio_tune.timer", "Timer: -"))
            self._audio_tune_status_var = tk.StringVar(value=self._tr("audio_tune.status_hint_start", "Click step 1 to start."))
            self._audio_tune_summary_var = tk.StringVar(value=self._tr("audio_tune.result_placeholder", "Results will appear here."))

            ttk.Label(
                container, text=self._tr("title.audio_tune", "Audio gate auto tuning"), font=("Arial", 12, "bold")
            ).grid(
                row=0, column=0, sticky="ew", pady=(0, 8)
            )
            ttk.Label(container, textvariable=self._audio_tune_step_var).grid(row=1, column=0, sticky="w")
            ttk.Label(container, textvariable=self._audio_tune_step_list_var, justify="left", wraplength=520).grid(
                row=2, column=0, sticky="w", pady=(4, 0)
            )
            ttk.Label(container, textvariable=self._audio_tune_status_var).grid(row=3, column=0, sticky="w", pady=(4, 0))
            ttk.Label(container, textvariable=self._audio_tune_timer_var).grid(row=4, column=0, sticky="w", pady=(4, 0))
            ttk.Label(container, textvariable=self._audio_tune_summary_var, wraplength=520).grid(
                row=5, column=0, sticky="w", pady=(8, 0)
            )

            btn_row = ttk.Frame(container)
            btn_row.grid(row=6, column=0, sticky="ew", pady=(12, 0))
            self._audio_tune_action_btn = ttk.Button(
                btn_row,
                text=self._tr("button.audio_tune_step_start", "Start Step 1"),
                command=self._run_audio_tune_next_step,
            )
            self._audio_tune_action_btn.pack(side="left")
            close_btn = ttk.Button(btn_row, text=self._tr("button.close", "Close"), command=self._close_auto_tune_window)
            close_btn.pack(side="right")
            self._audio_tune_window.protocol("WM_DELETE_WINDOW", self._close_auto_tune_window)
        else:
            self._audio_tune_window.lift()
            if self._audio_tune_step_var is not None:
                self._audio_tune_step_var.set(self._tr("audio_tune.step_label_waiting", "Waiting"))
            if self._audio_tune_step_list_var is not None:
                self._audio_tune_step_list_var.set("")
            if self._audio_tune_status_var is not None:
                self._audio_tune_status_var.set(self._tr("audio_tune.status_hint_start", "Click step 1 to start."))
            if self._audio_tune_timer_var is not None:
                self._audio_tune_timer_var.set(self._tr("audio_tune.timer", "Timer: -"))
            if self._audio_tune_summary_var is not None:
                self._audio_tune_summary_var.set(self._tr("audio_tune.result_placeholder", "Results will appear here."))
            if self._audio_tune_action_btn is not None and self._audio_tune_action_btn.winfo_exists():
                self._audio_tune_action_btn.configure(text=self._tr("button.audio_tune_step_start", "Start Step 1"), state="normal")
            elif self._audio_tune_window is not None and self._audio_tune_window.winfo_exists():
                # Keep button state consistent even if internal handle was lost.
                for widget in self._audio_tune_window.winfo_children():
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Button) and child.cget("text") == self._tr(
                            "button.audio_tune_step_start", "Start Step 1"
                        ):
                            self._audio_tune_action_btn = child
                            break

        self._audio_tune_window.protocol("WM_DELETE_WINDOW", self._close_auto_tune_window)

        self._audio_tune_running = True
        self._audio_tune_cancelled = False
        self._audio_tune_is_recording = False
        self._audio_tune_done = False
        self._audio_tune_error = None
        self._audio_tune_result_text = ""
        self._audio_tune_ambient = None
        self._audio_tune_step = 0
        self._audio_tune_progress = self._tr("audio_tune.progress_start_hint", "Press Start Step 1 to begin.")
        if self._audio_tune_step_var is not None:
            self._audio_tune_step_var.set(self._tr("audio_tune.step_counter", "Step {step}/2").format(step=0))
        if self._audio_tune_step_list_var is not None:
            self._audio_tune_step_list_var.set(
                self._tr("audio_tune.step_list_initial", "1) Capture quiet-environment audio (idle)\\n2) Capture voice sample (idle)")
            )
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set(self._tr("audio_tune.status_hint", "Click step 1 to continue."))
        if self._audio_tune_summary_var is not None:
            self._audio_tune_summary_var.set(self._tr("audio_tune.result_placeholder", "Results will appear here."))
        if self._audio_tune_timer_var is not None:
            self._audio_tune_timer_var.set(self._tr("audio_tune.timer", "Timer: -"))

        self._auto_tune_audio_gate_tick()

    def _run_audio_tune_next_step(self) -> None:
        if self._audio_tune_cancelled or not self._audio_tune_running or self._audio_tune_is_recording:
            return
        if self._audio_tune_done or self._audio_tune_error is not None:
            return

        try:
            sample_rate = int(self.vars["audio_sample_rate"].get())
            channels = int(self.vars["audio_channels"].get())
        except Exception:
            self._audio_tune_error = self._tr("msg.audio_tune_invalid_rate_channels", "audio sample rate/channels is invalid.")
            self._audio_tune_running = False
            return
        if channels <= 0:
            channels = 1

        if self._audio_tune_step == 0:
            self._start_tune_step_ambient(sample_rate, channels)
        elif self._audio_tune_step == 1:
            self._start_tune_step_speech(sample_rate, channels)
        else:
            self._audio_tune_error = self._tr("msg.audio_tune_invalid_step", "Invalid step state.")
            self._audio_tune_running = False

    def _start_tune_step_ambient(self, sample_rate: int, channels: int) -> None:
        if self._audio_tune_running is False:
            return

        self._audio_tune_is_recording = True
        self._audio_tune_step = 1
        self._audio_tune_progress = self._tr("audio_tune.progress_ambient", "Stay still and quiet for 2 seconds (measuring background noise).")
        self._audio_tune_step_deadline = time.time() + 2.0
        if self._audio_tune_step_list_var is not None:
            self._audio_tune_step_list_var.set(
                self._tr(
                    "audio_tune.step_list_ambient_running",
                    "1) Capture quiet-environment audio (running)\\n2) Capture voice sample (idle)",
                )
            )
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set(self._tr("audio_tune.status_ambient", "Step 1 recording in progress."))

        def _worker() -> None:
            try:
                ambient = self._record_audio_block(seconds=2.0, sample_rate=sample_rate, channels=channels, show_error=False)
                if self._audio_tune_cancelled:
                    return
                if ambient is None:
                    self._audio_tune_error = self._tr("msg.audio_tune_ambient_capture_failed", "Failed to measure ambient noise.")
                    self._audio_tune_running = False
                    return

                self._audio_tune_ambient = ambient
                self._audio_tune_progress = self._tr("audio_tune.progress_step1_done", "Step 1 completed. Start step 2.")
                if self._audio_tune_step_list_var is not None:
                    self._audio_tune_step_list_var.set(
                        self._tr(
                            "audio_tune.step_list_ambient_done",
                            "1) Capture quiet-environment audio (done)\\n2) Capture voice sample (idle)",
                        )
                    )
            except Exception as exc:
                self._audio_tune_error = str(exc)
                self._audio_tune_running = False
            finally:
                self._audio_tune_is_recording = False

        threading.Thread(target=_worker, daemon=True).start()

    def _start_tune_step_speech(self, sample_rate: int, channels: int) -> None:
        if self._audio_tune_running is False:
            return
        if self._audio_tune_ambient is None:
            self._audio_tune_error = self._tr("msg.audio_tune_need_step1", "Please complete step 1 first.")
            self._audio_tune_running = False
            return

        self._audio_tune_is_recording = True
        self._audio_tune_step = 2
        self._audio_tune_progress = self._tr(
            "audio_tune.progress_speech",
            "Talk normally for 3 seconds (measuring voice baseline).",
        )
        self._audio_tune_step_deadline = time.time() + 3.0
        if self._audio_tune_step_list_var is not None:
            self._audio_tune_step_list_var.set(
                self._tr(
                    "audio_tune.step_list_speech_running",
                    "1) Capture quiet-environment audio (done)\\n2) Capture voice sample (running)",
                )
            )
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set(self._tr("audio_tune.status_speech", "Step 2 recording in progress."))

        def _worker() -> None:
            try:
                speech = self._record_audio_block(seconds=3.0, sample_rate=sample_rate, channels=channels, show_error=False)
                if self._audio_tune_cancelled:
                    return
                if speech is None:
                    self._audio_tune_error = self._tr("msg.audio_tune_speech_capture_failed", "Failed to measure voice sample.")
                    self._audio_tune_running = False
                    return

                ambient = self._audio_tune_ambient
                if ambient is None:
                    self._audio_tune_error = self._tr("msg.audio_tune_ambient_missing", "Missing step 1 data.")
                    self._audio_tune_running = False
                    return

                ambient_db = self._rms_dbfs(ambient)
                speech_db = self._rms_dbfs(speech)
                ambient_voice = self._voice_band_ratio(ambient, sample_rate)
                speech_voice = self._voice_band_ratio(speech, sample_rate)

                if speech_db <= ambient_db + 1.0:
                    threshold_db = ambient_db + 2.0
                    hysteresis_db = 6.0
                else:
                    threshold_db = ambient_db + (speech_db - ambient_db) * 0.35
                    hysteresis_db = (speech_db - ambient_db) * 0.18
                threshold_db = float(max(-80.0, min(0.0, threshold_db)))
                hysteresis_db = float(max(1.5, min(12.0, hysteresis_db)))
                min_voice_ratio = float(max(0.10, min(0.95, (ambient_voice + speech_voice) * 0.5 + 0.05)))

                self.vars["audio_gate_threshold_db"].set(threshold_db)
                self.vars["audio_gate_hysteresis_db"].set(hysteresis_db)
                self.vars["audio_gate_min_voice_band_ratio"].set(min_voice_ratio)
                self._audio_tune_result_text = (
                    self._tr("msg.audio_tune_result_prefix", "Applied recommended values.") + "\\n"
                    + self._tr(
                        "msg.audio_tune_result_threshold",
                        "- thresholdDb: {threshold_db}",
                    ).format(threshold_db=f"{threshold_db:.1f}")
                    + "\\n"
                    + self._tr(
                        "msg.audio_tune_result_hysteresis",
                        "- hysteresisDb: {hysteresis_db}",
                    ).format(hysteresis_db=f"{hysteresis_db:.1f}")
                    + "\\n"
                    + self._tr(
                        "msg.audio_tune_result_min_ratio",
                        "- minVoiceBandRatio: {ratio}",
                    ).format(ratio=f"{min_voice_ratio:.2f}")
                )
                self._audio_tune_done = True
                self._audio_tune_progress = self._tr("audio_tune.progress_done", "Done")
                self._audio_tune_running = False
                if self._audio_tune_step_list_var is not None:
                    self._audio_tune_step_list_var.set(
                        self._tr(
                            "audio_tune.step_list_done",
                            "1) Capture quiet-environment audio (done)\\n2) Capture voice sample (done)",
                        )
                    )
            except Exception as exc:
                self._audio_tune_error = str(exc)
                self._audio_tune_running = False
            finally:
                self._audio_tune_is_recording = False
                self._audio_tune_running = False

        threading.Thread(target=_worker, daemon=True).start()

    def _auto_tune_audio_gate_tick(self):
        if self._audio_tune_window is None or not self._audio_tune_window.winfo_exists():
            self._audio_tune_running = False
            return

        if self._audio_tune_step_var is not None:
            self._audio_tune_step_var.set(
                self._tr("audio_tune.step_counter", "Step {step}/2").format(step=self._audio_tune_step)
            )
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set(self._audio_tune_progress or self._tr("audio_tune.status_processing", "Processing..."))

        remaining = 0.0
        if (
            self._audio_tune_running
            and self._audio_tune_is_recording
            and self._audio_tune_step in (1, 2)
            and self._audio_tune_step_deadline > 0.0
        ):
            remaining = max(0.0, self._audio_tune_step_deadline - time.time())
        if self._audio_tune_timer_var is not None:
            self._audio_tune_timer_var.set(self._tr("audio_tune.timer", "Timer: {seconds:.1f}s").format(seconds=remaining))

        if self._audio_tune_summary_var is not None:
            if self._audio_tune_error is not None:
                self._audio_tune_summary_var.set(f"{self._tr('msg.error_prefix', 'Error')}: {self._audio_tune_error}")
            elif self._audio_tune_done:
                self._audio_tune_summary_var.set(self._audio_tune_result_text)
            else:
                self._audio_tune_summary_var.set(self._audio_tune_progress)

        if self._audio_tune_action_btn is not None:
            if self._audio_tune_error is not None or self._audio_tune_done:
                self._audio_tune_action_btn.configure(state="disabled")
            elif self._audio_tune_is_recording:
                self._audio_tune_action_btn.configure(state="disabled")
            elif self._audio_tune_step == 0:
                self._audio_tune_action_btn.configure(text=self._tr("button.audio_tune_step_start", "Start Step 1"), state="normal")
            elif self._audio_tune_step == 1:
                self._audio_tune_action_btn.configure(text=self._tr("button.audio_tune_step2_start", "Start Step 2"), state="normal")
            elif self._audio_tune_step >= 2:
                self._audio_tune_action_btn.configure(state="disabled")

        if self._audio_tune_running or self._audio_tune_is_recording:
            self._audio_tune_after_id = self.root.after(100, self._auto_tune_audio_gate_tick)
            return

        if self._audio_tune_done:
            if self._audio_tune_step_list_var is not None:
                self._audio_tune_step_list_var.set(
                    self._tr("audio_tune.step_list_done", "1) Capture quiet-environment audio (done)\\n2) Capture voice sample (done)")
                )
            if self._audio_tune_summary_var is not None:
                self._audio_tune_summary_var.set(self._audio_tune_result_text or self._tr("audio_tune.progress_done", "Done"))
            if self._audio_tune_step_var is not None:
                self._audio_tune_step_var.set(self._tr("audio_tune.done", "Done"))
            if self._audio_tune_status_var is not None:
                self._audio_tune_status_var.set(self._tr("audio_tune.status_completed", "Audio gate auto tuning completed."))
            if self._audio_tune_timer_var is not None:
                self._audio_tune_timer_var.set(self._tr("audio_tune.timer", "Timer: {seconds:.1f}s").format(seconds=0.0))
        elif self._audio_tune_error is not None:
            if self._audio_tune_step_list_var is not None:
                self._audio_tune_step_list_var.set(
                    self._tr(
                        "audio_tune.step_list_failed",
                        "1) Capture quiet-environment audio (done/fail)\\n2) Capture voice sample (done/fail)",
                    )
                )
            if self._audio_tune_step_var is not None:
                self._audio_tune_step_var.set(self._tr("audio_tune.failed", "Failed"))
            if self._audio_tune_status_var is not None:
                self._audio_tune_status_var.set(self._tr("audio_tune.status_aborted", "Stopped due to an error."))

    def _close_auto_tune_window(self) -> None:
        self._audio_tune_cancelled = True
        self._audio_tune_running = False
        after_id = self._audio_tune_after_id
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._audio_tune_after_id = None
        self._audio_tune_action_btn = None
        if self._audio_tune_window is not None:
            try:
                self._audio_tune_window.destroy()
            except Exception:
                pass
        self._audio_tune_window = None

    def _run_audio_gate_test(self):
        try:
            config = self._build_config()
        except Exception as exc:
            messagebox.showerror(self._tr("title.audio_gate_test_error", "Audio gate test error"), str(exc))
            return

        audio_cfg = config.get("audio") or {}
        if audio_cfg.get("enabled", False) is False:
            proceed = messagebox.askyesno(
                self._tr("title.audio_gate_test", "Audio gate test"),
                self._tr(
                    "msg.audio_gate_test_disabled",
                    "audio.enabled is false.\nRun the test with the current value?",
                ),
            )
            if not proceed:
                return

        try:
            gate_config = AudioGateConfig.from_dict(audio_cfg.get("gate") or {})
        except Exception as exc:
            messagebox.showerror(
                self._tr("title.audio_gate_test_error", "Audio gate test error"),
                self._tr("msg.audio_gate_test_invalid_config", "Invalid gate config: {error}").format(error=exc),
            )
            return

        sample_rate = int(audio_cfg.get("sampleRate", 48000))
        frame_ms = int(audio_cfg.get("frameMs", 20))
        frame_samples = max(1, int(sample_rate * frame_ms / 1000))
        channels = max(1, int(audio_cfg.get("channels", 1)))
        input_device_requested = audio_cfg.get("inputDevice")
        if (
            not isinstance(input_device_requested, str)
            or not input_device_requested.strip()
            or input_device_requested.strip().lower() == "default"
        ):
            input_device_requested = _audio_default_input_device()
        input_device = _coerce_audio_input_device_for_sounddevice(input_device_requested)
        gate = NoiseGate(gate_config, frame_ms=frame_ms)

        if sd is None:
            messagebox.showerror(
                self._tr("title.audio_gate_test_error", "Audio gate test error"),
                self._tr(
                    "msg.audio_gate_test_sounddevice_missing",
                    "sounddevice module is missing. Run ./bin/avc setup and try again.",
                ),
            )
            return

        window = tk.Toplevel(self.root)
        window.title(self._tr("title.audio_gate_test", "Audio gate test"))
        window.geometry("640x480")
        window.minsize(640, 480)
        window.resizable(True, True)
        window.grab_set()

        content = ttk.Frame(window, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)

        title = ttk.Label(content, text=self._tr("title.audio_gate_test", "Audio gate test"), font=("Arial", 12, "bold"))
        title.grid(row=0, column=0, sticky="ew", padx=(0, 0), pady=(0, 8))

        runtime_suffix = ""
        if input_device != input_device_requested:
            runtime_suffix = self._tr("audio_gate_test.runtime_suffix", " (runtime: {runtime})").format(runtime=input_device)
        info_text = self._tr(
            "audio_gate_test.info",
            "Sample rate: {sample_rate}Hz / Frame: {frame_ms}ms / Channels: {channels} / Input: {input_device}",
        ).format(sample_rate=sample_rate, frame_ms=frame_ms, channels=channels, input_device=input_device_requested)

        info = ttk.Label(
            content,
            text=info_text + runtime_suffix,
        )
        info.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        state_var = tk.StringVar(value="-")
        level_var = tk.StringVar(value="- dB")
        ratio_var = tk.StringVar(value="-")
        threshold_var = tk.StringVar(value="-")
        gate_var = tk.StringVar(value="-")
        match_var = tk.StringVar(value="-")
        pass_var = tk.StringVar(value="-")
        stream_state_var = tk.StringVar(value="-")
        stream_open_count_var = tk.StringVar(value="0")
        stream_close_count_var = tk.StringVar(value="0")
        summary_var = tk.StringVar(value=self._tr("audio_gate_test.status_ready", "Ready to start."))
        runtime_var = tk.StringVar(value=self._tr("audio_gate_test.runtime", "Runtime: {seconds:.1f}s").format(seconds=0.0))
        row_index = 2
        for text, variable in [
            (self._tr("audio_gate_test.label_state", "Current gate state"), state_var),
            (self._tr("audio_gate_test.label_input_level", "Input level"), level_var),
            (self._tr("audio_gate_test.label_band_ratio", "Band ratio"), ratio_var),
            (self._tr("audio_gate_test.label_threshold", "Threshold pass"), threshold_var),
            (self._tr("audio_gate_test.label_match", "Band ratio pass"), match_var),
            (self._tr("audio_gate_test.label_gate", "Gate pass"), gate_var),
            (self._tr("audio_gate_test.label_pass", "PASS"), pass_var),
            (self._tr("audio_gate_test.label_stream_state", "Stream state"), stream_state_var),
            (self._tr("audio_gate_test.label_stream_open_count", "Stream open count"), stream_open_count_var),
            (self._tr("audio_gate_test.label_stream_close_count", "Stream close count"), stream_close_count_var),
        ]:
            row = ttk.Frame(content)
            row.grid(row=row_index, column=0, sticky="ew", pady=2)
            row.columnconfigure(0, weight=1)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=f"{text}").grid(row=0, column=0, sticky="w")
            ttk.Label(row, textvariable=variable).grid(row=0, column=1, sticky="e")
            row_index += 1

        level_bar = ttk.Progressbar(content, maximum=100)
        level_bar.grid(row=row_index, column=0, sticky="ew", pady=(8, 2))
        row_index += 1
        ratio_bar = ttk.Progressbar(content, maximum=100)
        ratio_bar.grid(row=row_index, column=0, sticky="ew", pady=(2, 8))
        row_index += 1

        runtime_label = ttk.Label(content, textvariable=runtime_var)
        runtime_label.grid(row=row_index, column=0, sticky="w")
        row_index += 1
        summary_label = ttk.Label(content, textvariable=summary_var)
        summary_label.grid(row=row_index, column=0, sticky="w", pady=(0, 10))
        row_index += 1

        control = ttk.Frame(content)
        control.grid(row=row_index, column=0, sticky="ew")
        stop_btn = ttk.Button(control, text=self._tr("button.stop", "Stop"))
        stop_btn.pack(anchor="e")

        self._audio_gate_test_running = True
        self._audio_gate_test_error = None
        self._audio_gate_test_queue = deque(maxlen=120)
        self._audio_gate_test_window = window
        self._audio_gate_test_gate = gate
        self._audio_gate_test_threshold_db = gate_config.thresholdDb
        self._audio_gate_test_min_ratio = gate_config.minVoiceBandRatio
        self._audio_gate_test_sample_count = 0
        self._audio_gate_test_pass_count = 0
        self._audio_gate_test_match_count = 0
        self._audio_gate_test_stream_pass_count = 0
        self._audio_gate_test_stream_open_count = 0
        self._audio_gate_test_stream_close_count = 0
        self._audio_gate_test_prev_stream_open = False
        self._audio_gate_test_started_at = time.time()

        def close_window():
            self._stop_audio_gate_test()
            if window.winfo_exists():
                window.destroy()

        stop_btn.configure(command=close_window)
        window.protocol("WM_DELETE_WINDOW", close_window)

        try:
            stream = sd.InputStream(
                device=input_device,
                channels=channels,
                samplerate=sample_rate,
                blocksize=frame_samples,
                dtype="float32",
                callback=self._audio_gate_test_callback,
            )
            self._audio_gate_test_stream = stream
            stream.start()
        except Exception as exc:
            self._stop_audio_gate_test()
            window.destroy()
            messagebox.showerror(
                self._tr("title.audio_gate_test_error", "Audio gate test error"),
                self._tr("msg.audio_gate_test_open_stream_failed", "Failed to open input stream: {error}").format(error=exc),
            )
            return

        def refresh() -> None:
            if not self._audio_gate_test_running or not self._audio_gate_test_window:
                return
            if not self._audio_gate_test_window.winfo_exists():
                self._stop_audio_gate_test()
                return

            if self._audio_gate_test_error is not None:
                summary_var.set(f"{self._tr('msg.error_prefix', 'Error')}: {self._audio_gate_test_error}")
                stop_btn.state(["disabled"])
                self._stop_audio_gate_test()
                return

            latest = None
            with self._audio_gate_test_lock:
                while self._audio_gate_test_queue:
                    latest = self._audio_gate_test_queue.popleft()
            if latest is not None:
                level_db, ratio, gate_state, gain, stream_open = latest
                state_text = gate_state.upper()
                level_var.set(f"{level_db:.1f} dB")
                ratio_var.set(f"{ratio:.2f}")

                passes_db = level_db >= self._audio_gate_test_threshold_db
                matches_band = ratio >= self._audio_gate_test_min_ratio
                passes_gate = gate_state in {"open", "hold"}
                pass_text = self._tr("audio_gate_test.pass", "PASS")
                block_text = self._tr("audio_gate_test.block", "BLOCK")
                open_text = self._tr("audio_gate_test.stream_open", "Open")
                close_text = self._tr("audio_gate_test.stream_closed", "Closed")

                threshold_var.set(pass_text if passes_db else block_text)
                match_var.set(pass_text if matches_band else block_text)
                gate_var.set(pass_text if passes_gate else block_text)
                pass_var.set(pass_text if (passes_db and matches_band and passes_gate) else block_text)
                state_var.set(f"{state_text} (gain={gain:.2f})")
                stream_state_var.set(open_text if stream_open else close_text)
                stream_open_count_var.set(f"{self._audio_gate_test_stream_open_count}")
                stream_close_count_var.set(f"{self._audio_gate_test_stream_close_count}")

                level_norm = max(0.0, min(100.0, (level_db - (-80.0)) / 80.0 * 100.0))
                ratio_norm = max(0.0, min(100.0, ratio * 100.0))
                level_bar["value"] = level_norm
                ratio_bar["value"] = ratio_norm

                if self._audio_gate_test_sample_count > 0:
                    pass_ratio = self._audio_gate_test_pass_count / float(self._audio_gate_test_sample_count) * 100.0
                    match_ratio = self._audio_gate_test_match_count / float(self._audio_gate_test_sample_count) * 100.0
                    stream_ratio = self._audio_gate_test_stream_pass_count / float(self._audio_gate_test_sample_count) * 100.0
                    summary = (
                        self._tr(
                            "audio_gate_test.summary",
                            "Realtime pass ratio: gate {pass_ratio:.1f}% / "
                            "band {match_ratio:.1f}% / "
                            "PASS stream {stream_ratio:.1f}%",
                        ).format(
                            pass_ratio=pass_ratio,
                            match_ratio=match_ratio,
                            stream_ratio=stream_ratio,
                        )
                    )
                    summary_var.set(summary)

            elapsed = time.time() - self._audio_gate_test_started_at
            runtime_var.set(self._tr("audio_gate_test.runtime", "Runtime: {seconds:.1f}s").format(seconds=elapsed))
            self._audio_gate_test_after_id = self.root.after(80, refresh)

        self._audio_gate_test_after_id = self.root.after(80, refresh)

    def _audio_gate_test_callback(self, indata, frames, time_info, status):
        if not self._audio_gate_test_running or self._audio_gate_test_gate is None:
            return
        try:
            mono = np.mean(np.asarray(indata, dtype=np.float32), axis=1)
            level_db = self._rms_dbfs(mono)
            ratio = self._voice_band_ratio(mono, int(self.vars["audio_sample_rate"].get()))
            result = self._audio_gate_test_gate.step(input_level_db=level_db, voice_band_ratio=ratio)
            state = str(result.state.value)
            stream_open = state in {"open", "hold"}
            with self._audio_gate_test_lock:
                self._audio_gate_test_queue.append((level_db, ratio, state, result.gain, stream_open))
                self._audio_gate_test_sample_count += 1
                if state in {"open", "hold"}:
                    self._audio_gate_test_pass_count += 1
                if ratio >= self._audio_gate_test_min_ratio:
                    self._audio_gate_test_match_count += 1
                if stream_open and level_db >= self._audio_gate_test_threshold_db and ratio >= self._audio_gate_test_min_ratio:
                    self._audio_gate_test_stream_pass_count += 1
                if stream_open != self._audio_gate_test_prev_stream_open:
                    if stream_open:
                        self._audio_gate_test_stream_open_count += 1
                    else:
                        self._audio_gate_test_stream_close_count += 1
                    self._audio_gate_test_prev_stream_open = stream_open
        except Exception as exc:
            self._audio_gate_test_error = str(exc)

    def _stop_audio_gate_test(self) -> None:
        self._audio_gate_test_running = False
        after_id = self._audio_gate_test_after_id
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._audio_gate_test_after_id = None

        stream = self._audio_gate_test_stream
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        self._audio_gate_test_stream = None
        self._audio_gate_test_gate = None
        self._audio_gate_test_window = None

    def _run_audio_input_meter(self):
        try:
            config = self._build_config()
        except Exception as exc:
            messagebox.showerror(self._tr("title.audio_input_meter_error", "Input dB meter error"), str(exc))
            return

        audio_cfg = config.get("audio") or {}
        sample_rate = int(audio_cfg.get("sampleRate", 48000))
        frame_ms = int(audio_cfg.get("frameMs", 20))
        frame_samples = max(1, int(sample_rate * frame_ms / 1000))
        channels = max(1, int(audio_cfg.get("channels", 1)))
        input_device_requested = audio_cfg.get("inputDevice")
        if not isinstance(input_device_requested, str) or not input_device_requested.strip():
            input_device_requested = _audio_default_input_device()
        input_device = _coerce_audio_input_device_for_sounddevice(input_device_requested)

        if sd is None:
            messagebox.showerror(
                self._tr("title.audio_input_meter_error", "Input dB meter error"),
                self._tr(
                    "msg.audio_input_meter_sounddevice_missing",
                    "sounddevice module is missing. Run ./bin/avc setup and try again.",
                ),
            )
            return

        window = tk.Toplevel(self.root)
        window.title(self._tr("title.audio_input_meter", "Microphone input dB meter"))
        window.geometry("640x480")
        window.minsize(640, 480)
        window.resizable(True, True)
        window.grab_set()

        content = ttk.Frame(window, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)

        ttk.Label(content, text=self._tr("title.audio_input_meter", "Microphone input dB meter"), font=("Arial", 12, "bold")).grid(
            row=0, column=0, sticky="ew", pady=(0, 8)
        )
        ttk.Label(
            content,
            text=(
                self._tr("audio_input_meter.info", "Input: {input_device} / Sample rate: {sample_rate}Hz / Frame: {frame_ms}ms / Channels: {channels}")
                .format(
                    input_device=input_device_requested,
                    sample_rate=sample_rate,
                    frame_ms=frame_ms,
                    channels=channels,
                )
                + (self._tr("audio_input_meter.runtime_suffix", " (runtime: {runtime})").format(runtime=input_device) if input_device != input_device_requested else "")
            ),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        level_var = tk.StringVar(value="- dB")
        runtime_var = tk.StringVar(value=self._tr("audio_input_meter.runtime", "Runtime: {seconds:.1f}s").format(seconds=0.0))
        summary_var = tk.StringVar(value=self._tr("audio_input_meter.status_ready", "Ready to start."))

        row = ttk.Frame(content)
        row.grid(row=2, column=0, sticky="ew", pady=2)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=self._tr("audio_input_meter.label_input_level", "Input level")).grid(row=0, column=0, sticky="w")
        ttk.Label(row, textvariable=level_var).grid(row=0, column=1, sticky="e")

        level_bar = ttk.Progressbar(content, maximum=100)
        level_bar.grid(row=3, column=0, sticky="ew", pady=(8, 8))
        ttk.Label(content, textvariable=runtime_var).grid(row=4, column=0, sticky="w")
        ttk.Label(content, textvariable=summary_var).grid(row=5, column=0, sticky="w", pady=(0, 10))

        control = ttk.Frame(content)
        control.grid(row=6, column=0, sticky="ew")
        stop_btn = ttk.Button(control, text=self._tr("button.stop", "Stop"))
        stop_btn.pack(anchor="e")

        self._audio_input_meter_running = True
        self._audio_input_meter_error = None
        self._audio_input_meter_queue = deque(maxlen=120)
        self._audio_input_meter_window = window
        self._audio_input_meter_started_at = time.time()

        def close_window():
            self._stop_audio_input_meter()
            if window.winfo_exists():
                window.destroy()

        stop_btn.configure(command=close_window)
        window.protocol("WM_DELETE_WINDOW", close_window)

        try:
            stream = sd.InputStream(
                device=input_device,
                channels=channels,
                samplerate=sample_rate,
                blocksize=frame_samples,
                dtype="float32",
                callback=self._audio_input_meter_callback,
            )
            self._audio_input_meter_stream = stream
            stream.start()
        except Exception as exc:
            available = []
            try:
                available = [
                    str(d.get("name", "")).strip()
                    for d in sd.query_devices()
                    if int(d.get("max_input_channels", 0)) > 0 and str(d.get("name", "")).strip()
                ]
            except Exception:
                available = []
            self._stop_audio_input_meter()
            window.destroy()
            messagebox.showerror(
                self._tr("title.audio_input_meter_error", "Input dB meter error"),
                self._tr(
                    "msg.audio_input_meter_open_stream_failed",
                    "Failed to open input stream: {error}\nconfigured={configured}\nruntime={runtime}\navailable={available}",
                ).format(
                    error=exc,
                    configured=input_device_requested,
                    runtime=input_device,
                    available=available if available else ["<none>"],
                ),
            )
            return

        def refresh() -> None:
            if not self._audio_input_meter_running or not self._audio_input_meter_window:
                return
            if not self._audio_input_meter_window.winfo_exists():
                self._stop_audio_input_meter()
                return
            if self._audio_input_meter_error is not None:
                summary_var.set(f"{self._tr('msg.error_prefix', 'Error')}: {self._audio_input_meter_error}")
                stop_btn.state(["disabled"])
                self._stop_audio_input_meter()
                return

            latest = None
            with self._audio_input_meter_lock:
                while self._audio_input_meter_queue:
                    latest = self._audio_input_meter_queue.popleft()
            if latest is not None:
                level_db = latest
                level_var.set(f"{level_db:.1f} dB")
                level_norm = max(0.0, min(100.0, (level_db - (-80.0)) / 80.0 * 100.0))
                level_bar["value"] = level_norm
                summary_var.set(self._tr("audio_input_meter.measuring", "Measuring input signal"))

            elapsed = time.time() - self._audio_input_meter_started_at
            runtime_var.set(self._tr("audio_input_meter.runtime", "Runtime: {seconds:.1f}s").format(seconds=elapsed))
            self._audio_input_meter_after_id = self.root.after(80, refresh)

        self._audio_input_meter_after_id = self.root.after(80, refresh)

    def _audio_input_meter_callback(self, indata, frames, time_info, status):
        if not self._audio_input_meter_running:
            return
        try:
            mono = np.mean(np.asarray(indata, dtype=np.float32), axis=1)
            level_db = self._rms_dbfs(mono)
            with self._audio_input_meter_lock:
                self._audio_input_meter_queue.append(level_db)
        except Exception as exc:
            self._audio_input_meter_error = str(exc)

    def _stop_audio_input_meter(self) -> None:
        self._audio_input_meter_running = False
        after_id = self._audio_input_meter_after_id
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._audio_input_meter_after_id = None

        stream = self._audio_input_meter_stream
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        self._audio_input_meter_stream = None
        self._audio_input_meter_window = None

    def _build_test_waveform(self, kind: str, sample_rate: int, seconds: float):
        frames = max(1, int(sample_rate * seconds))
        t = np.arange(frames, dtype=np.float32) / float(sample_rate)
        if kind == "speech":
            return 0.25 * (np.sin(2 * np.pi * 800.0 * t).astype(np.float32))
        if kind == "non_voice":
            return 0.20 * (np.sin(2 * np.pi * 140.0 * t).astype(np.float32))
        return np.zeros(frames, dtype=np.float32)

    def _record_audio_block(self, seconds: float, sample_rate: int, channels: int, show_error: bool = True):
        try:
            frames = max(1, int(seconds * sample_rate))
            data = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
            sd.wait()
        except Exception as exc:
            if show_error:
                messagebox.showerror(
                    self._tr("title.audio_tune_error", "Audio tuning error"),
                    self._tr("msg.audio_tune_capture_failed", "Microphone capture failed:\n{error}").format(error=exc),
                )
            return None
        if data is None or len(data) == 0:
            if show_error:
                messagebox.showerror(
                    self._tr("title.audio_tune_error", "Audio tuning error"),
                    self._tr("msg.audio_tune_capture_empty", "No audio data was captured."),
                )
            return None
        mono = np.mean(np.asarray(data, dtype=np.float32), axis=1)
        return mono

    def _rms_dbfs(self, mono: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
        return float(20.0 * np.log10(max(rms, 1e-9)))

    def _voice_band_ratio(self, mono: np.ndarray, sample_rate: int) -> float:
        if mono.size < 32:
            return 0.0
        window = np.hanning(mono.size).astype(np.float32)
        spec = np.fft.rfft((mono * window).astype(np.float32))
        power = np.abs(spec) ** 2
        freqs = np.fft.rfftfreq(mono.size, d=1.0 / float(sample_rate))
        total_band = (freqs >= 80.0) & (freqs <= 8000.0)
        voice_band = (freqs >= 300.0) & (freqs <= 3400.0)
        total_power = float(np.sum(power[total_band]))
        if total_power <= 1e-12:
            return 0.0
        voice_power = float(np.sum(power[voice_band]))
        return float(max(0.0, min(1.0, voice_power / total_power)))

    def _preview(self):
        now = time.monotonic()
        # Prevent duplicate callbacks (double-click / key repeat) from reopening preview repeatedly.
        if now - self._preview_last_toggle_at < 0.6:
            return
        self._preview_last_toggle_at = now
        if self._preview_starting:
            return
        if self._preview_active:
            self._stop_preview()
            return
        if self._is_serve_running():
            self._report_preview_error(self._tr("msg.preview_serve_running", "Cannot start camera preview while Serve is running."))
            return
        try:
            self._preview_starting = True
            config = self._build_config(validate_audio=False)
            self._start_preview(config)
        except Exception as exc:
            self._report_preview_error(str(exc))
        finally:
            self._preview_starting = False

    def _check_preview_runtime_ready(self) -> None:
        if self._preview_qt_check_done:
            return
        display = str(os.environ.get("DISPLAY", "")).strip()
        if not display:
            raise RuntimeError(self._tr("msg.preview_display_missing", "DISPLAY is empty. Please run in X11 environment."))

        plugin_path = Path(cv2.__file__).resolve().parent / "qt" / "plugins" / "platforms" / "libqxcb.so"
        if not plugin_path.exists():
            self._preview_qt_check_done = True
            return

        try:
            proc = _run_cmd(["ldd", str(plugin_path)], check=False, timeout=2.0)
        except Exception as exc:
            raise RuntimeError(self._tr("msg.preview_dependency_check_failed", "Qt xcb dependency check failed: {error}").format(error=exc)) from exc
        missing = []
        for line in (proc.stdout or "").splitlines():
            if "=> not found" not in line:
                continue
            missing.append(line.strip().split("=>", 1)[0].strip())
        if missing:
            unique_missing = list(dict.fromkeys(missing))
            missing_text = ", ".join(unique_missing)
            raise RuntimeError(
                self._tr("msg.preview_qt_missing", "Qt xcb plugin dependencies are missing. Missing libraries: {libraries}")
                .format(libraries=missing_text)
            )
        self._preview_qt_check_done = True

    def _start_preview(self, config: dict) -> None:
        from src.adapter.capture.opencv_capture import OpenCVCapture
        from src.domain.config import BackgroundConfig, FaceEnhanceConfig, InputCameraConfig, PersonCropConfig, SegmentationConfig
        from src.pipeline.frame_processor import FrameProcessor

        input_cfg = InputCameraConfig.from_dict(config["inputCamera"])
        seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
        bg_cfg = BackgroundConfig.from_dict(config["background"])
        crop_cfg = PersonCropConfig.from_dict(config["crop"])
        face_cfg = FaceEnhanceConfig.from_dict(config.get("faceEnhance") or {})
        output_w = int(config["outputCamera"]["width"])
        output_h = int(config["outputCamera"]["height"])

        self._preview_capture = OpenCVCapture(input_cfg)
        self._preview_processor = FrameProcessor(seg_cfg, bg_cfg, crop_cfg, face_cfg, output_w, output_h)
        self._preview_out_size = (output_w, output_h)
        self._preview_processing_signature = self._processing_signature(config)
        self._ensure_preview_window()
        self._preview_active = True
        self._sync_action_button_states()
        self.root.after(15, self._preview_tick)

    def _stop_preview(self) -> None:
        self._preview_active = False
        self._preview_last_toggle_at = time.monotonic()
        if self._preview_capture is not None:
            self._preview_capture.release()
        self._preview_capture = None
        self._preview_processor = None
        self._preview_processing_signature = None
        self._destroy_preview_window()
        self._sync_action_button_states()

    def _ensure_preview_window(self) -> None:
        if self._preview_window is not None and self._preview_window.winfo_exists():
            return
        window = tk.Toplevel(self.root)
        window.title(self._preview_window_name)
        window.geometry("640x400")
        window.protocol("WM_DELETE_WINDOW", self._stop_preview)
        canvas = tk.Canvas(window, bg="#111111", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        self._preview_window = window
        self._preview_canvas = canvas
        self._preview_canvas_image_id = None
        self._preview_tk_image = None

    def _destroy_preview_window(self) -> None:
        window = self._preview_window
        self._preview_window = None
        self._preview_canvas = None
        self._preview_canvas_image_id = None
        self._preview_tk_image = None
        if window is None:
            return
        try:
            if window.winfo_exists():
                window.destroy()
        except Exception:
            pass

    def _render_preview_to_tk(self, frame_bgr: np.ndarray) -> None:
        if self._preview_canvas is None:
            return
        display_frame = self._fit_preview_frame(frame_bgr)
        # Draw diagnostic traces at the final display resolution for crisp visibility.
        display_frame = self._apply_segment_trace_overlay(display_frame)
        display_frame = self._apply_face_edge_trace_overlay(display_frame)
        display_frame = self._apply_deidentify_trace_overlay(display_frame)
        ok, encoded = cv2.imencode(".ppm", display_frame)
        if not ok:
            raise RuntimeError("Failed to encode preview frame")
        image = tk.PhotoImage(data=encoded.tobytes(), format="PPM")
        self._preview_tk_image = image
        canvas_w = max(1, int(self._preview_canvas.winfo_width()))
        canvas_h = max(1, int(self._preview_canvas.winfo_height()))
        img_h, img_w = display_frame.shape[:2]
        x = max(0, (canvas_w - img_w) // 2)
        y = max(0, (canvas_h - img_h) // 2)
        if self._preview_canvas_image_id is None:
            self._preview_canvas_image_id = self._preview_canvas.create_image(
                x, y, image=image, anchor="nw"
            )
        else:
            self._preview_canvas.coords(self._preview_canvas_image_id, x, y)
            self._preview_canvas.itemconfigure(self._preview_canvas_image_id, image=image)

    def _fit_preview_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        if h <= 0 or w <= 0:
            return frame_bgr
        max_w = 960
        max_h = 540
        if self._preview_window is not None and self._preview_window.winfo_exists():
            win_w = max(1, int(self._preview_window.winfo_width()))
            win_h = max(1, int(self._preview_window.winfo_height()))
            max_w = max(160, win_w - 24)
            max_h = max(120, win_h - 56)
        scale = min(float(max_w) / float(w), float(max_h) / float(h))
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        interpolation = cv2.INTER_LINEAR if scale >= 1.0 else cv2.INTER_AREA
        return cv2.resize(frame_bgr, (new_w, new_h), interpolation=interpolation)

    def _preview_tick(self) -> None:
        if not self._preview_active:
            return
        from src.domain.config import BackgroundConfig, FaceEnhanceConfig, PersonCropConfig, SegmentationConfig
        from src.pipeline.frame_processor import FrameProcessor

        try:
            frame = self._preview_capture.read()
            config = self._build_config(validate_audio=False)
            sig = self._processing_signature(config)
            out_w = int(config["outputCamera"]["width"])
            out_h = int(config["outputCamera"]["height"])
            self._preview_out_size = (out_w, out_h)

            if sig != self._preview_processing_signature or self._preview_processor is None:
                bg_cfg = BackgroundConfig.from_dict(config["background"])
                seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
                crop_cfg = PersonCropConfig.from_dict(config["crop"])
                face_cfg = FaceEnhanceConfig.from_dict(config.get("faceEnhance") or {})
                self._preview_processor = FrameProcessor(seg_cfg, bg_cfg, crop_cfg, face_cfg, out_w, out_h)
                self._preview_processing_signature = sig

            output_frame = self._preview_processor.process(frame)
            if self._preview_window is None or not self._preview_window.winfo_exists():
                self._stop_preview()
                return
            self._render_preview_to_tk(output_frame)
        except Exception as exc:
            self._stop_preview()
            _log(f"Preview exception traceback:\n{traceback.format_exc()}")
            self._report_preview_error(str(exc))
            return

        self.root.after(15, self._preview_tick)

    def _apply_face_edge_trace_overlay(self, frame_bgr: np.ndarray) -> np.ndarray:
        if not self._preview_face_edge_trace_enabled or self._preview_processor is None:
            return frame_bgr
        getter = getattr(self._preview_processor, "last_face_enhance_edge_mask", None)
        if getter is None:
            return frame_bgr
        mask = getter()
        if not isinstance(mask, np.ndarray) or mask.size == 0:
            return frame_bgr
        if mask.shape[:2] != frame_bgr.shape[:2]:
            mask = cv2.resize(mask, (frame_bgr.shape[1], frame_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
        binary = (mask >= 127).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return frame_bgr
        overlay = frame_bgr.copy()
        cv2.drawContours(overlay, contours, -1, (64, 255, 128), 2)
        return overlay

    def _apply_segment_trace_overlay(self, frame_bgr: np.ndarray) -> np.ndarray:
        if not self._preview_segment_trace_enabled or self._preview_processor is None:
            return frame_bgr
        getter = getattr(self._preview_processor, "last_output_mask", None)
        if getter is None:
            return frame_bgr
        mask = getter()
        if not isinstance(mask, np.ndarray) or mask.size == 0:
            return frame_bgr
        if mask.shape[:2] != frame_bgr.shape[:2]:
            mask = cv2.resize(mask, (frame_bgr.shape[1], frame_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
        binary = (mask >= 127).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return frame_bgr
        overlay = frame_bgr.copy()
        cv2.drawContours(overlay, contours, -1, (255, 180, 32), 2)
        return overlay

    def _apply_deidentify_trace_overlay(self, frame_bgr: np.ndarray) -> np.ndarray:
        if not self._preview_deidentify_trace_enabled or self._preview_processor is None:
            return frame_bgr
        getter = getattr(self._preview_processor, "last_deidentify_mask", None)
        if getter is None:
            return frame_bgr
        mask = getter()
        if not isinstance(mask, np.ndarray) or mask.size == 0:
            return frame_bgr
        if mask.shape[:2] != frame_bgr.shape[:2]:
            mask = cv2.resize(mask, (frame_bgr.shape[1], frame_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
        binary = (mask >= 127).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return frame_bgr
        overlay = frame_bgr.copy()
        cv2.drawContours(overlay, contours, -1, (255, 64, 220), 2)
        return overlay

    def _report_preview_error(self, message: str) -> None:
        _log(f"Preview error: {message}")
        messagebox.showerror(self._tr("title.preview_error", "Preview error"), message)

    def _background_signature(self, background: dict):
        return (
            background.get("mode"),
            tuple(background.get("chromaColor") or []),
            background.get("imagePath"),
            tuple((background.get("crop") or {}).values()) if background.get("crop") else None,
            background.get("colorBlendAlpha"),
        )

    def _crop_signature(self, crop: dict):
        return (
            crop.get("margin"),
            crop.get("panSmoothing", crop.get("smoothing")),
            crop.get("tiltSmoothing"),
            crop.get("zoomSmoothing"),
            crop.get("upperBodyBias"),
            crop.get("upperBodyRatio"),
            crop.get("upperBodyEdgeSmoothing"),
            crop.get("zoom"),
            crop.get("panPidKp"),
            crop.get("panPidKi"),
            crop.get("panPidKd"),
            crop.get("tiltPidKp"),
            crop.get("tiltPidKi"),
            crop.get("tiltPidKd"),
            crop.get("panTargetOffsetX"),
            crop.get("panTargetOffsetY"),
        )

    def _processing_signature(self, config: dict):
        seg = config["segmentation"]
        selfie = seg.get("selfie") or {}
        engine_options = (seg.get("engineOptions") or {}).get(seg.get("backend"), {})
        face = config.get("faceEnhance") or {}
        return (
            seg.get("backend"),
            seg.get("threshold"),
            seg.get("edgeSmoothness"),
            seg.get("blendFeather"),
            selfie.get("modelSelection"),
            selfie.get("temporalSmoothing"),
            tuple(sorted((engine_options or {}).items())),
            face.get("enabled"),
            face.get("gamma"),
            face.get("offset"),
            face.get("saturation"),
            face.get("strength"),
            face.get("minRegionRatio"),
            face.get("edgeNoise"),
            (face.get("deidentify") or {}).get("enabled"),
            self._background_signature(config["background"]),
            self._crop_signature(config["crop"]),
            int(config["outputCamera"]["width"]),
            int(config["outputCamera"]["height"]),
        )

    def _on_seg_backend_changed(self, _event=None) -> None:
        backend = self.vars["seg_backend"].get().strip()
        allowed = set(SEG_ENGINE_OPTION_FIELDS.get(backend, ()))
        key_map = {
            "seg_opt_model_blend": "modelBlend",
            "seg_opt_temporal_alpha": "temporalAlpha",
            "seg_opt_mask_blur": "maskBlur",
            "seg_opt_morph_open": "morphOpen",
            "seg_opt_morph_close": "morphClose",
            "seg_opt_mask_gamma": "maskGamma",
        }
        for var_key, opt_key in key_map.items():
            widget = self._widgets.get(var_key)
            enabled = opt_key in allowed
            if widget is None:
                continue
            if enabled:
                widget.state(["!disabled"])
            else:
                widget.state(["disabled"])

    def _collect_seg_engine_options_from_form(self) -> dict[str, object]:
        backend = self.vars["seg_backend"].get().strip()
        allowed = set(SEG_ENGINE_OPTION_FIELDS.get(backend, ()))
        options: dict[str, object] = {}
        if "modelBlend" in allowed:
            options["modelBlend"] = float(self.vars["seg_opt_model_blend"].get())
        if "temporalAlpha" in allowed:
            options["temporalAlpha"] = float(self.vars["seg_opt_temporal_alpha"].get())
        if "maskBlur" in allowed:
            options["maskBlur"] = int(round(float(self.vars["seg_opt_mask_blur"].get())))
        if "morphOpen" in allowed:
            options["morphOpen"] = int(round(float(self.vars["seg_opt_morph_open"].get())))
        if "morphClose" in allowed:
            options["morphClose"] = int(round(float(self.vars["seg_opt_morph_close"].get())))
        if "maskGamma" in allowed:
            options["maskGamma"] = float(self.vars["seg_opt_mask_gamma"].get())
        return options

    def _apply_seg_engine_options_to_form(self, options: dict[str, object]) -> None:
        mapping = (
            ("seg_opt_model_blend", "modelBlend"),
            ("seg_opt_temporal_alpha", "temporalAlpha"),
            ("seg_opt_mask_blur", "maskBlur"),
            ("seg_opt_morph_open", "morphOpen"),
            ("seg_opt_morph_close", "morphClose"),
            ("seg_opt_mask_gamma", "maskGamma"),
        )
        for var_key, opt_key in mapping:
            value = options.get(opt_key)
            if value is None:
                continue
            self._set_var(var_key, value)
        self._on_seg_backend_changed()

    def _build_config(self, *, validate_audio: bool = True):
        iv = self.vars
        input_w = int(iv["input_width"].get())
        input_h = int(iv["input_height"].get())
        output_w = int(iv["output_width"].get())
        output_h = int(iv["output_height"].get())

        background = {"mode": iv["bg_mode"].get()}
        if background["mode"] in {"chroma", "image_chroma"}:
            background["chromaColor"] = [int(iv["bg_r"].get()), int(iv["bg_g"].get()), int(iv["bg_b"].get())]
        if background["mode"] in {"image", "image_chroma"}:
            image_path = iv["bg_image"].get().strip()
            if not image_path:
                raise ValueError("Background mode=image/image_chroma requires image path")
            background["imagePath"] = image_path
            background["crop"] = {"x": 0, "y": 0, "width": output_w, "height": output_h}
        if background["mode"] == "image_chroma":
            background["colorBlendAlpha"] = float(iv["bg_blend_alpha"].get())

        raw_audio_input = _audio_device_raw_from_display(
            iv["audio_input_device"].get().strip(),
            getattr(self, "_audio_input_display_to_raw", {}),
        )
        raw_audio_output = _audio_device_raw_from_display(
            iv["audio_output_device"].get().strip(),
            getattr(self, "_audio_output_display_to_raw", {}),
        )
        if validate_audio:
            _validate_pulse_runtime_device("input", raw_audio_input)
            _validate_pulse_runtime_device("output", raw_audio_output)
        seg_engine_options = self._collect_seg_engine_options_from_form()

        return build_config(
            input_device=iv["input_device"].get(),
            input_width=input_w,
            input_height=input_h,
            input_fps=int(iv["input_fps"].get()),
            output_device=iv["output_device"].get(),
            output_width=output_w,
            output_height=output_h,
            output_fps=int(iv["output_fps"].get()),
            output_backend=iv["output_backend"].get(),
            segmentation_backend=iv["seg_backend"].get(),
            segmentation_threshold=float(iv["seg_threshold"].get()),
            segmentation_edge_smoothness=float(iv["seg_edge_smoothness"].get()),
            segmentation_blend_feather=float(iv["seg_blend_feather"].get()),
            segmentation_selfie_model_selection=int(round(float(iv["seg_selfie_model"].get()))),
            segmentation_selfie_temporal_smoothing=float(iv["seg_selfie_smoothing"].get()),
            segmentation_engine_options=seg_engine_options,
            background=background,
            crop_margin=float(iv["crop_margin"].get()),
            crop_pan_smoothing=float(iv["crop_pan_smoothing"].get()),
            crop_tilt_smoothing=float(iv["crop_tilt_smoothing"].get()),
            crop_zoom_smoothing=float(iv["crop_zoom_smoothing"].get()),
            crop_upper_body_bias=float(iv["crop_upper_body_bias"].get()),
            crop_upper_body_ratio=float(iv["crop_upper_body_ratio"].get()),
            crop_upper_body_edge_smoothing=float(iv["crop_upper_body_edge_smoothing"].get()),
            input_software_zoom=float(iv["input_software_zoom"].get()),
            crop_pan_pid_kp=float(iv["crop_pan_pid_kp"].get()),
            crop_pan_pid_ki=float(iv["crop_pan_pid_ki"].get()),
            crop_pan_pid_kd=float(iv["crop_pan_pid_kd"].get()),
            crop_tilt_pid_kp=float(iv["crop_tilt_pid_kp"].get()),
            crop_tilt_pid_ki=float(iv["crop_tilt_pid_ki"].get()),
            crop_tilt_pid_kd=float(iv["crop_tilt_pid_kd"].get()),
            crop_pan_target_offset_x=float(iv["crop_pan_target_offset_x"].get()),
            crop_pan_target_offset_y=float(iv["crop_pan_target_offset_y"].get()),
            audio_enabled=self._parse_bool(iv["audio_enabled"].get()),
            audio_input_device=raw_audio_input,
            audio_output_device=raw_audio_output,
            audio_sample_rate=int(iv["audio_sample_rate"].get()),
            audio_channels=int(iv["audio_channels"].get()),
            audio_frame_ms=int(iv["audio_frame_ms"].get()),
            audio_denoise_enabled=self._parse_bool(iv["audio_denoise_enabled"].get()),
            audio_denoise_backend=iv["audio_denoise_backend"].get().strip(),
            audio_denoise_strength=float(iv["audio_denoise_strength"].get()),
            audio_gate_threshold_db=float(iv["audio_gate_threshold_db"].get()),
            audio_gate_hysteresis_db=float(iv["audio_gate_hysteresis_db"].get()),
            audio_gate_min_voice_band_ratio=float(iv["audio_gate_min_voice_band_ratio"].get()),
            audio_gate_attack_ms=int(round(float(iv["audio_gate_attack_ms"].get()))),
            audio_gate_hold_ms=int(round(float(iv["audio_gate_hold_ms"].get()))),
            audio_gate_release_ms=int(round(float(iv["audio_gate_release_ms"].get()))),
            audio_gate_open_gain=float(iv["audio_gate_open_gain"].get()),
            audio_gate_closed_gain=float(iv["audio_gate_closed_gain"].get()),
            face_enhance_enabled=self._parse_bool(iv["face_enhance_enabled"].get()),
            face_enhance_gamma=float(iv["face_enhance_gamma"].get()),
            face_enhance_brightness=float(iv["face_enhance_brightness"].get()),
            face_enhance_saturation=float(iv["face_enhance_saturation"].get()),
            face_enhance_blend=float(iv["face_enhance_blend"].get()),
            face_enhance_min_size_ratio=float(iv["face_enhance_min_size_ratio"].get()),
            face_enhance_edge_dither=float(iv["face_enhance_edge_dither"].get()),
            face_deidentify_enabled=self._parse_bool(iv["face_deidentify_enabled"].get()),
        )


def parse_args():
    parser = argparse.ArgumentParser(description="GUI config generator for ai-virtual-cam")
    parser.add_argument("--output", default="~/.avc/setting.json")
    parser.add_argument("--lang", choices=["ko", "en"], default="ko")
    return parser.parse_args()


def main() -> int:
    if TK_IMPORT_ERROR is not None:
        print(
            "Tkinter is not available in this Python runtime.\n"
            "To use GUI on macOS, install a Python build with Tk support.\n"
            "If GUI is unavailable, edit ~/.avc/setting.json directly.",
            file=sys.stderr,
        )
        return 2

    args = parse_args()
    root = tk.Tk()
    ConfigGui(root, args.output, args.lang)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

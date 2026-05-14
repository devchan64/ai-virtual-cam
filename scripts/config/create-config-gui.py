#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import deque
import sys
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
        return ["selfie", "mock", "onnxruntime"]
    return ["selfie", "mock", "onnxruntime", "tensorrt"]


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


def _log(msg: str) -> None:
    print(f"[avc] {msg}", flush=True)


def _run_cmd(cmd: list[str], *, check: bool = False, timeout: float | None = 1.5) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {cmd[0]}") from exc


def _run_sudo_cmd_noninteractive(
    args: list[str],
    *,
    check: bool = False,
    timeout: float | None = 4.0,
) -> subprocess.CompletedProcess:
    """Run sudo without password prompt to avoid GUI freeze on non-TTY contexts."""
    return _run_cmd(["sudo", "-n", *args], check=check, timeout=timeout)


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
        return device_name
    name = str(device_name).strip()
    if not name:
        return name
    lowered = name.lower()
    try:
        names = [
            str(d.get("name", "")).strip()
            for d in sd.query_devices()
            if int(d.get("max_input_channels", 0)) > 0
        ]
        names = [n for n in names if n]
        if not names:
            return name
        if name in names:
            return name
        if name == "default":
            if "default" in names:
                return "default"
            return names[0]
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
        return name
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
    if platform.system() != "Linux":
        print("[avc] 오디오 디바이스 후보: 플랫폼 비 Linux, 기본값 ['default'] 사용", flush=True)
        return ["default"]
    values: list[str] = ["default"]
    seen = {"default"}

    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    pactl_kind = "source" if kind == "input" else "sink"
    print(
        f"[avc] 오디오 {kind} 디바이스 채널키={channel_key}, pactl_kind={pactl_kind}",
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

    # Add PulseAudio/pipewire short device names to avoid missing monitor/source entries
    try:
        proc_list = subprocess.run(
            ["pactl", "list", "short", f"{pactl_kind}s"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        print(
            f"[avc] 오디오 {kind} pactl list short {pactl_kind}s rc={proc_list.returncode}",
            flush=True,
        )
        if proc_list.returncode == 0:
            for line in proc_list.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                if not name:
                    continue
                if name not in seen:
                    seen.add(name)
                    values.append(name)
                    print(f"[avc] 오디오 {kind} 후보(pactl): {name}", flush=True)
    except Exception:
        print(f"[avc] 오디오 {kind} pactl 조회 실패: 예외 발생", flush=True)
        pass

    if kind in {"input", "output"}:
        pactl_default = _pactl_default_audio_device(pactl_kind)
        print(f"[avc] 오디오 {kind} 기본값 후보: {pactl_default}", flush=True)
        if pactl_default != "default" and pactl_default not in seen:
            seen.add(pactl_default)
            values.append(pactl_default)
            print(f"[avc] 오디오 {kind} 기본값 후보 강제 추가: {pactl_default}", flush=True)

    if not values:
        values.append("default")
        print(f"[avc] 오디오 {kind} 후보가 비어 fallback 'default' 추가", flush=True)
    print(f"[avc] 오디오 {kind} 총 후보 수: {len(values)}", flush=True)
    return values


def _audio_input_device_candidates() -> list[str]:
    return _audio_device_candidates("input")


def _audio_output_device_candidates() -> list[str]:
    return _audio_device_candidates("output")


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
    def __init__(self, root: tk.Tk, output_path: str) -> None:
        self.root = root
        self.output_path = output_path
        self.root.title("ai-virtual-cam config GUI")
        self.root.geometry("640x480")
        self.root.minsize(640, 480)
        self.root.resizable(True, True)
        self.vars: dict[str, tk.Variable] = {}
        self._preview_active = False
        self._preview_capture = None
        self._preview_processor = None
        self._preview_processing_signature = None
        self._preview_out_size = (0, 0)
        self._preview_window_name = "ai-virtual-cam preview (press q or esc to close)"
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
        self._build_form()
        self._load_existing_config()

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._scroll_canvas = tk.Canvas(frame, highlightthickness=0)
        v_scroll = ttk.Scrollbar(frame, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=v_scroll.set)
        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        scroll_inner = ttk.Frame(self._scroll_canvas, padding=0)
        self._scroll_window = self._scroll_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
        scroll_inner.bind("<Configure>", lambda event: self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all")))
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mouse_wheel)
        self._scroll_canvas.bind_all("<Button-4>", self._on_mouse_wheel_linux)
        self._scroll_canvas.bind_all("<Button-5>", self._on_mouse_wheel_linux)

        notebook = ttk.Notebook(scroll_inner)
        notebook.grid(row=0, column=0, sticky="nsew")
        scroll_inner.columnconfigure(0, weight=1)
        scroll_inner.rowconfigure(0, weight=1)

        tab_io = ttk.Frame(notebook, padding=8)
        tab_seg = ttk.Frame(notebook, padding=8)
        tab_bg = ttk.Frame(notebook, padding=8)
        tab_crop = ttk.Frame(notebook, padding=8)
        tab_audio = ttk.Frame(notebook, padding=8)
        notebook.add(tab_io, text="입출력")
        notebook.add(tab_seg, text="세그멘테이션")
        notebook.add(tab_bg, text="배경")
        notebook.add(tab_crop, text="프레이밍")
        notebook.add(tab_audio, text="오디오")
        for tab in (tab_io, tab_seg, tab_bg, tab_crop, tab_audio):
            for col in range(4):
                tab.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        is_macos = platform.system() == "Darwin"
        cameras = discover_cameras()
        camera_values = [c["devicePath"] for c in cameras] or (["0"] if is_macos else ["/dev/video0"])

        row = 0
        self._add_combo(tab_io, row, "input_device", "Input device", camera_values, camera_values[0], readonly=True)
        row += 1
        initial_modes = discover_camera_mode_options(camera_values[0]) if camera_values else [(1280, 720, "30")]
        width_values = sorted({str(w) for w, _h, _fps in initial_modes}, key=lambda v: int(v))
        default_w = width_values[0] if width_values else "1280"
        height_values = sorted({str(h) for w, h, _fps in initial_modes if str(w) == default_w}, key=lambda v: int(v))
        default_h = height_values[0] if height_values else "720"
        self._add_combo(tab_io, row, "input_width", "Input width", width_values, default_w)
        row += 1
        self._add_combo(tab_io, row, "input_height", "Input height", height_values, default_h)
        row += 1
        fps_values = sorted(
            {fps for w, h, fps in initial_modes if str(w) == default_w and str(h) == default_h},
            key=lambda v: float(v),
        ) or ["30"]
        self._add_combo(tab_io, row, "input_fps", "Input FPS", fps_values, "30")
        row += 1
        self._add_slider(tab_io, row, "input_software_zoom", "Input SW zoom", 1.0, 1.0, 4.0, resolution=0.01)
        row += 1

        self._add_combo(tab_io, row, "output_backend", "Output backend", _output_backend_options(), _output_backend_options()[0])
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
        self._add_text(tab_io, row, "output_device", "Output path", default_output_device)
        row += 1
        self._add_combo(
            tab_io,
            row,
            "output_width",
            "Output width",
            output_width_values or ["1280"],
            output_default_w,
        )
        row += 1
        self._add_combo(
            tab_io,
            row,
            "output_height",
            "Output height",
            output_height_values or ["720"],
            output_default_h,
        )
        row += 1
        self._add_combo(
            tab_io,
            row,
            "output_fps",
            "Output FPS",
            output_fps_values or ["30"],
            output_fps_values[0] if output_fps_values else "30",
        )
        row += 1
        ttk.Button(tab_io, text="가상 카메라 생성", command=self._create_virtual_camera).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        ttk.Button(tab_io, text="가상 카메라 제거", command=self._remove_virtual_camera).grid(
            row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        row += 1
        ttk.Button(tab_io, text="비디오 기본값 복원", command=self._reset_video_settings).grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        row = 0
        self._add_combo(tab_seg, row, "seg_backend", "Seg backend", _segmentation_backend_options(), "selfie")
        row += 1
        self._add_slider(tab_seg, row, "seg_threshold", "Seg threshold", 0.65, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_seg, row, "seg_edge_smoothness", "Edge smoothness", 0.50, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_seg, row, "seg_blend_feather", "Blend feather", 0.35, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_seg, row, "seg_selfie_model", "Selfie model selection", 1, 0, 1, resolution=1)
        row += 1
        self._add_slider(tab_seg, row, "seg_selfie_smoothing", "Selfie temporal smoothing", 0.25, 0.0, 0.95, resolution=0.01)

        row = 0
        self._add_combo(tab_bg, row, "bg_mode", "Background mode", ["chroma", "image", "image_chroma"], "chroma")
        row += 1
        self._add_text(tab_bg, row, "bg_image", "Background image", "")
        ttk.Button(tab_bg, text="Browse", command=self._pick_bg_image).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_int(tab_bg, row, "bg_r", "Chroma R", 0)
        self._add_int(tab_bg, row, "bg_g", "Chroma G", 0, col_offset=2)
        row += 1
        self._add_int(tab_bg, row, "bg_b", "Chroma B", 0)
        ttk.Button(tab_bg, text="Pick Color", command=self._pick_chroma_color).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_slider(tab_bg, row, "bg_blend_alpha", "Color blend alpha", 0.35, 0.0, 1.0, resolution=0.01)

        row = 0
        self._add_slider(tab_crop, row, "crop_margin", "Person crop margin", 0.25, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_pan_smoothing", "Pan smoothing", 0.85, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_tilt_smoothing", "Tilt smoothing", 0.85, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_zoom_smoothing", "Zoom smoothing", 0.80, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_upper_body_bias", "Upper body bias", 0.00, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_upper_body_ratio", "Upper body ratio", 0.60, 0.2, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_upper_body_edge_smoothing", "Upper body edge smoothing", 0.35, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_pan_pid_kp", "Pan PID Kp", 0.35, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_pan_pid_ki", "Pan PID Ki", 0.01, 0.0, 0.5, resolution=0.001)
        row += 1
        self._add_slider(tab_crop, row, "crop_pan_pid_kd", "Pan PID Kd", 0.12, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_tilt_pid_kp", "Tilt PID Kp", 0.35, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_tilt_pid_ki", "Tilt PID Ki", 0.01, 0.0, 0.5, resolution=0.001)
        row += 1
        self._add_slider(tab_crop, row, "crop_tilt_pid_kd", "Tilt PID Kd", 0.12, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_pan_target_offset_x", "Pan target offset X", 0.00, -1.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_crop, row, "crop_pan_target_offset_y", "Pan target offset Y", 0.00, -1.0, 1.0, resolution=0.01)

        row = 0
        self._add_bool_switch(tab_audio, row, "audio_enabled", "Audio mixer", True)
        row += 1
        audio_input_candidates = _audio_input_device_candidates()
        audio_input_default = _audio_default_input_device()
        if audio_input_default not in audio_input_candidates:
            audio_input_candidates.append(audio_input_default)
        self._add_combo(
            tab_audio,
            row,
            "audio_input_device",
            "Input device",
            audio_input_candidates,
            audio_input_default,
        )
        row += 1
        audio_output_candidates = _audio_output_device_candidates()
        audio_output_default = _audio_default_output_device()
        if audio_output_default not in audio_output_candidates:
            audio_output_candidates.append(audio_output_default)
        self._add_combo(
            tab_audio,
            row,
            "audio_output_device",
            "Output device",
            audio_output_candidates,
            audio_output_default,
        )
        row += 1
        ttk.Button(tab_audio, text="가상 마이크 생성", command=self._create_virtual_speaker).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        ttk.Button(tab_audio, text="가상 마이크 제거", command=self._remove_virtual_speaker).grid(
            row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        row += 1
        self._add_int(tab_audio, row, "audio_sample_rate", "Sample rate", 48000)
        self._add_int(tab_audio, row, "audio_channels", "Channels", 1, col_offset=2)
        row += 1
        self._add_int(tab_audio, row, "audio_frame_ms", "Frame ms", 20)
        row += 1
        self._add_bool_switch(tab_audio, row, "audio_denoise_enabled", "Noise cancel", True)
        row += 1
        denoise_backends = _audio_denoise_backend_options()
        self._add_combo(tab_audio, row, "audio_denoise_backend", "NC backend", denoise_backends, denoise_backends[0])
        row += 1
        self._add_slider(tab_audio, row, "audio_denoise_strength", "NC strength", 0.50, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_threshold_db", "Gate threshold dB", -40.0, -80.0, 0.0, resolution=0.5)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_hysteresis_db", "Gate hysteresis dB", 4.0, 0.0, 20.0, resolution=0.5)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_min_voice_band_ratio", "Min voice band ratio", 0.50, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_attack_ms", "Gate attack ms", 30, 0, 500, resolution=1)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_hold_ms", "Gate hold ms", 160, 0, 2000, resolution=1)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_release_ms", "Gate release ms", 2000, 0, 4000, resolution=1)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_open_gain", "Gate open gain", 1.0, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_closed_gain", "Gate closed gain", 0.0, 0.0, 1.0, resolution=0.01)
        row += 1
        ttk.Button(tab_audio, text="게이트 자동 튜닝", command=self._auto_tune_audio_gate).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        ttk.Button(tab_audio, text="오디오 게이트 테스트", command=self._run_audio_gate_test).grid(
            row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )
        row += 1
        ttk.Button(tab_audio, text="오디오 기본값 복원", command=self._reset_audio_settings).grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        action_row = 1
        action_frame = ttk.Frame(scroll_inner)
        action_frame.grid(row=action_row, column=0, sticky="ew", pady=(10, 0))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        ttk.Button(action_frame, text="Preview", command=self._preview).grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Button(action_frame, text="Save JSON", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)
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

    def _on_scroll_canvas_configure(self, event) -> None:
        self._scroll_canvas.itemconfigure(self._scroll_window, width=event.width)

    def _on_mouse_wheel(self, event) -> None:
        if not getattr(self, "_scroll_canvas", None):
            return
        delta = -1 * int(event.delta / 120)
        self._scroll_canvas.yview_scroll(delta, "units")

    def _on_mouse_wheel_linux(self, event) -> None:
        if not getattr(self, "_scroll_canvas", None):
            return
        if event.num == 4:
            self._scroll_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._scroll_canvas.yview_scroll(1, "units")

    def _add_text(self, parent, row, key, label, default, col_offset=0, readonly=False):
        ttk.Label(parent, text=label).grid(row=row, column=col_offset, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        entry = ttk.Entry(parent, textvariable=var)
        if readonly:
            entry.state(["disabled"])
        entry.grid(row=row, column=col_offset + 1, sticky="ew", padx=4)

    def _add_int(self, parent, row, key, label, default, col_offset=0, readonly=False):
        self._add_text(parent, row, key, label, str(default), col_offset, readonly=readonly)

    def _add_float(self, parent, row, key, label, default, col_offset=0):
        self._add_text(parent, row, key, label, str(default), col_offset)

    def _add_slider(self, parent, row, key, label, default, min_value, max_value, resolution=0.01):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
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

    def _add_combo(self, parent, row, key, label, values, default, readonly=False, col_offset=0):
        ttk.Label(parent, text=label).grid(row=row, column=col_offset, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        state = "disabled" if readonly else "readonly"
        combo = ttk.Combobox(parent, textvariable=var, values=values, state=state)
        span = 3 if col_offset == 0 else 1
        combo.grid(row=row, column=col_offset + 1, columnspan=span, sticky="ew", padx=4)
        self._widgets[key] = combo

    def _add_bool_switch(self, parent, row, key, label, default=False):
        var = tk.BooleanVar(value=bool(default))
        self.vars[key] = var
        check_btn = ttk.Checkbutton(parent, text=label, variable=var)
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
        selected = filedialog.askopenfilename(title="Select background image")
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
        }

    def _create_virtual_camera(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror("가상 카메라 생성", "Linux에서만 가상 카메라 생성이 가능합니다.")
            return

        backend = self.vars.get("output_backend").get() if self.vars.get("output_backend") else ""
        if backend != "v4l2loopback":
            messagebox.showerror("가상 카메라 생성", "output_backend가 v4l2loopback이어야 생성할 수 있습니다.")
            return

        device = (self.vars.get("output_device").get() if self.vars.get("output_device") else "").strip()
        video_no = _parse_video_device_number(device)
        if not video_no:
            messagebox.showerror("가상 카메라 생성", f"출력 경로가 /dev/videoN 형식이 아닙니다: {device}")
            return

        _log(f"Create virtual camera: video_no={video_no} label={VIRTUAL_CAMERA_LABEL}")
        # Browser(WebRTC) compatibility is best with exclusive_caps=1.
        # Keep fallback args for hosts where this mode is unavailable.
        camera_args = [
            ["devices=1", f"video_nr={video_no}", f"card_label={VIRTUAL_CAMERA_LABEL}", "exclusive_caps=1", "max_buffers=2"],
            ["devices=1", f"video_nr={video_no}", f"card_label={VIRTUAL_CAMERA_LABEL}", "exclusive_caps=0", "max_buffers=2"],
            ["devices=1", f"video_nr={video_no}", f"card_label={VIRTUAL_CAMERA_LABEL}", "max_buffers=2"],
        ]

        last_error = ""
        for idx, args in enumerate(camera_args):
            if idx > 0:
                _log("Reconfigure virtual camera with fallback args (capture compatibility attempt)")
                try:
                    reload_proc = _run_sudo_cmd_noninteractive(
                        ["modprobe", "-r", "v4l2loopback"],
                        check=False,
                        timeout=4.0,
                    )
                    if reload_proc.returncode != 0:
                        _log(f"modprobe -r skipped/failed: {reload_proc.stderr.strip()}")
                except Exception as exc:
                    _log(f"modprobe -r 실패(무시): {exc}")

            cmd = ["modprobe", "v4l2loopback", *args]
            try:
                _run_sudo_cmd_noninteractive(["modprobe", "videodev"], check=False, timeout=4.0)
                proc = _run_sudo_cmd_noninteractive(cmd, check=False, timeout=4.0)
            except Exception as exc:
                last_error = f"modprobe 실행 예외: {exc}"
                _log(last_error)
                continue
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                if "a password is required" in err.lower() or "sudo" in err.lower():
                    messagebox.showerror(
                        "가상 카메라 생성",
                        "sudo 비밀번호 입력이 필요한 상태입니다.\n"
                        "GUI에서는 비밀번호 프롬프트를 처리할 수 없어 중단했습니다.\n\n"
                        "터미널에서 `sudo -v` 실행 후 다시 시도하세요.",
                    )
                    return
                last_error = f"modprobe 로드 실패(code={proc.returncode}): {err}"
                _log(last_error)
                continue

            ready, detail = _probe_v4l2_capture(
                device,
                retries=10,
                delay_sec=0.2,
                require_output=True,
            )
            if ready:
                _log(f"Virtual camera webcam-capable confirmed on {device}: {detail} (args={args})")
                messagebox.showinfo("가상 카메라 생성", f"가상 카메라를 생성했습니다: {device}")
                return

            last_error = f"{device} created but not webcam-capable: {detail} (args={args})"
            _log(last_error)

        messagebox.showerror(
            "가상 카메라 생성",
            f"사용 가능한 가상 카메라 장치 생성 실패: {last_error}",
        )

    def _remove_virtual_camera(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror("가상 카메라 제거", "Linux에서만 가상 카메라 제거가 가능합니다.")
            return

        _log("Remove virtual camera: modprobe -r v4l2loopback")
        try:
            proc = _run_sudo_cmd_noninteractive(["modprobe", "-r", "v4l2loopback"], check=False, timeout=4.0)
        except Exception as exc:
            messagebox.showerror("가상 카메라 제거", f"모듈 제거 실패: {exc}")
            return

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if "a password is required" in err.lower() or "sudo" in err.lower():
                messagebox.showerror(
                    "가상 카메라 제거",
                    "sudo 비밀번호 입력이 필요한 상태입니다.\n"
                    "터미널에서 `sudo -v` 실행 후 다시 시도하세요.",
                )
                return
            messagebox.showerror(
                "가상 카메라 제거",
                f"모듈 제거 실패 (code={proc.returncode})\n{proc.stdout or ''}{proc.stderr or ''}".strip(),
            )
            return
        _log("Virtual camera removed: modprobe -r v4l2loopback")
        messagebox.showinfo("가상 카메라 제거", "가상 카메라 모듈을 언로드했습니다.")

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
            messagebox.showerror("가상 마이크 생성", "Linux에서만 가상 마이크 생성이 가능합니다.")
            return

        if _audio_sink_exists(AUDIO_VIRTUAL_SINK_NAME):
            _log(f"Virtual microphone already exists: {AUDIO_VIRTUAL_SINK_NAME}")
            messagebox.showinfo("가상 마이크 생성", f"이미 가상 마이크가 존재합니다: {AUDIO_VIRTUAL_SINK_NAME}")
            return

        _log(f"Create virtual microphone sink: {AUDIO_VIRTUAL_SINK_NAME}")
        try:
            proc = _run_cmd(
                [
                    "pactl",
                    "load-module",
                    "module-null-sink",
                    f"sink_name={AUDIO_VIRTUAL_SINK_NAME}",
                    f"sink_properties=device.description={AUDIO_VIRTUAL_SINK_NAME}",
                ],
                check=False,
                timeout=2.0,
            )
        except Exception as exc:
            messagebox.showerror("가상 마이크 생성", f"pactl 실행 실패: {exc}")
            return

        if proc.returncode != 0:
            messagebox.showerror(
                "가상 마이크 생성",
                f"pactl load-module 실패 (code={proc.returncode})\n{proc.stderr}".strip(),
            )
            return

        if not _audio_sink_exists(AUDIO_VIRTUAL_SINK_NAME):
            messagebox.showerror("가상 마이크 생성", "모듈은 로드되었지만 sink 목록에 반영되지 않았습니다.")
            return

        source_proc = _run_cmd(
            [
                "pactl",
                "load-module",
                "module-remap-source",
                f"master={AUDIO_VIRTUAL_SINK_NAME}.monitor",
                f"source_name={AUDIO_VIRTUAL_SOURCE_NAME}",
                f"source_properties=device.description={AUDIO_VIRTUAL_SOURCE_NAME}",
            ],
            check=False,
            timeout=2.0,
        )
        if source_proc.returncode != 0:
            _log(f"Remap source create failed: code={source_proc.returncode} err={source_proc.stderr.strip()}")
        else:
            _log(
                f"Virtual microphone source created: {AUDIO_VIRTUAL_SOURCE_NAME} "
                f"module_id={source_proc.stdout.strip()}"
            )

        default_source = _run_cmd(
            ["pactl", "set-default-source", AUDIO_VIRTUAL_SOURCE_NAME],
            check=False,
            timeout=2.0,
        )
        if default_source.returncode != 0:
            _log(f"set-default-source failed: code={default_source.returncode} err={default_source.stderr.strip()}")

        _log(f"Virtual microphone sink created: {AUDIO_VIRTUAL_SINK_NAME} module_id={proc.stdout.strip()}")
        output_widget = self._widgets.get("audio_output_device")
        if isinstance(output_widget, ttk.Combobox):
            output_values = list(output_widget["values"])
            if AUDIO_VIRTUAL_SINK_NAME not in output_values:
                output_widget["values"] = tuple(output_values + [AUDIO_VIRTUAL_SINK_NAME])
            self._set_var("audio_output_device", AUDIO_VIRTUAL_SINK_NAME)
        messagebox.showinfo(
            "가상 마이크 생성",
            f"가상 마이크를 생성했습니다: {AUDIO_VIRTUAL_SOURCE_NAME} (source)\n"
            f"회의 앱 입력으로는 '{AUDIO_VIRTUAL_SOURCE_NAME}' 또는 '{AUDIO_VIRTUAL_SINK_NAME}.monitor'를 선택하세요.",
        )

    def _remove_virtual_speaker(self) -> None:
        if platform.system() != "Linux":
            messagebox.showerror("가상 마이크 제거", "Linux에서만 가상 마이크 제거가 가능합니다.")
            return

        source_module_ids = _get_audio_source_module_ids(AUDIO_VIRTUAL_SOURCE_NAME)
        sink_module_ids = _get_audio_sink_module_ids(AUDIO_VIRTUAL_SINK_NAME)
        if not source_module_ids and not sink_module_ids:
            _log(f"Virtual microphone remove skipped: no related modules for {AUDIO_VIRTUAL_SINK_NAME}")
            messagebox.showinfo(
                "가상 마이크 제거",
                f"제거할 {AUDIO_VIRTUAL_SINK_NAME} 모듈이 없습니다.",
            )
            return

        failed: list[str] = []
        for mod_id in source_module_ids + sink_module_ids:
            _log(f"Unload module {mod_id} for virtual microphone {AUDIO_VIRTUAL_SINK_NAME}")
            try:
                proc = _run_cmd(["pactl", "unload-module", mod_id], check=False, timeout=2.0)
            except Exception as exc:
                failed.append(f"{mod_id}:{exc}")
                continue
            if proc.returncode != 0:
                failed.append(f"{mod_id}:{proc.returncode}:{proc.stderr.strip()}")
        if failed:
            messagebox.showerror("가상 마이크 제거", "일부 모듈 제거 실패:\n" + "\n".join(failed))
            return
        _log(f"Virtual microphone removed: {AUDIO_VIRTUAL_SINK_NAME}")
        messagebox.showinfo("가상 마이크 제거", f"가상 마이크 모듈을 제거했습니다: {AUDIO_VIRTUAL_SINK_NAME}")

    def _reset_video_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key, value in defaults.items():
            self._set_var(key, value)
        self._on_input_device_changed()
        self._on_input_width_changed()
        self._on_output_device_changed()
        self._on_output_height_changed()

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
            messagebox.showwarning("Load warning", f"Failed to parse config file:\n{config_path}\n\n{exc}")
            return

        input_cfg = raw.get("inputCamera") or {}
        output_cfg = raw.get("outputCamera") or {}
        seg_cfg = raw.get("segmentation") or {}
        selfie_cfg = seg_cfg.get("selfie") or {}
        bg_cfg = raw.get("background") or {}
        crop_cfg = raw.get("crop") or {}
        audio_cfg = raw.get("audio") or {}

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
        resolved_input_device = (
            defaults["audio_input_device"]
            if raw_input_device.lower() == "default" or not raw_input_device
            else _coerce_audio_input_device_for_sounddevice(raw_input_device)
        )
        resolved_output_device = (
            defaults["audio_output_device"]
            if raw_output_device.lower() == "default" or not raw_output_device
            else _coerce_audio_output_device_for_sounddevice(raw_output_device)
        )
        if (
            resolved_output_device != raw_output_device
            and raw_output_device
            and raw_output_device.lower() != "default"
        ):
            _log(
                f"audio output device was normalized: raw='{raw_output_device}' -> '{resolved_output_device}'"
            )
        self._set_var("audio_input_device", resolved_input_device)
        input_widget = self._widgets.get("audio_input_device")
        if isinstance(input_widget, ttk.Combobox):
            input_values = list(input_widget["values"])
            if resolved_input_device not in input_values:
                input_widget["values"] = tuple(input_values + [resolved_input_device])
            self.vars["audio_input_device"].set(resolved_input_device)
        self._set_var("audio_output_device", resolved_output_device)
        output_widget = self._widgets.get("audio_output_device")
        if isinstance(output_widget, ttk.Combobox):
            output_values = list(output_widget["values"])
            if resolved_output_device not in output_values:
                output_widget["values"] = tuple(output_values + [resolved_output_device])
            self.vars["audio_output_device"].set(resolved_output_device)
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
            title="Select chroma color",
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
            write_config(self.output_path, config)
            messagebox.showinfo("Saved", f"Config saved to {self.output_path}")
        except Exception as exc:
            messagebox.showerror("Validation error", str(exc))

    def _auto_tune_audio_gate(self):
        if sd is None:
            messagebox.showerror(
                "Audio tuning error",
                "sounddevice 모듈이 없습니다. ./bin/avc setup 후 다시 시도하세요.",
            )
            return
        if self._audio_tune_running:
            return
        try:
            sample_rate = int(self.vars["audio_sample_rate"].get())
            channels = int(self.vars["audio_channels"].get())
        except Exception:
            messagebox.showerror("Audio tuning error", "audio sample rate/channels 값이 올바르지 않습니다.")
            return
        if channels <= 0:
            channels = 1

        if self._audio_tune_window is None or not self._audio_tune_window.winfo_exists():
            self._audio_tune_window = tk.Toplevel(self.root)
            self._audio_tune_window.title("오디오 게이트 자동 튜닝")
            self._audio_tune_window.geometry("560x260")
            self._audio_tune_window.resizable(False, False)
            self._audio_tune_window.grab_set()

            container = ttk.Frame(self._audio_tune_window, padding=12)
            container.grid(sticky="nsew")
            for c in range(1):
                container.columnconfigure(c, weight=1)

            self._audio_tune_step_var = tk.StringVar(value="대기 중")
            self._audio_tune_step_list_var = tk.StringVar(value="")
            self._audio_tune_timer_var = tk.StringVar(value="타이머: -")
            self._audio_tune_status_var = tk.StringVar(value="작업을 시작합니다.")
            self._audio_tune_summary_var = tk.StringVar(value="결과가 여기에 표시됩니다.")

            ttk.Label(container, text="오디오 게이트 자동 튜닝", font=("Arial", 12, "bold")).grid(
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
            self._audio_tune_action_btn = ttk.Button(btn_row, text="1단계 시작", command=self._run_audio_tune_next_step)
            self._audio_tune_action_btn.pack(side="left")
            close_btn = ttk.Button(btn_row, text="닫기", command=self._close_auto_tune_window)
            close_btn.pack(side="right")
            self._audio_tune_window.protocol("WM_DELETE_WINDOW", self._close_auto_tune_window)
        else:
            self._audio_tune_window.lift()
            if self._audio_tune_step_var is not None:
                self._audio_tune_step_var.set("대기 중")
            if self._audio_tune_step_list_var is not None:
                self._audio_tune_step_list_var.set("")
            if self._audio_tune_status_var is not None:
                self._audio_tune_status_var.set("작업을 시작합니다.")
            if self._audio_tune_timer_var is not None:
                self._audio_tune_timer_var.set("타이머: -")
            if self._audio_tune_summary_var is not None:
                self._audio_tune_summary_var.set("결과가 여기에 표시됩니다.")
            if self._audio_tune_action_btn is not None and self._audio_tune_action_btn.winfo_exists():
                self._audio_tune_action_btn.configure(text="1단계 시작", state="normal")
            elif self._audio_tune_window is not None and self._audio_tune_window.winfo_exists():
                # Keep button state consistent even if internal handle was lost.
                for widget in self._audio_tune_window.winfo_children():
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Button) and child.cget("text") == "1단계 시작":
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
        self._audio_tune_progress = "1단계를 시작하려면 버튼을 누르세요."
        if self._audio_tune_step_var is not None:
            self._audio_tune_step_var.set("단계 0/2")
        if self._audio_tune_step_list_var is not None:
            self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (대기)\\n2) 음성 샘플 수집 (대기)")
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set("1단계 버튼을 눌러 진행하세요.")
        if self._audio_tune_summary_var is not None:
            self._audio_tune_summary_var.set("결과는 단계 완료 후 계산됩니다.")
        if self._audio_tune_timer_var is not None:
            self._audio_tune_timer_var.set("타이머: -")

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
            self._audio_tune_error = "audio sample rate/channels 값이 올바르지 않습니다."
            self._audio_tune_running = False
            return
        if channels <= 0:
            channels = 1

        if self._audio_tune_step == 0:
            self._start_tune_step_ambient(sample_rate, channels)
        elif self._audio_tune_step == 1:
            self._start_tune_step_speech(sample_rate, channels)

    def _start_tune_step_ambient(self, sample_rate: int, channels: int) -> None:
        if self._audio_tune_running is False:
            return

        self._audio_tune_is_recording = True
        self._audio_tune_step = 1
        self._audio_tune_progress = "2초 동안 조용히 있어 주세요. (배경 소음 기준 측정)"
        self._audio_tune_step_deadline = time.time() + 2.0
        if self._audio_tune_step_list_var is not None:
            self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (진행 중)\\n2) 음성 샘플 수집 (대기)")
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set("1단계 녹음을 진행 중입니다.")

        def _worker() -> None:
            try:
                ambient = self._record_audio_block(seconds=2.0, sample_rate=sample_rate, channels=channels, show_error=False)
                if self._audio_tune_cancelled:
                    return
                if ambient is None:
                    self._audio_tune_error = "배경 소음 측정에 실패했습니다."
                    self._audio_tune_running = False
                    return

                self._audio_tune_ambient = ambient
                self._audio_tune_progress = "1단계 완료. 2단계를 시작하세요."
                if self._audio_tune_step_list_var is not None:
                    self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (완료)\\n2) 음성 샘플 수집 (대기)")
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
            self._audio_tune_error = "1단계가 먼저 필요합니다."
            self._audio_tune_running = False
            return

        self._audio_tune_is_recording = True
        self._audio_tune_step = 2
        self._audio_tune_progress = "3초 동안 평소 회의 톤으로 말해 주세요. (음성 기준 측정)"
        self._audio_tune_step_deadline = time.time() + 3.0
        if self._audio_tune_step_list_var is not None:
            self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (완료)\\n2) 음성 샘플 수집 (진행 중)")
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set("2단계 녹음을 진행 중입니다.")

        def _worker() -> None:
            try:
                speech = self._record_audio_block(seconds=3.0, sample_rate=sample_rate, channels=channels, show_error=False)
                if self._audio_tune_cancelled:
                    return
                if speech is None:
                    self._audio_tune_error = "음성 샘플 측정에 실패했습니다."
                    self._audio_tune_running = False
                    return

                ambient = self._audio_tune_ambient
                if ambient is None:
                    self._audio_tune_error = "1단계 데이터가 없습니다."
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
                    "추천값을 반영했습니다.\\n"
                    f"- thresholdDb: {threshold_db:.1f}\\n"
                    f"- hysteresisDb: {hysteresis_db:.1f}\\n"
                    f"- minVoiceBandRatio: {min_voice_ratio:.2f}"
                )
                self._audio_tune_done = True
                self._audio_tune_progress = "완료"
                self._audio_tune_running = False
                if self._audio_tune_step_list_var is not None:
                    self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (완료)\\n2) 음성 샘플 수집 (완료)")
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
            self._audio_tune_step_var.set(f"단계 {self._audio_tune_step}/2")
        if self._audio_tune_status_var is not None:
            self._audio_tune_status_var.set(self._audio_tune_progress or "처리 중...")

        remaining = 0.0
        if (
            self._audio_tune_running
            and self._audio_tune_is_recording
            and self._audio_tune_step in (1, 2)
            and self._audio_tune_step_deadline > 0.0
        ):
            remaining = max(0.0, self._audio_tune_step_deadline - time.time())
        if self._audio_tune_timer_var is not None:
            self._audio_tune_timer_var.set(f"타이머: {remaining:.1f}s")

        if self._audio_tune_summary_var is not None:
            if self._audio_tune_error is not None:
                self._audio_tune_summary_var.set(f"오류: {self._audio_tune_error}")
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
                self._audio_tune_action_btn.configure(text="1단계 시작", state="normal")
            elif self._audio_tune_step == 1:
                self._audio_tune_action_btn.configure(text="2단계 시작", state="normal")
            elif self._audio_tune_step >= 2:
                self._audio_tune_action_btn.configure(state="disabled")

        if self._audio_tune_running or self._audio_tune_is_recording:
            self._audio_tune_after_id = self.root.after(100, self._auto_tune_audio_gate_tick)
            return

        if self._audio_tune_done:
            if self._audio_tune_step_list_var is not None:
                self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (완료)\\n2) 음성 샘플 수집 (완료)")
            if self._audio_tune_summary_var is not None:
                self._audio_tune_summary_var.set(self._audio_tune_result_text or "완료")
            if self._audio_tune_step_var is not None:
                self._audio_tune_step_var.set("완료")
            if self._audio_tune_status_var is not None:
                self._audio_tune_status_var.set("오디오 게이트 자동 튜닝이 완료되었습니다.")
            if self._audio_tune_timer_var is not None:
                self._audio_tune_timer_var.set("타이머: 0.0s")
        elif self._audio_tune_error is not None:
            if self._audio_tune_step_list_var is not None:
                self._audio_tune_step_list_var.set("1) 조용한 환경 오디오 수집 (완료/실패)\\n2) 음성 샘플 수집 (완료/실패)")
            if self._audio_tune_step_var is not None:
                self._audio_tune_step_var.set("실패")
            if self._audio_tune_status_var is not None:
                self._audio_tune_status_var.set("오류가 발생해 중단되었습니다.")

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
            messagebox.showerror("Audio gate test error", str(exc))
            return

        audio_cfg = config.get("audio") or {}
        if audio_cfg.get("enabled", False) is False:
            proceed = messagebox.askyesno(
                "오디오 게이트 테스트",
                "audio.enabled 값이 false입니다.\n현재 값으로 테스트를 진행할까요?",
            )
            if not proceed:
                return

        try:
            gate_config = AudioGateConfig.from_dict(audio_cfg.get("gate") or {})
        except Exception as exc:
            messagebox.showerror("Audio gate test error", f"게이트 설정이 유효하지 않습니다: {exc}")
            return

        sample_rate = int(audio_cfg.get("sampleRate", 48000))
        frame_ms = int(audio_cfg.get("frameMs", 20))
        frame_samples = max(1, int(sample_rate * frame_ms / 1000))
        channels = max(1, int(audio_cfg.get("channels", 1)))
        input_device = audio_cfg.get("inputDevice")
        if not isinstance(input_device, str) or not input_device.strip() or input_device.strip().lower() == "default":
            input_device = _audio_default_input_device()
        gate = NoiseGate(gate_config, frame_ms=frame_ms)

        if sd is None:
            messagebox.showerror(
                "Audio gate test error",
                "sounddevice 모듈이 없습니다. ./bin/avc setup 후 다시 시도하세요.",
            )
            return

        window = tk.Toplevel(self.root)
        window.title("오디오 게이트 실시간 테스트")
        window.geometry("640x480")
        window.minsize(640, 480)
        window.resizable(True, True)
        window.grab_set()

        content = ttk.Frame(window, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)

        title = ttk.Label(content, text="오디오 게이트 테스트", font=("Arial", 12, "bold"))
        title.grid(row=0, column=0, sticky="ew", padx=(0, 0), pady=(0, 8))

        info = ttk.Label(
            content,
            text=f"샘플레이트: {sample_rate}Hz / 프레임: {frame_ms}ms / 채널: {channels} / 입력: {input_device}",
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
        summary_var = tk.StringVar(value="측정 준비")
        runtime_var = tk.StringVar(value="실행 시간: 0.0s")
        row_index = 2
        for text, variable in [
            ("현재 게이트 상태", state_var),
            ("입력 레벨", level_var),
            ("대역 매칭", ratio_var),
            ("데시벨 판정", threshold_var),
            ("대역 매칭 판정", match_var),
            ("게이트 통과", gate_var),
            ("pass 통과", pass_var),
            ("스트림 상태", stream_state_var),
            ("스트림 오픈 횟수", stream_open_count_var),
            ("스트림 클로즈 횟수", stream_close_count_var),
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
        stop_btn = ttk.Button(control, text="중지")
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
            messagebox.showerror("Audio gate test error", f"마이크 입력 스트림 열기 실패: {exc}")
            return

        def refresh() -> None:
            if not self._audio_gate_test_running or not self._audio_gate_test_window:
                return
            if not self._audio_gate_test_window.winfo_exists():
                self._stop_audio_gate_test()
                return

            if self._audio_gate_test_error is not None:
                summary_var.set(f"오류: {self._audio_gate_test_error}")
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

                threshold_var.set("PASS" if passes_db else "BLOCK")
                match_var.set("PASS" if matches_band else "BLOCK")
                gate_var.set("PASS" if passes_gate else "BLOCK")
                pass_var.set("PASS" if (passes_db and matches_band and passes_gate) else "BLOCK")
                state_var.set(f"{state_text} (gain={gain:.2f})")
                stream_state_var.set("열림" if stream_open else "닫힘")
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
                        f"실시간 통과률: 게이트 {pass_ratio:.1f}% / "
                        f"대역매칭 {match_ratio:.1f}% / "
                        f"PASS 스트림 {stream_ratio:.1f}%"
                    )
                    summary_var.set(summary)

            elapsed = time.time() - self._audio_gate_test_started_at
            runtime_var.set(f"실행 시간: {elapsed:.1f}s")
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
                messagebox.showerror("Audio tuning error", f"마이크 입력 측정 실패:\n{exc}")
            return None
        if data is None or len(data) == 0:
            if show_error:
                messagebox.showerror("Audio tuning error", "빈 오디오 데이터가 수집되었습니다.")
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
        if self._preview_active:
            self._stop_preview()
            return
        try:
            config = self._build_config()
            self._start_preview(config)
        except Exception as exc:
            messagebox.showerror("Preview error", str(exc))

    def _start_preview(self, config: dict) -> None:
        from src.adapter.capture.opencv_capture import OpenCVCapture
        from src.domain.config import BackgroundConfig, InputCameraConfig, PersonCropConfig, SegmentationConfig
        from src.pipeline.frame_processor import FrameProcessor

        input_cfg = InputCameraConfig.from_dict(config["inputCamera"])
        seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
        bg_cfg = BackgroundConfig.from_dict(config["background"])
        crop_cfg = PersonCropConfig.from_dict(config["crop"])
        output_w = int(config["outputCamera"]["width"])
        output_h = int(config["outputCamera"]["height"])

        self._preview_capture = OpenCVCapture(input_cfg)
        self._preview_processor = FrameProcessor(seg_cfg, bg_cfg, crop_cfg, output_w, output_h)
        self._preview_out_size = (output_w, output_h)
        self._preview_processing_signature = self._processing_signature(config)
        self._preview_active = True
        self.root.after(1, self._preview_tick)

    def _stop_preview(self) -> None:
        self._preview_active = False
        if self._preview_capture is not None:
            self._preview_capture.release()
        self._preview_capture = None
        self._preview_processor = None
        self._preview_processing_signature = None
        try:
            cv2.destroyWindow(self._preview_window_name)
        except cv2.error:
            pass

    def _preview_tick(self) -> None:
        if not self._preview_active:
            return
        from src.domain.config import BackgroundConfig, PersonCropConfig, SegmentationConfig
        from src.pipeline.frame_processor import FrameProcessor

        try:
            frame = self._preview_capture.read()
            config = self._build_config()
            sig = self._processing_signature(config)
            out_w = int(config["outputCamera"]["width"])
            out_h = int(config["outputCamera"]["height"])
            self._preview_out_size = (out_w, out_h)

            if sig != self._preview_processing_signature or self._preview_processor is None:
                bg_cfg = BackgroundConfig.from_dict(config["background"])
                seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
                crop_cfg = PersonCropConfig.from_dict(config["crop"])
                self._preview_processor = FrameProcessor(seg_cfg, bg_cfg, crop_cfg, out_w, out_h)
                self._preview_processing_signature = sig

            output_frame = self._preview_processor.process(frame)
            preview = cv2.resize(output_frame, (max(1, out_w // 2), max(1, out_h // 2)), interpolation=cv2.INTER_AREA)
            cv2.imshow(self._preview_window_name, preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                self._stop_preview()
                return
        except Exception as exc:
            self._stop_preview()
            messagebox.showerror("Preview error", str(exc))
            return

        self.root.after(1, self._preview_tick)

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
        return (
            seg.get("backend"),
            seg.get("threshold"),
            seg.get("edgeSmoothness"),
            seg.get("blendFeather"),
            selfie.get("modelSelection"),
            selfie.get("temporalSmoothing"),
            self._background_signature(config["background"]),
            self._crop_signature(config["crop"]),
            int(config["outputCamera"]["width"]),
            int(config["outputCamera"]["height"]),
        )

    def _build_config(self):
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
            audio_input_device=iv["audio_input_device"].get().strip(),
            audio_output_device=iv["audio_output_device"].get().strip(),
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
        )


def parse_args():
    parser = argparse.ArgumentParser(description="GUI config generator for ai-virtual-cam")
    parser.add_argument("--output", default="~/.avc/setting.json")
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
    ConfigGui(root, args.output)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

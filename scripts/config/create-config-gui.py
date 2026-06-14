#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
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
from src.domain.whisper_defaults import whisper_default, whisper_defaults
from src.tools.config_io import discover_camera_mode_options, discover_cameras, write_config
from src.audio.gate import AudioGateConfig, NoiseGate
from scripts.config.audio_devices import (
    AUDIO_VIRTUAL_SINK_NAME,
    AUDIO_VIRTUAL_SOURCE_NAME,
    _audio_default_input_device,
    _audio_default_output_device,
    _audio_device_display_values,
    _audio_device_raw_from_display,
    _audio_input_device_candidates,
    _audio_output_device_candidates,
    _audio_sink_exists,
    _audio_source_exists,
    _available_input_meter_devices,
    _can_capture_exact_pulse_source,
    _coerce_audio_input_device_for_sounddevice,
    _get_audio_sink_module_ids,
    _get_audio_source_module_ids,
    _resolve_and_validate_audio_runtime_devices,
)
from scripts.config.components import add_numeric_slider
from scripts.config.i18n import (
    LANG_PACK_DIR,
    load_language_pack as _load_language_pack,
    read_flat_yaml as _read_flat_yaml,
)
from scripts.config.audio_tab import build_audio_tab
from scripts.config.background_tab import build_background_tab
from scripts.config.crop_tab import build_crop_tab
from scripts.config.face_tab import build_face_tab
from scripts.config.io_tab import build_io_tab
from scripts.config.segmentation_tab import build_segmentation_tab
from scripts.config.whisper_tab import build_whisper_tab
from scripts.config.whisper_options import (
    whisper_language_display_from_raw as _whisper_language_display_from_raw,
    whisper_language_raw_from_display as _whisper_language_raw_from_display,
    whisper_sentence_boundary_model_options as _whisper_sentence_boundary_model_options,
    whisper_stt_backend_options as _whisper_stt_backend_options,
    whisper_stt_backend_runtime_option_keys as _whisper_stt_backend_runtime_option_keys,
    whisper_stt_model_options as _whisper_stt_model_options,
    whisper_translation_backend_options as _whisper_translation_backend_options,
    whisper_translation_model_options as _whisper_translation_model_options,
    whisper_translation_target_display_from_raw as _whisper_translation_target_display_from_raw,
    whisper_translation_target_options_for_backend as _whisper_translation_target_options_for_backend,
    whisper_translation_target_raw_from_display as _whisper_translation_target_raw_from_display,
)


def _segmentation_backend_options():
    if platform.system() == "Darwin":
        return ["selfie", "selfie_ensemble", "mock", "onnxruntime"]
    return ["selfie", "selfie_ensemble", "mock", "onnxruntime", "tensorrt"]


SEG_ENGINE_OPTION_FIELDS: dict[str, tuple[str, ...]] = {
    "selfie": ("temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "selfie_ensemble": ("modelBlend", "temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "onnxruntime": ("temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "tensorrt": ("enginePath", "temporalAlpha", "maskBlur", "morphOpen", "morphClose", "maskGamma"),
    "mock": (),
}


def _output_backend_options():
    if platform.system() == "Darwin":
        return ["pyvirtualcam", "opencv"]
    return ["v4l2loopback", "opencv"]


def _audio_denoise_backend_options():
    if platform.system() == "Darwin":
        return ["none", "rnnoise"]
    return ["none", "rnnoise", "deepfilternet"]


VIRTUAL_CAMERA_LABEL = "ai-virtual-cam"
DEFAULT_WINDOW_GEOMETRY = "780x900"
DEFAULT_WINDOW_GEOMETRY_META = {
    "windowGeometry": "780x900+0+0",
    "previewWindowGeometry": "640x480+80+80",
    "audioTuneWindowGeometry": "640x480+100+100",
    "audioGateTestWindowGeometry": "640x480+120+120",
    "inputMeterWindowGeometry": "640x480+140+140",
    "whisperWindowGeometry": "780x420+50+119",
    "whisperTranslationWindowGeometry": "780x420+860+119",
}
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 480
_WINDOW_GEOMETRY_RE = re.compile(
    r"^(?P<width>\d+)x(?P<height>\d+)(?P<x_sign>[+-])(?P<x>\d+)(?P<y_sign>[+-])(?P<y>\d+)$"
)
_WINDOW_GEOMETRY_CACHE_LOG_RE = re.compile(
    r"window geometry cached: key=(?P<key>[A-Za-z0-9_]+Geometry) geometry=(?P<geometry>\S+)"
)


def _default_tensorrt_engine_path() -> str:
    return str(Path.home() / ".avc" / "models" / "person-segmentation.engine")


def _log(msg: str) -> None:
    print(f"[avc] {msg}", flush=True)


def _parse_window_geometry(geometry: object) -> dict[str, int] | None:
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


def _format_window_geometry(parts: dict[str, int]) -> str:
    x = int(parts["x"])
    y = int(parts["y"])
    return f'{int(parts["width"])}x{int(parts["height"])}{x:+d}{y:+d}'


def _window_restore_extent(root) -> tuple[int, int]:
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


def _window_manager_geometry(window) -> str:
    try:
        geometry = window.geometry()
        if isinstance(geometry, str) and geometry.strip():
            return geometry
    except TypeError:
        pass
    except Exception:
        pass
    return window.winfo_geometry()


def _sanitize_window_geometry(geometry: object, screen_width: int, screen_height: int) -> str | None:
    parts = _parse_window_geometry(geometry)
    if parts is None:
        return None
    width = parts["width"]
    height = parts["height"]
    x = parts["x"]
    y = parts["y"]
    if width < MIN_WINDOW_WIDTH or height < MIN_WINDOW_HEIGHT:
        return None
    if screen_width <= 0 or screen_height <= 0:
        return _format_window_geometry(parts)
    visible_margin = 80
    if x >= screen_width - visible_margin or y >= screen_height - visible_margin:
        return None
    if x + width <= visible_margin or y + height <= visible_margin:
        return None
    return _format_window_geometry(parts)


def _merge_window_geometry_meta(config: dict, existing_meta: dict | None, cached_meta: dict[str, str]) -> None:
    meta = config.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        config["meta"] = meta
    for key, value in DEFAULT_WINDOW_GEOMETRY_META.items():
        meta.setdefault(key, value)
    if isinstance(existing_meta, dict):
        for key, value in existing_meta.items():
            if str(key).endswith("Geometry") and isinstance(value, str):
                meta[str(key)] = value
    for key, value in cached_meta.items():
        if str(key).endswith("Geometry") and isinstance(value, str):
            meta[key] = value


def _parse_window_geometry_cache_log(line: str) -> tuple[str, str] | None:
    match = _WINDOW_GEOMETRY_CACHE_LOG_RE.search(line or "")
    if match is None:
        return None
    key = match.group("key")
    parts = _parse_window_geometry(match.group("geometry"))
    if parts is None:
        return None
    return key, _format_window_geometry(parts)


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


class ConfigGui:
    def __init__(self, root: tk.Tk, output_path: str, language: str = "ko") -> None:
        self.root = root
        self._tk = tk
        self._ttk = ttk
        self.output_path = output_path
        self._lang = (language or "ko").strip().lower()
        if self._lang not in {"ko", "en"}:
            self._lang = "ko"
        self._i18n = _load_language_pack(self._lang)
        self._localized_widgets: list[tuple[object, str, str]] = []
        self._bool_switch_meta: list[tuple[ttk.Checkbutton, tk.BooleanVar, str, str]] = []
        self.root.title(self._tr("title.main", "ai-virtual-cam config GUI"))
        self.root.geometry(DEFAULT_WINDOW_GEOMETRY)
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
        self._slider_formatters: dict[str, object] = {}
        self._slider_normalizers: dict[str, object] = {}
        self._slider_entries: dict[str, object] = {}
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
        self._audio_input_meter_process: subprocess.Popen[bytes] | None = None
        self._audio_input_meter_reader_thread: threading.Thread | None = None
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
        self._whisper_model_download_process: subprocess.Popen[str] | None = None
        self._whisper_model_download_thread: threading.Thread | None = None
        self._whisper_model_download_btn: ttk.Button | None = None
        self._whisper_model_download_progress: ttk.Progressbar | None = None
        self._whisper_model_download_window: tk.Toplevel | None = None
        self._whisper_model_download_log_text: tk.Text | None = None
        self._whisper_model_download_on_success: Callable[[], None] | None = None
        self._whisper_model_download_status_var = tk.StringVar(
            value=self._tr("status.whisper_model_download_idle", "모델 다운로드 대기 중")
        )
        self._whisper_model_download_status_label: ttk.Label | None = None
        self._language_var = tk.StringVar(value=self._lang)
        self._language_var.trace_add("write", lambda *_args: self._on_language_changed())
        self._language_label: ttk.Label | None = None
        self._notebook: ttk.Notebook | None = None
        self._scroll_canvas: tk.Canvas | None = None
        self._scrollbar: ttk.Scrollbar | None = None
        self._scroll_inner: ttk.Frame | None = None
        self._scroll_window: int | None = None
        self._scrollbar_update_after_id = None
        self._window_geometry_save_after_id: str | None = None
        self._window_geometry_meta_cache: dict[str, str] = {}
        self._tab_meta: list[tuple[ttk.Frame, str, str]] = []
        self._grid_row_cache = {}
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
        self._register_hidden_whisper_vars()
        self._load_existing_config()
        self.root.bind("<Configure>", self._on_root_configure)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _register_hidden_whisper_vars(self) -> None:
        defaults = self._build_video_defaults()
        for key in (
            "whisper_sentence_boundary_device",
            "whisper_sentence_boundary_compute_type",
        ):
            if key not in self.vars:
                self.vars[key] = tk.StringVar(value=str(defaults[key]))

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
        return [avc_bin, "serve", "--config", config_path, "--with-whisper-window"]

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
        for check_btn, var, label_key, default_label in self._bool_switch_meta:
            self._update_bool_switch_text(check_btn, var, label_key, default_label)
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

    def _launch_serve_command(self, cmd: list[str]) -> None:
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
            self._show_error(
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

    def _whisper_enabled_in_config(self, config: dict) -> bool:
        whisper_cfg = config.get("whisper") if isinstance(config.get("whisper"), dict) else {}
        return bool(whisper_cfg.get("enabled"))

    def _check_whisper_models_ready_for_serve(self, config: dict, serve_cmd: list[str]) -> bool:
        if not self._whisper_enabled_in_config(config):
            _log("Whisper model cache check skipped: whisper.enabled=false")
            return True
        check_cmd = self._build_whisper_model_download_command(config, check_only=True)
        print(f"[avc] Whisper model cache check starting: {' '.join(check_cmd)}", flush=True)
        try:
            result = subprocess.run(
                check_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(ROOT_DIR),
                env=dict(os.environ),
                check=False,
            )
        except Exception as exc:
            output = f"Whisper model cache check failed to run: {exc}"
            print(f"[avc] {output}", flush=True)
            self._show_whisper_model_download_dialog(config, serve_cmd, output)
            return False
        output = result.stdout or ""
        for line in output.splitlines():
            print(line, flush=True)
        if result.returncode == 0:
            print("[avc] Whisper model cache check ok", flush=True)
            return True
        print(f"[avc] Whisper model cache check missing models: code={result.returncode}", flush=True)
        self._show_whisper_model_download_dialog(config, serve_cmd, output)
        return False

    def _show_whisper_model_download_dialog(self, config: dict, serve_cmd: list[str], check_output: str) -> None:
        if self._whisper_model_download_window is not None and self._whisper_model_download_window.winfo_exists():
            self._whisper_model_download_window.lift()
            return
        window = tk.Toplevel(self.root)
        self._whisper_model_download_window = window
        window.title(self._tr("title.whisper_model_download", "Whisper 모델 다운로드"))
        window.transient(self.root)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(2, weight=1)
        window.geometry("720x420")
        window.protocol("WM_DELETE_WINDOW", lambda: self._close_whisper_model_download_dialog(False))

        ttk.Label(
            window,
            text=self._tr(
                "msg.whisper_model_download_required",
                "설정에 적용된 Whisper/STT/문장경계/번역 모델 중 로컬 캐시에 없는 모델이 있습니다. 다운로드가 완료될 때까지 Serve는 시작되지 않습니다.",
            ),
            wraplength=680,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        self._whisper_model_download_progress = ttk.Progressbar(window, mode="determinate", maximum=100)
        self._whisper_model_download_progress.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        log_text = tk.Text(window, height=12, wrap="word")
        log_text.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 6))
        if check_output.strip():
            log_text.insert("end", check_output.strip() + "\n")
        log_text.configure(state="disabled")
        self._whisper_model_download_log_text = log_text

        self._whisper_model_download_status_var.set(
            self._tr("status.whisper_model_download_required", "모델 다운로드가 필요합니다.")
        )
        ttk.Label(window, textvariable=self._whisper_model_download_status_var, foreground="#666", wraplength=680).grid(
            row=3, column=0, sticky="ew", padx=12, pady=(0, 6)
        )

        button_frame = ttk.Frame(window)
        button_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=0)
        button_frame.columnconfigure(2, weight=0)
        self._whisper_model_download_btn = ttk.Button(
            button_frame,
            text=self._tr("button.whisper_model_download", "모델 다운로드"),
            command=lambda: self._start_whisper_model_download(
                config=config,
                on_success=lambda: self._launch_serve_command(serve_cmd),
            ),
        )
        self._whisper_model_download_btn.grid(row=0, column=1, sticky="e", padx=(4, 4))
        ttk.Button(
            button_frame,
            text=self._tr("button.cancel", "취소"),
            command=lambda: self._close_whisper_model_download_dialog(False),
        ).grid(row=0, column=2, sticky="e")

    def _close_whisper_model_download_dialog(self, downloaded: bool) -> None:
        process = self._whisper_model_download_process
        if process is not None and process.poll() is None:
            self._set_whisper_model_download_status(
                self._tr("status.whisper_model_download_running", "모델 다운로드가 이미 진행 중입니다.")
            )
            return
        window = self._whisper_model_download_window
        self._whisper_model_download_window = None
        self._whisper_model_download_btn = None
        self._whisper_model_download_progress = None
        self._whisper_model_download_log_text = None
        self._whisper_model_download_on_success = None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass
        if not downloaded:
            self._set_serve_status(
                self._tr("status.serve_stopped", "Serve: stopped"),
                running=False,
                status_key="status.serve_stopped",
            )

    def _start_serve(self) -> None:
        if self._is_serve_running():
            return
        if self._preview_active:
            self._show_error(
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
            self._apply_persistent_meta(config)
            write_config(config_path, config)
        except Exception as exc:
            _log(f"Validation error: {exc}")
            self._show_error(self._tr("msg.validation_error.title", "Validation error"), str(exc))
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
            self._show_error(
                self._tr("msg.serve_start_title", "Serve start failed"),
                str(exc),
            )
            return

        if not self._check_whisper_models_ready_for_serve(config, cmd):
            return
        self._launch_serve_command(cmd)

    def _set_whisper_model_download_status(self, message: str) -> None:
        self._whisper_model_download_status_var.set(message)

    def _on_whisper_model_download_line(self, message: str) -> None:
        self._set_whisper_model_download_status(message)
        log_text = self._whisper_model_download_log_text
        if log_text is not None:
            try:
                log_text.configure(state="normal")
                log_text.insert("end", message + "\n")
                log_text.see("end")
                log_text.configure(state="disabled")
            except Exception:
                pass
        progress = self._whisper_model_download_progress
        if progress is None:
            return
        lower = message.lower()
        current = float(progress.cget("value") or 0)
        value = current
        if "downloading faster-whisper" in lower or "downloading funasr stt" in lower:
            value = max(current, 15)
        elif "faster-whisper model ready" in lower or "funasr stt model ready" in lower:
            value = max(current, 35)
        elif "downloading sat sentence" in lower or "downloading funasr punctuation" in lower:
            value = max(current, 45)
        elif "sentence boundary model ready" in lower or "punctuation model ready" in lower:
            value = max(current, 65)
        elif "downloading nllb translation" in lower or "downloading m2m100 translation" in lower:
            value = max(current, 75)
        elif "translation model ready" in lower:
            value = max(current, 95)
        elif "pre-download completed" in lower:
            value = 100
        progress.configure(value=value)

    def _build_whisper_model_download_command(self, config: dict | None = None, *, check_only: bool = False) -> list[str]:
        if config is None:
            config = self._build_config(validate_audio=False)
        whisper_cfg = config.get("whisper") if isinstance(config.get("whisper"), dict) else {}
        venv_python = ROOT_DIR / ".venv" / "bin" / "python"
        python_cmd = str(venv_python if venv_python.exists() else Path(sys.executable))
        cmd = [
            python_cmd,
            "-u",
            str(ROOT_DIR / "scripts" / "setup" / "download-whisper-models.py"),
        ]
        if check_only:
            cmd.append("--check-only")

        stt_pairs = (
            ("backend", "model"),
            ("sttBackendEn", "sttModelEn"),
            ("sttBackendKo", "sttModelKo"),
            ("sttBackendZh", "sttModelZh"),
        )
        for backend_key, model_key in stt_pairs:
            backend = str(whisper_cfg.get(backend_key) or "").strip()
            model = str(whisper_cfg.get(model_key) or "").strip()
            if backend and model:
                cmd.extend(["--stt-backend", backend, "--stt-model", model])

        boundary_pairs = (
            ("sentenceBoundaryBackend", "sentenceBoundaryModel"),
            ("sentenceBoundaryBackendEn", "sentenceBoundaryModelEn"),
            ("sentenceBoundaryBackendKo", "sentenceBoundaryModelKo"),
            ("sentenceBoundaryBackendZh", "sentenceBoundaryModelZh"),
        )
        for backend_key, model_key in boundary_pairs:
            backend = str(whisper_cfg.get(backend_key) or "").strip()
            model = str(whisper_cfg.get(model_key) or "").strip()
            if backend and model:
                cmd.extend(["--boundary-backend", backend, "--boundary-model", model])

        if bool(whisper_cfg.get("translationEnabled")):
            translation_backend = str(whisper_cfg.get("translationBackend") or "nllb-transformers").strip()
            translation_model = str(whisper_cfg.get("translationModel") or "facebook/nllb-200-distilled-600M").strip()
            cmd.extend(["--translation-backend", translation_backend, "--translation-model", translation_model])
        else:
            cmd.append("--skip-translation")
        return cmd

    def _start_whisper_model_download(self, *, config: dict | None = None, on_success: Callable[[], None] | None = None) -> None:
        process = self._whisper_model_download_process
        if process is not None and process.poll() is None:
            self._set_whisper_model_download_status(
                self._tr("status.whisper_model_download_running", "모델 다운로드가 이미 진행 중입니다.")
            )
            return
        self._sync_whisper_runtime_options()
        self._sync_whisper_translation_backend_options()
        try:
            cmd = self._build_whisper_model_download_command(config)
        except Exception as exc:
            message = f"Whisper model download command build failed: {exc}"
            print(f"[avc] {message}", flush=True)
            self._show_error(self._tr("msg.whisper_model_download_error.title", "모델 다운로드 오류"), str(exc))
            return

        self._whisper_model_download_on_success = on_success
        print(f"[avc] Whisper model download starting: {' '.join(cmd)}", flush=True)
        self._set_whisper_model_download_status(
            self._tr("status.whisper_model_download_starting", "모델 다운로드를 시작합니다.")
        )
        if self._whisper_model_download_btn is not None:
            self._whisper_model_download_btn.state(["disabled"])
        if self._whisper_model_download_progress is not None:
            self._whisper_model_download_progress.configure(value=5)
        try:
            self._whisper_model_download_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(ROOT_DIR),
                env=dict(os.environ),
            )
        except Exception as exc:
            self._whisper_model_download_process = None
            if self._whisper_model_download_progress is not None:
                self._whisper_model_download_progress.configure(value=0)
            if self._whisper_model_download_btn is not None:
                self._whisper_model_download_btn.state(["!disabled"])
            print(f"[avc] Whisper model download start failed: {exc}", flush=True)
            self._show_error(self._tr("msg.whisper_model_download_error.title", "모델 다운로드 오류"), str(exc))
            self._set_whisper_model_download_status(str(exc))
            return

        self._whisper_model_download_thread = threading.Thread(
            target=self._whisper_model_download_worker,
            args=(self._whisper_model_download_process,),
            daemon=True,
        )
        self._whisper_model_download_thread.start()

    def _whisper_model_download_worker(self, process: subprocess.Popen[str]) -> None:
        last_line = ""
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    clean_line = line.rstrip("\n")
                    if not clean_line:
                        continue
                    last_line = clean_line
                    print(clean_line, flush=True)
                    try:
                        self.root.after(0, lambda msg=clean_line: self._on_whisper_model_download_line(msg))
                    except RuntimeError:
                        pass
            return_code = process.wait()
        except Exception as exc:
            last_line = str(exc)
            print(f"[avc] Whisper model download watcher failed: {exc}", flush=True)
            return_code = process.returncode if process is not None else 1
        try:
            self.root.after(0, lambda code=return_code, msg=last_line: self._whisper_model_download_finished(code, msg))
        except RuntimeError:
            self._whisper_model_download_process = None
            self._whisper_model_download_thread = None

    def _whisper_model_download_finished(self, return_code: int | None, last_line: str) -> None:
        self._whisper_model_download_process = None
        self._whisper_model_download_thread = None
        if self._whisper_model_download_progress is not None:
            self._whisper_model_download_progress.configure(value=100 if return_code == 0 else 0)
        if self._whisper_model_download_btn is not None:
            self._whisper_model_download_btn.state(["!disabled"])
        if return_code == 0:
            message = self._tr("status.whisper_model_download_done", "모델 다운로드가 완료되었습니다.")
            print(f"[avc] Whisper model download finished", flush=True)
            on_success = self._whisper_model_download_on_success
            self._close_whisper_model_download_dialog(True)
            if on_success is not None:
                on_success()
            return
        else:
            message = self._tr("status.whisper_model_download_failed", "모델 다운로드 실패(code={code})").format(code=return_code)
            if last_line:
                message = f"{message}: {last_line}"
            print(f"[avc] Whisper model download failed: code={return_code} last={last_line}", flush=True)
            self._set_serve_status(
                self._tr("status.serve_stopped", "Serve: stopped"),
                running=False,
                status_key="status.serve_stopped",
            )
        self._set_whisper_model_download_status(message)

    def _serve_output_worker(self, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    clean_line = line.rstrip("\n")
                    print(clean_line, flush=True)
                    self._remember_external_window_geometry_from_log(clean_line)
            return_code = process.wait()
        except Exception as exc:
            _log(f"Serve watcher failed: {exc}")
            return_code = process.returncode
        try:
            self.root.after(0, lambda: self._serve_process_finished(return_code))
        except RuntimeError:
            self._serve_process = None
            self._serve_stop_requested = False
            self._serve_output_thread = None

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
        if self._window_geometry_save_after_id is not None:
            try:
                self.root.after_cancel(self._window_geometry_save_after_id)
            except Exception:
                pass
            self._window_geometry_save_after_id = None
        self._capture_all_window_geometry_meta()
        if self._is_serve_running():
            self._stop_serve()
        if self._preview_active:
            self._stop_preview()
        self.root.destroy()

    def _current_window_geometry(self) -> str:
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        return _window_manager_geometry(self.root)

    def _current_preview_window_geometry(self) -> str | None:
        window = getattr(self, "_preview_window", None)
        if window is None:
            return None
        try:
            if not window.winfo_exists():
                return None
            window.update_idletasks()
            return _window_manager_geometry(window)
        except Exception:
            return None

    def _on_root_configure(self, event) -> None:
        if event.widget != self.root:
            return
        self._schedule_save_window_geometry_meta()

    def _on_preview_configure(self, event) -> None:
        if self._preview_window is None or event.widget != self._preview_window:
            return
        self._schedule_save_window_geometry_meta()

    def _schedule_save_window_geometry_meta(self) -> None:
        if self._window_geometry_save_after_id is not None:
            try:
                self.root.after_cancel(self._window_geometry_save_after_id)
            except Exception:
                pass
        self._window_geometry_save_after_id = self.root.after(600, self._capture_all_window_geometry_meta)

    def _restore_window_geometry(self, meta_cfg: dict) -> None:
        saved = meta_cfg.get("windowGeometry")
        geometry = _sanitize_window_geometry(
            saved,
            *_window_restore_extent(self.root),
        )
        if geometry is None:
            _log(
                "WARN [Window geometry restore] "
                f"setting.json has no valid meta.windowGeometry. saved={saved!r}; "
                "keeping startup geometry until JSON save captures it"
            )
            return
        self.root.geometry(geometry)
        self._geometry_meta_cache()["windowGeometry"] = geometry
        _log(f"Window geometry restored: key=windowGeometry geometry={geometry}")

    def _restore_preview_window_geometry(self, window: tk.Toplevel, meta_cfg: dict) -> None:
        self._restore_named_window_geometry(window, "previewWindowGeometry", meta_cfg)

    def _restore_named_window_geometry(self, window: tk.Toplevel, key: str, meta_cfg: dict | None = None) -> None:
        if meta_cfg is None:
            meta_cfg = self._read_geometry_meta()
        saved = meta_cfg.get(key)
        geometry = _sanitize_window_geometry(
            saved,
            *_window_restore_extent(window),
        )
        if geometry is None:
            geometry = DEFAULT_WINDOW_GEOMETRY_META.get(key)
            if geometry is None:
                _log(f"WARN [Window geometry restore] no default geometry: key={key} saved={saved!r}")
                return
            _log(
                f"WARN [Window geometry restore] key={key} has no valid saved geometry. "
                f"saved={saved!r}; using default={geometry}"
            )
        window.geometry(geometry)
        self._geometry_meta_cache()[key] = geometry
        _log(f"Window geometry restored: key={key} geometry={geometry}")

    def _read_geometry_meta(self) -> dict:
        config_path = Path(self.output_path).expanduser()
        if not config_path.exists():
            return {}
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            meta = raw.get("meta") or {}
            return meta if isinstance(meta, dict) else {}
        except Exception as exc:
            _log(f"Window geometry meta load failed: {exc}")
            return {}

    def _remember_named_window_geometry(self, key: str, window: tk.Toplevel | None) -> None:
        if window is None:
            return
        try:
            if not window.winfo_exists():
                return
            window.update_idletasks()
            geometry = _sanitize_window_geometry(
                _window_manager_geometry(window),
                *_window_restore_extent(window),
            )
            if geometry is not None:
                self._geometry_meta_cache()[key] = geometry
        except Exception as exc:
            _log(f"Window geometry capture failed: key={key} error={exc}")

    def _geometry_meta_cache(self) -> dict[str, str]:
        cache = getattr(self, "_window_geometry_meta_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._window_geometry_meta_cache = cache
        return cache

    def _remember_external_window_geometry_from_log(self, line: str) -> None:
        parsed = _parse_window_geometry_cache_log(line)
        if parsed is None:
            return
        key, geometry = parsed
        self._geometry_meta_cache()[key] = geometry
        _log(f"Window geometry cached from serve log: key={key} geometry={geometry}")

    def _capture_all_window_geometry_meta(self) -> None:
        self._window_geometry_save_after_id = None
        cache = self._geometry_meta_cache()
        try:
            raw_geometry = self._current_window_geometry()
            geometry = _sanitize_window_geometry(
                raw_geometry,
                *_window_restore_extent(self.root),
            )
            if geometry is None:
                _log(f"ERROR [Window geometry capture] invalid main window geometry: {raw_geometry!r}")
            else:
                cache["windowGeometry"] = geometry
                _log(f"Window geometry cached: key=windowGeometry geometry={geometry}")
            preview_geometry = self._current_preview_window_geometry()
            if preview_geometry:
                cache["previewWindowGeometry"] = preview_geometry
                _log(f"Window geometry cached: key=previewWindowGeometry geometry={preview_geometry}")
            self._remember_named_window_geometry("audioTuneWindowGeometry", getattr(self, "_audio_tune_window", None))
            self._remember_named_window_geometry("audioGateTestWindowGeometry", getattr(self, "_audio_gate_test_window", None))
            self._remember_named_window_geometry("inputMeterWindowGeometry", getattr(self, "_audio_input_meter_window", None))
        except Exception as exc:
            _log(f"ERROR [Window geometry capture] {exc}")

    def _apply_window_geometry_meta(self, config: dict) -> None:
        self._capture_all_window_geometry_meta()
        _merge_window_geometry_meta(config, self._read_geometry_meta(), self._geometry_meta_cache())
        meta = config.get("meta") if isinstance(config.get("meta"), dict) else {}
        keys = sorted(key for key in meta if str(key).endswith("Geometry"))
        missing = sorted(key for key in DEFAULT_WINDOW_GEOMETRY_META if key not in meta)
        if missing:
            raise ValueError(f"Window geometry save failed: missing geometry keys={','.join(missing)}")
        _log(f"Window geometry saved to setting.json on JSON save: keys={','.join(keys)}")

    def _apply_persistent_meta(self, config: dict) -> None:
        config.setdefault("meta", {})["language"] = self._language_var.get().strip().lower() or self._lang
        self._apply_window_geometry_meta(config)

    def _tr(self, key: str, default: str) -> str:
        value = self._i18n.get(key)
        if value is None:
            return default
        return value

    def _show_error(self, title: str, message: str) -> None:
        _log(f"ERROR [{title}] {message}")
        try:
            messagebox.showerror(title, message)
        except Exception:
            pass

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
        tab_whisper = ttk.Frame(notebook, padding=8)
        self._tab_meta = [
            (tab_io, "title.tab.io", "I/O"),
            (tab_seg, "title.tab.seg", "Segmentation"),
            (tab_bg, "title.tab.bg", "Background"),
            (tab_crop, "title.tab.crop", "Framing"),
            (tab_face, "title.tab.face", "Face"),
            (tab_audio, "title.tab.audio", "Audio"),
            (tab_whisper, "title.tab.whisper", "Whisper"),
        ]
        for tab, key, default in self._tab_meta:
            notebook.add(tab, text=self._tr(key, default))
        for tab in (tab_io, tab_seg, tab_bg, tab_crop, tab_audio, tab_face, tab_whisper):
            for col in range(4):
                tab.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        build_io_tab(
            self,
            tab_io,
            ttk,
            platform.system,
            discover_cameras,
            discover_camera_mode_options,
            _output_backend_options,
            _default_virtual_output_device,
        )

        build_segmentation_tab(self, tab_seg, ttk, _segmentation_backend_options)

        build_background_tab(self, tab_bg, ttk)

        build_crop_tab(self, tab_crop, ttk)

        build_audio_tab(
            self,
            tab_audio,
            ttk,
            platform.system,
            _audio_input_device_candidates,
            _audio_default_input_device,
            _audio_output_device_candidates,
            _audio_default_output_device,
            _audio_device_display_values,
            _audio_denoise_backend_options,
        )

        build_face_tab(self, tab_face, ttk)

        build_whisper_tab(
            self,
            tab_whisper,
            ttk,
            _audio_input_device_candidates,
            _audio_default_input_device,
            _audio_device_display_values,
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
        whisper_translation_backend_widget = self._widgets.get("whisper_translation_backend")
        if whisper_translation_backend_widget is not None:
            whisper_translation_backend_widget.bind("<<ComboboxSelected>>", self._on_whisper_translation_backend_changed)
        for key in (
            "whisper_language",
            "whisper_backend",
            "whisper_stt_backend_en",
            "whisper_stt_backend_ko",
            "whisper_stt_backend_zh",
            "whisper_sentence_boundary_backend",
        ):
            widget = self._widgets.get(key)
            if widget is not None:
                widget.bind("<<ComboboxSelected>>", self._on_whisper_runtime_selection_changed)
        self._on_seg_backend_changed()
        self._sync_whisper_runtime_options()
        self._sync_whisper_translation_backend_options()
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
        return add_numeric_slider(
            self,
            parent,
            row,
            key,
            label,
            default,
            min_value,
            max_value,
            step=resolution,
            label_key=label_key,
        )

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
        effective_label_key = label_key or label
        check_btn = ttk.Checkbutton(parent, variable=var)
        if label_key is not None:
            self._register_localized_widget(check_btn, label_key, label)
        self._bool_switch_meta.append((check_btn, var, effective_label_key, label))
        self._update_bool_switch_text(check_btn, var, effective_label_key, label)
        var.trace_add(
            "write",
            lambda *_args, cb=check_btn, v=var, lk=effective_label_key, dl=label: self._update_bool_switch_text(cb, v, lk, dl),
        )
        check_btn.grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 2))
        self._widgets[key] = check_btn

    def _update_bool_switch_text(
        self,
        check_btn: ttk.Checkbutton,
        var: tk.BooleanVar,
        label_key: str,
        default_label: str,
    ) -> None:
        base = self._tr(label_key, default_label)
        state_on = self._tr("label.toggle_on", "ON")
        state_off = self._tr("label.toggle_off", "OFF")
        suffix = state_on if bool(var.get()) else state_off
        check_btn.config(text=f"{base} ({suffix})")

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
        whisper = whisper_defaults()
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
            "camera_server_enabled": True,
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
            "seg_opt_engine_path": _default_tensorrt_engine_path(),
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
            "whisper_enabled": whisper["enabled"],
            "whisper_input_device": _audio_default_input_device(),
            "whisper_backend": whisper["backend"],
            "whisper_model": whisper["model"],
            "whisper_stt_backend_en": whisper["sttBackendEn"],
            "whisper_stt_model_en": whisper["sttModelEn"],
            "whisper_stt_backend_ko": whisper["sttBackendKo"],
            "whisper_stt_model_ko": whisper["sttModelKo"],
            "whisper_stt_backend_zh": whisper["sttBackendZh"],
            "whisper_stt_model_zh": whisper["sttModelZh"],
            "whisper_language": _whisper_language_display_from_raw(whisper["language"]),
            "whisper_task": whisper["task"],
            "whisper_translation_enabled": whisper["translationEnabled"],
            "whisper_translation_backend": whisper["translationBackend"],
            "whisper_translation_target_language": _whisper_translation_target_display_from_raw(whisper["translationTargetLanguage"]),
            "whisper_translation_model": whisper["translationModel"],
            "whisper_translation_device": whisper["translationDevice"],
            "whisper_translation_compute_type": whisper["translationComputeType"],
            "whisper_translation_beam_size": whisper["translationBeamSize"],
            "whisper_translation_max_new_tokens": whisper["translationMaxNewTokens"],
            "whisper_device": whisper["device"],
            "whisper_compute_type": whisper["computeType"],
            "whisper_chunk_seconds": whisper["chunkSeconds"],
            "whisper_step_seconds": whisper["stepSeconds"],
            "whisper_window_seconds": whisper["windowSeconds"],
            "whisper_commit_lag_seconds": whisper["commitLagSeconds"],
            "whisper_beam_size": whisper["beamSize"],
            "whisper_max_new_tokens": whisper["maxNewTokens"],
            "whisper_temperature": whisper["temperature"],
            "whisper_sentence_boundary_backend": whisper["sentenceBoundaryBackend"],
            "whisper_sentence_boundary_model": whisper["sentenceBoundaryModel"],
            "whisper_sentence_boundary_backend_en": whisper["sentenceBoundaryBackendEn"],
            "whisper_sentence_boundary_model_en": whisper["sentenceBoundaryModelEn"],
            "whisper_sentence_boundary_backend_ko": whisper["sentenceBoundaryBackendKo"],
            "whisper_sentence_boundary_model_ko": whisper["sentenceBoundaryModelKo"],
            "whisper_sentence_boundary_backend_zh": whisper["sentenceBoundaryBackendZh"],
            "whisper_sentence_boundary_model_zh": whisper["sentenceBoundaryModelZh"],
            "whisper_sentence_boundary_device": whisper["sentenceBoundaryDevice"],
            "whisper_sentence_boundary_compute_type": whisper["sentenceBoundaryComputeType"],
        }

    def _create_virtual_camera(self) -> None:
        if platform.system() != "Linux":
            self._show_error(
                self._tr("title.virtual_camera", "Virtual camera"),
                self._tr(
                    "msg.virtual_camera_only_linux",
                    "Linux only: virtual camera can be created on Linux.",
                ),
            )
            return

        backend = self.vars.get("output_backend").get() if self.vars.get("output_backend") else ""
        if backend != "v4l2loopback":
            self._show_error(
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
            self._show_error(
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
            self._show_error(self._tr("title.virtual_camera", "Virtual camera"), str(exc))
            return

        ready, detail = _probe_v4l2_capture(
            device,
            retries=10,
            delay_sec=0.2,
            require_output=True,
        )
        if not ready:
            _log(f"가상 카메라 생성 후 상태 확인 실패: {detail}")
            self._show_error(
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
            self._show_error(
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
            self._show_error(self._tr("title.virtual_camera", "Virtual camera"), str(exc))
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

    def _refresh_audio_device_choices(
        self,
        *,
        select_input: str | None = None,
        select_output: str | None = None,
    ) -> None:
        self._refresh_audio_device_choice(
            "input",
            "audio_input_device",
            "_audio_input_display_to_raw",
            _audio_input_device_candidates,
            _audio_default_input_device,
            select_input,
        )
        self._refresh_audio_device_choice(
            "output",
            "audio_output_device",
            "_audio_output_display_to_raw",
            _audio_output_device_candidates,
            _audio_default_output_device,
            select_output,
        )

    def _refresh_audio_device_choice(
        self,
        kind: str,
        var_key: str,
        mapping_attr: str,
        candidates_fn: Callable[[], list[str]],
        default_fn: Callable[[], str],
        select_raw: str | None,
    ) -> None:
        widget = self._widgets.get(var_key)
        if not isinstance(widget, ttk.Combobox):
            return

        old_mapping = getattr(self, mapping_attr, {})
        current_display = self.vars[var_key].get().strip()
        current_raw = _audio_device_raw_from_display(current_display, old_mapping) if current_display else ""
        candidates = candidates_fn()
        default_raw = default_fn()
        available_raw = set(candidates)

        target_raw = (select_raw or current_raw or default_raw).strip()
        if not select_raw and target_raw not in available_raw:
            target_raw = default_raw

        for value in (default_raw, target_raw):
            if value and value not in candidates:
                candidates.append(value)

        display_values, display_to_raw = _audio_device_display_values(kind, candidates)
        target_display = next(
            (display for display, raw in display_to_raw.items() if raw == target_raw),
            target_raw,
        )
        if target_display and target_display not in display_values:
            display_values.append(target_display)
            display_to_raw[target_display] = target_raw

        setattr(self, mapping_attr, display_to_raw)
        widget["values"] = tuple(display_values)
        self.vars[var_key].set(target_display)

    def _create_virtual_speaker(self) -> None:
        if platform.system() != "Linux":
            self._show_error(
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
            self._show_error(self._tr("title.virtual_mic", "Virtual microphone"), str(exc))
            return
        _log(f"Virtual microphone sink created: {AUDIO_VIRTUAL_SINK_NAME}")
        self._refresh_audio_device_choices(
            select_input=AUDIO_VIRTUAL_SOURCE_NAME,
            select_output=AUDIO_VIRTUAL_SINK_NAME,
        )
        messagebox.showinfo(
            self._tr("title.virtual_mic", "Virtual microphone"),
            self._tr(
                "msg.virtual_mic_created",
                "Created virtual microphone sink: {name}. Use '{name}.monitor' in your meeting app input.",
            ).format(name=AUDIO_VIRTUAL_SINK_NAME),
        )

    def _remove_virtual_speaker(self) -> None:
        if platform.system() != "Linux":
            self._show_error(
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
            self._show_error(self._tr("title.virtual_mic", "Virtual microphone"), str(exc))
            return
        _log(f"Virtual microphone removed: {AUDIO_VIRTUAL_SINK_NAME}")
        self._refresh_audio_device_choices()
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
            "seg_opt_engine_path",
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

    def _reset_whisper_settings(self) -> None:
        defaults = self._build_video_defaults()
        for key in (
            "whisper_enabled",
            "whisper_input_device",
            "whisper_backend",
            "whisper_model",
            "whisper_language",
            "whisper_translation_enabled",
            "whisper_translation_backend",
            "whisper_translation_target_language",
            "whisper_translation_model",
            "whisper_translation_device",
            "whisper_translation_compute_type",
            "whisper_translation_beam_size",
            "whisper_translation_max_new_tokens",
            "whisper_device",
            "whisper_compute_type",
            "whisper_chunk_seconds",
            "whisper_step_seconds",
            "whisper_window_seconds",
            "whisper_commit_lag_seconds",
            "whisper_beam_size",
            "whisper_max_new_tokens",
            "whisper_temperature",
            "whisper_sentence_boundary_backend",
            "whisper_sentence_boundary_model",
            "whisper_sentence_boundary_device",
            "whisper_sentence_boundary_compute_type",
        ):
            self._set_var(key, defaults.get(key))
        self._sync_whisper_translation_backend_options()

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
        if isinstance(meta_cfg, dict):
            self._window_geometry_meta_cache = {
                str(key): str(value)
                for key, value in meta_cfg.items()
                if str(key).endswith("Geometry") and isinstance(value, str)
            }
        lang = str(meta_cfg.get("language", "")).strip().lower()
        if lang in {"ko", "en"}:
            self._language_var.set(lang)
        self._restore_window_geometry(meta_cfg)

        camera_server_cfg = raw.get("cameraServer") or raw.get("camera") or {}
        input_cfg = raw.get("inputCamera") or {}
        output_cfg = raw.get("outputCamera") or {}
        seg_cfg = raw.get("segmentation") or {}
        selfie_cfg = seg_cfg.get("selfie") or {}
        bg_cfg = raw.get("background") or {}
        crop_cfg = raw.get("crop") or {}
        audio_cfg = raw.get("audio") or {}
        face_cfg = raw.get("faceEnhance") or {}
        whisper_cfg = raw.get("whisper") or {}

        self._set_var("camera_server_enabled", camera_server_cfg.get("enabled", True))
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
        self._load_whisper_settings_from_config(whisper_cfg)
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

    def _load_whisper_settings_from_config(self, whisper_cfg: dict) -> None:
        defaults = self._build_video_defaults()
        self._set_var("whisper_enabled", whisper_cfg.get("enabled", defaults["whisper_enabled"]))
        raw_input_device = str(whisper_cfg.get("inputDevice", "")).strip() if isinstance(whisper_cfg.get("inputDevice"), str) else ""
        resolved_input_device = defaults["whisper_input_device"] if not raw_input_device else raw_input_device
        self._set_var("whisper_input_device", resolved_input_device)
        input_widget = self._widgets.get("whisper_input_device")
        if isinstance(input_widget, ttk.Combobox):
            input_values = list(input_widget["values"])
            input_display = next(
                (k for k, v in getattr(self, "_whisper_input_display_to_raw", {}).items() if v == resolved_input_device),
                resolved_input_device,
            )
            if input_display not in input_values:
                input_widget["values"] = tuple(input_values + [input_display])
                getattr(self, "_whisper_input_display_to_raw", {})[input_display] = resolved_input_device
            self.vars["whisper_input_device"].set(input_display)
        self._set_var("whisper_backend", whisper_cfg.get("backend", defaults["whisper_backend"]))
        self._set_var("whisper_model", whisper_cfg.get("model", defaults["whisper_model"]))
        self._set_var("whisper_stt_backend_en", whisper_cfg.get("sttBackendEn", defaults["whisper_stt_backend_en"]))
        self._set_var("whisper_stt_model_en", whisper_cfg.get("sttModelEn", defaults["whisper_stt_model_en"]))
        self._set_var("whisper_stt_backend_ko", whisper_cfg.get("sttBackendKo", defaults["whisper_stt_backend_ko"]))
        self._set_var("whisper_stt_model_ko", whisper_cfg.get("sttModelKo", defaults["whisper_stt_model_ko"]))
        self._set_var("whisper_stt_backend_zh", whisper_cfg.get("sttBackendZh", defaults["whisper_stt_backend_zh"]))
        self._set_var("whisper_stt_model_zh", whisper_cfg.get("sttModelZh", defaults["whisper_stt_model_zh"]))
        self._set_var(
            "whisper_language",
            _whisper_language_display_from_raw(whisper_cfg.get("language", _whisper_language_raw_from_display(defaults["whisper_language"]))),
        )
        legacy_translation_enabled = whisper_cfg.get("task") == "translate"
        self._set_var(
            "whisper_translation_enabled",
            whisper_cfg.get("translationEnabled", legacy_translation_enabled or defaults["whisper_translation_enabled"]),
        )
        self._set_var("whisper_translation_backend", whisper_cfg.get("translationBackend", defaults["whisper_translation_backend"]))
        self._set_var(
            "whisper_translation_target_language",
            _whisper_translation_target_display_from_raw(
                whisper_cfg.get(
                    "translationTargetLanguage",
                    _whisper_translation_target_raw_from_display(defaults["whisper_translation_target_language"]),
                )
            ),
        )
        self._set_var("whisper_translation_model", whisper_cfg.get("translationModel", defaults["whisper_translation_model"]))
        self._set_var("whisper_translation_device", whisper_cfg.get("translationDevice", defaults["whisper_translation_device"]))
        self._set_var("whisper_translation_compute_type", whisper_cfg.get("translationComputeType", defaults["whisper_translation_compute_type"]))
        self._set_var("whisper_translation_beam_size", whisper_cfg.get("translationBeamSize", defaults["whisper_translation_beam_size"]))
        self._set_var("whisper_translation_max_new_tokens", whisper_cfg.get("translationMaxNewTokens", defaults["whisper_translation_max_new_tokens"]))
        self._set_var("whisper_device", whisper_cfg.get("device", defaults["whisper_device"]))
        self._set_var("whisper_compute_type", whisper_cfg.get("computeType", defaults["whisper_compute_type"]))
        window_seconds = whisper_cfg.get("windowSeconds", whisper_cfg.get("chunkSeconds", defaults["whisper_window_seconds"]))
        self._set_var("whisper_chunk_seconds", window_seconds)
        self._set_var("whisper_step_seconds", whisper_cfg.get("stepSeconds", defaults["whisper_step_seconds"]))
        self._set_var("whisper_window_seconds", window_seconds)
        self._set_var("whisper_commit_lag_seconds", whisper_cfg.get("commitLagSeconds", defaults["whisper_commit_lag_seconds"]))
        self._set_var("whisper_beam_size", whisper_cfg.get("beamSize", defaults["whisper_beam_size"]))
        self._set_var("whisper_max_new_tokens", whisper_cfg.get("maxNewTokens", defaults["whisper_max_new_tokens"]))
        self._set_var("whisper_temperature", whisper_cfg.get("temperature", defaults["whisper_temperature"]))
        self._set_var("whisper_sentence_boundary_backend", whisper_cfg.get("sentenceBoundaryBackend", defaults["whisper_sentence_boundary_backend"]))
        self._set_var("whisper_sentence_boundary_model", whisper_cfg.get("sentenceBoundaryModel", defaults["whisper_sentence_boundary_model"]))
        self._set_var("whisper_sentence_boundary_device", whisper_cfg.get("sentenceBoundaryDevice", defaults["whisper_sentence_boundary_device"]))
        self._set_var("whisper_sentence_boundary_compute_type", whisper_cfg.get("sentenceBoundaryComputeType", defaults["whisper_sentence_boundary_compute_type"]))
        self._sync_whisper_runtime_options()
        self._sync_whisper_translation_backend_options()

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
            normalizer = self._slider_normalizers.get(key)
            if normalizer is not None:
                float_value = normalizer(float_value)
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
            normalizer = self._slider_normalizers.get(key)
            if normalizer is not None:
                int_value = int(round(normalizer(int_value)))
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
            self._apply_persistent_meta(config)
            write_config(self.output_path, config)
            messagebox.showinfo(
                self._tr("msg.saved.title", "Saved"),
                self._tr("msg.saved.body", "Config saved to {path}").format(path=self.output_path),
            )
        except Exception as exc:
            _log(f"Validation error: {exc}")
            self._show_error(self._tr("msg.validation_error.title", "Validation error"), str(exc))

    def _auto_tune_audio_gate(self):
        if sd is None:
            self._show_error(
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
            self._show_error(
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
            self._restore_named_window_geometry(self._audio_tune_window, "audioTuneWindowGeometry")
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
            self._remember_named_window_geometry("audioTuneWindowGeometry", self._audio_tune_window)
            try:
                self._audio_tune_window.destroy()
            except Exception:
                pass
        self._audio_tune_window = None

    def _run_audio_gate_test(self):
        try:
            config = self._build_config()
        except Exception as exc:
            _log(f"audio gate test error: {exc}")
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
            _log(
                "audio gate test error: "
                + self._tr("msg.audio_gate_test_invalid_config", "Invalid gate config: {error}").format(error=exc)
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
            _log(
                "audio gate test error: "
                + self._tr(
                    "msg.audio_gate_test_sounddevice_missing",
                    "sounddevice module is missing. Run ./bin/avc setup and try again.",
                )
            )
            return

        window = tk.Toplevel(self.root)
        window.title(self._tr("title.audio_gate_test", "Audio gate test"))
        window.geometry("640x480")
        self._restore_named_window_geometry(window, "audioGateTestWindowGeometry")
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
            self._remember_named_window_geometry("audioGateTestWindowGeometry", window)
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
            _log(
                "audio gate test error: "
                + self._tr("msg.audio_gate_test_open_stream_failed", "Failed to open input stream: {error}").format(error=exc)
            )
            return

        if opened_sample_rate != int(sample_rate):
            summary_var.set(
                self._tr(
                    "audio_input_meter.sample_rate_adjusted",
                    "Opened with supported sample rate: {sample_rate}Hz",
                ).format(sample_rate=opened_sample_rate)
            )

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
            self._show_error(self._tr("title.audio_input_meter_error", "Input dB meter error"), str(exc))
            return

        audio_cfg = config.get("audio") or {}
        input_device_requested = audio_cfg.get("inputDevice")
        if not isinstance(input_device_requested, str) or not input_device_requested.strip():
            input_device_requested = _audio_default_input_device()
        self._run_input_meter(
            title_key="title.audio_input_meter",
            title_default="Microphone input dB meter",
            error_title_key="title.audio_input_meter_error",
            error_title_default="Input dB meter error",
            input_device_requested=input_device_requested,
            sample_rate=int(audio_cfg.get("sampleRate", 48000)),
            frame_ms=int(audio_cfg.get("frameMs", 20)),
            channels=max(1, int(audio_cfg.get("channels", 1))),
        )

    def _run_whisper_input_meter(self):
        try:
            config = self._build_config(validate_audio=False)
        except Exception as exc:
            self._show_error(self._tr("title.whisper_input_meter_error", "Whisper input meter error"), str(exc))
            return

        whisper_cfg = config.get("whisper") or {}
        input_device_requested = whisper_cfg.get("inputDevice")
        if not isinstance(input_device_requested, str) or not input_device_requested.strip():
            input_device_requested = _audio_default_input_device()
        self._run_input_meter(
            title_key="title.whisper_input_meter",
            title_default="Whisper input dB meter",
            error_title_key="title.whisper_input_meter_error",
            error_title_default="Whisper input meter error",
            input_device_requested=input_device_requested,
            sample_rate=48000,
            frame_ms=20,
            channels=1,
            sample_rate_candidates=(48000, 44100, 16000),
            prefer_exact_pulse_source=True,
        )

    def _run_input_meter(
        self,
        *,
        title_key: str,
        title_default: str,
        error_title_key: str,
        error_title_default: str,
        input_device_requested: str,
        sample_rate: int,
        frame_ms: int,
        channels: int,
        sample_rate_candidates: tuple[int, ...] | None = None,
        prefer_exact_pulse_source: bool = False,
    ):
        input_device = str(input_device_requested).strip()
        use_exact_pulse_source = prefer_exact_pulse_source and _can_capture_exact_pulse_source(input_device)
        if not use_exact_pulse_source:
            input_device = _coerce_audio_input_device_for_sounddevice(input_device_requested)
        candidate_rates = tuple(sample_rate_candidates or (sample_rate,))
        capture_backend = "pulse-recorder" if use_exact_pulse_source else "sounddevice"
        _log(
            "input meter requested: "
            f"title={title_default!r} configured='{input_device_requested}' runtime='{input_device}' "
            f"backend={capture_backend} sample_rates={candidate_rates} frame_ms={frame_ms} channels={channels}"
        )

        if sd is None and not use_exact_pulse_source:
            _log(
                "input meter failed all attempts: "
                f"configured='{input_device_requested}' runtime='{input_device}' backend={capture_backend} "
                f"sample_rates={candidate_rates} error={exc}"
            )
            self._show_error(
                self._tr(error_title_key, error_title_default),
                self._tr(
                    "msg.audio_input_meter_sounddevice_missing",
                    "sounddevice module is missing. Run ./bin/avc setup and try again.",
                ),
            )
            return

        window = tk.Toplevel(self.root)
        window.title(self._tr(title_key, title_default))
        window.geometry("640x480")
        self._restore_named_window_geometry(window, "inputMeterWindowGeometry")
        window.minsize(640, 480)
        window.resizable(True, True)
        window.grab_set()

        content = ttk.Frame(window, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)

        ttk.Label(content, text=self._tr(title_key, title_default), font=("Arial", 12, "bold")).grid(
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
            self._remember_named_window_geometry("inputMeterWindowGeometry", window)
            self._stop_audio_input_meter()
            if window.winfo_exists():
                window.destroy()

        stop_btn.configure(command=close_window)
        window.protocol("WM_DELETE_WINDOW", close_window)

        stream = None
        stream_error: Exception | None = None
        opened_sample_rate = int(sample_rate)
        if use_exact_pulse_source:
            for candidate_rate in candidate_rates:
                try:
                    opened_sample_rate = int(candidate_rate)
                    _log(
                        "input meter open attempt: "
                        f"backend=pulse-recorder source='{input_device}' sample_rate={opened_sample_rate}"
                    )
                    self._start_pulse_input_meter_process(
                        input_device,
                        sample_rate=opened_sample_rate,
                        frame_ms=frame_ms,
                        channels=channels,
                    )
                    stream = self._audio_input_meter_process
                    _log(
                        "input meter open success: "
                        f"backend=pulse-recorder source='{input_device}' sample_rate={opened_sample_rate}"
                    )
                    break
                except Exception as exc:
                    _log(
                        "input meter open failed: "
                        f"backend=pulse-recorder source='{input_device}' sample_rate={candidate_rate} error={exc}"
                    )
                    stream_error = exc
                    self._audio_input_meter_process = None
        else:
            for candidate_rate in candidate_rates:
                try:
                    opened_sample_rate = int(candidate_rate)
                    frame_samples = max(1, int(opened_sample_rate * frame_ms / 1000))
                    _log(
                        "input meter open attempt: "
                        f"backend=sounddevice device='{input_device}' sample_rate={opened_sample_rate}"
                    )
                    stream = sd.InputStream(
                        device=input_device,
                        channels=channels,
                        samplerate=opened_sample_rate,
                        blocksize=frame_samples,
                        dtype="float32",
                        callback=self._audio_input_meter_callback,
                    )
                    self._audio_input_meter_stream = stream
                    stream.start()
                    _log(
                        "input meter open success: "
                        f"backend=sounddevice device='{input_device}' sample_rate={opened_sample_rate}"
                    )
                    break
                except Exception as exc:
                    _log(
                        "input meter open failed: "
                        f"backend=sounddevice device='{input_device}' sample_rate={candidate_rate} error={exc}"
                    )
                    stream_error = exc
                    stream = None
                    self._audio_input_meter_stream = None
        if stream is None:
            exc = stream_error or RuntimeError("failed to open input stream")
            available = _available_input_meter_devices()
            self._stop_audio_input_meter()
            window.destroy()
            self._show_error(
                self._tr(error_title_key, error_title_default),
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

    def _start_pulse_input_meter_process(self, source_name: str, *, sample_rate: int, frame_ms: int, channels: int) -> None:
        recorder = shutil.which("parec") or shutil.which("parecord")
        if recorder is None:
            raise RuntimeError("parec/parecord command not found. Install pulseaudio-utils or pipewire-pulse tools.")
        frame_samples = max(1, int(sample_rate * frame_ms / 1000))
        bytes_per_frame = frame_samples * max(1, int(channels)) * 2
        cmd = [
            recorder,
            "--device",
            source_name,
            "--format=s16le",
            "--rate",
            str(sample_rate),
            "--channels",
            str(channels),
            "--raw",
        ]
        _log("input meter pulse recorder spawn: " + " ".join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._audio_input_meter_process = process

        def read_loop() -> None:
            _log(f"input meter pulse recorder reader started: pid={process.pid} source='{source_name}'")
            assert process.stdout is not None
            while self._audio_input_meter_running and process.poll() is None:
                data = process.stdout.read(bytes_per_frame)
                if not data:
                    break
                try:
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    if channels > 1:
                        samples = samples.reshape(-1, channels).mean(axis=1)
                    level_db = self._rms_dbfs(samples)
                    with self._audio_input_meter_lock:
                        self._audio_input_meter_queue.append(level_db)
                except Exception as exc:
                    self._audio_input_meter_error = str(exc)
                    break
            if process.poll() not in (None, 0) and self._audio_input_meter_running:
                stderr = ""
                try:
                    stderr = (process.stderr.read() if process.stderr is not None else b"").decode(errors="replace").strip()
                except Exception:
                    stderr = ""
                self._audio_input_meter_error = stderr or f"recorder exited with code {process.returncode}"
                _log(
                    "input meter pulse recorder reader failed: "
                    f"pid={process.pid} code={process.returncode} error={self._audio_input_meter_error}"
                )
            else:
                _log(f"input meter pulse recorder reader stopped: pid={process.pid} code={process.poll()}")

        self._audio_input_meter_reader_thread = threading.Thread(target=read_loop, daemon=True)
        self._audio_input_meter_reader_thread.start()

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
        _log("input meter stopping")
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
        process = self._audio_input_meter_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self._audio_input_meter_stream = None
        self._audio_input_meter_process = None
        self._audio_input_meter_reader_thread = None
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
                self._show_error(
                    self._tr("title.audio_tune_error", "Audio tuning error"),
                    self._tr("msg.audio_tune_capture_failed", "Microphone capture failed:\n{error}").format(error=exc),
                )
            return None
        if data is None or len(data) == 0:
            if show_error:
                self._show_error(
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
        try:
            config_path = Path(self.output_path).expanduser()
            if config_path.exists():
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._restore_preview_window_geometry(window, raw.get("meta") or {})
        except Exception as exc:
            _log(f"Preview window geometry restore failed: {exc}")
        window.protocol("WM_DELETE_WINDOW", self._stop_preview)
        window.bind("<Configure>", self._on_preview_configure)
        canvas = tk.Canvas(window, bg="#111111", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        self._preview_window = window
        self._preview_canvas = canvas
        self._preview_canvas_image_id = None
        self._preview_tk_image = None

    def _destroy_preview_window(self) -> None:
        self._capture_all_window_geometry_meta()
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
        self._show_error(self._tr("title.preview_error", "Preview error"), message)

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
            "seg_opt_engine_path": "enginePath",
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

    def _on_whisper_runtime_selection_changed(self, _event=None) -> None:
        self._sync_whisper_runtime_options()
        self._sync_whisper_translation_backend_options()

    def _grid_rows(self, parent, rows: list[int], visible: bool) -> None:
        if parent is None:
            return
        target_rows = set(rows)
        cache = getattr(self, "_grid_row_cache", None)
        if cache is None:
            cache = {}
            self._grid_row_cache = cache
        try:
            children = parent.winfo_children()
        except Exception:
            children = parent.grid_slaves()
        for child in children:
            try:
                grid_info = child.grid_info()
            except Exception:
                continue
            if grid_info.get("row") not in (None, ""):
                try:
                    cache[child] = int(grid_info.get("row", -1))
                except Exception:
                    pass
            row = cache.get(child)
            if row not in target_rows:
                continue
            if visible:
                child.grid()
            else:
                child.grid_remove()

    def _set_combobox_values_for_backend(self, key: str, values: list[str]) -> None:
        widget = self._widgets.get(key)
        var = self.vars.get(key)
        if widget is not None:
            widget["values"] = tuple(values)
        if var is not None and values and var.get().strip() not in values:
            var.set(values[0])

    def _sync_whisper_runtime_options(self) -> None:
        language_var = self.vars.get("whisper_language")
        selected_language = _whisper_language_raw_from_display(language_var.get()) if language_var is not None else "en"
        if selected_language not in {"en", "ko", "zh"}:
            selected_language = "en"
        global_stt_parent = getattr(self, "_whisper_global_stt_parent", getattr(self, "_whisper_tab", None))
        for row in getattr(self, "_whisper_global_stt_rows", []):
            self._grid_rows(global_stt_parent, [row], False)

        stt_frame = getattr(self, "_whisper_stt_frame", None)
        if stt_frame is not None:
            stt_frame.grid()
        for lang, rows in getattr(self, "_whisper_stt_language_rows", {}).items():
            self._grid_rows(stt_frame, rows, lang == selected_language)

        manual_boundary_parent = getattr(self, "_whisper_manual_boundary_parent", getattr(self, "_whisper_tab", None))
        for row in getattr(self, "_whisper_manual_boundary_rows", []):
            self._grid_rows(manual_boundary_parent, [row], True)

        active_stt_backend = "faster-whisper"
        for lang in ("en", "ko", "zh"):
            stt_backend_key = f"whisper_stt_backend_{lang}"
            stt_model_key = f"whisper_stt_model_{lang}"
            stt_backend_widget = self._widgets.get(stt_backend_key)
            stt_backend_var = self.vars.get(stt_backend_key)
            stt_backend_values = _whisper_stt_backend_options(lang)
            if stt_backend_widget is not None:
                stt_backend_widget["values"] = tuple(stt_backend_values)
            if stt_backend_var is not None and stt_backend_var.get().strip() not in stt_backend_values:
                stt_backend_var.set(stt_backend_values[0])
            stt_backend = stt_backend_var.get().strip() if stt_backend_var is not None else "faster-whisper"
            self._set_combobox_values_for_backend(
                stt_model_key,
                _whisper_stt_model_options(stt_backend, lang),
            )
            if lang == selected_language:
                active_stt_backend = stt_backend

        active_boundary_backend_key = "whisper_sentence_boundary_backend"
        active_boundary_model_key = "whisper_sentence_boundary_model"
        active_boundary_backend_var = self.vars.get(active_boundary_backend_key)
        active_boundary_backend = active_boundary_backend_var.get().strip() if active_boundary_backend_var is not None else "sat"
        self._set_combobox_values_for_backend(
            active_boundary_model_key,
            _whisper_sentence_boundary_model_options(active_boundary_backend),
        )

        active_stt_option_keys = set(_whisper_stt_backend_runtime_option_keys(active_stt_backend))
        backend_option_parent = getattr(self, "_whisper_backend_option_parent", getattr(self, "_whisper_tab", None))
        for option_key, row in getattr(self, "_whisper_backend_option_rows", {}).items():
            self._grid_rows(backend_option_parent, [row], option_key in active_stt_option_keys)

        self._schedule_update_scrollbar_state()

    def _on_whisper_translation_backend_changed(self, _event=None) -> None:
        self._sync_whisper_translation_backend_options()

    def _sync_whisper_translation_backend_options(self) -> None:
        language_var = self.vars.get("whisper_language")
        language_display = language_var.get().strip() if language_var is not None else "en"
        language = _whisper_language_raw_from_display(language_display)
        backend_var = self.vars.get("whisper_translation_backend")
        backend = backend_var.get().strip() if backend_var is not None else "whisper"
        backend_options = _whisper_translation_backend_options(language)
        backend_widget = self._widgets.get("whisper_translation_backend")
        if backend_widget is not None:
            backend_widget["values"] = tuple(backend_options)
        if backend not in backend_options:
            backend = backend_options[0] if backend_options else "whisper"
            self._set_var("whisper_translation_backend", backend)

        frames = getattr(self, "_whisper_translation_backend_frames", {})
        selected_frame = frames.get(backend)
        seen_frame_ids: set[int] = set()
        for frame in frames.values():
            frame_id = id(frame)
            if frame_id in seen_frame_ids:
                continue
            seen_frame_ids.add(frame_id)
            if frame is selected_frame:
                frame.grid()
            else:
                frame.grid_remove()

        target_options = _whisper_translation_target_options_for_backend(language, backend)
        target_widget = self._widgets.get("whisper_translation_target_language")
        if target_widget is not None:
            target_widget["values"] = tuple(target_options)
        target_var = self.vars.get("whisper_translation_target_language")
        target_display = target_var.get().strip() if target_var is not None else ""
        if target_options and target_display not in target_options:
            self._set_var("whisper_translation_target_language", target_options[0])

        model_options = _whisper_translation_model_options(backend)
        self._set_combobox_values_for_backend("whisper_translation_model", model_options)

        if backend == "whisper":
            self._set_var("whisper_translation_target_language", _whisper_translation_target_display_from_raw("en"))
        elif backend in {"nllb-transformers", "m2m100-transformers"}:
            self._set_var("whisper_translation_device", "cuda")
            compute_var = self.vars.get("whisper_translation_compute_type")
            compute_type = compute_var.get().strip() if compute_var is not None else ""
            if compute_type not in {"float16", "float32"}:
                self._set_var("whisper_translation_compute_type", "float16")

        self._schedule_update_scrollbar_state()

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
        if "enginePath" in allowed:
            engine_path = self.vars["seg_opt_engine_path"].get().strip()
            if engine_path:
                options["enginePath"] = engine_path
        return options

    def _apply_seg_engine_options_to_form(self, options: dict[str, object]) -> None:
        mapping = (
            ("seg_opt_model_blend", "modelBlend"),
            ("seg_opt_temporal_alpha", "temporalAlpha"),
            ("seg_opt_mask_blur", "maskBlur"),
            ("seg_opt_morph_open", "morphOpen"),
            ("seg_opt_morph_close", "morphClose"),
            ("seg_opt_mask_gamma", "maskGamma"),
            ("seg_opt_engine_path", "enginePath"),
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

        if validate_audio:
            raw_audio_input, raw_audio_output = _resolve_and_validate_audio_runtime_devices(
                iv["audio_input_device"].get(),
                iv["audio_output_device"].get(),
                getattr(self, "_audio_input_display_to_raw", {}),
                getattr(self, "_audio_output_display_to_raw", {}),
            )
        else:
            raw_audio_input = _audio_device_raw_from_display(
                iv["audio_input_device"].get().strip(),
                getattr(self, "_audio_input_display_to_raw", {}),
            )
            raw_audio_output = _audio_device_raw_from_display(
                iv["audio_output_device"].get().strip(),
                getattr(self, "_audio_output_display_to_raw", {}),
            )
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
            camera_server_enabled=self._parse_bool(iv["camera_server_enabled"].get()),
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
            whisper_enabled=self._parse_bool(iv["whisper_enabled"].get()),
            whisper_input_device=_audio_device_raw_from_display(
                iv["whisper_input_device"].get().strip(),
                getattr(self, "_whisper_input_display_to_raw", {}),
            ),
            whisper_backend=iv["whisper_backend"].get().strip(),
            whisper_model=iv["whisper_model"].get().strip(),
            whisper_stt_backend_en=iv["whisper_stt_backend_en"].get().strip(),
            whisper_stt_model_en=iv["whisper_stt_model_en"].get().strip(),
            whisper_stt_backend_ko=iv["whisper_stt_backend_ko"].get().strip(),
            whisper_stt_model_ko=iv["whisper_stt_model_ko"].get().strip(),
            whisper_stt_backend_zh=iv["whisper_stt_backend_zh"].get().strip(),
            whisper_stt_model_zh=iv["whisper_stt_model_zh"].get().strip(),
            whisper_language=_whisper_language_raw_from_display(iv["whisper_language"].get()),
            whisper_task="transcribe",
            whisper_translation_enabled=self._parse_bool(iv["whisper_translation_enabled"].get()),
            whisper_translation_backend=iv["whisper_translation_backend"].get().strip(),
            whisper_translation_target_language=_whisper_translation_target_raw_from_display(
                iv["whisper_translation_target_language"].get()
            ),
            whisper_translation_model=iv["whisper_translation_model"].get().strip(),
            whisper_translation_device=iv["whisper_translation_device"].get().strip(),
            whisper_translation_compute_type=iv["whisper_translation_compute_type"].get().strip(),
            whisper_translation_beam_size=int(round(float(iv["whisper_translation_beam_size"].get()))),
            whisper_translation_max_new_tokens=int(round(float(iv["whisper_translation_max_new_tokens"].get()))),
            whisper_device=iv["whisper_device"].get().strip(),
            whisper_compute_type=iv["whisper_compute_type"].get().strip(),
            whisper_chunk_seconds=float(iv["whisper_window_seconds"].get()),
            whisper_step_seconds=float(iv["whisper_step_seconds"].get()),
            whisper_window_seconds=float(iv["whisper_window_seconds"].get()),
            whisper_commit_lag_seconds=float(iv["whisper_commit_lag_seconds"].get()),
            whisper_beam_size=int(round(float(iv["whisper_beam_size"].get()))),
            whisper_max_new_tokens=int(round(float(iv["whisper_max_new_tokens"].get()))),
            whisper_temperature=float(iv["whisper_temperature"].get()),
            whisper_post_processing_profile=whisper_default("postProcessingProfile"),
            whisper_sentence_boundary_backend=iv["whisper_sentence_boundary_backend"].get().strip(),
            whisper_sentence_boundary_model=iv["whisper_sentence_boundary_model"].get().strip(),
            whisper_sentence_boundary_backend_en=whisper_default("sentenceBoundaryBackendEn"),
            whisper_sentence_boundary_model_en=whisper_default("sentenceBoundaryModelEn"),
            whisper_sentence_boundary_backend_ko=whisper_default("sentenceBoundaryBackendKo"),
            whisper_sentence_boundary_model_ko=whisper_default("sentenceBoundaryModelKo"),
            whisper_sentence_boundary_backend_zh=whisper_default("sentenceBoundaryBackendZh"),
            whisper_sentence_boundary_model_zh=whisper_default("sentenceBoundaryModelZh"),
            whisper_sentence_boundary_device=iv["whisper_sentence_boundary_device"].get().strip(),
            whisper_sentence_boundary_compute_type=iv["whisper_sentence_boundary_compute_type"].get().strip(),
        )


def parse_args():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        parser = argparse.ArgumentParser(description="Validate ai-virtual-cam config")
        parser.add_argument("command", choices=["check"])
        parser.add_argument("--output", "--config", dest="output", default="~/.avc/setting.json")
        return parser.parse_args()

    if len(sys.argv) > 1 and sys.argv[1] == "gui":
        sys.argv.pop(1)

    parser = argparse.ArgumentParser(description="GUI config generator for ai-virtual-cam")
    parser.add_argument("--output", default="~/.avc/setting.json")
    parser.add_argument("--lang", choices=["ko", "en"], default="ko")
    return parser.parse_args()


def _run_check(output_path: str) -> int:
    from src.domain.config import AppConfig

    config_path = Path(output_path).expanduser()
    config = AppConfig.load(config_path)
    print(
        "[avc] config check ok: "
        f"path={config_path} "
        f"whisper.enabled={config.whisper.enabled} "
        f"whisper.input={config.whisper.inputDevice} "
        f"whisper.backend={config.whisper.backend} "
        f"whisper.model={config.whisper.model}",
        flush=True,
    )
    return 0


def main() -> int:
    args = parse_args()
    if getattr(args, "command", "") == "check":
        return _run_check(args.output)

    if TK_IMPORT_ERROR is not None:
        print(
            "Tkinter is not available in this Python runtime.\n"
            "To use GUI on macOS, install a Python build with Tk support.\n"
            "If GUI is unavailable, edit ~/.avc/setting.json directly.",
            file=sys.stderr,
        )
        return 2

    root = tk.Tk()
    ConfigGui(root, args.output, args.lang)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

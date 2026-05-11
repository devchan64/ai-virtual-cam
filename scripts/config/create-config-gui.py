#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import cv2
import platform
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


def _segmentation_backend_options():
    if platform.system() == "Darwin":
        return ["selfie", "mock", "onnxruntime"]
    return ["selfie", "mock", "onnxruntime", "tensorrt"]


def _output_backend_options():
    if platform.system() == "Darwin":
        return ["pyvirtualcam", "opencv"]
    return ["v4l2loopback", "opencv"]


class ConfigGui:
    def __init__(self, root: tk.Tk, output_path: str) -> None:
        self.root = root
        self.output_path = output_path
        self.root.title("ai-virtual-cam config GUI")
        self.vars: dict[str, tk.Variable] = {}
        self._preview_active = False
        self._preview_capture = None
        self._preview_processor = None
        self._preview_processing_signature = None
        self._preview_out_size = (0, 0)
        self._preview_window_name = "ai-virtual-cam preview (press q or esc to close)"
        self._widgets: dict[str, object] = {}
        self._input_modes: list[tuple[int, int, str]] = []
        self._build_form()
        self._load_existing_config()

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(frame)
        notebook.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

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
        self._add_combo(tab_io, row, "input_height", "Input height", height_values, default_h, col_offset=2)
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
        default_output_device = "virtual-cam" if is_macos else "/dev/video10"
        self._add_text(tab_io, row, "output_device", "Output path", default_output_device)
        row += 1
        self._add_int(tab_io, row, "output_width", "Output width", 1280)
        self._add_int(tab_io, row, "output_height", "Output height", 720, col_offset=2)
        row += 1
        self._add_int(tab_io, row, "output_fps", "Output FPS", 30)

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
        self._add_combo(tab_audio, row, "audio_enabled", "Audio mixer", ["false", "true"], "false")
        row += 1
        self._add_text(tab_audio, row, "audio_input_device", "Input device", "default")
        self._add_text(tab_audio, row, "audio_output_device", "Output device", "default", col_offset=2)
        row += 1
        self._add_int(tab_audio, row, "audio_sample_rate", "Sample rate", 48000)
        self._add_int(tab_audio, row, "audio_channels", "Channels", 1, col_offset=2)
        row += 1
        self._add_int(tab_audio, row, "audio_frame_ms", "Frame ms", 20)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_threshold_db", "Gate threshold dB", -42.0, -80.0, 0.0, resolution=0.5)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_hysteresis_db", "Gate hysteresis dB", 3.0, 0.0, 20.0, resolution=0.5)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_min_voice_band_ratio", "Min voice band ratio", 0.55, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_attack_ms", "Gate attack ms", 20, 0, 500, resolution=1)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_hold_ms", "Gate hold ms", 140, 0, 2000, resolution=1)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_release_ms", "Gate release ms", 220, 0, 2000, resolution=1)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_open_gain", "Gate open gain", 1.0, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(tab_audio, row, "audio_gate_closed_gain", "Gate closed gain", 0.0, 0.0, 1.0, resolution=0.01)
        row += 1
        ttk.Button(tab_audio, text="게이트 자동 튜닝", command=self._auto_tune_audio_gate).grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0)
        )

        action_row = 1
        action = ttk.Frame(frame)
        action.grid(row=action_row, column=0, sticky="ew", pady=(10, 0))
        action.columnconfigure(0, weight=1)
        action.columnconfigure(1, weight=1)
        ttk.Button(action, text="Preview", command=self._preview).grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Button(action, text="Save JSON", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)
        input_device_widget = self._widgets.get("input_device")
        if input_device_widget is not None:
            input_device_widget.bind("<<ComboboxSelected>>", self._on_input_device_changed)
        input_width_widget = self._widgets.get("input_width")
        if input_width_widget is not None:
            input_width_widget.bind("<<ComboboxSelected>>", self._on_input_width_changed)
        input_height_widget = self._widgets.get("input_height")
        if input_height_widget is not None:
            input_height_widget.bind("<<ComboboxSelected>>", self._on_input_height_changed)

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

    def _add_combo(self, parent, row, key, label, values, default, readonly=False, col_offset=0):
        ttk.Label(parent, text=label).grid(row=row, column=col_offset, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        state = "disabled" if readonly else "readonly"
        combo = ttk.Combobox(parent, textvariable=var, values=values, state=state)
        span = 3 if col_offset == 0 else 1
        combo.grid(row=row, column=col_offset + 1, columnspan=span, sticky="ew", padx=4)
        self._widgets[key] = combo

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

    def _pick_bg_image(self):
        selected = filedialog.askopenfilename(title="Select background image")
        if selected:
            self.vars["bg_image"].set(selected)

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
        gate_cfg = audio_cfg.get("gate") or {}

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
        self._set_var("audio_enabled", str(bool(audio_cfg.get("enabled", False))).lower())
        self._set_var("audio_input_device", audio_cfg.get("inputDevice"))
        self._set_var("audio_output_device", audio_cfg.get("outputDevice"))
        self._set_var("audio_sample_rate", audio_cfg.get("sampleRate"))
        self._set_var("audio_channels", audio_cfg.get("channels"))
        self._set_var("audio_frame_ms", audio_cfg.get("frameMs"))
        self._set_var("audio_gate_threshold_db", gate_cfg.get("thresholdDb"))
        self._set_var("audio_gate_hysteresis_db", gate_cfg.get("hysteresisDb"))
        self._set_var("audio_gate_min_voice_band_ratio", gate_cfg.get("minVoiceBandRatio"))
        self._set_var("audio_gate_attack_ms", gate_cfg.get("attackMs"))
        self._set_var("audio_gate_hold_ms", gate_cfg.get("holdMs"))
        self._set_var("audio_gate_release_ms", gate_cfg.get("releaseMs"))
        self._set_var("audio_gate_open_gain", gate_cfg.get("openGain"))
        self._set_var("audio_gate_closed_gain", gate_cfg.get("closedGain"))
        self._on_input_device_changed()
        self._on_input_width_changed()

    def _set_var(self, key: str, value):
        if value is None:
            return
        var = self.vars.get(key)
        if var is None:
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
        try:
            sample_rate = int(self.vars["audio_sample_rate"].get())
            channels = int(self.vars["audio_channels"].get())
        except Exception:
            messagebox.showerror("Audio tuning error", "audio sample rate/channels 값이 올바르지 않습니다.")
            return
        if channels <= 0:
            channels = 1

        messagebox.showinfo(
            "게이트 자동 튜닝 1/2",
            "2초 동안 조용히 있어 주세요.\n(배경 소음 기준 측정)",
        )
        ambient = self._record_audio_block(seconds=2.0, sample_rate=sample_rate, channels=channels)
        if ambient is None:
            return

        messagebox.showinfo(
            "게이트 자동 튜닝 2/2",
            "3초 동안 평소 회의 톤으로 말해 주세요.\n(음성 기준 측정)",
        )
        speech = self._record_audio_block(seconds=3.0, sample_rate=sample_rate, channels=channels)
        if speech is None:
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

        messagebox.showinfo(
            "게이트 자동 튜닝 완료",
            "추천값을 반영했습니다.\n"
            f"- thresholdDb: {threshold_db:.1f}\n"
            f"- hysteresisDb: {hysteresis_db:.1f}\n"
            f"- minVoiceBandRatio: {min_voice_ratio:.2f}",
        )

    def _record_audio_block(self, seconds: float, sample_rate: int, channels: int):
        try:
            frames = max(1, int(seconds * sample_rate))
            data = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
            sd.wait()
        except Exception as exc:
            messagebox.showerror("Audio tuning error", f"마이크 입력 측정 실패:\n{exc}")
            return None
        if data is None or len(data) == 0:
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
            audio_enabled=iv["audio_enabled"].get().strip().lower() == "true",
            audio_input_device=iv["audio_input_device"].get().strip(),
            audio_output_device=iv["audio_output_device"].get().strip(),
            audio_sample_rate=int(iv["audio_sample_rate"].get()),
            audio_channels=int(iv["audio_channels"].get()),
            audio_frame_ms=int(iv["audio_frame_ms"].get()),
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

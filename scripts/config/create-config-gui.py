#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import cv2
import platform

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
from src.tools.config_io import discover_cameras, write_config


def _segmentation_backend_options():
    if platform.system() == "Darwin":
        return ["selfie", "mock", "onnxruntime"]
    return ["selfie", "mock", "onnxruntime", "tensorrt"]


def _output_backend_options():
    if platform.system() == "Darwin":
        return ["pyvirtualcam", "opencv"]
    return ["opencv", "pyvirtualcam"]


class ConfigGui:
    def __init__(self, root: tk.Tk, output_path: str) -> None:
        self.root = root
        self.output_path = output_path
        self.root.title("ai-virtual-cam config GUI")
        self.vars: dict[str, tk.Variable] = {}
        self._preview_active = False
        self._preview_capture = None
        self._preview_segmenter = None
        self._preview_background = None
        self._preview_composer = None
        self._preview_seg_cfg = None
        self._preview_bg_signature = None
        self._preview_out_size = (0, 0)
        self._preview_window_name = "ai-virtual-cam preview (press q or esc to close)"
        self._build_form()

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        for col in range(4):
            frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        row = 0
        is_macos = platform.system() == "Darwin"
        cameras = discover_cameras()
        camera_values = [c["devicePath"] for c in cameras] or (["0"] if is_macos else ["/dev/video0"])

        self._add_combo(frame, row, "input_device", "Input device", camera_values, camera_values[0])
        row += 1
        self._add_int(frame, row, "input_width", "Input width", 1280)
        self._add_int(frame, row, "input_height", "Input height", 720, col_offset=2)
        row += 1
        self._add_int(frame, row, "input_fps", "Input FPS", 30)
        row += 1

        self._add_combo(frame, row, "output_backend", "Output backend", _output_backend_options(), _output_backend_options()[0])
        row += 1
        default_output_device = "virtual-cam" if is_macos else "/dev/video10"
        self._add_text(frame, row, "output_device", "Output path", default_output_device)
        row += 1
        self._add_int(frame, row, "output_width", "Output width", 1280)
        self._add_int(frame, row, "output_height", "Output height", 720, col_offset=2)
        row += 1
        self._add_int(frame, row, "output_fps", "Output FPS", 30)
        row += 1

        self._add_combo(frame, row, "seg_backend", "Seg backend", _segmentation_backend_options(), "selfie")
        row += 1
        self._add_slider(frame, row, "seg_threshold", "Seg threshold", 0.65, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(frame, row, "seg_edge_smoothness", "Edge smoothness", 0.50, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(frame, row, "seg_blend_feather", "Blend feather", 0.35, 0.0, 1.0, resolution=0.01)
        row += 1
        self._add_slider(frame, row, "seg_selfie_model", "Selfie model selection", 1, 0, 1, resolution=1)
        row += 1
        self._add_slider(frame, row, "seg_selfie_smoothing", "Selfie temporal smoothing", 0.25, 0.0, 0.95, resolution=0.01)
        row += 1

        self._add_combo(frame, row, "bg_mode", "Background mode", ["chroma", "image", "image_chroma"], "chroma")
        row += 1
        self._add_text(frame, row, "bg_image", "Background image", "")
        ttk.Button(frame, text="Browse", command=self._pick_bg_image).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_int(frame, row, "bg_r", "Chroma R", 0)
        self._add_int(frame, row, "bg_g", "Chroma G", 0, col_offset=2)
        row += 1
        self._add_int(frame, row, "bg_b", "Chroma B", 0)
        ttk.Button(frame, text="Pick Color", command=self._pick_chroma_color).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_slider(frame, row, "bg_blend_alpha", "Color blend alpha", 0.35, 0.0, 1.0, resolution=0.01)
        row += 1

        self._add_slider(frame, row, "crop_margin", "Person crop margin", 0.25, 0.0, 2.0, resolution=0.01)
        row += 1
        self._add_slider(frame, row, "crop_smoothing", "Person crop smoothing", 0.85, 0.0, 1.0, resolution=0.01)
        row += 1

        ttk.Button(frame, text="Preview", command=self._preview).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10, padx=4)
        ttk.Button(frame, text="Save JSON", command=self._save).grid(row=row, column=2, columnspan=2, sticky="ew", pady=10, padx=4)

    def _add_text(self, parent, row, key, label, default, col_offset=0):
        ttk.Label(parent, text=label).grid(row=row, column=col_offset, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        ttk.Entry(parent, textvariable=var).grid(row=row, column=col_offset + 1, sticky="ew", padx=4)

    def _add_int(self, parent, row, key, label, default, col_offset=0):
        self._add_text(parent, row, key, label, str(default), col_offset)

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
        ttk.Scale(parent, from_=min_value, to=max_value, variable=var, command=on_change).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=4
        )
        ttk.Label(parent, textvariable=value_var).grid(row=row, column=3, sticky="e")

    def _add_combo(self, parent, row, key, label, values, default):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        ttk.Combobox(parent, textvariable=var, values=values, state="readonly").grid(row=row, column=1, columnspan=3, sticky="ew", padx=4)

    def _pick_bg_image(self):
        selected = filedialog.askopenfilename(title="Select background image")
        if selected:
            self.vars["bg_image"].set(selected)

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
        from src.domain.config import BackgroundConfig, InputCameraConfig, SegmentationConfig
        from src.pipeline.background import BackgroundProvider
        from src.pipeline.composer import Composer
        from src.pipeline.segmentation import build_segmenter

        input_cfg = InputCameraConfig.from_dict(config["inputCamera"])
        self._preview_seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
        bg_cfg = BackgroundConfig.from_dict(config["background"])
        output_w = int(config["outputCamera"]["width"])
        output_h = int(config["outputCamera"]["height"])

        self._preview_capture = OpenCVCapture(input_cfg)
        self._preview_segmenter = build_segmenter(self._preview_seg_cfg)
        self._preview_background = BackgroundProvider(bg_cfg, output_w, output_h)
        self._preview_composer = Composer()
        self._preview_out_size = (output_w, output_h)
        self._preview_bg_signature = self._background_signature(config["background"])
        self._preview_active = True
        self.root.after(1, self._preview_tick)

    def _stop_preview(self) -> None:
        self._preview_active = False
        if self._preview_capture is not None:
            self._preview_capture.release()
        self._preview_capture = None
        self._preview_segmenter = None
        self._preview_background = None
        self._preview_composer = None
        self._preview_seg_cfg = None
        try:
            cv2.destroyWindow(self._preview_window_name)
        except cv2.error:
            pass

    def _preview_tick(self) -> None:
        if not self._preview_active:
            return
        from src.domain.config import BackgroundConfig, SegmentationConfig
        from src.pipeline.background import BackgroundProvider
        from src.pipeline.mask_processing import refine_mask
        from src.pipeline.segmentation import build_segmenter

        try:
            frame = self._preview_capture.read()
            config = self._build_config()

            seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
            if (
                self._preview_seg_cfg is None
                or seg_cfg.backend != self._preview_seg_cfg.backend
                or seg_cfg.selfieModelSelection != self._preview_seg_cfg.selfieModelSelection
                or abs(seg_cfg.selfieTemporalSmoothing - self._preview_seg_cfg.selfieTemporalSmoothing) > 1e-6
            ):
                self._preview_seg_cfg = seg_cfg
                self._preview_segmenter = build_segmenter(self._preview_seg_cfg)

            bg_sig = self._background_signature(config["background"])
            if bg_sig != self._preview_bg_signature:
                self._preview_bg_signature = bg_sig
                bg_cfg = BackgroundConfig.from_dict(config["background"])
                out_w, out_h = self._preview_out_size
                self._preview_background = BackgroundProvider(bg_cfg, out_w, out_h)

            raw_mask = self._preview_segmenter.segment(frame)
            mask = refine_mask(raw_mask, self._preview_seg_cfg.threshold)
            bg = self._preview_background.frame()
            out_w, out_h = self._preview_out_size
            composed = self._preview_composer.compose(frame, mask, bg)
            if composed.shape[1] != out_w or composed.shape[0] != out_h:
                composed = cv2.resize(composed, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
            preview = cv2.resize(composed, (max(1, out_w // 2), max(1, out_h // 2)), interpolation=cv2.INTER_AREA)
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
            crop_smoothing=float(iv["crop_smoothing"].get()),
        )


def parse_args():
    parser = argparse.ArgumentParser(description="GUI config generator for ai-virtual-cam")
    parser.add_argument("--output", default="~/.avc/setting.json")
    return parser.parse_args()


def main() -> int:
    if TK_IMPORT_ERROR is not None:
        print(
            "Tkinter is not available in this Python runtime.\n"
            "Use CLI config instead: ./bin/avc config\n"
            "To use GUI, install a Python build with Tk support (for macOS, python.org installer is recommended).",
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

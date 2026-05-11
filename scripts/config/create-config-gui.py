#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


class ConfigGui:
    def __init__(self, root: tk.Tk, output_path: str) -> None:
        self.root = root
        self.output_path = output_path
        self.root.title("ai-virtual-cam config GUI")
        self.vars: dict[str, tk.Variable] = {}
        self._build_form()

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        for col in range(4):
            frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        row = 0
        cameras = discover_cameras()
        camera_values = [c["devicePath"] for c in cameras] or ["/dev/video0"]

        self._add_combo(frame, row, "input_device", "Input device", camera_values, camera_values[0])
        row += 1
        self._add_int(frame, row, "input_width", "Input width", 1280)
        self._add_int(frame, row, "input_height", "Input height", 720, col_offset=2)
        row += 1
        self._add_int(frame, row, "input_fps", "Input FPS", 30)
        row += 1

        self._add_text(frame, row, "output_device", "Output path", "output/virtual-cam-preview.mp4")
        row += 1
        self._add_int(frame, row, "output_width", "Output width", 1280)
        self._add_int(frame, row, "output_height", "Output height", 720, col_offset=2)
        row += 1
        self._add_int(frame, row, "output_fps", "Output FPS", 30)
        row += 1

        self._add_combo(frame, row, "seg_backend", "Seg backend", ["face", "mock", "tensorrt", "onnxruntime"], "face")
        row += 1
        self._add_float(frame, row, "seg_threshold", "Seg threshold", 0.65)
        row += 1

        self._add_combo(frame, row, "bg_mode", "Background mode", ["chroma", "image", "image_chroma"], "chroma")
        row += 1
        self._add_text(frame, row, "bg_image", "Background image", "")
        ttk.Button(frame, text="Browse", command=self._pick_bg_image).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_int(frame, row, "bg_r", "Chroma R", 0)
        self._add_int(frame, row, "bg_g", "Chroma G", 255, col_offset=2)
        row += 1
        self._add_int(frame, row, "bg_b", "Chroma B", 0)
        ttk.Button(frame, text="Pick Color", command=self._pick_chroma_color).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_float(frame, row, "bg_blend_alpha", "Color blend alpha", 0.35)
        row += 1

        self._add_float(frame, row, "crop_margin", "Person crop margin", 0.25)
        self._add_float(frame, row, "crop_smoothing", "Person crop smoothing", 0.85, col_offset=2)
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
        try:
            config = self._build_config()
            self._run_preview(config)
        except Exception as exc:
            messagebox.showerror("Preview error", str(exc))

    def _run_preview(self, config: dict) -> None:
        import cv2
        from src.adapter.capture.opencv_capture import OpenCVCapture
        from src.domain.config import BackgroundConfig, InputCameraConfig, SegmentationConfig
        from src.pipeline.background import BackgroundProvider
        from src.pipeline.composer import Composer
        from src.pipeline.mask_processing import refine_mask
        from src.pipeline.segmentation import build_segmenter

        input_cfg = InputCameraConfig.from_dict(config["inputCamera"])
        seg_cfg = SegmentationConfig.from_dict(config["segmentation"])
        bg_cfg = BackgroundConfig.from_dict(config["background"])
        output_w = int(config["outputCamera"]["width"])
        output_h = int(config["outputCamera"]["height"])

        capture = OpenCVCapture(input_cfg)
        segmenter = build_segmenter(seg_cfg)
        background = BackgroundProvider(bg_cfg, output_w, output_h)
        composer = Composer()

        window_name = "ai-virtual-cam preview (press q or esc to close)"
        try:
            while True:
                frame = capture.read()
                raw_mask = segmenter.segment(frame)
                mask = refine_mask(raw_mask, seg_cfg.threshold)
                bg = background.frame()
                composed = composer.compose(frame, mask, bg)
                if composed.shape[1] != output_w or composed.shape[0] != output_h:
                    composed = cv2.resize(composed, (output_w, output_h), interpolation=cv2.INTER_LINEAR)
                preview_w = max(1, output_w // 2)
                preview_h = max(1, output_h // 2)
                preview = cv2.resize(composed, (preview_w, preview_h), interpolation=cv2.INTER_AREA)
                cv2.imshow(window_name, preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
        finally:
            capture.release()
            cv2.destroyWindow(window_name)

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
            segmentation_backend=iv["seg_backend"].get(),
            segmentation_threshold=float(iv["seg_threshold"].get()),
            background=background,
            crop_margin=float(iv["crop_margin"].get()),
            crop_smoothing=float(iv["crop_smoothing"].get()),
        )


def parse_args():
    parser = argparse.ArgumentParser(description="GUI config generator for ai-virtual-cam")
    parser.add_argument("--output", default="config/settings.json")
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

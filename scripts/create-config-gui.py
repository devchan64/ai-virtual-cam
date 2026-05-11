#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

def discover_cameras():
    cameras = []
    video_root = Path("/sys/class/video4linux")
    if not video_root.exists():
        return cameras
    for entry in sorted(video_root.iterdir()):
        device_path = Path("/dev") / entry.name
        name_path = entry / "name"
        label = entry.name
        if name_path.exists():
            label = name_path.read_text(encoding="utf-8").strip()
        cameras.append({"name": entry.name, "devicePath": str(device_path), "label": label})
    return cameras


def write_config(output_path: str, config: dict) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


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

        self._add_combo(frame, row, "seg_backend", "Seg backend", ["mock", "tensorrt", "onnxruntime"], "mock")
        row += 1
        self._add_float(frame, row, "seg_threshold", "Seg threshold", 0.65)
        row += 1

        self._add_combo(frame, row, "bg_mode", "Background mode", ["chroma", "image"], "chroma")
        row += 1
        self._add_text(frame, row, "bg_image", "Background image", "")
        ttk.Button(frame, text="Browse", command=self._pick_bg_image).grid(row=row, column=2, sticky="ew", padx=4)
        row += 1
        self._add_int(frame, row, "bg_r", "Chroma R", 0)
        self._add_int(frame, row, "bg_g", "Chroma G", 255, col_offset=2)
        row += 1
        self._add_int(frame, row, "bg_b", "Chroma B", 0)
        row += 1

        self._add_float(frame, row, "crop_margin", "Person crop margin", 0.25)
        self._add_float(frame, row, "crop_smoothing", "Person crop smoothing", 0.85, col_offset=2)
        row += 1

        ttk.Button(frame, text="Save JSON", command=self._save).grid(row=row, column=0, columnspan=4, sticky="ew", pady=10)

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

    def _save(self):
        try:
            config = self._build_config()
            write_config(self.output_path, config)
            messagebox.showinfo("Saved", f"Config saved to {self.output_path}")
        except Exception as exc:
            messagebox.showerror("Validation error", str(exc))

    def _build_config(self):
        iv = self.vars
        input_w = int(iv["input_width"].get())
        input_h = int(iv["input_height"].get())
        output_w = int(iv["output_width"].get())
        output_h = int(iv["output_height"].get())

        background = {"mode": iv["bg_mode"].get()}
        if background["mode"] == "chroma":
            background["chromaColor"] = [int(iv["bg_r"].get()), int(iv["bg_g"].get()), int(iv["bg_b"].get())]
        else:
            image_path = iv["bg_image"].get().strip()
            if not image_path:
                raise ValueError("Background mode=image requires image path")
            background["imagePath"] = image_path
            background["crop"] = {"x": 0, "y": 0, "width": output_w, "height": output_h}

        return {
            "inputCamera": {
                "devicePath": iv["input_device"].get(),
                "width": input_w,
                "height": input_h,
                "fps": int(iv["input_fps"].get()),
                "crop": {"x": 0, "y": 0, "width": input_w, "height": input_h},
            },
            "outputCamera": {
                "devicePath": iv["output_device"].get(),
                "width": output_w,
                "height": output_h,
                "fps": int(iv["output_fps"].get()),
            },
            "segmentation": {
                "backend": iv["seg_backend"].get(),
                "threshold": float(iv["seg_threshold"].get()),
            },
            "background": background,
            "crop": {
                "margin": float(iv["crop_margin"].get()),
                "smoothing": float(iv["crop_smoothing"].get()),
            },
        }


def parse_args():
    parser = argparse.ArgumentParser(description="GUI config generator for ai-virtual-cam")
    parser.add_argument("--output", default="config/settings.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = tk.Tk()
    ConfigGui(root, args.output)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

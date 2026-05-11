#!/usr/bin/env python3

import argparse
import platform
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.tools.config_builder import build_config
from src.tools.config_io import discover_cameras, write_config

def prompt_text(message, default=None, validator=None):
    while True:
        suffix = f" [{default}]" if default is not None else ""
        try:
            value = input(f"{message}{suffix}: ").strip()
        except EOFError:
            if default is not None:
                print()
                return str(default)
            raise SystemExit(f"Input ended before a value was provided for: {message}")
        if not value and default is not None:
            value = str(default)
        if not value:
            print("Value is required.")
            continue
        if validator is None:
            return value
        error = validator(value)
        if error is None:
            return value
        print(error)


def prompt_int(message, default=None, minimum=0, maximum=None):
    def validator(raw):
        try:
            value = int(raw)
        except ValueError:
            return "Enter a valid integer."
        if value < minimum:
            return f"Value must be >= {minimum}."
        if maximum is not None and value > maximum:
            return f"Value must be <= {maximum}."
        return None

    return int(prompt_text(message, default=default, validator=validator))


def prompt_float(message, default=None, minimum=None, maximum=None):
    def validator(raw):
        try:
            value = float(raw)
        except ValueError:
            return "Enter a valid number."
        if minimum is not None and value < minimum:
            return f"Value must be >= {minimum}."
        if maximum is not None and value > maximum:
            return f"Value must be <= {maximum}."
        return None

    return float(prompt_text(message, default=default, validator=validator))


def prompt_choice(message, options, default=None):
    option_set = {option.lower(): option for option in options}

    def validator(raw):
        if raw.lower() not in option_set:
            return f"Choose one of: {', '.join(options)}"
        return None

    selected = prompt_text(message, default=default, validator=validator)
    return option_set[selected.lower()]


def prompt_path(message, default=None, must_exist=False):
    def validator(raw):
        if must_exist and not Path(raw).exists():
            return f"Path does not exist: {raw}"
        return None

    return prompt_text(message, default=default, validator=validator)


def prompt_crop(prefix, default_width, default_height):
    print(f"\n{prefix} crop")
    x = prompt_int("  x", default=0, minimum=0)
    y = prompt_int("  y", default=0, minimum=0)
    width = prompt_int("  width", default=default_width, minimum=1)
    height = prompt_int("  height", default=default_height, minimum=1)
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def choose_camera(cameras):
    if not cameras:
        default_input = "0" if platform.system() == "Darwin" else "/dev/video0"
        return prompt_path("Input camera device path", default=default_input)

    print("Detected camera interfaces:")
    for index, camera in enumerate(cameras, start=1):
        print(f"  {index}. {camera['devicePath']} ({camera['label']})")

    while True:
        raw = prompt_text("Select camera number", default="1")
        try:
            selected = int(raw)
        except ValueError:
            print("Enter a valid number.")
            continue
        if 1 <= selected <= len(cameras):
            return cameras[selected - 1]["devicePath"]
        print(f"Select a number between 1 and {len(cameras)}.")


def build_config():
    is_macos = platform.system() == "Darwin"
    cameras = discover_cameras()
    input_camera_path = choose_camera(cameras)

    print("\nInput camera settings")
    input_width = prompt_int("  width", default=1280, minimum=1)
    input_height = prompt_int("  height", default=720, minimum=1)
    input_fps = prompt_int("  fps", default=30, minimum=1)
    input_software_zoom = prompt_float("  software zoom (1.0..4.0)", default=1.0, minimum=1.0, maximum=4.0)

    print("\nOutput camera settings")
    output_backend = prompt_choice(
        "  backend",
        ["pyvirtualcam", "opencv"] if is_macos else ["opencv"],
        default="pyvirtualcam" if is_macos else "opencv",
    )
    output_camera_path = prompt_path(
        "  device path",
        default="virtual-cam" if output_backend == "pyvirtualcam" else "/dev/video10",
    )
    output_width = prompt_int("  width", default=input_width, minimum=1)
    output_height = prompt_int("  height", default=input_height, minimum=1)
    output_fps = prompt_int("  fps", default=input_fps, minimum=1)

    camera_crop = prompt_crop("Camera", input_width, input_height)

    print("\nSegmentation settings")
    segmentation_backend = prompt_choice("  backend", _segmentation_backend_options(), default="selfie")
    segmentation_threshold = prompt_float("  threshold", default=0.65, minimum=0.0, maximum=1.0)
    segmentation_edge_smoothness = prompt_float("  edge smoothness (0.0..1.0)", default=0.50, minimum=0.0, maximum=1.0)
    segmentation_blend_feather = prompt_float("  blend feather (0.0..1.0)", default=0.35, minimum=0.0, maximum=1.0)
    segmentation_selfie_model_selection = prompt_int("  selfie model selection (0 or 1)", default=1, minimum=0, maximum=1)
    segmentation_selfie_temporal_smoothing = prompt_float(
        "  selfie temporal smoothing (0.0..0.95)",
        default=0.25,
        minimum=0.0,
        maximum=0.95,
    )

    print("\nBackground settings")
    background_mode = prompt_choice("  mode", ["chroma", "image", "image_chroma"], default="chroma")
    background = {"mode": background_mode}

    if background_mode in {"chroma", "image_chroma"}:
        background["chromaColor"] = [
            prompt_int("  chroma R", default=0, minimum=0, maximum=255),
            prompt_int("  chroma G", default=0, minimum=0, maximum=255),
            prompt_int("  chroma B", default=0, minimum=0, maximum=255),
        ]
    if background_mode in {"image", "image_chroma"}:
        image_path = prompt_path("  image path", must_exist=True)
        background["imagePath"] = image_path
        background["crop"] = prompt_crop("Background image", output_width, output_height)
    if background_mode == "image_chroma":
        background["colorBlendAlpha"] = prompt_float(
            "  color blend alpha (0.0=image only, 1.0=color only)",
            default=0.35,
            minimum=0.0,
            maximum=1.0,
        )

    print("\nPerson crop / framing settings")
    crop_margin = prompt_float("  margin", default=0.25, minimum=0.0)
    crop_pan_smoothing = prompt_float("  pan smoothing", default=0.85, minimum=0.0, maximum=1.0)
    crop_upper_body_bias = prompt_float("  upper body bias (0.0=top, 1.0=bottom)", default=0.35, minimum=0.0, maximum=1.0)
    crop_upper_body_ratio = prompt_float("  upper body ratio (0.2..1.0)", default=0.60, minimum=0.2, maximum=1.0)
    crop_pan_pid_kp = prompt_float("  pan PID Kp", default=0.35, minimum=0.0)
    crop_pan_pid_ki = prompt_float("  pan PID Ki", default=0.01, minimum=0.0)
    crop_pan_pid_kd = prompt_float("  pan PID Kd", default=0.12, minimum=0.0)

    config = build_config(
        input_device=input_camera_path,
        input_width=input_width,
        input_height=input_height,
        input_fps=input_fps,
        output_device=output_camera_path,
        output_width=output_width,
        output_height=output_height,
        output_fps=output_fps,
        output_backend=output_backend,
        segmentation_backend=segmentation_backend,
        segmentation_threshold=segmentation_threshold,
        segmentation_edge_smoothness=segmentation_edge_smoothness,
        segmentation_blend_feather=segmentation_blend_feather,
        segmentation_selfie_model_selection=segmentation_selfie_model_selection,
        segmentation_selfie_temporal_smoothing=segmentation_selfie_temporal_smoothing,
        background=background,
        crop_margin=crop_margin,
        crop_pan_smoothing=crop_pan_smoothing,
        crop_upper_body_bias=crop_upper_body_bias,
        crop_upper_body_ratio=crop_upper_body_ratio,
        input_software_zoom=input_software_zoom,
        crop_pan_pid_kp=crop_pan_pid_kp,
        crop_pan_pid_ki=crop_pan_pid_ki,
        crop_pan_pid_kd=crop_pan_pid_kd,
    )
    config["inputCamera"]["crop"] = camera_crop
    return config


def list_cameras():
    cameras = discover_cameras()
    if not cameras:
        print("No cameras detected.")
        return 0

    for camera in cameras:
        print(f"{camera['devicePath']}\t{camera['label']}")
    return 0


def write_config_with_log(output_path, config):
    write_config(output_path, config)
    print(f"Config written to {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a JSON configuration file for ai-virtual-cam."
    )
    parser.add_argument(
        "--output",
        default="~/.avc/setting.json",
        help="Output JSON file path (default: ~/.avc/setting.json)",
    )
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="List detected V4L2 camera interfaces and exit",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.list_cameras:
        return list_cameras()

    config = build_config()
    write_config_with_log(args.output, config)
    return 0


def _segmentation_backend_options():
    if platform.system() == "Darwin":
        return ["selfie", "mock", "onnxruntime"]
    return ["selfie", "mock", "onnxruntime", "tensorrt"]


if __name__ == "__main__":
    sys.exit(main())

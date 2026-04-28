#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


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
        cameras.append(
            {
                "name": entry.name,
                "devicePath": str(device_path),
                "label": label,
            }
        )
    return cameras


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
        return prompt_path("Input camera device path", default="/dev/video0")

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
    cameras = discover_cameras()
    input_camera_path = choose_camera(cameras)

    print("\nInput camera settings")
    input_width = prompt_int("  width", default=1280, minimum=1)
    input_height = prompt_int("  height", default=720, minimum=1)
    input_fps = prompt_int("  fps", default=30, minimum=1)

    print("\nOutput camera settings")
    output_camera_path = prompt_path("  device path", default="/dev/video10")
    output_width = prompt_int("  width", default=input_width, minimum=1)
    output_height = prompt_int("  height", default=input_height, minimum=1)
    output_fps = prompt_int("  fps", default=input_fps, minimum=1)

    camera_crop = prompt_crop("Camera", input_width, input_height)

    print("\nSegmentation settings")
    segmentation_backend = prompt_choice("  backend", ["mock", "tensorrt", "onnxruntime"], default="mock")
    segmentation_threshold = prompt_float("  threshold", default=0.65, minimum=0.0, maximum=1.0)

    print("\nBackground settings")
    background_mode = prompt_choice("  mode", ["chroma", "image"], default="chroma")
    background = {"mode": background_mode}

    if background_mode == "chroma":
        background["chromaColor"] = [
            prompt_int("  chroma R", default=0, minimum=0, maximum=255),
            prompt_int("  chroma G", default=255, minimum=0, maximum=255),
            prompt_int("  chroma B", default=0, minimum=0, maximum=255),
        ]
    else:
        image_path = prompt_path("  image path", must_exist=True)
        background["imagePath"] = image_path
        background["crop"] = prompt_crop("Background image", output_width, output_height)

    print("\nPerson crop settings")
    crop_margin = prompt_float("  margin", default=0.25, minimum=0.0)
    crop_smoothing = prompt_float("  smoothing", default=0.85, minimum=0.0, maximum=1.0)

    return {
        "inputCamera": {
            "devicePath": input_camera_path,
            "width": input_width,
            "height": input_height,
            "fps": input_fps,
            "crop": camera_crop,
        },
        "outputCamera": {
            "devicePath": output_camera_path,
            "width": output_width,
            "height": output_height,
            "fps": output_fps,
        },
        "segmentation": {
            "backend": segmentation_backend,
            "threshold": segmentation_threshold,
        },
        "background": background,
        "crop": {
            "margin": crop_margin,
            "smoothing": crop_smoothing,
        },
    }


def list_cameras():
    cameras = discover_cameras()
    if not cameras:
        print("No cameras detected.")
        return 0

    for camera in cameras:
        print(f"{camera['devicePath']}\t{camera['label']}")
    return 0


def write_config(output_path, config):
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Config written to {output_file}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a JSON configuration file for ai-virtual-cam."
    )
    parser.add_argument(
        "--output",
        default="config/settings.json",
        help="Output JSON file path (default: config/settings.json)",
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
    write_config(args.output, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())

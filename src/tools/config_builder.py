from __future__ import annotations


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
    segmentation_backend: str,
    segmentation_threshold: float,
    segmentation_selfie_model_selection: int = 1,
    segmentation_selfie_temporal_smoothing: float = 0.25,
    background: dict,
    crop_margin: float,
    crop_smoothing: float,
) -> dict:
    return {
        "inputCamera": {
            "devicePath": input_device,
            "width": input_width,
            "height": input_height,
            "fps": input_fps,
            "crop": {"x": 0, "y": 0, "width": input_width, "height": input_height},
        },
        "outputCamera": {
            "devicePath": output_device,
            "width": output_width,
            "height": output_height,
            "fps": output_fps,
        },
        "segmentation": {
            "backend": segmentation_backend,
            "threshold": segmentation_threshold,
            "selfie": {
                "modelSelection": int(segmentation_selfie_model_selection),
                "temporalSmoothing": float(segmentation_selfie_temporal_smoothing),
            },
        },
        "background": background,
        "crop": {
            "margin": crop_margin,
            "smoothing": crop_smoothing,
        },
    }

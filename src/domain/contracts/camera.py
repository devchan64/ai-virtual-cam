from __future__ import annotations

CAMERA_FEATURE_TOGGLE_KEYS = (
    "seg_enabled",
    "bg_enabled",
    "crop_enabled",
    "face_enhance_enabled",
    "face_deidentify_enabled",
)

CAMERA_PIPELINE_FEATURE_DEFAULTS = {
    "cameraServerEnabled": True,
    "segmentationEnabled": True,
    "backgroundEnabled": True,
    "cropEnabled": True,
    "faceEnhanceEnabled": False,
    "faceDeidentifyEnabled": False,
}


def camera_feature_toggle_keys() -> tuple[str, ...]:
    return CAMERA_FEATURE_TOGGLE_KEYS


def camera_default(key: str):
    return CAMERA_PIPELINE_FEATURE_DEFAULTS[key]

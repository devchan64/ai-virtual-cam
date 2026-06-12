from __future__ import annotations

WHISPER_DEFAULTS = {
    "enabled": False,
    "backend": "faster-whisper",
    "model": "large-v3",
    "language": "ko",
    "task": "transcribe",
    "translationEnabled": False,
    "translationTargetLanguage": "en",
    "translationBackend": "whisper",
    "translationModel": "facebook/nllb-200-distilled-600M",
    "translationDevice": "cuda",
    "translationComputeType": "float16",
    "translationBeamSize": 1,
    "translationMaxNewTokens": 128,
    "device": "cuda",
    "computeType": "float16",
    "vadFilter": True,
    "chunkSeconds": 2.5,
    "beamSize": 3,
    "maxNewTokens": 96,
    "temperature": 0.0,
}


def whisper_default(key: str):
    return WHISPER_DEFAULTS[key]


def whisper_defaults() -> dict:
    return dict(WHISPER_DEFAULTS)

from __future__ import annotations

WHISPER_DEFAULTS = {
    "enabled": False,
    "backend": "faster-whisper",
    "model": "large-v3",
    "language": "en",
    "task": "transcribe",
    "translationEnabled": False,
    "translationTargetLanguage": "ko",
    "translationBackend": "nllb-transformers",
    "translationModel": "facebook/nllb-200-distilled-600M",
    "translationDevice": "cuda",
    "translationComputeType": "float16",
    "translationBeamSize": 1,
    "translationMaxNewTokens": 128,
    "device": "cuda",
    "computeType": "float16",
    "chunkSeconds": 5.0,
    "stepSeconds": 1.0,
    "windowSeconds": 5.0,
    "commitLagSeconds": 0.5,
    "beamSize": 3,
    "maxNewTokens": 96,
    "temperature": 0.0,
}


def whisper_default(key: str):
    return WHISPER_DEFAULTS[key]


def whisper_defaults() -> dict:
    return dict(WHISPER_DEFAULTS)

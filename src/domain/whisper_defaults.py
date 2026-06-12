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
    "vadFilter": True,
    "chunkSeconds": 4.0,
    "stepSeconds": 1.0,
    "windowSeconds": 4.0,
    "commitLagSeconds": 1.0,
    "beamSize": 5,
    "maxNewTokens": 64,
    "temperature": 0.0,
}


def whisper_default(key: str):
    return WHISPER_DEFAULTS[key]


def whisper_defaults() -> dict:
    return dict(WHISPER_DEFAULTS)

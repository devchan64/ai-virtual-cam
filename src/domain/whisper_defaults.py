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
    "chunkSeconds": 7.5,
    "stepSeconds": 1.5,
    "windowSeconds": 7.5,
    "commitLagSeconds": 0.8,
    "beamSize": 3,
    "maxNewTokens": 96,
    "temperature": 0.0,
    "sentenceBoundaryBackend": "sat",
    "sentenceBoundaryModel": "sat-3l-sm",
    "sentenceBoundaryDevice": "cuda",
    "sentenceBoundaryComputeType": "float16",
}


def whisper_default(key: str):
    return WHISPER_DEFAULTS[key]


def whisper_defaults() -> dict:
    return dict(WHISPER_DEFAULTS)

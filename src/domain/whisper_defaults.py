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
    "commitLagSeconds": 1.5,
    "beamSize": 3,
    "maxNewTokens": 96,
    "temperature": 0.0,
    "postProcessingProfile": "auto-by-language",
    "sentenceBoundaryBackend": "sat",
    "sentenceBoundaryModel": "sat-3l-sm",
    "sentenceBoundaryBackendEn": "sat",
    "sentenceBoundaryModelEn": "sat-3l-sm",
    "sentenceBoundaryBackendKo": "sat",
    "sentenceBoundaryModelKo": "sat-3l-sm",
    "sentenceBoundaryBackendZh": "funasr-ct-punc",
    "sentenceBoundaryModelZh": "ct-punc-c",
    "sentenceBoundaryDevice": "cuda",
    "sentenceBoundaryComputeType": "float16",
}


def whisper_default(key: str):
    return WHISPER_DEFAULTS[key]


def whisper_defaults() -> dict:
    return dict(WHISPER_DEFAULTS)

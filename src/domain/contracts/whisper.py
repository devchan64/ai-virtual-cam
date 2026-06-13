from __future__ import annotations

from .fields import ConfigFieldSpec

WHISPER_BACKENDS = ("faster-whisper", "openai-whisper", "whisper.cpp", "mock")
WHISPER_STT_BACKENDS = ("faster-whisper", "funasr-paraformer", "funasr-sensevoice", "mock")
WHISPER_LANGUAGES = ("ko", "en", "zh")
WHISPER_TASKS = ("transcribe", "translate")
WHISPER_TRANSLATION_TARGET_LANGUAGES = ("en", "ko", "zh")
WHISPER_TRANSLATION_BACKENDS = ("whisper", "nllb-transformers", "mock")
WHISPER_RUNTIME_DEVICES = ("cuda", "cpu")
WHISPER_COMPUTE_TYPES = ("float16", "float32")
WHISPER_POST_PROCESSING_PROFILES = ("manual", "auto-by-language")
WHISPER_SENTENCE_BOUNDARY_BACKENDS = ("sat", "funasr-ct-punc", "mock")

WHISPER_CONTRACT: dict[str, ConfigFieldSpec] = {
    "enabled": ConfigFieldSpec("enabled", False, bool),
    "backend": ConfigFieldSpec("backend", "faster-whisper", str, allowed=WHISPER_BACKENDS, ui_group="stt.global"),
    "model": ConfigFieldSpec("model", "large-v3", str, ui_group="stt.global"),
    "sttBackendEn": ConfigFieldSpec("sttBackendEn", "faster-whisper", str, allowed=WHISPER_STT_BACKENDS, ui_group="stt.en"),
    "sttModelEn": ConfigFieldSpec("sttModelEn", "large-v3", str, ui_group="stt.en"),
    "sttBackendKo": ConfigFieldSpec("sttBackendKo", "faster-whisper", str, allowed=WHISPER_STT_BACKENDS, ui_group="stt.ko"),
    "sttModelKo": ConfigFieldSpec("sttModelKo", "large-v3", str, ui_group="stt.ko"),
    "sttBackendZh": ConfigFieldSpec("sttBackendZh", "funasr-paraformer", str, allowed=WHISPER_STT_BACKENDS, ui_group="stt.zh"),
    "sttModelZh": ConfigFieldSpec("sttModelZh", "paraformer-zh", str, ui_group="stt.zh"),
    "language": ConfigFieldSpec("language", "en", str, allowed=WHISPER_LANGUAGES),
    "task": ConfigFieldSpec("task", "transcribe", str, allowed=WHISPER_TASKS),
    "translationEnabled": ConfigFieldSpec("translationEnabled", False, bool),
    "translationTargetLanguage": ConfigFieldSpec(
        "translationTargetLanguage", "ko", str, allowed=WHISPER_TRANSLATION_TARGET_LANGUAGES
    ),
    "translationBackend": ConfigFieldSpec(
        "translationBackend", "nllb-transformers", str, allowed=WHISPER_TRANSLATION_BACKENDS
    ),
    "translationModel": ConfigFieldSpec("translationModel", "facebook/nllb-200-distilled-600M", str),
    "translationDevice": ConfigFieldSpec("translationDevice", "cuda", str, allowed=WHISPER_RUNTIME_DEVICES),
    "translationComputeType": ConfigFieldSpec("translationComputeType", "float16", str, allowed=WHISPER_COMPUTE_TYPES),
    "translationBeamSize": ConfigFieldSpec("translationBeamSize", 1, int, min_value=1, max_value=8),
    "translationMaxNewTokens": ConfigFieldSpec("translationMaxNewTokens", 128, int, min_value=16, max_value=512),
    "device": ConfigFieldSpec("device", "cuda", str),
    "computeType": ConfigFieldSpec("computeType", "float16", str),
    "chunkSeconds": ConfigFieldSpec("chunkSeconds", 7.5, float, min_value=1.0, max_value=15.0),
    "stepSeconds": ConfigFieldSpec("stepSeconds", 1.5, float, min_value=0.5, max_value=5.0),
    "windowSeconds": ConfigFieldSpec("windowSeconds", 7.5, float, min_value=1.0, max_value=15.0),
    "commitLagSeconds": ConfigFieldSpec("commitLagSeconds", 1.5, float, min_value=0.0),
    "beamSize": ConfigFieldSpec("beamSize", 3, int, min_value=1, max_value=8),
    "maxNewTokens": ConfigFieldSpec("maxNewTokens", 96, int, min_value=16, max_value=512),
    "temperature": ConfigFieldSpec("temperature", 0.0, float, min_value=0.0, max_value=1.0),
    "postProcessingProfile": ConfigFieldSpec(
        "postProcessingProfile", "auto-by-language", str, allowed=WHISPER_POST_PROCESSING_PROFILES
    ),
    "sentenceBoundaryBackend": ConfigFieldSpec(
        "sentenceBoundaryBackend", "sat", str, allowed=WHISPER_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.manual"
    ),
    "sentenceBoundaryModel": ConfigFieldSpec("sentenceBoundaryModel", "sat-3l-sm", str, ui_group="boundary.manual"),
    "sentenceBoundaryBackendEn": ConfigFieldSpec(
        "sentenceBoundaryBackendEn", "sat", str, allowed=WHISPER_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.en"
    ),
    "sentenceBoundaryModelEn": ConfigFieldSpec("sentenceBoundaryModelEn", "sat-3l-sm", str, ui_group="boundary.en"),
    "sentenceBoundaryBackendKo": ConfigFieldSpec(
        "sentenceBoundaryBackendKo", "sat", str, allowed=WHISPER_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.ko"
    ),
    "sentenceBoundaryModelKo": ConfigFieldSpec("sentenceBoundaryModelKo", "sat-3l-sm", str, ui_group="boundary.ko"),
    "sentenceBoundaryBackendZh": ConfigFieldSpec(
        "sentenceBoundaryBackendZh", "funasr-ct-punc", str, allowed=WHISPER_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.zh"
    ),
    "sentenceBoundaryModelZh": ConfigFieldSpec("sentenceBoundaryModelZh", "ct-punc-c", str, ui_group="boundary.zh"),
    "sentenceBoundaryDevice": ConfigFieldSpec("sentenceBoundaryDevice", "cuda", str, allowed=WHISPER_RUNTIME_DEVICES),
    "sentenceBoundaryComputeType": ConfigFieldSpec("sentenceBoundaryComputeType", "float16", str, allowed=WHISPER_COMPUTE_TYPES),
}


def whisper_default(key: str):
    return WHISPER_CONTRACT[key].default


def whisper_defaults() -> dict:
    return {key: spec.default for key, spec in WHISPER_CONTRACT.items()}


def whisper_spec(key: str) -> ConfigFieldSpec:
    return WHISPER_CONTRACT[key]


def whisper_allowed(key: str) -> tuple[object, ...]:
    allowed = WHISPER_CONTRACT[key].allowed
    if allowed is None:
        raise KeyError(f"whisper contract field has no allowed values: {key}")
    return allowed

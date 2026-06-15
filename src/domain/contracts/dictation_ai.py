from __future__ import annotations

from .fields import ConfigFieldSpec

DICTATION_AI_BACKENDS = ("faster-whisper", "openai-whisper", "whisper.cpp", "mock")
DICTATION_AI_STT_BACKENDS = (
    "faster-whisper",
    "qwen3-asr-transformers",
    "qwen3-asr-vllm-streaming",
    "mock",
)
DICTATION_AI_LANGUAGES = ("ko", "en", "zh")
DICTATION_AI_TASKS = ("transcribe", "translate")
DICTATION_AI_TRANSLATION_TARGET_LANGUAGES = ("en", "ko", "zh")
DICTATION_AI_TRANSLATION_BACKENDS = ("whisper", "nllb-transformers", "m2m100-transformers", "mock")
DICTATION_AI_RUNTIME_DEVICES = ("cuda", "cpu")
DICTATION_AI_COMPUTE_TYPES = ("float16", "float32")
DICTATION_AI_POST_PROCESSING_PROFILES = ("manual",)
DICTATION_AI_SENTENCE_BOUNDARY_BACKENDS = ("sat", "mock")

DICTATION_AI_STT_BACKENDS_BY_LANGUAGE = {
    "en": ("faster-whisper", "mock"),
    "ko": ("faster-whisper", "mock"),
    "zh": (
        "faster-whisper",
        "qwen3-asr-transformers",
        "qwen3-asr-vllm-streaming",
        "mock",
    ),
}

DICTATION_AI_TRANSLATION_GROUPS = {
    "whisper": {
        "source_languages": DICTATION_AI_LANGUAGES,
        "target_languages": ("en",),
        "models": (),
    },
    "nllb-transformers": {
        "source_languages": DICTATION_AI_LANGUAGES,
        "target_languages": DICTATION_AI_TRANSLATION_TARGET_LANGUAGES,
        "models": (
            "facebook/nllb-200-distilled-600M",
            "facebook/nllb-200-distilled-1.3B",
            "facebook/nllb-200-1.3B",
            "facebook/nllb-200-3.3B",
        ),
    },
    "m2m100-transformers": {
        "source_languages": DICTATION_AI_LANGUAGES,
        "target_languages": DICTATION_AI_TRANSLATION_TARGET_LANGUAGES,
        "models": ("facebook/m2m100_1.2B",),
    },
    "mock": {
        "source_languages": DICTATION_AI_LANGUAGES,
        "target_languages": DICTATION_AI_TRANSLATION_TARGET_LANGUAGES,
        "models": (),
    },
}


def dictation_ai_translation_backends_for_language(language: str) -> tuple[str, ...]:
    normalized = str(language or "").strip().lower()
    return tuple(
        backend
        for backend, group in DICTATION_AI_TRANSLATION_GROUPS.items()
        if normalized in group["source_languages"]
    )


def dictation_ai_translation_backends_for_target_language(target_language: str) -> tuple[str, ...]:
    normalized = str(target_language or "").strip().lower()
    return tuple(
        backend
        for backend, group in DICTATION_AI_TRANSLATION_GROUPS.items()
        if normalized in group["target_languages"]
    )


def dictation_ai_translation_targets_for_backend(language: str, backend: str) -> tuple[str, ...]:
    normalized_language = str(language or "").strip().lower()
    normalized_backend = str(backend or "").strip().lower()
    group = DICTATION_AI_TRANSLATION_GROUPS.get(normalized_backend)
    if not group or normalized_language not in group["source_languages"]:
        return ()
    return tuple(group["target_languages"])


def dictation_ai_translation_models_for_backend(backend: str) -> tuple[str, ...]:
    normalized_backend = str(backend or "").strip().lower()
    group = DICTATION_AI_TRANSLATION_GROUPS.get(normalized_backend)
    if not group:
        return ()
    return tuple(group["models"])


def dictation_ai_stt_backends_for_language(language: str) -> tuple[str, ...]:
    normalized = str(language or "").strip().lower()
    return DICTATION_AI_STT_BACKENDS_BY_LANGUAGE.get(normalized, ("faster-whisper", "mock"))

DICTATION_AI_CONTRACT: dict[str, ConfigFieldSpec] = {
    "enabled": ConfigFieldSpec("enabled", False, bool),
    "showSttStatusWindow": ConfigFieldSpec("showSttStatusWindow", False, bool),
    "backend": ConfigFieldSpec("backend", "faster-whisper", str, allowed=DICTATION_AI_BACKENDS, ui_group="stt.global"),
    "model": ConfigFieldSpec("model", "large-v3", str, ui_group="stt.global"),
    "sttBackendEn": ConfigFieldSpec("sttBackendEn", "faster-whisper", str, allowed=DICTATION_AI_STT_BACKENDS, ui_group="stt.en"),
    "sttModelEn": ConfigFieldSpec("sttModelEn", "large-v3", str, ui_group="stt.en"),
    "sttBackendKo": ConfigFieldSpec("sttBackendKo", "faster-whisper", str, allowed=DICTATION_AI_STT_BACKENDS, ui_group="stt.ko"),
    "sttModelKo": ConfigFieldSpec("sttModelKo", "large-v3", str, ui_group="stt.ko"),
    "sttBackendZh": ConfigFieldSpec(
        "sttBackendZh", "qwen3-asr-transformers", str, allowed=DICTATION_AI_STT_BACKENDS, ui_group="stt.zh"
    ),
    "sttModelZh": ConfigFieldSpec("sttModelZh", "qwen3-asr-0.6b", str, ui_group="stt.zh"),
    "language": ConfigFieldSpec("language", "en", str, allowed=DICTATION_AI_LANGUAGES),
    "task": ConfigFieldSpec("task", "transcribe", str, allowed=DICTATION_AI_TASKS),
    "translationEnabled": ConfigFieldSpec("translationEnabled", False, bool),
    "translationTargetLanguage": ConfigFieldSpec(
        "translationTargetLanguage", "ko", str, allowed=DICTATION_AI_TRANSLATION_TARGET_LANGUAGES
    ),
    "translationBackend": ConfigFieldSpec(
        "translationBackend", "nllb-transformers", str, allowed=DICTATION_AI_TRANSLATION_BACKENDS
    ),
    "translationModel": ConfigFieldSpec("translationModel", "facebook/nllb-200-distilled-600M", str),
    "translationDevice": ConfigFieldSpec("translationDevice", "cuda", str, allowed=DICTATION_AI_RUNTIME_DEVICES),
    "translationComputeType": ConfigFieldSpec("translationComputeType", "float16", str, allowed=DICTATION_AI_COMPUTE_TYPES),
    "translationBeamSize": ConfigFieldSpec("translationBeamSize", 1, int, min_value=1, max_value=8),
    "translationMaxNewTokens": ConfigFieldSpec("translationMaxNewTokens", 128, int, min_value=16, max_value=512),
    "translationBackendEn": ConfigFieldSpec(
        "translationBackendEn", "whisper", str, allowed=DICTATION_AI_TRANSLATION_BACKENDS, ui_group="translation.en"
    ),
    "translationModelEn": ConfigFieldSpec("translationModelEn", "", str, ui_group="translation.en"),
    "translationDeviceEn": ConfigFieldSpec("translationDeviceEn", "cuda", str, allowed=DICTATION_AI_RUNTIME_DEVICES, ui_group="translation.en"),
    "translationComputeTypeEn": ConfigFieldSpec(
        "translationComputeTypeEn", "float16", str, allowed=DICTATION_AI_COMPUTE_TYPES, ui_group="translation.en"
    ),
    "translationBeamSizeEn": ConfigFieldSpec("translationBeamSizeEn", 1, int, min_value=1, max_value=8, ui_group="translation.en"),
    "translationMaxNewTokensEn": ConfigFieldSpec(
        "translationMaxNewTokensEn", 128, int, min_value=16, max_value=512, ui_group="translation.en"
    ),
    "translationBackendKo": ConfigFieldSpec(
        "translationBackendKo", "nllb-transformers", str, allowed=DICTATION_AI_TRANSLATION_BACKENDS, ui_group="translation.ko"
    ),
    "translationModelKo": ConfigFieldSpec("translationModelKo", "facebook/nllb-200-distilled-600M", str, ui_group="translation.ko"),
    "translationDeviceKo": ConfigFieldSpec("translationDeviceKo", "cuda", str, allowed=DICTATION_AI_RUNTIME_DEVICES, ui_group="translation.ko"),
    "translationComputeTypeKo": ConfigFieldSpec(
        "translationComputeTypeKo", "float16", str, allowed=DICTATION_AI_COMPUTE_TYPES, ui_group="translation.ko"
    ),
    "translationBeamSizeKo": ConfigFieldSpec("translationBeamSizeKo", 1, int, min_value=1, max_value=8, ui_group="translation.ko"),
    "translationMaxNewTokensKo": ConfigFieldSpec(
        "translationMaxNewTokensKo", 128, int, min_value=16, max_value=512, ui_group="translation.ko"
    ),
    "translationBackendZh": ConfigFieldSpec(
        "translationBackendZh", "m2m100-transformers", str, allowed=DICTATION_AI_TRANSLATION_BACKENDS, ui_group="translation.zh"
    ),
    "translationModelZh": ConfigFieldSpec("translationModelZh", "facebook/m2m100_1.2B", str, ui_group="translation.zh"),
    "translationDeviceZh": ConfigFieldSpec("translationDeviceZh", "cuda", str, allowed=DICTATION_AI_RUNTIME_DEVICES, ui_group="translation.zh"),
    "translationComputeTypeZh": ConfigFieldSpec(
        "translationComputeTypeZh", "float16", str, allowed=DICTATION_AI_COMPUTE_TYPES, ui_group="translation.zh"
    ),
    "translationBeamSizeZh": ConfigFieldSpec("translationBeamSizeZh", 1, int, min_value=1, max_value=8, ui_group="translation.zh"),
    "translationMaxNewTokensZh": ConfigFieldSpec(
        "translationMaxNewTokensZh", 128, int, min_value=16, max_value=512, ui_group="translation.zh"
    ),
    "device": ConfigFieldSpec("device", "cuda", str),
    "computeType": ConfigFieldSpec("computeType", "float16", str),
    "chunkSeconds": ConfigFieldSpec("chunkSeconds", 7.0, float, min_value=1.0, max_value=30.0),
    "stepSeconds": ConfigFieldSpec("stepSeconds", 2.0, float, min_value=0.5, max_value=5.0),
    "windowSeconds": ConfigFieldSpec("windowSeconds", 7.0, float, min_value=1.0, max_value=30.0),
    "sentenceFinalizeAge": ConfigFieldSpec("sentenceFinalizeAge", 3, int, min_value=1, max_value=8),
    "beamSize": ConfigFieldSpec("beamSize", 3, int, min_value=1, max_value=8),
    "maxNewTokens": ConfigFieldSpec("maxNewTokens", 192, int, min_value=16, max_value=512),
    "temperature": ConfigFieldSpec("temperature", 0.0, float, min_value=0.0, max_value=1.0),
    "stepSecondsEn": ConfigFieldSpec("stepSecondsEn", 1.0, float, min_value=0.5, max_value=5.0, ui_group="runtime.en"),
    "windowSecondsEn": ConfigFieldSpec("windowSecondsEn", 7.0, float, min_value=1.0, max_value=30.0, ui_group="runtime.en"),
    "sentenceFinalizeAgeEn": ConfigFieldSpec(
        "sentenceFinalizeAgeEn", 3, int, min_value=1, max_value=8, ui_group="runtime.en"
    ),
    "beamSizeEn": ConfigFieldSpec("beamSizeEn", 3, int, min_value=1, max_value=8, ui_group="runtime.en"),
    "maxNewTokensEn": ConfigFieldSpec("maxNewTokensEn", 192, int, min_value=16, max_value=512, ui_group="runtime.en"),
    "temperatureEn": ConfigFieldSpec("temperatureEn", 0.0, float, min_value=0.0, max_value=1.0, ui_group="runtime.en"),
    "stepSecondsKo": ConfigFieldSpec("stepSecondsKo", 1.0, float, min_value=0.5, max_value=5.0, ui_group="runtime.ko"),
    "windowSecondsKo": ConfigFieldSpec("windowSecondsKo", 7.0, float, min_value=1.0, max_value=30.0, ui_group="runtime.ko"),
    "sentenceFinalizeAgeKo": ConfigFieldSpec(
        "sentenceFinalizeAgeKo", 3, int, min_value=1, max_value=8, ui_group="runtime.ko"
    ),
    "beamSizeKo": ConfigFieldSpec("beamSizeKo", 3, int, min_value=1, max_value=8, ui_group="runtime.ko"),
    "maxNewTokensKo": ConfigFieldSpec("maxNewTokensKo", 192, int, min_value=16, max_value=512, ui_group="runtime.ko"),
    "temperatureKo": ConfigFieldSpec("temperatureKo", 0.0, float, min_value=0.0, max_value=1.0, ui_group="runtime.ko"),
    "stepSecondsZh": ConfigFieldSpec("stepSecondsZh", 1.0, float, min_value=0.5, max_value=5.0, ui_group="runtime.zh"),
    "windowSecondsZh": ConfigFieldSpec("windowSecondsZh", 12.0, float, min_value=1.0, max_value=30.0, ui_group="runtime.zh"),
    "sentenceFinalizeAgeZh": ConfigFieldSpec(
        "sentenceFinalizeAgeZh", 3, int, min_value=1, max_value=8, ui_group="runtime.zh"
    ),
    "beamSizeZh": ConfigFieldSpec("beamSizeZh", 3, int, min_value=1, max_value=8, ui_group="runtime.zh"),
    "maxNewTokensZh": ConfigFieldSpec("maxNewTokensZh", 192, int, min_value=16, max_value=512, ui_group="runtime.zh"),
    "temperatureZh": ConfigFieldSpec("temperatureZh", 0.0, float, min_value=0.0, max_value=1.0, ui_group="runtime.zh"),
    "postProcessingProfile": ConfigFieldSpec(
        "postProcessingProfile", "manual", str, allowed=DICTATION_AI_POST_PROCESSING_PROFILES
    ),
    "sentenceBoundaryBackend": ConfigFieldSpec(
        "sentenceBoundaryBackend", "sat", str, allowed=DICTATION_AI_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.stt_result"
    ),
    "sentenceBoundaryModel": ConfigFieldSpec("sentenceBoundaryModel", "sat-3l-sm", str, ui_group="boundary.stt_result"),
    "sentenceBoundaryBackendEn": ConfigFieldSpec(
        "sentenceBoundaryBackendEn", "sat", str, allowed=DICTATION_AI_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.en"
    ),
    "sentenceBoundaryModelEn": ConfigFieldSpec("sentenceBoundaryModelEn", "sat-3l-sm", str, ui_group="boundary.en"),
    "sentenceBoundaryBackendKo": ConfigFieldSpec(
        "sentenceBoundaryBackendKo", "sat", str, allowed=DICTATION_AI_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.ko"
    ),
    "sentenceBoundaryModelKo": ConfigFieldSpec("sentenceBoundaryModelKo", "sat-3l-sm", str, ui_group="boundary.ko"),
    "sentenceBoundaryBackendZh": ConfigFieldSpec(
        "sentenceBoundaryBackendZh", "sat", str, allowed=DICTATION_AI_SENTENCE_BOUNDARY_BACKENDS, ui_group="boundary.zh"
    ),
    "sentenceBoundaryModelZh": ConfigFieldSpec("sentenceBoundaryModelZh", "sat-3l-sm", str, ui_group="boundary.zh"),
    "sentenceBoundaryDevice": ConfigFieldSpec("sentenceBoundaryDevice", "cuda", str, allowed=DICTATION_AI_RUNTIME_DEVICES),
    "sentenceBoundaryComputeType": ConfigFieldSpec("sentenceBoundaryComputeType", "float16", str, allowed=DICTATION_AI_COMPUTE_TYPES),
}

QWEN_ASR_MODEL_ALIASES = {
    "qwen3-asr-0.6b": "Qwen/Qwen3-ASR-0.6B",
    "qwen3-asr-1.7b": "Qwen/Qwen3-ASR-1.7B",
}


def resolve_qwen_asr_model_name(model_name: str) -> str:
    normalized = str(model_name or "").strip()
    return QWEN_ASR_MODEL_ALIASES.get(normalized.lower(), normalized)


def dictation_ai_default(key: str):
    return DICTATION_AI_CONTRACT[key].default


def dictation_ai_defaults() -> dict:
    return {key: spec.default for key, spec in DICTATION_AI_CONTRACT.items()}


def dictation_ai_spec(key: str) -> ConfigFieldSpec:
    return DICTATION_AI_CONTRACT[key]


def dictation_ai_allowed(key: str) -> tuple[object, ...]:
    allowed = DICTATION_AI_CONTRACT[key].allowed
    if allowed is None:
        raise KeyError(f"whisper contract field has no allowed values: {key}")
    return allowed

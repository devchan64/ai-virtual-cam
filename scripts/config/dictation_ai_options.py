from __future__ import annotations

from src.domain.contracts.dictation_ai import (
    dictation_ai_translation_backends_for_language,
    dictation_ai_translation_backends_for_target_language,
    dictation_ai_translation_models_for_backend,
    dictation_ai_translation_targets_for_backend,
)


def dictation_ai_backend_options() -> list[str]:
    return ["faster-whisper", "openai-whisper", "whisper.cpp", "mock"]


def dictation_ai_stt_backend_options(language: str | None = None) -> list[str]:
    normalized_language = str(language or "").strip().lower()
    if normalized_language in {"en", "ko"}:
        return ["faster-whisper", "mock"]
    if normalized_language == "zh":
        return ["faster-whisper", "qwen3-asr-transformers", "mock"]
    return ["faster-whisper", "mock"]


def dictation_ai_stt_backend_runtime_option_keys(backend: str | None = None) -> tuple[str, ...]:
    normalized = str(backend or "").strip().lower()
    if normalized == "faster-whisper":
        return ("compute_type", "beam_size", "max_new_tokens", "temperature")
    if normalized == "mock":
        return ()
    if normalized in {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}:
        return ("compute_type", "max_new_tokens")
    return ()


def dictation_ai_stt_model_options(backend: str | None = None, language: str | None = None) -> list[str]:
    normalized = str(backend or "").strip().lower()
    normalized_language = str(language or "").strip().lower()
    if normalized in {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}:
        return ["qwen3-asr-0.6b", "qwen3-asr-1.7b"] if normalized_language == "zh" else []
    if normalized == "mock":
        return ["mock"]
    return dictation_ai_model_options()


def dictation_ai_model_options() -> list[str]:
    return ["large-v3", "medium", "small", "base", "tiny"]


DICTATION_AI_LANGUAGE_DISPLAY_TO_RAW = {
    "한국어 (ko)": "ko",
    "English (en)": "en",
    "中文 (zh)": "zh",
}
DICTATION_AI_LANGUAGE_RAW_TO_DISPLAY = {value: label for label, value in DICTATION_AI_LANGUAGE_DISPLAY_TO_RAW.items()}


def dictation_ai_language_options() -> list[str]:
    return list(DICTATION_AI_LANGUAGE_DISPLAY_TO_RAW.keys())


def dictation_ai_language_raw_from_display(value: str) -> str:
    raw = DICTATION_AI_LANGUAGE_DISPLAY_TO_RAW.get(str(value).strip())
    if raw is not None:
        return raw
    normalized = str(value).strip().lower()
    if normalized in DICTATION_AI_LANGUAGE_RAW_TO_DISPLAY:
        return normalized
    return normalized


def dictation_ai_language_display_from_raw(value: object) -> str:
    raw = str(value).strip().lower()
    return DICTATION_AI_LANGUAGE_RAW_TO_DISPLAY.get(raw, DICTATION_AI_LANGUAGE_RAW_TO_DISPLAY["ko"])


DICTATION_AI_TRANSLATION_TARGET_DISPLAY_TO_RAW = {
    "English (en)": "en",
    "한국어 (ko)": "ko",
    "中文 (zh)": "zh",
}
DICTATION_AI_TRANSLATION_TARGET_RAW_TO_DISPLAY = {
    value: label for label, value in DICTATION_AI_TRANSLATION_TARGET_DISPLAY_TO_RAW.items()
}


def dictation_ai_translation_target_options() -> list[str]:
    return list(DICTATION_AI_TRANSLATION_TARGET_DISPLAY_TO_RAW.keys())


def dictation_ai_translation_target_raw_from_display(value: str) -> str:
    raw = DICTATION_AI_TRANSLATION_TARGET_DISPLAY_TO_RAW.get(str(value).strip())
    if raw is not None:
        return raw
    normalized = str(value).strip().lower()
    if normalized in DICTATION_AI_TRANSLATION_TARGET_RAW_TO_DISPLAY:
        return normalized
    return normalized


def dictation_ai_translation_target_display_from_raw(value: object) -> str:
    raw = str(value).strip().lower()
    return DICTATION_AI_TRANSLATION_TARGET_RAW_TO_DISPLAY.get(raw, DICTATION_AI_TRANSLATION_TARGET_RAW_TO_DISPLAY["en"])


def dictation_ai_translation_backend_options(language: str | None = None) -> list[str]:
    return list(dictation_ai_translation_backends_for_language(language or "en"))


def dictation_ai_translation_backend_options_for_target(target_language: str | None = None) -> list[str]:
    return list(dictation_ai_translation_backends_for_target_language(target_language or "ko"))


def dictation_ai_translation_target_options_for_backend(language: str | None, backend: str | None) -> list[str]:
    return [
        dictation_ai_translation_target_display_from_raw(target)
        for target in dictation_ai_translation_targets_for_backend(language or "en", backend or "whisper")
    ]


def dictation_ai_translation_model_options(backend: str | None = None) -> list[str]:
    return list(dictation_ai_translation_models_for_backend(backend or "nllb-transformers"))


def dictation_ai_sentence_boundary_backend_options() -> list[str]:
    return ["sat", "mock"]


def dictation_ai_sentence_boundary_model_options(backend: str | None = None) -> list[str]:
    normalized = str(backend or "").strip().lower()
    if normalized == "mock":
        return ["mock"]
    return ["sat-3l-sm", "sat-6l-sm", "sat-12l-sm"]

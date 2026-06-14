from __future__ import annotations

from src.domain.contracts.whisper import (
    whisper_translation_backends_for_language,
    whisper_translation_models_for_backend,
    whisper_translation_targets_for_backend,
)


def whisper_backend_options() -> list[str]:
    return ["faster-whisper", "openai-whisper", "whisper.cpp", "mock"]


def whisper_stt_backend_options(language: str | None = None) -> list[str]:
    normalized_language = str(language or "").strip().lower()
    if normalized_language in {"en", "ko"}:
        return ["faster-whisper", "mock"]
    if normalized_language == "zh":
        return ["faster-whisper", "qwen3-asr-transformers", "mock"]
    return ["faster-whisper", "mock"]


def whisper_stt_backend_runtime_option_keys(backend: str | None = None) -> tuple[str, ...]:
    normalized = str(backend or "").strip().lower()
    if normalized == "faster-whisper":
        return ("compute_type", "beam_size", "max_new_tokens", "temperature")
    if normalized == "mock":
        return ()
    if normalized in {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}:
        return ("compute_type", "max_new_tokens")
    return ()


def whisper_stt_model_options(backend: str | None = None, language: str | None = None) -> list[str]:
    normalized = str(backend or "").strip().lower()
    normalized_language = str(language or "").strip().lower()
    if normalized in {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}:
        return ["qwen3-asr-0.6b", "qwen3-asr-1.7b"] if normalized_language == "zh" else []
    if normalized == "mock":
        return ["mock"]
    return whisper_model_options()


def whisper_model_options() -> list[str]:
    return ["large-v3", "medium", "small", "base", "tiny"]


WHISPER_LANGUAGE_DISPLAY_TO_RAW = {
    "한국어 (ko)": "ko",
    "English (en)": "en",
    "中文 (zh)": "zh",
}
WHISPER_LANGUAGE_RAW_TO_DISPLAY = {value: label for label, value in WHISPER_LANGUAGE_DISPLAY_TO_RAW.items()}


def whisper_language_options() -> list[str]:
    return list(WHISPER_LANGUAGE_DISPLAY_TO_RAW.keys())


def whisper_language_raw_from_display(value: str) -> str:
    raw = WHISPER_LANGUAGE_DISPLAY_TO_RAW.get(str(value).strip())
    if raw is not None:
        return raw
    normalized = str(value).strip().lower()
    if normalized in WHISPER_LANGUAGE_RAW_TO_DISPLAY:
        return normalized
    return normalized


def whisper_language_display_from_raw(value: object) -> str:
    raw = str(value).strip().lower()
    return WHISPER_LANGUAGE_RAW_TO_DISPLAY.get(raw, WHISPER_LANGUAGE_RAW_TO_DISPLAY["ko"])


WHISPER_TRANSLATION_TARGET_DISPLAY_TO_RAW = {
    "English (en)": "en",
    "한국어 (ko)": "ko",
    "中文 (zh)": "zh",
}
WHISPER_TRANSLATION_TARGET_RAW_TO_DISPLAY = {
    value: label for label, value in WHISPER_TRANSLATION_TARGET_DISPLAY_TO_RAW.items()
}


def whisper_translation_target_options() -> list[str]:
    return list(WHISPER_TRANSLATION_TARGET_DISPLAY_TO_RAW.keys())


def whisper_translation_target_raw_from_display(value: str) -> str:
    raw = WHISPER_TRANSLATION_TARGET_DISPLAY_TO_RAW.get(str(value).strip())
    if raw is not None:
        return raw
    normalized = str(value).strip().lower()
    if normalized in WHISPER_TRANSLATION_TARGET_RAW_TO_DISPLAY:
        return normalized
    return normalized


def whisper_translation_target_display_from_raw(value: object) -> str:
    raw = str(value).strip().lower()
    return WHISPER_TRANSLATION_TARGET_RAW_TO_DISPLAY.get(raw, WHISPER_TRANSLATION_TARGET_RAW_TO_DISPLAY["en"])


def whisper_translation_backend_options(language: str | None = None) -> list[str]:
    return list(whisper_translation_backends_for_language(language or "en"))


def whisper_translation_target_options_for_backend(language: str | None, backend: str | None) -> list[str]:
    return [
        whisper_translation_target_display_from_raw(target)
        for target in whisper_translation_targets_for_backend(language or "en", backend or "whisper")
    ]


def whisper_translation_model_options(backend: str | None = None) -> list[str]:
    return list(whisper_translation_models_for_backend(backend or "nllb-transformers"))


def whisper_sentence_boundary_backend_options() -> list[str]:
    return ["sat", "mock"]


def whisper_sentence_boundary_model_options(backend: str | None = None) -> list[str]:
    normalized = str(backend or "").strip().lower()
    if normalized == "mock":
        return ["mock"]
    return ["sat-3l-sm", "sat-6l-sm", "sat-12l-sm"]

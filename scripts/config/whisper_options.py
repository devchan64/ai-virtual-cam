from __future__ import annotations


def whisper_backend_options() -> list[str]:
    return ["faster-whisper", "openai-whisper", "whisper.cpp", "mock"]


def whisper_model_options() -> list[str]:
    return ["large-v3", "medium", "small", "base", "tiny"]


WHISPER_LANGUAGE_DISPLAY_TO_RAW = {
    "자동 감지 (auto)": "auto",
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


def whisper_translation_backend_options() -> list[str]:
    return ["whisper", "nllb-transformers", "mock"]


def whisper_translation_model_options() -> list[str]:
    return ["facebook/nllb-200-distilled-600M"]

_WINDOW_TITLES = {
    "en": {
        "transcript": "ai-virtual-cam Dictation AI Transcript",
        "translation": "ai-virtual-cam Dictation AI Translation",
        "sttStatus": "ai-virtual-cam Dictation AI STT Raw Transcript",
    },
    "ko": {
        "transcript": "ai-virtual-cam 받아쓰기 AI 전사",
        "translation": "ai-virtual-cam 받아쓰기 AI 번역",
        "sttStatus": "ai-virtual-cam 받아쓰기 AI STT 원문창",
    },
}


def dictation_window_title(kind: str, language: str) -> str:
    titles = _WINDOW_TITLES.get(language) or _WINDOW_TITLES["en"]
    return titles.get(kind, _WINDOW_TITLES["en"].get(kind, "ai-virtual-cam"))


def supported_dictation_window_languages() -> set[str]:
    return set(_WINDOW_TITLES)

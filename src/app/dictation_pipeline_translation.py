from __future__ import annotations
"""Final-only translation helpers.

Translation remains downstream of lifecycle finalization. This module should
never decide sentence boundaries or promote partial text; it only filters final
segments and sends them to the configured translation sink.
"""

import time
from typing import Any, Callable

from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _normalized_text,
    _new_text_delta,
    _should_translate_final_sentence,
    _stable_window_text,
)
from src.app.dictation_pipeline_types import SttModelLike, TextTranslatorLike, TranscriptWorkerLike
from src.app.transcript_revision import append_context as _append_committed_text
from src.app.translation_model import TranslationRequest


def collect_translation_jobs(
    *,
    final_segments: list[tuple[int, str]],
    detected: str,
    chunk_index: int,
    count_metric: Callable[[str, int], None],
    worker: TranscriptWorkerLike,
) -> list[tuple[int, str]]:
    translation_jobs: list[tuple[int, str]] = []
    for segment_id, sentence in final_segments:
        if _should_translate_final_sentence(sentence, detected):
            translation_jobs.append((segment_id, sentence))
            continue
        count_metric("translation_skip_final_quality")
        worker._emit(
            "status",
            "받아쓰기 AI 번역 생략: "
            f"chunk={chunk_index} segment_id={segment_id} reason=final_quality "
            f"flags={','.join(_final_sentence_diagnostic_flags(sentence, detected))} "
            f"text={sentence!r}",
            display=False,
        )
    return translation_jobs


def execute_translation_jobs(
    *,
    worker: TranscriptWorkerLike,
    model: SttModelLike,
    text_translator: TextTranslatorLike | None,
    audio: Any,
    language: str,
    detected: str,
    window_seconds: float,
    chunk_index: int,
    translation_jobs: list[tuple[int, str]],
    committed_translation_text: str,
) -> tuple[str, float, bool]:
    if not worker._cfg.translationEnabled or not translation_jobs:
        return committed_translation_text, 0.0, False
    translation_elapsed = 0.0
    target_language = worker._cfg.translationTargetLanguage
    source_language = detected if detected in {"ko", "en", "zh"} else worker._cfg.language
    request_label = "Whisper 백엔드 내장 번역 요청" if text_translator is None else "외부 텍스트 번역 요청"
    for segment_id, sentence in translation_jobs:
        translation_started_at = time.perf_counter()
        worker._emit(
            "status",
            f"{request_label}: chunk={chunk_index} segment_id={segment_id} final=True",
            display=False,
        )
        translated_text = ""
        translated_target_language = target_language
        if text_translator is None:
            translated_segments, _translated_info = model.transcribe(
                audio,
                language=language,
                task="translate",
                beam_size=worker._cfg.beamSize,
                temperature=worker._cfg.temperature,
                max_new_tokens=worker._cfg.maxNewTokens,
                without_timestamps=True,
                condition_on_previous_text=False,
            )
            translated_window_text = " ".join(
                segment.text.strip() for segment in translated_segments if segment.text.strip()
            ).strip()
            translated_stable_text = _stable_window_text(
                translated_window_text,
                0.0,
                window_seconds,
            )
            translated_text = _new_text_delta(committed_translation_text, translated_stable_text)
            translated_target_language = "en"
        else:
            translated_text = text_translator.translate(
                TranslationRequest(
                    text=sentence,
                    source_language=source_language,
                    target_language=translated_target_language,
                )
            )
        translation_elapsed += time.perf_counter() - translation_started_at
        if translated_text:
            worker._emit(
                "status",
                "받아쓰기 AI 번역 진단: "
                f"chunk={chunk_index} segment_id={segment_id} final=True "
                f"source_lang={source_language} target_lang={translated_target_language} "
                f"source_chars={len(_normalized_text(sentence))} "
                f"target_chars={len(_normalized_text(translated_text))} "
                f"backend={worker._cfg.translationBackend} model={worker._cfg.translationModel}",
                display=False,
            )
            committed_translation_text = _append_committed_text(
                committed_translation_text,
                translated_text,
            )
            worker._emit(
                "translation",
                translated_text,
                log_text=f"[{detected}->{translated_target_language}#{segment_id}] {translated_text}",
                final=True,
                segment_id=segment_id,
            )
        else:
            worker._emit(
                "status",
                f"받아쓰기 AI 번역 결과 없음: chunk={chunk_index}",
                display=False,
            )
    return committed_translation_text, translation_elapsed, True

from __future__ import annotations

import time
from typing import Any

from src.app.dictation_pipeline_contracts import AudioEvidence, RecognitionHypothesis
from src.app.dictation_pipeline_types import SttModelLike
from src.app.dictation_pipeline_settings import (
    CJK_CHAR_RANGES,
    MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB,
    MAX_SEGMENT_NO_SPEECH_PROB,
    MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE,
    MIN_SEGMENT_AVG_LOGPROB,
    SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES,
    SEGMENT_LOGPROB_CONFIDENCE_WEIGHT,
    SEGMENT_LOGPROB_SCORE_OFFSET,
    SEGMENT_LOGPROB_SCORE_SCALE,
    SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT,
    STT_CONDITION_ON_PREVIOUS_TEXT,
    STT_STREAM_AUDIO_DTYPE,
    STT_TRANSCRIBE_TASK,
    STT_WITHOUT_TIMESTAMPS,
)
from src.app.dictation_revision_text import _new_text_delta, _normalized_text, _stable_window_text
from src.app.stable_token_detection import analyze_stable_window, combine_boundary_confidence
from src.app.transcript_revision import append_context as _append_committed_text


class SpeechEvidenceToSttHypothesisNode:
    def __init__(self, config: Any) -> None:
        self._cfg = config
        self._previous_window_text = ""

    def recognize(
        self,
        *,
        evidence: AudioEvidence,
        model: SttModelLike,
        stream_block: Any,
        committed_text: str,
        pending_text: str,
    ) -> RecognitionHypothesis:
        started_at = time.perf_counter()
        transcribe_kwargs = {
            "language": self._cfg.language,
            "task": STT_TRANSCRIBE_TASK,
            "beam_size": self._cfg.beamSize,
            "temperature": self._cfg.temperature,
            "max_new_tokens": self._cfg.maxNewTokens,
            "without_timestamps": STT_WITHOUT_TIMESTAMPS,
            "condition_on_previous_text": STT_CONDITION_ON_PREVIOUS_TEXT,
        }
        if getattr(model, "streaming", False):
            transcribe_kwargs["stream_audio"] = stream_block.astype(STT_STREAM_AUDIO_DTYPE, copy=False)
            transcribe_kwargs["stream_chunk_seconds"] = self._cfg.stepSeconds
            transcribe_kwargs["stream_context_seconds"] = self._cfg.windowSeconds

        segments, info = model.transcribe(evidence.audioWindow, **transcribe_kwargs)
        segment_list = list(segments)
        accepted_texts, rejected_reasons, boundary_confidence = self._accepted_segment_texts(segment_list)
        raw_window_text = " ".join(accepted_texts).strip()
        window_text = _normalized_text(raw_window_text)
        stable_text = _stable_window_text(window_text, 0.0, evidence.windowSeconds)
        stable_analysis = analyze_stable_window(self._previous_window_text, window_text, self._cfg.language)
        self._previous_window_text = window_text
        adjusted_boundary_confidence = combine_boundary_confidence(
            boundary_confidence,
            stable_analysis.boundary_confidence,
        )
        delta_base_text = _append_committed_text(committed_text, pending_text)
        delta_text = _new_text_delta(delta_base_text, stable_text)
        detected_language = str(getattr(info, "language", self._cfg.language))

        return RecognitionHypothesis(
            chunkIndex=evidence.chunkIndex,
            language=detected_language,
            rawText=raw_window_text,
            windowText=window_text,
            stableText=stable_text,
            deltaText=delta_text,
            acceptedSegments=tuple(accepted_texts),
            rejectedReasons=tuple(rejected_reasons),
            stability=stable_analysis,
            boundaryConfidence=adjusted_boundary_confidence,
            segmentBoundaryConfidence=boundary_confidence,
            stableBoundaryConfidence=stable_analysis.boundary_confidence,
            elapsedSeconds=time.perf_counter() - started_at,
        )

    def _accepted_segment_texts(self, segments: list[Any]) -> tuple[list[str], list[str], float | None]:
        texts: list[str] = []
        accepted_scores: list[tuple[float, float]] = []
        rejected: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
            no_speech_prob = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
            if no_speech_prob >= MAX_SEGMENT_NO_SPEECH_PROB and not self._should_accept_high_no_speech_segment(
                text, avg_logprob, no_speech_prob
            ):
                rejected.append(f"no_speech text={text!r} prob={no_speech_prob:.2f}")
                continue
            if avg_logprob <= MIN_SEGMENT_AVG_LOGPROB:
                rejected.append(f"low_logprob text={text!r} avg_logprob={avg_logprob:.2f}")
                continue
            texts.append(text)
            accepted_scores.append((avg_logprob, no_speech_prob))
        if not accepted_scores:
            return texts, rejected, None

        avg_logprob = sum(score for score, _ in accepted_scores) / len(accepted_scores)
        avg_no_speech = sum(no_speech for _, no_speech in accepted_scores) / len(accepted_scores)
        logprob_score = max(0.0, min(1.0, (avg_logprob + SEGMENT_LOGPROB_SCORE_OFFSET) / SEGMENT_LOGPROB_SCORE_SCALE))
        no_speech_score = max(0.0, min(1.0, 1.0 - (avg_no_speech / MAX_SEGMENT_NO_SPEECH_PROB)))
        confidence = (
            SEGMENT_LOGPROB_CONFIDENCE_WEIGHT * logprob_score
            + SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT * no_speech_score
        )
        return texts, rejected, confidence

    def _should_accept_high_no_speech_segment(self, text: str, avg_logprob: float, no_speech_prob: float) -> bool:
        language = str(getattr(self._cfg, "language", "en") or "en").strip().lower()
        if language not in SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES:
            return False
        if no_speech_prob >= MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB:
            return False
        if avg_logprob <= MIN_SEGMENT_AVG_LOGPROB:
            return False
        return self._cjk_char_count(text) >= MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE

    def _cjk_char_count(self, text: str) -> int:
        return sum(1 for char in str(text or "") if any(start <= char <= end for start, end in CJK_CHAR_RANGES))

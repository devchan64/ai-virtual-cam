from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable

from src.app.dictation_pipeline_contracts import (
    AudioEvidence,
    RecognitionHypothesis,
    SentenceCandidateSet,
    UncommittedContext,
)
from src.app.dictation_transcript_logic import (
    _new_text_delta,
    _next_revision_confirmation_count,
    _normalized_text,
    _prefer_sentence_revision,
    _sentences_are_revisions,
    _should_reset_revision_age,
    _stable_window_text,
)
from src.app.stable_token_detection import analyze_stable_window, combine_boundary_confidence
from src.app.transcript_revision import append_context as _append_committed_text


AcceptedSegmentTexts = Callable[[Any], tuple[list[str], list[str], float | None]]
SentenceBoundaryProvider = Callable[[str], Any]
MetricCounter = Callable[[str, int], None]


class SpeechEvidenceToSttHypothesisNode:
    def __init__(self, config: Any) -> None:
        self._cfg = config
        self._previous_window_text = ""

    def recognize(
        self,
        *,
        evidence: AudioEvidence,
        model: Any,
        stream_block: Any,
        accepted_segment_texts: AcceptedSegmentTexts,
        committed_text: str,
        pending_text: str,
    ) -> RecognitionHypothesis:
        started_at = time.perf_counter()
        transcribe_kwargs = {
            "language": self._cfg.language,
            "task": "transcribe",
            "beam_size": self._cfg.beamSize,
            "temperature": self._cfg.temperature,
            "max_new_tokens": self._cfg.maxNewTokens,
            "without_timestamps": True,
            "condition_on_previous_text": False,
        }
        if getattr(model, "streaming", False):
            transcribe_kwargs["stream_audio"] = stream_block.astype("float32", copy=False)
            transcribe_kwargs["stream_chunk_seconds"] = self._cfg.stepSeconds
            transcribe_kwargs["stream_context_seconds"] = self._cfg.windowSeconds

        segments, info = model.transcribe(evidence.audioWindow, **transcribe_kwargs)
        segment_list = list(segments)
        accepted_texts, rejected_reasons, boundary_confidence = accepted_segment_texts(segment_list)
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


class SttHypothesisToSentenceCandidateNode:
    def __init__(self, boundary_provider: SentenceBoundaryProvider) -> None:
        self._boundary_provider = boundary_provider

    def interpret(
        self,
        *,
        hypothesis: RecognitionHypothesis,
        context: UncommittedContext,
    ) -> SentenceCandidateSet:
        detector = self._boundary_provider(hypothesis.language)
        boundary_result = detector.split(
            context.pendingText,
            hypothesis.deltaText,
            hypothesis.language,
            boundary_confidence=hypothesis.boundaryConfidence,
        )
        completed = tuple(_normalized_text(sentence) for sentence in boundary_result.completed)
        return SentenceCandidateSet(
            chunkIndex=hypothesis.chunkIndex,
            language=hypothesis.language,
            completedCandidates=completed,
            pendingTail=_normalized_text(boundary_result.pending),
            priorPendingText=context.pendingText,
            boundarySignals={
                "boundary_count": boundary_result.boundary_count,
                "soft_boundary_count": boundary_result.soft_boundary_count,
                "end_mark_count": boundary_result.end_mark_count,
                "right_context_start_count": boundary_result.right_context_start_count,
                "boundary_confidence": hypothesis.boundaryConfidence
                if hypothesis.boundaryConfidence is not None
                else "n/a",
                "boundary_backend": getattr(detector, "backend", ""),
            },
            textDelta=hypothesis.deltaText,
        )


class SentenceCandidateCommitBufferNode:
    def __init__(self, max_size: int) -> None:
        self._queue: deque[dict[str, object]] = deque()
        self._max_size = max_size

    def __len__(self) -> int:
        return len(self._queue)

    def enqueue_or_revision(
        self,
        *,
        candidate: str,
        forced: bool,
        chunk_index: int,
        stable_analysis: Any,
        count_metric: MetricCounter,
        count_segment_state: MetricCounter,
    ) -> None:
        for entry in self._queue:
            queued_sentence = str(entry["sentence"])
            if not _sentences_are_revisions(queued_sentence, candidate):
                continue
            preferred = _prefer_sentence_revision(queued_sentence, candidate)
            reset_age = _should_reset_revision_age(
                queued_sentence,
                preferred,
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            )
            entry["sentence"] = preferred
            entry["confirmations"] = _next_revision_confirmation_count(
                queued_sentence,
                preferred,
                int(entry["confirmations"]),
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            )
            entry["age"] = 0 if reset_age else int(entry["age"]) + 1
            entry["forced"] = bool(entry["forced"]) or forced
            entry["deferred_age_chunk"] = chunk_index
            count_metric("stage_queue_revision", 1)
            if reset_age:
                count_metric("stage_queue_revision_age_reset", 1)
            count_metric("stage_age_tick", 1)
            return

        if len(self._queue) >= self._max_size:
            self._queue.popleft()
            count_metric("stage_queue_drop_oldest", 1)
        self._queue.append(
            {
                "sentence": candidate,
                "confirmations": 1,
                "age": 0,
                "forced": forced,
                "deferred_age_chunk": -1,
            }
        )
        count_metric("stage_queue_enqueue", 1)
        count_segment_state("staged", 1)

    def promote_if_idle(
        self,
        *,
        active_sentence: str,
        chunk_index: int,
        count_metric: MetricCounter,
        count_segment_state: MetricCounter,
    ) -> dict[str, object] | None:
        if active_sentence or not self._queue:
            return None
        entry = self._queue.popleft()
        entry["deferred_age_chunk"] = chunk_index
        count_metric("stage_queue_promote", 1)
        count_metric("stage_start", 1)
        count_segment_state("staged", 1)
        return entry

from __future__ import annotations
"""Chunk-level candidate interpretation helpers for the realtime dictation loop."""

from dataclasses import dataclass
from typing import Callable

from src.app.dictation.pipeline_contracts import RecognitionHypothesis, UncommittedContext
from src.app.dictation_core.dictation_transcript_logic import (
    _coalesce_completed_short_no_end_fragments,
    _normalized_text,
    _should_allow_no_text_stage_aging,
)


@dataclass(frozen=True, slots=True)
class ChunkSentenceFlowResult:
    pending_transcript_text: str
    pending_chunks: int
    no_text_stage_skip_chunks: int
    completed_sentences: list[str]
    final_segments: list[tuple[int, str]]
    boundary_complete: int
    boundary_soft: int
    boundary_end_marks: int
    boundary_right_context_starts: int


def process_chunk_sentence_flow(
    *,
    candidate_node: object,
    hypothesis: RecognitionHypothesis,
    detected: str,
    text: str,
    chunk_index: int,
    committed_text: str,
    pending_transcript_text: str,
    pending_chunks: int,
    no_text_stage_skip_chunks: int,
    active_stage_sentence: str,
    staged_queue_sentences: tuple[str, ...],
    window_text: str,
    stable_text: str,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    stage_completed_sentence: Callable[..., list[tuple[int, str]]],
    finalize_right_context_staged_sentences: Callable[[str], list[tuple[int, str]]],
    age_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    suppress_stale_no_text_stage: Callable[[str, int], int],
    consume_committed_prefix: Callable[[str, str], str],
    emit_status: Callable[[str], None],
) -> ChunkSentenceFlowResult:
    completed_sentences: list[str] = []
    final_segments: list[tuple[int, str]] = []
    boundary_complete = 0
    boundary_soft = 0
    boundary_end_marks = 0
    boundary_right_context_starts = 0
    allow_no_text_stage_aging = _should_allow_no_text_stage_aging(
        active_stage_sentence,
        detected,
        staged_queue_sentences,
    )

    if text:
        no_text_stage_skip_chunks = 0
        prior_pending_transcript_text = pending_transcript_text
        candidate_set = candidate_node.interpret(
            hypothesis=hypothesis,
            context=UncommittedContext(
                committedText=committed_text,
                pendingText=pending_transcript_text,
            ),
        )
        completed_sentences = list(candidate_set.completedCandidates)
        coalesced_completed_sentences = list(
            _coalesce_completed_short_no_end_fragments(completed_sentences, detected)
        )
        if coalesced_completed_sentences != completed_sentences:
            count_metric("completed_short_no_end_coalesced", 1)
            count_metric(
                "completed_short_no_end_coalesced_delta",
                len(completed_sentences) - len(coalesced_completed_sentences),
            )
            completed_sentences = coalesced_completed_sentences
        pending_transcript_text = candidate_set.pendingTail
        boundary_complete = int(candidate_set.boundarySignals.get("boundary_count", 0))
        boundary_soft = int(candidate_set.boundarySignals.get("soft_boundary_count", 0))
        boundary_end_marks = int(candidate_set.boundarySignals.get("end_mark_count", 0))
        boundary_right_context_starts = int(candidate_set.boundarySignals.get("right_context_start_count", 0))
        if boundary_end_marks:
            count_metric("boundary_end_marks", boundary_end_marks)
        if boundary_right_context_starts:
            count_metric("boundary_right_context_starts", boundary_right_context_starts)
        if completed_sentences:
            pending_chunks = 0
        elif pending_transcript_text:
            pending_chunks += 1
        for sentence_index, sentence in enumerate(completed_sentences):
            produced_segments = stage_completed_sentence(
                sentence,
                detected,
                pending_transcript_text=pending_transcript_text,
                later_completed_sentences=completed_sentences[sentence_index + 1 :],
                prior_pending_text=prior_pending_transcript_text,
            )
            final_segments.extend(produced_segments)
            for _segment_id, produced_sentence in produced_segments:
                pending_transcript_text = consume_committed_prefix(pending_transcript_text, produced_sentence)
                if not pending_transcript_text:
                    pending_chunks = 0
        if completed_sentences:
            final_segments.extend(finalize_right_context_staged_sentences(detected))
            final_segments.extend(age_staged_sentence(detected, pending_transcript_text))
        if pending_transcript_text:
            count_segment_state("pending", 1)
            emit_status(
                "받아쓰기 AI pending tail: "
                f"chunk={chunk_index} language={detected} text={pending_transcript_text!r}"
            )
        elif not completed_sentences:
            final_segments.extend(age_staged_sentence(detected, pending_transcript_text))
    else:
        preview_chars = max(0, len(_normalized_text(window_text)) - len(_normalized_text(stable_text)))
        emit_status(f"받아쓰기 AI 전사 결과 없음: chunk={chunk_index} preview_chars={preview_chars}")
        if pending_transcript_text:
            count_segment_state("pending", 1)
            pending_chunks += 1
        count_metric("stage_age_no_text_skipped", 1)
        if active_stage_sentence and not pending_transcript_text and allow_no_text_stage_aging:
            final_segments.extend(age_staged_sentence(detected, pending_transcript_text))
            if final_segments:
                no_text_stage_skip_chunks = 0
            else:
                no_text_stage_skip_chunks += 1
                no_text_stage_skip_chunks = suppress_stale_no_text_stage(detected, no_text_stage_skip_chunks)
        else:
            no_text_stage_skip_chunks = 0

    return ChunkSentenceFlowResult(
        pending_transcript_text=pending_transcript_text,
        pending_chunks=pending_chunks,
        no_text_stage_skip_chunks=no_text_stage_skip_chunks,
        completed_sentences=completed_sentences,
        final_segments=final_segments,
        boundary_complete=boundary_complete,
        boundary_soft=boundary_soft,
        boundary_end_marks=boundary_end_marks,
        boundary_right_context_starts=boundary_right_context_starts,
    )

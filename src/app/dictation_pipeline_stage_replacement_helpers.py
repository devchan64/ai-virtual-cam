from __future__ import annotations
"""Replacement-path policy helpers for staged sentence lifecycle."""

from typing import Callable

from src.app.dictation_revision_progression import _diagnostic_tail, _sentence_end_count
from src.app.dictation_pipeline_stage_state_helpers import tick_stage_age_once
from src.app.dictation_transcript_logic import (
    _replacement_decision_reason,
    _staged_sentence_required_confirmations,
    _should_defer_unconfirmed_replacement,
    _should_finalize_before_replacement,
    _should_finalize_replaced_sentence,
    _should_stage_boundary_candidate,
)
from src.app.dictation_pipeline_types import ActiveStage, CommitBufferNode, TranscriptWorkerLike


def _handle_deferred_replacement(
    *,
    active_stage: ActiveStage,
    candidate: str,
    forced: bool,
    detected: str,
    replacement_reason: str,
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    queue_staged_sentence: Callable[[str, bool], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    suppress_active_stage_for_quality: Callable[..., None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
    sentence_max_age_chunks: Callable[[bool, int], int],
    stage_quality_block_age_limit: Callable[[str, str, bool, int], int],
    commit_buffer_node: CommitBufferNode,
) -> list[tuple[int, str]]:
    queue_staged_sentence(candidate, forced)
    count_metric("stage_replace_deferred")
    tick_stage_age_once(active_stage, chunk_index=chunk_index, count_metric=count_metric)
    worker._emit(
        "status",
        "받아쓰기 AI stage 교체 보류: "
        f"chunk={chunk_index} decision={replacement_reason} staged_confirmations={active_stage.confirmations} "
        f"staged_age={active_stage.age} staged_tail={_diagnostic_tail(active_stage.sentence)} "
        f"candidate_tail={_diagnostic_tail(candidate)}",
        display=False,
    )
    if (
        active_stage.age >= sentence_max_age_chunks(active_stage.forced, sentence_finalize_age)
        and _should_finalize_before_replacement(
            active_stage.sentence,
            detected,
            active_stage.confirmations,
            active_stage.age,
            sentence_finalize_age,
            active_stage.forced,
            commit_buffer_node.queued_sentences(),
        )
    ):
        count_metric("stage_age_finalize")
        worker._emit(
            "status",
            "받아쓰기 AI stage 보류 후보 순서 확정: "
            f"chunk={chunk_index} decision={replacement_reason} staged_confirmations={active_stage.confirmations} "
            f"staged_age={active_stage.age} staged_tail={_diagnostic_tail(active_stage.sentence)} "
            f"candidate_tail={_diagnostic_tail(candidate)}",
            display=False,
        )
        finalized = finalize_staged_sentence(
            detected,
            "aged_forced" if active_stage.forced else "aged",
        )
        promote_next_staged_sentence(detected)
        return finalized
    if active_stage.age >= stage_quality_block_age_limit(
        active_stage.sentence,
        detected,
        active_stage.forced,
        sentence_finalize_age,
    ):
        suppress_active_stage_for_quality(
            detected,
            metric_name="stage_age_quality_blocked",
            status_prefix="받아쓰기 AI stage 보류 후보 품질 차단",
            extra_status=(
                f"decision={replacement_reason} staged_confirmations={active_stage.confirmations} "
                f"staged_age={active_stage.age} "
            ),
        )
    return []


def _finish_replacement_transition(
    *,
    active_stage: ActiveStage,
    candidate: str,
    forced: bool,
    detected: str,
    replacement_reason: str,
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    queue_staged_sentence: Callable[[str, bool], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    start_staged_sentence: Callable[[str, str, bool], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
    commit_buffer_node: CommitBufferNode,
) -> list[tuple[int, str]]:
    worker._emit(
        "status",
        "받아쓰기 AI stage 교체: "
        f"chunk={chunk_index} reason=revision_false decision={replacement_reason} forced={forced} "
        f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} "
        f"staged_tail={_diagnostic_tail(active_stage.sentence)} candidate_tail={_diagnostic_tail(candidate)}",
        display=False,
    )
    if _should_finalize_replaced_sentence(
        active_stage.sentence,
        candidate,
        detected,
        active_stage.confirmations,
        active_stage.forced,
        active_stage.age,
        sentence_finalize_age,
    ):
        finalized = finalize_staged_sentence(detected, f"replaced_{replacement_reason}")
    elif _should_finalize_before_replacement(
        active_stage.sentence,
        detected,
        active_stage.confirmations,
        active_stage.age,
        sentence_finalize_age,
        active_stage.forced,
        commit_buffer_node.queued_sentences(),
    ):
        count_metric("stage_finalize_before_replace")
        finalized = finalize_staged_sentence(detected, "next_completed")
    else:
        count_metric("stage_replaced_unconfirmed")
        count_segment_state("suppressed")
        required_confirmations = _staged_sentence_required_confirmations(
            active_stage.sentence,
            active_stage.forced,
        )
        worker._emit(
            "status",
            "받아쓰기 AI stage 미확정 교체: "
            f"chunk={chunk_index} decision={replacement_reason} "
            f"staged_confirmations={active_stage.confirmations} required={required_confirmations} "
            f"staged_forced={active_stage.forced} staged_tail={_diagnostic_tail(active_stage.sentence)} "
            f"candidate_tail={_diagnostic_tail(candidate)}",
            display=False,
        )
        finalized = []
        active_stage.clear()
    if not active_stage.sentence:
        promote_next_staged_sentence(detected)
    if active_stage.sentence:
        queue_staged_sentence(candidate, forced)
        return finalized
    start_staged_sentence(candidate, detected, forced)
    return finalized


def handle_replacement_candidate(
    *,
    active_stage: ActiveStage,
    candidate: str,
    detected: str,
    forced: bool,
    prior_pending_text: str,
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    queue_staged_sentence: Callable[[str, bool], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    suppress_active_stage_for_quality: Callable[..., None],
    start_staged_sentence: Callable[[str, str, bool], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
    sentence_max_age_chunks: Callable[[bool, int], int],
    stage_quality_block_age_limit: Callable[[str, str, bool, int], int],
    strip_prior_pending_prefix_from_final: Callable[[str, str], str],
    commit_buffer_node: CommitBufferNode,
) -> list[tuple[int, str]]:
    count_metric("stage_replace")
    replacement_reason = _replacement_decision_reason(
        active_stage.sentence,
        candidate,
        active_stage.confirmations,
        active_stage.forced,
        active_stage.age,
        sentence_finalize_age,
    )
    count_metric(f"stage_replace_decision_{replacement_reason}")
    if _should_defer_unconfirmed_replacement(replacement_reason):
        return _handle_deferred_replacement(
            active_stage=active_stage,
            candidate=candidate,
            forced=forced,
            detected=detected,
            replacement_reason=replacement_reason,
            chunk_index=chunk_index,
            sentence_finalize_age=sentence_finalize_age,
            count_metric=count_metric,
            queue_staged_sentence=queue_staged_sentence,
            finalize_staged_sentence=finalize_staged_sentence,
            suppress_active_stage_for_quality=suppress_active_stage_for_quality,
            promote_next_staged_sentence=promote_next_staged_sentence,
            worker=worker,
            sentence_max_age_chunks=sentence_max_age_chunks,
            stage_quality_block_age_limit=stage_quality_block_age_limit,
            commit_buffer_node=commit_buffer_node,
        )
    allow_same_chunk_suffix_replacement = (
        replacement_reason == "duplicate_or_suffix"
        and _sentence_end_count(candidate) > 0
        and _should_stage_boundary_candidate(candidate, detected)
    )
    if active_stage.deferredAgeChunk == chunk_index and not allow_same_chunk_suffix_replacement:
        queue_staged_sentence(candidate, forced)
        count_metric("stage_replace_deferred_same_chunk")
        worker._emit(
            "status",
            "받아쓰기 AI stage 교체 보류: "
            f"chunk={chunk_index} decision={replacement_reason} same_chunk=True "
            f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} "
            f"staged_tail={_diagnostic_tail(active_stage.sentence)} "
            f"candidate_tail={_diagnostic_tail(candidate)}",
            display=False,
        )
        return []
    if allow_same_chunk_suffix_replacement:
        count_metric("stage_replace_same_chunk_suffix_allowed")
        stripped_stage = strip_prior_pending_prefix_from_final(
            active_stage.sentence,
            prior_pending_text,
        )
        if stripped_stage != active_stage.sentence:
            active_stage.sentence = stripped_stage
            count_metric("stage_replace_same_chunk_prior_pending_prefix_stripped")
    return _finish_replacement_transition(
        active_stage=active_stage,
        candidate=candidate,
        forced=forced,
        detected=detected,
        replacement_reason=replacement_reason,
        chunk_index=chunk_index,
        sentence_finalize_age=sentence_finalize_age,
        count_metric=count_metric,
        count_segment_state=count_segment_state,
        queue_staged_sentence=queue_staged_sentence,
        finalize_staged_sentence=finalize_staged_sentence,
        start_staged_sentence=start_staged_sentence,
        promote_next_staged_sentence=promote_next_staged_sentence,
        worker=worker,
        commit_buffer_node=commit_buffer_node,
    )

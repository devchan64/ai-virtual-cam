from __future__ import annotations
"""Chunk-to-chunk staged sentence maintenance helpers.

These helpers handle lifecycle actions that happen after initial candidate
classification: staged aging, right-context finalization, and no-text stale
cleanup. They are distinct from revision/replacement branching because they run
on chunk progression rather than on a newly completed candidate.
"""

from typing import Callable

from src.app.dictation_core.dictation_revision_progression import _diagnostic_tail, _should_age_staged_sentence
from src.app.dictation.pipeline_stage_state_helpers import tick_stage_age
from src.app.dictation_core.dictation_transcript_logic import (
    _stage_quality_block_age_limit,
    _staged_sentence_required_confirmations,
    _should_confirm_staged_sentence,
    _should_finalize_before_replacement,
    _should_finalize_with_right_context,
)
from src.app.dictation.pipeline_types import ActiveStage, CommitBufferNode, TranscriptWorkerLike


def age_staged_sentence(
    *,
    active_stage: ActiveStage,
    commit_buffer_node: CommitBufferNode,
    sentence_finalize_age: int,
    pending_text: str,
    detected: str,
    chunk_index: int,
    count_metric: Callable[[str, int], None],
    finalize_staged_sentence: Callable[[str, str], list[str]],
    suppress_active_stage_for_quality: Callable[..., None],
    should_defer_short_closed_queue_quality_block: Callable[[str], bool],
    worker: TranscriptWorkerLike,
    sentence_max_age_chunks: Callable[[bool, int], int],
) -> list[str]:
    if not active_stage.sentence:
        return []
    if not _should_age_staged_sentence(active_stage.sentence, pending_text):
        count_metric("stage_age_hold")
        worker._emit(
            "status",
            "받아쓰기 AI staged aging 보류: "
            f"chunk={chunk_index} staged={active_stage.sentence!r} pending={pending_text!r}",
            display=False,
        )
        return []
    tick_stage_age(active_stage, chunk_index=chunk_index, count_metric=count_metric)
    max_age = sentence_max_age_chunks(active_stage.forced, sentence_finalize_age)
    if active_stage.age < max_age:
        return []
    if _should_confirm_staged_sentence(
        active_stage.sentence,
        active_stage.confirmations,
        active_stage.forced,
    ):
        count_metric("stage_confirmed_before_age_queue")
        return finalize_staged_sentence(
            detected,
            "confirmed_forced" if active_stage.forced else "confirmed",
        )
    if not _should_finalize_before_replacement(
        active_stage.sentence,
        detected,
        active_stage.confirmations,
        active_stage.age,
        sentence_finalize_age,
        active_stage.forced,
        commit_buffer_node.queued_sentences(),
    ):
        if active_stage.age < _stage_quality_block_age_limit(
            active_stage.sentence,
            detected,
            active_stage.forced,
            sentence_finalize_age,
        ):
            return []
        if should_defer_short_closed_queue_quality_block(detected):
            count_metric("stage_age_quality_block_deferred_short_queue")
            return []
        suppress_active_stage_for_quality(
            detected,
            metric_name="stage_age_quality_blocked",
            status_prefix="받아쓰기 AI staged age 확정 차단",
        )
        return []
    count_metric("stage_age_finalize")
    return finalize_staged_sentence(
        detected,
        "aged_forced" if active_stage.forced else "aged",
    )


def finalize_right_context_staged_sentences(
    *,
    active_stage: ActiveStage,
    commit_buffer_node: CommitBufferNode,
    detected: str,
    chunk_index: int,
    count_metric: Callable[[str, int], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
) -> list[tuple[int, str]]:
    final_segments: list[tuple[int, str]] = []
    while (
        active_stage.sentence
        and commit_buffer_node.queued_sentences()
        and active_stage.deferredAgeChunk < chunk_index
        and _should_finalize_with_right_context(
            active_stage.sentence,
            detected,
            commit_buffer_node.queued_sentences(),
            promoted_from_queue_same_chunk=active_stage.queuePromotedChunk == chunk_index,
        )
    ):
        count_metric("stage_finalize_right_context")
        produced = finalize_staged_sentence(detected, "right_context")
        if not produced:
            break
        final_segments.extend(produced)
    return final_segments


def suppress_stale_no_text_stage(
    *,
    active_stage: ActiveStage,
    detected: str,
    chunk_index: int,
    no_text_stage_skip_chunks: int,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
    no_text_stale_stage_suppress_chunks: Callable[[], int],
) -> int:
    if not active_stage.sentence:
        return 0
    required_confirmations = _staged_sentence_required_confirmations(
        active_stage.sentence,
        active_stage.forced,
    )
    if active_stage.confirmations >= required_confirmations:
        return no_text_stage_skip_chunks
    if no_text_stage_skip_chunks < no_text_stale_stage_suppress_chunks():
        return no_text_stage_skip_chunks
    count_metric("stage_no_text_stale_suppressed")
    count_segment_state("suppressed")
    worker._emit(
        "status",
        "받아쓰기 AI 무텍스트 stale stage 폐기: "
        f"chunk={chunk_index} no_text_chunks={no_text_stage_skip_chunks} "
        f"staged_confirmations={active_stage.confirmations}/{required_confirmations} "
        f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
        display=False,
    )
    active_stage.clear()
    promote_next_staged_sentence(detected)
    return 0

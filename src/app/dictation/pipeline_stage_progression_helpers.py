from __future__ import annotations
"""Progression-oriented helper functions for StageLoopFacade."""

from src.app.dictation.pipeline_stage_actions import (
    age_staged_sentence as _age_staged_sentence,
    finalize_right_context_staged_sentences as _finalize_right_context_staged_sentences,
    suppress_stale_no_text_stage as _suppress_stale_no_text_stage,
)
from src.app.dictation.pipeline_stage_coordinator import (
    handle_replacement_candidate as _handle_replacement_candidate,
    handle_revision_candidate as _handle_revision_candidate,
)
from src.app.dictation.pipeline_stage_facade_support import StageFacadeContext
from src.app.dictation.pipeline_stage_finalize_helpers import (
    finalize_staged_sentence,
    promote_next_staged_sentence,
    queue_staged_sentence,
    start_staged_sentence,
    suppress_active_stage_for_quality,
)
from src.app.dictation.pipeline_stage_runtime import prepare_stage_candidate as _prepare_stage_candidate
from src.app.dictation_core.dictation_revision_text import _sentences_are_revisions
from src.app.dictation_core.dictation_transcript_logic import (
    _sentence_max_age_chunks,
    _stage_quality_block_age_limit,
    _should_confirm_staged_sentence,
    _should_defer_short_closed_queue_quality_block,
    _should_split_terminal_tail_revision,
    _strip_prior_pending_prefix_from_final,
    _strip_prior_pending_prefix_revision,
)


def prepare_stage_candidate(
    ctx: StageFacadeContext,
    sentence: str,
    detected: str,
    *,
    later_completed_sentences: list[str] | tuple[str, ...],
    prior_pending_text: str,
    pending_transcript_text: str,
) -> str | None:
    return _prepare_stage_candidate(
        active_stage=ctx.active_stage,
        commit_buffer_node=ctx.commit_buffer_node,
        committed_text=ctx.committed_text,
        pending_transcript_text=pending_transcript_text,
        prior_pending_text=prior_pending_text,
        sentence=sentence,
        detected=detected,
        later_completed_sentences=later_completed_sentences,
        recent_transcripts=tuple(ctx.loop_support.recent_transcripts),
        chunk_index=ctx.chunk_index,
        sentence_finalize_age=ctx.sentence_finalize_age,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        count_recent_final_stable_internal_suppression=ctx.count_recent_final_stable_internal_suppression,
        suppress_active_stage_for_quality=lambda language, **kwargs: suppress_active_stage_for_quality(
            ctx,
            language,
            **kwargs,
        ),
        worker=ctx.worker,
        strip_prior_pending_prefix_revision=_strip_prior_pending_prefix_revision,
        stage_quality_block_age_limit=_stage_quality_block_age_limit,
    )


def handle_revision_candidate(
    ctx: StageFacadeContext,
    candidate: str,
    detected: str,
    *,
    forced: bool,
    later_completed_sentences: list[str] | tuple[str, ...],
) -> list[tuple[int, str]]:
    return _handle_revision_candidate(
        active_stage=ctx.active_stage,
        candidate=candidate,
        detected=detected,
        forced=forced,
        later_completed_sentences=later_completed_sentences,
        stable_analysis=ctx.require_stable_analysis(),
        chunk_index=ctx.chunk_index,
        sentence_finalize_age=ctx.sentence_finalize_age,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        queue_staged_sentence=lambda candidate_text, candidate_forced: queue_staged_sentence(
            ctx,
            candidate_text,
            candidate_forced,
        ),
        finalize_staged_sentence=lambda language, reason: finalize_staged_sentence(ctx, language, reason),
        suppress_active_stage_for_quality=lambda language, **kwargs: suppress_active_stage_for_quality(
            ctx,
            language,
            **kwargs,
        ),
        worker=ctx.worker,
        sentence_max_age_chunks=_sentence_max_age_chunks,
        stage_quality_block_age_limit=_stage_quality_block_age_limit,
        commit_buffer_node=ctx.commit_buffer_node,
    )


def handle_replacement_candidate(
    ctx: StageFacadeContext,
    candidate: str,
    detected: str,
    *,
    forced: bool,
    prior_pending_text: str,
) -> list[tuple[int, str]]:
    return _handle_replacement_candidate(
        active_stage=ctx.active_stage,
        candidate=candidate,
        detected=detected,
        forced=forced,
        prior_pending_text=prior_pending_text,
        chunk_index=ctx.chunk_index,
        sentence_finalize_age=ctx.sentence_finalize_age,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        queue_staged_sentence=lambda candidate_text, candidate_forced: queue_staged_sentence(
            ctx,
            candidate_text,
            candidate_forced,
        ),
        finalize_staged_sentence=lambda language, reason: finalize_staged_sentence(ctx, language, reason),
        suppress_active_stage_for_quality=lambda language, **kwargs: suppress_active_stage_for_quality(
            ctx,
            language,
            **kwargs,
        ),
        start_staged_sentence=lambda candidate_text, language, candidate_forced: start_staged_sentence(
            ctx,
            candidate_text,
            language,
            candidate_forced,
        ),
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
        sentence_max_age_chunks=_sentence_max_age_chunks,
        stage_quality_block_age_limit=_stage_quality_block_age_limit,
        strip_prior_pending_prefix_from_final=_strip_prior_pending_prefix_from_final,
        commit_buffer_node=ctx.commit_buffer_node,
    )


def stage_completed_sentence(
    ctx: StageFacadeContext,
    sentence: str,
    detected: str,
    *,
    pending_transcript_text: str,
    forced: bool = False,
    later_completed_sentences: list[str] | tuple[str, ...] = (),
    prior_pending_text: str = "",
) -> list[tuple[int, str]]:
    candidate = prepare_stage_candidate(
        ctx,
        sentence,
        detected,
        later_completed_sentences=later_completed_sentences,
        prior_pending_text=prior_pending_text,
        pending_transcript_text=pending_transcript_text,
    )
    if candidate is None:
        return []
    if not ctx.active_stage.sentence:
        promote_next_staged_sentence(ctx, detected)
    if not ctx.active_stage.sentence:
        start_staged_sentence(ctx, candidate, detected, forced)
        return []
    if _should_confirm_staged_sentence(
        ctx.active_stage.sentence,
        ctx.active_stage.confirmations,
        ctx.active_stage.forced,
    ) and _should_split_terminal_tail_revision(ctx.active_stage.sentence, candidate):
        ctx.count_metric("stage_revision_terminal_tail_split")
        finalized = finalize_staged_sentence(ctx, detected, "terminal_tail_revision_split")
        if not ctx.active_stage.sentence:
            promote_next_staged_sentence(ctx, detected)
        if ctx.active_stage.sentence:
            queue_staged_sentence(ctx, candidate, forced)
            return finalized
        start_staged_sentence(ctx, candidate, detected, forced)
        return finalized
    if _sentences_are_revisions(ctx.active_stage.sentence, candidate):
        return handle_revision_candidate(
            ctx,
            candidate,
            detected,
            forced=forced,
            later_completed_sentences=later_completed_sentences,
        )
    return handle_replacement_candidate(
        ctx,
        candidate,
        detected,
        forced=forced,
        prior_pending_text=prior_pending_text,
    )


def age_staged_sentence(
    ctx: StageFacadeContext,
    detected: str,
    pending_text: str = "",
) -> list[tuple[int, str]]:
    return _age_staged_sentence(
        active_stage=ctx.active_stage,
        commit_buffer_node=ctx.commit_buffer_node,
        sentence_finalize_age=ctx.sentence_finalize_age,
        pending_text=pending_text,
        detected=detected,
        chunk_index=ctx.chunk_index,
        count_metric=ctx.count_metric,
        finalize_staged_sentence=lambda language, reason: finalize_staged_sentence(ctx, language, reason),
        suppress_active_stage_for_quality=lambda language, **kwargs: suppress_active_stage_for_quality(
            ctx,
            language,
            **kwargs,
        ),
        should_defer_short_closed_queue_quality_block=lambda language: _should_defer_short_closed_queue_quality_block(
            ctx.active_stage.sentence,
            language,
            ctx.commit_buffer_node.queued_sentences(),
            ctx.active_stage.confirmations,
        ),
        worker=ctx.worker,
        sentence_max_age_chunks=_sentence_max_age_chunks,
    )


def finalize_right_context_staged_sentences(
    ctx: StageFacadeContext,
    detected: str,
) -> list[tuple[int, str]]:
    return _finalize_right_context_staged_sentences(
        active_stage=ctx.active_stage,
        commit_buffer_node=ctx.commit_buffer_node,
        detected=detected,
        chunk_index=ctx.chunk_index,
        count_metric=ctx.count_metric,
        finalize_staged_sentence=lambda language, reason: finalize_staged_sentence(ctx, language, reason),
    )


def suppress_stale_no_text_stage(
    ctx: StageFacadeContext,
    detected: str,
    no_text_stage_skip_chunks: int,
) -> int:
    return _suppress_stale_no_text_stage(
        active_stage=ctx.active_stage,
        detected=detected,
        chunk_index=ctx.chunk_index,
        no_text_stage_skip_chunks=no_text_stage_skip_chunks,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
        no_text_stale_stage_suppress_chunks=ctx.no_text_stale_stage_suppress_chunks,
    )

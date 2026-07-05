from __future__ import annotations
"""Finalize-oriented helper functions for StageLoopFacade."""

from src.app.dictation.pipeline_stage_facade_support import StageFacadeContext
from src.app.dictation.pipeline_settings import (
    aged_queue_backlog_promotion_extra_age as _aged_queue_backlog_promotion_extra_age,
)
from src.app.dictation.pipeline_stage_runtime import (
    apply_delta_finalize_guard as _apply_delta_finalize_guard,
    apply_recent_final_finalize_adjustment as _apply_recent_final_finalize_adjustment,
    emit_finalized_sentence as _emit_finalized_sentence,
    finalize_staged_sentence as _finalize_staged_sentence,
    preserve_staged_output_when_delta_fragment,
    promote_next_staged_sentence as _promote_next_staged_sentence,
    start_staged_sentence as _start_staged_sentence,
    suppress_active_stage_for_quality as _suppress_active_stage_for_quality,
    suppress_finalize_candidate as _suppress_finalize_candidate,
)


def promote_next_staged_sentence(ctx: StageFacadeContext, detected: str) -> None:
    _promote_next_staged_sentence(
        active_stage=ctx.active_stage,
        commit_buffer_node=ctx.commit_buffer_node,
        detected=detected,
        chunk_index=ctx.chunk_index,
        recent_transcripts=tuple(ctx.loop_support.recent_transcripts),
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        count_recent_final_stable_internal_suppression=ctx.count_recent_final_stable_internal_suppression,
        staged_queue_max_promotion_age_chunks=ctx.staged_queue_max_promotion_age_chunks,
        queue_promotion_backlog_boost_remaining=lambda: ctx.queue_promotion_backlog_boost_remaining,
        consume_queue_promotion_backlog_boost=lambda: setattr(
            ctx,
            "queue_promotion_backlog_boost_remaining",
            max(0, ctx.queue_promotion_backlog_boost_remaining - 1),
        ),
        queue_backlog_promotion_extra_age=_aged_queue_backlog_promotion_extra_age,
        worker=ctx.worker,
    )


def queue_staged_sentence(
    ctx: StageFacadeContext,
    candidate: str,
    forced: bool,
    recent_final_trimmed: bool,
) -> None:
    ctx.commit_buffer_node.enqueue_or_revision(
        candidate=candidate,
        forced=forced,
        recent_final_trimmed=recent_final_trimmed,
        chunk_index=ctx.chunk_index,
        stable_analysis=ctx.require_stable_analysis(),
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
    )


def start_staged_sentence(
    ctx: StageFacadeContext,
    candidate: str,
    detected: str,
    forced: bool,
    recent_final_trimmed: bool,
) -> None:
    _start_staged_sentence(
        active_stage=ctx.active_stage,
        candidate=candidate,
        forced=forced,
        recent_final_trimmed=recent_final_trimmed,
        detected=detected,
        chunk_index=ctx.chunk_index,
        committed_text=ctx.committed_text,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        worker=ctx.worker,
    )


def suppress_active_stage_for_quality(
    ctx: StageFacadeContext,
    detected: str,
    *,
    metric_name: str,
    status_prefix: str,
    extra_status: str = "",
) -> None:
    _suppress_active_stage_for_quality(
        active_stage=ctx.active_stage,
        detected=detected,
        chunk_index=ctx.chunk_index,
        metric_name=metric_name,
        status_prefix=status_prefix,
        extra_status=extra_status,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
    )


def suppress_finalize_candidate(
    ctx: StageFacadeContext,
    detected: str,
    *,
    metric_name: str,
    reason: str,
    status_prefix: str,
    text: str,
    extra_status: str = "",
) -> list[tuple[int, str]]:
    return _suppress_finalize_candidate(
        active_stage=ctx.active_stage,
        detected=detected,
        chunk_index=ctx.chunk_index,
        metric_name=metric_name,
        reason=reason,
        status_prefix=status_prefix,
        text=text,
        extra_status=extra_status,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
    )


def apply_recent_final_finalize_adjustment(
    ctx: StageFacadeContext,
    detected: str,
    *,
    reason: str,
    staged_before: str,
    output_sentence: str,
) -> str | None:
    return _apply_recent_final_finalize_adjustment(
        active_stage=ctx.active_stage,
        recent_transcripts=tuple(ctx.loop_support.recent_transcripts),
        detected=detected,
        chunk_index=ctx.chunk_index,
        reason=reason,
        output_sentence=output_sentence,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
    )


def apply_delta_finalize_guard(
    ctx: StageFacadeContext,
    detected: str,
    *,
    reason: str,
    staged_before: str,
    output_sentence: str,
) -> bool:
    return _apply_delta_finalize_guard(
        active_stage=ctx.active_stage,
        detected=detected,
        chunk_index=ctx.chunk_index,
        reason=reason,
        staged_before=staged_before,
        output_sentence=output_sentence,
        delta_suppressed_stage_max_chunks=ctx.delta_suppressed_stage_max_chunks,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
    )


def emit_finalized_sentence(
    ctx: StageFacadeContext,
    detected: str,
    *,
    reason: str,
    staged_before: str,
    output_sentence: str,
    committed_before_chars: int,
) -> tuple[str, int, list[tuple[int, str]]]:
    committed_text, next_final_segment_id, produced = _emit_finalized_sentence(
        active_stage=ctx.active_stage,
        committed_text=ctx.committed_text,
        next_final_segment_id=ctx.next_final_segment_id,
        detected=detected,
        chunk_index=ctx.chunk_index,
        reason=reason,
        staged_before=staged_before,
        output_sentence=output_sentence,
        committed_before_chars=committed_before_chars,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        remember_transcript=ctx.remember_transcript,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
    )
    ctx.committed_text = committed_text
    ctx.next_final_segment_id = next_final_segment_id
    return committed_text, next_final_segment_id, produced


def finalize_staged_sentence(ctx: StageFacadeContext, detected: str, reason: str) -> list[tuple[int, str]]:
    ctx.committed_text, ctx.next_final_segment_id, produced = _finalize_staged_sentence(
        active_stage=ctx.active_stage,
        commit_buffer_node=ctx.commit_buffer_node,
        committed_text=ctx.committed_text,
        next_final_segment_id=ctx.next_final_segment_id,
        detected=detected,
        chunk_index=ctx.chunk_index,
        reason=reason,
        count_metric=ctx.count_metric,
        count_segment_state=ctx.count_segment_state,
        remember_transcript=ctx.remember_transcript,
        promote_next_staged_sentence=lambda language: promote_next_staged_sentence(ctx, language),
        worker=ctx.worker,
        staged_queue_max_promotion_age_chunks=ctx.staged_queue_max_promotion_age_chunks,
        set_queue_promotion_backlog_boost=lambda amount: setattr(
            ctx,
            "queue_promotion_backlog_boost_remaining",
            max(ctx.queue_promotion_backlog_boost_remaining, amount),
        ),
        preserve_staged_output_when_delta_fragment=preserve_staged_output_when_delta_fragment,
        suppress_finalize_candidate=lambda language, **kwargs: suppress_finalize_candidate(ctx, language, **kwargs),
        apply_recent_final_finalize_adjustment=lambda language, **kwargs: apply_recent_final_finalize_adjustment(
            ctx,
            language,
            **kwargs,
        ),
        apply_delta_finalize_guard=lambda language, **kwargs: apply_delta_finalize_guard(ctx, language, **kwargs),
        emit_finalized_sentence=lambda language, **kwargs: emit_finalized_sentence(ctx, language, **kwargs),
    )
    return produced

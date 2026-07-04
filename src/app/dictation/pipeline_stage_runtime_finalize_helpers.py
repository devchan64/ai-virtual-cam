from __future__ import annotations
"""Finalize helpers for stage runtime."""

from typing import Callable

from src.app.dictation_core.dictation_recent_final import _recent_final_output_delta
from src.app.dictation_core.dictation_revision_progression import _diagnostic_tail
from src.app.dictation_core.dictation_revision_text import _sentence_output_delta
from src.app.dictation_core.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _normalized_text,
    _should_suppress_ko_numeric_aged_final_with_queue,
    _should_suppress_ko_pure_latin_final_with_hangul_queue,
    _should_suppress_right_context_short_prefix_extension_with_single_queue,
    _should_enable_aged_queue_backlog_promotion_boost,
    _should_preserve_staged_output_when_delta_fragment,
    _should_suppress_aged_short_closed_when_queue_has_stronger_candidate,
    _should_suppress_aged_low_value_final,
    _should_suppress_aged_no_end_marker_queue_final,
    _should_suppress_delta_final,
)
from src.app.dictation.pipeline_stage_runtime_candidate_helpers import suppress_finalize_candidate
from src.app.dictation.pipeline_settings import staged_queue_max_promotion_age_chunks_for_language
from src.app.dictation.pipeline_types import ActiveStage, CommitBufferNode, TranscriptWorkerLike
from src.app.dictation_core.transcript_revision import append_context as _append_committed_text


def apply_recent_final_finalize_adjustment(
    *,
    active_stage: ActiveStage,
    recent_transcripts: tuple[str, ...],
    detected: str,
    chunk_index: int,
    reason: str,
    output_sentence: str,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
) -> str | None:
    recent_adjusted_sentence, echo_source = _recent_final_output_delta(
        output_sentence,
        recent_transcripts,
        detected,
    )
    if echo_source is None:
        return output_sentence
    if recent_adjusted_sentence:
        count_metric("finalize_recent_delta_trimmed")
        worker._emit(
            "status",
            "받아쓰기 AI 확정 후보 최근 final 중복 제거: "
            f"chunk={chunk_index} reason={reason} recent={echo_source!r} "
            f"before={output_sentence!r} after={recent_adjusted_sentence!r}",
            display=False,
        )
        return recent_adjusted_sentence
    return suppress_finalize_candidate(
        active_stage=active_stage,
        detected=detected,
        chunk_index=chunk_index,
        metric_name="finalize_recent_echo_suppressed",
        reason=reason,
        status_prefix="받아쓰기 AI 확정 후보 유사 대안 무시",
        text=output_sentence,
        extra_status=f"recent={echo_source!r}",
        count_metric=count_metric,
        count_segment_state=count_segment_state,
        promote_next_staged_sentence=promote_next_staged_sentence,
        worker=worker,
    ) or None


def emit_finalized_sentence(
    *,
    active_stage: ActiveStage,
    committed_text: str,
    next_final_segment_id: int,
    detected: str,
    chunk_index: int,
    reason: str,
    staged_before: str,
    output_sentence: str,
    committed_before_chars: int,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    remember_transcript: Callable[[str], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
) -> tuple[str, int, list[tuple[int, str]]]:
    active_stage.clear()
    count_metric("finalized")
    count_segment_state("final")
    segment_id = next_final_segment_id
    next_final_segment_id += 1
    final_quality_flags = _final_sentence_diagnostic_flags(output_sentence, detected)
    for flag in final_quality_flags:
        count_metric(f"final_quality_{flag}")
    committed_text = _append_committed_text(committed_text, output_sentence)
    remember_transcript(output_sentence)
    worker._emit(
        "status",
        "받아쓰기 AI 문장 확정: "
        f"chunk={chunk_index} segment_id={segment_id} reason={reason} committed_before_chars={committed_before_chars} "
        f"output_chars={len(_normalized_text(output_sentence))} "
        f"quality_flags={','.join(final_quality_flags) or 'none'} "
        f"staged_tail={_diagnostic_tail(staged_before)} text={output_sentence!r}",
        display=False,
    )
    worker._emit(
        "transcript",
        output_sentence,
        log_text=f"[{detected}#{segment_id}] {output_sentence}",
        final=True,
        segment_id=segment_id,
    )
    promote_next_staged_sentence(detected)
    return committed_text, next_final_segment_id, [(segment_id, output_sentence)]


def apply_delta_finalize_guard(
    *,
    active_stage: ActiveStage,
    detected: str,
    chunk_index: int,
    reason: str,
    staged_before: str,
    output_sentence: str,
    delta_suppressed_stage_max_chunks: Callable[[], int],
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
) -> bool:
    if not _should_suppress_delta_final(staged_before, output_sentence, detected, reason):
        return False
    count_metric("finalize_delta_suppressed")
    if active_stage.deltaSuppressedChunkIndex != chunk_index:
        active_stage.deltaSuppressedChunks += 1
    active_stage.deltaSuppressedChunkIndex = chunk_index
    if active_stage.deltaSuppressedChunks >= delta_suppressed_stage_max_chunks():
        suppress_chunks = active_stage.deltaSuppressedChunks
        active_stage.clear()
        count_metric("finalize_delta_suppressed_stage_dropped")
        count_segment_state("suppressed")
        worker._emit(
            "status",
            "받아쓰기 AI delta 보류 stage 폐기: "
            f"chunk={chunk_index} reason={reason} suppress_chunks={suppress_chunks} "
            f"staged_tail={_diagnostic_tail(staged_before)} output={output_sentence!r}",
            display=False,
        )
        promote_next_staged_sentence(detected)
        return True
    count_metric("finalize_delta_suppressed_stage_retained")
    worker._emit(
        "status",
        "받아쓰기 AI delta 확정 보류: "
        f"suppress_chunks={active_stage.deltaSuppressedChunks} "
        f"chunk={chunk_index} reason={reason} staged_tail={_diagnostic_tail(staged_before)} "
        f"output={output_sentence!r}",
        display=False,
    )
    return True


def preserve_staged_output_when_delta_fragment(
    *,
    staged_before: str,
    output_sentence: str,
    detected: str,
    chunk_index: int,
    reason: str,
    count_metric: Callable[[str, int], None],
    worker: TranscriptWorkerLike,
) -> str:
    if not _should_preserve_staged_output_when_delta_fragment(
        staged_before,
        output_sentence,
        detected,
    ):
        return output_sentence
    count_metric("finalize_delta_fragment_preserved")
    worker._emit(
        "status",
        "받아쓰기 AI 확정 delta 조각 보존: "
        f"chunk={chunk_index} reason={reason} staged_tail={_diagnostic_tail(staged_before)} "
        f"delta={output_sentence!r}",
        display=False,
    )
    return staged_before


def finalize_staged_sentence(
    *,
    active_stage: ActiveStage,
    commit_buffer_node: CommitBufferNode,
    committed_text: str,
    next_final_segment_id: int,
    detected: str,
    chunk_index: int,
    reason: str,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    remember_transcript: Callable[[str], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
    staged_queue_max_promotion_age_chunks: Callable[[], int],
    set_queue_promotion_backlog_boost: Callable[[int], None],
    preserve_staged_output_when_delta_fragment: Callable[..., str],
    suppress_finalize_candidate: Callable[..., list[tuple[int, str]]],
    apply_recent_final_finalize_adjustment: Callable[..., str | None],
    apply_delta_finalize_guard: Callable[..., bool],
    emit_finalized_sentence: Callable[..., tuple[str, int, list[tuple[int, str]]]],
) -> tuple[str, int, list[tuple[int, str]]]:
    if not active_stage.sentence:
        return committed_text, next_final_segment_id, []
    count_metric("finalize_attempt")
    count_metric(f"finalize_reason_{reason}")
    queue_before_sentences = commit_buffer_node.queued_sentences()
    if reason in {"confirmed", "confirmed_forced"} and queue_before_sentences:
        count_metric("finalize_confirmed_with_queue_tail")
        count_metric(f"finalize_confirmed_with_queue_tail_q{min(len(queue_before_sentences), 5)}")
    if commit_buffer_node.prefer_queued_revision_for_active(
        chunk_index=chunk_index,
        max_promotion_age_chunks=staged_queue_max_promotion_age_chunks_for_language(detected),
        finalize_reason=reason,
        count_metric=count_metric,
        count_segment_state=count_segment_state,
    ):
        worker._emit(
            "status",
            "받아쓰기 AI 확정 전 queue revision 보류: "
            f"chunk={chunk_index} reason={reason} staged_tail={_diagnostic_tail(active_stage.sentence)}",
            display=False,
        )
        return committed_text, next_final_segment_id, []
    output_sentence = _sentence_output_delta(committed_text, active_stage.sentence)
    staged_before = active_stage.sentence
    committed_before_chars = len(_normalized_text(committed_text))
    output_sentence = preserve_staged_output_when_delta_fragment(
        staged_before=staged_before,
        output_sentence=output_sentence,
        detected=detected,
        chunk_index=chunk_index,
        reason=reason,
        count_metric=count_metric,
        worker=worker,
    )
    if not output_sentence:
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                detected,
                metric_name="finalize_duplicate_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI 확정 후보 중복 무시",
                text=staged_before,
            ),
        )
    output_sentence = apply_recent_final_finalize_adjustment(
        detected,
        reason=reason,
        staged_before=staged_before,
        output_sentence=output_sentence,
    )
    if output_sentence is None:
        return committed_text, next_final_segment_id, []
    if _should_suppress_aged_low_value_final(
        staged_before,
        detected,
        reason,
        active_stage.confirmations,
        active_stage.forced,
        commit_buffer_node.queued_sentences(),
    ):
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                active_stage=active_stage,
                detected=detected,
                chunk_index=chunk_index,
                metric_name="finalize_aged_low_value_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI 낮은 가치 aged 확정 후보 무시",
                text=staged_before,
                extra_status="",
                count_metric=count_metric,
                count_segment_state=count_segment_state,
                promote_next_staged_sentence=promote_next_staged_sentence,
                worker=worker,
            ),
        )
    if _should_suppress_aged_short_closed_when_queue_has_stronger_candidate(
        staged_before,
        detected,
        reason,
        active_stage.confirmations,
        active_stage.forced,
        commit_buffer_node.queue_entries(),
    ):
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                active_stage=active_stage,
                detected=detected,
                chunk_index=chunk_index,
                metric_name="finalize_aged_short_closed_stronger_queue_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI 강한 queue로 짧은 aged 확정 후보 무시",
                text=staged_before,
                extra_status="",
                count_metric=count_metric,
                count_segment_state=count_segment_state,
                promote_next_staged_sentence=promote_next_staged_sentence,
                worker=worker,
            ),
        )
    if _should_suppress_right_context_short_prefix_extension_with_single_queue(
        staged_before,
        reason,
        commit_buffer_node.queued_sentences(),
    ):
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                active_stage=active_stage,
                detected=detected,
                chunk_index=chunk_index,
                metric_name="finalize_right_context_short_prefix_queue_extension_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI 짧은 right-context prefix 확정 후보 무시",
                text=staged_before,
                extra_status="",
                count_metric=count_metric,
                count_segment_state=count_segment_state,
                promote_next_staged_sentence=promote_next_staged_sentence,
                worker=worker,
            ),
        )
    if _should_suppress_ko_pure_latin_final_with_hangul_queue(
        staged_before,
        detected,
        reason,
        commit_buffer_node.queued_sentences(),
    ):
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                active_stage=active_stage,
                detected=detected,
                chunk_index=chunk_index,
                metric_name="finalize_ko_pure_latin_hangul_queue_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI 한글 queue 뒤 순수 영문 확정 후보 무시",
                text=staged_before,
                extra_status="",
                count_metric=count_metric,
                count_segment_state=count_segment_state,
                promote_next_staged_sentence=promote_next_staged_sentence,
                worker=worker,
            ),
        )
    if _should_suppress_ko_numeric_aged_final_with_queue(
        staged_before,
        detected,
        reason,
        commit_buffer_node.queued_sentences(),
    ):
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                active_stage=active_stage,
                detected=detected,
                chunk_index=chunk_index,
                metric_name="finalize_ko_numeric_aged_queue_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI 숫자 위주 aged 확정 후보 무시",
                text=staged_before,
                extra_status="",
                count_metric=count_metric,
                count_segment_state=count_segment_state,
                promote_next_staged_sentence=promote_next_staged_sentence,
                worker=worker,
            ),
        )
    if _should_suppress_aged_no_end_marker_queue_final(
        staged_before,
        detected,
        reason,
        active_stage.confirmations,
        commit_buffer_node.queued_sentences(),
    ):
        return (
            committed_text,
            next_final_segment_id,
            suppress_finalize_candidate(
                active_stage=active_stage,
                detected=detected,
                chunk_index=chunk_index,
                metric_name="finalize_aged_no_end_marker_queue_suppressed",
                reason=reason,
                status_prefix="받아쓰기 AI no-end queue aged 확정 후보 무시",
                text=staged_before,
                extra_status="",
                count_metric=count_metric,
                count_segment_state=count_segment_state,
                promote_next_staged_sentence=promote_next_staged_sentence,
                worker=worker,
            ),
        )
    if apply_delta_finalize_guard(
        detected,
        reason=reason,
        staged_before=staged_before,
        output_sentence=output_sentence,
    ):
        return committed_text, next_final_segment_id, []
    queued_sentence_count = len(commit_buffer_node)
    if _should_enable_aged_queue_backlog_promotion_boost(reason, queued_sentence_count, detected):
        set_queue_promotion_backlog_boost(queued_sentence_count)
        count_metric("stage_queue_backlog_boost_enabled")
    committed_text, next_final_segment_id, produced = emit_finalized_sentence(
        detected,
        reason=reason,
        staged_before=staged_before,
        output_sentence=output_sentence,
        committed_before_chars=committed_before_chars,
    )
    return committed_text, next_final_segment_id, produced

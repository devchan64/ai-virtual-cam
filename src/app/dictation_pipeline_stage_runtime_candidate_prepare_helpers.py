from __future__ import annotations
"""Candidate preparation and quality gating helpers for stage runtime."""

from typing import Callable

from src.app.dictation_recent_final import _recent_final_output_delta
from src.app.dictation_revision_progression import _diagnostic_tail
from src.app.dictation_pipeline_stage_state_helpers import tick_stage_age_once
from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _is_cjk_text,
    _is_pending_prefix_mixed_candidate,
    _is_prior_pending_recent_final_mixed_candidate,
    _normalized_text,
    _sentence_output_delta,
    _should_stage_boundary_candidate,
)
from src.app.dictation_pipeline_types import ActiveStage, CommitBufferNode, TranscriptWorkerLike


def prepare_stage_candidate(
    *,
    active_stage: ActiveStage,
    commit_buffer_node: CommitBufferNode,
    committed_text: str,
    pending_transcript_text: str,
    prior_pending_text: str,
    sentence: str,
    detected: str,
    later_completed_sentences: list[str] | tuple[str, ...],
    recent_transcripts: tuple[str, ...],
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    count_recent_final_stable_internal_suppression: Callable[[str], None],
    suppress_active_stage_for_quality: Callable[..., None],
    worker: TranscriptWorkerLike,
    strip_prior_pending_prefix_revision: Callable[[str, str, str], str],
    stage_quality_block_age_limit: Callable[[str, str, bool, int], int],
) -> str | None:
    normalized_sentence = _normalized_text(sentence)
    candidate = _sentence_output_delta(committed_text, sentence)
    if active_stage.sentence and prior_pending_text and candidate:
        stripped_candidate = strip_prior_pending_prefix_revision(
            active_stage.sentence,
            candidate,
            prior_pending_text,
        )
        if stripped_candidate != candidate:
            count_metric("candidate_prior_pending_prefix_trimmed")
            worker._emit(
                "status",
                "받아쓰기 AI prior pending prefix 후보 정리: "
                f"chunk={chunk_index} prior_pending={_diagnostic_tail(prior_pending_text)} "
                f"before={_diagnostic_tail(candidate)} after={_diagnostic_tail(stripped_candidate)}",
                display=False,
            )
            candidate = stripped_candidate
    if candidate and candidate != normalized_sentence:
        count_metric("candidate_delta_trimmed")
        if _is_cjk_text(normalized_sentence):
            count_metric("candidate_delta_trimmed_cjk")
    recent_candidate, recent_source = _recent_final_output_delta(
        normalized_sentence,
        recent_transcripts,
        detected,
    )
    if recent_source is not None and recent_candidate != candidate:
        candidate = recent_candidate
        count_metric("candidate_recent_final_delta_trimmed")
    if not candidate:
        count_metric("candidate_duplicate_suppressed")
        if recent_source is not None:
            count_recent_final_stable_internal_suppression("candidate_duplicate_suppressed")
        count_segment_state("suppressed")
        worker._emit(
            "status",
            f"받아쓰기 AI 중복 문장 무시: chunk={chunk_index} text={sentence!r}",
            display=False,
        )
        return None
    if _is_pending_prefix_mixed_candidate(candidate, pending_transcript_text):
        count_metric("candidate_pending_prefix_mixed_suppressed")
        count_segment_state("suppressed")
        worker._emit(
            "status",
            "받아쓰기 AI pending prefix 혼합 후보 무시: "
            f"chunk={chunk_index} candidate_tail={_diagnostic_tail(candidate)} "
            f"pending_tail={_diagnostic_tail(pending_transcript_text)}",
            display=False,
        )
        return None
    if _is_prior_pending_recent_final_mixed_candidate(
        candidate,
        prior_pending_text,
        recent_transcripts,
        detected,
    ):
        count_metric("candidate_prior_pending_recent_final_mixed_suppressed")
        count_segment_state("suppressed")
        worker._emit(
            "status",
            "받아쓰기 AI prior pending/recent final 혼합 후보 무시: "
            f"chunk={chunk_index} candidate_tail={_diagnostic_tail(candidate)} "
            f"prior_pending_tail={_diagnostic_tail(prior_pending_text)}",
            display=False,
        )
        return None
    if not _should_stage_boundary_candidate(candidate, detected):
        count_metric("stage_candidate_quality_blocked")
        count_segment_state("suppressed")
        candidate_quality_flags = _final_sentence_diagnostic_flags(candidate, detected)
        for flag in candidate_quality_flags:
            count_metric(f"stage_candidate_quality_{flag}")
        if "no_end_marker" in candidate_quality_flags:
            if active_stage.sentence:
                count_metric("stage_candidate_quality_no_end_marker_with_active_stage")
            if commit_buffer_node.queued_sentences():
                count_metric("stage_candidate_quality_no_end_marker_with_queue")
            if not active_stage.sentence and not commit_buffer_node.queued_sentences():
                count_metric("stage_candidate_quality_no_end_marker_without_blocker")
        for blocking_flag in ("short_no_end_fragment", "trailing_ellipsis"):
            if blocking_flag not in candidate_quality_flags:
                continue
            if active_stage.sentence:
                count_metric(f"stage_candidate_quality_{blocking_flag}_with_active_stage")
            if commit_buffer_node.queued_sentences():
                count_metric(f"stage_candidate_quality_{blocking_flag}_with_queue")
            if not active_stage.sentence and not commit_buffer_node.queued_sentences():
                count_metric(f"stage_candidate_quality_{blocking_flag}_without_blocker")
            if blocking_flag == "short_no_end_fragment" and later_completed_sentences:
                count_metric("stage_candidate_quality_short_no_end_fragment_with_later_completed")
        active_stage_flags = (
            set(_final_sentence_diagnostic_flags(active_stage.sentence, detected))
            if active_stage.sentence
            else set()
        )
        if (
            "short_no_end_fragment" in candidate_quality_flags
            and active_stage_flags.intersection({"no_end_marker", "short_cjk"})
            and active_stage.deferredAgeChunk != chunk_index
        ):
            tick_stage_age_once(active_stage, chunk_index=chunk_index, count_metric=count_metric)
            count_metric("stage_blocked_short_no_end_aged_active_stage")
            if active_stage.age >= stage_quality_block_age_limit(
                active_stage.sentence,
                detected,
                active_stage.forced,
                sentence_finalize_age,
            ):
                count_metric("stage_blocked_short_no_end_active_stage_quality_suppressed")
                suppress_active_stage_for_quality(
                    detected,
                    metric_name="stage_age_quality_blocked",
                    status_prefix="받아쓰기 AI stage 후보 품질 차단",
                )
        worker._emit(
            "status",
            "받아쓰기 AI stage 후보 품질 차단: "
            f"chunk={chunk_index} flags={','.join(candidate_quality_flags) or 'none'} "
            f"candidate_tail={_diagnostic_tail(candidate)}",
            display=False,
        )
        return None
    return candidate

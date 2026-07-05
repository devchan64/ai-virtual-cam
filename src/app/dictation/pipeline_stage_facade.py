from __future__ import annotations
"""Loop-local stage lifecycle facade for realtime dictation orchestration."""

from typing import Callable

from src.app.dictation.pipeline_runtime_support import RuntimeLoopSupport
from src.app.dictation.pipeline_stage_facade_support import StageFacadeContext
from src.app.dictation.pipeline_stage_finalize_helpers import (
    apply_delta_finalize_guard as _apply_delta_finalize_guard,
    apply_recent_final_finalize_adjustment as _apply_recent_final_finalize_adjustment,
    emit_finalized_sentence as _emit_finalized_sentence,
    finalize_staged_sentence as _finalize_staged_sentence,
    promote_next_staged_sentence as _promote_next_staged_sentence,
    queue_staged_sentence as _queue_staged_sentence,
    start_staged_sentence as _start_staged_sentence,
    suppress_active_stage_for_quality as _suppress_active_stage_for_quality,
    suppress_finalize_candidate as _suppress_finalize_candidate,
)
from src.app.dictation.pipeline_stage_progression_helpers import (
    age_staged_sentence as _age_staged_sentence,
    finalize_right_context_staged_sentences as _finalize_right_context_staged_sentences,
    handle_replacement_candidate as _handle_replacement_candidate,
    handle_revision_candidate as _handle_revision_candidate,
    prepare_stage_candidate as _prepare_stage_candidate,
    stage_completed_sentence as _stage_completed_sentence,
    suppress_stale_no_text_stage as _suppress_stale_no_text_stage,
)
from src.app.dictation.pipeline_types import ActiveStage, CommitBufferNode, StableAnalysis, TranscriptWorkerLike


class StageLoopFacade:
    def __init__(
        self,
        *,
        worker: TranscriptWorkerLike,
        loop_support: RuntimeLoopSupport,
        active_stage: ActiveStage,
        commit_buffer_node: CommitBufferNode,
        sentence_finalize_age: int,
        staged_queue_max_promotion_age_chunks: Callable[[], int],
        delta_suppressed_stage_max_chunks: Callable[[], int],
        no_text_stale_stage_suppress_chunks: Callable[[], int],
    ) -> None:
        self._ctx = StageFacadeContext(
            worker=worker,
            loop_support=loop_support,
            active_stage=active_stage,
            commit_buffer_node=commit_buffer_node,
            sentence_finalize_age=sentence_finalize_age,
            staged_queue_max_promotion_age_chunks=staged_queue_max_promotion_age_chunks,
            delta_suppressed_stage_max_chunks=delta_suppressed_stage_max_chunks,
            no_text_stale_stage_suppress_chunks=no_text_stale_stage_suppress_chunks,
        )

    def sync_chunk(
        self,
        *,
        chunk_index: int,
        committed_text: str,
        stable_analysis: StableAnalysis,
    ) -> None:
        self._ctx.sync_chunk(
            chunk_index=chunk_index,
            committed_text=committed_text,
            stable_analysis=stable_analysis,
        )

    def count_metric(self, name: str, amount: int = 1) -> None:
        self._ctx.count_metric(name, amount)

    def count_segment_state(self, state: str, amount: int = 1) -> None:
        self._ctx.count_segment_state(state, amount)

    def is_repeated_hallucination(self, text: str) -> bool:
        return self._ctx.is_repeated_hallucination(text)

    def remember_transcript(self, text: str) -> None:
        self._ctx.remember_transcript(text)

    @property
    def active_stage(self) -> ActiveStage:
        return self._ctx.active_stage

    @property
    def committed_text(self) -> str:
        return self._ctx.committed_text

    @property
    def stable_analysis(self) -> StableAnalysis | None:
        return self._ctx.stable_analysis

    def promote_next_staged_sentence(self, detected: str) -> None:
        _promote_next_staged_sentence(self._ctx, detected)

    def queue_staged_sentence(self, candidate: str, forced: bool, recent_final_trimmed: bool = False) -> None:
        _queue_staged_sentence(self._ctx, candidate, forced, recent_final_trimmed)

    def start_staged_sentence(
        self,
        candidate: str,
        detected: str,
        forced: bool,
        recent_final_trimmed: bool = False,
    ) -> None:
        _start_staged_sentence(self._ctx, candidate, detected, forced, recent_final_trimmed)

    def suppress_active_stage_for_quality(
        self,
        detected: str,
        *,
        metric_name: str,
        status_prefix: str,
        extra_status: str = "",
    ) -> None:
        _suppress_active_stage_for_quality(
            self._ctx,
            detected,
            metric_name=metric_name,
            status_prefix=status_prefix,
            extra_status=extra_status,
        )

    def suppress_finalize_candidate(
        self,
        detected: str,
        *,
        metric_name: str,
        reason: str,
        status_prefix: str,
        text: str,
        extra_status: str = "",
    ) -> list[tuple[int, str]]:
        return _suppress_finalize_candidate(
            self._ctx,
            detected,
            metric_name=metric_name,
            reason=reason,
            status_prefix=status_prefix,
            text=text,
            extra_status=extra_status,
        )

    def apply_recent_final_finalize_adjustment(
        self,
        detected: str,
        *,
        reason: str,
        staged_before: str,
        output_sentence: str,
    ) -> str | None:
        return _apply_recent_final_finalize_adjustment(
            self._ctx,
            detected,
            reason=reason,
            staged_before=staged_before,
            output_sentence=output_sentence,
        )

    def apply_delta_finalize_guard(
        self,
        detected: str,
        *,
        reason: str,
        staged_before: str,
        output_sentence: str,
    ) -> bool:
        return _apply_delta_finalize_guard(
            self._ctx,
            detected,
            reason=reason,
            staged_before=staged_before,
            output_sentence=output_sentence,
        )

    def emit_finalized_sentence(
        self,
        detected: str,
        *,
        reason: str,
        staged_before: str,
        output_sentence: str,
        committed_before_chars: int,
    ) -> tuple[str, int, list[tuple[int, str]]]:
        return _emit_finalized_sentence(
            self._ctx,
            detected,
            reason=reason,
            staged_before=staged_before,
            output_sentence=output_sentence,
            committed_before_chars=committed_before_chars,
        )

    def prepare_stage_candidate(
        self,
        sentence: str,
        detected: str,
        *,
        later_completed_sentences: list[str] | tuple[str, ...],
        prior_pending_text: str,
        pending_transcript_text: str,
    ) -> str | None:
        return _prepare_stage_candidate(
            self._ctx,
            sentence,
            detected,
            later_completed_sentences=later_completed_sentences,
            prior_pending_text=prior_pending_text,
            pending_transcript_text=pending_transcript_text,
        )

    def finalize_staged_sentence(self, detected: str, reason: str) -> list[tuple[int, str]]:
        return _finalize_staged_sentence(self._ctx, detected, reason)

    def handle_revision_candidate(
        self,
        candidate: str,
        detected: str,
        *,
        forced: bool,
        later_completed_sentences: list[str] | tuple[str, ...],
    ) -> list[tuple[int, str]]:
        return _handle_revision_candidate(
            self._ctx,
            candidate,
            detected,
            forced=forced,
            later_completed_sentences=later_completed_sentences,
        )

    def handle_replacement_candidate(
        self,
        candidate: str,
        detected: str,
        *,
        forced: bool,
        prior_pending_text: str,
    ) -> list[tuple[int, str]]:
        return _handle_replacement_candidate(
            self._ctx,
            candidate,
            detected,
            forced=forced,
            prior_pending_text=prior_pending_text,
        )

    def stage_completed_sentence(
        self,
        sentence: str,
        detected: str,
        *,
        pending_transcript_text: str,
        forced: bool = False,
        later_completed_sentences: list[str] | tuple[str, ...] = (),
        prior_pending_text: str = "",
    ) -> list[tuple[int, str]]:
        return _stage_completed_sentence(
            self._ctx,
            sentence,
            detected,
            pending_transcript_text=pending_transcript_text,
            forced=forced,
            later_completed_sentences=later_completed_sentences,
            prior_pending_text=prior_pending_text,
        )

    def age_staged_sentence(self, detected: str, pending_text: str = "") -> list[tuple[int, str]]:
        return _age_staged_sentence(self._ctx, detected, pending_text)

    def finalize_right_context_staged_sentences(self, detected: str) -> list[tuple[int, str]]:
        return _finalize_right_context_staged_sentences(self._ctx, detected)

    def suppress_stale_no_text_stage(self, detected: str, no_text_stage_skip_chunks: int) -> int:
        return _suppress_stale_no_text_stage(self._ctx, detected, no_text_stage_skip_chunks)

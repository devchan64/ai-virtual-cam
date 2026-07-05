from __future__ import annotations
"""Revision-path policy helpers for staged sentence lifecycle."""

from typing import Callable

from src.app.dictation_core.dictation_revision_progression import (
    _diagnostic_tail,
    _next_revision_confirmation_count,
    _prefer_sentence_revision,
    _revision_internal_stability_bucket,
    _should_preserve_revision_confirmation_from_internal_stability,
    _should_reset_revision_age,
)
from src.app.dictation_core.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _has_later_completed_extension,
    _is_cjk_text,
    _stage_finalize_age_limit,
    _staged_sentence_required_confirmations,
    _should_confirm_staged_sentence,
    _should_defer_token_sentence_revision,
    _should_finalize_before_replacement,
)
from src.app.dictation.pipeline_stage_state_helpers import tick_stage_age, tick_stage_age_once
from src.app.dictation.pipeline_types import ActiveStage, CommitBufferNode, StableAnalysis, TranscriptWorkerLike


def _handle_deferred_token_sentence_revision(
    *,
    active_stage: ActiveStage,
    preferred: str,
    forced: bool,
    detected: str,
    staged_before: str,
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    queue_staged_sentence: Callable[[str, bool], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    suppress_active_stage_for_quality: Callable[..., None],
    worker: TranscriptWorkerLike,
    sentence_max_age_chunks: Callable[[bool, int], int],
    stage_quality_block_age_limit: Callable[[str, str, bool, int], int],
    commit_buffer_node: CommitBufferNode,
) -> list[tuple[int, str]]:
    count_metric("stage_revision_token_sentence_deferred")
    queue_staged_sentence(preferred, forced)
    tick_stage_age_once(active_stage, chunk_index=chunk_index, count_metric=count_metric)
    worker._emit(
        "status",
        "받아쓰기 AI stage 리비전 token-sentence 보류: "
        f"chunk={chunk_index} staged_confirmations={active_stage.confirmations} "
        f"staged_age={active_stage.age} staged_tail={_diagnostic_tail(staged_before)} "
        f"candidate_tail={_diagnostic_tail(preferred)}",
        display=False,
    )
    if _should_confirm_staged_sentence(
        active_stage.sentence,
        active_stage.confirmations,
        active_stage.forced,
    ):
        count_metric("stage_confirmed_before_deferred_revision")
        return finalize_staged_sentence(
            detected,
            "confirmed_forced" if active_stage.forced else "confirmed",
        )
    if _should_finalize_before_replacement(
        active_stage.sentence,
        detected,
        active_stage.confirmations,
        active_stage.age,
        sentence_finalize_age,
        active_stage.forced,
        commit_buffer_node.queued_sentences(),
    ):
        max_age = _stage_finalize_age_limit(
            active_stage.sentence,
            detected,
            active_stage.forced,
            sentence_finalize_age,
            commit_buffer_node.queued_sentences(),
        )
        if active_stage.age >= max_age:
            count_metric("stage_age_finalize")
            return finalize_staged_sentence(
                detected,
                "aged_forced" if active_stage.forced else "aged",
            )
    if active_stage.age >= stage_quality_block_age_limit(
        active_stage.sentence,
        detected,
        active_stage.forced,
        sentence_finalize_age,
    ):
        suppress_active_stage_for_quality(
            detected,
            metric_name="stage_age_quality_blocked",
            status_prefix="받아쓰기 AI stage 리비전 품질 차단",
        )
    return []


def _resolve_revised_stage_progression(
    *,
    active_stage: ActiveStage,
    detected: str,
    later_completed_sentences: list[str] | tuple[str, ...],
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    suppress_active_stage_for_quality: Callable[..., None],
    worker: TranscriptWorkerLike,
    sentence_max_age_chunks: Callable[[bool, int], int],
    stage_quality_block_age_limit: Callable[[str, str, bool, int], int],
    commit_buffer_node: CommitBufferNode,
) -> list[tuple[int, str]]:
    defer_for_later_extension = _has_later_completed_extension(
        active_stage.sentence,
        later_completed_sentences,
    )
    if defer_for_later_extension:
        count_metric("stage_confirm_deferred_later_extension")
        worker._emit(
            "status",
            "받아쓰기 AI stage 확정 보류: "
            f"chunk={chunk_index} reason=later_completed_extension staged_tail={_diagnostic_tail(active_stage.sentence)}",
            display=False,
        )
    if not defer_for_later_extension and _should_confirm_staged_sentence(
        active_stage.sentence,
        active_stage.confirmations,
        active_stage.forced,
    ):
        return finalize_staged_sentence(
            detected,
            "confirmed_forced" if active_stage.forced else "confirmed",
        )
    if not defer_for_later_extension and _should_finalize_before_replacement(
        active_stage.sentence,
        detected,
        active_stage.confirmations,
        active_stage.age,
        sentence_finalize_age,
        active_stage.forced,
        commit_buffer_node.queued_sentences(),
    ):
        max_age = _stage_finalize_age_limit(
            active_stage.sentence,
            detected,
            active_stage.forced,
            sentence_finalize_age,
            commit_buffer_node.queued_sentences(),
        )
        if active_stage.age >= max_age:
            count_metric("stage_age_finalize")
            reason = "aged_forced" if active_stage.forced else "aged"
        else:
            count_metric("stage_finalize_before_replace")
            reason = "next_completed"
        return finalize_staged_sentence(detected, reason)
    if not defer_for_later_extension and active_stage.age >= stage_quality_block_age_limit(
        active_stage.sentence,
        detected,
        active_stage.forced,
        sentence_finalize_age,
    ):
        suppress_active_stage_for_quality(
            detected,
            metric_name="stage_age_quality_blocked",
            status_prefix="받아쓰기 AI stage 리비전 품질 차단",
        )
        return []
    worker._emit(
        "transcript",
        active_stage.sentence,
        log_text=f"[{detected}] {active_stage.sentence}",
        final=False,
    )
    return []


def handle_revision_candidate(
    *,
    active_stage: ActiveStage,
    candidate: str,
    detected: str,
    forced: bool,
    later_completed_sentences: list[str] | tuple[str, ...],
    stable_analysis: StableAnalysis,
    chunk_index: int,
    sentence_finalize_age: int,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    queue_staged_sentence: Callable[[str, bool], None],
    finalize_staged_sentence: Callable[[str, str], list[tuple[int, str]]],
    suppress_active_stage_for_quality: Callable[..., None],
    worker: TranscriptWorkerLike,
    sentence_max_age_chunks: Callable[[bool, int], int],
    stage_quality_block_age_limit: Callable[[str, str, bool, int], int],
    commit_buffer_node: CommitBufferNode,
) -> list[tuple[int, str]]:
    count_metric("stage_revision")
    count_segment_state("revised")
    staged_before = active_stage.sentence
    preferred = _prefer_sentence_revision(active_stage.sentence, candidate)
    preferred_changed = preferred != staged_before
    if preferred_changed:
        count_metric("stage_revision_changed")
        defer_token_sentence_revision = _should_defer_token_sentence_revision(
            staged_before,
            preferred,
            active_stage.confirmations,
            active_stage.forced or forced,
            stable_analysis.stable_internal_ratio,
            stable_analysis.stable_internal_chars,
            stable_analysis.stable_overlap_source,
        )
        if _is_cjk_text(staged_before) or _is_cjk_text(preferred):
            count_metric(
                "stage_revision_internal_stability_"
                + _revision_internal_stability_bucket(
                    stable_analysis.stable_internal_ratio,
                    stable_analysis.stable_internal_chars,
                )
            )
            if not defer_token_sentence_revision:
                if _should_preserve_revision_confirmation_from_internal_stability(
                    staged_before,
                    preferred,
                    stable_analysis.stable_internal_ratio,
                    stable_analysis.stable_internal_chars,
                    stable_analysis.stable_overlap_source,
                ):
                    count_metric("stage_revision_confirmation_preserved_internal")
                else:
                    count_metric("stage_revision_confirmation_reset")
        if defer_token_sentence_revision:
            return _handle_deferred_token_sentence_revision(
                active_stage=active_stage,
                preferred=preferred,
                forced=forced,
                detected=detected,
                staged_before=staged_before,
                chunk_index=chunk_index,
                sentence_finalize_age=sentence_finalize_age,
                count_metric=count_metric,
                queue_staged_sentence=queue_staged_sentence,
                finalize_staged_sentence=finalize_staged_sentence,
                suppress_active_stage_for_quality=suppress_active_stage_for_quality,
                worker=worker,
                sentence_max_age_chunks=sentence_max_age_chunks,
                stage_quality_block_age_limit=stage_quality_block_age_limit,
                commit_buffer_node=commit_buffer_node,
            )
    else:
        candidate_flags = set(_final_sentence_diagnostic_flags(candidate, detected))
        staged_flags = set(_final_sentence_diagnostic_flags(staged_before, detected))
        if (
            "cjk_repeated_ngram" in candidate_flags
            and "cjk_repeated_ngram" not in staged_flags
        ) or (
            "repeated_word_ngram" in candidate_flags
            and "repeated_word_ngram" not in staged_flags
        ):
            count_metric("stage_revision_candidate_quality_blocked")
    preferred_changed = preferred != staged_before
    active_stage.sentence = preferred
    if preferred_changed:
        active_stage.deltaSuppressedChunks = 0
        active_stage.deltaSuppressedChunkIndex = -1
    active_stage.confirmations = _next_revision_confirmation_count(
        staged_before,
        preferred,
        active_stage.confirmations,
        stable_analysis.stable_internal_ratio,
        stable_analysis.stable_internal_chars,
        stable_analysis.stable_overlap_source,
    )
    revision_age_reset = _should_reset_revision_age(
        staged_before,
        preferred,
        stable_analysis.stable_internal_ratio,
        stable_analysis.stable_internal_chars,
        stable_analysis.stable_overlap_source,
    )
    if revision_age_reset:
        active_stage.age = 0
        count_metric("stage_revision_age_reset")
        active_stage.deferredAgeChunk = chunk_index
    else:
        tick_stage_age(active_stage, chunk_index=chunk_index, count_metric=count_metric)
    active_stage.forced = active_stage.forced or forced
    required_confirmations = _staged_sentence_required_confirmations(
        active_stage.sentence,
        active_stage.forced,
    )
    worker._emit(
        "status",
        "받아쓰기 AI stage 리비전: "
        f"chunk={chunk_index} confirmations={active_stage.confirmations}/{required_confirmations} "
        f"staged_age={active_stage.age} "
        f"forced={active_stage.forced} preferred_changed={preferred_changed} "
        f"staged_before={_diagnostic_tail(staged_before)} candidate={_diagnostic_tail(candidate)} "
        f"preferred={_diagnostic_tail(preferred)}",
        display=False,
    )
    if revision_age_reset:
        return []
    return _resolve_revised_stage_progression(
        active_stage=active_stage,
        detected=detected,
        later_completed_sentences=later_completed_sentences,
        chunk_index=chunk_index,
        sentence_finalize_age=sentence_finalize_age,
        count_metric=count_metric,
        finalize_staged_sentence=finalize_staged_sentence,
        suppress_active_stage_for_quality=suppress_active_stage_for_quality,
        worker=worker,
        sentence_max_age_chunks=sentence_max_age_chunks,
        stage_quality_block_age_limit=stage_quality_block_age_limit,
        commit_buffer_node=commit_buffer_node,
    )

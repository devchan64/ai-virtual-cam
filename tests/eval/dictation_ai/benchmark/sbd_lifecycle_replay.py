from __future__ import annotations

from typing import Any

from src.app.dictation.node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation.pipeline_contracts import ActiveSentenceCandidate
from src.app.dictation_core.sentence_boundary import normalized_text
from src.app.dictation.pipeline_settings import (
    aged_queue_backlog_promotion_extra_age,
    delta_suppressed_stage_max_chunks,
    max_staged_sentence_queue,
    no_text_stale_stage_suppress_chunks,
    staged_queue_max_promotion_age_chunks,
)
from src.app.dictation_core.dictation_recent_final import _recent_final_output_delta_with_reason
from src.app.dictation_core.dictation_revision_progression import (
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _prefer_sentence_revision,
    _revision_internal_stability_bucket,
    _sentence_end_count,
    _should_age_staged_sentence,
    _should_preserve_revision_confirmation_from_internal_stability,
    _should_reset_revision_age,
)
from src.app.dictation_core.dictation_revision_text import (
    _final_sentence_diagnostic_flags,
    _is_cjk_text,
    _sentence_output_delta,
    _sentences_are_revisions,
    _word_units,
)
from src.app.dictation_core.dictation_transcript_logic import (
    _coalesce_completed_short_no_end_fragments,
    _has_later_completed_extension,
    _is_pending_prefix_mixed_candidate,
    _is_prior_pending_recent_final_mixed_candidate,
    _replacement_decision_reason,
    _sentence_max_age_chunks,
    _stage_quality_block_age_limit,
    _staged_sentence_required_confirmations,
    _should_confirm_staged_sentence,
    _should_defer_token_sentence_revision,
    _should_enable_aged_queue_backlog_promotion_boost,
    _should_defer_unconfirmed_replacement,
    _should_finalize_before_replacement,
    _should_finalize_with_right_context,
    _should_finalize_replaced_sentence,
    _should_preserve_staged_output_when_delta_fragment,
    _should_suppress_aged_low_value_final,
    _should_suppress_aged_no_end_marker_queue_final,
    _should_split_terminal_tail_revision,
    _should_stage_boundary_candidate,
    _should_suppress_delta_final,
    _strip_prior_pending_prefix_from_final,
    _strip_prior_pending_prefix_revision,
)
from src.app.dictation_core.stable_token_detection import analyze_stable_window
from src.app.dictation_core.transcript_revision import append_context as _append_committed_text
from src.app.dictation_core.transcript_revision import consume_committed_prefix as _consume_committed_prefix
from tests.eval.dictation_ai.benchmark.sbd_lifecycle_state import (
    LifecycleState,
    _stable_internal_chars,
    _stable_internal_ratio,
    _stable_overlap_source,
)
from tests.eval.dictation_ai.benchmark.sbd_lifecycle_scoring import (
    score_boundary_offsets,
    score_ordered_sequence,
    score_sequence,
)
from tests.eval.dictation_ai.cases.sbd_case_loader import SbdCase


def _commit_buffer_from_state(state: LifecycleState) -> SentenceCandidateCommitBufferNode:
    node = SentenceCandidateCommitBufferNode(max_staged_sentence_queue())
    active = ActiveSentenceCandidate(
        sentence=state.staged_sentence,
        confirmations=state.staged_confirmations,
        age=state.staged_age,
        forced=state.staged_forced,
        deferredAgeChunk=state.staged_deferred_age_chunk,
        deltaSuppressedChunks=state.staged_delta_suppressed_chunks,
        deltaSuppressedChunkIndex=state.staged_delta_suppressed_chunk_index,
    )
    node.load_snapshot(active=active, queue_entries=state.staged_queue or ())
    return node


def _sync_state_from_commit_buffer(state: LifecycleState, node: SentenceCandidateCommitBufferNode) -> None:
    state.staged_sentence = node.active.sentence
    state.staged_confirmations = node.active.confirmations
    state.staged_age = node.active.age
    state.staged_forced = node.active.forced
    state.staged_deferred_age_chunk = node.active.deferredAgeChunk
    state.staged_delta_suppressed_chunks = node.active.deltaSuppressedChunks
    state.staged_delta_suppressed_chunk_index = node.active.deltaSuppressedChunkIndex
    assert state.staged_queue is not None
    state.staged_queue.clear()
    state.staged_queue.extend(node.queue_entries())


def _count_segment_state(state: LifecycleState, segment_state: str, amount: int = 1) -> None:
    state.count(f"segment_state_{segment_state}", amount)


def _count_recent_final_stable_internal_suppression(state: LifecycleState, prefix: str) -> None:
    bucket = _revision_internal_stability_bucket(
        _stable_internal_ratio(state),
        _stable_internal_chars(state),
    )
    state.count(f"{prefix}_stable_internal_{bucket}")


def _promote_next_staged_sentence(state: LifecycleState, chunk_index: int) -> None:
    if state.staged_sentence:
        return
    node = _commit_buffer_from_state(state)
    while node.promote_if_idle(
        chunk_index=chunk_index,
        max_promotion_age_chunks=(
            staged_queue_max_promotion_age_chunks()
            + (
                max(0, aged_queue_backlog_promotion_extra_age())
                if state.queue_promotion_backlog_boost_remaining > 0
                else 0
            )
        ),
        count_metric=state.count,
        count_segment_state=lambda name, amount=1: _count_segment_state(state, name, amount),
    ):
        _sync_state_from_commit_buffer(state, node)
        if (
            state.queue_promotion_backlog_boost_remaining > 0
            and state.staged_age > staged_queue_max_promotion_age_chunks()
        ):
            state.queue_promotion_backlog_boost_remaining = max(0, state.queue_promotion_backlog_boost_remaining - 1)
            state.count("stage_queue_backlog_boost_promote")
        promoted_quality_flags = set(_final_sentence_diagnostic_flags(state.staged_sentence, state.language))
        if not _should_stage_boundary_candidate(state.staged_sentence, state.language):
            state.count("stage_queue_quality_suppressed")
            state.count("segment_state_suppressed")
            for flag in promoted_quality_flags:
                state.count(f"stage_queue_quality_{flag}")
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            node = _commit_buffer_from_state(state)
            continue
        promoted_sentence, recent_source, recent_reason = _recent_final_output_delta_with_reason(
            state.staged_sentence,
            tuple(state.final_sentences or ()),
            state.language,
        )
        if recent_source is None:
            return
        if promoted_sentence and _should_stage_boundary_candidate(promoted_sentence, state.language):
            state.staged_sentence = promoted_sentence
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            state.count("stage_queue_recent_final_delta_trimmed")
            state.count(f"stage_queue_recent_final_delta_trimmed_{recent_reason}")
            return
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        state.count("stage_queue_recent_final_suppressed")
        state.count(f"stage_queue_recent_final_suppressed_{recent_reason}")
        _count_recent_final_stable_internal_suppression(state, "stage_queue_recent_final_suppressed")
        state.count("segment_state_suppressed")
        node = _commit_buffer_from_state(state)


def _prefer_queued_revision_for_active(state: LifecycleState, chunk_index: int, finalize_reason: str) -> bool:
    node = _commit_buffer_from_state(state)
    deferred = node.prefer_queued_revision_for_active(
        chunk_index=chunk_index,
        max_promotion_age_chunks=staged_queue_max_promotion_age_chunks(),
        count_metric=state.count,
        count_segment_state=lambda name, amount=1: _count_segment_state(state, name, amount),
        finalize_reason=finalize_reason,
    )
    _sync_state_from_commit_buffer(state, node)
    return deferred


def _queue_staged_sentence(state: LifecycleState, candidate: str, forced: bool, chunk_index: int) -> None:
    node = _commit_buffer_from_state(state)
    node.enqueue_or_revision(
        candidate=candidate,
        forced=forced,
        chunk_index=chunk_index,
        stable_analysis=state.stable_analysis,
        count_metric=state.count,
        count_segment_state=lambda name, amount=1: _count_segment_state(state, name, amount),
    )
    _sync_state_from_commit_buffer(state, node)


def _finalize_staged_sentence(state: LifecycleState, language: str, reason: str, chunk_index: int) -> list[str]:
    if not state.staged_sentence:
        return []
    state.count("finalize_attempt")
    state.count(f"finalize_reason_{reason}")
    assert state.finalize_events is not None
    staged_before = state.staged_sentence
    queue_before = [str(entry["sentence"]) for entry in (state.staged_queue or ())]
    if _prefer_queued_revision_for_active(state, chunk_index, reason):
        state.finalize_events.append(
            {
                "chunk_index": chunk_index,
                "reason": reason,
                "staged_before": staged_before,
                "queue_before": queue_before,
                "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                "suppressed": "queued_revision_preferred",
                "output_sentence": "",
            }
        )
        return []
    output_sentence = _sentence_output_delta(state.committed_text, staged_before)
    if _should_preserve_staged_output_when_delta_fragment(staged_before, output_sentence, language):
        state.count("finalize_delta_fragment_preserved")
        output_sentence = staged_before
    assert state.final_sentences is not None
    output_sentence, recent_source, recent_reason = _recent_final_output_delta_with_reason(
        output_sentence,
        tuple(state.final_sentences),
        language,
    )
    if recent_source is not None:
        if output_sentence:
            state.count("finalize_recent_delta_trimmed")
            state.count(f"finalize_recent_delta_trimmed_{recent_reason}")
        else:
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            state.count("finalize_recent_echo_suppressed")
            state.count(f"finalize_recent_echo_suppressed_{recent_reason}")
            state.count("segment_state_suppressed")
            _promote_next_staged_sentence(state, chunk_index)
            state.finalize_events.append(
                {
                    "chunk_index": chunk_index,
                    "reason": reason,
                    "staged_before": staged_before,
                    "queue_before": queue_before,
                    "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                    "suppressed": f"recent_echo_{recent_reason}",
                    "output_sentence": "",
                }
            )
            return []
    if not output_sentence:
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        state.count("finalize_duplicate_suppressed")
        state.count("segment_state_suppressed")
        _promote_next_staged_sentence(state, chunk_index)
        state.finalize_events.append(
            {
                "chunk_index": chunk_index,
                "reason": reason,
                "staged_before": staged_before,
                "queue_before": queue_before,
                "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                "suppressed": "duplicate",
                "output_sentence": "",
            }
        )
        return []
    if _should_suppress_aged_low_value_final(
        staged_before,
        language,
        reason,
        state.staged_confirmations,
        state.staged_forced,
        tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
    ):
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        state.count("finalize_aged_low_value_suppressed")
        state.count("segment_state_suppressed")
        _promote_next_staged_sentence(state, chunk_index)
        state.finalize_events.append(
            {
                "chunk_index": chunk_index,
                "reason": reason,
                "staged_before": staged_before,
                "queue_before": queue_before,
                "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                "suppressed": "aged_low_value",
                "output_sentence": output_sentence,
            }
        )
        return []
    if _should_suppress_aged_no_end_marker_queue_final(
        staged_before,
        language,
        reason,
        state.staged_confirmations,
        tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
    ):
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        state.count("finalize_aged_no_end_marker_queue_suppressed")
        state.count("segment_state_suppressed")
        _promote_next_staged_sentence(state, chunk_index)
        state.finalize_events.append(
            {
                "chunk_index": chunk_index,
                "reason": reason,
                "staged_before": staged_before,
                "queue_before": queue_before,
                "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                "suppressed": "aged_no_end_marker_queue",
                "output_sentence": output_sentence,
            }
        )
        return []
    if _should_suppress_delta_final(staged_before, output_sentence, language, reason):
        state.count("finalize_delta_suppressed")
        if state.staged_delta_suppressed_chunk_index != chunk_index:
            state.staged_delta_suppressed_chunks += 1
        state.staged_delta_suppressed_chunk_index = chunk_index
        if state.staged_delta_suppressed_chunks >= delta_suppressed_stage_max_chunks():
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            state.count("finalize_delta_suppressed_stage_dropped")
            state.count("segment_state_suppressed")
            _promote_next_staged_sentence(state, chunk_index)
            state.finalize_events.append(
                {
                    "chunk_index": chunk_index,
                    "reason": reason,
                    "staged_before": staged_before,
                    "queue_before": queue_before,
                    "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                    "suppressed": "delta_stage_dropped",
                    "output_sentence": output_sentence,
                }
            )
            return []
        state.count("finalize_delta_suppressed_stage_retained")
        state.finalize_events.append(
            {
                "chunk_index": chunk_index,
                "reason": reason,
                "staged_before": staged_before,
                "queue_before": queue_before,
                "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
                "suppressed": "delta_stage_retained",
                "output_sentence": output_sentence,
            }
        )
        return []
    if _should_enable_aged_queue_backlog_promotion_boost(reason, len(state.staged_queue or ()), language):
        state.queue_promotion_backlog_boost_remaining = max(
            state.queue_promotion_backlog_boost_remaining,
            len(state.staged_queue or ()),
        )
        state.count("stage_queue_backlog_boost_enabled")
    state.staged_sentence = ""
    state.staged_confirmations = 0
    state.staged_age = 0
    state.staged_forced = False
    state.staged_deferred_age_chunk = -1
    state.staged_delta_suppressed_chunks = 0
    state.staged_delta_suppressed_chunk_index = -1
    state.count("finalized")
    state.count("segment_state_final")
    for flag in _final_sentence_diagnostic_flags(output_sentence, language):
        state.count(f"final_quality_{flag}")
    state.committed_text = _append_committed_text(state.committed_text, output_sentence)
    state.final_sentences.append(output_sentence)
    _promote_next_staged_sentence(state, chunk_index)
    state.finalize_events.append(
        {
            "chunk_index": chunk_index,
            "reason": reason,
            "staged_before": staged_before,
            "queue_before": queue_before,
            "queue_after": [str(entry["sentence"]) for entry in (state.staged_queue or ())],
            "suppressed": "",
            "output_sentence": output_sentence,
        }
    )
    return [output_sentence]


def _stage_completed_sentence(
    state: LifecycleState,
    sentence: str,
    language: str,
    *,
    forced: bool,
    sentence_finalize_age: int,
    chunk_index: int,
    prior_pending_text: str = "",
    later_completed_sentences: list[str] | tuple[str, ...] = (),
) -> list[str]:
    normalized_sentence = normalized_text(sentence)
    candidate = _sentence_output_delta(state.committed_text, normalized_sentence)
    if candidate and candidate != normalized_sentence:
        state.count("candidate_delta_trimmed")
        if _is_cjk_text(normalized_sentence):
            state.count("candidate_delta_trimmed_cjk")
    if state.staged_sentence and prior_pending_text and candidate:
        stripped_candidate = _strip_prior_pending_prefix_revision(
            state.staged_sentence,
            candidate,
            prior_pending_text,
        )
        if stripped_candidate != candidate:
            candidate = stripped_candidate
            state.count("candidate_prior_pending_prefix_trimmed")
    assert state.final_sentences is not None
    recent_candidate, recent_source, recent_reason = _recent_final_output_delta_with_reason(
        normalized_sentence,
        tuple(state.final_sentences),
        language,
    )
    if recent_source is not None and recent_candidate != candidate:
        candidate = recent_candidate
        state.count("candidate_recent_final_delta_trimmed")
        state.count(f"candidate_recent_final_delta_trimmed_{recent_reason}")
    if not candidate:
        state.count("candidate_duplicate_suppressed")
        if recent_source is not None:
            state.count(f"candidate_duplicate_suppressed_{recent_reason}")
            _count_recent_final_stable_internal_suppression(state, "candidate_duplicate_suppressed")
        state.count("segment_state_suppressed")
        return []
    if _is_pending_prefix_mixed_candidate(candidate, state.pending_text):
        state.count("candidate_pending_prefix_mixed_suppressed")
        state.count("segment_state_suppressed")
        return []
    assert state.final_sentences is not None
    if _is_prior_pending_recent_final_mixed_candidate(
        candidate,
        prior_pending_text,
        tuple(state.final_sentences),
        language,
    ):
        state.count("candidate_prior_pending_recent_final_mixed_suppressed")
        state.count("segment_state_suppressed")
        return []
    if not _should_stage_boundary_candidate(candidate, language):
        state.count("stage_candidate_quality_blocked")
        state.count("segment_state_suppressed")
        candidate_quality_flags = _final_sentence_diagnostic_flags(candidate, language)
        for flag in candidate_quality_flags:
            state.count(f"stage_candidate_quality_{flag}")
        if "no_end_marker" in candidate_quality_flags:
            if state.staged_sentence:
                state.count("stage_candidate_quality_no_end_marker_with_active_stage")
            if state.staged_queue:
                state.count("stage_candidate_quality_no_end_marker_with_queue")
            if not state.staged_sentence and not state.staged_queue:
                state.count("stage_candidate_quality_no_end_marker_without_blocker")
        for blocking_flag in ("short_no_end_fragment", "trailing_ellipsis"):
            if blocking_flag not in candidate_quality_flags:
                continue
            if state.staged_sentence:
                state.count(f"stage_candidate_quality_{blocking_flag}_with_active_stage")
            if state.staged_queue:
                state.count(f"stage_candidate_quality_{blocking_flag}_with_queue")
            if not state.staged_sentence and not state.staged_queue:
                state.count(f"stage_candidate_quality_{blocking_flag}_without_blocker")
            if blocking_flag == "short_no_end_fragment" and later_completed_sentences:
                state.count("stage_candidate_quality_short_no_end_fragment_with_later_completed")
        active_stage_flags = set(_final_sentence_diagnostic_flags(state.staged_sentence, language)) if state.staged_sentence else set()
        if (
            "short_no_end_fragment" in candidate_quality_flags
            and active_stage_flags.intersection({"no_end_marker", "short_cjk"})
            and state.staged_deferred_age_chunk != chunk_index
        ):
            state.staged_age += 1
            state.staged_deferred_age_chunk = chunk_index
            state.count("stage_blocked_short_no_end_aged_active_stage")
            state.count("stage_age_tick")
            if state.staged_age >= _stage_quality_block_age_limit(state.staged_sentence, language, state.staged_forced, sentence_finalize_age):
                state.count("stage_blocked_short_no_end_active_stage_quality_suppressed")
                state.count("stage_age_quality_blocked")
                state.count("segment_state_suppressed")
                state.staged_sentence = ""
                state.staged_confirmations = 0
                state.staged_age = 0
                state.staged_forced = False
                state.staged_deferred_age_chunk = -1
                state.staged_delta_suppressed_chunks = 0
                state.staged_delta_suppressed_chunk_index = -1
                _promote_next_staged_sentence(state, chunk_index)
        return []
    if not state.staged_sentence:
        _promote_next_staged_sentence(state, chunk_index)
    if not state.staged_sentence:
        state.count("stage_start")
        state.count("segment_state_staged")
        state.staged_sentence = candidate
        state.staged_confirmations = 1
        state.staged_age = 0
        state.staged_forced = forced
        state.staged_deferred_age_chunk = chunk_index
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        return []
    if _should_confirm_staged_sentence(
        state.staged_sentence,
        state.staged_confirmations,
        state.staged_forced,
    ) and _should_split_terminal_tail_revision(state.staged_sentence, candidate):
        state.count("stage_revision_terminal_tail_split")
        finalized = _finalize_staged_sentence(state, language, "terminal_tail_revision_split", chunk_index)
        if not state.staged_sentence:
            _promote_next_staged_sentence(state, chunk_index)
        if state.staged_sentence:
            _queue_staged_sentence(state, candidate, forced, chunk_index)
            return finalized
        state.count("stage_start")
        state.count("segment_state_staged")
        state.staged_sentence = candidate
        state.staged_confirmations = 1
        state.staged_age = 0
        state.staged_forced = forced
        state.staged_deferred_age_chunk = chunk_index
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        return finalized

    if _sentences_are_revisions(state.staged_sentence, candidate):
        state.count("stage_revision")
        state.count("segment_state_revised")
        previous = state.staged_sentence
        preferred = _prefer_sentence_revision(previous, candidate)
        preferred_changed = preferred != previous
        if preferred_changed:
            state.count("stage_revision_changed")
            defer_token_sentence_revision = _should_defer_token_sentence_revision(
                previous,
                preferred,
                state.staged_confirmations,
                state.staged_forced or forced,
                _stable_internal_ratio(state),
                _stable_internal_chars(state),
                _stable_overlap_source(state),
            )
            if _is_cjk_text(previous) or _is_cjk_text(preferred):
                state.count(
                    "stage_revision_internal_stability_"
                    + _revision_internal_stability_bucket(
                        _stable_internal_ratio(state),
                        _stable_internal_chars(state),
                    )
                )
                if not defer_token_sentence_revision:
                    if _should_preserve_revision_confirmation_from_internal_stability(
                        previous,
                        preferred,
                        _stable_internal_ratio(state),
                        _stable_internal_chars(state),
                        _stable_overlap_source(state),
                    ):
                        state.count("stage_revision_confirmation_preserved_internal")
                    else:
                        state.count("stage_revision_confirmation_reset")
            if defer_token_sentence_revision:
                state.count("stage_revision_token_sentence_deferred")
                _queue_staged_sentence(state, preferred, forced, chunk_index)
                if state.staged_deferred_age_chunk != chunk_index:
                    state.staged_age += 1
                    state.staged_deferred_age_chunk = chunk_index
                    state.count("stage_age_tick")
                if _should_confirm_staged_sentence(
                    state.staged_sentence,
                    state.staged_confirmations,
                    state.staged_forced,
                ):
                    state.count("stage_confirmed_before_deferred_revision")
                    return _finalize_staged_sentence(
                        state,
                        language,
                        "confirmed_forced" if state.staged_forced else "confirmed",
                        chunk_index,
                    )
                if (
                    state.staged_age >= _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age)
                    and _should_finalize_before_replacement(
                        state.staged_sentence,
                        language,
                        state.staged_confirmations,
                    state.staged_age,
                    sentence_finalize_age,
                    state.staged_forced,
                    tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
                )
            ):
                    state.count("stage_age_finalize")
                    finalized = _finalize_staged_sentence(
                        state,
                        language,
                        "aged_forced" if state.staged_forced else "aged",
                        chunk_index,
                    )
                    _promote_next_staged_sentence(state, chunk_index)
                    return finalized
                if state.staged_age >= _stage_quality_block_age_limit(state.staged_sentence, language, state.staged_forced, sentence_finalize_age):
                    state.count("stage_age_quality_blocked")
                    state.count("segment_state_suppressed")
                    state.staged_sentence = ""
                    state.staged_confirmations = 0
                    state.staged_age = 0
                    state.staged_forced = False
                    state.staged_deferred_age_chunk = -1
                    state.staged_delta_suppressed_chunks = 0
                    state.staged_delta_suppressed_chunk_index = -1
                    _promote_next_staged_sentence(state, chunk_index)
                return []
        state.staged_sentence = preferred
        if preferred_changed:
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
        state.staged_confirmations = _next_revision_confirmation_count(
            previous,
            preferred,
            state.staged_confirmations,
            _stable_internal_ratio(state),
            _stable_internal_chars(state),
            _stable_overlap_source(state),
        )
        revision_age_reset = _should_reset_revision_age(
            previous,
            preferred,
            _stable_internal_ratio(state),
            _stable_internal_chars(state),
            _stable_overlap_source(state),
        )
        if revision_age_reset:
            state.staged_age = 0
            state.count("stage_revision_age_reset")
        else:
            state.staged_age += 1
        state.staged_deferred_age_chunk = chunk_index
        state.count("stage_age_tick")
        state.staged_forced = state.staged_forced or forced
        if revision_age_reset:
            return []
        defer_for_later_extension = _has_later_completed_extension(state.staged_sentence, later_completed_sentences)
        if defer_for_later_extension:
            state.count("stage_confirm_deferred_later_extension")
        if not defer_for_later_extension and _should_confirm_staged_sentence(
            state.staged_sentence,
            state.staged_confirmations,
            state.staged_forced,
        ):
            return _finalize_staged_sentence(state, language, "confirmed_forced" if state.staged_forced else "confirmed", chunk_index)
        if not defer_for_later_extension and _should_finalize_before_replacement(
            state.staged_sentence,
            language,
            state.staged_confirmations,
            state.staged_age,
            sentence_finalize_age,
            state.staged_forced,
            tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
        ):
            max_age = _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age)
            if state.staged_age >= max_age:
                state.count("stage_age_finalize")
                reason = "aged_forced" if state.staged_forced else "aged"
            else:
                state.count("stage_finalize_before_replace")
                reason = "next_completed"
            return _finalize_staged_sentence(state, language, reason, chunk_index)
        if not defer_for_later_extension and state.staged_age >= _stage_quality_block_age_limit(state.staged_sentence, language, state.staged_forced, sentence_finalize_age):
            state.count("stage_age_quality_blocked")
            state.count("segment_state_suppressed")
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            _promote_next_staged_sentence(state, chunk_index)
            return []
        return []

    state.count("stage_replace")
    replacement_reason = _replacement_decision_reason(
        state.staged_sentence,
        candidate,
        state.staged_confirmations,
        state.staged_forced,
        state.staged_age,
        sentence_finalize_age,
    )
    state.count(f"stage_replace_decision_{replacement_reason}")
    if _should_defer_unconfirmed_replacement(replacement_reason):
        _queue_staged_sentence(state, candidate, forced, chunk_index)
        state.count("stage_replace_deferred")
        if state.staged_deferred_age_chunk != chunk_index:
            state.staged_age += 1
            state.staged_deferred_age_chunk = chunk_index
            state.count("stage_age_tick")
        if (
            state.staged_age >= _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age)
            and _should_finalize_before_replacement(
                state.staged_sentence,
                language,
                state.staged_confirmations,
                state.staged_age,
                sentence_finalize_age,
                state.staged_forced,
                tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
            )
        ):
            state.count("stage_age_finalize")
            finalized = _finalize_staged_sentence(
                state,
                language,
                "aged_forced" if state.staged_forced else "aged",
                chunk_index,
            )
            _promote_next_staged_sentence(state, chunk_index)
            return finalized
        if state.staged_age >= _stage_quality_block_age_limit(state.staged_sentence, language, state.staged_forced, sentence_finalize_age):
            state.count("stage_age_quality_blocked")
            state.count("segment_state_suppressed")
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            _promote_next_staged_sentence(state, chunk_index)
        return []
    allow_same_chunk_suffix_replacement = (
        replacement_reason == "duplicate_or_suffix"
        and _sentence_end_count(candidate) > 0
        and _should_stage_boundary_candidate(candidate, language)
    )
    if state.staged_deferred_age_chunk == chunk_index and not allow_same_chunk_suffix_replacement:
        _queue_staged_sentence(state, candidate, forced, chunk_index)
        state.count("stage_replace_deferred_same_chunk")
        return []
    if allow_same_chunk_suffix_replacement:
        state.count("stage_replace_same_chunk_suffix_allowed")
        stripped_stage = _strip_prior_pending_prefix_from_final(state.staged_sentence, prior_pending_text)
        if stripped_stage != state.staged_sentence:
            state.staged_sentence = stripped_stage
            state.count("stage_replace_same_chunk_prior_pending_prefix_stripped")
    if _should_finalize_replaced_sentence(
        state.staged_sentence,
        candidate,
        language,
        state.staged_confirmations,
        state.staged_forced,
        state.staged_age,
        sentence_finalize_age,
    ):
        finalized = _finalize_staged_sentence(state, language, f"replaced_{replacement_reason}", chunk_index)
    elif _should_finalize_before_replacement(
        state.staged_sentence,
        language,
        state.staged_confirmations,
        state.staged_age,
        sentence_finalize_age,
        state.staged_forced,
        tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
    ):
        state.count("stage_finalize_before_replace")
        finalized = _finalize_staged_sentence(state, language, "next_completed", chunk_index)
    else:
        state.count("stage_replaced_unconfirmed")
        state.count("segment_state_suppressed")
        finalized = []
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
    if not state.staged_sentence:
        _promote_next_staged_sentence(state, chunk_index)
    if state.staged_sentence:
        _queue_staged_sentence(state, candidate, forced, chunk_index)
        return finalized
    state.count("stage_start")
    state.count("segment_state_staged")
    state.staged_sentence = candidate
    state.staged_confirmations = 1
    state.staged_age = 0
    state.staged_forced = forced
    state.staged_deferred_age_chunk = chunk_index
    state.staged_delta_suppressed_chunks = 0
    state.staged_delta_suppressed_chunk_index = -1
    return finalized


def _age_staged_sentence(state: LifecycleState, language: str, sentence_finalize_age: int, chunk_index: int) -> list[str]:
    if not state.staged_sentence:
        return []
    if not _should_age_staged_sentence(state.staged_sentence, state.pending_text):
        state.count("stage_age_hold")
        return []
    state.staged_age += 1
    state.staged_deferred_age_chunk = chunk_index
    state.count("stage_age_tick")
    if state.staged_age < _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age):
        return []
    if _should_confirm_staged_sentence(
        state.staged_sentence,
        state.staged_confirmations,
        state.staged_forced,
    ):
        state.count("stage_confirmed_before_age_queue")
        return _finalize_staged_sentence(
            state,
            language,
            "confirmed_forced" if state.staged_forced else "confirmed",
            chunk_index,
        )
    if not _should_finalize_before_replacement(
        state.staged_sentence,
        language,
        state.staged_confirmations,
        state.staged_age,
        sentence_finalize_age,
        state.staged_forced,
        tuple(str(entry["sentence"]) for entry in (state.staged_queue or ())),
    ):
        if state.staged_age < _stage_quality_block_age_limit(state.staged_sentence, language, state.staged_forced, sentence_finalize_age):
            return []
        state.count("stage_age_quality_blocked")
        state.count("segment_state_suppressed")
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        _promote_next_staged_sentence(state, chunk_index)
        return []
    state.count("stage_age_finalize")
    return _finalize_staged_sentence(state, language, "aged_forced" if state.staged_forced else "aged", chunk_index)


def _finalize_right_context_staged_sentences(
    state: LifecycleState,
    language: str,
    chunk_index: int,
) -> list[str]:
    produced: list[str] = []
    while (
        state.staged_sentence
        and state.staged_queue
        and state.staged_deferred_age_chunk < chunk_index
        and _should_finalize_with_right_context(
            state.staged_sentence,
            language,
            tuple(str(entry["sentence"]) for entry in state.staged_queue),
        )
    ):
        state.count("stage_finalize_right_context")
        finalized = _finalize_staged_sentence(state, language, "right_context", chunk_index)
        if not finalized:
            break
        produced.extend(finalized)
    return produced


def _suppress_stale_no_text_stage(state: LifecycleState, chunk_index: int) -> None:
    if not state.staged_sentence:
        state.no_text_stage_skip_chunks = 0
        return
    required_confirmations = _staged_sentence_required_confirmations(state.staged_sentence, state.staged_forced)
    if state.staged_confirmations >= required_confirmations:
        return
    if state.no_text_stage_skip_chunks < no_text_stale_stage_suppress_chunks():
        return
    state.count("stage_no_text_stale_suppressed")
    state.count("segment_state_suppressed")
    state.staged_sentence = ""
    state.staged_confirmations = 0
    state.staged_age = 0
    state.staged_forced = False
    state.staged_deferred_age_chunk = -1
    state.staged_delta_suppressed_chunks = 0
    state.staged_delta_suppressed_chunk_index = -1
    state.no_text_stage_skip_chunks = 0
    _promote_next_staged_sentence(state, chunk_index)


def _run_lifecycle_case(case: SbdCase, detector: Any) -> dict[str, Any]:
    state = LifecycleState(language=case.language)
    initial_final_count = 0
    for initial_sentence in case.initial_final:
        normalized_initial = normalized_text(initial_sentence)
        if not normalized_initial:
            continue
        state.committed_text = _append_committed_text(state.committed_text, normalized_initial)
        assert state.final_sentences is not None
        state.final_sentences.append(normalized_initial)
        initial_final_count += 1
    chunks: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(case.chunks, start=1):
        assert state.finalize_events is not None
        state.finalize_events.clear()
        prior_pending_text = state.pending_text
        window_text = normalized_text(chunk)
        state.stable_analysis = analyze_stable_window(state.previous_window_text, window_text, case.language)
        state.previous_window_text = window_text
        if getattr(state.stable_analysis, "current_units", 0):
            state.count("stable_window_observed")
            state.count("stable_prefix_chars", int(state.stable_analysis.stable_prefix_chars))
            state.count("unstable_tail_chars", int(state.stable_analysis.unstable_tail_chars))
            state.count("stable_internal_chars", int(state.stable_analysis.stable_internal_chars))
            state.count(
                "stable_internal_ratio_per_1000",
                int(round(float(state.stable_analysis.stable_internal_ratio) * 1000)),
            )
            state.count(
                "stable_token_ratio_per_1000",
                int(round(float(state.stable_analysis.stable_token_ratio) * 1000)),
            )
            state.count(f"stable_overlap_source_{state.stable_analysis.stable_overlap_source}")
        if window_text:
            state.no_text_stage_skip_chunks = 0
        boundary = detector.split(state.pending_text, chunk, case.language)
        completed = []
        for sentence in boundary.completed:
            completed.append(normalized_text(sentence))
        coalesced_completed = list(_coalesce_completed_short_no_end_fragments(completed, case.language))
        if coalesced_completed != completed:
            state.count("completed_short_no_end_coalesced")
            state.count("completed_short_no_end_coalesced_delta", len(completed) - len(coalesced_completed))
            completed = coalesced_completed
        state.pending_text = normalized_text(boundary.pending)
        if boundary.end_mark_count:
            state.count("boundary_end_marks", boundary.end_mark_count)
        if boundary.right_context_start_count:
            state.count("boundary_right_context_starts", boundary.right_context_start_count)
        if completed:
            state.pending_chunks = 0
        elif state.pending_text:
            state.pending_chunks += 1
            state.count("segment_state_pending")
        produced: list[str] = []
        for sentence_index, sentence in enumerate(completed):
            finalized = _stage_completed_sentence(
                state,
                sentence,
                case.language,
                forced=False,
                sentence_finalize_age=case.sentence_finalize_age,
                chunk_index=chunk_index,
                prior_pending_text=prior_pending_text,
                later_completed_sentences=completed[sentence_index + 1 :],
            )
            produced.extend(finalized)
            for produced_sentence in finalized:
                state.pending_text = _consume_committed_prefix(state.pending_text, produced_sentence)
                if not state.pending_text:
                    state.pending_chunks = 0
        if completed:
            produced.extend(_finalize_right_context_staged_sentences(state, case.language, chunk_index))
            produced.extend(_age_staged_sentence(state, case.language, case.sentence_finalize_age, chunk_index))
        if state.pending_text and completed:
            state.count("segment_state_pending")
        if not completed and (state.pending_text or window_text):
            produced.extend(_age_staged_sentence(state, case.language, case.sentence_finalize_age, chunk_index))
        if not completed and not state.pending_text and not window_text:
            state.count("stage_age_no_text_skipped")
            if state.staged_sentence:
                state.no_text_stage_skip_chunks += 1
                _suppress_stale_no_text_stage(state, chunk_index)
            else:
                state.no_text_stage_skip_chunks = 0
        pending_overrun = _pending_overrun_reason(state.pending_text, state.pending_chunks)
        if pending_overrun:
            state.count("pending_overrun")
            state.count(f"pending_overrun_reason_{pending_overrun}")
        for flag in _pending_text_diagnostic_flags(state.pending_text, case.language, state.pending_chunks):
            state.count(f"pending_quality_{flag}")
        chunks.append(
            {
                "index": chunk_index,
                "input": chunk,
                "completed": completed,
                "pending": state.pending_text,
                "staged": state.staged_sentence,
                "staged_confirmations": state.staged_confirmations,
                "staged_age": state.staged_age,
                "finalized": produced,
                "finalized_events": list(state.finalize_events),
                "boundary_count": boundary.boundary_count,
                "end_mark_count": boundary.end_mark_count,
                "right_context_start_count": boundary.right_context_start_count,
            }
        )
    assert state.final_sentences is not None
    assert state.metrics is not None
    assert state.staged_queue is not None
    return {
        "chunks": chunks,
        "actual_completed_last": chunks[-1]["completed"] if chunks else [],
        "actual_pending": state.pending_text,
        "actual_final": state.final_sentences[initial_final_count:],
        "initial_final": state.final_sentences[:initial_final_count],
        "actual_staged": state.staged_sentence,
        "actual_staged_queue": [str(entry["sentence"]) for entry in state.staged_queue],
        "committed_text": state.committed_text,
        "metrics": state.metrics,
    }

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.app.sentence_boundary import normalized_text
from src.app.dictation_pipeline_settings import (
    FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
    delta_suppressed_stage_max_chunks,
    max_staged_sentence_queue,
    no_text_stale_stage_suppress_chunks,
    staged_queue_max_promotion_age_chunks,
)
from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _has_later_completed_extension,
    _is_cjk_text,
    _is_pending_prefix_mixed_candidate,
    _is_prior_pending_recent_final_mixed_candidate,
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _prefer_sentence_revision,
    _recent_final_output_delta,
    _replacement_decision_reason,
    _revision_internal_stability_bucket,
    _sentence_max_age_chunks,
    _sentence_end_count,
    _sentence_output_delta,
    _sentences_are_revisions,
    _stage_quality_block_age_limit,
    _staged_sentence_required_confirmations,
    _should_age_staged_sentence,
    _should_confirm_staged_sentence,
    _should_defer_token_sentence_revision,
    _should_defer_unconfirmed_replacement,
    _should_finalize_before_replacement,
    _should_finalize_with_right_context,
    _should_finalize_replaced_sentence,
    _should_preserve_revision_confirmation_from_internal_stability,
    _should_preserve_staged_output_when_delta_fragment,
    _should_reset_revision_age,
    _should_split_terminal_tail_revision,
    _should_stage_boundary_candidate,
    _should_suppress_delta_final,
    _strip_prior_pending_prefix_revision,
    _word_units,
)
from src.app.stable_token_detection import analyze_stable_window
from src.app.transcript_revision import append_context as _append_committed_text
from src.app.transcript_revision import consume_committed_prefix as _consume_committed_prefix
from tests.eval.dictation_ai.benchmark.sbd_lifecycle_state import (
    LifecycleState,
    _stable_internal_chars,
    _stable_internal_ratio,
    _stable_overlap_source,
)
from tests.eval.dictation_ai.cases.sbd_case_loader import SbdCase


def _promote_next_staged_sentence(state: LifecycleState, chunk_index: int) -> None:
    if state.staged_sentence:
        return
    assert state.staged_queue is not None
    while state.staged_queue:
        entry = state.staged_queue.popleft()
        state.staged_sentence = str(entry["sentence"])
        state.staged_confirmations = int(entry["confirmations"])
        state.staged_age = int(entry["age"])
        state.staged_forced = bool(entry["forced"])
        deferred_age_chunk = int(entry["deferred_age_chunk"])
        state.staged_deferred_age_chunk = chunk_index if deferred_age_chunk < 0 else deferred_age_chunk
        if deferred_age_chunk >= 0:
            state.staged_age = max(state.staged_age, chunk_index - deferred_age_chunk)
        if state.staged_age > staged_queue_max_promotion_age_chunks():
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            state.count("stage_queue_stale_promote_suppressed")
            state.count("segment_state_suppressed")
            continue
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        state.count("stage_queue_promote")
        state.count("stage_start")
        state.count("segment_state_staged")
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
            continue
        promoted_sentence, recent_source = _recent_final_output_delta(
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
            return
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        state.count("stage_queue_recent_final_suppressed")
        state.count("segment_state_suppressed")


def _prefer_queued_revision_for_active(state: LifecycleState, chunk_index: int, finalize_reason: str) -> bool:
    if not state.staged_sentence:
        return False
    assert state.staged_queue is not None
    index = 0
    max_promotion_age = staged_queue_max_promotion_age_chunks()
    while index < len(state.staged_queue):
        entry = state.staged_queue[index]
        deferred_age_chunk = int(entry["deferred_age_chunk"])
        queued_age = int(entry["age"])
        if deferred_age_chunk >= 0:
            queued_age = max(queued_age, chunk_index - deferred_age_chunk)
        entry["age"] = queued_age
        if queued_age > max_promotion_age:
            del state.staged_queue[index]
            state.count("stage_queue_stale_promote_suppressed")
            state.count("segment_state_suppressed")
            continue
        queued_sentence = str(entry["sentence"])
        if not _sentences_are_revisions(state.staged_sentence, queued_sentence):
            index += 1
            continue
        preferred = _prefer_sentence_revision(state.staged_sentence, queued_sentence)
        if preferred == state.staged_sentence:
            index += 1
            continue
        queued_confirmations = int(entry["confirmations"])
        queued_forced = bool(entry["forced"]) or state.staged_forced
        if (
            _sentence_end_count(state.staged_sentence) > 0
            and _sentence_end_count(preferred) <= _sentence_end_count(state.staged_sentence)
            and queued_confirmations < _staged_sentence_required_confirmations(preferred, queued_forced)
        ):
            state.count("stage_queue_revision_preempt_deferred")
            state.count(f"stage_queue_revision_preempt_deferred_{finalize_reason}")
            index += 1
            continue
        entry["sentence"] = preferred
        state.staged_sentence = str(entry["sentence"])
        state.staged_confirmations = int(entry["confirmations"])
        state.staged_age = int(entry["age"])
        state.staged_forced = bool(entry["forced"])
        state.staged_deferred_age_chunk = int(entry["deferred_age_chunk"])
        state.staged_delta_suppressed_chunks = 0
        state.staged_delta_suppressed_chunk_index = -1
        del state.staged_queue[index]
        state.count("stage_finalize_deferred_for_queue_revision")
        state.count("stage_revision")
        state.count("segment_state_revised")
        return True
    return False


def _queue_staged_sentence(state: LifecycleState, candidate: str, forced: bool, chunk_index: int) -> None:
    assert state.staged_queue is not None
    for entry in state.staged_queue:
        queued_sentence = str(entry["sentence"])
        if not _sentences_are_revisions(queued_sentence, candidate):
            continue
        preferred = _prefer_sentence_revision(queued_sentence, candidate)
        reset_age = _should_reset_revision_age(
            queued_sentence,
            preferred,
            _stable_internal_ratio(state),
            _stable_internal_chars(state),
            _stable_overlap_source(state),
        )
        if reset_age:
            # Runtime parity: unstable revision of the same queued utterance is not a new segment.
            state.count("stage_queue_revision_token_sentence_deferred")
            return
        entry["sentence"] = preferred
        entry["confirmations"] = _next_revision_confirmation_count(
            queued_sentence,
            preferred,
            int(entry["confirmations"]),
            _stable_internal_ratio(state),
            _stable_internal_chars(state),
            _stable_overlap_source(state),
        )
        entry["age"] = int(entry["age"]) + 1
        entry["forced"] = bool(entry["forced"]) or forced
        entry["deferred_age_chunk"] = chunk_index
        state.count("stage_queue_revision")
        state.count("stage_age_tick")
        return
    if len(state.staged_queue) >= max_staged_sentence_queue():
        state.staged_queue.popleft()
        state.count("stage_queue_drop_oldest")
    state.staged_queue.append(
        {
            "sentence": candidate,
            "confirmations": 1,
            "age": 0,
            "forced": forced,
            "deferred_age_chunk": chunk_index,
        }
    )
    state.count("stage_queue_enqueue")
    state.count("segment_state_staged")


def _boundary_offsets(sentences: list[str]) -> set[int]:
    offsets: set[int] = set()
    cursor = 0
    for sentence in sentences:
        normalized = normalized_text(sentence)
        if not normalized:
            continue
        cursor += len(normalized)
        offsets.add(cursor)
        cursor += 1
    return offsets


def _score_boundary_offsets(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "exact": True,
        }
    expected_offsets = _boundary_offsets(expected_normalized)
    actual_offsets = _boundary_offsets(actual_normalized)
    true_positive = len(expected_offsets & actual_offsets)
    false_positive = len(actual_offsets - expected_offsets)
    false_negative = len(expected_offsets - actual_offsets)
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact": actual_normalized == expected_normalized,
    }


def _sentence_similarity(left: str, right: str) -> float:
    left_words = _word_units(left)
    right_words = _word_units(right)
    if left_words and right_words:
        return SequenceMatcher(None, left_words, right_words, autojunk=False).ratio()
    return SequenceMatcher(None, normalized_text(left), normalized_text(right), autojunk=False).ratio()


def _score_sequence(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "similarity_avg": 1.0,
            "similarity_coverage": 1.0,
            "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
            "exact": True,
        }
    used_actual: set[int] = set()
    matched_similarities: list[float] = []
    for expected_sentence in expected_normalized:
        best_index = -1
        best_similarity = 0.0
        for actual_index, actual_sentence in enumerate(actual_normalized):
            if actual_index in used_actual:
                continue
            similarity = _sentence_similarity(expected_sentence, actual_sentence)
            if similarity > best_similarity:
                best_index = actual_index
                best_similarity = similarity
        if best_index >= 0 and best_similarity >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            used_actual.add(best_index)
            matched_similarities.append(best_similarity)
    true_positive = len(matched_similarities)
    false_positive = len(actual_normalized) - len(used_actual)
    false_negative = len(expected_normalized) - true_positive
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    similarity_avg = sum(matched_similarities) / max(true_positive, 1)
    similarity_coverage = sum(matched_similarities) / max(len(expected_normalized), len(actual_normalized), 1)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_avg": similarity_avg,
        "similarity_coverage": similarity_coverage,
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "exact": actual_normalized == expected_normalized,
    }


def _score_ordered_sequence(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "similarity_avg": 1.0,
            "similarity_coverage": 1.0,
            "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
            "exact": True,
        }
    actual_index = 0
    matched_similarities: list[float] = []
    for expected_sentence in expected_normalized:
        best_index = -1
        best_similarity = 0.0
        for index in range(actual_index, len(actual_normalized)):
            similarity = _sentence_similarity(expected_sentence, actual_normalized[index])
            if similarity > best_similarity:
                best_index = index
                best_similarity = similarity
        if best_index >= 0 and best_similarity >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            actual_index = best_index + 1
            matched_similarities.append(best_similarity)
    true_positive = len(matched_similarities)
    false_positive = len(actual_normalized) - true_positive
    false_negative = len(expected_normalized) - true_positive
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    similarity_avg = sum(matched_similarities) / max(true_positive, 1)
    similarity_coverage = sum(matched_similarities) / max(len(expected_normalized), len(actual_normalized), 1)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_avg": similarity_avg,
        "similarity_coverage": similarity_coverage,
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "exact": actual_normalized == expected_normalized,
    }


def _finalize_staged_sentence(state: LifecycleState, language: str, reason: str, chunk_index: int) -> list[str]:
    if not state.staged_sentence:
        return []
    state.count("finalize_attempt")
    state.count(f"finalize_reason_{reason}")
    if _prefer_queued_revision_for_active(state, chunk_index, reason):
        return []
    staged_before = state.staged_sentence
    output_sentence = _sentence_output_delta(state.committed_text, staged_before)
    if _should_preserve_staged_output_when_delta_fragment(staged_before, output_sentence, language):
        state.count("finalize_delta_fragment_preserved")
        output_sentence = staged_before
    assert state.final_sentences is not None
    output_sentence, recent_source = _recent_final_output_delta(output_sentence, tuple(state.final_sentences), language)
    if recent_source is not None:
        if output_sentence:
            state.count("finalize_recent_delta_trimmed")
        else:
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            state.staged_delta_suppressed_chunks = 0
            state.staged_delta_suppressed_chunk_index = -1
            state.count("finalize_recent_echo_suppressed")
            state.count("segment_state_suppressed")
            _promote_next_staged_sentence(state, chunk_index)
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
            return []
        state.count("finalize_delta_suppressed_stage_retained")
        return []
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
    recent_candidate, recent_source = _recent_final_output_delta(
        normalized_sentence,
        tuple(state.final_sentences),
        language,
    )
    if recent_source is not None and recent_candidate != candidate:
        candidate = recent_candidate
        state.count("candidate_recent_final_delta_trimmed")
    if not candidate:
        state.count("candidate_duplicate_suppressed")
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
    if state.staged_deferred_age_chunk == chunk_index:
        _queue_staged_sentence(state, candidate, forced, chunk_index)
        state.count("stage_replace_deferred_same_chunk")
        return []
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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.sentence_boundary import create_sentence_boundary_detector, normalized_text
from src.app.dictation_pipeline_settings import (
    FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
    MAX_STAGED_SENTENCE_QUEUE,
    NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS,
    SBD_BENCHMARK_BACKEND,
    SBD_BENCHMARK_COMPUTE_TYPE,
    SBD_BENCHMARK_DEVICE,
    SBD_BENCHMARK_MODEL,
    dictation_pipeline_policy,
)
from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _has_later_completed_extension,
    _is_pending_prefix_mixed_candidate,
    _is_prior_pending_recent_final_mixed_candidate,
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _prefer_sentence_revision,
    _recent_final_output_delta,
    _replacement_decision_reason,
    _revision_similarity_policy,
    _sentence_max_age_chunks,
    _sentence_output_delta,
    _sentence_required_confirmations,
    _sentences_are_revisions,
    _word_units,
    _should_age_staged_sentence,
    _should_confirm_staged_sentence,
    _should_defer_unconfirmed_replacement,
    _should_finalize_before_replacement,
    _should_finalize_replaced_sentence,
    _should_reset_revision_age,
    _should_split_terminal_tail_revision,
    _should_stage_boundary_candidate,
    _should_suppress_delta_final,
    _strip_prior_pending_prefix_revision,
)
from src.app.transcript_revision import append_context as _append_committed_text
from src.app.transcript_revision import consume_committed_prefix as _consume_committed_prefix


@dataclass(frozen=True)
class SbdCase:
    id: str
    language: str
    chunks: list[str]
    expected_completed: list[str]
    expected_pending: str
    expected_final: list[str]
    expected_staged: str
    tags: tuple[str, ...]
    sentence_finalize_age: int


@dataclass
class LifecycleState:
    committed_text: str = ""
    pending_text: str = ""
    pending_chunks: int = 0
    staged_sentence: str = ""
    staged_confirmations: int = 0
    staged_age: int = 0
    staged_forced: bool = False
    staged_deferred_age_chunk: int = -1
    no_text_stage_skip_chunks: int = 0
    staged_queue: deque[dict[str, object]] | None = None
    final_sentences: list[str] | None = None
    metrics: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.staged_queue is None:
            self.staged_queue = deque()
        if self.final_sentences is None:
            self.final_sentences = []
        if self.metrics is None:
            self.metrics = {}

    def count(self, name: str, amount: int = 1) -> None:
        assert self.metrics is not None
        self.metrics[name] = self.metrics.get(name, 0) + amount


def _promote_next_staged_sentence(state: LifecycleState, chunk_index: int) -> None:
    if state.staged_sentence:
        return
    assert state.staged_queue is not None
    if not state.staged_queue:
        return
    entry = state.staged_queue.popleft()
    state.staged_sentence = str(entry["sentence"])
    state.staged_confirmations = int(entry["confirmations"])
    state.staged_age = int(entry["age"])
    state.staged_forced = bool(entry["forced"])
    state.staged_deferred_age_chunk = chunk_index
    state.count("stage_queue_promote")
    state.count("stage_start")
    state.count("segment_state_staged")


def _queue_staged_sentence(state: LifecycleState, candidate: str, forced: bool, chunk_index: int) -> None:
    assert state.staged_queue is not None
    for entry in state.staged_queue:
        queued_sentence = str(entry["sentence"])
        if not _sentences_are_revisions(queued_sentence, candidate):
            continue
        preferred = _prefer_sentence_revision(queued_sentence, candidate)
        reset_age = _should_reset_revision_age(queued_sentence, preferred)
        entry["sentence"] = preferred
        entry["confirmations"] = _next_revision_confirmation_count(
            queued_sentence,
            preferred,
            int(entry["confirmations"]),
        )
        entry["age"] = 0 if reset_age else int(entry["age"]) + 1
        entry["forced"] = bool(entry["forced"]) or forced
        entry["deferred_age_chunk"] = chunk_index
        state.count("stage_queue_revision")
        if reset_age:
            state.count("stage_queue_revision_age_reset")
        state.count("stage_age_tick")
        return
    if len(state.staged_queue) >= MAX_STAGED_SENTENCE_QUEUE:
        state.staged_queue.popleft()
        state.count("stage_queue_drop_oldest")
    state.staged_queue.append(
        {
            "sentence": candidate,
            "confirmations": 1,
            "age": 0,
            "forced": forced,
            "deferred_age_chunk": -1,
        }
    )
    state.count("stage_queue_enqueue")
    state.count("segment_state_staged")


def _load_cases(path: Path) -> list[SbdCase]:
    cases: list[SbdCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            case_id = str(payload.get("id") or f"{path.name}:{line_no}").strip()
            chunks = payload.get("chunks")
            if chunks is None:
                chunks = [payload.get("text", "")]
            normalized_chunks = [normalized_text(chunk) for chunk in chunks]
            if not any(normalized_chunks):
                raise ValueError(f"{path}:{line_no} case {case_id!r} has no text chunks")
            cases.append(
                SbdCase(
                    id=case_id,
                    language=str(payload.get("language", "")).strip().lower() or "en",
                    chunks=normalized_chunks,
                    expected_completed=[normalized_text(item) for item in payload.get("expected_completed", [])],
                    expected_pending=normalized_text(str(payload.get("expected_pending", ""))),
                    expected_final=[normalized_text(item) for item in payload.get("expected_final", [])],
                    expected_staged=normalized_text(str(payload.get("expected_staged", ""))),
                    tags=tuple(str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()),
                    sentence_finalize_age=int(payload.get("sentence_finalize_age", 3)),
                )
            )
    if not cases:
        raise ValueError(f"no SBD benchmark cases loaded from {path}")
    return cases


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


def _average_scores(results: list[dict[str, Any]], key: str) -> dict[str, float]:
    if not results:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "similarity_coverage": 0.0}
    return {
        "precision": sum(float(result[key]["precision"]) for result in results) / len(results),
        "recall": sum(float(result[key]["recall"]) for result in results) / len(results),
        "f1": sum(float(result[key]["f1"]) for result in results) / len(results),
        "similarity_coverage": sum(float(result[key].get("similarity_coverage", 0.0)) for result in results)
        / len(results),
    }


def _finalize_staged_sentence(state: LifecycleState, language: str, reason: str, chunk_index: int) -> list[str]:
    if not state.staged_sentence:
        return []
    state.count("finalize_attempt")
    state.count(f"finalize_reason_{reason}")
    staged_before = state.staged_sentence
    output_sentence = _sentence_output_delta(state.committed_text, staged_before)
    assert state.final_sentences is not None
    output_sentence, recent_source = _recent_final_output_delta(output_sentence, tuple(state.final_sentences), language)
    state.staged_sentence = ""
    state.staged_confirmations = 0
    state.staged_age = 0
    state.staged_forced = False
    state.staged_deferred_age_chunk = -1
    if recent_source is not None and output_sentence:
        state.count("finalize_recent_delta_trimmed")
    if not output_sentence:
        state.count("finalize_duplicate_suppressed")
        state.count("segment_state_suppressed")
        _promote_next_staged_sentence(state, chunk_index)
        return []
    if _should_suppress_delta_final(staged_before, output_sentence, language, reason):
        state.count("finalize_delta_suppressed")
        state.count("segment_state_suppressed")
        _promote_next_staged_sentence(state, chunk_index)
        return []
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
    if state.staged_sentence and prior_pending_text and candidate:
        stripped_candidate = _strip_prior_pending_prefix_revision(
            state.staged_sentence,
            candidate,
            prior_pending_text,
        )
        if stripped_candidate != candidate:
            candidate = stripped_candidate
            state.count("candidate_prior_pending_prefix_trimmed")
    if candidate and candidate != normalized_sentence:
        assert state.final_sentences is not None
        recent_candidate, recent_source = _recent_final_output_delta(
            normalized_sentence,
            tuple(state.final_sentences),
            language,
        )
        if recent_source is not None and recent_candidate != candidate:
            candidate = recent_candidate
            state.count("candidate_recent_final_delta_trimmed")
    elif candidate:
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
        for flag in _final_sentence_diagnostic_flags(candidate, language):
            state.count(f"stage_candidate_quality_{flag}")
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
        return []
    if _should_split_terminal_tail_revision(state.staged_sentence, candidate):
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
        return finalized

    if _sentences_are_revisions(state.staged_sentence, candidate):
        state.count("stage_revision")
        state.count("segment_state_revised")
        previous = state.staged_sentence
        preferred = _prefer_sentence_revision(previous, candidate)
        if preferred != previous:
            state.count("stage_revision_changed")
        state.staged_sentence = preferred
        state.staged_confirmations = _next_revision_confirmation_count(previous, preferred, state.staged_confirmations)
        if _should_reset_revision_age(previous, preferred):
            state.staged_age = 0
            state.count("stage_revision_age_reset")
        else:
            state.staged_age += 1
        state.staged_deferred_age_chunk = chunk_index
        state.count("stage_age_tick")
        state.staged_forced = state.staged_forced or forced
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
        ):
            max_age = _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age)
            if state.staged_age >= max_age:
                state.count("stage_age_finalize")
                reason = "aged_forced" if state.staged_forced else "aged"
            else:
                state.count("stage_finalize_before_replace")
                reason = "next_completed"
            return _finalize_staged_sentence(state, language, reason, chunk_index)
        if not defer_for_later_extension and state.staged_age >= _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age):
            state.count("stage_age_quality_blocked")
            state.count("segment_state_suppressed")
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
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
        if state.staged_age >= _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age):
            state.count("stage_age_quality_blocked")
            state.count("segment_state_suppressed")
            state.staged_sentence = ""
            state.staged_confirmations = 0
            state.staged_age = 0
            state.staged_forced = False
            state.staged_deferred_age_chunk = -1
            _promote_next_staged_sentence(state, chunk_index)
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
    return finalized


def _age_staged_sentence(state: LifecycleState, language: str, sentence_finalize_age: int, chunk_index: int) -> list[str]:
    if not state.staged_sentence:
        return []
    if state.staged_deferred_age_chunk == chunk_index:
        state.count("stage_age_same_chunk_skipped")
        return []
    if not _should_age_staged_sentence(state.staged_sentence, state.pending_text):
        state.count("stage_age_hold")
        return []
    state.staged_age += 1
    state.staged_deferred_age_chunk = chunk_index
    state.count("stage_age_tick")
    if state.staged_age < _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age):
        return []
    if not _should_finalize_before_replacement(
        state.staged_sentence,
        language,
        state.staged_confirmations,
        state.staged_age,
        sentence_finalize_age,
        state.staged_forced,
    ):
        state.count("stage_age_quality_blocked")
        state.count("segment_state_suppressed")
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        _promote_next_staged_sentence(state, chunk_index)
        return []
    state.count("stage_age_finalize")
    return _finalize_staged_sentence(state, language, "aged_forced" if state.staged_forced else "aged", chunk_index)


def _suppress_stale_no_text_stage(state: LifecycleState, chunk_index: int) -> None:
    if not state.staged_sentence:
        state.no_text_stage_skip_chunks = 0
        return
    required_confirmations = _sentence_required_confirmations(state.staged_forced)
    if state.staged_confirmations >= required_confirmations:
        return
    if state.no_text_stage_skip_chunks < NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS:
        return
    state.count("stage_no_text_stale_suppressed")
    state.count("segment_state_suppressed")
    state.staged_sentence = ""
    state.staged_confirmations = 0
    state.staged_age = 0
    state.staged_forced = False
    state.staged_deferred_age_chunk = -1
    state.no_text_stage_skip_chunks = 0
    _promote_next_staged_sentence(state, chunk_index)


def _run_lifecycle_case(case: SbdCase, detector: Any) -> dict[str, Any]:
    state = LifecycleState()
    chunks: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(case.chunks, start=1):
        prior_pending_text = state.pending_text
        if normalized_text(chunk):
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
            produced.extend(_age_staged_sentence(state, case.language, case.sentence_finalize_age, chunk_index))
        if state.pending_text and completed:
            state.count("segment_state_pending")
        if not completed and (state.pending_text or normalized_text(chunk)):
            produced.extend(_age_staged_sentence(state, case.language, case.sentence_finalize_age, chunk_index))
        if not completed and not state.pending_text and not normalized_text(chunk):
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
        "actual_final": state.final_sentences,
        "actual_staged": state.staged_sentence,
        "actual_staged_queue": [str(entry["sentence"]) for entry in state.staged_queue],
        "committed_text": state.committed_text,
        "metrics": state.metrics,
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_real_ai_cuda_args(args: argparse.Namespace) -> None:
    device = str(args.device or "").strip().lower()
    compute_type = str(args.compute_type or "").strip().lower()
    if device != "cuda":
        raise ValueError(
            "Dictation AI SBD benchmark must run on CUDA: "
            f"--device=cuda required, got {args.device!r}. CPU benchmarks are not valid performance data."
        )
    if compute_type != "float16":
        raise ValueError(
            "Dictation AI SBD benchmark must use the production CUDA precision: "
            f"--compute-type=float16 required, got {args.compute_type!r}."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run text-only Dictation AI SBD lifecycle benchmark cases.")
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "tests/eval/dictation_ai/sbd_text_cases.sample.jsonl")
    parser.add_argument("--model", default=SBD_BENCHMARK_MODEL)
    parser.add_argument("--device", default=SBD_BENCHMARK_DEVICE)
    parser.add_argument("--compute-type", default=SBD_BENCHMARK_COMPUTE_TYPE)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".tmp/eval/dictation-ai-sbd/latest.json")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when final F1 average is below --min-final-f1.",
    )
    parser.add_argument("--min-final-f1", type=float, default=0.0)
    parser.add_argument("--min-pass-rate", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    _validate_real_ai_cuda_args(args)

    cases = _load_cases(args.cases)
    detector = create_sentence_boundary_detector(
        SBD_BENCHMARK_BACKEND,
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
    )

    results: list[dict[str, Any]] = []
    metric_totals: dict[str, int] = {}
    started = time.perf_counter()
    for case in cases:
        case_started = time.perf_counter()
        lifecycle = _run_lifecycle_case(case, detector)
        elapsed_ms = (time.perf_counter() - case_started) * 1000.0
        final_score = _score_sequence(case.expected_final, lifecycle["actual_final"])
        final_boundary_score = _score_boundary_offsets(case.expected_final, lifecycle["actual_final"])
        completed_score = _score_sequence(case.expected_completed, lifecycle["actual_completed_last"])
        pending_exact = lifecycle["actual_pending"] == case.expected_pending
        staged_exact = lifecycle["actual_staged"] == case.expected_staged
        case_exact_match = final_score["exact"] and pending_exact and staged_exact
        for key, value in lifecycle["metrics"].items():
            metric_totals[key] = metric_totals.get(key, 0) + int(value)
        results.append(
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "elapsed_ms": round(elapsed_ms, 3),
                "expected_final": case.expected_final,
                "actual_final": lifecycle["actual_final"],
                "expected_pending": case.expected_pending,
                "actual_pending": lifecycle["actual_pending"],
                "expected_staged": case.expected_staged,
                "actual_staged": lifecycle["actual_staged"],
                "actual_staged_queue": lifecycle["actual_staged_queue"],
                "final_score": final_score,
                "final_boundary_score": final_boundary_score,
                "completed_last_score": completed_score,
                "pending_exact": pending_exact,
                "staged_exact": staged_exact,
                "case_exact_match": case_exact_match,
                "metrics": lifecycle["metrics"],
                "chunks": lifecycle["chunks"],
            }
        )

    exact_match_count = sum(1 for result in results if result["case_exact_match"])
    pending_exact_count = sum(1 for result in results if result["pending_exact"])
    staged_exact_count = sum(1 for result in results if result["staged_exact"])
    finalized = metric_totals.get("finalized", 0)
    stage_start = metric_totals.get("stage_start", 0)
    final_score_avg = _average_scores(results, "final_score")
    final_boundary_score_avg = _average_scores(results, "final_boundary_score")
    completed_last_score_avg = _average_scores(results, "completed_last_score")
    report = {
        "backend": SBD_BENCHMARK_BACKEND,
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "dictation_pipeline_policy": dictation_pipeline_policy(),
        "revision_similarity_policy": _revision_similarity_policy(),
        "case_count": len(results),
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "summary": {
            "case_exact_match": exact_match_count,
            "pending_exact_match": pending_exact_count,
            "staged_exact_match": staged_exact_count,
            "min_final_f1": args.min_final_f1,
            "finalized": finalized,
            "stage_start": stage_start,
            "finalized_per_stage_start": finalized / max(stage_start, 1),
            "final_precision_avg": final_score_avg["precision"],
            "final_recall_avg": final_score_avg["recall"],
            "final_f1_avg": final_score_avg["f1"],
            "final_similarity_coverage_avg": final_score_avg["similarity_coverage"],
            "final_boundary_precision_avg": final_boundary_score_avg["precision"],
            "final_boundary_recall_avg": final_boundary_score_avg["recall"],
            "final_boundary_f1_avg": final_boundary_score_avg["f1"],
            "completed_last_precision_avg": completed_last_score_avg["precision"],
            "completed_last_recall_avg": completed_last_score_avg["recall"],
            "completed_last_f1_avg": completed_last_score_avg["f1"],
            "stage_revision": metric_totals.get("stage_revision", 0),
            "stage_replace": metric_totals.get("stage_replace", 0),
            "stage_replaced_unconfirmed": metric_totals.get("stage_replaced_unconfirmed", 0),
            "pending_overrun": metric_totals.get("pending_overrun", 0),
        },
        "metrics": metric_totals,
        "cases": results,
    }
    _write_report(args.output, report)
    print(
        "[dictation-ai-sbd-benchmark] "
        f"cases={len(results)} finalized={finalized} "
        f"stage_start={stage_start} finalized_per_stage_start={finalized / max(stage_start, 1):.3f} "
        f"final_precision_avg={final_score_avg['precision']:.3f} final_recall_avg={final_score_avg['recall']:.3f} "
        f"final_f1_avg={final_score_avg['f1']:.3f} "
        f"final_similarity_coverage_avg={final_score_avg['similarity_coverage']:.3f} "
        f"final_boundary_f1_avg={final_boundary_score_avg['f1']:.3f} "
        f"case_exact_match={exact_match_count} "
        f"pending_exact_match={pending_exact_count} "
        f"staged_exact_match={staged_exact_count} "
        f"output={args.output}"
    )
    if args.fail_on_regression and final_score_avg["f1"] < args.min_final_f1:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any

from src.app.dictation_pipeline_settings import (
    FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
    SBD_BENCHMARK_BACKEND,
    dictation_pipeline_policy,
    dictation_tuning_manifest,
    dictation_tuning_protocol,
    lifecycle_tuning_policy,
)
from src.app.dictation_transcript_logic import _final_sentence_diagnostic_flags, _revision_similarity_policy, _word_units
from src.app.sentence_boundary import normalized_text
from tests.eval.dictation_ai.cases.sbd_case_loader import SbdCase
from tests.eval.dictation_ai.cases.sbd_case_paths import (
    build_evidence_protocol,
    corpus_interpretation,
    missing_required_evidence_fields,
    summarize_representative_metadata,
)
from tests.eval.dictation_ai.cases.sbd_diagnostic_tags import is_diagnostic_tag
from tests.eval.dictation_ai.cases.sbd_expected_quality import expected_quality_flags
from tests.eval.dictation_ai.cases.sbd_input_evidence import case_input_evidence, case_stable_sentence_candidates
from tests.eval.dictation_ai.benchmark.sbd_runtime_contract import lifecycle_replay_contract, runtime_contract

LIFECYCLE_BOTTLENECK_METRICS = (
    "stage_start",
    "finalized",
    "stage_replace",
    "stage_replace_deferred",
    "stage_queue_enqueue",
    "stage_queue_revision",
    "stage_queue_revision_token_sentence_deferred",
    "stage_queue_revision_preempt_deferred",
    "stage_queue_revision_preempt_deferred_aged",
    "stage_queue_revision_preempt_deferred_confirmed",
    "stage_queue_revision_preempt_deferred_confirmed_forced",
    "stage_queue_revision_preempt_deferred_next_completed",
    "stage_queue_revision_preempt_deferred_replaced_confirmed",
    "stage_queue_revision_preempt_deferred_terminal_tail_revision_split",
    "stage_queue_promote",
    "stage_queue_drop_oldest",
    "stage_queue_stale_promote_suppressed",
    "stage_queue_recent_final_suppressed",
    "stage_queue_recent_final_delta_trimmed",
    "stage_finalize_deferred_for_queue_revision",
    "stage_finalize_right_context",
    "stage_finalize_before_replace",
    "stage_age_hold",
    "stage_age_tick",
    "stage_age_finalize",
    "stage_age_quality_blocked",
    "stage_age_no_text_skipped",
    "stage_confirmed_before_age_queue",
    "stage_confirmed_before_deferred_revision",
    "stage_confirm_deferred_later_extension",
    "stage_confirmed_before_prefix_drop_revision",
    "stage_revision",
    "stage_revision_changed",
    "stage_revision_age_reset",
    "stage_revision_token_sentence_deferred",
    "stage_revision_terminal_tail_split",
    "stage_revision_internal_stability_high",
    "stage_revision_internal_stability_mid",
    "stage_revision_internal_stability_low",
    "stage_revision_confirmation_preserved_internal",
    "stage_revision_confirmation_reset",
    "stage_revision_candidate_quality_blocked",
    "stage_queue_quality_suppressed",
    "stage_candidate_quality_blocked",
    "stage_candidate_quality_no_end_marker",
    "stage_candidate_quality_no_end_marker_with_active_stage",
    "stage_candidate_quality_no_end_marker_with_queue",
    "stage_candidate_quality_no_end_marker_without_blocker",
    "stage_candidate_quality_short_no_end_fragment",
    "stage_candidate_quality_short_no_end_fragment_with_active_stage",
    "stage_candidate_quality_short_no_end_fragment_with_later_completed",
    "stage_candidate_quality_short_no_end_fragment_with_queue",
    "stage_candidate_quality_short_no_end_fragment_without_blocker",
    "stage_candidate_quality_trailing_ellipsis",
    "stage_candidate_quality_trailing_ellipsis_with_active_stage",
    "stage_candidate_quality_trailing_ellipsis_with_queue",
    "stage_candidate_quality_trailing_ellipsis_without_blocker",
    "stage_blocked_short_no_end_aged_active_stage",
    "stage_blocked_short_no_end_active_stage_quality_suppressed",
    "stage_no_text_stale_suppressed",
    "stage_replace_deferred_same_chunk",
    "stage_replaced_unconfirmed",
    "final_quality_no_end_marker",
    "pending_overrun",
    "pending_overrun_reason_long_no_boundary",
    "pending_quality_repeated_word_ngram",
    "pending_quality_cjk_repeated_ngram",
    "pending_quality_overrun_long_no_boundary",
    "candidate_delta_trimmed",
    "candidate_delta_trimmed_cjk",
    "candidate_recent_final_delta_trimmed",
    "candidate_duplicate_suppressed",
    "candidate_pending_prefix_mixed_suppressed",
    "candidate_prior_pending_prefix_trimmed",
    "candidate_prior_pending_recent_final_mixed_suppressed",
    "finalize_attempt",
    "finalize_delta_fragment_preserved",
    "finalize_delta_suppressed",
    "finalize_delta_suppressed_stage_dropped",
    "finalize_delta_suppressed_stage_retained",
    "finalize_duplicate_suppressed",
    "finalize_recent_delta_trimmed",
    "finalize_recent_echo_suppressed",
)
DEFERRED_REPLACEMENT_REASONS = frozenset(
    {
        "open_latin_clause",
        "unconfirmed",
        "unconfirmed_cjk",
    }
)
INPUT_CONTAMINATION_REVIEW_TAG_MARKERS = (
    "audio-residual",
    "no-speech",
    "no-text",
    "speaker-transition",
)
LIFECYCLE_FOCUS_TAG_MARKERS = (
    "boundary",
    "duplicate",
    "final",
    "fragment",
    "missing",
    "no-end",
    "pending",
    "queue",
    "recent-final",
    "revision",
    "stage",
    "staged",
    "tail-echo",
    "terminal-tail",
)
CASE_EXEMPLAR_METRICS = (
    "stage_queue_revision",
    "stage_queue_revision_token_sentence_deferred",
    "stage_queue_promote",
    "stage_queue_recent_final_suppressed",
    "stage_finalize_deferred_for_queue_revision",
    "stage_revision_internal_stability_high",
    "stage_revision_internal_stability_mid",
    "stage_revision_internal_stability_low",
    "stage_revision_confirmation_preserved_internal",
    "stage_revision_confirmation_reset",
    "stage_revision_age_reset",
    "stage_revision_token_sentence_deferred",
    "stage_queue_quality_suppressed",
    "stage_replace_deferred",
    "stage_replace_deferred_same_chunk",
    "stage_age_hold",
    "stage_age_quality_blocked",
    "stage_confirmed_before_age_queue",
    "stage_confirmed_before_deferred_revision",
    "stage_confirm_deferred_later_extension",
    "stage_confirmed_before_prefix_drop_revision",
    "stage_candidate_quality_blocked",
    "stage_candidate_quality_no_end_marker",
    "stage_candidate_quality_no_end_marker_with_active_stage",
    "stage_candidate_quality_no_end_marker_with_queue",
    "stage_candidate_quality_no_end_marker_without_blocker",
    "stage_candidate_quality_short_no_end_fragment",
    "stage_candidate_quality_short_no_end_fragment_with_active_stage",
    "stage_candidate_quality_short_no_end_fragment_with_later_completed",
    "stage_candidate_quality_short_no_end_fragment_with_queue",
    "stage_candidate_quality_short_no_end_fragment_without_blocker",
    "stage_candidate_quality_trailing_ellipsis",
    "stage_candidate_quality_trailing_ellipsis_with_active_stage",
    "stage_candidate_quality_trailing_ellipsis_with_queue",
    "stage_candidate_quality_trailing_ellipsis_without_blocker",
    "stage_blocked_short_no_end_aged_active_stage",
    "stage_blocked_short_no_end_active_stage_quality_suppressed",
    "pending_overrun",
    "pending_quality_repeated_word_ngram",
    "pending_quality_overrun_long_no_boundary",
    "candidate_delta_trimmed",
    "candidate_delta_trimmed_cjk",
    "candidate_recent_final_delta_trimmed",
    "candidate_duplicate_suppressed",
    "candidate_pending_prefix_mixed_suppressed",
    "candidate_prior_pending_prefix_trimmed",
    "candidate_prior_pending_recent_final_mixed_suppressed",
    "finalize_delta_fragment_preserved",
    "finalize_recent_echo_suppressed",
)
CASE_EXEMPLAR_LIMIT = 8
CASE_EXEMPLAR_PREVIEW_CHARS = 160
BOUNDARY_ZERO_HIGH_FINAL_F1 = 0.95
BOUNDARY_GRANULARITY_FINAL_RECALL = 0.95
BOUNDARY_GRANULARITY_FINAL_F1 = 0.85
BOUNDARY_GRANULARITY_MAX_BOUNDARY_F1 = 0.50
LOW_SCORE_THRESHOLDS = (0.35, 0.50, 0.65)
LOW_SCORE_METRIC_PREFIXES = (
    "candidate_",
    "finalize_",
    "final_quality_",
    "pending_",
    "stage_",
)
SUPPORTED_LOW_BOTTLENECK_METRICS = (
    "pending_overrun",
    "pending_quality_overrun_long_no_boundary",
    "pending_quality_repeated_word_ngram",
    "stage_candidate_quality_blocked",
    "stage_revision_token_sentence_deferred",
    "stage_revision_age_reset",
    "stage_age_quality_blocked",
    "stage_confirmed_before_age_queue",
    "stage_confirmed_before_deferred_revision",
    "stage_confirm_deferred_later_extension",
    "stage_confirmed_before_prefix_drop_revision",
    "stage_replace_deferred",
    "stage_replace_deferred_same_chunk",
    "stage_finalize_deferred_for_queue_revision",
    "stage_finalize_right_context",
    "stage_queue_revision",
    "stage_queue_promote",
    "candidate_recent_final_delta_trimmed",
    "candidate_delta_trimmed",
    "candidate_duplicate_suppressed",
)
CASE_REVIEW_ACTION_FLAGS = (
    "recut_or_relabel_stable_candidate_mismatch",
    "rewrite_expected_final_to_stable_repeated_candidate",
    "remove_or_recut_expected_outside_replay_input",
    "rewrite_expected_final_to_observed_stt_text",
    "add_initial_final_or_recut_mid_stream_case",
    "restore_source_log_or_recut_from_observed_log",
    "rewrite_expected_final_to_final_sentence_boundary",
    "extend_replay_tail_or_reclassify_staged_expectation",
    "deduplicate_or_justify_shifted_window_repeat",
    "manual_boundary_review",
)
PREFIX_CONTEXT_MIN_SUPPORT = max(0.30, FINAL_SENTENCE_MATCH_MIN_SIMILARITY - 0.40)
TERMINAL_RESIDUE_MIN_UNITS = 6
TERMINAL_RESIDUE_SUFFIX_COVERAGE_MIN = 0.85
TERMINAL_RESIDUE_ACTUAL_COMPLETE_MIN = 0.95
STABLE_CANDIDATE_ORDERED_REWRITE_MIN_SIMILARITY = 0.80
STABLE_CANDIDATE_ORDERED_REVIEW_MIN_SIMILARITY = 0.60
EXPECTED_REVISION_VARIANT_MIN_SIMILARITY = 0.55
EXPECTED_REVISION_VARIANT_MIN_COVERAGE = 0.55
EXPECTED_REVISION_VARIANT_MIN_COMMON_RUN = 8
EXPECTED_CONTAINED_TOKEN_MIN_UNITS = 8
EXPECTED_CONTAINED_TOKEN_MIN_COVERAGE = 0.80
EXPECTED_SHORT_CONTAINED_TOKEN_MIN_UNITS = 5
EXPECTED_SHORT_SUPPORTED_BY_LONGER_MIN_UNITS = 5
EXPECTED_SHORT_SUPPORTED_BY_LONGER_MAX_UNITS = 8
EXPECTED_SHORT_SUPPORTED_BY_LONGER_MIN_SIMILARITY = 0.80
OMITTED_STABLE_ACTUAL_MIN_SIMILARITY = 0.70
OMITTED_STABLE_ACTUAL_MIN_RATIO = 0.70
COMBINED_RESIDUE_MATCH_MIN_SIMILARITY = 0.70


def _sentence_support_score(sentence: str, chunk: str) -> float:
    sentence_words = _word_units(sentence)
    chunk_words = _word_units(chunk)
    if sentence_words and chunk_words:
        matcher = SequenceMatcher(None, sentence_words, chunk_words, autojunk=False)
        ratio = matcher.ratio()
        common_run = max((block.size for block in matcher.get_matching_blocks()), default=0)
        coverage = common_run / max(len(sentence_words), 1)
        return max(ratio, coverage)
    return SequenceMatcher(None, normalized_text(sentence), normalized_text(chunk), autojunk=False).ratio()


def _sentence_token_ratio(left: str, right: str) -> float:
    left_words = _word_units(left)
    right_words = _word_units(right)
    if left_words and right_words:
        return SequenceMatcher(None, left_words, right_words, autojunk=False).ratio()
    return SequenceMatcher(None, normalized_text(left), normalized_text(right), autojunk=False).ratio()


def _expected_sentences_are_revision_variants(left: str, right: str) -> bool:
    left_words = _word_units(normalized_text(left))
    right_words = _word_units(normalized_text(right))
    if not left_words or not right_words:
        return False
    matcher = SequenceMatcher(None, left_words, right_words, autojunk=False)
    common_run = max((block.size for block in matcher.get_matching_blocks()), default=0)
    coverage = common_run / max(min(len(left_words), len(right_words)), 1)
    return (
        common_run >= EXPECTED_REVISION_VARIANT_MIN_COMMON_RUN
        and coverage >= EXPECTED_REVISION_VARIANT_MIN_COVERAGE
        and matcher.ratio() >= EXPECTED_REVISION_VARIANT_MIN_SIMILARITY
    )


def _expected_sentences_have_contained_token_units(left: str, right: str) -> bool:
    left_words = _word_units(normalized_text(left))
    right_words = _word_units(normalized_text(right))
    if not left_words or not right_words:
        return False
    shorter_len = min(len(left_words), len(right_words))
    if shorter_len < EXPECTED_CONTAINED_TOKEN_MIN_UNITS:
        return False
    matcher = SequenceMatcher(None, left_words, right_words, autojunk=False)
    matched_units = sum(block.size for block in matcher.get_matching_blocks())
    return matched_units / max(shorter_len, 1) >= EXPECTED_CONTAINED_TOKEN_MIN_COVERAGE


def _expected_sentences_have_short_contained_token_units(left: str, right: str) -> bool:
    left_words = _word_units(normalized_text(left))
    right_words = _word_units(normalized_text(right))
    if not left_words or not right_words:
        return False
    shorter, longer = (left_words, right_words) if len(left_words) <= len(right_words) else (right_words, left_words)
    if len(shorter) < EXPECTED_SHORT_CONTAINED_TOKEN_MIN_UNITS or len(shorter) >= EXPECTED_CONTAINED_TOKEN_MIN_UNITS:
        return False
    for index in range(0, len(longer) - len(shorter) + 1):
        if longer[index : index + len(shorter)] == shorter:
            return True
    return False


def _expected_short_sentence_supported_by_longer_sentence(left: str, right: str) -> bool:
    left_words = _word_units(normalized_text(left))
    right_words = _word_units(normalized_text(right))
    if not left_words or not right_words:
        return False
    if len(left_words) == len(right_words):
        return False
    shorter, longer = (left, right) if len(left_words) < len(right_words) else (right, left)
    shorter_len = min(len(left_words), len(right_words))
    if (
        shorter_len < EXPECTED_SHORT_SUPPORTED_BY_LONGER_MIN_UNITS
        or shorter_len > EXPECTED_SHORT_SUPPORTED_BY_LONGER_MAX_UNITS
    ):
        return False
    return _sentence_support_score(shorter, longer) >= EXPECTED_SHORT_SUPPORTED_BY_LONGER_MIN_SIMILARITY


def _has_expected_app_quality_blocked_sentence(expected_final: list[str], language: str) -> bool:
    app_quality_flags = {"empty", "spaced_cjk", "cjk_repeated_ngram", "repeated_word_ngram"}
    for sentence in expected_final:
        if app_quality_flags.intersection(_final_sentence_diagnostic_flags(sentence, language)):
            return True
    return False


def _punctuation_only_final_mismatch(result: dict[str, Any]) -> bool:
    expected_final = [
        str(sentence).strip()
        for sentence in result.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    actual_final = [
        str(sentence).strip()
        for sentence in result.get("actual_final", []) or []
        if str(sentence).strip()
    ]
    if not expected_final or len(expected_final) != len(actual_final):
        return False
    if expected_final == actual_final:
        return False
    return all(
        _word_units(normalized_text(expected)) == _word_units(normalized_text(actual))
        for expected, actual in zip(expected_final, actual_final, strict=True)
    )


def _expected_sentence_support(sentence: str, chunks: list[str]) -> dict[str, Any]:
    best_index = -1
    best_similarity = 0.0
    for index, chunk in enumerate(chunks):
        similarity = _sentence_support_score(sentence, chunk)
        if similarity > best_similarity:
            best_index = index
            best_similarity = similarity
        if similarity >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            return {
                "chunk_index": index,
                "similarity": similarity,
                "supported": True,
            }
    return {
        "chunk_index": best_index,
        "similarity": best_similarity,
        "supported": False,
    }


def _find_word_subsequence(words: list[str], needle: list[str]) -> int:
    if not words or not needle or len(needle) > len(words):
        return -1
    for index in range(0, len(words) - len(needle) + 1):
        if words[index : index + len(needle)] == needle:
            return index
    return -1


def _prefix_before_expected_sentence(chunk: str, sentence: str) -> str:
    normalized_chunk = normalized_text(chunk)
    normalized_sentence = normalized_text(sentence)
    if not normalized_chunk or not normalized_sentence:
        return ""
    index = normalized_chunk.find(normalized_sentence)
    if index >= 0:
        return normalized_chunk[:index].strip()
    chunk_words = _word_units(normalized_chunk)
    sentence_words = _word_units(normalized_sentence)
    start = _find_word_subsequence(chunk_words, sentence_words)
    if start <= 0:
        return _fuzzy_prefix_before_expected_sentence(normalized_chunk, chunk_words, sentence_words)
    return "".join(chunk_words[:start]) if any(_is_cjk_word(word) for word in chunk_words) else " ".join(chunk_words[:start])


def _fuzzy_prefix_before_expected_sentence(
    normalized_chunk: str,
    chunk_words: list[str],
    sentence_words: list[str],
) -> str:
    if not chunk_words or not sentence_words:
        return ""
    matcher = SequenceMatcher(None, sentence_words, chunk_words, autojunk=False)
    min_run = min(len(sentence_words), max(3, len(sentence_words) // 3))
    for block in matcher.get_matching_blocks():
        if not block.size:
            continue
        if block.a > 1 or block.b <= 0 or block.size < min_run:
            continue
        first_matched_word = chunk_words[block.b]
        index = normalized_chunk.find(first_matched_word)
        if index > 0:
            return normalized_chunk[:index].strip()
        prefix_words = chunk_words[: block.b]
        return "".join(prefix_words) if any(_is_cjk_word(word) for word in chunk_words) else " ".join(prefix_words)
    return ""


def _is_cjk_word(word: str) -> bool:
    return any("\u3400" <= ch <= "\u9fff" for ch in word)


def _has_completed_prefix_context(prefix: str) -> bool:
    normalized = normalized_text(prefix)
    if not normalized:
        return False
    if not any(marker in normalized for marker in ".!?。？！"):
        return False
    return len(_word_units(normalized)) >= 3


def case_context_flags(result: dict[str, Any]) -> list[str]:
    expected_final = [str(sentence).strip() for sentence in result.get("expected_final", []) if str(sentence).strip()]
    if not expected_final or result.get("initial_final"):
        return []
    flags: list[str] = []
    chunks = [
        str(chunk.get("input", "") if isinstance(chunk, dict) else chunk).strip()
        for chunk in result.get("chunks", [])
        if str(chunk.get("input", "") if isinstance(chunk, dict) else chunk).strip()
    ]
    if chunks:
        for chunk in chunks:
            if _sentence_support_score(expected_final[0], chunk) < PREFIX_CONTEXT_MIN_SUPPORT:
                continue
            prefix = _prefix_before_expected_sentence(chunk, expected_final[0])
            if _has_completed_prefix_context(prefix):
                flags.append("unmodeled_prefix_context")
                break
    if not flags and _has_actual_prefix_before_expected_final(result):
        flags.append("actual_prefix_before_expected_final")
    return flags


def _has_actual_prefix_before_expected_final(result: dict[str, Any]) -> bool:
    expected_final = [
        str(sentence).strip()
        for sentence in result.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    actual_final = [
        str(sentence).strip()
        for sentence in result.get("actual_final", []) or []
        if str(sentence).strip()
    ]
    if not expected_final or len(actual_final) < 2 or result.get("initial_final"):
        return False
    first_expected = expected_final[0]
    for index, actual in enumerate(actual_final):
        if _sentence_support_score(first_expected, actual) >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            return index > 0 and any(_has_completed_prefix_context(prefix) for prefix in actual_final[:index])
    return False


def _has_end_marker(sentence: str) -> bool:
    return any(marker in normalized_text(sentence) for marker in ".!?。？！")


def _has_actual_final_supported_by_omitted_stable_candidate(result: dict[str, Any]) -> bool:
    expected_final = [
        str(sentence).strip()
        for sentence in result.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    actual_final = [
        str(sentence).strip()
        for sentence in result.get("actual_final", []) or []
        if str(sentence).strip()
    ]
    stable_examples = [
        str(candidate.get("text", "")).strip()
        for candidate in dict(result.get("input_evidence", {}) or {}).get("stable_candidate_examples", []) or []
        if str(candidate.get("text", "")).strip()
    ]
    if not expected_final or not actual_final or not stable_examples:
        return False
    for stable in stable_examples:
        if max((_sentence_support_score(stable, expected) for expected in expected_final), default=0.0) >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            continue
        stable_flags = set(_final_sentence_diagnostic_flags(stable, str(result.get("language") or "")))
        if stable_flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "repeated_word_ngram"}):
            continue
        for actual in actual_final:
            if max((_sentence_support_score(actual, expected) for expected in expected_final), default=0.0) >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
                continue
            if (
                _sentence_support_score(stable, actual) >= OMITTED_STABLE_ACTUAL_MIN_SIMILARITY
                and _sentence_token_ratio(stable, actual) >= OMITTED_STABLE_ACTUAL_MIN_RATIO
            ):
                return True
    return False


def _expected_final_order_support_kind(case: SbdCase) -> str:
    if len(case.expected_final) < 2:
        return "single"
    supports = [_expected_sentence_support(sentence, case.chunks) for sentence in case.expected_final]
    if any(not support["supported"] for support in supports):
        return "review_needed"
    supported_indices = [int(support["chunk_index"]) for support in supports]
    if any(right < left for left, right in zip(supported_indices, supported_indices[1:])):
        return "review_needed"
    return "supported_monotonic"


def _expected_order_supports_logic_tuning(kind: str) -> bool:
    return kind in {"single", "supported_monotonic"}


def summarize_expected_final_order_support(cases: list[SbdCase]) -> dict[str, Any]:
    review_cases: list[dict[str, Any]] = []
    multi_expected_cases = [case for case in cases if len(case.expected_final) >= 2]
    unsupported_case_count = 0
    inversion_case_count = 0
    all_supported_monotonic_count = 0
    for case in multi_expected_cases:
        supports = [_expected_sentence_support(sentence, case.chunks) for sentence in case.expected_final]
        unsupported = [support for support in supports if not support["supported"]]
        if unsupported:
            unsupported_case_count += 1
        supported_indices = [int(support["chunk_index"]) for support in supports if support["supported"]]
        inversion_count = sum(
            1
            for left, right in zip(supported_indices, supported_indices[1:])
            if right < left
        )
        if inversion_count:
            inversion_case_count += 1
        if not unsupported and not inversion_count:
            all_supported_monotonic_count += 1
        if unsupported or inversion_count:
            review_cases.append(
                {
                    "id": case.id,
                    "language": case.language,
                    "tags": list(case.tags),
                    "unsupported_expected_count": len(unsupported),
                    "supported_order_inversion_count": inversion_count,
                    "support_chunk_indices": [int(support["chunk_index"]) for support in supports],
                    "support_similarities": [round(float(support["similarity"]), 4) for support in supports],
                    "expected_final_preview": _first_text_preview(case.expected_final),
                    "chunk_preview": _first_text_preview(case.chunks),
                }
            )
    review_cases.sort(
        key=lambda item: (
            -int(item["supported_order_inversion_count"]),
            -int(item["unsupported_expected_count"]),
            str(item["id"]),
        )
    )
    total = len(multi_expected_cases)
    return {
        "multi_expected_case_count": total,
        "all_supported_monotonic_case_count": all_supported_monotonic_count,
        "all_supported_monotonic_case_ratio": all_supported_monotonic_count / max(total, 1),
        "unsupported_expected_case_count": unsupported_case_count,
        "supported_order_inversion_case_count": inversion_case_count,
        "review_needed_case_count": len(review_cases),
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "top_review_needed_cases": review_cases[:CASE_EXEMPLAR_LIMIT],
    }


def summarize_results_by_expected_order_support(cases: list[SbdCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    support_by_id = {case.id: _expected_final_order_support_kind(case) for case in cases}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(support_by_id.get(str(result.get("id")), "unknown"), []).append(result)
    return {
        group: _summarize_result_group(group_results)
        for group, group_results in sorted(grouped.items())
    }


def summarize_low_score_characteristics(cases: list[SbdCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    support_by_id = {case.id: _expected_final_order_support_kind(case) for case in cases}
    expected_results = [
        result
        for result in results
        if result.get("expected_final") and isinstance(result.get("final_score"), dict)
    ]
    thresholds: dict[str, dict[str, Any]] = {}
    for threshold in LOW_SCORE_THRESHOLDS:
        low_results = [
            result
            for result in expected_results
            if float(dict(result.get("final_score", {})).get("f1", 0.0)) < threshold
        ]
        support_counts = Counter(support_by_id.get(str(result.get("id")), "unknown") for result in low_results)
        language_counts = Counter(str(result.get("language") or "unknown") for result in low_results)
        tag_counts = Counter(str(tag) for result in low_results for tag in result.get("tags", []))
        metric_case_counts: Counter[str] = Counter()
        metric_total_counts: Counter[str] = Counter()
        by_support_kind: dict[str, dict[str, Any]] = {}
        for support_kind in sorted(support_counts):
            support_results = [
                result
                for result in low_results
                if support_by_id.get(str(result.get("id")), "unknown") == support_kind
            ]
            by_support_kind[support_kind] = _summarize_low_score_support_group(support_results)
        for result in low_results:
            for key, value in dict(result.get("metrics", {})).items():
                value_int = int(value)
                if not value_int or not key.startswith(LOW_SCORE_METRIC_PREFIXES):
                    continue
                metric_case_counts[key] += 1
                metric_total_counts[key] += value_int
        thresholds[f"{threshold:.2f}"] = {
            "threshold": threshold,
            "case_count": len(low_results),
            "case_ratio": len(low_results) / max(len(expected_results), 1),
            "avg_final_f1": _avg_final_f1(low_results),
            "avg_ordered_f1": _avg_score_f1(low_results, "final_ordered_score"),
            "avg_boundary_f1": _avg_score_f1(low_results, "final_boundary_score"),
            "empty_actual_count": sum(1 for result in low_results if not result.get("actual_final")),
            "staged_residue_count": sum(
                1
                for result in low_results
                if result.get("actual_staged") or result.get("actual_staged_queue")
            ),
            "underfinal_count": sum(
                1
                for result in low_results
                if len(result.get("actual_final", []) or []) < len(result.get("expected_final", []) or [])
            ),
            "overfinal_count": sum(
                1
                for result in low_results
                if len(result.get("actual_final", []) or []) > len(result.get("expected_final", []) or [])
            ),
            "support_kind_counts": dict(sorted(support_counts.items())),
            "support_kind_ratios": {
                key: value / max(len(low_results), 1)
                for key, value in sorted(support_counts.items())
            },
            "by_support_kind": by_support_kind,
            "language_counts": dict(sorted(language_counts.items())),
            "top_tags": [
                {"tag": tag, "case_count": count}
                for tag, count in tag_counts.most_common(CASE_EXEMPLAR_LIMIT)
            ],
            "top_lifecycle_metrics": [
                {
                    "metric": metric,
                    "case_count": count,
                    "total_count": int(metric_total_counts[metric]),
                }
                for metric, count in sorted(
                    metric_case_counts.items(),
                    key=lambda item: (-item[1], -metric_total_counts[item[0]], item[0]),
                )[:CASE_EXEMPLAR_LIMIT]
            ],
            "lowest_cases": [
                _low_score_case_payload(result, support_by_id.get(str(result.get("id")), "unknown"))
                for result in sorted(
                    low_results,
                    key=lambda result: (
                        float(dict(result.get("final_score", {})).get("f1", 0.0)),
                        float(dict(result.get("final_ordered_score", {})).get("f1", 0.0)),
                        str(result.get("id")),
                    ),
                )[:CASE_EXEMPLAR_LIMIT]
            ],
        }
    return {
        "interpretation": (
            "Low-F1 cases are diagnostics, not direct optimization targets. "
            "Prefer single or supported_monotonic low cases for app logic tuning; review_needed cases require expected_final/input-order audit first."
        ),
        "expected_result_count": len(expected_results),
        "thresholds": thresholds,
    }


def summarize_supported_low_bottleneck_intersections(
    cases: list[SbdCase],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    support_by_id = {case.id: _expected_final_order_support_kind(case) for case in cases}
    thresholds: dict[str, dict[str, Any]] = {}
    for threshold in LOW_SCORE_THRESHOLDS:
        low_results = [
            result
            for result in results
            if _expected_order_supports_logic_tuning(support_by_id.get(str(result.get("id")), "unknown"))
            and result.get("expected_final")
            and isinstance(result.get("final_score"), dict)
            and float(dict(result.get("final_score", {})).get("f1", 0.0)) < threshold
        ]
        thresholds[f"{threshold:.2f}"] = _summarize_supported_low_threshold(low_results, threshold)
    return {
        "interpretation": (
            "These are low-score cases whose expected_final is a single sentence or whose sentences are supported by input chunks in monotonic order. "
            "Use them before changing app logic; review_needed cases may be collection or labeling issues."
        ),
        "metric_candidates": list(SUPPORTED_LOW_BOTTLENECK_METRICS),
        "thresholds": thresholds,
    }


def summarize_clean_low_bottleneck_intersections(
    cases: list[SbdCase],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return low-score bottlenecks after excluding known case-definition review flags."""
    support_by_id = {case.id: _expected_final_order_support_kind(case) for case in cases}
    thresholds: dict[str, dict[str, Any]] = {}
    for threshold in LOW_SCORE_THRESHOLDS:
        low_results = [
            result
            for result in results
            if _expected_order_supports_logic_tuning(support_by_id.get(str(result.get("id")), "unknown"))
            and result.get("expected_final")
            and isinstance(result.get("final_score"), dict)
            and float(dict(result.get("final_score", {})).get("f1", 0.0)) < threshold
            and not result.get("expected_quality_flags")
            and not result.get("case_context_flags")
            and not result.get("case_definition_flags")
            and dict(result.get("input_evidence", {})).get("fully_supported")
            and not _case_review_actions(result)
        ]
        thresholds[f"{threshold:.2f}"] = _summarize_supported_low_threshold(low_results, threshold)
    return {
        "interpretation": (
            "Clean low-score cases are single or supported_monotonic, have full input evidence, and have no expected_quality_flags. "
            "They also exclude unmodeled prefix context flags. "
            "They exclude case-definition review flags such as repeated expected groups. "
            "Prefer this subset for app logic changes; broader low-score groups can still be label or source review work."
        ),
        "metric_candidates": list(SUPPORTED_LOW_BOTTLENECK_METRICS),
        "thresholds": thresholds,
    }


def _summarize_supported_low_threshold(results: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    metric_presence = {
        metric: _summarize_supported_low_metric_presence(results, metric)
        for metric in SUPPORTED_LOW_BOTTLENECK_METRICS
    }
    metric_presence = {
        metric: summary
        for metric, summary in metric_presence.items()
        if int(summary["case_count"]) > 0
    }
    return {
        "threshold": threshold,
        "case_count": len(results),
        "avg_final_f1": _avg_final_f1(results),
        "avg_ordered_f1": _avg_score_f1(results, "final_ordered_score"),
        "avg_boundary_f1": _avg_score_f1(results, "final_boundary_score"),
        "staged_residue_count": sum(
            1
            for result in results
            if result.get("actual_staged") or result.get("actual_staged_queue")
        ),
        "underfinal_count": sum(
            1
            for result in results
            if len(result.get("actual_final", []) or []) < len(result.get("expected_final", []) or [])
        ),
        "overfinal_count": sum(
            1
            for result in results
            if len(result.get("actual_final", []) or []) > len(result.get("expected_final", []) or [])
        ),
        "metric_presence": metric_presence,
        "top_metric_pairs": _summarize_supported_low_metric_intersections(results, size=2),
        "top_metric_triples": _summarize_supported_low_metric_intersections(results, size=3),
        "lowest_cases": [
            _low_score_case_payload(result, "supported_monotonic")
            for result in sorted(
                results,
                key=lambda result: (
                    float(dict(result.get("final_score", {})).get("f1", 0.0)),
                    float(dict(result.get("final_ordered_score", {})).get("f1", 0.0)),
                    str(result.get("id")),
                ),
            )[:CASE_EXEMPLAR_LIMIT]
        ],
    }


def _summarize_supported_low_metric_presence(results: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    present = [result for result in results if int(dict(result.get("metrics", {})).get(metric, 0)) > 0]
    return {
        "case_count": len(present),
        "case_ratio": len(present) / max(len(results), 1),
        "total_count": int(sum(int(dict(result.get("metrics", {})).get(metric, 0)) for result in present)),
        "avg_final_f1": _avg_final_f1(present),
        "avg_ordered_f1": _avg_score_f1(present, "final_ordered_score"),
        "avg_boundary_f1": _avg_score_f1(present, "final_boundary_score"),
    }


def _summarize_supported_low_metric_intersections(results: list[dict[str, Any]], *, size: int) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for metrics in combinations(SUPPORTED_LOW_BOTTLENECK_METRICS, size):
        present = [
            result
            for result in results
            if all(int(dict(result.get("metrics", {})).get(metric, 0)) > 0 for metric in metrics)
        ]
        if not present:
            continue
        summaries.append(
            {
                "metrics": list(metrics),
                "case_count": len(present),
                "case_ratio": len(present) / max(len(results), 1),
                "avg_final_f1": _avg_final_f1(present),
                "avg_ordered_f1": _avg_score_f1(present, "final_ordered_score"),
                "avg_boundary_f1": _avg_score_f1(present, "final_boundary_score"),
                "top_cases": [
                    str(result.get("id"))
                    for result in sorted(
                        present,
                        key=lambda result: (
                            float(dict(result.get("final_score", {})).get("f1", 0.0)),
                            str(result.get("id")),
                        ),
                    )[:CASE_EXEMPLAR_LIMIT]
                ],
            }
        )
    summaries.sort(
        key=lambda item: (
            -int(item["case_count"]),
            float(item["avg_final_f1"]),
            item["metrics"],
        )
    )
    return summaries[:CASE_EXEMPLAR_LIMIT]


def _summarize_low_score_support_group(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(results),
        "avg_final_f1": _avg_final_f1(results),
        "avg_ordered_f1": _avg_score_f1(results, "final_ordered_score"),
        "avg_boundary_f1": _avg_score_f1(results, "final_boundary_score"),
        "empty_actual_count": sum(1 for result in results if not result.get("actual_final")),
        "staged_residue_count": sum(
            1
            for result in results
            if result.get("actual_staged") or result.get("actual_staged_queue")
        ),
        "underfinal_count": sum(
            1
            for result in results
            if len(result.get("actual_final", []) or []) < len(result.get("expected_final", []) or [])
        ),
        "overfinal_count": sum(
            1
            for result in results
            if len(result.get("actual_final", []) or []) > len(result.get("expected_final", []) or [])
        ),
    }


def _avg_score_f1(results: list[dict[str, Any]], key: str) -> float:
    if not results:
        return 0.0
    return sum(float(dict(result.get(key, {})).get("f1", 0.0)) for result in results) / len(results)


def _low_score_case_payload(result: dict[str, Any], support_kind: str) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}) or {})
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "support_kind": support_kind,
        "tags": list(result.get("tags", [])),
        "final_f1": float(dict(result.get("final_score", {})).get("f1", 0.0)),
        "final_ordered_f1": float(dict(result.get("final_ordered_score", {})).get("f1", 0.0)),
        "final_boundary_f1": float(dict(result.get("final_boundary_score", {})).get("f1", 0.0)),
        "expected_final_count": len(result.get("expected_final", []) or []),
        "actual_final_count": len(result.get("actual_final", []) or []),
        "staged_queue_len": len(result.get("actual_staged_queue", []) or []),
        "expected_quality_flags": list(result.get("expected_quality_flags", []) or []),
        "case_context_flags": list(result.get("case_context_flags", []) or []),
        "case_definition_flags": list(result.get("case_definition_flags", []) or []),
        "lifecycle_metrics": {
            metric: int(metrics.get(metric, 0))
            for metric in SUPPORTED_LOW_BOTTLENECK_METRICS
            if int(metrics.get(metric, 0)) > 0
        },
        "expected_final_preview": _first_text_preview(result.get("expected_final")),
        "actual_final_preview": _first_text_preview(result.get("actual_final")),
        "actual_staged_preview": _text_preview(result.get("actual_staged")),
    }


def _staged_queue_lengths(results: list[dict[str, Any]]) -> list[int]:
    return [len(result.get("actual_staged_queue", []) or []) for result in results]


def summarize_staged_queue_residue(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return queue residue shape for lifecycle structure analysis."""
    lengths = _staged_queue_lengths(results)
    non_empty_lengths = [length for length in lengths if length > 0]
    case_count = len(results)
    active_or_pending_residue = [
        result
        for result in results
        if result.get("actual_staged") or result.get("actual_pending")
    ]
    return {
        "case_count": case_count,
        "queue_residue_case_count": len(non_empty_lengths),
        "queue_residue_case_ratio": len(non_empty_lengths) / max(case_count, 1),
        "queue_residue_total": sum(non_empty_lengths),
        "queue_residue_avg_per_case": sum(lengths) / max(case_count, 1),
        "queue_residue_avg_when_present": sum(non_empty_lengths) / max(len(non_empty_lengths), 1),
        "queue_residue_max": max(non_empty_lengths, default=0),
        "queue_residue_len_ge_2_count": sum(1 for length in lengths if length >= 2),
        "queue_residue_len_ge_5_count": sum(1 for length in lengths if length >= 5),
        "active_staged_residue_case_count": sum(1 for result in results if result.get("actual_staged")),
        "pending_residue_case_count": sum(1 for result in results if result.get("actual_pending")),
        "top_queue_residue_cases": [
            _queue_residue_case_payload(result)
            for result in sorted(results, key=_queue_residue_case_sort_key, reverse=True)
            if result.get("actual_staged_queue")
        ][:CASE_EXEMPLAR_LIMIT],
        "top_active_or_pending_residue_cases": [
            _active_or_pending_residue_case_payload(result)
            for result in sorted(active_or_pending_residue, key=_active_or_pending_residue_case_sort_key, reverse=True)
        ][:CASE_EXEMPLAR_LIMIT],
    }


def summarize_ordered_final_gap(results: list[dict[str, Any]]) -> dict[str, Any]:
    gap_cases: list[dict[str, Any]] = []
    for result in results:
        final_score = dict(result.get("final_score", {}))
        ordered_score = dict(result.get("final_ordered_score", final_score))
        final_f1 = float(final_score.get("f1", 0.0))
        ordered_f1 = float(ordered_score.get("f1", final_f1))
        gap = final_f1 - ordered_f1
        if gap <= 0.0:
            continue
        gap_cases.append(
            {
                "id": result.get("id"),
                "language": result.get("language"),
                "tags": list(result.get("tags", [])),
                "final_f1": final_f1,
                "final_ordered_f1": ordered_f1,
                "ordered_gap": gap,
                "expected_final_count": len(result.get("expected_final", []) or []),
                "actual_final_count": len(result.get("actual_final", []) or []),
                "expected_final_preview": _first_text_preview(result.get("expected_final")),
                "actual_final_preview": _first_text_preview(result.get("actual_final")),
            }
        )
    return {
        "ordered_gap_case_count": len(gap_cases),
        "ordered_gap_avg_when_present": sum(float(item["ordered_gap"]) for item in gap_cases) / max(len(gap_cases), 1),
        "ordered_gap_max": max((float(item["ordered_gap"]) for item in gap_cases), default=0.0),
        "top_ordered_gap_cases": sorted(gap_cases, key=lambda item: (-float(item["ordered_gap"]), str(item["id"])))[
            :CASE_EXEMPLAR_LIMIT
        ],
    }


def _boundary_zero_high_final_payload(result: dict[str, Any]) -> dict[str, Any]:
    final_score = dict(result.get("final_score", {}))
    ordered_score = dict(result.get("final_ordered_score", final_score))
    boundary_score = dict(result.get("final_boundary_score", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_ordered_f1": float(ordered_score.get("f1", final_score.get("f1", 0.0))),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "expected_final_preview": _first_text_preview(result.get("expected_final")),
        "actual_final_preview": _first_text_preview(result.get("actual_final")),
    }


def summarize_boundary_zero_high_final_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Find cases where exact boundary offsets are stricter than final sentence matching."""
    expected_results = [
        result
        for result in results
        if result.get("expected_final") and isinstance(result.get("final_boundary_score"), dict)
    ]
    high_final_boundary_zero: list[dict[str, Any]] = []
    high_ordered_boundary_zero: list[dict[str, Any]] = []
    for result in expected_results:
        final_score = dict(result.get("final_score", {}))
        ordered_score = dict(result.get("final_ordered_score", final_score))
        boundary_score = dict(result.get("final_boundary_score", {}))
        final_f1 = float(final_score.get("f1", 0.0))
        ordered_f1 = float(ordered_score.get("f1", final_f1))
        boundary_f1 = float(boundary_score.get("f1", 0.0))
        if boundary_f1 != 0.0:
            continue
        if final_f1 >= BOUNDARY_ZERO_HIGH_FINAL_F1:
            high_final_boundary_zero.append(result)
        if ordered_f1 >= BOUNDARY_ZERO_HIGH_FINAL_F1:
            high_ordered_boundary_zero.append(result)
    return {
        "interpretation": (
            "final_boundary_f1 is an exact boundary-offset diagnostic. Cases in this summary "
            "matched final sentences well but scored zero on boundary offsets, so they should be "
            "reviewed as metric sensitivity or label-boundary issues before treating them as app "
            "logic failures."
        ),
        "high_final_threshold": BOUNDARY_ZERO_HIGH_FINAL_F1,
        "expected_case_count": len(expected_results),
        "boundary_zero_high_final_count": len(high_final_boundary_zero),
        "boundary_zero_high_ordered_count": len(high_ordered_boundary_zero),
        "boundary_zero_high_final_examples": [
            _boundary_zero_high_final_payload(result)
            for result in sorted(
                high_final_boundary_zero,
                key=lambda item: (
                    -float(dict(item.get("final_score", {})).get("f1", 0.0)),
                    str(item.get("id", "")),
                ),
            )[:CASE_EXEMPLAR_LIMIT]
        ],
    }


def _boundary_granularity_payload(result: dict[str, Any]) -> dict[str, Any]:
    final_score = dict(result.get("final_score", {}))
    ordered_score = dict(result.get("final_ordered_score", final_score))
    boundary_score = dict(result.get("final_boundary_score", {}))
    expected_final = list(result.get("expected_final", []) or [])
    actual_final = list(result.get("actual_final", []) or [])
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "final_precision": float(final_score.get("precision", 0.0)),
        "final_recall": float(final_score.get("recall", 0.0)),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_ordered_f1": float(ordered_score.get("f1", final_score.get("f1", 0.0))),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "expected_final_count": len(expected_final),
        "actual_final_count": len(actual_final),
        "expected_final_preview": _first_text_preview(expected_final),
        "actual_final_preview": _first_text_preview(actual_final),
    }


def summarize_boundary_granularity_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Find likely label granularity cases where content is recalled but split differently."""
    expected_results = [
        result
        for result in results
        if result.get("expected_final") and isinstance(result.get("final_boundary_score"), dict)
    ]
    granularity_cases: list[dict[str, Any]] = []
    for result in expected_results:
        final_score = dict(result.get("final_score", {}))
        boundary_score = dict(result.get("final_boundary_score", {}))
        expected_count = len(list(result.get("expected_final", []) or []))
        actual_count = len(list(result.get("actual_final", []) or []))
        final_recall = float(final_score.get("recall", 0.0))
        final_f1 = float(final_score.get("f1", 0.0))
        boundary_f1 = float(boundary_score.get("f1", 0.0))
        if actual_count <= expected_count:
            continue
        if final_recall < BOUNDARY_GRANULARITY_FINAL_RECALL:
            continue
        if final_f1 < BOUNDARY_GRANULARITY_FINAL_F1:
            continue
        if boundary_f1 > BOUNDARY_GRANULARITY_MAX_BOUNDARY_F1:
            continue
        granularity_cases.append(result)
    return {
        "interpretation": (
            "These cases recovered expected content with high recall but emitted more final "
            "segments than expected and scored low on exact boundary offsets. Review them as "
            "boundary granularity or label-boundary cases before using them as missing-final "
            "app-logic evidence."
        ),
        "thresholds": {
            "min_final_recall": BOUNDARY_GRANULARITY_FINAL_RECALL,
            "min_final_f1": BOUNDARY_GRANULARITY_FINAL_F1,
            "max_boundary_f1": BOUNDARY_GRANULARITY_MAX_BOUNDARY_F1,
        },
        "expected_case_count": len(expected_results),
        "boundary_granularity_case_count": len(granularity_cases),
        "boundary_granularity_examples": [
            _boundary_granularity_payload(result)
            for result in sorted(
                granularity_cases,
                key=lambda item: (
                    float(dict(item.get("final_boundary_score", {})).get("f1", 0.0)),
                    -float(dict(item.get("final_score", {})).get("recall", 0.0)),
                    str(item.get("id", "")),
                ),
            )[:CASE_EXEMPLAR_LIMIT]
        ],
    }


def _average_scores(results: list[dict[str, Any]], key: str) -> dict[str, float]:
    if not results:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "similarity_coverage": 0.0}
    fallback_key = "final_score" if key == "final_ordered_score" else key
    scores = [dict(result.get(key) or result.get(fallback_key, {})) for result in results]
    return {
        "precision": sum(float(score["precision"]) for score in scores) / len(scores),
        "recall": sum(float(score["recall"]) for score in scores) / len(scores),
        "f1": sum(float(score["f1"]) for score in scores) / len(scores),
        "similarity_coverage": sum(float(score.get("similarity_coverage", 0.0)) for score in scores)
        / len(results),
    }


def _summarize_result_group(group_results: list[dict[str, Any]]) -> dict[str, Any]:
    final_score_avg = _average_scores(group_results, "final_score")
    final_ordered_score_avg = _average_scores(group_results, "final_ordered_score")
    final_boundary_score_avg = _average_scores(group_results, "final_boundary_score")
    completed_last_score_avg = _average_scores(group_results, "completed_last_score")
    metrics_total: dict[str, int] = {}
    for result in group_results:
        for key, value in dict(result.get("metrics", {})).items():
            metrics_total[key] = metrics_total.get(key, 0) + int(value)
    stage_start = metrics_total.get("stage_start", 0)
    finalized = metrics_total.get("finalized", 0)
    return {
        "case_count": len(group_results),
        "case_exact_match": sum(1 for result in group_results if result["case_exact_match"]),
        "pending_exact_match": sum(1 for result in group_results if result["pending_exact"]),
        "staged_exact_match": sum(1 for result in group_results if result["staged_exact"]),
        "finalized": finalized,
        "stage_start": stage_start,
        "finalized_per_stage_start": finalized / max(stage_start, 1),
        "final_precision_avg": final_score_avg["precision"],
        "final_recall_avg": final_score_avg["recall"],
        "final_f1_avg": final_score_avg["f1"],
        "final_similarity_coverage_avg": final_score_avg["similarity_coverage"],
        "final_ordered_precision_avg": final_ordered_score_avg["precision"],
        "final_ordered_recall_avg": final_ordered_score_avg["recall"],
        "final_ordered_f1_avg": final_ordered_score_avg["f1"],
        "final_ordered_similarity_coverage_avg": final_ordered_score_avg["similarity_coverage"],
        "final_boundary_precision_avg": final_boundary_score_avg["precision"],
        "final_boundary_recall_avg": final_boundary_score_avg["recall"],
        "final_boundary_f1_avg": final_boundary_score_avg["f1"],
        "completed_last_precision_avg": completed_last_score_avg["precision"],
        "completed_last_recall_avg": completed_last_score_avg["recall"],
        "completed_last_f1_avg": completed_last_score_avg["f1"],
        "staged_residue_count": sum(
            1
            for result in group_results
            if result["actual_staged"] or result["actual_staged_queue"]
        ),
        "empty_final_count": sum(
            1
            for result in group_results
            if result["expected_final"] and not result["actual_final"]
        ),
        "expected_boundary_zero_count": sum(
            1
            for result in group_results
            if result["expected_final"] and float(result["final_boundary_score"]["f1"]) == 0.0
        ),
        "metrics": metrics_total,
    }


def summarize_results_by_language(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        language = str(result.get("language") or "unknown")
        grouped.setdefault(language, []).append(result)
    return {language: _summarize_result_group(grouped[language]) for language in sorted(grouped)}


def summarize_results_by_tag(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        for tag in result.get("tags", []):
            tag_name = str(tag).strip()
            if not tag_name or not is_diagnostic_tag(tag_name):
                continue
            grouped.setdefault(tag_name, []).append(result)
    return {tag: _summarize_result_group(grouped[tag]) for tag in sorted(grouped)}


def _has_tag_marker(result: dict[str, Any], markers: tuple[str, ...]) -> bool:
    return any(
        marker in str(tag).strip()
        for tag in result.get("tags", [])
        for marker in markers
    )


def summarize_results_by_evidence_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Separate lifecycle evidence from cases that need input/source review."""
    input_review = [
        result
        for result in results
        if _has_tag_marker(result, INPUT_CONTAMINATION_REVIEW_TAG_MARKERS)
    ]
    lifecycle_focus = [
        result
        for result in results
        if _has_tag_marker(result, LIFECYCLE_FOCUS_TAG_MARKERS)
    ]
    lifecycle_without_input_review = [
        result
        for result in lifecycle_focus
        if not _has_tag_marker(result, INPUT_CONTAMINATION_REVIEW_TAG_MARKERS)
    ]
    return {
        "all_cases": _summarize_result_group(results),
        "lifecycle_focus": _summarize_result_group(lifecycle_focus),
        "lifecycle_without_input_review": _summarize_result_group(lifecycle_without_input_review),
        "input_contamination_review": _summarize_result_group(input_review),
    }


def summarize_results_by_expected_quality_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Separate case-definition review candidates from cleaner lifecycle cases."""
    expected_quality: list[dict[str, Any]] = []
    without_expected_quality: list[dict[str, Any]] = []
    for result in results:
        expected_final = [
            str(item).strip()
            for item in result.get("expected_final", [])
            if str(item).strip()
        ]
        if expected_quality_flags(expected_final):
            expected_quality.append(result)
        else:
            without_expected_quality.append(result)
    return {
        "expected_quality_review": _summarize_result_group(expected_quality),
        "without_expected_quality_review": _summarize_result_group(without_expected_quality),
    }


def summarize_results_by_input_evidence_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Separate cases whose expected final text is weakly represented in replay inputs."""
    full_input_evidence: list[dict[str, Any]] = []
    partial_input_evidence_review: list[dict[str, Any]] = []
    weak_input_evidence: list[dict[str, Any]] = []
    for result in results:
        evidence = case_input_evidence(result)
        if evidence["fully_supported"]:
            full_input_evidence.append(result)
        elif evidence["has_evidence"]:
            partial_input_evidence_review.append(result)
        else:
            weak_input_evidence.append(result)
    return {
        "full_input_evidence": _summarize_result_group(full_input_evidence),
        "partial_input_evidence_review": _summarize_result_group(partial_input_evidence_review),
        "weak_input_evidence_review": _summarize_result_group(weak_input_evidence),
    }


def summarize_results_by_context_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    clean_context: list[dict[str, Any]] = []
    context_review: list[dict[str, Any]] = []
    for result in results:
        if result.get("case_context_flags"):
            context_review.append(result)
        else:
            clean_context.append(result)
    return {
        "clean_context": _summarize_result_group(clean_context),
        "context_definition_review": _summarize_result_group(context_review),
    }


def summarize_results_by_case_definition_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    clean_definition: list[dict[str, Any]] = []
    definition_review: list[dict[str, Any]] = []
    for result in results:
        if result.get("case_definition_flags"):
            definition_review.append(result)
        else:
            clean_definition.append(result)
    return {
        "clean_case_definition": _summarize_result_group(clean_definition),
        "case_definition_review": _summarize_result_group(definition_review),
    }


def _case_primary_review_action(result: dict[str, Any]) -> str:
    if not result.get("expected_final"):
        return ""
    input_evidence = dict(result.get("input_evidence", {}))
    expected_quality = set(result.get("expected_quality_flags", []) or [])
    context_flags = set(result.get("case_context_flags", []) or [])
    definition_flags = set(result.get("case_definition_flags", []) or [])
    if (
        not input_evidence.get("stable_repeat_fully_supported", True)
        and int(input_evidence.get("stable_candidate_count", 0)) > 0
    ):
        if _stable_candidate_ordered_alignment(result) != "ordered_high_similarity":
            return "recut_or_relabel_stable_candidate_mismatch"
        return "rewrite_expected_final_to_stable_repeated_candidate"
    if not input_evidence.get("fully_supported"):
        return "remove_or_recut_expected_outside_replay_input"
    if not input_evidence.get("observed_fully_supported", True):
        return "rewrite_expected_final_to_observed_stt_text"
    if context_flags.intersection({"unmodeled_prefix_context", "actual_prefix_before_expected_final"}):
        return "add_initial_final_or_recut_mid_stream_case"
    if "legacy_sample_without_source_trace" in definition_flags:
        return "restore_source_log_or_recut_from_observed_log"
    if definition_flags.intersection(
        {
            "duplicate_expected_sentence",
            "expected_revision_variant_group",
            "contained_expected_token_sentence",
            "short_contained_expected_token_sentence",
            "short_expected_supported_by_longer_sentence",
            "expected_app_quality_blocked_sentence",
        }
    ):
        return "rewrite_expected_final_to_final_sentence_boundary"
    if "punctuation_only_final_mismatch" in definition_flags:
        return "manual_boundary_review"
    if expected_quality:
        return "rewrite_expected_final_to_final_sentence_boundary"
    if "repeated_expected_group" in definition_flags:
        return "deduplicate_or_justify_shifted_window_repeat"
    if "expected_final_omits_stable_actual_sentence" in definition_flags:
        return "manual_boundary_review"
    if _has_expected_final_staged_residue(result):
        return "extend_replay_tail_or_reclassify_staged_expectation"
    if _missing_expected_split_coverage_payload(result) is not None:
        return "manual_boundary_review"
    if _is_boundary_granularity_review(result):
        return "manual_boundary_review"
    if definition_flags.intersection({"nested_expected_sentence"}):
        return "manual_boundary_review"
    return ""


def _is_boundary_granularity_review(result: dict[str, Any]) -> bool:
    if not result.get("expected_final"):
        return False
    if not isinstance(result.get("final_boundary_score"), dict):
        return False
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    expected_count = len(list(result.get("expected_final", []) or []))
    actual_count = len(list(result.get("actual_final", []) or []))
    return (
        actual_count > expected_count
        and float(final_score.get("recall", 0.0)) >= BOUNDARY_GRANULARITY_FINAL_RECALL
        and float(final_score.get("f1", 0.0)) >= BOUNDARY_GRANULARITY_FINAL_F1
        and float(boundary_score.get("f1", 0.0)) <= BOUNDARY_GRANULARITY_MAX_BOUNDARY_F1
    )


def _has_expected_final_staged_residue(result: dict[str, Any]) -> bool:
    expected_final = [
        str(sentence).strip()
        for sentence in result.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    if not expected_final:
        return False
    actual_final = [
        normalized_text(sentence)
        for sentence in result.get("actual_final", []) or []
        if normalized_text(sentence)
    ]
    residue = [
        str(result.get("actual_staged") or "").strip(),
        str(result.get("actual_pending") or "").strip(),
        *[str(sentence).strip() for sentence in result.get("actual_staged_queue", []) or []],
    ]
    residue = [sentence for sentence in residue if sentence]
    if not residue:
        return False
    for expected in expected_final:
        actual_support = max(
            (_sentence_support_score(expected, final) for final in actual_final),
            default=0.0,
        )
        if actual_support >= TERMINAL_RESIDUE_ACTUAL_COMPLETE_MIN:
            continue
        if any(_sentence_support_score(expected, staged) >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY for staged in residue):
            return True
        if any(_is_expected_terminal_residue(expected, staged) for staged in residue):
            return True
        if _combined_residue_support_score(expected, residue) >= COMBINED_RESIDUE_MATCH_MIN_SIMILARITY:
            return True
        if actual_support >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            continue
    return False


def _combined_residue_support_score(expected: str, residue: list[str]) -> float:
    expected_text = normalized_text(expected)
    if not expected_text or len(residue) < 2:
        return 0.0
    best = 0.0
    for index in range(0, len(residue) - 1):
        combined = normalized_text(residue[index]) + normalized_text(residue[index + 1])
        if not combined:
            continue
        best = max(best, _sentence_support_score(expected_text, combined))
    return best


def _is_expected_terminal_residue(expected: str, residue: str) -> bool:
    expected_words = _word_units(normalized_text(expected))
    residue_words = _word_units(normalized_text(residue))
    if len(residue_words) < TERMINAL_RESIDUE_MIN_UNITS or len(expected_words) <= len(residue_words):
        return False
    matcher = SequenceMatcher(None, expected_words, residue_words, autojunk=False)
    best_tail_coverage = 0.0
    for block in matcher.get_matching_blocks():
        if block.size <= 0:
            continue
        if block.b + block.size != len(residue_words):
            continue
        if block.a + block.size != len(expected_words):
            continue
        best_tail_coverage = max(best_tail_coverage, block.size / max(len(residue_words), 1))
    return best_tail_coverage >= TERMINAL_RESIDUE_SUFFIX_COVERAGE_MIN


def _case_review_actions(result: dict[str, Any]) -> list[str]:
    action = _case_primary_review_action(result)
    return [action] if action else []


def _case_review_payload(result: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(result.get("case_metadata", {}) or {})
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "case_file": metadata.get("case_file"),
        "case_line": metadata.get("case_line"),
        "source_log": metadata.get("source_log"),
        "source_chunk": metadata.get("source_chunk"),
        "review_group_id": metadata.get("review_group_id"),
        "actions": _case_review_actions(result),
        "primary_action": _case_primary_review_action(result),
        "stable_candidate_shape": _stable_repeat_candidate_shape(result),
        "stable_candidate_ordered_alignment": _stable_candidate_ordered_alignment(result),
        "initial_final": list(result.get("initial_final", []) or []),
        "expected_final": list(result.get("expected_final", []) or []),
        "actual_final": list(result.get("actual_final", []) or []),
        "input_evidence": dict(result.get("input_evidence", {}) or {}),
        "stable_candidates": case_stable_sentence_candidates(result),
        "expected_quality_flags": list(result.get("expected_quality_flags", []) or []),
        "case_context_flags": list(result.get("case_context_flags", []) or []),
        "case_definition_flags": list(result.get("case_definition_flags", []) or []),
        "final_f1": float(dict(result.get("final_score", {})).get("f1", 0.0)),
        "expected_final_count": len(result.get("expected_final", []) or []),
        "actual_final_count": len(result.get("actual_final", []) or []),
        "expected_final_preview": _first_text_preview(result.get("expected_final")),
        "actual_final_preview": _first_text_preview(result.get("actual_final")),
    }


def _stable_repeat_candidate_shape(result: dict[str, Any]) -> str:
    input_evidence = dict(result.get("input_evidence", {}) or {})
    expected_count = int(input_evidence.get("expected_count", 0) or 0)
    stable_candidate_count = int(input_evidence.get("stable_candidate_count", 0) or 0)
    stable_repeat_count = int(input_evidence.get("stable_repeat_count", 0) or 0)
    if expected_count <= 0:
        return "no_expected_final"
    if stable_repeat_count >= expected_count:
        return "fully_supported"
    if stable_candidate_count <= 0:
        return "no_stable_candidate"
    if stable_candidate_count < expected_count:
        return "fewer_stable_candidates_than_expected"
    if stable_candidate_count == expected_count:
        return "same_stable_candidate_count_as_expected"
    return "more_stable_candidates_than_expected"


def _stable_candidate_ordered_alignment(result: dict[str, Any]) -> str:
    expected_final = [
        str(sentence).strip()
        for sentence in result.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    if not expected_final:
        return "no_expected_final"
    input_evidence = dict(result.get("input_evidence", {}) or {})
    stable_candidate_count = int(input_evidence.get("stable_candidate_count", 0) or 0)
    if stable_candidate_count <= 0:
        return "no_stable_candidate"
    if stable_candidate_count != len(expected_final):
        return "candidate_count_mismatch"
    stable_examples = [
        str(candidate.get("text", "")).strip()
        for candidate in case_stable_sentence_candidates(result)
        if str(candidate.get("text", "")).strip()
    ]
    if len(stable_examples) != stable_candidate_count:
        return "candidate_count_mismatch"
    similarities = [
        _sentence_support_score(expected, stable)
        for expected, stable in zip(expected_final, stable_examples, strict=False)
    ]
    if not similarities:
        return "no_stable_candidate"
    min_similarity = min(similarities)
    if min_similarity >= STABLE_CANDIDATE_ORDERED_REWRITE_MIN_SIMILARITY:
        return "ordered_high_similarity"
    if min_similarity >= STABLE_CANDIDATE_ORDERED_REVIEW_MIN_SIMILARITY:
        return "ordered_review_similarity"
    return "ordered_low_similarity"


def summarize_case_definition_action_items(results: list[dict[str, Any]]) -> dict[str, Any]:
    review_results = [
        result
        for result in results
        if _case_review_actions(result)
    ]
    logic_tuning_candidate_count = sum(
        1
        for result in results
        if result.get("expected_final")
        and not _case_review_actions(result)
    )
    action_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    expected_quality_counts: Counter[str] = Counter()
    context_flag_counts: Counter[str] = Counter()
    definition_flag_counts: Counter[str] = Counter()
    stable_candidate_shape_counts: Counter[str] = Counter()
    stable_candidate_ordered_alignment_counts: Counter[str] = Counter()
    for result in review_results:
        action_counts.update(_case_review_actions(result))
        language_counts[str(result.get("language") or "unknown")] += 1
        expected_quality_counts.update(str(flag) for flag in result.get("expected_quality_flags", []) or [])
        context_flag_counts.update(str(flag) for flag in result.get("case_context_flags", []) or [])
        definition_flag_counts.update(str(flag) for flag in result.get("case_definition_flags", []) or [])
        stable_candidate_shape_counts[_stable_repeat_candidate_shape(result)] += 1
        stable_candidate_ordered_alignment_counts[_stable_candidate_ordered_alignment(result)] += 1
    by_action: dict[str, Any] = {}
    for action in CASE_REVIEW_ACTION_FLAGS:
        action_results = [
            result
            for result in review_results
            if action in _case_review_actions(result)
        ]
        by_action[action] = {
            "case_count": len(action_results),
            "final_f1_avg": _avg_final_f1(action_results),
            "language_counts": dict(
                sorted(Counter(str(result.get("language") or "unknown") for result in action_results).items())
            ),
            "stable_candidate_shape_counts": dict(
                sorted(Counter(_stable_repeat_candidate_shape(result) for result in action_results).items())
            ),
            "stable_candidate_ordered_alignment_counts": dict(
                sorted(Counter(_stable_candidate_ordered_alignment(result) for result in action_results).items())
            ),
            "examples": [
                _case_review_payload(result)
                for result in sorted(
                    action_results,
                    key=lambda result: (
                        float(dict(result.get("final_score", {})).get("f1", 0.0)),
                        str(result.get("id")),
                    ),
                )[:CASE_EXEMPLAR_LIMIT]
            ],
        }
    return {
        "interpretation": (
            "These are prioritized case-definition review actions, not automatic deletion rules. "
            "Use recut_or_relabel_stable_candidate_mismatch when replay chunks contain stable token-sentence "
            "candidates repeated at least sentence_finalize_age times but expected_final does not align with "
            "their count or ordered text; this usually needs replay recut, initial_final restoration, or "
            "expected sentence count changes before app-logic tuning. Use rewrite_expected_final_to_stable_repeated_candidate "
            "only when stable candidates are count-compatible and ordered-high-similarity with expected_final. "
            "Use remove_or_recut_expected_outside_replay_input when expected_final "
            "is not fully represented in replay chunks and no stable repeated candidate explains the case, "
            "rewrite_expected_final_to_observed_stt_text when expected labels have similar "
            "unit coverage but are not observed as raw STT text, add_initial_final_or_recut_mid_stream_case "
            "for mid-stream cases or actual finals that show missing prefix context, "
            "restore_source_log_or_recut_from_observed_log when migrated legacy sample cases have no "
            "traceable source_log/source_chunk, "
            "rewrite_expected_final_to_final_sentence_boundary for fragment-like "
            "expected_final labels, extend_replay_tail_or_reclassify_staged_expectation when expected final "
            "text is still staged at the end of the replay window without ordered stable-repeat support, "
            "deduplicate_or_justify_shifted_window_repeat when repeated sliding-window samples overweight "
            "one log region, and manual_boundary_review for remaining nested boundary ambiguities. "
            "stable_candidate_shape_counts separates simple expected_final rewrites from cases that need "
            "label count changes, replay recuts, or initial_final context restoration. "
            "stable_candidate_ordered_alignment_counts separates count-compatible stable candidates from "
            "cases whose ordered expected_final labels still do not align with stable candidates."
        ),
        "review_case_count": len(review_results),
        "logic_tuning_candidate_count": logic_tuning_candidate_count,
        "action_counts": dict(sorted(action_counts.items())),
        "language_counts": dict(sorted(language_counts.items())),
        "expected_quality_flag_counts": dict(sorted(expected_quality_counts.items())),
        "case_context_flag_counts": dict(sorted(context_flag_counts.items())),
        "case_definition_flag_counts": dict(sorted(definition_flag_counts.items())),
        "stable_candidate_shape_counts": dict(sorted(stable_candidate_shape_counts.items())),
        "stable_candidate_ordered_alignment_counts": dict(sorted(stable_candidate_ordered_alignment_counts.items())),
        "by_action": by_action,
    }


def _stable_cleanup_queue_for_result(result: dict[str, Any]) -> str:
    shape = _stable_repeat_candidate_shape(result)
    alignment = _stable_candidate_ordered_alignment(result)
    if shape == "fewer_stable_candidates_than_expected":
        return "expected_final_over_specified_or_window_too_short"
    if shape == "more_stable_candidates_than_expected":
        return "expected_final_omits_stable_candidates_or_boundary_merged"
    if shape == "same_stable_candidate_count_as_expected":
        if alignment == "ordered_low_similarity":
            return "same_count_but_expected_text_mismatch"
        if alignment == "ordered_review_similarity":
            return "same_count_needs_manual_text_review"
        return "same_count_alignment_review"
    if shape == "no_stable_candidate":
        return "no_stable_repeat_evidence"
    return "other_stable_candidate_review"


def summarize_case_definition_cleanup_queue(results: list[dict[str, Any]]) -> dict[str, Any]:
    stable_mismatches = [
        result
        for result in results
        if _case_primary_review_action(result) == "recut_or_relabel_stable_candidate_mismatch"
    ]
    by_queue: dict[str, Any] = {}
    for queue in sorted({_stable_cleanup_queue_for_result(result) for result in stable_mismatches}):
        queue_results = [
            result
            for result in stable_mismatches
            if _stable_cleanup_queue_for_result(result) == queue
        ]
        by_queue[queue] = {
            "case_count": len(queue_results),
            "final_f1_avg": _avg_final_f1(queue_results),
            "language_counts": dict(
                sorted(Counter(str(result.get("language") or "unknown") for result in queue_results).items())
            ),
            "stable_candidate_shape_counts": dict(
                sorted(Counter(_stable_repeat_candidate_shape(result) for result in queue_results).items())
            ),
            "stable_candidate_ordered_alignment_counts": dict(
                sorted(Counter(_stable_candidate_ordered_alignment(result) for result in queue_results).items())
            ),
            "case_file_counts": dict(
                sorted(
                    Counter(
                        str(dict(result.get("case_metadata", {}) or {}).get("case_file") or "unknown")
                        for result in queue_results
                    ).items()
                )
            ),
            "examples": [
                _case_review_payload(result)
                for result in sorted(
                    queue_results,
                    key=lambda result: (
                        float(dict(result.get("final_score", {})).get("f1", 0.0)),
                        str(result.get("id")),
                    ),
                )[:CASE_EXEMPLAR_LIMIT]
            ],
        }
    return {
        "interpretation": (
            "Groups recut_or_relabel_stable_candidate_mismatch cases by the kind of expected_final cleanup needed. "
            "The repeat threshold is the case sentence_finalize_age; with the current default this is 3 observations, "
            "but it is not a separate benchmark policy. Use this queue before changing app logic."
        ),
        "case_count": len(stable_mismatches),
        "queue_counts": {
            queue: int(item["case_count"])
            for queue, item in by_queue.items()
        },
        "by_queue": by_queue,
    }


def summarize_case_definition_files(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize case-definition review pressure by JSONL shard."""
    by_file: dict[str, dict[str, Any]] = {}
    for result in results:
        metadata = dict(result.get("case_metadata", {}) or {})
        case_file = str(metadata.get("case_file") or "unknown")
        item = by_file.setdefault(
            case_file,
            {
                "case_file": case_file,
                "case_count": 0,
                "review_case_count": 0,
                "logic_tuning_candidate_count": 0,
                "final_f1_total": 0.0,
                "action_counts": Counter(),
                "expected_quality_flag_counts": Counter(),
                "case_definition_flag_counts": Counter(),
                "language_counts": Counter(),
                "examples": [],
            },
        )
        item["case_count"] += 1
        item["final_f1_total"] += float(dict(result.get("final_score", {})).get("f1", 0.0))
        item["language_counts"][str(result.get("language") or "unknown")] += 1
        actions = _case_review_actions(result)
        if actions:
            item["review_case_count"] += 1
            item["action_counts"].update(actions)
            item["expected_quality_flag_counts"].update(
                str(flag) for flag in result.get("expected_quality_flags", []) or []
            )
            item["case_definition_flag_counts"].update(
                str(flag) for flag in result.get("case_definition_flags", []) or []
            )
            item["examples"].append(_case_review_payload(result))
        elif result.get("expected_final"):
            item["logic_tuning_candidate_count"] += 1

    file_items: list[dict[str, Any]] = []
    for item in by_file.values():
        examples = sorted(
            item["examples"],
            key=lambda example: (float(example.get("final_f1", 0.0)), str(example.get("id"))),
        )[:CASE_EXEMPLAR_LIMIT]
        file_items.append(
            {
                "case_file": item["case_file"],
                "case_count": item["case_count"],
                "review_case_count": item["review_case_count"],
                "review_case_ratio": item["review_case_count"] / max(item["case_count"], 1),
                "logic_tuning_candidate_count": item["logic_tuning_candidate_count"],
                "final_f1_avg": item["final_f1_total"] / max(item["case_count"], 1),
                "action_counts": dict(sorted(item["action_counts"].items())),
                "expected_quality_flag_counts": dict(sorted(item["expected_quality_flag_counts"].items())),
                "case_definition_flag_counts": dict(sorted(item["case_definition_flag_counts"].items())),
                "language_counts": dict(sorted(item["language_counts"].items())),
                "examples": examples,
            }
        )
    file_items.sort(
        key=lambda item: (
            int(item["review_case_count"]),
            float(item["review_case_ratio"]),
            -float(item["final_f1_avg"]),
            str(item["case_file"]),
        ),
        reverse=True,
    )
    return {
        "interpretation": (
            "Ranks JSONL shards by case-definition review pressure. "
            "Use this to choose recut/deduplication targets before changing app logic."
        ),
        "file_count": len(file_items),
        "files_with_review_cases": sum(1 for item in file_items if item["review_case_count"]),
        "top_files": file_items[:CASE_EXEMPLAR_LIMIT],
    }


def _case_collection_kind(result: dict[str, Any]) -> str:
    case_id = str(result.get("id") or "")
    metadata = dict(result.get("case_metadata", {}) or {})
    tags = {str(tag).strip() for tag in result.get("tags", []) if str(tag).strip()}
    if "_draft_" in case_id or metadata.get("review_group_id") or "reviewed-log" in tags:
        return "reviewed_log_work_item"
    if metadata.get("source_log") or any(str(tag).startswith("log-") for tag in tags):
        return "manual_log_case"
    if "manual-promoted" in tags or "manual-reviewed" in tags:
        return "manual_reviewed_case"
    return "manual_named_case"


def summarize_results_by_collection_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(_case_collection_kind(result), []).append(result)
    return {
        name: _summarize_result_group(grouped[name])
        for name in sorted(grouped)
    }


def _case_source_trace_kind(result: dict[str, Any]) -> str:
    if not result.get("expected_final"):
        return "no_expected_final"
    metadata = dict(result.get("case_metadata", {}) or {})
    if metadata.get("source_log") and metadata.get("source_chunk") is not None:
        return "traceable_source_log"
    if "legacy_sample_without_source_trace" in set(result.get("case_definition_flags", []) or []):
        return "legacy_sample_without_source_trace"
    return "missing_source_trace"


def summarize_results_by_source_trace_strata(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(_case_source_trace_kind(result), []).append(result)

    strata: dict[str, Any] = {}
    for name in sorted(grouped):
        items = grouped[name]
        review_items = [result for result in items if _case_review_actions(result)]
        logic_items = [
            result
            for result in items
            if result.get("expected_final")
            and not _case_review_actions(result)
        ]
        source_logs = Counter(
            str(dict(result.get("case_metadata", {}) or {}).get("source_log") or "")
            for result in items
            if str(dict(result.get("case_metadata", {}) or {}).get("source_log") or "")
        )
        strata[name] = {
            **_summarize_result_group(items),
            "expected_final_case_count": sum(1 for result in items if result.get("expected_final")),
            "review_case_count": len(review_items),
            "logic_tuning_candidate_count": len(logic_items),
            "source_log_count": len(source_logs),
            "source_log_counts": dict(sorted(source_logs.items())),
            "examples": [
                _case_review_payload(result)
                for result in sorted(
                    review_items,
                    key=lambda result: (
                        float(dict(result.get("final_score", {})).get("f1", 0.0)),
                        str(result.get("id")),
                    ),
                )[:CASE_EXEMPLAR_LIMIT]
            ],
        }
    return {
        "interpretation": (
            "Separates cases with traceable source_log/source_chunk from migrated or manual cases whose "
            "original log location is missing. App-logic tuning should prefer traceable_source_log cases."
        ),
        "strata": strata,
    }


def _strict_logic_candidate(case: SbdCase, result: dict[str, Any]) -> bool:
    if not result.get("expected_final"):
        return False
    if not _expected_order_supports_logic_tuning(_expected_final_order_support_kind(case)):
        return False
    if result.get("expected_quality_flags"):
        return False
    input_evidence = dict(result.get("input_evidence", {}))
    if not input_evidence.get("fully_supported"):
        return False
    if not input_evidence.get("stable_repeat_fully_supported", True):
        return False
    if result.get("case_context_flags"):
        return False
    if result.get("case_definition_flags"):
        return False
    if _case_review_actions(result):
        return False
    return True


def summarize_strict_logic_candidate_results(cases: list[SbdCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    cases_by_id = {case.id: case for case in cases}
    strict = [
        result
        for result in results
        if (case := cases_by_id.get(str(result.get("id")))) is not None
        and _strict_logic_candidate(case, result)
    ]
    low_by_threshold: dict[str, Any] = {}
    for threshold in LOW_SCORE_THRESHOLDS:
        low = [
            result
            for result in strict
            if float(dict(result.get("final_score", {})).get("f1", 0.0)) < threshold
        ]
        low_by_threshold[f"{threshold:.2f}"] = _summarize_supported_low_threshold(low, threshold)
    return {
        "interpretation": (
            "Strict logic candidates are single or supported_monotonic, fully input-supported, have no expected quality flags, "
            "do not have unmodeled prefix context flags, have no case-definition review flags, and exclude split-coverage "
            "boundary granularity cases. "
            "Use this subset before changing app logic; other challenge cases may still be valid diagnostics but need review context."
        ),
        "strict_case_count": len(strict),
        "strict_case_ids": [str(result.get("id")) for result in strict],
        "summary": _summarize_result_group(strict),
        "collection_strata": summarize_results_by_collection_strata(strict),
        "metric_presence": {
            metric: _summarize_supported_low_metric_presence(strict, metric)
            for metric in SUPPORTED_LOW_BOTTLENECK_METRICS
            if any(int(dict(result.get("metrics", {})).get(metric, 0)) > 0 for result in strict)
        },
        "lowest_cases": [
            _low_score_case_payload(result, "strict_logic_candidate")
            for result in sorted(
                strict,
                key=lambda result: (
                    float(dict(result.get("final_score", {})).get("f1", 0.0)),
                    float(dict(result.get("final_boundary_score", {})).get("f1", 0.0)),
                    str(result.get("id")),
                ),
            )[:CASE_EXEMPLAR_LIMIT]
        ],
        "low_score_thresholds": low_by_threshold,
    }


def summarize_case_definition_health(
    *,
    results: list[dict[str, Any]],
    case_definition_action_summary: dict[str, Any],
    strict_logic_candidate_summary: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether the current case set is usable as app-logic tuning evidence."""
    expected_final_count = sum(1 for result in results if result.get("expected_final"))
    review_case_count = int(case_definition_action_summary.get("review_case_count", 0))
    logic_tuning_candidate_count = int(case_definition_action_summary.get("logic_tuning_candidate_count", 0))
    strict_case_count = int(strict_logic_candidate_summary.get("strict_case_count", 0))
    action_counts = {
        str(action): int(count)
        for action, count in dict(case_definition_action_summary.get("action_counts", {}) or {}).items()
    }
    top_actions = [
        {"action": action, "case_count": count}
        for action, count in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))[:CASE_EXEMPLAR_LIMIT]
    ]
    review_ratio = review_case_count / max(expected_final_count, 1)
    strict_ratio = strict_case_count / max(expected_final_count, 1)
    if strict_case_count <= 0:
        recommendation = "case-definition-review-required"
    elif review_ratio >= 0.50:
        recommendation = "prioritize-case-definition-cleanup"
    else:
        recommendation = "app-logic-tuning-subset-usable"
    return {
        "interpretation": (
            "Use this health summary before treating aggregate final_f1_avg as app-logic evidence. "
            "High review ratios mean the challenge corpus is dominated by label/window definition work; "
            "strict_logic_candidates are the preferred subset for conservative app-logic tuning."
        ),
        "expected_final_case_count": expected_final_count,
        "case_definition_review_count": review_case_count,
        "case_definition_review_ratio": review_ratio,
        "logic_tuning_candidate_count": logic_tuning_candidate_count,
        "logic_tuning_candidate_ratio": logic_tuning_candidate_count / max(expected_final_count, 1),
        "strict_logic_candidate_count": strict_case_count,
        "strict_logic_candidate_ratio": strict_ratio,
        "top_review_actions": top_actions,
        "recommendation": recommendation,
    }


def summarize_results_by_queue_residue_strata(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Separate cases by residual staged queue severity."""
    no_queue: list[dict[str, Any]] = []
    queue_len_1: list[dict[str, Any]] = []
    queue_len_2_to_4: list[dict[str, Any]] = []
    queue_len_ge_5: list[dict[str, Any]] = []
    for result in results:
        queue_len = len(result.get("actual_staged_queue", []) or [])
        if queue_len == 0:
            no_queue.append(result)
        elif queue_len == 1:
            queue_len_1.append(result)
        elif queue_len < 5:
            queue_len_2_to_4.append(result)
        else:
            queue_len_ge_5.append(result)
    return {
        "no_queue": _summarize_result_group(no_queue),
        "queue_len_1": _summarize_result_group(queue_len_1),
        "queue_len_2_to_4": _summarize_result_group(queue_len_2_to_4),
        "queue_len_ge_5": _summarize_result_group(queue_len_ge_5),
    }


def _with_case_evidence_metadata(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    expected_group_counts: Counter[str] = Counter()
    normalized_expected_by_id: dict[int, list[str]] = {}
    for result in results:
        expected_final = [
            normalized_text(sentence)
            for sentence in result.get("expected_final", []) or []
            if normalized_text(sentence)
        ]
        normalized_expected_by_id[id(result)] = expected_final
        if expected_final:
            expected_group_counts[
                json.dumps(
                    {
                        "language": str(result.get("language", "")),
                        "expected_final": expected_final,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            ] += 1
    for result in results:
        item = dict(result)
        metadata = dict(item.get("case_metadata", {}) or {})
        expected_final = normalized_expected_by_id.get(id(result), [])
        item["expected_quality_flags"] = expected_quality_flags(expected_final)
        item["input_evidence"] = case_input_evidence(item)
        item["case_context_flags"] = case_context_flags(item)
        case_definition_flags: list[str] = []
        review_source_file = str(metadata.get("review_source_file") or "").strip()
        source_log = str(metadata.get("source_log") or "").strip()
        source_chunk = metadata.get("source_chunk")
        if (
            expected_final
            and not source_log
            and source_chunk is None
            and review_source_file.endswith("tests/eval/dictation_ai/sbd_text_cases.sample.jsonl")
        ):
            case_definition_flags.append("legacy_sample_without_source_trace")
        if len(expected_final) != len(set(expected_final)):
            case_definition_flags.append("duplicate_expected_sentence")
        has_nested_expected = any(
            left
            and right
            and (left in right or right in left)
            for left_index, left in enumerate(expected_final)
            for right_index, right in enumerate(expected_final)
            if left_index < right_index
        )
        if has_nested_expected:
            case_definition_flags.append("nested_expected_sentence")
        has_revision_variant_expected = any(
            _expected_sentences_are_revision_variants(left, right)
            for left_index, left in enumerate(expected_final)
            for right_index, right in enumerate(expected_final)
            if left_index < right_index and left and right and left != right and left not in right and right not in left
        )
        if has_revision_variant_expected:
            case_definition_flags.append("expected_revision_variant_group")
        has_contained_token_expected = any(
            _expected_sentences_have_contained_token_units(left, right)
            for left_index, left in enumerate(expected_final)
            for right_index, right in enumerate(expected_final)
            if left_index < right_index and left and right and left != right and left not in right and right not in left
        )
        if has_contained_token_expected and not has_revision_variant_expected:
            case_definition_flags.append("contained_expected_token_sentence")
        has_short_contained_token_expected = any(
            _expected_sentences_have_short_contained_token_units(left, right)
            for left_index, left in enumerate(expected_final)
            for right_index, right in enumerate(expected_final)
            if left_index < right_index and left and right and left != right and left not in right and right not in left
        )
        if has_short_contained_token_expected and not has_revision_variant_expected:
            case_definition_flags.append("short_contained_expected_token_sentence")
        has_short_supported_by_longer_expected = any(
            _expected_short_sentence_supported_by_longer_sentence(left, right)
            for left_index, left in enumerate(expected_final)
            for right_index, right in enumerate(expected_final)
            if left_index < right_index and left and right and left != right and left not in right and right not in left
        )
        if (
            has_short_supported_by_longer_expected
            and not has_revision_variant_expected
            and not has_short_contained_token_expected
        ):
            case_definition_flags.append("short_expected_supported_by_longer_sentence")
        language = str(item.get("language", "")).strip().lower()
        if _has_expected_app_quality_blocked_sentence(expected_final, language):
            case_definition_flags.append("expected_app_quality_blocked_sentence")
        if _punctuation_only_final_mismatch(item):
            case_definition_flags.append("punctuation_only_final_mismatch")
        if expected_final:
            expected_group_key = json.dumps(
                {
                    "language": str(item.get("language", "")),
                    "expected_final": expected_final,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if expected_group_counts[expected_group_key] > 1:
                case_definition_flags.append("repeated_expected_group")
        if (
            not case_definition_flags
            and not item["expected_quality_flags"]
            and not item["case_context_flags"]
            and _has_actual_final_supported_by_omitted_stable_candidate(item)
        ):
            case_definition_flags.append("expected_final_omits_stable_actual_sentence")
        item["case_definition_flags"] = case_definition_flags
        enriched.append(item)
    return enriched


def _text_preview(value: Any, *, limit: int = CASE_EXEMPLAR_PREVIEW_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _first_text_preview(values: Any) -> str:
    if isinstance(values, list) and values:
        return _text_preview(values[0])
    return ""


def _best_sentence_similarity(sentence: str, candidates: list[str]) -> float:
    if not sentence or not candidates:
        return 0.0
    return max((_sentence_support_score(sentence, candidate) for candidate in candidates), default=0.0)


def _terminal_residue_texts(result: dict[str, Any]) -> list[str]:
    residues: list[str] = []
    staged = str(result.get("actual_staged") or "").strip()
    if staged:
        residues.append(staged)
    for item in result.get("actual_staged_queue", []) or []:
        text = str(item or "").strip()
        if text:
            residues.append(text)
    pending = str(result.get("actual_pending") or "").strip()
    if pending:
        residues.append(pending)
    return residues


def _terminal_expected_residue_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    expected_final = [str(sentence).strip() for sentence in result.get("expected_final", []) or [] if str(sentence).strip()]
    if not expected_final:
        return None
    actual_final = [str(sentence).strip() for sentence in result.get("actual_final", []) or [] if str(sentence).strip()]
    residues = _terminal_residue_texts(result)
    if not residues:
        return None
    missing_matches: list[dict[str, Any]] = []
    for sentence in expected_final:
        if _best_sentence_similarity(sentence, actual_final) >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            continue
        residue_score = _best_sentence_similarity(sentence, residues)
        if residue_score < FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            continue
        missing_matches.append(
            {
                "expected": _text_preview(sentence),
                "best_residue_similarity": residue_score,
            }
        )
    if not missing_matches:
        return None
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    metrics = dict(result.get("metrics", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "expected_final_count": len(expected_final),
        "actual_final_count": len(actual_final),
        "terminal_residue_count": len(residues),
        "matched_missing_expected_count": len(missing_matches),
        "stage_age_quality_blocked": int(metrics.get("stage_age_quality_blocked", 0)),
        "stage_queue_promote": int(metrics.get("stage_queue_promote", 0)),
        "stage_revision_token_sentence_deferred": int(metrics.get("stage_revision_token_sentence_deferred", 0)),
        "expected_residue_matches": missing_matches[:3],
        "actual_staged_preview": _text_preview(result.get("actual_staged")),
        "actual_staged_queue_preview": _first_text_preview(result.get("actual_staged_queue")),
        "actual_pending_preview": _text_preview(result.get("actual_pending")),
    }


def _missing_expected_without_terminal_residue_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    expected_final = [str(sentence).strip() for sentence in result.get("expected_final", []) or [] if str(sentence).strip()]
    if not expected_final:
        return None
    actual_final = [str(sentence).strip() for sentence in result.get("actual_final", []) or [] if str(sentence).strip()]
    residues = _terminal_residue_texts(result)
    missing: list[dict[str, Any]] = []
    for sentence in expected_final:
        actual_score = _best_sentence_similarity(sentence, actual_final)
        residue_score = _best_sentence_similarity(sentence, residues)
        if actual_score >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY or residue_score >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            continue
        missing.append(
            {
                "expected": _text_preview(sentence),
                "best_actual_similarity": actual_score,
                "best_residue_similarity": residue_score,
            }
        )
    if not missing:
        return None
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    metrics = dict(result.get("metrics", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "expected_final_count": len(expected_final),
        "actual_final_count": len(actual_final),
        "terminal_residue_count": len(residues),
        "missing_expected_count": len(missing),
        "stage_age_quality_blocked": int(metrics.get("stage_age_quality_blocked", 0)),
        "stage_candidate_quality_blocked": int(metrics.get("stage_candidate_quality_blocked", 0)),
        "stage_queue_promote": int(metrics.get("stage_queue_promote", 0)),
        "stage_revision_token_sentence_deferred": int(metrics.get("stage_revision_token_sentence_deferred", 0)),
        "candidate_delta_trimmed": int(metrics.get("candidate_delta_trimmed", 0)),
        "candidate_recent_final_delta_trimmed": int(metrics.get("candidate_recent_final_delta_trimmed", 0)),
        "missing_expected": missing[:3],
        "actual_final_preview": _first_text_preview(actual_final),
        "actual_staged_preview": _text_preview(result.get("actual_staged")),
        "actual_staged_queue_preview": _first_text_preview(result.get("actual_staged_queue")),
        "actual_pending_preview": _text_preview(result.get("actual_pending")),
    }


def summarize_terminal_expected_residue(results: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [
        payload
        for result in results
        if (payload := _terminal_expected_residue_payload(result)) is not None
    ]
    payloads.sort(
        key=lambda item: (
            int(item["matched_missing_expected_count"]),
            int(item["terminal_residue_count"]),
            -float(item["final_f1"]),
        ),
        reverse=True,
    )
    return {
        "interpretation": (
            "Expected finals matched only by terminal staged/queue/pending residue are replay-tail lifecycle "
            "evidence. Treat them separately from cases where the expected sentence disappeared entirely."
        ),
        "case_count": len(payloads),
        "matched_missing_expected_total": sum(int(item["matched_missing_expected_count"]) for item in payloads),
        "top_cases": payloads[:8],
    }


def _combined_output_texts(result: dict[str, Any]) -> list[str]:
    texts = [str(sentence).strip() for sentence in result.get("actual_final", []) or [] if str(sentence).strip()]
    texts.extend(_terminal_residue_texts(result))
    return texts


def _combined_output_coverage(sentence: str, output_texts: list[str]) -> dict[str, float]:
    sentence_units = _word_units(normalized_text(sentence))
    output_units = _word_units(normalized_text(" ".join(output_texts)))
    if not sentence_units or not output_units:
        return {"total_coverage": 0.0, "common_run_coverage": 0.0, "ratio": 0.0}
    matcher = SequenceMatcher(None, sentence_units, output_units, autojunk=False)
    blocks = matcher.get_matching_blocks()
    return {
        "total_coverage": sum(block.size for block in blocks) / max(len(sentence_units), 1),
        "common_run_coverage": max((block.size for block in blocks), default=0) / max(len(sentence_units), 1),
        "ratio": matcher.ratio(),
    }


def _missing_expected_split_coverage_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    missing_payload = _missing_expected_without_terminal_residue_payload(result)
    if missing_payload is None:
        return None
    outputs = _combined_output_texts(result)
    split_matches: list[dict[str, Any]] = []
    for missing in missing_payload.get("missing_expected", []):
        expected = str(missing.get("expected", "")).strip()
        coverage = _combined_output_coverage(expected, outputs)
        if coverage["total_coverage"] < 0.85:
            continue
        split_matches.append(
            {
                "expected": _text_preview(expected),
                "combined_total_coverage": coverage["total_coverage"],
                "combined_common_run_coverage": coverage["common_run_coverage"],
                "combined_ratio": coverage["ratio"],
            }
        )
    if not split_matches:
        return None
    payload = dict(missing_payload)
    payload["split_coverage_count"] = len(split_matches)
    payload["split_coverage_matches"] = split_matches[:3]
    return payload


def summarize_missing_expected_without_terminal_residue(results: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [
        payload
        for result in results
        if (payload := _missing_expected_without_terminal_residue_payload(result)) is not None
    ]
    payloads.sort(
        key=lambda item: (
            int(item["missing_expected_count"]),
            -float(item["final_f1"]),
            int(item["stage_age_quality_blocked"]) + int(item["stage_candidate_quality_blocked"]),
        ),
        reverse=True,
    )
    metric_totals: dict[str, int] = {
        "stage_age_quality_blocked": 0,
        "stage_candidate_quality_blocked": 0,
        "stage_queue_promote": 0,
        "stage_revision_token_sentence_deferred": 0,
        "candidate_delta_trimmed": 0,
        "candidate_recent_final_delta_trimmed": 0,
    }
    for item in payloads:
        for key in metric_totals:
            metric_totals[key] += int(item.get(key, 0))
    return {
        "interpretation": (
            "Expected finals absent from both actual final and terminal residue are stronger candidates "
            "for real sentence loss than replay-tail residue cases."
        ),
        "case_count": len(payloads),
        "missing_expected_total": sum(int(item["missing_expected_count"]) for item in payloads),
        "metric_totals": metric_totals,
        "top_cases": payloads[:8],
    }


def summarize_missing_expected_split_coverage(results: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [
        payload
        for result in results
        if (payload := _missing_expected_split_coverage_payload(result)) is not None
    ]
    payloads.sort(
        key=lambda item: (
            int(item["split_coverage_count"]),
            -float(item["final_f1"]),
            int(item["stage_age_quality_blocked"]),
        ),
        reverse=True,
    )
    return {
        "interpretation": (
            "No-residue missing expected sentences whose tokens are covered by combined actual final and "
            "terminal residue are boundary granularity or split-final candidates, not pure content loss."
        ),
        "case_count": len(payloads),
        "split_coverage_total": sum(int(item["split_coverage_count"]) for item in payloads),
        "top_cases": payloads[:8],
    }


def _case_exemplar_score(result: dict[str, Any]) -> float:
    metrics = dict(result.get("metrics", {}))
    final_score = dict(result.get("final_score", {}))
    ordered_score = dict(result.get("final_ordered_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    score = 0.0
    score += min(float(metrics.get("stage_queue_revision", 0)), 20.0)
    score += min(float(metrics.get("stage_replace_deferred", 0)), 20.0)
    score += min(float(metrics.get("stage_candidate_quality_blocked", 0)), 20.0)
    score += min(float(metrics.get("candidate_duplicate_suppressed", 0)), 10.0) / 2.0
    if result.get("actual_staged"):
        score += 4.0
    score += min(float(len(result.get("actual_staged_queue", []) or [])), 8.0)
    if result.get("expected_final") and not result.get("actual_final"):
        score += 8.0
    if float(final_score.get("f1", 0.0)) < 0.35:
        score += 6.0
    if float(ordered_score.get("f1", 0.0)) < float(final_score.get("f1", 0.0)):
        score += 3.0
    if float(boundary_score.get("f1", 0.0)) == 0.0:
        score += 4.0
    return score


def _case_exemplar_payload(result: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}))
    final_score = dict(result.get("final_score", {}))
    ordered_score = dict(result.get("final_ordered_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "bottleneck_score": round(_case_exemplar_score(result), 3),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_ordered_f1": float(ordered_score.get("f1", 0.0)),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "expected_final_count": len(result.get("expected_final", []) or []),
        "actual_final_count": len(result.get("actual_final", []) or []),
        "staged_queue_len": len(result.get("actual_staged_queue", []) or []),
        "metrics": {key: int(metrics.get(key, 0)) for key in CASE_EXEMPLAR_METRICS},
        "expected_final_preview": _first_text_preview(result.get("expected_final")),
        "actual_final_preview": _first_text_preview(result.get("actual_final")),
        "actual_staged_preview": _text_preview(result.get("actual_staged")),
        "actual_staged_queue_preview": _first_text_preview(result.get("actual_staged_queue")),
    }


def _queue_residue_case_sort_key(result: dict[str, Any]) -> tuple[int, int, int, float, float]:
    metrics = dict(result.get("metrics", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    return (
        len(result.get("actual_staged_queue", []) or []),
        int(metrics.get("stage_queue_revision", 0)),
        int(metrics.get("stage_replace_deferred", 0)),
        -float(boundary_score.get("f1", 0.0)),
        -float(dict(result.get("final_score", {})).get("f1", 0.0)),
    )


def _queue_residue_case_payload(result: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}))
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "queue_len": len(result.get("actual_staged_queue", []) or []),
        "active_staged": bool(result.get("actual_staged")),
        "pending": bool(result.get("actual_pending")),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "stage_queue_revision": int(metrics.get("stage_queue_revision", 0)),
        "stage_replace_deferred": int(metrics.get("stage_replace_deferred", 0)),
        "expected_final_preview": _first_text_preview(result.get("expected_final")),
        "actual_final_preview": _first_text_preview(result.get("actual_final")),
        "actual_staged_preview": _text_preview(result.get("actual_staged")),
        "actual_staged_queue_preview": _first_text_preview(result.get("actual_staged_queue")),
    }


def _active_or_pending_residue_case_sort_key(result: dict[str, Any]) -> tuple[float, float, int, int, int]:
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    metrics = dict(result.get("metrics", {}))
    return (
        -float(final_score.get("f1", 0.0)),
        -float(boundary_score.get("f1", 0.0)),
        len(str(result.get("actual_staged") or "")),
        len(str(result.get("actual_pending") or "")),
        int(metrics.get("stage_age_quality_blocked", 0)) + int(metrics.get("stage_candidate_quality_blocked", 0)),
    )


def _active_or_pending_residue_case_payload(result: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}))
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "active_staged": bool(result.get("actual_staged")),
        "pending": bool(result.get("actual_pending")),
        "final_f1": float(final_score.get("f1", 0.0)),
        "final_boundary_f1": float(boundary_score.get("f1", 0.0)),
        "stage_age_quality_blocked": int(metrics.get("stage_age_quality_blocked", 0)),
        "stage_candidate_quality_blocked": int(metrics.get("stage_candidate_quality_blocked", 0)),
        "stage_revision": int(metrics.get("stage_revision", 0)),
        "stage_replace_deferred": int(metrics.get("stage_replace_deferred", 0)),
        "expected_final_preview": _first_text_preview(result.get("expected_final")),
        "actual_final_preview": _first_text_preview(result.get("actual_final")),
        "actual_staged_preview": _text_preview(result.get("actual_staged")),
        "actual_pending_preview": _text_preview(result.get("actual_pending")),
    }


def summarize_case_exemplars(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact high-bottleneck cases for qualitative paper analysis."""
    lifecycle_candidates = [
        result
        for result in results
        if _has_tag_marker(result, LIFECYCLE_FOCUS_TAG_MARKERS)
        and not _has_tag_marker(result, INPUT_CONTAMINATION_REVIEW_TAG_MARKERS)
    ]
    input_review_candidates = [
        result
        for result in results
        if _has_tag_marker(result, INPUT_CONTAMINATION_REVIEW_TAG_MARKERS)
    ]
    return {
        "selection_rule": (
            "top lifecycle-focus cases by queue/replacement/quality bottleneck score; "
            "input-contamination review cases are listed separately"
        ),
        "metric_keys": list(CASE_EXEMPLAR_METRICS),
        "lifecycle_focus_top": [
            _case_exemplar_payload(result)
            for result in sorted(lifecycle_candidates, key=_case_exemplar_score, reverse=True)[
                :CASE_EXEMPLAR_LIMIT
            ]
        ],
        "input_contamination_review": [
            _case_exemplar_payload(result)
            for result in sorted(input_review_candidates, key=_case_exemplar_score, reverse=True)[
                :CASE_EXEMPLAR_LIMIT
            ]
        ],
    }


def _lifecycle_bottleneck_group_summary(group_results: list[dict[str, Any]]) -> dict[str, Any]:
    metrics_total: dict[str, int] = {}
    for result in group_results:
        for key, value in dict(result.get("metrics", {})).items():
            metrics_total[key] = metrics_total.get(key, 0) + int(value)
    expected_final_count = sum(len(result.get("expected_final", [])) for result in group_results)
    actual_final_count = sum(len(result.get("actual_final", [])) for result in group_results)
    staged_residue_count = sum(
        1
        for result in group_results
        if result.get("actual_staged") or result.get("actual_staged_queue")
    )
    return {
        "case_count": len(group_results),
        "expected_final_count": expected_final_count,
        "actual_final_count": actual_final_count,
        "underfinal_count": sum(
            1
            for result in group_results
            if len(result.get("actual_final", [])) < len(result.get("expected_final", []))
        ),
        "overfinal_count": sum(
            1
            for result in group_results
            if len(result.get("actual_final", [])) > len(result.get("expected_final", []))
        ),
        "zero_actual_final_expected_count": sum(
            1
            for result in group_results
            if result.get("expected_final") and not result.get("actual_final")
        ),
        "pending_residue_count": sum(1 for result in group_results if result.get("actual_pending")),
        "staged_residue_count": staged_residue_count,
        "staged_queue_residue_count": sum(len(result.get("actual_staged_queue", [])) for result in group_results),
        "no_end_marker_count": metrics_total.get("stage_candidate_quality_no_end_marker", 0)
        + metrics_total.get("final_quality_no_end_marker", 0),
        "quality_blocked_count": metrics_total.get("stage_candidate_quality_blocked", 0),
        "replace_deferred_count": metrics_total.get("stage_replace_deferred", 0),
        "queue_revision_count": metrics_total.get("stage_queue_revision", 0),
    }


def summarize_lifecycle_bottlenecks(results: list[dict[str, Any]], metric_totals: dict[str, int]) -> dict[str, Any]:
    """Return structural counters used to interpret finalization failures."""
    language_groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        language_groups.setdefault(str(result.get("language") or "unknown"), []).append(result)
    replacement_decision_counts = {
        key.removeprefix("stage_replace_decision_"): int(value)
        for key, value in sorted(metric_totals.items())
        if key.startswith("stage_replace_decision_") and int(value)
    }
    quality_block_reason_counts = {
        key.removeprefix("stage_candidate_quality_"): int(value)
        for key, value in sorted(metric_totals.items())
        if key.startswith("stage_candidate_quality_")
        and key != "stage_candidate_quality_blocked"
        and int(value)
    }
    metric_keys = _lifecycle_metric_keys(metric_totals)
    return {
        "metric_keys": metric_keys,
        "metrics": {key: int(metric_totals.get(key, 0)) for key in metric_keys},
        "metric_presence_summary": _summarize_metric_presence(results, tuple(metric_keys)),
        "replacement_decision_counts": replacement_decision_counts,
        "deferred_replacement_decision_counts": {
            key: value
            for key, value in replacement_decision_counts.items()
            if key in DEFERRED_REPLACEMENT_REASONS
        },
        "quality_block_reason_counts": quality_block_reason_counts,
        "by_language": {
            language: _lifecycle_bottleneck_group_summary(language_groups[language])
            for language in sorted(language_groups)
        },
    }


def _lifecycle_metric_keys(metric_totals: dict[str, int]) -> list[str]:
    keys = set(LIFECYCLE_BOTTLENECK_METRICS)
    for key, value in metric_totals.items():
        if not int(value):
            continue
        if key.startswith(
            (
                "stage_candidate_quality_",
                "final_quality_",
                "pending_quality_",
                "stage_replace_decision_",
            )
        ):
            keys.add(key)
    return sorted(keys)


def _summarize_metric_presence(results: list[dict[str, Any]], metric_keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    expected_results = [
        result
        for result in results
        if result.get("expected_final") and isinstance(result.get("final_score"), dict)
    ]
    summary: dict[str, dict[str, Any]] = {}
    for key in metric_keys:
        present = [result for result in expected_results if int(dict(result.get("metrics", {})).get(key, 0)) > 0]
        absent = [result for result in expected_results if int(dict(result.get("metrics", {})).get(key, 0)) == 0]
        if not present:
            continue
        present_f1 = _avg_final_f1(present)
        absent_f1 = _avg_final_f1(absent)
        summary[key] = {
            "total_count": int(sum(int(dict(result.get("metrics", {})).get(key, 0)) for result in expected_results)),
            "case_count_present": len(present),
            "case_count_absent": len(absent),
            "final_f1_avg_present": present_f1,
            "final_f1_avg_absent": absent_f1,
            "final_f1_avg_delta_present_minus_absent": present_f1 - absent_f1,
            "low_final_f1_present_count": _low_final_f1_count(present),
            "low_final_f1_absent_count": _low_final_f1_count(absent),
        }
    return summary


def _avg_final_f1(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(float(result["final_score"]["f1"]) for result in results) / len(results)


def _low_final_f1_count(results: list[dict[str, Any]], threshold: float = 0.45) -> int:
    return sum(1 for result in results if float(result["final_score"]["f1"]) < threshold)


def build_benchmark_report(
    *,
    args: argparse.Namespace,
    case_sources: list[str],
    corpus_role: str,
    cases: list[SbdCase],
    results: list[dict[str, Any]],
    metric_totals: dict[str, int],
    elapsed_ms: float,
    representative_review_packet_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results = _with_case_evidence_metadata(results)
    exact_match_count = sum(1 for result in results if result["case_exact_match"])
    pending_exact_count = sum(1 for result in results if result["pending_exact"])
    staged_exact_count = sum(1 for result in results if result["staged_exact"])
    finalized = metric_totals.get("finalized", 0)
    stage_start = metric_totals.get("stage_start", 0)
    final_score_avg = _average_scores(results, "final_score")
    final_ordered_score_avg = _average_scores(results, "final_ordered_score")
    final_boundary_score_avg = _average_scores(results, "final_boundary_score")
    completed_last_score_avg = _average_scores(results, "completed_last_score")
    language_summary = summarize_results_by_language(results)
    tag_summary = summarize_results_by_tag(results)
    evidence_strata_summary = summarize_results_by_evidence_strata(results)
    expected_quality_strata_summary = summarize_results_by_expected_quality_strata(results)
    input_evidence_strata_summary = summarize_results_by_input_evidence_strata(results)
    context_strata_summary = summarize_results_by_context_strata(results)
    case_definition_strata_summary = summarize_results_by_case_definition_strata(results)
    case_definition_action_summary = summarize_case_definition_action_items(results)
    case_definition_cleanup_queue_summary = summarize_case_definition_cleanup_queue(results)
    case_definition_file_summary = summarize_case_definition_files(results)
    collection_strata_summary = summarize_results_by_collection_strata(results)
    source_trace_strata_summary = summarize_results_by_source_trace_strata(results)
    strict_logic_candidate_summary = summarize_strict_logic_candidate_results(cases, results)
    case_definition_health_summary = summarize_case_definition_health(
        results=results,
        case_definition_action_summary=case_definition_action_summary,
        strict_logic_candidate_summary=strict_logic_candidate_summary,
    )
    queue_residue_strata_summary = summarize_results_by_queue_residue_strata(results)
    case_exemplar_summary = summarize_case_exemplars(results)
    lifecycle_bottleneck_summary = summarize_lifecycle_bottlenecks(results, metric_totals)
    staged_queue_residue_summary = summarize_staged_queue_residue(results)
    terminal_expected_residue_summary = summarize_terminal_expected_residue(results)
    missing_expected_without_terminal_residue_summary = summarize_missing_expected_without_terminal_residue(results)
    missing_expected_split_coverage_summary = summarize_missing_expected_split_coverage(results)
    ordered_final_gap_summary = summarize_ordered_final_gap(results)
    boundary_zero_high_final_summary = summarize_boundary_zero_high_final_cases(results)
    boundary_granularity_summary = summarize_boundary_granularity_cases(results)
    expected_final_order_support_summary = summarize_expected_final_order_support(cases)
    expected_order_support_result_summary = summarize_results_by_expected_order_support(cases, results)
    low_score_characteristics_summary = summarize_low_score_characteristics(cases, results)
    supported_low_bottleneck_intersection_summary = summarize_supported_low_bottleneck_intersections(cases, results)
    clean_low_bottleneck_intersection_summary = summarize_clean_low_bottleneck_intersections(cases, results)
    expected_final_case_count = sum(1 for case in cases if case.expected_final)
    case_summary = {
        "case_count": len(results),
        "corpus_role": corpus_role,
        "expected_final_case_count": expected_final_case_count,
        "draft_count": 0,
    }
    if corpus_role == "representative":
        representative_records = [dict(case.metadata or {}) for case in cases]
        case_summary["representative_metadata"] = summarize_representative_metadata(representative_records)
        if representative_review_packet_validation is not None:
            case_summary["representative_review_packet_validation"] = representative_review_packet_validation
    evidence_protocol = build_evidence_protocol(
        case_summary=case_summary,
        corpus_roles=[corpus_role],
        paper_evidence=False,
    )
    report = {
        "backend": SBD_BENCHMARK_BACKEND,
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "case_sources": case_sources,
        "corpus_role": corpus_role,
        "corpus_interpretation": corpus_interpretation(corpus_role),
        "case_summary": case_summary,
        "evidence_protocol": evidence_protocol,
        "dictation_pipeline_policy": dictation_pipeline_policy(),
        "lifecycle_tuning_policy": lifecycle_tuning_policy(),
        "dictation_tuning_protocol": dictation_tuning_protocol(),
        "dictation_tuning_manifest": dictation_tuning_manifest(),
        "revision_similarity_policy": _revision_similarity_policy(),
        "runtime_contract": runtime_contract(),
        "lifecycle_replay_contract": lifecycle_replay_contract(),
        "case_count": len(results),
        "elapsed_ms": round(elapsed_ms, 3),
        "regression_guard": {
            "enabled": bool(getattr(args, "fail_on_regression", False)),
            "min_final_f1": args.min_final_f1,
            "metric": "final_f1_avg",
            "paper_metric": False,
        },
        "summary": {
            "case_exact_match": exact_match_count,
            "pending_exact_match": pending_exact_count,
            "staged_exact_match": staged_exact_count,
            "finalized": finalized,
            "stage_start": stage_start,
            "finalized_per_stage_start": finalized / max(stage_start, 1),
            "final_precision_avg": final_score_avg["precision"],
            "final_recall_avg": final_score_avg["recall"],
            "final_f1_avg": final_score_avg["f1"],
            "final_similarity_coverage_avg": final_score_avg["similarity_coverage"],
            "final_ordered_precision_avg": final_ordered_score_avg["precision"],
            "final_ordered_recall_avg": final_ordered_score_avg["recall"],
            "final_ordered_f1_avg": final_ordered_score_avg["f1"],
            "final_ordered_similarity_coverage_avg": final_ordered_score_avg["similarity_coverage"],
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
        "lifecycle_bottleneck_summary": lifecycle_bottleneck_summary,
        "staged_queue_residue_summary": staged_queue_residue_summary,
        "terminal_expected_residue_summary": terminal_expected_residue_summary,
        "missing_expected_without_terminal_residue_summary": missing_expected_without_terminal_residue_summary,
        "missing_expected_split_coverage_summary": missing_expected_split_coverage_summary,
        "ordered_final_gap_summary": ordered_final_gap_summary,
        "boundary_zero_high_final_summary": boundary_zero_high_final_summary,
        "boundary_granularity_summary": boundary_granularity_summary,
        "expected_final_order_support_summary": expected_final_order_support_summary,
        "expected_order_support_result_summary": expected_order_support_result_summary,
        "low_score_characteristics_summary": low_score_characteristics_summary,
        "supported_low_bottleneck_intersection_summary": supported_low_bottleneck_intersection_summary,
        "clean_low_bottleneck_intersection_summary": clean_low_bottleneck_intersection_summary,
        "queue_residue_strata_summary": queue_residue_strata_summary,
        "evidence_strata_summary": evidence_strata_summary,
        "expected_quality_strata_summary": expected_quality_strata_summary,
        "input_evidence_strata_summary": input_evidence_strata_summary,
        "context_strata_summary": context_strata_summary,
        "case_definition_strata_summary": case_definition_strata_summary,
        "case_definition_action_summary": case_definition_action_summary,
        "case_definition_cleanup_queue_summary": case_definition_cleanup_queue_summary,
        "case_definition_health_summary": case_definition_health_summary,
        "case_definition_file_summary": case_definition_file_summary,
        "collection_strata_summary": collection_strata_summary,
        "source_trace_strata_summary": source_trace_strata_summary,
        "strict_logic_candidate_summary": strict_logic_candidate_summary,
        "case_exemplar_summary": case_exemplar_summary,
        "language_summary": language_summary,
        "tag_summary": tag_summary,
        "metrics": metric_totals,
        "cases": results,
    }
    report["evidence_protocol"]["missing_required_evidence_fields"] = missing_required_evidence_fields(report)
    return report

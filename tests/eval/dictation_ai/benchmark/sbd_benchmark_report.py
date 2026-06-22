from __future__ import annotations

import argparse
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
from src.app.dictation_transcript_logic import _revision_similarity_policy, _word_units
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
from tests.eval.dictation_ai.cases.sbd_input_evidence import case_input_evidence
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
    "stage_finalize_deferred_for_queue_revision",
    "stage_finalize_right_context",
    "stage_age_hold",
    "stage_age_tick",
    "stage_age_finalize",
    "stage_age_quality_blocked",
    "stage_revision_internal_stability_high",
    "stage_revision_internal_stability_mid",
    "stage_revision_internal_stability_low",
    "stage_revision_confirmation_preserved_internal",
    "stage_revision_confirmation_reset",
    "stage_queue_quality_suppressed",
    "stage_candidate_quality_blocked",
    "stage_candidate_quality_no_end_marker",
    "stage_candidate_quality_no_end_marker_with_active_stage",
    "stage_candidate_quality_no_end_marker_with_queue",
    "stage_candidate_quality_no_end_marker_without_blocker",
    "stage_candidate_quality_short_no_end_fragment",
    "stage_candidate_quality_short_no_end_fragment_with_active_stage",
    "stage_candidate_quality_short_no_end_fragment_with_queue",
    "stage_candidate_quality_short_no_end_fragment_without_blocker",
    "stage_candidate_quality_trailing_ellipsis",
    "stage_candidate_quality_trailing_ellipsis_with_active_stage",
    "stage_candidate_quality_trailing_ellipsis_with_queue",
    "stage_candidate_quality_trailing_ellipsis_without_blocker",
    "stage_blocked_short_no_end_aged_active_stage",
    "stage_blocked_short_no_end_active_stage_quality_suppressed",
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
    "finalize_delta_fragment_preserved",
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
    "stage_finalize_deferred_for_queue_revision",
    "stage_revision_internal_stability_high",
    "stage_revision_internal_stability_mid",
    "stage_revision_internal_stability_low",
    "stage_revision_confirmation_preserved_internal",
    "stage_revision_confirmation_reset",
    "stage_queue_quality_suppressed",
    "stage_replace_deferred",
    "stage_age_hold",
    "stage_age_quality_blocked",
    "stage_candidate_quality_blocked",
    "stage_candidate_quality_no_end_marker",
    "stage_candidate_quality_no_end_marker_with_active_stage",
    "stage_candidate_quality_no_end_marker_with_queue",
    "stage_candidate_quality_no_end_marker_without_blocker",
    "stage_candidate_quality_short_no_end_fragment",
    "stage_candidate_quality_short_no_end_fragment_with_active_stage",
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
    "finalize_delta_fragment_preserved",
    "finalize_recent_echo_suppressed",
)
CASE_EXEMPLAR_LIMIT = 8
CASE_EXEMPLAR_PREVIEW_CHARS = 160
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
    "stage_age_quality_blocked",
    "stage_replace_deferred",
    "stage_finalize_deferred_for_queue_revision",
    "stage_finalize_right_context",
    "stage_queue_revision",
    "candidate_recent_final_delta_trimmed",
    "candidate_delta_trimmed",
    "candidate_duplicate_suppressed",
)


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
        return ""
    return "".join(chunk_words[:start]) if any(_is_cjk_word(word) for word in chunk_words) else " ".join(chunk_words[:start])


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
    chunks = [
        str(chunk.get("input", "") if isinstance(chunk, dict) else chunk).strip()
        for chunk in result.get("chunks", [])
        if str(chunk.get("input", "") if isinstance(chunk, dict) else chunk).strip()
    ]
    if not chunks:
        return []
    first_support = _expected_sentence_support(expected_final[0], chunks)
    if not first_support.get("supported"):
        return []
    chunk_index = int(first_support.get("chunk_index", -1))
    if chunk_index < 0 or chunk_index >= len(chunks):
        return []
    prefix = _prefix_before_expected_sentence(chunks[chunk_index], expected_final[0])
    if _has_completed_prefix_context(prefix):
        return ["unmodeled_prefix_context"]
    return []


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
            "Prefer supported_monotonic low cases for app logic tuning; review_needed cases require expected_final/input-order audit first."
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
            if support_by_id.get(str(result.get("id")), "unknown") == "supported_monotonic"
            and result.get("expected_final")
            and isinstance(result.get("final_score"), dict)
            and float(dict(result.get("final_score", {})).get("f1", 0.0)) < threshold
        ]
        thresholds[f"{threshold:.2f}"] = _summarize_supported_low_threshold(low_results, threshold)
    return {
        "interpretation": (
            "These are low-score cases whose expected_final sentences are supported by input chunks in monotonic order. "
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
            if support_by_id.get(str(result.get("id")), "unknown") == "supported_monotonic"
            and result.get("expected_final")
            and isinstance(result.get("final_score"), dict)
            and float(dict(result.get("final_score", {})).get("f1", 0.0)) < threshold
            and not result.get("expected_quality_flags")
            and dict(result.get("input_evidence", {})).get("has_evidence")
        ]
        thresholds[f"{threshold:.2f}"] = _summarize_supported_low_threshold(low_results, threshold)
    return {
        "interpretation": (
            "Clean low-score cases are supported_monotonic, have input evidence, and have no expected_quality_flags. "
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


def _strict_logic_candidate(case: SbdCase, result: dict[str, Any]) -> bool:
    if not result.get("expected_final"):
        return False
    if _expected_final_order_support_kind(case) != "supported_monotonic":
        return False
    if result.get("expected_quality_flags"):
        return False
    if not dict(result.get("input_evidence", {})).get("fully_supported"):
        return False
    if result.get("case_context_flags"):
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
            "Strict logic candidates are supported_monotonic, fully input-supported, have no expected quality flags, "
            "and do not have unmodeled prefix context flags. "
            "Use this subset before changing app logic; other challenge cases may still be valid diagnostics but need review context."
        ),
        "strict_case_count": len(strict),
        "summary": _summarize_result_group(strict),
        "collection_strata": summarize_results_by_collection_strata(strict),
        "low_score_thresholds": low_by_threshold,
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
    for result in results:
        item = dict(result)
        expected_final = [
            str(sentence).strip()
            for sentence in item.get("expected_final", []) or []
            if str(sentence).strip()
        ]
        item["expected_quality_flags"] = expected_quality_flags(expected_final)
        item["input_evidence"] = case_input_evidence(item)
        item["case_context_flags"] = case_context_flags(item)
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
    collection_strata_summary = summarize_results_by_collection_strata(results)
    strict_logic_candidate_summary = summarize_strict_logic_candidate_results(cases, results)
    queue_residue_strata_summary = summarize_results_by_queue_residue_strata(results)
    case_exemplar_summary = summarize_case_exemplars(results)
    lifecycle_bottleneck_summary = summarize_lifecycle_bottlenecks(results, metric_totals)
    staged_queue_residue_summary = summarize_staged_queue_residue(results)
    ordered_final_gap_summary = summarize_ordered_final_gap(results)
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
        "ordered_final_gap_summary": ordered_final_gap_summary,
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
        "collection_strata_summary": collection_strata_summary,
        "strict_logic_candidate_summary": strict_logic_candidate_summary,
        "case_exemplar_summary": case_exemplar_summary,
        "language_summary": language_summary,
        "tag_summary": tag_summary,
        "metrics": metric_totals,
        "cases": results,
    }
    report["evidence_protocol"]["missing_required_evidence_fields"] = missing_required_evidence_fields(report)
    return report

from __future__ import annotations

import argparse
from typing import Any

from src.app.dictation_pipeline_settings import (
    SBD_BENCHMARK_BACKEND,
    dictation_pipeline_policy,
    dictation_tuning_manifest,
    dictation_tuning_protocol,
    lifecycle_tuning_policy,
)
from src.app.dictation_transcript_logic import _revision_similarity_policy
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
    "stage_revision_internal_stability_high",
    "stage_revision_internal_stability_mid",
    "stage_revision_internal_stability_low",
    "stage_revision_confirmation_preserved_internal",
    "stage_revision_confirmation_reset",
    "stage_queue_quality_suppressed",
    "stage_candidate_quality_blocked",
    "stage_candidate_quality_no_end_marker",
    "final_quality_no_end_marker",
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
    "stage_candidate_quality_blocked",
    "stage_candidate_quality_no_end_marker",
    "candidate_delta_trimmed",
    "candidate_delta_trimmed_cjk",
    "candidate_recent_final_delta_trimmed",
    "candidate_duplicate_suppressed",
    "finalize_delta_fragment_preserved",
    "finalize_recent_echo_suppressed",
)
CASE_EXEMPLAR_LIMIT = 8
CASE_EXEMPLAR_PREVIEW_CHARS = 160


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


def _summarize_result_group(group_results: list[dict[str, Any]]) -> dict[str, Any]:
    final_score_avg = _average_scores(group_results, "final_score")
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
    if float(boundary_score.get("f1", 0.0)) == 0.0:
        score += 4.0
    return score


def _case_exemplar_payload(result: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}))
    final_score = dict(result.get("final_score", {}))
    boundary_score = dict(result.get("final_boundary_score", {}))
    return {
        "id": result.get("id"),
        "language": result.get("language"),
        "tags": list(result.get("tags", [])),
        "bottleneck_score": round(_case_exemplar_score(result), 3),
        "final_f1": float(final_score.get("f1", 0.0)),
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
    return {
        "metric_keys": list(LIFECYCLE_BOTTLENECK_METRICS),
        "metrics": {key: int(metric_totals.get(key, 0)) for key in LIFECYCLE_BOTTLENECK_METRICS},
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
    final_boundary_score_avg = _average_scores(results, "final_boundary_score")
    completed_last_score_avg = _average_scores(results, "completed_last_score")
    language_summary = summarize_results_by_language(results)
    tag_summary = summarize_results_by_tag(results)
    evidence_strata_summary = summarize_results_by_evidence_strata(results)
    expected_quality_strata_summary = summarize_results_by_expected_quality_strata(results)
    input_evidence_strata_summary = summarize_results_by_input_evidence_strata(results)
    queue_residue_strata_summary = summarize_results_by_queue_residue_strata(results)
    case_exemplar_summary = summarize_case_exemplars(results)
    lifecycle_bottleneck_summary = summarize_lifecycle_bottlenecks(results, metric_totals)
    staged_queue_residue_summary = summarize_staged_queue_residue(results)
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
        "queue_residue_strata_summary": queue_residue_strata_summary,
        "evidence_strata_summary": evidence_strata_summary,
        "expected_quality_strata_summary": expected_quality_strata_summary,
        "input_evidence_strata_summary": input_evidence_strata_summary,
        "case_exemplar_summary": case_exemplar_summary,
        "language_summary": language_summary,
        "tag_summary": tag_summary,
        "metrics": metric_totals,
        "cases": results,
    }
    report["evidence_protocol"]["missing_required_evidence_fields"] = missing_required_evidence_fields(report)
    return report

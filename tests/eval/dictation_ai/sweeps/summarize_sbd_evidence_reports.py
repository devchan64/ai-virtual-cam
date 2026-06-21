#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.dictation_ai.sweeps.validate_sbd_evidence_report import expand_report_paths, validate_report


AXIS_CONCLUSION_DESCRIPTIONS = {
    "baseline-preferred-tradeoff": "Every candidate is review-risk and none improves final F1; keep the baseline for this axis.",
    "manual-review": "The available evidence does not match an automatic summary class; inspect candidate deltas manually.",
    "minor-no-risk-gain": "A no-risk candidate improves final F1, but the gain is small enough to treat as supporting evidence, not proof of broad optimality.",
    "neutral": "At least one no-risk candidate exists, but the axis does not clearly change the evidence summary.",
    "no-candidate": "The report has no non-baseline parameter candidate.",
    "no-effect-or-tiny": "No review-risk candidate and the observed final/precision/boundary deltas are effectively zero.",
    "tradeoff-gain": "At least one candidate improves final F1, but review-risk flags mean the gain has precision, language, tag, or boundary trade-offs.",
    "tradeoff-or-regression": "Review-risk candidates exist and the axis does not provide a clear final F1 gain.",
}

HYPOTHESIS_STATUS_DESCRIPTIONS = {
    "유지": "The axis has enough evidence to keep the current lifecycle hypothesis within its stated claim scope.",
    "축소": "The axis has useful signal, but trade-offs require narrowing the claim to a failure-mode or condition.",
    "폐기": "The axis does not support a new default or central paper claim for the current corpus.",
    "보류": "The axis needs manual review, representative replay, translation replay, or stronger evidence before a claim is made.",
}

PAPER_CLAIM_DESCRIPTIONS = {
    "partial_final_separation": "Partial STT hypothesis and final transcript must be separated.",
    "layered_finalization_metrics": "SBD candidates and final lifecycle must be evaluated as separate layers.",
    "threshold_optimization_limit": "Single-threshold tuning is not the central improvement path for this corpus.",
    "challenge_replay_baseline": "The current baseline is a reproducible failure-enriched challenge replay baseline.",
    "operating_average_quality": "Operating-average quality improved.",
    "translation_stability": "The final-only sink improved downstream translation stability.",
    "raw_stt_accuracy": "Raw STT backend accuracy improved.",
    "runtime_loop_equivalence": "Text replay is equivalent to the full runtime loop.",
}

BASELINE_METRIC_KEYS = (
    "final_precision_avg",
    "final_recall_avg",
    "final_f1_avg",
    "final_boundary_f1_avg",
    "finalized_per_stage_start",
)

CASE_SET_COUNT_KEYS = (
    "case_count",
    "expected_final_case_count",
    "draft_count",
)


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: report root must be a JSON object")
    return payload


def _fmt(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:+.4f}"
    return ""


def summarize_report(path: Path) -> dict[str, Any]:
    validation = validate_report(path)
    if validation["missing_required_evidence_fields"]:
        raise ValueError(f"{path}: report has missing evidence fields")
    payload = _load_report(path)
    lifecycle_replay_contract = dict(payload.get("lifecycle_replay_contract", {}))
    case_summary = payload.get("case_summary", {})
    if not isinstance(case_summary, dict):
        case_summary = {}
    evidence_summary = dict(payload.get("evidence_summary", {}))
    results = evidence_summary.get("results", [])
    if not isinstance(results, list):
        results = []
    candidates: list[dict[str, Any]] = []
    baseline_metrics: dict[str, float] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("label") == "baseline":
            metrics = result.get("metrics", {})
            if isinstance(metrics, dict):
                baseline_metrics = {
                    key: float(metrics[key])
                    for key in BASELINE_METRIC_KEYS
                    if isinstance(metrics.get(key), (int, float))
                    and not isinstance(metrics.get(key), bool)
                }
            continue
        metric_deltas = dict(result.get("metric_deltas", {}))
        lifecycle_metric_deltas = dict(
            dict(result.get("lifecycle_bottleneck_deltas", {})).get("metrics", {})
        )
        queue_residue_deltas = dict(result.get("staged_queue_residue_deltas", {}))
        clean_lifecycle_deltas = dict(
            dict(result.get("evidence_strata_deltas", {})).get(
                "lifecycle_without_input_review",
                {},
            )
        )
        candidates.append(
            {
                "label": result.get("label", ""),
                "env_overrides": result.get("env_overrides", {}),
                "adoption_review": result.get("adoption_review", ""),
                "interpretation_flags": result.get("interpretation_flags", []),
                "final_f1_delta": metric_deltas.get("final_f1_avg"),
                "precision_delta": metric_deltas.get("final_precision_avg"),
                "recall_delta": metric_deltas.get("final_recall_avg"),
                "boundary_f1_delta": metric_deltas.get("final_boundary_f1_avg"),
                "stage_replace_deferred_delta": lifecycle_metric_deltas.get("stage_replace_deferred"),
                "stage_queue_revision_delta": lifecycle_metric_deltas.get("stage_queue_revision"),
                "queue_residue_total_delta": queue_residue_deltas.get("queue_residue_total"),
                "queue_residue_max_delta": queue_residue_deltas.get("queue_residue_max"),
                "clean_lifecycle_boundary_f1_delta": clean_lifecycle_deltas.get(
                    "final_boundary_f1_avg"
                ),
            }
        )
    return {
        "path": str(path),
        "experiment_stage": validation["experiment_stage"],
        "claim_scope_key": validation["claim_scope_key"],
        "claim_scope": validation["claim_scope"],
        "parameter_axes": validation["parameter_axes"],
        "lifecycle_replay_contract": {
            "state_machine_parity": lifecycle_replay_contract.get("state_machine_parity", ""),
            "runtime_state_owner": lifecycle_replay_contract.get("runtime_state_owner", ""),
            "replay_state_owner": lifecycle_replay_contract.get("replay_state_owner", ""),
            "missing_runtime_signals": lifecycle_replay_contract.get("missing_runtime_signals", []),
        },
        "candidate_count": len(candidates),
        "baseline_metrics": baseline_metrics,
        "case_summary": {
            key: case_summary.get(key)
            for key in CASE_SET_COUNT_KEYS
            if isinstance(case_summary.get(key), int)
            and not isinstance(case_summary.get(key), bool)
        },
        "language_counts": dict(case_summary.get("language_counts", {}))
        if isinstance(case_summary.get("language_counts", {}), dict)
        else {},
        "adoption_review_counts": evidence_summary.get("adoption_review_counts", {}),
        "interpretation_flag_counts": evidence_summary.get("interpretation_flag_counts", {}),
        "candidates": candidates,
    }


def _axis_name(report: dict[str, Any]) -> str:
    return ",".join(str(axis) for axis in report.get("parameter_axes", []))


def _report_richness_score(report: dict[str, Any]) -> tuple[int, int, int, str]:
    candidates = list(report.get("candidates", []))
    lifecycle_delta_count = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in (
            "stage_replace_deferred_delta",
            "stage_queue_revision_delta",
            "queue_residue_total_delta",
            "queue_residue_max_delta",
            "clean_lifecycle_boundary_f1_delta",
        ):
            if candidate.get(key) is not None:
                lifecycle_delta_count += 1
    return (
        lifecycle_delta_count,
        int(report.get("candidate_count", 0)),
        len(dict(report.get("interpretation_flag_counts", {}))),
        str(report.get("path", "")),
    )


def _axis_representative_reports(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for report in reports:
        axis_name = _axis_name(report)
        current = selected.get(axis_name)
        if current is None or _report_richness_score(report) > _report_richness_score(current):
            selected[axis_name] = report
    return [selected[axis] for axis in sorted(selected)]


def _adoption_counts_for_reports(reports: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        report_counts = report.get("adoption_review_counts", {})
        if isinstance(report_counts, dict):
            for key, value in report_counts.items():
                counts[str(key)] = counts.get(str(key), 0) + int(value)
    return dict(sorted(counts.items()))


def _lifecycle_replay_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    parity_counts: dict[str, int] = {}
    runtime_state_owner_counts: dict[str, int] = {}
    replay_state_owner_counts: dict[str, int] = {}
    missing_runtime_signal_counts: dict[str, int] = {}
    for report in reports:
        contract = dict(report.get("lifecycle_replay_contract", {}))
        parity = str(contract.get("state_machine_parity", "") or "unknown")
        parity_counts[parity] = parity_counts.get(parity, 0) + 1
        runtime_owner = str(contract.get("runtime_state_owner", "") or "unknown")
        runtime_state_owner_counts[runtime_owner] = runtime_state_owner_counts.get(runtime_owner, 0) + 1
        replay_owner = str(contract.get("replay_state_owner", "") or "unknown")
        replay_state_owner_counts[replay_owner] = replay_state_owner_counts.get(replay_owner, 0) + 1
        signals = contract.get("missing_runtime_signals", [])
        if not isinstance(signals, list):
            signals = []
        for signal in signals:
            signal_name = str(signal)
            if signal_name:
                missing_runtime_signal_counts[signal_name] = (
                    missing_runtime_signal_counts.get(signal_name, 0) + 1
                )
    return {
        "state_machine_parity_counts": dict(sorted(parity_counts.items())),
        "runtime_state_owner_counts": dict(sorted(runtime_state_owner_counts.items())),
        "replay_state_owner_counts": dict(sorted(replay_state_owner_counts.items())),
        "missing_runtime_signal_counts": dict(sorted(missing_runtime_signal_counts.items())),
    }


def _numeric_candidate_values(candidates: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for candidate in candidates:
        value = candidate.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def _axis_conclusion(report: dict[str, Any]) -> str:
    candidates = [candidate for candidate in report.get("candidates", []) if isinstance(candidate, dict)]
    if not candidates:
        return "no-candidate"
    final_deltas = _numeric_candidate_values(candidates, "final_f1_delta")
    precision_deltas = _numeric_candidate_values(candidates, "precision_delta")
    boundary_deltas = _numeric_candidate_values(candidates, "boundary_f1_delta")
    review_risk_count = sum(1 for candidate in candidates if candidate.get("adoption_review") == "review-risk")
    no_risk_count = sum(1 for candidate in candidates if candidate.get("adoption_review") == "no-risk-flag")
    max_abs_delta = max(
        [abs(value) for value in final_deltas + precision_deltas + boundary_deltas],
        default=0.0,
    )
    max_final_delta = max(final_deltas, default=0.0)
    if review_risk_count == 0 and max_abs_delta < 0.0005:
        return "no-effect-or-tiny"
    if review_risk_count == 0 and max_final_delta > 0.0005:
        return "minor-no-risk-gain"
    if review_risk_count == len(candidates) and max_final_delta <= 0.0:
        return "baseline-preferred-tradeoff"
    if review_risk_count and max_final_delta > 0.0:
        return "tradeoff-gain"
    if review_risk_count:
        return "tradeoff-or-regression"
    if no_risk_count:
        return "neutral"
    return "manual-review"


def _hypothesis_status_for_conclusion(conclusion: str) -> str:
    if conclusion in {"baseline-preferred-tradeoff", "minor-no-risk-gain"}:
        return "유지"
    if conclusion == "tradeoff-gain":
        return "축소"
    if conclusion in {
        "no-effect-or-tiny",
        "tradeoff-or-regression",
    }:
        return "폐기"
    return "보류"


def _axis_conclusion_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        conclusion = _axis_conclusion(report)
        counts[conclusion] = counts.get(conclusion, 0) + 1
    return dict(sorted(counts.items()))


def _hypothesis_status_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        status = _hypothesis_status_for_conclusion(_axis_conclusion(report))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _baseline_metric_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in BASELINE_METRIC_KEYS:
        values: list[float] = []
        for report in reports:
            metrics = report.get("baseline_metrics", {})
            if not isinstance(metrics, dict):
                continue
            value = metrics.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        unique_values = sorted({round(value, 12) for value in values})
        summary[key] = {
            "report_count": len(values),
            "consistent": len(unique_values) <= 1,
            "value": unique_values[0] if len(unique_values) == 1 else None,
            "unique_values": unique_values,
        }
    return summary


def _consistent_int_summary(reports: list[dict[str, Any]], *, source_key: str, value_key: str) -> dict[str, Any]:
    values: list[int] = []
    for report in reports:
        source = report.get(source_key, {})
        if not isinstance(source, dict):
            continue
        value = source.get(value_key)
        if isinstance(value, int) and not isinstance(value, bool):
            values.append(value)
    unique_values = sorted(set(values))
    return {
        "report_count": len(values),
        "consistent": len(unique_values) <= 1,
        "value": unique_values[0] if len(unique_values) == 1 else None,
        "unique_values": unique_values,
    }


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _case_set_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        key: _consistent_int_summary(reports, source_key="case_summary", value_key=key)
        for key in CASE_SET_COUNT_KEYS
    }
    language_keys = sorted(
        {
            str(language)
            for report in reports
            for language in _dict_value(report.get("language_counts", {})).keys()
        }
    )
    summary["language_counts"] = {
        language: _consistent_int_summary(
            [
                {
                    "language_counts": {
                        language: _dict_value(report.get("language_counts", {})).get(language)
                    }
                }
                for report in reports
            ],
            source_key="language_counts",
            value_key=language,
        )
        for language in language_keys
    }
    return summary


def _paper_claim_matrix(
    *,
    report_count: int,
    experiment_stage_counts: dict[str, int],
    claim_scope_key_counts: dict[str, int],
    hypothesis_status_counts: dict[str, int],
    lifecycle_replay_summary: dict[str, Any],
) -> list[dict[str, str]]:
    challenge_reports = int(experiment_stage_counts.get("challenge-replay", 0))
    failure_scope_reports = int(claim_scope_key_counts.get("failure-lifecycle-tradeoff", 0))
    has_challenge_failure_evidence = (
        report_count > 0
        and challenge_reports == report_count
        and failure_scope_reports == report_count
    )
    has_representative = int(experiment_stage_counts.get("representative-replay", 0)) > 0
    has_translation = int(experiment_stage_counts.get("translation-replay", 0)) > 0
    has_classified_parameter_axes = any(
        int(hypothesis_status_counts.get(status, 0)) > 0
        for status in ("유지", "축소", "폐기")
    )
    parity_counts = dict(lifecycle_replay_summary.get("state_machine_parity_counts", {}))
    partial_replay_reports = int(parity_counts.get("partial", 0))
    missing_runtime_signal_counts = dict(
        lifecycle_replay_summary.get("missing_runtime_signal_counts", {})
    )
    has_missing_runtime_signals = bool(missing_runtime_signal_counts)
    runtime_equivalence_blocked = partial_replay_reports > 0 or has_missing_runtime_signals

    return [
        {
            "claim_id": "partial_final_separation",
            "claim": PAPER_CLAIM_DESCRIPTIONS["partial_final_separation"],
            "status": "사용 가능" if has_challenge_failure_evidence else "보류",
            "evidence": "complete challenge-replay failure-lifecycle reports"
            if has_challenge_failure_evidence
            else "missing complete challenge-replay evidence",
            "required_next_evidence": "representative replay confirmation",
        },
        {
            "claim_id": "layered_finalization_metrics",
            "claim": PAPER_CLAIM_DESCRIPTIONS["layered_finalization_metrics"],
            "status": "사용 가능" if has_challenge_failure_evidence else "보류",
            "evidence": "final/boundary/lifecycle/queue metrics in complete reports"
            if has_challenge_failure_evidence
            else "missing complete lifecycle evidence",
            "required_next_evidence": "representative boundary and queue strata",
        },
        {
            "claim_id": "threshold_optimization_limit",
            "claim": PAPER_CLAIM_DESCRIPTIONS["threshold_optimization_limit"],
            "status": "사용 가능" if has_classified_parameter_axes else "보류",
            "evidence": "hypothesis_status_counts classify parameter axes as kept baseline, narrowed, or discarded"
            if has_classified_parameter_axes
            else "no classified parameter axes",
            "required_next_evidence": "structural lifecycle check before reopening narrowed or discarded axes",
        },
        {
            "claim_id": "challenge_replay_baseline",
            "claim": PAPER_CLAIM_DESCRIPTIONS["challenge_replay_baseline"],
            "status": "사용 가능" if has_challenge_failure_evidence else "보류",
            "evidence": "paper-evidence complete reports share challenge-replay/failure-lifecycle scope"
            if has_challenge_failure_evidence
            else "mixed or incomplete evidence scope",
            "required_next_evidence": "rerun after adding new reviewed cases",
        },
        {
            "claim_id": "operating_average_quality",
            "claim": PAPER_CLAIM_DESCRIPTIONS["operating_average_quality"],
            "status": "사용 금지" if not has_representative else "보류",
            "evidence": "no representative replay evidence in this package"
            if not has_representative
            else "representative replay exists but requires separate review",
            "required_next_evidence": "human-reviewed representative cases and validator summary",
        },
        {
            "claim_id": "translation_stability",
            "claim": PAPER_CLAIM_DESCRIPTIONS["translation_stability"],
            "status": "보류",
            "evidence": "no translation replay evidence in this package"
            if not has_translation
            else "translation replay exists but requires separate churn analysis",
            "required_next_evidence": "final event, translation request id, and translation output replay",
        },
        {
            "claim_id": "raw_stt_accuracy",
            "claim": PAPER_CLAIM_DESCRIPTIONS["raw_stt_accuracy"],
            "status": "사용 금지",
            "evidence": "SBD/finalization replay does not evaluate raw STT CER/WER",
            "required_next_evidence": "separate reference transcript and ASR CER/WER evaluation",
        },
        {
            "claim_id": "runtime_loop_equivalence",
            "claim": PAPER_CLAIM_DESCRIPTIONS["runtime_loop_equivalence"],
            "status": "사용 금지" if runtime_equivalence_blocked else "보류",
            "evidence": (
                f"state_machine_parity_counts={parity_counts}; "
                f"missing_runtime_signal_counts={missing_runtime_signal_counts}"
            )
            if runtime_equivalence_blocked
            else "no partial replay marker in this package",
            "required_next_evidence": (
                "end-to-end runtime replay with stable analysis, audio timestamps, "
                "and translation request/output linkage"
            ),
        },
    ]


def _axis_conclusion_descriptions(counts: dict[str, int]) -> dict[str, str]:
    return {
        conclusion: AXIS_CONCLUSION_DESCRIPTIONS.get(conclusion, "")
        for conclusion in sorted(counts)
    }


def _hypothesis_status_descriptions(counts: dict[str, int]) -> dict[str, str]:
    return {
        status: HYPOTHESIS_STATUS_DESCRIPTIONS.get(status, "")
        for status in sorted(counts)
    }


def summarize_reports(paths: list[Path]) -> dict[str, Any]:
    reports = [summarize_report(path) for path in paths]
    report_count = len(reports)
    candidate_count = sum(int(report["candidate_count"]) for report in reports)
    experiment_stage_counts: dict[str, int] = {}
    claim_scope_key_counts: dict[str, int] = {}
    axis_name_counts: dict[str, int] = {}
    for report in reports:
        stage = str(report.get("experiment_stage", "unknown"))
        experiment_stage_counts[stage] = experiment_stage_counts.get(stage, 0) + 1
        claim_scope_key = str(report.get("claim_scope_key", "unknown"))
        claim_scope_key_counts[claim_scope_key] = claim_scope_key_counts.get(claim_scope_key, 0) + 1
        axis_name = _axis_name(report)
        axis_name_counts[axis_name] = axis_name_counts.get(axis_name, 0) + 1
    duplicate_axis_counts = {
        axis: count
        for axis, count in sorted(axis_name_counts.items())
        if count > 1
    }
    axis_representative_reports = _axis_representative_reports(reports)
    axis_conclusion_counts = _axis_conclusion_counts(axis_representative_reports)
    hypothesis_status_counts = _hypothesis_status_counts(axis_representative_reports)
    sorted_experiment_stage_counts = dict(sorted(experiment_stage_counts.items()))
    sorted_claim_scope_key_counts = dict(sorted(claim_scope_key_counts.items()))
    lifecycle_replay_summary = _lifecycle_replay_summary(reports)
    baseline_metric_summary = _baseline_metric_summary(reports)
    case_set_summary = _case_set_summary(reports)
    return {
        "report_count": report_count,
        "unique_axis_count": len(axis_name_counts),
        "candidate_count": candidate_count,
        "unique_axis_candidate_count": sum(
            int(report["candidate_count"]) for report in axis_representative_reports
        ),
        "experiment_stage_counts": sorted_experiment_stage_counts,
        "mixed_experiment_stage": len(experiment_stage_counts) > 1,
        "claim_scope_key_counts": sorted_claim_scope_key_counts,
        "mixed_claim_scope_key": len(claim_scope_key_counts) > 1,
        "axis_name_counts": dict(sorted(axis_name_counts.items())),
        "duplicate_axis_counts": duplicate_axis_counts,
        "adoption_review_counts": _adoption_counts_for_reports(reports),
        "unique_axis_adoption_review_counts": _adoption_counts_for_reports(
            axis_representative_reports
        ),
        "axis_conclusion_counts": axis_conclusion_counts,
        "axis_conclusion_descriptions": _axis_conclusion_descriptions(axis_conclusion_counts),
        "hypothesis_status_counts": hypothesis_status_counts,
        "hypothesis_status_descriptions": _hypothesis_status_descriptions(hypothesis_status_counts),
        "case_set_summary": case_set_summary,
        "baseline_metric_summary": baseline_metric_summary,
        "lifecycle_replay_summary": lifecycle_replay_summary,
        "axis_representative_reports": [
            {
                "axis": _axis_name(report),
                "path": report.get("path"),
                "candidate_count": report.get("candidate_count"),
                "richness_score": list(_report_richness_score(report)[:3]),
                "conclusion": _axis_conclusion(report),
                "hypothesis_status": _hypothesis_status_for_conclusion(_axis_conclusion(report)),
            }
            for report in axis_representative_reports
        ],
        "paper_claim_matrix": _paper_claim_matrix(
            report_count=report_count,
            experiment_stage_counts=sorted_experiment_stage_counts,
            claim_scope_key_counts=sorted_claim_scope_key_counts,
            hypothesis_status_counts=hypothesis_status_counts,
            lifecycle_replay_summary=lifecycle_replay_summary,
        ),
        "reports": reports,
    }


def complete_report_paths(paths: list[Path]) -> list[Path]:
    complete: list[Path] = []
    for path in paths:
        validation = validate_report(path)
        if validation["missing_required_evidence_fields"]:
            continue
        complete.append(path)
    return complete


def render_markdown(summary: dict[str, Any]) -> str:
    lifecycle_replay_summary = dict(summary.get("lifecycle_replay_summary", {}))
    case_set_summary = dict(summary.get("case_set_summary", {}))
    case_language_counts = dict(case_set_summary.get("language_counts", {}))
    lines = [
        "# Dictation AI Complete Evidence Summary",
        "",
        f"- report_count: {summary['report_count']}",
        f"- unique_axis_count: {summary['unique_axis_count']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- unique_axis_candidate_count: {summary['unique_axis_candidate_count']}",
        "- experiment_stage_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["experiment_stage_counts"].items()),
        f"- mixed_experiment_stage: {str(summary.get('mixed_experiment_stage', False)).lower()}",
        "- claim_scope_key_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["claim_scope_key_counts"].items()),
        f"- mixed_claim_scope_key: {str(summary.get('mixed_claim_scope_key', False)).lower()}",
        "- duplicate_axis_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["duplicate_axis_counts"].items()),
        "- adoption_review_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["adoption_review_counts"].items()),
        "- unique_axis_adoption_review_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["unique_axis_adoption_review_counts"].items()),
        "- axis_conclusion_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["axis_conclusion_counts"].items()),
        "- hypothesis_status_counts: "
        + ", ".join(f"{key}={value}" for key, value in summary["hypothesis_status_counts"].items()),
        "- baseline_metric_summary: "
        + ", ".join(
            f"{key}={dict(value).get('value')}"
            for key, value in dict(summary.get("baseline_metric_summary", {})).items()
        ),
        "- case_set_summary: "
        + ", ".join(
            f"{key}={dict(case_set_summary.get(key, {})).get('value')}"
            for key in CASE_SET_COUNT_KEYS
            if key in case_set_summary
        ),
        "- case_language_counts: "
        + ", ".join(
            f"{key}={dict(value).get('value')}"
            for key, value in sorted(case_language_counts.items())
        ),
        "- lifecycle_state_machine_parity_counts: "
        + ", ".join(
            f"{key}={value}"
            for key, value in dict(
                lifecycle_replay_summary.get("state_machine_parity_counts", {})
            ).items()
        ),
        "- lifecycle_runtime_state_owner_counts: "
        + ", ".join(
            f"{key}={value}"
            for key, value in dict(
                lifecycle_replay_summary.get("runtime_state_owner_counts", {})
            ).items()
        ),
        "- lifecycle_replay_state_owner_counts: "
        + ", ".join(
            f"{key}={value}"
            for key, value in dict(
                lifecycle_replay_summary.get("replay_state_owner_counts", {})
            ).items()
        ),
        "- lifecycle_missing_runtime_signal_counts: "
        + ", ".join(
            f"{key}={value}"
            for key, value in dict(
                lifecycle_replay_summary.get("missing_runtime_signal_counts", {})
            ).items()
        ),
        "",
        "## Baseline Metric Summary",
        "",
        "| metric | consistent | report_count | value | unique_values |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for key, value in dict(summary.get("baseline_metric_summary", {})).items():
        item = dict(value)
        lines.append(
            "| "
            + " | ".join(
                [
                    key,
                    str(item.get("consistent", False)).lower(),
                    str(item.get("report_count", "")),
                    str(item.get("value", "")),
                    ", ".join(str(v) for v in item.get("unique_values", [])),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Case Set Summary",
            "",
            "| count | consistent | report_count | value | unique_values |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for key in CASE_SET_COUNT_KEYS:
        value = case_set_summary.get(key, {})
        if not isinstance(value, dict):
            value = {}
        lines.append(
            "| "
            + " | ".join(
                [
                    key,
                    str(value.get("consistent", False)).lower(),
                    str(value.get("report_count", "")),
                    str(value.get("value", "")),
                    ", ".join(str(v) for v in value.get("unique_values", [])),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Case Language Counts",
            "",
            "| language | consistent | report_count | value | unique_values |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for language, value in sorted(case_language_counts.items()):
        if not isinstance(value, dict):
            value = {}
        lines.append(
            "| "
            + " | ".join(
                [
                    language,
                    str(value.get("consistent", False)).lower(),
                    str(value.get("report_count", "")),
                    str(value.get("value", "")),
                    ", ".join(str(v) for v in value.get("unique_values", [])),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Axis Conclusion Legend",
        "",
        "| conclusion | meaning |",
        "| --- | --- |",
        ]
    )
    for conclusion in sorted(summary["axis_conclusion_counts"]):
        lines.append(
            "| "
            + " | ".join(
                [
                    conclusion,
                    AXIS_CONCLUSION_DESCRIPTIONS.get(conclusion, ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Hypothesis Status Legend",
            "",
            "| status | meaning |",
            "| --- | --- |",
        ]
    )
    for status in sorted(summary["hypothesis_status_counts"]):
        lines.append(
            "| "
            + " | ".join(
                [
                    status,
                    HYPOTHESIS_STATUS_DESCRIPTIONS.get(status, ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Paper Claim Matrix",
            "",
            "| claim_id | claim | status | evidence | required_next_evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for claim in summary.get("paper_claim_matrix", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(claim.get("claim_id", "")),
                    str(claim.get("claim", "")),
                    str(claim.get("status", "")),
                    str(claim.get("evidence", "")),
                    str(claim.get("required_next_evidence", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
        "## Representative Axis Reports",
        "",
        "| axis | axis_representative_report | candidate_count | richness_score | conclusion | hypothesis_status |",
        "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for report in summary["axis_representative_reports"]:
        richness_score = ",".join(str(value) for value in report.get("richness_score", []))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(report.get("axis", "")),
                    str(report.get("path", "")),
                    str(report.get("candidate_count", "")),
                    richness_score,
                    str(report.get("conclusion", "")),
                    str(report.get("hypothesis_status", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Candidate Deltas",
            "",
            "| stage | axis | candidate | final_f1_delta | precision_delta | recall_delta | boundary_f1_delta | stage_replace_deferred_delta | stage_queue_revision_delta | queue_residue_total_delta | queue_residue_max_delta | clean_lifecycle_boundary_f1_delta | adoption_review | flags |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for report in summary["reports"]:
        axis = ",".join(report["parameter_axes"])
        for candidate in report["candidates"]:
            flags = ", ".join(str(flag) for flag in candidate.get("interpretation_flags", []))
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(report.get("experiment_stage", "")),
                        axis,
                        str(candidate["label"]),
                        _fmt(candidate.get("final_f1_delta")),
                        _fmt(candidate.get("precision_delta")),
                        _fmt(candidate.get("recall_delta")),
                        _fmt(candidate.get("boundary_f1_delta")),
                        _fmt(candidate.get("stage_replace_deferred_delta")),
                        _fmt(candidate.get("stage_queue_revision_delta")),
                        _fmt(candidate.get("queue_residue_total_delta")),
                        _fmt(candidate.get("queue_residue_max_delta")),
                        _fmt(candidate.get("clean_lifecycle_boundary_f1_delta")),
                        str(candidate.get("adoption_review", "")),
                        flags,
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize complete Dictation AI SBD evidence reports.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument(
        "--complete-only",
        action="store_true",
        help="Skip reports with missing evidence fields instead of failing on mixed historical directories.",
    )
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--markdown-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        paths = expand_report_paths(args.reports)
        if args.complete_only:
            paths = complete_report_paths(paths)
        if not paths:
            raise ValueError("no evidence report files matched")
        summary = summarize_reports(paths)
        if args.summary_output is not None:
            args.summary_output.parent.mkdir(parents=True, exist_ok=True)
            args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.markdown_output is not None:
            args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_output.write_text(render_markdown(summary), encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-evidence-summary] error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

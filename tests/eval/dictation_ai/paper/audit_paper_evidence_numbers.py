#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tests.eval.dictation_ai.paper.audit_evidence_contract import audit_current_evidence_contract


PAPER_BASELINE_METRIC_DECIMALS = {
    "final_precision_avg": 3,
    "final_recall_avg": 3,
    "final_f1_avg": 3,
    "final_boundary_f1_avg": 3,
    "finalized_per_stage_start": 3,
}

PAPER_TOP_LEVEL_COUNTS = (
    "report_count",
    "unique_axis_count",
)

PAPER_CASE_SET_COUNTS = (
    "case_count",
    "expected_final_case_count",
)

PAPER_LANGUAGE_COUNTS = (
    "en",
    "ko",
    "zh",
)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _baseline_metric_summary(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = summary.get("baseline_metric_summary", {})
    if not isinstance(metrics, dict):
        metrics = {}
    if metrics:
        return metrics
    evidence_summary = summary.get("evidence_summary", {})
    if not isinstance(evidence_summary, dict):
        return {}
    results = evidence_summary.get("results", [])
    if not isinstance(results, list):
        return {}
    for result in results:
        if not isinstance(result, dict) or result.get("label") != "baseline":
            continue
        baseline_metrics = result.get("metrics", {})
        if not isinstance(baseline_metrics, dict):
            return {}
        return {
            key: {"consistent": True, "value": value, "unique_values": [value]}
            for key, value in baseline_metrics.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return metrics


def _case_set_summary(summary: dict[str, Any]) -> dict[str, Any]:
    case_summary = summary.get("case_set_summary", {})
    if not isinstance(case_summary, dict):
        case_summary = {}
    if case_summary:
        return case_summary
    source = summary.get("case_summary", {})
    if not isinstance(source, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key in PAPER_CASE_SET_COUNTS:
        value = source.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            normalized[key] = {"consistent": True, "value": value, "unique_values": [value]}
    language_counts = source.get("language_counts", {})
    if isinstance(language_counts, dict):
        normalized["language_counts"] = {
            str(language): {"consistent": True, "value": value, "unique_values": [value]}
            for language, value in language_counts.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    return normalized


def _top_level_count(summary: dict[str, Any], key: str) -> int | None:
    value = summary.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if key == "report_count":
        results = summary.get("results")
        if isinstance(results, list) and results:
            return len(results)
    if key == "unique_axis_count":
        axes = summary.get("parameter_axes")
        if isinstance(axes, list):
            return len(set(str(axis) for axis in axes))
    return None
    return case_summary


def _consistent_int_item(source: dict[str, Any], key: str) -> tuple[int | None, dict[str, Any] | None]:
    item = source.get(key, {})
    if not isinstance(item, dict):
        return None, None
    if not item.get("consistent", False):
        return None, item
    value = item.get("value")
    if isinstance(value, int) and not isinstance(value, bool):
        return value, item
    return None, item


def _audit_expected_text(
    *,
    kind: str,
    name: str,
    value: int,
    paper: str,
) -> dict[str, Any]:
    expected_text = str(value)
    return {
        "kind": kind,
        "name": name,
        "value": value,
        "expected_text": expected_text,
        "matched": expected_text in paper,
    }


def audit_paper_evidence_numbers(summary_path: Path, paper_path: Path) -> dict[str, Any]:
    summary = _load_json_object(summary_path)
    paper = paper_path.read_text(encoding="utf-8")
    evidence_contract = audit_current_evidence_contract(summary)
    baseline_metrics = _baseline_metric_summary(summary)
    case_set_summary = _case_set_summary(summary)
    checked_metrics: list[dict[str, Any]] = []
    missing_metrics: list[dict[str, Any]] = []
    inconsistent_metrics: list[dict[str, Any]] = []
    for metric, decimals in PAPER_BASELINE_METRIC_DECIMALS.items():
        item = baseline_metrics.get(metric, {})
        if not isinstance(item, dict):
            missing_metrics.append(
                {
                    "metric": metric,
                    "reason": "missing baseline_metric_summary entry",
                }
            )
            continue
        if not item.get("consistent", False):
            inconsistent_metrics.append(
                {
                    "metric": metric,
                    "unique_values": item.get("unique_values", []),
                }
            )
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            missing_metrics.append(
                {
                    "metric": metric,
                    "reason": "missing consistent numeric value",
                }
            )
            continue
        expected_text = f"{float(value):.{decimals}f}"
        checked = {
            "metric": metric,
            "value": float(value),
            "expected_text": expected_text,
            "matched": expected_text in paper,
        }
        checked_metrics.append(checked)
        if not checked["matched"]:
            missing_metrics.append(checked)
    checked_counts: list[dict[str, Any]] = []
    missing_counts: list[dict[str, Any]] = []
    inconsistent_counts: list[dict[str, Any]] = []
    for key in PAPER_TOP_LEVEL_COUNTS:
        value = _top_level_count(summary, key)
        if value is None:
            missing_counts.append(
                {
                    "kind": "top_level",
                    "name": key,
                    "reason": "missing integer summary count",
                }
            )
            continue
        checked = _audit_expected_text(kind="top_level", name=key, value=value, paper=paper)
        checked_counts.append(checked)
        if not checked["matched"]:
            missing_counts.append(checked)
    for key in PAPER_CASE_SET_COUNTS:
        value, item = _consistent_int_item(case_set_summary, key)
        if item is None:
            missing_counts.append(
                {
                    "kind": "case_set",
                    "name": key,
                    "reason": "missing case_set_summary entry",
                }
            )
            continue
        if value is None:
            inconsistent_counts.append(
                {
                    "kind": "case_set",
                    "name": key,
                    "unique_values": item.get("unique_values", []),
                }
            )
            continue
        checked = _audit_expected_text(kind="case_set", name=key, value=value, paper=paper)
        checked_counts.append(checked)
        if not checked["matched"]:
            missing_counts.append(checked)
    language_counts = case_set_summary.get("language_counts", {})
    if not isinstance(language_counts, dict):
        language_counts = {}
    for language in PAPER_LANGUAGE_COUNTS:
        value, item = _consistent_int_item(language_counts, language)
        if item is None:
            missing_counts.append(
                {
                    "kind": "language",
                    "name": language,
                    "reason": "missing language count entry",
                }
            )
            continue
        if value is None:
            inconsistent_counts.append(
                {
                    "kind": "language",
                    "name": language,
                    "unique_values": item.get("unique_values", []),
                }
            )
            continue
        checked = _audit_expected_text(kind="language", name=language, value=value, paper=paper)
        checked_counts.append(checked)
        if not checked["matched"]:
            missing_counts.append(checked)
    return {
        "paper": str(paper_path),
        "summary": str(summary_path),
        "checked_metrics": checked_metrics,
        "checked_counts": checked_counts,
        "missing_metrics": missing_metrics,
        "missing_counts": missing_counts,
        "inconsistent_metrics": inconsistent_metrics,
        "inconsistent_counts": inconsistent_counts,
        "evidence_contract": evidence_contract,
        "ok": (
            not missing_metrics
            and not missing_counts
            and not inconsistent_metrics
            and not inconsistent_counts
            and evidence_contract["ok"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit that a paper draft carries baseline metric numbers from the evidence summary.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json"),
        help="Complete paper evidence summary JSON.",
    )
    parser.add_argument(
        "--paper",
        type=Path,
        default=Path("docs/paper/ko-revision-aware-realtime-stt.md"),
        help="Paper draft Markdown to audit.",
    )
    args = parser.parse_args()
    try:
        result = audit_paper_evidence_numbers(args.summary, args.paper)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[dictation-ai-paper-number-audit] error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

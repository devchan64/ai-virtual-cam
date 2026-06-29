#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_REPORT = REPO_ROOT / ".tmp/eval/dictation-ai-sbd/length-strata-baseline.json"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _as_float(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key, 0.0)
    if isinstance(value, bool):
        return 0.0
    return float(value)


def audit_length_strata_hypothesis(
    report_path: Path,
    *,
    max_short_missing_final_rate: float = 0.05,
    min_short_duplicate_suppression_rate: float = 0.90,
    min_short_queue_bypass_rate: float = 0.75,
    min_long_merge_error_rate: float = 0.20,
    min_long_missing_final_rate_delta: float = 0.05,
) -> dict[str, Any]:
    report = _load_json_object(report_path)
    length_summary = dict(report.get("length_strata_summary", {}) or {})
    short_summary = dict(length_summary.get("short_sentences", {}) or {})
    long_summary = dict(length_summary.get("long_sentences", {}) or {})
    all_summary = dict(length_summary.get("all_cases", {}) or {})

    short_missing_final_rate = _as_float(short_summary, "missing_final_rate")
    short_duplicate_suppression_rate = _as_float(short_summary, "duplicate_suppression_rate")
    short_queue_bypass_rate = _as_float(short_summary, "queue_bypass_rate")
    short_merge_error_rate = _as_float(short_summary, "merge_error_rate")
    long_missing_final_rate = _as_float(long_summary, "missing_final_rate")
    long_merge_error_rate = _as_float(long_summary, "merge_error_rate")
    long_queue_bypass_rate = _as_float(long_summary, "queue_bypass_rate")

    checks = [
        {
            "name": "short_missing_final_rate_low",
            "actual": short_missing_final_rate,
            "expected": f"<= {max_short_missing_final_rate:.3f}",
            "passed": short_missing_final_rate <= max_short_missing_final_rate,
        },
        {
            "name": "short_duplicate_suppression_rate_high",
            "actual": short_duplicate_suppression_rate,
            "expected": f">= {min_short_duplicate_suppression_rate:.3f}",
            "passed": short_duplicate_suppression_rate >= min_short_duplicate_suppression_rate,
        },
        {
            "name": "short_queue_bypass_rate_high",
            "actual": short_queue_bypass_rate,
            "expected": f">= {min_short_queue_bypass_rate:.3f}",
            "passed": short_queue_bypass_rate >= min_short_queue_bypass_rate,
        },
        {
            "name": "long_merge_error_rate_high",
            "actual": long_merge_error_rate,
            "expected": f">= {min_long_merge_error_rate:.3f}",
            "passed": long_merge_error_rate >= min_long_merge_error_rate,
        },
        {
            "name": "long_missing_final_rate_exceeds_short",
            "actual": long_missing_final_rate - short_missing_final_rate,
            "expected": f">= {min_long_missing_final_rate_delta:.3f}",
            "passed": (long_missing_final_rate - short_missing_final_rate) >= min_long_missing_final_rate_delta,
        },
        {
            "name": "long_merge_error_rate_exceeds_short",
            "actual": long_merge_error_rate - short_merge_error_rate,
            "expected": "> 0.000",
            "passed": long_merge_error_rate > short_merge_error_rate,
        },
        {
            "name": "short_queue_bypass_rate_exceeds_long",
            "actual": short_queue_bypass_rate - long_queue_bypass_rate,
            "expected": "> 0.000",
            "passed": short_queue_bypass_rate > long_queue_bypass_rate,
        },
    ]

    return {
        "report_path": str(report_path),
        "criteria": {
            "max_short_missing_final_rate": max_short_missing_final_rate,
            "min_short_duplicate_suppression_rate": min_short_duplicate_suppression_rate,
            "min_short_queue_bypass_rate": min_short_queue_bypass_rate,
            "min_long_merge_error_rate": min_long_merge_error_rate,
            "min_long_missing_final_rate_delta": min_long_missing_final_rate_delta,
        },
        "summary": {
            "all_cases": {
                "case_count": int(all_summary.get("case_count", 0)),
                "final_f1_avg": _as_float(all_summary, "final_f1_avg"),
            },
            "short_sentences": {
                "case_count": int(short_summary.get("case_count", 0)),
                "missing_final_rate": short_missing_final_rate,
                "duplicate_suppression_rate": short_duplicate_suppression_rate,
                "queue_bypass_rate": short_queue_bypass_rate,
                "merge_error_rate": short_merge_error_rate,
            },
            "long_sentences": {
                "case_count": int(long_summary.get("case_count", 0)),
                "missing_final_rate": long_missing_final_rate,
                "merge_error_rate": long_merge_error_rate,
                "queue_bypass_rate": long_queue_bypass_rate,
            },
        },
        "checks": checks,
        "hypothesis_supported": all(check["passed"] for check in checks),
        "interpretation": (
            "Short-sentence consumption is treated as supported when missing-final stays low, "
            "duplicate suppression stays high, and queue bypass remains high, while long "
            "sentences retain higher missing-final and merge-error rates."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether a benchmark report supports the short-vs-long length strata hypothesis."
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    result = audit_length_strata_hypothesis(args.report)
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("hypothesis_supported", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

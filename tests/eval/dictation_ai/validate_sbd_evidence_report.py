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

from tests.eval.dictation_ai.sbd_case_paths import build_evidence_protocol, missing_required_evidence_fields


def _report_corpus_roles(payload: dict[str, Any]) -> list[str]:
    roles = payload.get("corpus_roles")
    if isinstance(roles, list) and roles:
        return [str(role) for role in roles if str(role).strip()]
    evidence_protocol = dict(payload.get("evidence_protocol", {}))
    protocol_roles = evidence_protocol.get("corpus_roles")
    if isinstance(protocol_roles, list) and protocol_roles:
        return [str(role) for role in protocol_roles if str(role).strip()]
    role = (
        evidence_protocol.get("corpus_role")
        or dict(payload.get("case_summary", {})).get("corpus_role")
        or payload.get("corpus_role")
        or "exploratory"
    )
    return [str(role)]


def validate_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: report root must be a JSON object")
    evidence_protocol = dict(payload.get("evidence_protocol", {}))
    case_summary = dict(payload.get("case_summary", {}))
    current_protocol = build_evidence_protocol(
        case_summary=case_summary,
        corpus_roles=_report_corpus_roles(payload),
        paper_evidence=bool(evidence_protocol.get("paper_evidence", False)),
    )
    merged_protocol = dict(evidence_protocol)
    merged_protocol["required_evidence_fields"] = current_protocol["required_evidence_fields"]
    current_payload = dict(payload)
    current_payload["evidence_protocol"] = merged_protocol
    missing = missing_required_evidence_fields(current_payload)
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        jobs = []
    return {
        "path": str(path),
        "corpus_role": current_protocol["corpus_role"],
        "experiment_stage": current_protocol["experiment_stage"],
        "claim_scope_key": current_protocol["claim_scope_key"],
        "claim_scope": current_protocol["claim_scope"],
        "paper_evidence": bool(evidence_protocol.get("paper_evidence", False)),
        "parameter_axes": [str(axis) for axis in payload.get("parameter_axes", [])],
        "job_count": len(jobs),
        "job_env_overrides": [
            dict(job.get("env_overrides", {})) for job in jobs if isinstance(job, dict)
        ],
        "missing_required_evidence_fields": missing,
    }


def _count_reports_by_field(reports: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        value = str(report.get(field, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _has_mixed_counts(counts: dict[str, int]) -> bool:
    return len(counts) > 1


def validate_reports(paths: list[Path]) -> dict[str, Any]:
    reports = [validate_report(path) for path in paths]
    missing_reports = [report for report in reports if report["missing_required_evidence_fields"]]
    complete_reports = [report for report in reports if not report["missing_required_evidence_fields"]]
    paper_evidence_complete_reports = [
        report for report in complete_reports if bool(report.get("paper_evidence", False))
    ]
    paper_evidence_rerun_candidates = [
        report
        for report in missing_reports
        if bool(report.get("paper_evidence", False))
    ]
    missing_field_counts: dict[str, int] = {}
    for report in missing_reports:
        for field in report["missing_required_evidence_fields"]:
            missing_field_counts[str(field)] = missing_field_counts.get(str(field), 0) + 1
    experiment_stage_counts = _count_reports_by_field(reports, "experiment_stage")
    claim_scope_key_counts = _count_reports_by_field(reports, "claim_scope_key")
    complete_experiment_stage_counts = _count_reports_by_field(
        complete_reports,
        "experiment_stage",
    )
    complete_claim_scope_key_counts = _count_reports_by_field(
        complete_reports,
        "claim_scope_key",
    )
    return {
        "report_count": len(reports),
        "complete_report_count": len(complete_reports),
        "paper_evidence_complete_report_count": len(paper_evidence_complete_reports),
        "missing_report_count": len(missing_reports),
        "paper_evidence_rerun_candidate_count": len(paper_evidence_rerun_candidates),
        "experiment_stage_counts": experiment_stage_counts,
        "mixed_experiment_stage": _has_mixed_counts(experiment_stage_counts),
        "claim_scope_key_counts": claim_scope_key_counts,
        "mixed_claim_scope_key": _has_mixed_counts(claim_scope_key_counts),
        "complete_experiment_stage_counts": complete_experiment_stage_counts,
        "complete_mixed_experiment_stage": _has_mixed_counts(complete_experiment_stage_counts),
        "complete_claim_scope_key_counts": complete_claim_scope_key_counts,
        "complete_mixed_claim_scope_key": _has_mixed_counts(complete_claim_scope_key_counts),
        "missing_field_counts": dict(sorted(missing_field_counts.items())),
        "complete_reports": complete_reports,
        "paper_evidence_rerun_candidates": paper_evidence_rerun_candidates,
        "reports": reports,
    }


def expand_report_paths(inputs: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in inputs:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("summary.json")))
            expanded.extend(sorted(path.rglob("summary.refreshed.json")))
        else:
            expanded.append(path)
    return sorted(dict.fromkeys(expanded))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dictation AI SBD evidence report context.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Print missing evidence fields without failing. Use only for auditing old reports.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print aggregate counts only.",
    )
    parser.add_argument(
        "--complete-only",
        action="store_true",
        help="Print only reports that satisfy the current required evidence fields.",
    )
    parser.add_argument(
        "--rerun-candidates-only",
        action="store_true",
        help="Print only incomplete reports that were marked as paper evidence.",
    )
    args = parser.parse_args()

    try:
        report_paths = expand_report_paths(args.reports)
        if not report_paths:
            raise ValueError("no evidence report files matched")
        summary = validate_reports(report_paths)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-evidence-validator] error: {exc}", file=sys.stderr)
        return 1
    has_missing_reports = bool(summary["missing_report_count"])
    if args.summary_only:
        summary = {
            "report_count": summary["report_count"],
            "complete_report_count": summary["complete_report_count"],
            "paper_evidence_complete_report_count": summary["paper_evidence_complete_report_count"],
            "paper_evidence_rerun_candidate_count": summary["paper_evidence_rerun_candidate_count"],
            "experiment_stage_counts": summary["experiment_stage_counts"],
            "mixed_experiment_stage": summary["mixed_experiment_stage"],
            "claim_scope_key_counts": summary["claim_scope_key_counts"],
            "mixed_claim_scope_key": summary["mixed_claim_scope_key"],
            "complete_experiment_stage_counts": summary["complete_experiment_stage_counts"],
            "complete_mixed_experiment_stage": summary["complete_mixed_experiment_stage"],
            "complete_claim_scope_key_counts": summary["complete_claim_scope_key_counts"],
            "complete_mixed_claim_scope_key": summary["complete_mixed_claim_scope_key"],
            "missing_report_count": summary["missing_report_count"],
            "missing_field_counts": summary["missing_field_counts"],
        }
    elif args.complete_only:
        summary = {
            "report_count": summary["report_count"],
            "complete_report_count": summary["complete_report_count"],
            "paper_evidence_complete_report_count": summary["paper_evidence_complete_report_count"],
            "experiment_stage_counts": summary["complete_experiment_stage_counts"],
            "mixed_experiment_stage": summary["complete_mixed_experiment_stage"],
            "claim_scope_key_counts": summary["complete_claim_scope_key_counts"],
            "mixed_claim_scope_key": summary["complete_mixed_claim_scope_key"],
            "complete_reports": summary["complete_reports"],
        }
    elif args.rerun_candidates_only:
        summary = {
            "report_count": summary["report_count"],
            "paper_evidence_rerun_candidate_count": summary["paper_evidence_rerun_candidate_count"],
            "paper_evidence_rerun_candidates": summary["paper_evidence_rerun_candidates"],
        }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if has_missing_reports and not args.allow_missing and not args.complete_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

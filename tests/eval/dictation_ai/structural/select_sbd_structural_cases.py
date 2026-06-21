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

from tests.eval.dictation_ai.benchmark.sbd_benchmark_report import (  # noqa: E402
    summarize_case_exemplars,
    summarize_staged_queue_residue,
)
from tests.eval.dictation_ai.cases.sbd_expected_quality import expected_quality_flags  # noqa: E402
from tests.eval.dictation_ai.cases.sbd_input_evidence import (  # noqa: E402
    MIN_INPUT_EVIDENCE_COVERAGE,
    case_input_evidence,
)


DEFAULT_LIMIT = 16
EXPECTED_QUALITY_MODES = ("exclude", "include", "only")
INPUT_EVIDENCE_MODES = ("require", "include", "weak-only")


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: report root must be a JSON object")
    return payload


def _report_cases(report: dict[str, Any], *, path: Path) -> list[dict[str, Any]]:
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: report does not contain benchmark case rows")
    return [case for case in cases if isinstance(case, dict)]


def _case_score(case: dict[str, Any]) -> float:
    metrics = dict(case.get("metrics", {}))
    final_score = dict(case.get("final_score", {}))
    boundary_score = dict(case.get("final_boundary_score", {}))
    expected_final_count = len(case.get("expected_final", []) or [])
    actual_final_count = len(case.get("actual_final", []) or [])
    queue_len = len(case.get("actual_staged_queue", []) or [])
    score = 0.0
    score += min(float(metrics.get("stage_queue_revision", 0)), 80.0) * 0.3
    score += min(float(metrics.get("stage_replace_deferred", 0)), 120.0) * 0.2
    score += min(float(metrics.get("stage_candidate_quality_blocked", 0)), 80.0) * 0.15
    score += min(float(metrics.get("candidate_duplicate_suppressed", 0)), 100.0) * 0.05
    score += min(float(queue_len), 12.0) * 2.0
    if case.get("actual_staged"):
        score += 4.0
    if expected_final_count > actual_final_count:
        score += min(float(expected_final_count - actual_final_count), 8.0) * 1.5
    if expected_final_count and not actual_final_count:
        score += 8.0
    if float(final_score.get("f1", 0.0)) < 0.35:
        score += 4.0
    if float(boundary_score.get("f1", 0.0)) == 0.0:
        score += 5.0
    return score


def _case_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "").strip()


def _case_expected_quality_flags(case: dict[str, Any]) -> list[str]:
    expected_final = [
        str(sentence).strip()
        for sentence in case.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    return expected_quality_flags(expected_final)


def _filter_expected_quality_cases(cases: list[dict[str, Any]], *, mode: str) -> list[dict[str, Any]]:
    if mode not in EXPECTED_QUALITY_MODES:
        raise ValueError(f"unsupported expected quality mode: {mode!r}")
    if mode == "include":
        return cases
    filtered: list[dict[str, Any]] = []
    for case in cases:
        has_flags = bool(_case_expected_quality_flags(case))
        if mode == "exclude" and not has_flags:
            filtered.append(case)
        elif mode == "only" and has_flags:
            filtered.append(case)
    return filtered


def _filter_input_evidence_cases(cases: list[dict[str, Any]], *, mode: str) -> list[dict[str, Any]]:
    if mode not in INPUT_EVIDENCE_MODES:
        raise ValueError(f"unsupported input evidence mode: {mode!r}")
    if mode == "include":
        return cases
    filtered: list[dict[str, Any]] = []
    for case in cases:
        has_evidence = bool(case_input_evidence(case)["has_evidence"])
        if mode == "require" and has_evidence:
            filtered.append(case)
        elif mode == "weak-only" and not has_evidence:
            filtered.append(case)
    return filtered


def _append_unique(
    selected: list[dict[str, Any]],
    seen: set[str],
    candidate: dict[str, Any] | None,
    *,
    reason: str,
) -> None:
    if not candidate:
        return
    case_id = _case_id(candidate)
    if not case_id or case_id in seen:
        return
    item = dict(candidate)
    reasons = list(item.get("selection_reasons", []))
    reasons.append(reason)
    item["selection_reasons"] = reasons
    item["structural_selection_score"] = round(_case_score(candidate), 3)
    item["expected_quality_flags"] = _case_expected_quality_flags(candidate)
    item["input_evidence"] = case_input_evidence(candidate)
    selected.append(item)
    seen.add(case_id)


def select_structural_cases(
    report: dict[str, Any],
    *,
    limit: int = DEFAULT_LIMIT,
    expected_quality_mode: str = "exclude",
    input_evidence_mode: str = "require",
) -> list[dict[str, Any]]:
    cases = _report_cases(report, path=Path("<memory>"))
    cases = _filter_expected_quality_cases(cases, mode=expected_quality_mode)
    cases = _filter_input_evidence_cases(cases, mode=input_evidence_mode)
    by_id = {_case_id(case): case for case in cases if _case_id(case)}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    exemplars = summarize_case_exemplars(cases)
    for item in exemplars.get("lifecycle_focus_top", []):
        _append_unique(selected, seen, by_id.get(_case_id(item)), reason="lifecycle-focus-top")
        if len(selected) >= limit:
            return selected

    queue_summary = summarize_staged_queue_residue(cases)
    for item in queue_summary.get("top_queue_residue_cases", []):
        _append_unique(selected, seen, by_id.get(_case_id(item)), reason="top-queue-residue")
        if len(selected) >= limit:
            return selected

    queue_boundary_cases = sorted(
        (
            case
            for case in cases
            if case.get("actual_staged_queue")
            and float(dict(case.get("final_boundary_score", {})).get("f1", 0.0)) == 0.0
        ),
        key=_case_score,
        reverse=True,
    )
    for case in queue_boundary_cases:
        _append_unique(selected, seen, case, reason="queue-boundary-zero")
        if len(selected) >= limit:
            return selected

    for case in sorted(cases, key=_case_score, reverse=True):
        _append_unique(selected, seen, case, reason="structural-score")
        if len(selected) >= limit:
            return selected
    return selected


def _chunk_inputs(case: dict[str, Any]) -> list[str]:
    chunks = case.get("chunks", [])
    if not isinstance(chunks, list):
        return []
    inputs: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            text = str(chunk.get("input", "")).strip()
        else:
            text = str(chunk).strip()
        if text:
            inputs.append(text)
    return inputs


def _case_payload(case: dict[str, Any]) -> dict[str, Any]:
    tags = [str(tag) for tag in case.get("tags", []) if str(tag).strip()]
    for tag in ("structural-lifecycle", "manual-reviewed"):
        if tag not in tags:
            tags.append(tag)
    return {
        "id": str(case.get("id", "")),
        "language": str(case.get("language", "en")),
        "chunks": _chunk_inputs(case),
        "initial_final": list(case.get("initial_final", []) or []),
        "expected_final": list(case.get("expected_final", []) or []),
        "expected_pending": str(case.get("expected_pending", "") or ""),
        "expected_staged": str(case.get("expected_staged", "") or ""),
        "sentence_finalize_age": int(case.get("sentence_finalize_age", 3) or 3),
        "tags": tags,
    }


def write_case_jsonl(cases: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(_case_payload(case), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def render_markdown(
    cases: list[dict[str, Any]],
    *,
    source_report: str,
    expected_quality_mode: str = "exclude",
    input_evidence_mode: str = "require",
) -> str:
    lines = [
        "# Dictation AI Structural Case Selection",
        "",
        f"- source_report: {source_report}",
        f"- selected_case_count: {len(cases)}",
        f"- expected_quality_mode: {expected_quality_mode}",
        f"- input_evidence_mode: {input_evidence_mode}",
        f"- min_input_evidence_coverage: {MIN_INPUT_EVIDENCE_COVERAGE:.2f}",
        "- corpus_role: exploratory",
        "- paper_evidence: false",
        "- interpretation: structural lifecycle preflight only; expected-quality review candidates and weak input-evidence candidates are excluded by default; rerun the full challenge replay with sat + cuda + float16 before using any metric as paper evidence.",
        "",
        "| rank | id | language | score | reasons | expected_quality_flags | input_evidence | final_f1 | boundary_f1 | queue_len | stage_queue_revision | stage_replace_deferred |",
        "| ---: | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, case in enumerate(cases, start=1):
        metrics = dict(case.get("metrics", {}))
        final_score = dict(case.get("final_score", {}))
        boundary_score = dict(case.get("final_boundary_score", {}))
        quality_flags = ", ".join(str(flag) for flag in case.get("expected_quality_flags", []))
        input_evidence = dict(case.get("input_evidence", {}))
        input_evidence_label = (
            f"{int(input_evidence.get('covered_count', 0))}/"
            f"{int(input_evidence.get('expected_count', 0))} "
            f"{float(input_evidence.get('coverage_avg', 0.0)):.2f}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    str(case.get("id", "")),
                    str(case.get("language", "")),
                    f"{float(case.get('structural_selection_score', 0.0)):.3f}",
                    ", ".join(str(reason) for reason in case.get("selection_reasons", [])),
                    quality_flags,
                    input_evidence_label,
                    f"{float(final_score.get('f1', 0.0)):.3f}",
                    f"{float(boundary_score.get('f1', 0.0)):.3f}",
                    str(len(case.get("actual_staged_queue", []) or [])),
                    str(int(metrics.get("stage_queue_revision", 0))),
                    str(int(metrics.get("stage_replace_deferred", 0))),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select structural lifecycle SBD benchmark cases from a report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--expected-quality",
        choices=EXPECTED_QUALITY_MODES,
        default="exclude",
        help="How to handle expected_final definition review candidates. Default excludes them from structural app-logic preflight.",
    )
    parser.add_argument(
        "--input-evidence",
        choices=INPUT_EVIDENCE_MODES,
        default="require",
        help="How to handle cases where expected_final has weak evidence in replay input chunks.",
    )
    parser.add_argument("--case-output", type=Path, default=None)
    parser.add_argument("--markdown-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        if args.limit <= 0:
            raise ValueError("--limit must be positive")
        report = _load_report(args.report)
        cases = select_structural_cases(
            report,
            limit=args.limit,
            expected_quality_mode=args.expected_quality,
            input_evidence_mode=args.input_evidence,
        )
        if args.case_output is not None:
            write_case_jsonl(cases, args.case_output)
        if args.markdown_output is not None:
            args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_output.write_text(
                render_markdown(
                    cases,
                    source_report=str(args.report),
                    expected_quality_mode=args.expected_quality,
                    input_evidence_mode=args.input_evidence,
                ),
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-structural-selector] error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "source_report": str(args.report),
                "selected_case_count": len(cases),
                "case_ids": [_case_id(case) for case in cases],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

from tests.eval.dictation_ai.benchmark.sbd_benchmark_report import CASE_EXEMPLAR_METRICS  # noqa: E402


DEFAULT_LIMIT = 8


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


def _case_id(case: dict[str, Any]) -> str:
    return str(case.get("id") or "").strip()


def _chunk_input(chunk: dict[str, Any]) -> str:
    return str(chunk.get("input", "")).strip()


def _selected_metric_keys(case: dict[str, Any], extra_metric_keys: list[str]) -> list[str]:
    metrics = dict(case.get("metrics", {}) or {})
    keys: list[str] = []
    for key in (*CASE_EXEMPLAR_METRICS, *extra_metric_keys):
        normalized = str(key).strip()
        if not normalized or normalized in keys:
            continue
        if int(metrics.get(normalized, 0)) > 0:
            keys.append(normalized)
    return keys


def _case_payload(case: dict[str, Any], *, extra_metric_keys: list[str], include_chunks: bool) -> dict[str, Any]:
    metrics = dict(case.get("metrics", {}) or {})
    chunk_rows = [chunk for chunk in case.get("chunks", []) or [] if isinstance(chunk, dict)]
    payload = {
        "id": case.get("id"),
        "language": case.get("language"),
        "tags": list(case.get("tags", []) or []),
        "case_metadata": dict(case.get("case_metadata", {}) or {}),
        "expected_final": list(case.get("expected_final", []) or []),
        "actual_final": list(case.get("actual_final", []) or []),
        "actual_pending": str(case.get("actual_pending") or ""),
        "actual_staged": str(case.get("actual_staged") or ""),
        "actual_staged_queue": list(case.get("actual_staged_queue", []) or []),
        "scores": {
            "final": dict(case.get("final_score", {}) or {}),
            "final_ordered": dict(case.get("final_ordered_score", {}) or {}),
            "final_boundary": dict(case.get("final_boundary_score", {}) or {}),
            "boundary_granularity_adjusted": dict(case.get("boundary_granularity_adjusted_score", {}) or {}),
        },
        "metrics": {key: int(metrics.get(key, 0)) for key in _selected_metric_keys(case, extra_metric_keys)},
        "finalized_events": [
            {
                "chunk_index": int(chunk.get("index", 0)),
                **dict(event),
            }
            for chunk in chunk_rows
            for event in chunk.get("finalized_events", []) or []
            if isinstance(event, dict)
        ],
    }
    if include_chunks:
        payload["chunks"] = [
            {
                "index": int(chunk.get("index", 0)),
                "input": _chunk_input(chunk),
                "completed": list(chunk.get("completed", []) or []),
                "pending": str(chunk.get("pending") or ""),
                "staged": str(chunk.get("staged") or ""),
                "staged_confirmations": int(chunk.get("staged_confirmations", 0)),
                "staged_age": int(chunk.get("staged_age", 0)),
                "finalized": list(chunk.get("finalized", []) or []),
                "finalized_events": list(chunk.get("finalized_events", []) or []),
                "boundary_count": int(chunk.get("boundary_count", 0)),
                "end_mark_count": int(chunk.get("end_mark_count", 0)),
                "right_context_start_count": int(chunk.get("right_context_start_count", 0)),
            }
            for chunk in chunk_rows
        ]
    return payload


def extract_case_lifecycle_traces(
    report: dict[str, Any],
    *,
    case_ids: list[str] | None = None,
    language: str | None = None,
    limit: int = DEFAULT_LIMIT,
    extra_metric_keys: list[str] | None = None,
    include_chunks: bool = True,
) -> dict[str, Any]:
    cases = _report_cases(report, path=Path("<memory>"))
    requested_ids = [str(case_id).strip() for case_id in case_ids or [] if str(case_id).strip()]
    requested_id_set = set(requested_ids)
    normalized_language = str(language or "").strip().lower()
    extra_metrics = [str(key).strip() for key in extra_metric_keys or [] if str(key).strip()]

    if normalized_language:
        cases = [case for case in cases if str(case.get("language") or "").strip().lower() == normalized_language]
    if requested_id_set:
        cases = [case for case in cases if _case_id(case) in requested_id_set]
        cases.sort(
            key=lambda case: (
                requested_ids.index(_case_id(case)) if _case_id(case) in requested_id_set else len(requested_ids),
                _case_id(case),
            )
        )
    else:
        cases = cases[: max(int(limit), 0)]

    return {
        "selected_case_count": len(cases),
        "case_ids": [_case_id(case) for case in cases],
        "cases": [
            _case_payload(case, extra_metric_keys=extra_metrics, include_chunks=include_chunks)
            for case in cases
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract benchmark report lifecycle traces for selected SBD cases.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--case-id", dest="case_ids", action="append", default=[], help="Repeat to select specific case ids.")
    parser.add_argument("--language", default=None, help="Optional language filter when --case-id is omitted.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum cases to return when --case-id is omitted.")
    parser.add_argument(
        "--metric",
        dest="metric_keys",
        action="append",
        default=[],
        help="Additional metric key to include when non-zero.",
    )
    parser.add_argument("--no-chunks", action="store_true", help="Omit per-chunk trace rows and only emit case-level summary.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = _load_report(args.report)
    payload = {
        "source_report": str(args.report),
        **extract_case_lifecycle_traces(
            report,
            case_ids=args.case_ids,
            language=args.language,
            limit=args.limit,
            extra_metric_keys=args.metric_keys,
            include_chunks=not args.no_chunks,
        ),
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

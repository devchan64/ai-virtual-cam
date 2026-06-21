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

from tests.eval.dictation_ai.sweeps.run_sbd_parameter_sweep import SweepJob, build_summary_payload
from tests.eval.dictation_ai.sweeps.sbd_parameter_sweep_report import render_markdown_summary


def _load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: summary root must be a JSON object")
    return payload


def _job_from_payload(summary_path: Path, raw: dict[str, Any]) -> SweepJob:
    output = Path(str(raw.get("output", "")))
    if not output.is_absolute():
        output = (summary_path.parent / output).resolve() if not output.exists() else output
    env_overrides = raw.get("env_overrides", {})
    if not isinstance(env_overrides, dict):
        env_overrides = {}
    command = str(raw.get("command", "")).strip()
    return SweepJob(
        label=str(raw.get("label", output.stem)),
        output=output,
        argv=tuple(command.split()) if command else ("existing-report", str(output)),
        env_overrides={str(key): str(value) for key, value in env_overrides.items()},
    )


def refresh_summary_payload(summary_path: Path, *, paper_evidence: bool = True) -> dict[str, Any]:
    old_summary = _load_summary(summary_path)
    jobs_raw = old_summary.get("jobs", [])
    if not isinstance(jobs_raw, list) or not jobs_raw:
        raise ValueError(f"{summary_path}: summary has no jobs to refresh")
    jobs = [_job_from_payload(summary_path, raw) for raw in jobs_raw if isinstance(raw, dict)]
    if not jobs:
        raise ValueError(f"{summary_path}: summary has no valid jobs to refresh")
    missing_outputs = [str(job.output) for job in jobs if not job.output.exists()]
    if missing_outputs:
        raise ValueError(f"{summary_path}: missing job output files: {', '.join(missing_outputs)}")
    case_summary = old_summary.get("case_summary", {})
    if not isinstance(case_summary, dict):
        case_summary = {}
    return build_summary_payload(
        jobs,
        dry_run=False,
        paper_evidence=paper_evidence,
        case_summary=case_summary,
    )


def expand_summary_paths(inputs: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in inputs:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("summary.json")))
        else:
            expanded.append(path)
    return expanded


def _default_refreshed_summary_path(summary_path: Path) -> Path:
    return summary_path.with_name("summary.refreshed.json")


def _default_refreshed_markdown_path(summary_path: Path) -> Path:
    return summary_path.with_name("summary.refreshed.md")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh an existing Dictation AI SBD parameter sweep summary from saved job reports."
    )
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--markdown-output", type=Path, default=None)
    parser.add_argument(
        "--write-markdown",
        action="store_true",
        help="Write summary.refreshed.md next to each refreshed summary.",
    )
    parser.add_argument(
        "--not-paper-evidence",
        action="store_true",
        help="Refresh as exploratory evidence instead of paper evidence.",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip summaries whose saved benchmark job output files are missing.",
    )
    args = parser.parse_args()

    try:
        summary_paths = expand_summary_paths(args.summaries)
        if not summary_paths:
            raise ValueError("no summary files matched")
        if len(summary_paths) > 1 and (args.output is not None or args.markdown_output is not None):
            raise ValueError("--output and --markdown-output are only valid for a single summary")
        refreshed: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for summary_path in summary_paths:
            try:
                payload = refresh_summary_payload(summary_path, paper_evidence=not args.not_paper_evidence)
            except ValueError as exc:
                if not args.skip_missing:
                    raise
                skipped.append({"input": str(summary_path), "reason": str(exc)})
                continue
            output = args.output or _default_refreshed_summary_path(summary_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            markdown_output = args.markdown_output
            if args.write_markdown and markdown_output is None:
                markdown_output = _default_refreshed_markdown_path(summary_path)
            if markdown_output is not None:
                markdown_output.parent.mkdir(parents=True, exist_ok=True)
                markdown_output.write_text(render_markdown_summary(payload), encoding="utf-8")
            refreshed.append(
                {
                    "input": str(summary_path),
                    "summary": str(output),
                    "markdown": str(markdown_output) if markdown_output is not None else None,
                    "paper_evidence": payload.get("evidence_protocol", {}).get("paper_evidence", False),
                    "missing_required_evidence_fields": payload.get("evidence_protocol", {}).get(
                        "missing_required_evidence_fields", []
                    ),
                }
            )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-refresh-summary] error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "refreshed_count": len(refreshed),
                "skipped_count": len(skipped),
                "refreshed": refreshed,
                "skipped": skipped,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

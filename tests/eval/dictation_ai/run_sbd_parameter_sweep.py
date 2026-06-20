#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.dictation_pipeline_settings import (
    PAPER_EVIDENCE_REVIEWED_FINALIZATION_CASE_TARGET,
    dictation_tuning_manifest,
    dictation_tuning_protocol,
)
from tests.eval.dictation_ai.validate_sbd_case_files import enforce_case_thresholds, validate_case_files


DEFAULT_CASES = (
    Path("tests/eval/dictation_ai/sbd_cases"),
)
DEFAULT_OUTPUT_DIR = Path(".tmp/eval/dictation-ai-sbd/parameter-sweeps")
METRIC_KEYS = (
    "final_precision_avg",
    "final_recall_avg",
    "final_f1_avg",
    "final_boundary_f1_avg",
    "finalized_per_stage_start",
)
LANGUAGE_MARKDOWN_KEYS = (
    "final_precision_avg",
    "final_recall_avg",
    "final_f1_avg",
    "final_boundary_f1_avg",
    "staged_residue_count",
    "empty_final_count",
)


@dataclass(frozen=True)
class SweepParameter:
    name: str
    value: str

    @property
    def env_name(self) -> str:
        return f"AVC_DICTATION_{self.name}"

    @property
    def label(self) -> str:
        safe_value = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.value).strip("_")
        return f"{self.name.lower()}-{safe_value or 'value'}"


@dataclass(frozen=True)
class SweepJob:
    label: str
    output: Path
    argv: tuple[str, ...]
    env_overrides: dict[str, str]


def _allowed_parameter_names() -> set[str]:
    return {str(entry["name"]) for entry in dictation_tuning_manifest()}


def _manifest_by_name() -> dict[str, dict[str, Any]]:
    return {str(entry["name"]): entry for entry in dictation_tuning_manifest()}


def parse_sweep_parameter(raw: str) -> SweepParameter:
    if "=" not in raw:
        raise ValueError(f"sweep parameter must use NAME=VALUE format: {raw!r}")
    name, value = raw.split("=", 1)
    name = name.strip().upper()
    value = value.strip()
    if not name or not value:
        raise ValueError(f"sweep parameter must include both NAME and VALUE: {raw!r}")
    manifest = _manifest_by_name()
    if name not in manifest:
        raise ValueError(
            f"unsupported sweep parameter {name!r}. "
            "Only dictation_tuning_manifest parameters can be swept: " + ", ".join(sorted(manifest))
        )
    value_type = str(manifest[name].get("value_type", ""))
    min_value = manifest[name].get("min_value")
    max_value = manifest[name].get("max_value")
    if value_type == "int":
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError(f"{name} requires an integer value, got {value!r}") from None
        if parsed < 0:
            raise ValueError(f"{name} requires a non-negative integer value, got {value!r}")
        if min_value is not None and parsed < int(min_value):
            raise ValueError(f"{name} must be >= {min_value}, got {value!r}")
        if max_value is not None and parsed > int(max_value):
            raise ValueError(f"{name} must be <= {max_value}, got {value!r}")
    elif value_type == "float":
        try:
            parsed_float = float(value)
        except ValueError:
            raise ValueError(f"{name} requires a float value, got {value!r}") from None
        if not 0.0 <= parsed_float <= 1.0:
            raise ValueError(f"{name} requires a float value between 0.0 and 1.0, got {value!r}")
        if min_value is not None and parsed_float < float(min_value):
            raise ValueError(f"{name} must be >= {min_value}, got {value!r}")
        if max_value is not None and parsed_float > float(max_value):
            raise ValueError(f"{name} must be <= {max_value}, got {value!r}")
    return SweepParameter(name=name, value=value)


def build_sweep_jobs(
    *,
    python: str,
    cases: tuple[Path, ...],
    output_dir: Path,
    parameters: tuple[SweepParameter, ...],
    include_baseline: bool,
) -> list[SweepJob]:
    jobs: list[SweepJob] = []
    benchmark = Path("tests/eval/dictation_ai/sbd_benchmark.py")
    case_args = tuple(str(path) for path in cases)
    base_argv = (
        python,
        str(benchmark),
        "--cases",
        *case_args,
        "--device",
        "cuda",
        "--compute-type",
        "float16",
        "--output",
    )
    if include_baseline:
        output = output_dir / "baseline.json"
        jobs.append(
            SweepJob(
                label="baseline",
                output=output,
                argv=(*base_argv, str(output)),
                env_overrides={},
            )
        )
    for parameter in parameters:
        output = output_dir / f"{parameter.label}.json"
        jobs.append(
            SweepJob(
                label=parameter.label,
                output=output,
                argv=(*base_argv, str(output)),
                env_overrides={parameter.env_name: parameter.value},
            )
        )
    return jobs


def _load_report_summary(job: SweepJob) -> dict[str, Any]:
    report = json.loads(job.output.read_text(encoding="utf-8"))
    summary = report.get("summary", {})
    return {
        "label": job.label,
        "output": str(job.output),
        "case_count": report.get("case_count"),
        "env_overrides": job.env_overrides,
        "metrics": {key: summary.get(key) for key in METRIC_KEYS},
        "language_summary": report.get("language_summary", {}),
    }


def _numeric_delta(current: Any, baseline: Any) -> float | None:
    if isinstance(current, bool) or isinstance(baseline, bool):
        return None
    if not isinstance(current, (int, float)) or not isinstance(baseline, (int, float)):
        return None
    return float(current) - float(baseline)


def _attach_baseline_deltas(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = next((result for result in results if not result.get("env_overrides")), None)
    if baseline is None:
        return results
    baseline_metrics = dict(baseline.get("metrics", {}))
    baseline_languages = dict(baseline.get("language_summary", {}))
    updated: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        metric_deltas: dict[str, float] = {}
        for key, value in dict(result.get("metrics", {})).items():
            delta = _numeric_delta(value, baseline_metrics.get(key))
            if delta is not None:
                metric_deltas[key] = delta
        language_deltas: dict[str, dict[str, float]] = {}
        for language, language_summary in dict(result.get("language_summary", {})).items():
            baseline_summary = baseline_languages.get(language, {})
            if not isinstance(language_summary, dict) or not isinstance(baseline_summary, dict):
                continue
            deltas: dict[str, float] = {}
            for key, value in language_summary.items():
                delta = _numeric_delta(value, baseline_summary.get(key))
                if delta is not None:
                    deltas[key] = delta
            language_deltas[language] = deltas
        item["metric_deltas"] = metric_deltas
        item["language_deltas"] = language_deltas
        updated.append(item)
    return updated


def _format_markdown_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _format_markdown_delta(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    if abs(float(value)) < 0.00005:
        return "+0.0000"
    return f"{float(value):+.4f}"


def render_markdown_summary(payload: dict[str, Any]) -> str:
    lines = [
        "# Dictation AI SBD Parameter Sweep",
        "",
        f"- dry_run: {str(payload.get('dry_run', False)).lower()}",
        f"- jobs: {len(payload.get('jobs', []))}",
        "",
        "## Overall Metrics",
        "",
        "| label | env | " + " | ".join(METRIC_KEYS) + " |",
        "| --- | --- | " + " | ".join("---:" for _ in METRIC_KEYS) + " |",
    ]
    results = list(payload.get("results", []))
    for result in results:
        metrics = dict(result.get("metrics", {}))
        deltas = dict(result.get("metric_deltas", {}))
        env = ", ".join(f"{key}={value}" for key, value in dict(result.get("env_overrides", {})).items()) or "baseline"
        cells = []
        for key in METRIC_KEYS:
            value = _format_markdown_number(metrics.get(key))
            delta = _format_markdown_delta(deltas.get(key))
            cells.append(f"{value} ({delta})" if delta else value)
        lines.append(f"| {result.get('label', '')} | {env} | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Language Metrics",
            "",
            "| label | language | " + " | ".join(LANGUAGE_MARKDOWN_KEYS) + " |",
            "| --- | --- | " + " | ".join("---:" for _ in LANGUAGE_MARKDOWN_KEYS) + " |",
        ]
    )
    for result in results:
        language_summary = dict(result.get("language_summary", {}))
        language_deltas = dict(result.get("language_deltas", {}))
        for language in sorted(language_summary):
            summary = dict(language_summary.get(language, {}))
            deltas = dict(language_deltas.get(language, {}))
            cells = []
            for key in LANGUAGE_MARKDOWN_KEYS:
                value = _format_markdown_number(summary.get(key))
                delta = _format_markdown_delta(deltas.get(key))
                cells.append(f"{value} ({delta})" if delta else value)
            lines.append(f"| {result.get('label', '')} | {language} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def validate_sweep_case_set(
    cases: tuple[Path, ...],
    *,
    paper_evidence: bool,
    min_expected_final_cases: int | None,
) -> dict[str, object]:
    summary = validate_case_files(cases, allow_drafts=False)
    min_expected = min_expected_final_cases
    if paper_evidence and min_expected is None:
        min_expected = PAPER_EVIDENCE_REVIEWED_FINALIZATION_CASE_TARGET
    enforce_case_thresholds(summary, min_expected_final_cases=min_expected, max_drafts=0)
    return summary


def run_job(job: SweepJob, *, dry_run: bool = False) -> None:
    env = os.environ.copy()
    env.update(job.env_overrides)
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(job.env_overrides.items()))
    command = shlex.join(job.argv)
    if prefix:
        command = f"{prefix} {command}"
    print(f"[dictation-ai-sbd-parameter-sweep] {job.label}: {command}", flush=True)
    if dry_run:
        return
    job.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(job.argv, cwd=REPO_ROOT, env=env, check=True)


def build_summary_payload(jobs: list[SweepJob], *, dry_run: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dry_run": dry_run,
        "tuning_protocol": dictation_tuning_protocol(),
        "tuning_manifest": dictation_tuning_manifest(),
        "jobs": [
            {
                "label": job.label,
                "output": str(job.output),
                "command": shlex.join(job.argv),
                "env_overrides": job.env_overrides,
            }
            for job in jobs
        ],
    }
    if not dry_run:
        payload["results"] = _attach_baseline_deltas([_load_report_summary(job) for job in jobs])
    return payload


def write_summary(path: Path, jobs: list[SweepJob], *, dry_run: bool) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_summary_payload(jobs, dry_run=dry_run)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def write_markdown_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_summary(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CUDA/AI SBD benchmark parameter sweeps.")
    parser.add_argument("--cases", nargs="*", type=Path, default=list(DEFAULT_CASES))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_OUTPUT_DIR / "summary.json")
    parser.add_argument("--markdown-output", type=Path, default=None)
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Parameter override in NAME=VALUE format. NAME must exist in dictation_tuning_manifest.",
    )
    parser.add_argument("--include-baseline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--paper-evidence",
        action="store_true",
        help=(
            "Require reviewed expected_final cases to reach the paper evidence target before running. "
            "Use exploratory mode without this flag for early tuning."
        ),
    )
    parser.add_argument(
        "--min-expected-final-cases",
        type=int,
        default=None,
        help="Optional reviewed finalization case threshold. --paper-evidence defaults this to the protocol target.",
    )
    args = parser.parse_args()

    parameters = tuple(parse_sweep_parameter(raw) for raw in args.param)
    if not parameters and not args.include_baseline:
        raise ValueError("at least one --param or --include-baseline is required")
    case_summary = validate_sweep_case_set(
        tuple(args.cases),
        paper_evidence=args.paper_evidence,
        min_expected_final_cases=args.min_expected_final_cases,
    )
    jobs = build_sweep_jobs(
        python=sys.executable,
        cases=tuple(args.cases),
        output_dir=args.output_dir,
        parameters=parameters,
        include_baseline=args.include_baseline,
    )
    for job in jobs:
        run_job(job, dry_run=args.dry_run)
    summary_payload = write_summary(args.summary_output, jobs, dry_run=args.dry_run)
    if args.markdown_output is not None:
        write_markdown_summary(args.markdown_output, summary_payload)
    print(
        "[dictation-ai-sbd-parameter-sweep] "
        f"case_count={case_summary['case_count']} "
        f"expected_final_case_count={case_summary['expected_final_case_count']} "
        f"paper_evidence={args.paper_evidence}",
        flush=True,
    )
    print(f"[dictation-ai-sbd-parameter-sweep] summary={args.summary_output}", flush=True)
    if args.markdown_output is not None:
        print(f"[dictation-ai-sbd-parameter-sweep] markdown={args.markdown_output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

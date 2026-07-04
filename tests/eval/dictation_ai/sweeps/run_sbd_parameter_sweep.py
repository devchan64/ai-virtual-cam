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


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.dictation.pipeline_settings import (
    PAPER_EVIDENCE_REVIEWED_FINALIZATION_CASE_TARGET,
    dictation_tuning_manifest,
    dictation_tuning_protocol,
)
from tests.eval.dictation_ai.cases.sbd_case_paths import (
    SBD_CHALLENGE_CASE_DIR,
    build_evidence_protocol,
    corpus_interpretation,
)
from tests.eval.dictation_ai.sweeps.sbd_parameter_sweep_report import (
    METRIC_KEYS,
    attach_baseline_deltas,
    build_evidence_summary,
    missing_required_evidence_fields,
    render_markdown_summary,
    summarize_case_scores,
)
from tests.eval.dictation_ai.benchmark.sbd_runtime_contract import OFFLINE_MODEL_ENV, lifecycle_replay_contract, runtime_contract
from tests.eval.dictation_ai.cases.validate_sbd_case_files import enforce_case_thresholds, validate_case_files


DEFAULT_CASES: tuple[Path, ...] = (SBD_CHALLENGE_CASE_DIR,)
DEFAULT_OUTPUT_DIR = Path(".tmp/eval/dictation-ai-sbd/parameter-sweeps")
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
        "corpus_role": report.get("corpus_role", "unknown"),
        "case_count": report.get("case_count"),
        "env_overrides": job.env_overrides,
        "metrics": {key: summary.get(key) for key in METRIC_KEYS},
        "language_summary": report.get("language_summary", {}),
        "tag_summary": report.get("tag_summary", {}),
        "lifecycle_bottleneck_summary": report.get("lifecycle_bottleneck_summary", {}),
        "staged_queue_residue_summary": report.get("staged_queue_residue_summary", {}),
        "ordered_final_gap_summary": report.get("ordered_final_gap_summary", {}),
        "expected_final_order_support_summary": report.get("expected_final_order_support_summary", {}),
        "expected_order_support_result_summary": report.get("expected_order_support_result_summary", {}),
        "low_score_characteristics_summary": report.get("low_score_characteristics_summary", {}),
        "clean_low_bottleneck_intersection_summary": report.get("clean_low_bottleneck_intersection_summary", {}),
        "queue_residue_strata_summary": report.get("queue_residue_strata_summary", {}),
        "evidence_strata_summary": report.get("evidence_strata_summary", {}),
        "expected_quality_strata_summary": report.get("expected_quality_strata_summary", {}),
        "input_evidence_strata_summary": report.get("input_evidence_strata_summary", {}),
        "context_strata_summary": report.get("context_strata_summary", {}),
        "collection_strata_summary": report.get("collection_strata_summary", {}),
        "strict_logic_candidate_summary": report.get("strict_logic_candidate_summary", {}),
        "case_exemplar_summary": report.get("case_exemplar_summary", {}),
        "case_score_summary": summarize_case_scores(list(report.get("cases", []))),
    }


def _parameter_axes_from_jobs(jobs: list[SweepJob]) -> list[str]:
    prefix = "AVC_DICTATION_"
    axes: set[str] = set()
    for job in jobs:
        for env_name in job.env_overrides:
            if env_name.startswith(prefix):
                axes.add(env_name[len(prefix) :])
            else:
                axes.add(env_name)
    return sorted(axes)


def validate_sweep_case_set(
    cases: tuple[Path, ...],
    *,
    paper_evidence: bool,
    min_expected_final_cases: int | None,
    review_packets: Path | None = None,
) -> dict[str, object]:
    summary = validate_case_files(cases, allow_drafts=False, review_packets=review_packets)
    corpus_role = str(summary.get("corpus_role", "unknown"))
    if paper_evidence and corpus_role == "exploratory":
        raise ValueError(
            "--paper-evidence requires a challenge-replay or representative corpus; "
            "use exploratory mode without --paper-evidence for ad-hoc case inputs"
        )
    if paper_evidence and corpus_role == "representative" and min_expected_final_cases is None:
        raise ValueError(
            "--paper-evidence with representative corpus requires explicit --min-expected-final-cases; "
            "representative operating sample size is not shared with the challenge-replay target"
        )
    if paper_evidence and corpus_role == "representative" and review_packets is None:
        raise ValueError(
            "--paper-evidence with representative corpus requires --review-packets so source packet traceability "
            "is verified before using the result as paper evidence"
        )
    min_expected = min_expected_final_cases
    if paper_evidence and corpus_role == "challenge-replay" and min_expected is None:
        min_expected = PAPER_EVIDENCE_REVIEWED_FINALIZATION_CASE_TARGET
    enforce_case_thresholds(summary, min_expected_final_cases=min_expected, max_drafts=0)
    return summary


def validate_sweep_execution_contract(
    *,
    paper_evidence: bool,
    include_baseline: bool,
    parameters: tuple[SweepParameter, ...],
) -> None:
    if not paper_evidence:
        return
    if paper_evidence and not include_baseline:
        raise ValueError("--paper-evidence requires --include-baseline so all deltas use the same case set baseline")
    parameter_axes = {parameter.name for parameter in parameters}
    if len(parameter_axes) > 1:
        raise ValueError(
            "--paper-evidence requires one parameter axis per sweep; "
            f"got: {', '.join(sorted(parameter_axes))}"
        )


def run_job(job: SweepJob, *, dry_run: bool = False) -> None:
    env = os.environ.copy()
    env.update(OFFLINE_MODEL_ENV)
    env.update(job.env_overrides)
    command_env = {**OFFLINE_MODEL_ENV, **job.env_overrides}
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(command_env.items()))
    command = shlex.join(job.argv)
    if prefix:
        command = f"{prefix} {command}"
    print(f"[dictation-ai-sbd-parameter-sweep] {job.label}: {command}", flush=True)
    if dry_run:
        return
    job.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(job.argv, cwd=REPO_ROOT, env=env, check=True)


def build_summary_payload(
    jobs: list[SweepJob],
    *,
    dry_run: bool,
    paper_evidence: bool = False,
    case_summary: dict[str, object] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dry_run": dry_run,
        "case_summary": case_summary or {},
        "parameter_axes": _parameter_axes_from_jobs(jobs),
        "runtime_contract": runtime_contract(),
        "lifecycle_replay_contract": lifecycle_replay_contract(),
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
        payload["results"] = attach_baseline_deltas([_load_report_summary(job) for job in jobs])
        payload["evidence_summary"] = build_evidence_summary(payload["results"])
        corpus_roles = sorted({str(result.get("corpus_role", "unknown")) for result in payload["results"]})
        payload["corpus_roles"] = corpus_roles
    else:
        payload["corpus_roles"] = [str((case_summary or {}).get("corpus_role", "unknown"))]
    payload["evidence_protocol"] = build_evidence_protocol(
        case_summary=case_summary,
        corpus_roles=list(payload.get("corpus_roles", [])),
        paper_evidence=paper_evidence and not dry_run,
    )
    payload["evidence_protocol"]["paper_evidence_requested"] = paper_evidence
    payload["evidence_protocol"]["dry_run"] = dry_run
    payload["evidence_protocol"]["missing_required_evidence_fields"] = missing_required_evidence_fields(payload)
    return payload


def write_summary(
    path: Path,
    jobs: list[SweepJob],
    *,
    dry_run: bool,
    paper_evidence: bool = False,
    case_summary: dict[str, object] | None = None,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_summary_payload(
        jobs,
        dry_run=dry_run,
        paper_evidence=paper_evidence,
        case_summary=case_summary,
    )
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
    parser.add_argument(
        "--review-packets",
        type=Path,
        default=None,
        help="For representative paper evidence, validate case review_packet_id/source_log/language links.",
    )
    args = parser.parse_args()

    parameters = tuple(parse_sweep_parameter(raw) for raw in args.param)
    if not parameters and not args.include_baseline:
        raise ValueError("at least one --param or --include-baseline is required")
    validate_sweep_execution_contract(
        paper_evidence=args.paper_evidence,
        include_baseline=args.include_baseline,
        parameters=parameters,
    )
    case_summary = validate_sweep_case_set(
        tuple(args.cases),
        paper_evidence=args.paper_evidence,
        min_expected_final_cases=args.min_expected_final_cases,
        review_packets=args.review_packets,
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
    summary_payload = write_summary(
        args.summary_output,
        jobs,
        dry_run=args.dry_run,
        paper_evidence=args.paper_evidence,
        case_summary=case_summary,
    )
    if args.markdown_output is not None:
        write_markdown_summary(args.markdown_output, summary_payload)
    evidence_protocol = dict(summary_payload.get("evidence_protocol", {}))
    print(
        "[dictation-ai-sbd-parameter-sweep] "
        f"corpus_role={case_summary.get('corpus_role', 'unknown')} "
        f"case_count={case_summary['case_count']} "
        f"expected_final_case_count={case_summary['expected_final_case_count']} "
        f"claim_scope_key={evidence_protocol.get('claim_scope_key', '')} "
        f"paper_evidence_requested={evidence_protocol.get('paper_evidence_requested', args.paper_evidence)} "
        f"paper_evidence={evidence_protocol.get('paper_evidence', False)} "
        f"paper_evidence_eligible={evidence_protocol.get('paper_evidence_eligible', False)}",
        flush=True,
    )
    print(f"[dictation-ai-sbd-parameter-sweep] summary={args.summary_output}", flush=True)
    if args.markdown_output is not None:
        print(f"[dictation-ai-sbd-parameter-sweep] markdown={args.markdown_output}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[dictation-ai-sbd-parameter-sweep] error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        print(
            f"[dictation-ai-sbd-parameter-sweep] error: job failed with exit_code={exc.returncode}: "
            f"{shlex.join(exc.cmd) if isinstance(exc.cmd, (list, tuple)) else exc.cmd}",
            file=sys.stderr,
        )
        raise SystemExit(exc.returncode)

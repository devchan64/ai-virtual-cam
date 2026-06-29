#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.eval.dictation_ai.cases.sbd_case_paths import default_case_inputs

REPO_ROOT = Path(__file__).resolve().parents[4]
BENCHMARK_ENTRYPOINT = REPO_ROOT / "tests/eval/dictation_ai/sbd_benchmark.py"
DEFAULT_OUTPUT = REPO_ROOT / ".tmp/eval/dictation-ai-sbd/paper-baseline-recheck.json"
DEFAULT_REPORT_DIR = REPO_ROOT / ".tmp/eval/dictation-ai-sbd/paper-baseline-recheck"
ROUND_DECIMALS = 3

PAPER_BASELINE_EXPECTATIONS = {
    "case_count": 815,
    "final_precision_avg": 0.614,
    "final_recall_avg": 0.786,
    "final_f1_avg": 0.666,
    "final_boundary_f1_avg": 0.136,
    "strict_final_f1_avg": 0.866,
}


@dataclass(frozen=True)
class BenchmarkVariant:
    label: str
    env_overrides: dict[str, str]


def _git_output(*args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _git_revision_metadata() -> dict[str, Any]:
    head_full = _git_output("rev-parse", "HEAD")
    sample_commit_line = _git_output(
        "log",
        "-1",
        "--format=%H%x09%h%x09%cs%x09%s",
        "--",
        "tests/eval/dictation_ai/sbd_predicted_cases",
    )
    sample_basis: dict[str, str] | None = None
    if sample_commit_line:
        full_hash, short_hash, committed_at, subject = sample_commit_line.split("\t", 3)
        sample_basis = {
            "full_hash": full_hash,
            "short_hash": short_hash,
            "committed_at": committed_at,
            "subject": subject,
            "path": "tests/eval/dictation_ai/sbd_predicted_cases",
        }
    return {
        "worktree_head_full_hash": head_full,
        "worktree_head_short_hash": head_full[:7] if head_full else None,
        "sample_basis_commit": sample_basis,
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _normalize_env_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("variant env name must not be empty")
    if normalized.startswith("AVC_DICTATION_"):
        return normalized
    return f"AVC_DICTATION_{normalized}"


def parse_variant_spec(spec: str) -> BenchmarkVariant:
    label, sep, env_blob = spec.partition(":")
    if not sep or not label.strip() or not env_blob.strip():
        raise ValueError(
            "variant spec must be '<label>:<NAME=VALUE>[,<NAME=VALUE>...]'"
        )
    env_overrides: dict[str, str] = {}
    for entry in env_blob.split(","):
        name, eq, value = entry.partition("=")
        if not eq:
            raise ValueError(f"invalid variant env override: {entry!r}")
        env_name = _normalize_env_name(name)
        env_overrides[env_name] = value.strip()
    return BenchmarkVariant(label=label.strip(), env_overrides=env_overrides)


def _metric_snapshot(report: dict[str, Any]) -> dict[str, float | int]:
    summary = dict(report.get("summary", {}) or {})
    strict_summary = dict(dict(report.get("strict_logic_candidate_summary", {}) or {}).get("summary", {}) or {})
    return {
        "case_count": int(report.get("case_count", 0) or 0),
        "final_precision_avg": float(summary.get("final_precision_avg", 0.0) or 0.0),
        "final_recall_avg": float(summary.get("final_recall_avg", 0.0) or 0.0),
        "final_f1_avg": float(summary.get("final_f1_avg", 0.0) or 0.0),
        "final_boundary_f1_avg": float(summary.get("final_boundary_f1_avg", 0.0) or 0.0),
        "strict_final_f1_avg": float(strict_summary.get("final_f1_avg", 0.0) or 0.0),
    }


def _audit_paper_baseline(metrics: dict[str, float | int]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for key, expected in PAPER_BASELINE_EXPECTATIONS.items():
        actual = metrics[key]
        if isinstance(expected, int):
            matched = int(actual) == expected
            rendered_actual = int(actual)
            rendered_expected = expected
        else:
            rendered_actual = round(float(actual), ROUND_DECIMALS)
            rendered_expected = round(float(expected), ROUND_DECIMALS)
            matched = rendered_actual == rendered_expected
        checks.append(
            {
                "metric": key,
                "actual": rendered_actual,
                "expected": rendered_expected,
                "matched": matched,
            }
        )
    return checks


def _run_benchmark(
    *,
    label: str,
    cases: list[Path],
    report_dir: Path,
    model: str,
    device: str,
    compute_type: str,
    env_overrides: dict[str, str],
) -> dict[str, Any]:
    report_path = report_dir / f"{label}.json"
    command = [
        sys.executable,
        str(BENCHMARK_ENTRYPOINT),
        "--cases",
        *[str(case) for case in cases],
        "--model",
        model,
        "--device",
        device,
        "--compute-type",
        compute_type,
        "--output",
        str(report_path),
    ]
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env.update(env_overrides)
    subprocess.run(command, check=True, cwd=REPO_ROOT, env=env)
    report = _load_json_object(report_path)
    return {
        "label": label,
        "report_path": str(report_path),
        "command": command,
        "env_overrides": env_overrides,
        "metrics": _metric_snapshot(report),
    }


def _variant_delta(
    baseline_metrics: dict[str, float | int],
    variant_metrics: dict[str, float | int],
) -> dict[str, float | int]:
    delta: dict[str, float | int] = {}
    for key, baseline_value in baseline_metrics.items():
        variant_value = variant_metrics[key]
        if isinstance(baseline_value, int):
            delta[key] = int(variant_value) - int(baseline_value)
        else:
            delta[key] = round(float(variant_value) - float(baseline_value), 6)
    return delta


def recheck_paper_challenge_baseline(
    *,
    cases: list[Path],
    output_path: Path,
    report_dir: Path,
    model: str,
    device: str,
    compute_type: str,
    variants: list[BenchmarkVariant],
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    baseline_run = _run_benchmark(
        label="baseline",
        cases=cases,
        report_dir=report_dir,
        model=model,
        device=device,
        compute_type=compute_type,
        env_overrides={},
    )
    baseline_checks = _audit_paper_baseline(dict(baseline_run["metrics"]))
    comparison_runs: list[dict[str, Any]] = []
    for variant in variants:
        variant_run = _run_benchmark(
            label=variant.label,
            cases=cases,
            report_dir=report_dir,
            model=model,
            device=device,
            compute_type=compute_type,
            env_overrides=variant.env_overrides,
        )
        variant_run["delta_vs_baseline"] = _variant_delta(
            dict(baseline_run["metrics"]),
            dict(variant_run["metrics"]),
        )
        comparison_runs.append(variant_run)
    payload = {
        "cases": [str(case) for case in cases],
        "model": model,
        "device": device,
        "compute_type": compute_type,
        "git_revision_metadata": _git_revision_metadata(),
        "baseline": baseline_run,
        "baseline_paper_checks": baseline_checks,
        "comparisons": comparison_runs,
        "all_baseline_checks_matched": all(check["matched"] for check in baseline_checks),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rerun the reviewed challenge replay corpus on sat+cuda+float16 and "
            "recheck the paper baseline metrics with optional comparison variants."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        nargs="+",
        default=default_case_inputs(),
        help="Challenge replay inputs. Defaults to reviewed sbd_predicted_cases.",
    )
    parser.add_argument("--model", default="sat-3l-sm")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--compare",
        action="append",
        default=[],
        help=(
            "Comparison variant in the form "
            "'label:NAME=VALUE[,OTHER_NAME=VALUE]'. Names are mapped to AVC_DICTATION_*."
        ),
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    variants = [parse_variant_spec(spec) for spec in args.compare]
    payload = recheck_paper_challenge_baseline(
        cases=list(args.cases),
        output_path=args.output,
        report_dir=args.report_dir,
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        variants=variants,
    )
    baseline = dict(payload["baseline"])
    metrics = dict(baseline["metrics"])
    revision = dict(payload.get("git_revision_metadata", {}) or {})
    sample_basis = dict(revision.get("sample_basis_commit", {}) or {})
    print(
        "[dictation-ai-paper-baseline-recheck] "
        f"worktree_head={revision.get('worktree_head_short_hash')} "
        f"sample_basis={sample_basis.get('short_hash')} "
        f"case_count={metrics['case_count']} "
        f"final_precision_avg={metrics['final_precision_avg']:.3f} "
        f"final_recall_avg={metrics['final_recall_avg']:.3f} "
        f"final_f1_avg={metrics['final_f1_avg']:.3f} "
        f"strict_final_f1_avg={metrics['strict_final_f1_avg']:.3f} "
        f"final_boundary_f1_avg={metrics['final_boundary_f1_avg']:.3f} "
        f"baseline_checks_matched={payload['all_baseline_checks_matched']} "
        f"comparisons={len(payload['comparisons'])} "
        f"output={args.output}"
    )
    return 0 if payload["all_baseline_checks_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

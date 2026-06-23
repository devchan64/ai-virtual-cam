#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.sentence_boundary import create_sentence_boundary_detector, normalized_text
from src.app.dictation_pipeline_settings import (
    FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
    SBD_BENCHMARK_BACKEND,
    SBD_BENCHMARK_COMPUTE_TYPE,
    SBD_BENCHMARK_DEVICE,
    SBD_BENCHMARK_MODEL,
)
from src.app.dictation_transcript_logic import _word_units
from tests.eval.dictation_ai.cases.sbd_case_paths import (
    case_corpus_role as _case_corpus_role,
    default_case_inputs as _default_case_inputs,
)
from tests.eval.dictation_ai.cases.sbd_case_loader import SbdCase, load_cases as _load_cases
from tests.eval.dictation_ai.benchmark.sbd_benchmark_report import build_benchmark_report
from tests.eval.dictation_ai.benchmark.sbd_lifecycle_replay import (
    LifecycleState,
    _finalize_staged_sentence,
    _run_lifecycle_case,
    _score_boundary_offsets,
    _score_ordered_sequence,
    _score_sequence,
    _stage_completed_sentence,
)
from tests.eval.dictation_ai.benchmark.sbd_runtime_contract import force_offline_model_cache_env
from tests.eval.dictation_ai.cases.validate_sbd_case_files import validate_case_files

_SUBCOMMANDS: dict[str, str] = {
    "validate-cases": "tests.eval.dictation_ai.cases.validate_sbd_case_files:main",
    "audit-initial-final-context": "tests.eval.dictation_ai.cases.audit_sbd_initial_final_context:main",
    "run-sweep": "tests.eval.dictation_ai.sweeps.run_sbd_parameter_sweep:main",
    "refresh-sweep": "tests.eval.dictation_ai.sweeps.refresh_sbd_parameter_sweep_summary:main",
    "summarize-evidence": "tests.eval.dictation_ai.sweeps.summarize_sbd_evidence_reports:main",
    "validate-evidence": "tests.eval.dictation_ai.sweeps.validate_sbd_evidence_report:main",
    "paper-claim-scope": "tests.eval.dictation_ai.paper.audit_paper_claim_scope:main",
    "paper-evidence-numbers": "tests.eval.dictation_ai.paper.audit_paper_evidence_numbers:main",
    "paper-readiness": "tests.eval.dictation_ai.paper.audit_paper_readiness:main",
    "paper-reference-scope": "tests.eval.dictation_ai.paper.audit_paper_reference_scope:main",
    "followup-readiness": "tests.eval.dictation_ai.paper.audit_sbd_followup_readiness:main",
    "representative-sources": "tests.eval.dictation_ai.representative.audit_sbd_representative_sources:main",
    "select-representative-sources": "tests.eval.dictation_ai.representative.select_sbd_representative_sources:main",
    "extract-review-packets": "tests.eval.dictation_ai.representative.extract_sbd_representative_review_packets:main",
    "validate-review-packets": "tests.eval.dictation_ai.representative.validate_sbd_representative_review_packets:main",
    "extract-representative-drafts": "tests.eval.dictation_ai.representative.extract_sbd_representative_case_drafts:main",
    "promote-representative-cases": "tests.eval.dictation_ai.representative.promote_sbd_representative_cases:main",
    "select-structural-cases": "tests.eval.dictation_ai.structural.select_sbd_structural_cases:main",
}


def _print_subcommands() -> None:
    print("usage: sbd_benchmark.py [benchmark options] | <subcommand> [options]\n")
    print("subcommands:")
    for name in sorted(_SUBCOMMANDS):
        print(f"  {name}")


def _dispatch_subcommand() -> int | None:
    if len(sys.argv) < 2:
        return None
    subcommand = sys.argv[1]
    if subcommand in {"commands", "subcommands"}:
        _print_subcommands()
        return 0
    target = _SUBCOMMANDS.get(subcommand)
    if target is None:
        return None

    module_name, function_name = target.split(":", 1)
    original_argv = sys.argv[:]
    try:
        sys.argv = [f"{Path(original_argv[0]).name} {subcommand}", *original_argv[2:]]
        module = importlib.import_module(module_name)
        return int(getattr(module, function_name)())
    finally:
        sys.argv = original_argv

def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_real_ai_cuda_args(args: argparse.Namespace) -> None:
    device = str(args.device or "").strip().lower()
    compute_type = str(args.compute_type or "").strip().lower()
    if device != "cuda":
        raise ValueError(
            "Dictation AI SBD benchmark must run on CUDA: "
            f"--device=cuda required, got {args.device!r}. CPU benchmarks are not valid performance data."
        )
    if compute_type != "float16":
        raise ValueError(
            "Dictation AI SBD benchmark must use the production CUDA precision: "
            f"--compute-type=float16 required, got {args.compute_type!r}."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run text-only Dictation AI SBD lifecycle benchmark cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        nargs="+",
        default=_default_case_inputs(),
        help=(
            "One or more JSONL files, directories containing JSONL files, or glob patterns. "
            "By default, reviewed challenge sbd_cases/{en,ko,zh}/*.jsonl files are loaded."
        ),
    )
    parser.add_argument("--model", default=SBD_BENCHMARK_MODEL)
    parser.add_argument("--device", default=SBD_BENCHMARK_DEVICE)
    parser.add_argument("--compute-type", default=SBD_BENCHMARK_COMPUTE_TYPE)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".tmp/eval/dictation-ai-sbd/latest.json")
    parser.add_argument(
        "--review-packets",
        type=Path,
        default=None,
        help="For representative cases, validate review_packet_id/source_log/language links before writing the report.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Optional local guard: exit non-zero when final F1 average is below --min-final-f1.",
    )
    parser.add_argument("--min-final-f1", type=float, default=0.0)
    parser.add_argument("--min-pass-rate", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    _validate_real_ai_cuda_args(args)
    force_offline_model_cache_env()

    corpus_role = _case_corpus_role(args.cases)
    case_validation_summary = (
        validate_case_files(args.cases, review_packets=args.review_packets) if args.review_packets is not None else None
    )
    cases, case_sources = _load_cases(args.cases)
    detector = create_sentence_boundary_detector(
        SBD_BENCHMARK_BACKEND,
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
    )

    results: list[dict[str, Any]] = []
    metric_totals: dict[str, int] = {}
    started = time.perf_counter()
    for case in cases:
        case_started = time.perf_counter()
        lifecycle = _run_lifecycle_case(case, detector)
        elapsed_ms = (time.perf_counter() - case_started) * 1000.0
        final_score = _score_sequence(case.expected_final, lifecycle["actual_final"])
        final_ordered_score = _score_ordered_sequence(case.expected_final, lifecycle["actual_final"])
        final_boundary_score = _score_boundary_offsets(case.expected_final, lifecycle["actual_final"])
        completed_score = _score_sequence(case.expected_completed, lifecycle["actual_completed_last"])
        pending_exact = lifecycle["actual_pending"] == case.expected_pending
        staged_exact = lifecycle["actual_staged"] == case.expected_staged
        case_exact_match = final_score["exact"] and pending_exact and staged_exact
        for key, value in lifecycle["metrics"].items():
            metric_totals[key] = metric_totals.get(key, 0) + int(value)
        results.append(
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "case_metadata": dict(case.metadata or {}),
                "elapsed_ms": round(elapsed_ms, 3),
                "expected_final": case.expected_final,
                "initial_final": list(case.initial_final),
                "actual_final": lifecycle["actual_final"],
                "expected_pending": case.expected_pending,
                "actual_pending": lifecycle["actual_pending"],
                "expected_staged": case.expected_staged,
                "actual_staged": lifecycle["actual_staged"],
                "actual_staged_queue": lifecycle["actual_staged_queue"],
                "final_score": final_score,
                "final_ordered_score": final_ordered_score,
                "final_boundary_score": final_boundary_score,
                "completed_last_score": completed_score,
                "pending_exact": pending_exact,
                "staged_exact": staged_exact,
                "case_exact_match": case_exact_match,
                "metrics": lifecycle["metrics"],
                "chunks": lifecycle["chunks"],
            }
        )

    report = build_benchmark_report(
        args=args,
        case_sources=case_sources,
        corpus_role=corpus_role,
        cases=cases,
        results=results,
        metric_totals=metric_totals,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
        representative_review_packet_validation=(
            dict(case_validation_summary.get("representative_review_packet_validation", {}))
            if case_validation_summary is not None
            else None
        ),
    )
    summary = dict(report["summary"])
    evidence_protocol = dict(report.get("evidence_protocol", {}))
    case_definition_actions = dict(report.get("case_definition_action_summary", {}))
    case_definition_health = dict(report.get("case_definition_health_summary", {}))
    strict_logic_summary = dict(report.get("strict_logic_candidate_summary", {}))
    strict_summary = dict(strict_logic_summary.get("summary", {}))
    _write_report(args.output, report)
    print(
        "[dictation-ai-sbd-benchmark] "
        f"corpus_role={corpus_role} cases={len(results)} finalized={summary['finalized']} "
        f"claim_scope_key={evidence_protocol.get('claim_scope_key', '')} "
        f"case_definition_review={case_definition_actions.get('review_case_count', 0)} "
        f"case_definition_cleanup={case_definition_actions.get('case_definition_cleanup_count', 0)} "
        f"case_interpretation_review={case_definition_actions.get('case_interpretation_review_count', 0)} "
        f"case_definition_review_ratio={float(case_definition_health.get('case_definition_review_ratio', 0.0)):.3f} "
        f"logic_tuning_candidates={case_definition_actions.get('logic_tuning_candidate_count', 0)} "
        f"strict_logic_candidates={strict_logic_summary.get('strict_case_count', 0)} "
        f"stage_start={summary['stage_start']} "
        f"finalized_per_stage_start={summary['finalized_per_stage_start']:.3f} "
        f"final_precision_avg={summary['final_precision_avg']:.3f} "
        f"final_recall_avg={summary['final_recall_avg']:.3f} "
        f"final_f1_avg={summary['final_f1_avg']:.3f} "
        f"strict_final_f1_avg={float(strict_summary.get('final_f1_avg', 0.0)):.3f} "
        f"final_similarity_coverage_avg={summary['final_similarity_coverage_avg']:.3f} "
        f"final_boundary_f1_avg={summary['final_boundary_f1_avg']:.3f} "
        f"case_exact_match={summary['case_exact_match']} "
        f"pending_exact_match={summary['pending_exact_match']} "
        f"staged_exact_match={summary['staged_exact_match']} "
        f"output={args.output}"
    )
    if args.fail_on_regression and summary["final_f1_avg"] < args.min_final_f1:
        return 1
    return 0


def cli_main() -> int:
    subcommand_result = _dispatch_subcommand()
    if subcommand_result is not None:
        return subcommand_result
    try:
        return main()
    except (ValueError, RuntimeError) as exc:
        print(f"[dictation-ai-sbd-benchmark] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli_main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.sentence_boundary import create_sentence_boundary_detector, normalized_text
from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _prefer_sentence_revision,
    _replacement_decision_reason,
    _sentence_max_age_chunks,
    _sentence_output_delta,
    _sentence_required_confirmations,
    _sentences_are_revisions,
    _should_age_staged_sentence,
    _should_confirm_staged_sentence,
    _should_finalize_before_replacement,
    _should_finalize_replaced_sentence,
    _should_stage_boundary_candidate,
)
from src.app.transcript_revision import append_context as _append_committed_text
from src.app.transcript_revision import consume_committed_prefix as _consume_committed_prefix


@dataclass(frozen=True)
class SbdCase:
    id: str
    language: str
    chunks: list[str]
    expected_completed: list[str]
    expected_pending: str
    expected_final: list[str]
    expected_staged: str
    tags: tuple[str, ...]
    sentence_finalize_age: int


@dataclass
class LifecycleState:
    committed_text: str = ""
    pending_text: str = ""
    pending_chunks: int = 0
    staged_sentence: str = ""
    staged_confirmations: int = 0
    staged_age: int = 0
    staged_forced: bool = False
    staged_deferred_age_chunk: int = -1
    final_sentences: list[str] | None = None
    metrics: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.final_sentences is None:
            self.final_sentences = []
        if self.metrics is None:
            self.metrics = {}

    def count(self, name: str, amount: int = 1) -> None:
        assert self.metrics is not None
        self.metrics[name] = self.metrics.get(name, 0) + amount


def _load_cases(path: Path) -> list[SbdCase]:
    cases: list[SbdCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            case_id = str(payload.get("id") or f"{path.name}:{line_no}").strip()
            chunks = payload.get("chunks")
            if chunks is None:
                chunks = [payload.get("text", "")]
            normalized_chunks = [normalized_text(chunk) for chunk in chunks if normalized_text(chunk)]
            if not normalized_chunks:
                raise ValueError(f"{path}:{line_no} case {case_id!r} has no text chunks")
            cases.append(
                SbdCase(
                    id=case_id,
                    language=str(payload.get("language", "")).strip().lower() or "en",
                    chunks=normalized_chunks,
                    expected_completed=[normalized_text(item) for item in payload.get("expected_completed", [])],
                    expected_pending=normalized_text(str(payload.get("expected_pending", ""))),
                    expected_final=[normalized_text(item) for item in payload.get("expected_final", [])],
                    expected_staged=normalized_text(str(payload.get("expected_staged", ""))),
                    tags=tuple(str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()),
                    sentence_finalize_age=int(payload.get("sentence_finalize_age", 3)),
                )
            )
    if not cases:
        raise ValueError(f"no SBD benchmark cases loaded from {path}")
    return cases


def _boundary_offsets(sentences: list[str]) -> set[int]:
    offsets: set[int] = set()
    cursor = 0
    for sentence in sentences:
        normalized = normalized_text(sentence)
        if not normalized:
            continue
        cursor += len(normalized)
        offsets.add(cursor)
        cursor += 1
    return offsets


def _score_sequence(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    expected_offsets = _boundary_offsets(expected_normalized)
    actual_offsets = _boundary_offsets(actual_normalized)
    true_positive = len(expected_offsets & actual_offsets)
    false_positive = len(actual_offsets - expected_offsets)
    false_negative = len(expected_offsets - actual_offsets)
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact": actual_normalized == expected_normalized,
    }


def _average_scores(results: list[dict[str, Any]], key: str) -> dict[str, float]:
    if not results:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    return {
        "precision": sum(float(result[key]["precision"]) for result in results) / len(results),
        "recall": sum(float(result[key]["recall"]) for result in results) / len(results),
        "f1": sum(float(result[key]["f1"]) for result in results) / len(results),
    }


def _finalize_staged_sentence(state: LifecycleState, language: str, reason: str) -> list[str]:
    if not state.staged_sentence:
        return []
    state.count("finalize_attempt")
    state.count(f"finalize_reason_{reason}")
    output_sentence = _sentence_output_delta(state.committed_text, state.staged_sentence)
    state.staged_sentence = ""
    state.staged_confirmations = 0
    state.staged_age = 0
    state.staged_forced = False
    state.staged_deferred_age_chunk = -1
    if not output_sentence:
        state.count("finalize_duplicate_suppressed")
        state.count("segment_state_suppressed")
        return []
    state.count("finalized")
    state.count("segment_state_final")
    for flag in _final_sentence_diagnostic_flags(output_sentence, language):
        state.count(f"final_quality_{flag}")
    state.committed_text = _append_committed_text(state.committed_text, output_sentence)
    assert state.final_sentences is not None
    state.final_sentences.append(output_sentence)
    return [output_sentence]


def _stage_completed_sentence(
    state: LifecycleState,
    sentence: str,
    language: str,
    *,
    forced: bool,
    sentence_finalize_age: int,
    chunk_index: int,
) -> list[str]:
    normalized_sentence = normalized_text(sentence)
    candidate = _sentence_output_delta(state.committed_text, normalized_sentence)
    if not candidate:
        state.count("candidate_duplicate_suppressed")
        state.count("segment_state_suppressed")
        return []
    if not _should_stage_boundary_candidate(candidate, language):
        state.count("stage_candidate_quality_blocked")
        state.count("segment_state_suppressed")
        for flag in _final_sentence_diagnostic_flags(candidate, language):
            state.count(f"stage_candidate_quality_{flag}")
        return []
    if not state.staged_sentence:
        state.count("stage_start")
        state.count("segment_state_staged")
        state.staged_sentence = candidate
        state.staged_confirmations = 1
        state.staged_age = 0
        state.staged_forced = forced
        return []
    if _sentences_are_revisions(state.staged_sentence, candidate):
        state.count("stage_revision")
        state.count("segment_state_revised")
        previous = state.staged_sentence
        preferred = _prefer_sentence_revision(previous, candidate)
        if preferred != previous:
            state.count("stage_revision_changed")
        state.staged_sentence = preferred
        state.staged_confirmations = _next_revision_confirmation_count(previous, preferred, state.staged_confirmations)
        state.staged_age += 1
        state.count("stage_age_tick")
        state.staged_forced = state.staged_forced or forced
        if _should_confirm_staged_sentence(state.staged_sentence, state.staged_confirmations, state.staged_forced):
            return _finalize_staged_sentence(state, language, "confirmed_forced" if state.staged_forced else "confirmed")
        if _should_finalize_before_replacement(
            state.staged_sentence,
            language,
            state.staged_confirmations,
            state.staged_age,
            sentence_finalize_age,
            state.staged_forced,
        ):
            max_age = _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age)
            if state.staged_age >= max_age:
                state.count("stage_age_finalize")
                reason = "aged_forced" if state.staged_forced else "aged"
            else:
                state.count("stage_finalize_before_replace")
                reason = "next_completed"
            return _finalize_staged_sentence(state, language, reason)
        return []

    state.count("stage_replace")
    replacement_reason = _replacement_decision_reason(
        state.staged_sentence,
        candidate,
        state.staged_confirmations,
        state.staged_forced,
        state.staged_age,
        sentence_finalize_age,
    )
    state.count(f"stage_replace_decision_{replacement_reason}")
    if replacement_reason == "unconfirmed_cjk":
        state.count("stage_replace_deferred")
        if state.staged_deferred_age_chunk != chunk_index:
            state.staged_age += 1
            state.staged_deferred_age_chunk = chunk_index
            state.count("stage_age_tick")
        if _should_finalize_before_replacement(
            state.staged_sentence,
            language,
            state.staged_confirmations,
            state.staged_age,
            sentence_finalize_age,
            state.staged_forced,
        ):
            state.count("stage_age_finalize")
            return _finalize_staged_sentence(state, language, "aged")
        return []
    if _should_finalize_replaced_sentence(
        state.staged_sentence,
        candidate,
        state.staged_confirmations,
        state.staged_forced,
        state.staged_age,
        sentence_finalize_age,
    ):
        finalized = _finalize_staged_sentence(state, language, f"replaced_{replacement_reason}")
    elif _should_finalize_before_replacement(
        state.staged_sentence,
        language,
        state.staged_confirmations,
        state.staged_age,
        sentence_finalize_age,
        state.staged_forced,
    ):
        state.count("stage_finalize_before_replace")
        finalized = _finalize_staged_sentence(state, language, "next_completed")
    else:
        state.count("stage_replaced_unconfirmed")
        state.count("segment_state_suppressed")
        finalized = []
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        state.staged_deferred_age_chunk = -1
    state.count("stage_start")
    state.count("segment_state_staged")
    state.staged_sentence = candidate
    state.staged_confirmations = 1
    state.staged_age = 0
    state.staged_forced = forced
    state.staged_deferred_age_chunk = -1
    return finalized


def _age_staged_sentence(state: LifecycleState, language: str, sentence_finalize_age: int) -> list[str]:
    if not state.staged_sentence:
        return []
    if not _should_age_staged_sentence(state.staged_sentence, state.pending_text):
        state.count("stage_age_hold")
        state.staged_age = 0
        return []
    state.staged_age += 1
    state.count("stage_age_tick")
    if state.staged_age < _sentence_max_age_chunks(state.staged_forced, sentence_finalize_age):
        return []
    if not _should_finalize_before_replacement(
        state.staged_sentence,
        language,
        state.staged_confirmations,
        state.staged_age,
        sentence_finalize_age,
        state.staged_forced,
    ):
        state.count("stage_age_quality_blocked")
        state.count("segment_state_suppressed")
        state.staged_sentence = ""
        state.staged_confirmations = 0
        state.staged_age = 0
        state.staged_forced = False
        return []
    state.count("stage_age_finalize")
    return _finalize_staged_sentence(state, language, "aged_forced" if state.staged_forced else "aged")


def _run_lifecycle_case(case: SbdCase, detector: Any) -> dict[str, Any]:
    state = LifecycleState()
    chunks: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(case.chunks, start=1):
        boundary = detector.split(state.pending_text, chunk, case.language)
        completed = []
        for sentence in boundary.completed:
            completed.append(normalized_text(sentence))
        state.pending_text = normalized_text(boundary.pending)
        if boundary.end_mark_count:
            state.count("boundary_end_marks", boundary.end_mark_count)
        if boundary.right_context_start_count:
            state.count("boundary_right_context_starts", boundary.right_context_start_count)
        if completed:
            state.pending_chunks = 0
        elif state.pending_text:
            state.pending_chunks += 1
            state.count("segment_state_pending")
        produced: list[str] = []
        for sentence in completed:
            finalized = _stage_completed_sentence(
                state,
                sentence,
                case.language,
                forced=False,
                sentence_finalize_age=case.sentence_finalize_age,
                chunk_index=chunk_index,
            )
            produced.extend(finalized)
            for produced_sentence in finalized:
                state.pending_text = _consume_committed_prefix(state.pending_text, produced_sentence)
                if not state.pending_text:
                    state.pending_chunks = 0
        if state.pending_text and completed:
            state.count("segment_state_pending")
        if not completed:
            produced.extend(_age_staged_sentence(state, case.language, case.sentence_finalize_age))
        pending_overrun = _pending_overrun_reason(state.pending_text, state.pending_chunks)
        if pending_overrun:
            state.count("pending_overrun")
            state.count(f"pending_overrun_reason_{pending_overrun}")
        chunks.append(
            {
                "index": chunk_index,
                "input": chunk,
                "completed": completed,
                "pending": state.pending_text,
                "staged": state.staged_sentence,
                "staged_confirmations": state.staged_confirmations,
                "staged_age": state.staged_age,
                "finalized": produced,
                "boundary_count": boundary.boundary_count,
                "end_mark_count": boundary.end_mark_count,
                "right_context_start_count": boundary.right_context_start_count,
            }
        )
    assert state.final_sentences is not None
    assert state.metrics is not None
    return {
        "chunks": chunks,
        "actual_completed_last": chunks[-1]["completed"] if chunks else [],
        "actual_pending": state.pending_text,
        "actual_final": state.final_sentences,
        "actual_staged": state.staged_sentence,
        "committed_text": state.committed_text,
        "metrics": state.metrics,
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


BENCHMARK_BACKEND = "sat"


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
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "tests/eval/dictation_ai/sbd_text_cases.sample.jsonl")
    parser.add_argument("--model", default="sat-3l-sm")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".tmp/eval/dictation-ai-sbd/latest.json")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when final pass rate is below --min-pass-rate.",
    )
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()
    _validate_real_ai_cuda_args(args)

    cases = _load_cases(args.cases)
    detector = create_sentence_boundary_detector(
        BENCHMARK_BACKEND,
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
        completed_score = _score_sequence(case.expected_completed, lifecycle["actual_completed_last"])
        pending_exact = lifecycle["actual_pending"] == case.expected_pending
        staged_exact = lifecycle["actual_staged"] == case.expected_staged
        case_pass = final_score["exact"] and pending_exact and staged_exact
        for key, value in lifecycle["metrics"].items():
            metric_totals[key] = metric_totals.get(key, 0) + int(value)
        results.append(
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "elapsed_ms": round(elapsed_ms, 3),
                "expected_final": case.expected_final,
                "actual_final": lifecycle["actual_final"],
                "expected_pending": case.expected_pending,
                "actual_pending": lifecycle["actual_pending"],
                "expected_staged": case.expected_staged,
                "actual_staged": lifecycle["actual_staged"],
                "final_score": final_score,
                "completed_last_score": completed_score,
                "pending_exact": pending_exact,
                "staged_exact": staged_exact,
                "case_pass": case_pass,
                "metrics": lifecycle["metrics"],
                "chunks": lifecycle["chunks"],
            }
        )

    pass_count = sum(1 for result in results if result["case_pass"])
    pass_rate = pass_count / len(results)
    finalized = metric_totals.get("finalized", 0)
    stage_start = metric_totals.get("stage_start", 0)
    final_score_avg = _average_scores(results, "final_score")
    completed_last_score_avg = _average_scores(results, "completed_last_score")
    report = {
        "backend": BENCHMARK_BACKEND,
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "case_count": len(results),
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "summary": {
            "case_pass": pass_count,
            "pass_rate": pass_rate,
            "min_pass_rate": args.min_pass_rate,
            "finalized": finalized,
            "stage_start": stage_start,
            "finalized_per_stage_start": finalized / max(stage_start, 1),
            "final_precision_avg": final_score_avg["precision"],
            "final_recall_avg": final_score_avg["recall"],
            "final_f1_avg": final_score_avg["f1"],
            "completed_last_precision_avg": completed_last_score_avg["precision"],
            "completed_last_recall_avg": completed_last_score_avg["recall"],
            "completed_last_f1_avg": completed_last_score_avg["f1"],
            "stage_revision": metric_totals.get("stage_revision", 0),
            "stage_replace": metric_totals.get("stage_replace", 0),
            "stage_replaced_unconfirmed": metric_totals.get("stage_replaced_unconfirmed", 0),
            "pending_overrun": metric_totals.get("pending_overrun", 0),
        },
        "metrics": metric_totals,
        "cases": results,
    }
    _write_report(args.output, report)
    print(
        "[dictation-ai-sbd-benchmark] "
        f"cases={len(results)} pass_rate={pass_rate:.3f} finalized={finalized} "
        f"stage_start={stage_start} finalized_per_stage_start={finalized / max(stage_start, 1):.3f} "
        f"final_f1_avg={final_score_avg['f1']:.3f} "
        f"output={args.output}"
    )
    if args.fail_on_regression and pass_rate < args.min_pass_rate:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

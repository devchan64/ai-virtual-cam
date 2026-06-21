#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


TIMESTAMP_RE = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
LANGUAGE_RE = re.compile(r"\[(?P<language>[a-z]{2}) raw\]|language=(?P<language_kv>[a-z]{2})\b")
KV_RE = re.compile(r"\b(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s,]+)")
LOG_GLOB = "avc-whisper.log*"


def iter_log_paths(inputs: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    for source in inputs:
        if source.is_dir():
            paths.extend(sorted(path for path in source.glob(LOG_GLOB) if path.is_file()))
        elif source.is_file():
            paths.append(source)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _merge_counter(target: Counter[str], source: Counter[str]) -> None:
    for key, value in source.items():
        target[key] += value


def _first_non_empty(current: str | None, candidate: str | None) -> str | None:
    if current:
        return current
    if candidate:
        return candidate
    return current


def _line_markers(line: str) -> set[str]:
    markers: set[str] = set()
    if "Dictation AI stt_raw:" in line:
        markers.add("stt_raw")
    if "Dictation AI transcript:" in line:
        markers.add("transcript")
    if "Dictation AI translation:" in line:
        markers.add("translation")
    if "받아쓰기 AI 문장 확정:" in line:
        markers.add("finalize_event")
    if "받아쓰기 AI 문장 진단:" in line:
        markers.add("sentence_diagnostic")
    if "받아쓰기 AI 안정성 지표:" in line:
        markers.add("stability_metrics")
    if "받아쓰기 AI 성능:" in line:
        markers.add("performance_metrics")
    if "받아쓰기 AI 전사 요청:" in line:
        markers.add("stt_request")
    if "받아쓰기 AI 번역 진단:" in line:
        markers.add("translation_diagnostic")
    if "중복 문장 무시" in line:
        markers.add("duplicate_suppressed")
    if "stage 후보 품질 차단" in line or "stage 보류 후보 품질 차단" in line:
        markers.add("quality_block")
    if "stage 큐 승격" in line:
        markers.add("stage_queue_promote")
    if "stage 리비전" in line:
        markers.add("stage_revision")
    if "stage 교체 보류" in line:
        markers.add("stage_replace_deferred")
    if "pending tail:" in line:
        markers.add("pending_tail")
    if "Dictation AI error:" in line or " ERROR " in line or "Validation error" in line:
        markers.add("error")
    return markers


def _line_key_values(line: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in KV_RE.finditer(line)}


def _add_runtime_counts(
    *,
    line: str,
    values: dict[str, str],
    stt_backend_counts: Counter[str],
    stt_model_counts: Counter[str],
    boundary_backend_counts: Counter[str],
    boundary_model_counts: Counter[str],
    translation_backend_counts: Counter[str],
    translation_model_counts: Counter[str],
    window_counts: Counter[str],
    step_counts: Counter[str],
    finalize_age_counts: Counter[str],
) -> None:
    if "받아쓰기 AI 전사 루프 시작:" in line:
        stt_backend = values.get("stt_backend")
        stt_model = values.get("stt_model")
        if stt_backend:
            stt_backend_counts[stt_backend] += 1
        if stt_model:
            stt_model_counts[stt_model] += 1
        if "window_seconds" in values:
            window_counts[values["window_seconds"]] += 1
        if "step_seconds" in values:
            step_counts[values["step_seconds"]] += 1
        if "sentence_finalize_age" in values:
            finalize_age_counts[values["sentence_finalize_age"]] += 1
    elif "STT 모델 로딩" in line:
        backend = values.get("backend")
        model = values.get("model")
        if backend:
            stt_backend_counts[backend] += 1
        if model:
            stt_model_counts[model] += 1
    elif "STT 결과 문장 경계 처리 모델" in line:
        backend = values.get("backend")
        model = values.get("model")
        if backend:
            boundary_backend_counts[backend] += 1
        if model:
            boundary_model_counts[model] += 1
    elif "받아쓰기 AI 번역 진단:" in line:
        backend = values.get("backend")
        model = values.get("model")
        if backend:
            translation_backend_counts[backend] += 1
        if model:
            translation_model_counts[model] += 1

    boundary_backend = values.get("boundary_backend")
    if boundary_backend:
        boundary_backend_counts[boundary_backend] += 1
    if "window" in values:
        window_counts[values["window"]] += 1
    if "step" in values:
        step_counts[values["step"]] += 1
    if "sentenceFinalizeAge" in values:
        finalize_age_counts[values["sentenceFinalizeAge"]] += 1


def audit_log_file(path: Path) -> dict[str, object]:
    marker_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    backend_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    stt_backend_counts: Counter[str] = Counter()
    stt_model_counts: Counter[str] = Counter()
    boundary_backend_counts: Counter[str] = Counter()
    boundary_model_counts: Counter[str] = Counter()
    translation_backend_counts: Counter[str] = Counter()
    translation_model_counts: Counter[str] = Counter()
    window_counts: Counter[str] = Counter()
    step_counts: Counter[str] = Counter()
    finalize_age_counts: Counter[str] = Counter()
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    line_count = 0
    timestamped_line_count = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line_count += 1
            line = raw_line.rstrip("\n")
            timestamp_match = TIMESTAMP_RE.match(line)
            if timestamp_match:
                timestamped_line_count += 1
                timestamp = timestamp_match.group("timestamp")
                first_timestamp = _first_non_empty(first_timestamp, timestamp)
                last_timestamp = timestamp
            marker_counts.update(_line_markers(line))
            language_match = LANGUAGE_RE.search(line)
            if language_match:
                language = language_match.group("language") or language_match.group("language_kv")
                if language:
                    language_counts[language] += 1
            values = _line_key_values(line)
            _add_runtime_counts(
                line=line,
                values=values,
                stt_backend_counts=stt_backend_counts,
                stt_model_counts=stt_model_counts,
                boundary_backend_counts=boundary_backend_counts,
                boundary_model_counts=boundary_model_counts,
                translation_backend_counts=translation_backend_counts,
                translation_model_counts=translation_model_counts,
                window_counts=window_counts,
                step_counts=step_counts,
                finalize_age_counts=finalize_age_counts,
            )
            for key, value in values.items():
                if key in {"backend", "boundary_backend"}:
                    backend_counts[value] += 1
                elif key == "model":
                    model_counts[value] += 1

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "line_count": line_count,
        "timestamped_line_count": timestamped_line_count,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "marker_counts": _counter_payload(marker_counts),
        "language_counts": _counter_payload(language_counts),
        "backend_counts": _counter_payload(backend_counts),
        "model_counts": _counter_payload(model_counts),
        "stt_backend_counts": _counter_payload(stt_backend_counts),
        "stt_model_counts": _counter_payload(stt_model_counts),
        "boundary_backend_counts": _counter_payload(boundary_backend_counts),
        "boundary_model_counts": _counter_payload(boundary_model_counts),
        "translation_backend_counts": _counter_payload(translation_backend_counts),
        "translation_model_counts": _counter_payload(translation_model_counts),
        "window_seconds_counts": _counter_payload(window_counts),
        "step_seconds_counts": _counter_payload(step_counts),
        "sentence_finalize_age_counts": _counter_payload(finalize_age_counts),
    }


def _sum_marker(file_summaries: list[dict[str, object]], marker: str) -> int:
    return sum(int(dict(summary.get("marker_counts", {})).get(marker, 0)) for summary in file_summaries)


def build_readiness(summary: dict[str, object]) -> dict[str, object]:
    marker_counts = dict(summary.get("marker_counts", {}))
    language_counts = dict(summary.get("language_counts", {}))
    stt_backend_counts = dict(summary.get("stt_backend_counts", {}))
    stt_model_counts = dict(summary.get("stt_model_counts", {}))
    window_counts = dict(summary.get("window_seconds_counts", {}))
    step_counts = dict(summary.get("step_seconds_counts", {}))
    finalize_age_counts = dict(summary.get("sentence_finalize_age_counts", {}))
    has_timestamped_logs = int(summary.get("timestamped_line_count", 0)) > 0
    has_stt_windows = int(marker_counts.get("stt_raw", 0)) > 0
    has_transcripts = int(marker_counts.get("transcript", 0)) > 0
    has_final_events = int(marker_counts.get("finalize_event", 0)) > 0
    has_runtime_metadata = (
        bool(language_counts)
        and bool(stt_backend_counts)
        and bool(stt_model_counts)
        and bool(window_counts)
        and bool(step_counts)
        and bool(finalize_age_counts)
    )
    can_seed_representative_candidates = (
        has_timestamped_logs and has_stt_windows and has_transcripts and has_final_events
    )
    blockers: list[str] = []
    if not has_timestamped_logs:
        blockers.append("timestamped log lines are missing")
    if not has_stt_windows:
        blockers.append("stt_raw window lines are missing")
    if not has_transcripts:
        blockers.append("transcript lines are missing")
    if not has_final_events:
        blockers.append("finalize event lines are missing")
    if not language_counts:
        blockers.append("language markers are missing")
    if not stt_backend_counts:
        blockers.append("STT backend markers are missing")
    if not stt_model_counts:
        blockers.append("STT model markers are missing")
    if not window_counts:
        blockers.append("window seconds markers are missing")
    if not step_counts:
        blockers.append("step seconds markers are missing")
    if not finalize_age_counts:
        blockers.append("sentence finalize age markers are missing")
    return {
        "has_timestamped_logs": has_timestamped_logs,
        "has_stt_windows": has_stt_windows,
        "has_transcripts": has_transcripts,
        "has_final_events": has_final_events,
        "has_runtime_metadata": has_runtime_metadata,
        "can_seed_representative_candidates": can_seed_representative_candidates,
        "requires_manual_expected_final": True,
        "blockers": blockers,
    }


def audit_sources(inputs: Iterable[Path]) -> dict[str, object]:
    paths = iter_log_paths(inputs)
    if not paths:
        raise ValueError("no Dictation AI source logs matched")
    file_summaries = [audit_log_file(path) for path in paths]
    marker_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    backend_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    stt_backend_counts: Counter[str] = Counter()
    stt_model_counts: Counter[str] = Counter()
    boundary_backend_counts: Counter[str] = Counter()
    boundary_model_counts: Counter[str] = Counter()
    translation_backend_counts: Counter[str] = Counter()
    translation_model_counts: Counter[str] = Counter()
    window_counts: Counter[str] = Counter()
    step_counts: Counter[str] = Counter()
    finalize_age_counts: Counter[str] = Counter()
    for file_summary in file_summaries:
        _merge_counter(marker_counts, Counter(dict(file_summary.get("marker_counts", {}))))
        _merge_counter(language_counts, Counter(dict(file_summary.get("language_counts", {}))))
        _merge_counter(backend_counts, Counter(dict(file_summary.get("backend_counts", {}))))
        _merge_counter(model_counts, Counter(dict(file_summary.get("model_counts", {}))))
        _merge_counter(stt_backend_counts, Counter(dict(file_summary.get("stt_backend_counts", {}))))
        _merge_counter(stt_model_counts, Counter(dict(file_summary.get("stt_model_counts", {}))))
        _merge_counter(boundary_backend_counts, Counter(dict(file_summary.get("boundary_backend_counts", {}))))
        _merge_counter(boundary_model_counts, Counter(dict(file_summary.get("boundary_model_counts", {}))))
        _merge_counter(translation_backend_counts, Counter(dict(file_summary.get("translation_backend_counts", {}))))
        _merge_counter(translation_model_counts, Counter(dict(file_summary.get("translation_model_counts", {}))))
        _merge_counter(window_counts, Counter(dict(file_summary.get("window_seconds_counts", {}))))
        _merge_counter(step_counts, Counter(dict(file_summary.get("step_seconds_counts", {}))))
        _merge_counter(finalize_age_counts, Counter(dict(file_summary.get("sentence_finalize_age_counts", {}))))

    first_timestamps = [str(summary["first_timestamp"]) for summary in file_summaries if summary["first_timestamp"]]
    last_timestamps = [str(summary["last_timestamp"]) for summary in file_summaries if summary["last_timestamp"]]
    summary: dict[str, object] = {
        "source_count": len(file_summaries),
        "total_bytes": sum(int(summary.get("bytes", 0)) for summary in file_summaries),
        "line_count": sum(int(summary.get("line_count", 0)) for summary in file_summaries),
        "timestamped_line_count": sum(int(summary.get("timestamped_line_count", 0)) for summary in file_summaries),
        "first_timestamp": min(first_timestamps) if first_timestamps else None,
        "last_timestamp": max(last_timestamps) if last_timestamps else None,
        "marker_counts": _counter_payload(marker_counts),
        "language_counts": _counter_payload(language_counts),
        "backend_counts": _counter_payload(backend_counts),
        "model_counts": _counter_payload(model_counts),
        "stt_backend_counts": _counter_payload(stt_backend_counts),
        "stt_model_counts": _counter_payload(stt_model_counts),
        "boundary_backend_counts": _counter_payload(boundary_backend_counts),
        "boundary_model_counts": _counter_payload(boundary_model_counts),
        "translation_backend_counts": _counter_payload(translation_backend_counts),
        "translation_model_counts": _counter_payload(translation_model_counts),
        "window_seconds_counts": _counter_payload(window_counts),
        "step_seconds_counts": _counter_payload(step_counts),
        "sentence_finalize_age_counts": _counter_payload(finalize_age_counts),
        "stt_raw_line_count": _sum_marker(file_summaries, "stt_raw"),
        "files": file_summaries,
    }
    summary["representative_readiness"] = build_readiness(summary)
    return summary


def compact_summary(summary: dict[str, object]) -> dict[str, object]:
    """Return a small report suitable for logs and experiment notes."""
    return {
        "source_count": summary.get("source_count"),
        "total_bytes": summary.get("total_bytes"),
        "line_count": summary.get("line_count"),
        "timestamped_line_count": summary.get("timestamped_line_count"),
        "first_timestamp": summary.get("first_timestamp"),
        "last_timestamp": summary.get("last_timestamp"),
        "marker_counts": summary.get("marker_counts", {}),
        "language_counts": summary.get("language_counts", {}),
        "backend_counts": summary.get("backend_counts", {}),
        "model_counts": summary.get("model_counts", {}),
        "stt_backend_counts": summary.get("stt_backend_counts", {}),
        "stt_model_counts": summary.get("stt_model_counts", {}),
        "boundary_backend_counts": summary.get("boundary_backend_counts", {}),
        "boundary_model_counts": summary.get("boundary_model_counts", {}),
        "translation_backend_counts": summary.get("translation_backend_counts", {}),
        "translation_model_counts": summary.get("translation_model_counts", {}),
        "window_seconds_counts": summary.get("window_seconds_counts", {}),
        "step_seconds_counts": summary.get("step_seconds_counts", {}),
        "sentence_finalize_age_counts": summary.get("sentence_finalize_age_counts", {}),
        "representative_readiness": summary.get("representative_readiness", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Dictation AI logs before representative SBD case sampling.")
    parser.add_argument("sources", nargs="+", type=Path, help="Dictation AI log files or directories.")
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--compact", action="store_true", help="Print aggregate fields only; summary-output stays complete.")
    args = parser.parse_args()

    try:
        summary = audit_sources(args.sources)
    except ValueError as exc:
        print(f"[dictation-ai-sbd-source-audit] error: {exc}", file=sys.stderr)
        return 1
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = compact_summary(summary) if args.compact else summary
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

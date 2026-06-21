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
TRANSCRIPT_SEGMENT_RE = re.compile(r"Dictation AI transcript:\s+\[[a-z]{2}#(?P<segment_id>\d+)\]")
TRANSLATION_SEGMENT_RE = re.compile(r"Dictation AI translation:\s+\[[a-z]{2}->[a-z]{2}#(?P<segment_id>\d+)\]")
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


def _timestamp_in_range(timestamp: str | None, since: str | None, until: str | None) -> bool:
    if timestamp is None:
        return since is None and until is None
    if since is not None and timestamp < since:
        return False
    if until is not None and timestamp > until:
        return False
    return True


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


def _segment_id_from_values(values: dict[str, str]) -> int | None:
    segment_id = values.get("segment_id")
    if segment_id is None:
        return None
    try:
        return int(segment_id)
    except ValueError:
        return None


def _segment_id_from_match(pattern: re.Pattern[str], line: str) -> int | None:
    match = pattern.search(line)
    if not match:
        return None
    try:
        return int(match.group("segment_id"))
    except ValueError:
        return None


def _segment_linkage_payload(
    *,
    finalize_segments: set[int],
    transcript_segments: set[int],
    translation_diagnostic_segments: set[int],
    translation_segments: set[int],
    translation_enabled: bool,
) -> dict[str, object]:
    final_transcript = finalize_segments & transcript_segments
    final_translation_diagnostic = final_transcript & translation_diagnostic_segments
    final_translation = final_transcript & translation_segments
    translation_enabled_finalize_count = len(finalize_segments) if translation_enabled else 0
    translation_enabled_translation_count = len(final_translation) if translation_enabled else 0
    return {
        "translation_enabled": translation_enabled,
        "finalize_segment_count": len(finalize_segments),
        "transcript_segment_count": len(transcript_segments),
        "translation_diagnostic_segment_count": len(translation_diagnostic_segments),
        "translation_segment_count": len(translation_segments),
        "final_transcript_linked_segment_count": len(final_transcript),
        "final_translation_diagnostic_linked_segment_count": len(final_translation_diagnostic),
        "final_translation_linked_segment_count": len(final_translation),
        "finalize_without_transcript_count": len(finalize_segments - transcript_segments),
        "transcript_without_finalize_count": len(transcript_segments - finalize_segments),
        "translation_diagnostic_without_transcript_count": len(
            translation_diagnostic_segments - transcript_segments
        ),
        "translation_without_transcript_count": len(translation_segments - transcript_segments),
        "translation_enabled_finalize_segment_count": translation_enabled_finalize_count,
        "translation_enabled_final_translation_linked_segment_count": translation_enabled_translation_count,
        "translation_enabled_untranslated_final_segment_count": max(
            translation_enabled_finalize_count - translation_enabled_translation_count,
            0,
        ),
        "ready_for_translation_replay_linkage": bool(final_translation),
        "ready_for_translation_diagnostic_linkage": bool(final_translation_diagnostic),
    }


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


def _merge_context_counter(target: Counter[str], context: Counter[str]) -> None:
    if target or not context:
        return
    _merge_counter(target, context)


def audit_log_file(path: Path, *, since: str | None = None, until: str | None = None) -> dict[str, object]:
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
    finalize_segments: set[int] = set()
    transcript_segments: set[int] = set()
    translation_diagnostic_segments: set[int] = set()
    translation_segments: set[int] = set()
    translation_enabled = False
    context_stt_backend_counts: Counter[str] = Counter()
    context_stt_model_counts: Counter[str] = Counter()
    context_boundary_backend_counts: Counter[str] = Counter()
    context_boundary_model_counts: Counter[str] = Counter()
    context_window_counts: Counter[str] = Counter()
    context_step_counts: Counter[str] = Counter()
    context_finalize_age_counts: Counter[str] = Counter()
    context_translation_enabled = False

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            timestamp_match = TIMESTAMP_RE.match(line)
            timestamp = timestamp_match.group("timestamp") if timestamp_match else None
            if since is not None and timestamp is not None and timestamp < since:
                values = _line_key_values(line)
                if values.get("translation_enabled") == "True":
                    context_translation_enabled = True
                _add_runtime_counts(
                    line=line,
                    values=values,
                    stt_backend_counts=context_stt_backend_counts,
                    stt_model_counts=context_stt_model_counts,
                    boundary_backend_counts=context_boundary_backend_counts,
                    boundary_model_counts=context_boundary_model_counts,
                    translation_backend_counts=Counter(),
                    translation_model_counts=Counter(),
                    window_counts=context_window_counts,
                    step_counts=context_step_counts,
                    finalize_age_counts=context_finalize_age_counts,
                )
                continue
            if not _timestamp_in_range(timestamp, since, until):
                continue
            line_count += 1
            if timestamp:
                timestamped_line_count += 1
                first_timestamp = _first_non_empty(first_timestamp, timestamp)
                last_timestamp = timestamp
            marker_counts.update(_line_markers(line))
            language_match = LANGUAGE_RE.search(line)
            if language_match:
                language = language_match.group("language") or language_match.group("language_kv")
                if language:
                    language_counts[language] += 1
            values = _line_key_values(line)
            chunk_values = _line_key_values(line.split(" lifecycle_metrics=", 1)[0])
            for metric_name in (
                "stage_queue_recent_final_suppressed",
                "stage_queue_recent_final_delta_trimmed",
                "finalize_delta_suppressed_stage_retained",
                "finalize_delta_suppressed_stage_dropped",
            ):
                metric_value = chunk_values.get(metric_name)
                if metric_value and metric_value.isdigit():
                    marker_counts[metric_name] += int(metric_value)
            if values.get("translation_enabled") == "True":
                translation_enabled = True
            segment_id = _segment_id_from_values(values)
            if segment_id is not None:
                if "받아쓰기 AI 문장 확정:" in line:
                    finalize_segments.add(segment_id)
                elif "받아쓰기 AI 번역 진단:" in line:
                    translation_diagnostic_segments.add(segment_id)
            transcript_segment_id = _segment_id_from_match(TRANSCRIPT_SEGMENT_RE, line)
            if transcript_segment_id is not None:
                transcript_segments.add(transcript_segment_id)
            translation_segment_id = _segment_id_from_match(TRANSLATION_SEGMENT_RE, line)
            if translation_segment_id is not None:
                translation_segments.add(translation_segment_id)
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

    if line_count > 0:
        if context_translation_enabled:
            translation_enabled = True
        _merge_context_counter(stt_backend_counts, context_stt_backend_counts)
        _merge_context_counter(stt_model_counts, context_stt_model_counts)
        _merge_context_counter(boundary_backend_counts, context_boundary_backend_counts)
        _merge_context_counter(boundary_model_counts, context_boundary_model_counts)
        _merge_context_counter(window_counts, context_window_counts)
        _merge_context_counter(step_counts, context_step_counts)
        _merge_context_counter(finalize_age_counts, context_finalize_age_counts)

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "time_filter": {
            "since": since,
            "until": until,
            "applied": since is not None or until is not None,
        },
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
        "segment_linkage": _segment_linkage_payload(
            finalize_segments=finalize_segments,
            transcript_segments=transcript_segments,
            translation_diagnostic_segments=translation_diagnostic_segments,
            translation_segments=translation_segments,
            translation_enabled=translation_enabled,
        ),
    }


def _sum_marker(file_summaries: list[dict[str, object]], marker: str) -> int:
    return sum(int(dict(summary.get("marker_counts", {})).get(marker, 0)) for summary in file_summaries)


def _sum_segment_linkage(file_summaries: list[dict[str, object]]) -> dict[str, object]:
    numeric_keys = (
        "finalize_segment_count",
        "transcript_segment_count",
        "translation_diagnostic_segment_count",
        "translation_segment_count",
        "final_transcript_linked_segment_count",
        "final_translation_diagnostic_linked_segment_count",
        "final_translation_linked_segment_count",
        "finalize_without_transcript_count",
        "transcript_without_finalize_count",
        "translation_diagnostic_without_transcript_count",
        "translation_without_transcript_count",
        "translation_enabled_finalize_segment_count",
        "translation_enabled_final_translation_linked_segment_count",
        "translation_enabled_untranslated_final_segment_count",
    )
    payload: dict[str, object] = {}
    for key in numeric_keys:
        payload[key] = sum(int(dict(summary.get("segment_linkage", {})).get(key, 0)) for summary in file_summaries)
    payload["translation_enabled_source_count"] = sum(
        1 for summary in file_summaries if bool(dict(summary.get("segment_linkage", {})).get("translation_enabled", False))
    )
    payload["ready_for_translation_replay_linkage"] = int(payload["final_translation_linked_segment_count"]) > 0
    payload["ready_for_translation_diagnostic_linkage"] = (
        int(payload["final_translation_diagnostic_linked_segment_count"]) > 0
    )
    enabled_final_count = int(payload["translation_enabled_finalize_segment_count"])
    if enabled_final_count > 0:
        payload["translation_enabled_final_translation_linked_ratio"] = (
            int(payload["translation_enabled_final_translation_linked_segment_count"]) / enabled_final_count
        )
    else:
        payload["translation_enabled_final_translation_linked_ratio"] = None
    return payload


def _finalization_observation_payload(marker_counts: Counter[str]) -> dict[str, float | int | None]:
    stt_raw = int(marker_counts.get("stt_raw", 0))
    finalize_events = int(marker_counts.get("finalize_event", 0))
    deferred = int(marker_counts.get("stage_replace_deferred", 0))
    quality_blocks = int(marker_counts.get("quality_block", 0))
    duplicate_suppressed = int(marker_counts.get("duplicate_suppressed", 0))
    queue_promotes = int(marker_counts.get("stage_queue_promote", 0))
    queue_recent_suppressed = int(marker_counts.get("stage_queue_recent_final_suppressed", 0))
    queue_recent_trimmed = int(marker_counts.get("stage_queue_recent_final_delta_trimmed", 0))
    delta_suppressed_stage_retained = int(marker_counts.get("finalize_delta_suppressed_stage_retained", 0))
    delta_suppressed_stage_dropped = int(marker_counts.get("finalize_delta_suppressed_stage_dropped", 0))
    return {
        "stt_raw_line_count": stt_raw,
        "finalize_event_count": finalize_events,
        "stage_replace_deferred_count": deferred,
        "quality_block_count": quality_blocks,
        "duplicate_suppressed_count": duplicate_suppressed,
        "stage_queue_promote_count": queue_promotes,
        "stage_queue_recent_final_suppressed_count": queue_recent_suppressed,
        "stage_queue_recent_final_delta_trimmed_count": queue_recent_trimmed,
        "finalize_delta_suppressed_stage_retained_count": delta_suppressed_stage_retained,
        "finalize_delta_suppressed_stage_dropped_count": delta_suppressed_stage_dropped,
        "finalize_per_stt_raw": (finalize_events / stt_raw) if stt_raw else None,
        "stage_replace_deferred_per_stt_raw": (deferred / stt_raw) if stt_raw else None,
        "quality_block_per_stt_raw": (quality_blocks / stt_raw) if stt_raw else None,
        "duplicate_suppressed_per_stt_raw": (duplicate_suppressed / stt_raw) if stt_raw else None,
        "stage_queue_promote_per_stt_raw": (queue_promotes / stt_raw) if stt_raw else None,
        "stage_queue_recent_final_suppressed_per_stt_raw": (queue_recent_suppressed / stt_raw) if stt_raw else None,
        "stage_queue_recent_final_delta_trimmed_per_stt_raw": (queue_recent_trimmed / stt_raw) if stt_raw else None,
        "finalize_delta_suppressed_stage_retained_per_stt_raw": (
            delta_suppressed_stage_retained / stt_raw
        )
        if stt_raw
        else None,
        "finalize_delta_suppressed_stage_dropped_per_stt_raw": (
            delta_suppressed_stage_dropped / stt_raw
        )
        if stt_raw
        else None,
    }


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


def audit_sources(
    inputs: Iterable[Path],
    *,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, object]:
    paths = iter_log_paths(inputs)
    if not paths:
        raise ValueError("no Dictation AI source logs matched")
    file_summaries = [
        summary
        for path in paths
        if (summary := audit_log_file(path, since=since, until=until))["line_count"]
    ]
    if not file_summaries:
        raise ValueError("no Dictation AI source log lines matched the selected time range")
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
        "time_filter": {
            "since": since,
            "until": until,
            "applied": since is not None or until is not None,
        },
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
        "segment_linkage": _sum_segment_linkage(file_summaries),
        "stt_raw_line_count": _sum_marker(file_summaries, "stt_raw"),
        "files": file_summaries,
    }
    summary["finalization_observation"] = _finalization_observation_payload(marker_counts)
    summary["representative_readiness"] = build_readiness(summary)
    return summary


def compact_summary(summary: dict[str, object]) -> dict[str, object]:
    """Return a small report suitable for logs and experiment notes."""
    return {
        "source_count": summary.get("source_count"),
        "time_filter": summary.get("time_filter", {}),
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
        "segment_linkage": summary.get("segment_linkage", {}),
        "finalization_observation": summary.get("finalization_observation", {}),
        "representative_readiness": summary.get("representative_readiness", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Dictation AI logs before representative SBD case sampling.")
    parser.add_argument("sources", nargs="+", type=Path, help="Dictation AI log files or directories.")
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--compact", action="store_true", help="Print aggregate fields only; summary-output stays complete.")
    parser.add_argument("--since", default=None, help="Include timestamped lines at or after YYYY-MM-DD HH:MM:SS.")
    parser.add_argument("--until", default=None, help="Include timestamped lines at or before YYYY-MM-DD HH:MM:SS.")
    args = parser.parse_args()

    try:
        summary = audit_sources(args.sources, since=args.since, until=args.until)
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

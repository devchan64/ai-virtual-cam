#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


REVIEW_PACKET_VERSION = 1
REQUIRED_REVIEW_EVENT_KINDS = ("raw_chunks", "transcripts", "final_events", "performance_events")
LIFECYCLE_EVENT_MARKERS = (
    ("stage_replace_deferred", "stage 교체 보류"),
    ("quality_block", "stage 후보 품질 차단"),
    ("quality_block", "stage 보류 후보 품질 차단"),
    ("stage_queue_promote", "stage 큐 승격"),
    ("duplicate_suppressed", "중복 문장 무시"),
)
PRIORITY_METRIC_TO_LIFECYCLE_KIND = {
    "stage_replace_deferred_per_stt_raw": "stage_replace_deferred",
    "quality_block_per_stt_raw": "quality_block",
    "duplicate_suppressed_per_stt_raw": "duplicate_suppressed",
    "stage_queue_promote_per_stt_raw": "stage_queue_promote",
    "stage_queue_recent_final_suppressed_per_stt_raw": "stage_queue_recent_final_suppressed",
    "stage_queue_recent_final_delta_trimmed_per_stt_raw": "stage_queue_recent_final_delta_trimmed",
    "finalize_delta_suppressed_stage_retained_per_stt_raw": "finalize_delta_suppressed_stage_retained",
    "finalize_delta_suppressed_stage_dropped_per_stt_raw": "finalize_delta_suppressed_stage_dropped",
}

TIMESTAMP_RE = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
STT_RAW_RE = re.compile(r"Dictation AI stt_raw: \[(?P<language>[a-z]{2}) raw\] (?P<text>.*)$")
TRANSCRIPT_RE = re.compile(
    r"Dictation AI transcript: \[(?P<language>[a-z]{2})(?:#(?P<segment_id>\d+))?\] (?P<text>.*)$"
)
FINAL_RE = re.compile(r"받아쓰기 AI 문장 확정: (?P<payload>.*)$")
PERFORMANCE_RE = re.compile(r"받아쓰기 AI 성능: (?P<payload>.*)$")
KV_RE = re.compile(r"(?P<key>[A-Za-z_]+)=(?P<value>[^\s,]+)")


def _timestamp(line: str) -> str:
    match = TIMESTAMP_RE.search(line)
    return match.group("timestamp") if match else ""


def _trim_text(text: str, *, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _evenly_spaced(items: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if limit <= 0:
        return []
    if len(items) <= limit:
        return items
    if limit == 1:
        return [items[0]]
    max_index = len(items) - 1
    indexes = sorted({round(index * max_index / (limit - 1)) for index in range(limit)})
    return [items[index] for index in indexes]


def _kv_payload(payload: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in KV_RE.finditer(payload)}


def _quoted_value(payload: str, key: str) -> str:
    marker = f"{key}="
    start = payload.find(marker)
    if start < 0:
        return ""
    value_start = start + len(marker)
    if value_start >= len(payload):
        return ""
    if payload[value_start] not in ("'", '"'):
        value = payload[value_start:].split(maxsplit=1)[0]
        return value.rstrip(",")

    quote = payload[value_start]
    cursor = value_start + 1
    escaped = False
    while cursor < len(payload):
        char = payload[cursor]
        if char == "\\" and not escaped:
            escaped = True
            cursor += 1
            continue
        if char == quote and not escaped:
            raw_value = payload[value_start : cursor + 1]
            try:
                parsed = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError):
                return raw_value[1:-1]
            return str(parsed)
        escaped = False
        cursor += 1
    return payload[value_start + 1 :]


def _parse_final_event(line: str, *, text_limit: int) -> dict[str, object] | None:
    match = FINAL_RE.search(line)
    if not match:
        return None
    payload = match.group("payload")
    values = _kv_payload(payload)
    record: dict[str, object] = {
        "timestamp": _timestamp(line),
        "chunk": values.get("chunk", ""),
        "reason": values.get("reason", ""),
        "output_chars": values.get("output_chars", ""),
        "quality_flags": values.get("quality_flags", ""),
        "text": _trim_text(_quoted_value(payload, "text"), limit=text_limit),
    }
    staged_tail = _quoted_value(payload, "staged_tail")
    if staged_tail:
        record["staged_tail"] = _trim_text(staged_tail, limit=text_limit)
    return record


def _parse_performance_event(line: str) -> dict[str, object] | None:
    match = PERFORMANCE_RE.search(line)
    if not match:
        return None
    values = _kv_payload(match.group("payload"))
    wanted_keys = (
        "chunk",
        "step",
        "window",
        "text_chars",
        "audio_rms",
        "audio_peak",
        "stability",
        "stable_support",
        "boundary_score",
        "end_probability",
    )
    record: dict[str, object] = {"timestamp": _timestamp(line)}
    for key in wanted_keys:
        if key in values:
            record[key] = values[key]
    return record


def _parse_lifecycle_event(line: str, *, text_limit: int) -> dict[str, object] | None:
    matched_kind = ""
    for kind, marker in LIFECYCLE_EVENT_MARKERS:
        if marker in line:
            matched_kind = kind
            break
    if not matched_kind:
        return None
    payload = line.split("Dictation AI status:", 1)[-1].strip()
    values = _kv_payload(payload)
    record: dict[str, object] = {
        "timestamp": _timestamp(line),
        "kind": matched_kind,
        "chunk": values.get("chunk", ""),
        "decision": values.get("decision", ""),
        "staged_confirmations": values.get("staged_confirmations", ""),
        "staged_age": values.get("staged_age", ""),
        "queue_remaining": values.get("queue_remaining", ""),
    }
    for key in ("staged_tail", "candidate_tail", "text"):
        value = _quoted_value(payload, key)
        if value:
            record[key] = _trim_text(value, limit=text_limit)
    return record


def _inside_source_window(timestamp: str, *, started_at: str, ended_at: str) -> bool:
    if not started_at and not ended_at:
        return True
    if not timestamp:
        return False
    if started_at and timestamp < started_at:
        return False
    if ended_at and timestamp > ended_at:
        return False
    return True


def _collect_source_events(
    source_log: Path,
    *,
    text_limit: int,
    started_at: str = "",
    ended_at: str = "",
) -> dict[str, list[dict[str, object]]]:
    raw_chunks: list[dict[str, object]] = []
    transcripts: list[dict[str, object]] = []
    final_events: list[dict[str, object]] = []
    performance_events: list[dict[str, object]] = []
    lifecycle_events: list[dict[str, object]] = []

    with source_log.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            timestamp = _timestamp(line)
            if not _inside_source_window(timestamp, started_at=started_at, ended_at=ended_at):
                continue

            raw_match = STT_RAW_RE.search(line)
            if raw_match:
                raw_chunks.append(
                    {
                        "timestamp": timestamp,
                        "line_number": line_number,
                        "language": raw_match.group("language"),
                        "text": _trim_text(raw_match.group("text"), limit=text_limit),
                    }
                )
                continue

            transcript_match = TRANSCRIPT_RE.search(line)
            if transcript_match:
                record = {
                    "timestamp": timestamp,
                    "line_number": line_number,
                    "language": transcript_match.group("language"),
                    "text": _trim_text(transcript_match.group("text"), limit=text_limit),
                }
                segment_id = transcript_match.group("segment_id")
                if segment_id:
                    record["segment_id"] = segment_id
                transcripts.append(record)
                continue

            final_event = _parse_final_event(line, text_limit=text_limit)
            if final_event is not None:
                final_event["line_number"] = line_number
                final_events.append(final_event)
                continue

            performance_event = _parse_performance_event(line)
            if performance_event is not None:
                performance_event["line_number"] = line_number
                performance_events.append(performance_event)
                continue

            lifecycle_event = _parse_lifecycle_event(line, text_limit=text_limit)
            if lifecycle_event is not None:
                lifecycle_event["line_number"] = line_number
                lifecycle_events.append(lifecycle_event)

    return {
        "raw_chunks": raw_chunks,
        "transcripts": transcripts,
        "final_events": final_events,
        "performance_events": performance_events,
        "lifecycle_events": lifecycle_events,
    }


def _source_record_runtime(record: dict[str, object]) -> dict[str, object]:
    return {
        "stt_backend_candidates": dict(record.get("stt_backend_candidates", {})),
        "stt_model_candidates": dict(record.get("stt_model_candidates", {})),
        "boundary_backend_candidates": dict(record.get("boundary_backend_candidates", {})),
        "boundary_model_candidates": dict(record.get("boundary_model_candidates", {})),
        "window_seconds_candidates": dict(record.get("window_seconds_candidates", {})),
        "step_seconds_candidates": dict(record.get("step_seconds_candidates", {})),
        "sentence_finalize_age_candidates": dict(record.get("sentence_finalize_age_candidates", {})),
    }


def _review_readiness(event_counts: dict[str, int]) -> dict[str, object]:
    missing = [kind for kind in REQUIRED_REVIEW_EVENT_KINDS if int(event_counts.get(kind, 0)) <= 0]
    return {
        "ready_for_human_review": not missing,
        "missing_event_kinds": missing,
    }


def build_review_packets(
    manifest: dict[str, object],
    *,
    max_raw_chunks_per_source: int,
    max_transcripts_per_source: int,
    max_finals_per_source: int,
    max_performance_events_per_source: int,
    max_lifecycle_events_per_source: int,
    text_limit: int = 220,
) -> dict[str, object]:
    packets: list[dict[str, object]] = []
    missing_sources: list[str] = []
    for source in list(manifest.get("selected_sources", [])):
        if not isinstance(source, dict):
            continue
        source_log = Path(str(source.get("source_log", "")))
        if not source_log.is_file():
            missing_sources.append(str(source_log))
            continue
        source_started_at = str(source.get("source_started_at", "")).strip()
        source_ended_at = str(source.get("source_ended_at", "")).strip()
        events = _collect_source_events(
            source_log,
            text_limit=text_limit,
            started_at=source_started_at,
            ended_at=source_ended_at,
        )
        event_counts = {key: len(value) for key, value in events.items()}
        readiness = _review_readiness(event_counts)
        priority_metric = source.get("priority_metric")
        priority_lifecycle_kind = PRIORITY_METRIC_TO_LIFECYCLE_KIND.get(str(priority_metric or ""))
        priority_lifecycle_events = [
            event
            for event in events["lifecycle_events"]
            if priority_lifecycle_kind and event.get("kind") == priority_lifecycle_kind
        ]
        packets.append(
            {
                "id": source.get("id", ""),
                "language": source.get("language", ""),
                "source_log": str(source_log),
                "source_started_at": source_started_at,
                "source_ended_at": source_ended_at,
                "source_window_filter": {
                    "applied": bool(source_started_at or source_ended_at),
                    "started_at": source_started_at,
                    "ended_at": source_ended_at,
                },
                "sampling_unit": source.get("sampling_unit", ""),
                "sampling_rule": source.get("sampling_rule", ""),
                "priority_metric": priority_metric,
                "priority_rank": source.get("priority_rank"),
                "priority_ratio": source.get("priority_ratio"),
                "priority_marker_count": source.get("priority_marker_count"),
                "priority_lifecycle_kind": priority_lifecycle_kind,
                "runtime_candidates": _source_record_runtime(source),
                "event_counts": event_counts,
                "review_readiness": readiness,
                "raw_chunks_sample": _evenly_spaced(events["raw_chunks"], max_raw_chunks_per_source),
                "transcript_events_sample": _evenly_spaced(
                    events["transcripts"],
                    max_transcripts_per_source,
                ),
                "final_events_sample": _evenly_spaced(events["final_events"], max_finals_per_source),
                "performance_events_sample": _evenly_spaced(
                    events["performance_events"],
                    max_performance_events_per_source,
                ),
                "lifecycle_events_sample": _evenly_spaced(
                    events["lifecycle_events"],
                    max_lifecycle_events_per_source,
                ),
                "priority_lifecycle_events_sample": _evenly_spaced(
                    priority_lifecycle_events,
                    max_lifecycle_events_per_source,
                ),
                "review_status": "orientation_only_requires_manual_window_selection_and_expected_final",
                "case_generation": False,
                "paper_evidence": False,
                "expected_final_generated": False,
            }
        )
    packet_readiness_blockers = [
        {
            "id": packet.get("id", ""),
            "source_log": packet.get("source_log", ""),
            "missing_event_kinds": dict(packet.get("review_readiness", {})).get("missing_event_kinds", []),
        }
        for packet in packets
        if not bool(dict(packet.get("review_readiness", {})).get("ready_for_human_review", False))
    ]

    return {
        "representative_review_packet_version": REVIEW_PACKET_VERSION,
        "source_manifest": {
            "sampling_unit": manifest.get("sampling_unit", ""),
            "sampling_rule": manifest.get("sampling_rule", ""),
            "selected_source_count": manifest.get("selected_source_count", 0),
            "selected_source_counts": manifest.get("selected_source_counts", {}),
        },
        "limits": {
            "max_raw_chunks_per_source": max_raw_chunks_per_source,
            "max_transcripts_per_source": max_transcripts_per_source,
            "max_finals_per_source": max_finals_per_source,
            "max_performance_events_per_source": max_performance_events_per_source,
            "max_lifecycle_events_per_source": max_lifecycle_events_per_source,
            "text_limit": text_limit,
        },
        "packet_count": len(packets),
        "ready_packet_count": sum(
            1
            for packet in packets
            if bool(dict(packet.get("review_readiness", {})).get("ready_for_human_review", False))
        ),
        "packet_readiness_blockers": packet_readiness_blockers,
        "missing_source_logs": missing_sources,
        "packets": packets,
        "interpretation": {
            "paper_evidence": False,
            "case_generation": False,
            "expected_final_generated": False,
            "claim_scope": "human review orientation packet only",
        },
    }


def write_markdown_packets(payload: dict[str, object], path: Path) -> None:
    lines = [
        "# Representative Source Review Packets",
        "",
        f"- packet_count: `{payload.get('packet_count')}`",
        f"- ready_packet_count: `{payload.get('ready_packet_count')}`",
        f"- packet_readiness_blockers: `{payload.get('packet_readiness_blockers')}`",
        f"- missing_source_logs: `{payload.get('missing_source_logs')}`",
        "- paper_evidence: `false`",
        "- case_generation: `false`",
        "- expected_final_generated: `false`",
        "",
        "## Review Checklist",
        "",
        "- Select a bounded time/chunk window from one packet before writing a representative JSONL case.",
        "- Confirm the runtime metadata inside that selected window.",
        "- Write `expected_final` by human review; do not copy transcript/final output as the answer.",
        "- Preserve `review_packet_id`, `source_log`, `language`, sampling metadata, and reviewer id in the case.",
        "",
    ]
    for packet in list(payload.get("packets", [])):
        if not isinstance(packet, dict):
            continue
        runtime_candidates = packet.get("runtime_candidates")
        source_window_filter = packet.get("source_window_filter")
        lines.extend(
            [
                f"## {packet.get('id')}",
                "",
                f"- language: `{packet.get('language')}`",
                f"- source_log: `{packet.get('source_log')}`",
                f"- source_range: `{packet.get('source_started_at')}` - `{packet.get('source_ended_at')}`",
                f"- sampling_unit: `{packet.get('sampling_unit')}`",
                f"- sampling_rule: `{packet.get('sampling_rule')}`",
                f"- priority: metric=`{packet.get('priority_metric')}` rank=`{packet.get('priority_rank')}` ratio=`{packet.get('priority_ratio')}` count=`{packet.get('priority_marker_count')}`",
                f"- priority_lifecycle_kind: `{packet.get('priority_lifecycle_kind')}`",
                f"- runtime_candidates: `{runtime_candidates}`",
                f"- source_window_filter: `{source_window_filter}`",
                f"- event_counts: `{packet.get('event_counts')}`",
                f"- review_readiness: `{packet.get('review_readiness')}`",
                "",
                "| kind | timestamp | line | text |",
                "| --- | --- | --- | --- |",
            ]
        )
        for kind, field in (
            ("raw", "raw_chunks_sample"),
            ("final", "final_events_sample"),
            ("transcript", "transcript_events_sample"),
        ):
            for event in list(packet.get(field, []))[:8]:
                if not isinstance(event, dict):
                    continue
                text = str(event.get("text", "")).replace("|", "\\|")
                lines.append(
                    f"| {kind} | {event.get('timestamp', '')} | {event.get('line_number', '')} | {text} |"
                )
        performance_sample = [event for event in list(packet.get("performance_events_sample", [])) if isinstance(event, dict)]
        if performance_sample:
            lines.extend(
                [
                    "",
                    "| performance_timestamp | line | chunk | window | stability | stable_support | boundary_score | end_probability |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for event in performance_sample[:8]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(event.get("timestamp", "")),
                            str(event.get("line_number", "")),
                            str(event.get("chunk", "")),
                            str(event.get("window", "")),
                            str(event.get("stability", "")),
                            str(event.get("stable_support", "")),
                            str(event.get("boundary_score", "")),
                            str(event.get("end_probability", "")),
                        ]
                    )
                    + " |"
                )
        lifecycle_sample = [event for event in list(packet.get("lifecycle_events_sample", [])) if isinstance(event, dict)]
        priority_lifecycle_sample = [
            event
            for event in list(packet.get("priority_lifecycle_events_sample", []))
            if isinstance(event, dict)
        ]
        if priority_lifecycle_sample:
            lines.extend(
                [
                    "",
                    "| priority_lifecycle_timestamp | line | kind | chunk | staged_age | staged_confirmations | staged_tail | candidate_tail |",
                    "| --- | ---: | --- | ---: | ---: | ---: | --- | --- |",
                ]
            )
            for event in priority_lifecycle_sample[:12]:
                staged_tail = str(event.get("staged_tail", "")).replace("|", "\\|")
                candidate_tail = str(event.get("candidate_tail", "")).replace("|", "\\|")
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(event.get("timestamp", "")),
                            str(event.get("line_number", "")),
                            str(event.get("kind", "")),
                            str(event.get("chunk", "")),
                            str(event.get("staged_age", "")),
                            str(event.get("staged_confirmations", "")),
                            staged_tail,
                            candidate_tail,
                        ]
                    )
                    + " |"
                )
        if lifecycle_sample:
            lines.extend(
                [
                    "",
                    "| lifecycle_timestamp | line | kind | chunk | staged_age | staged_confirmations | staged_tail | candidate_tail |",
                    "| --- | ---: | --- | ---: | ---: | ---: | --- | --- |",
                ]
            )
            for event in lifecycle_sample[:12]:
                staged_tail = str(event.get("staged_tail", "")).replace("|", "\\|")
                candidate_tail = str(event.get("candidate_tail", "")).replace("|", "\\|")
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(event.get("timestamp", "")),
                            str(event.get("line_number", "")),
                            str(event.get("kind", "")),
                            str(event.get("chunk", "")),
                            str(event.get("staged_age", "")),
                            str(event.get("staged_confirmations", "")),
                            staged_tail,
                            candidate_tail,
                        ]
                    )
                    + " |"
                )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract non-case representative source review packets from selected Dictation AI logs."
    )
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, default=None)
    parser.add_argument("--max-raw-chunks-per-source", type=int, default=40)
    parser.add_argument("--max-transcripts-per-source", type=int, default=60)
    parser.add_argument("--max-finals-per-source", type=int, default=60)
    parser.add_argument("--max-performance-events-per-source", type=int, default=30)
    parser.add_argument("--max-lifecycle-events-per-source", type=int, default=40)
    parser.add_argument("--text-limit", type=int, default=220)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
        payload = build_review_packets(
            manifest,
            max_raw_chunks_per_source=args.max_raw_chunks_per_source,
            max_transcripts_per_source=args.max_transcripts_per_source,
            max_finals_per_source=args.max_finals_per_source,
            max_performance_events_per_source=args.max_performance_events_per_source,
            max_lifecycle_events_per_source=args.max_lifecycle_events_per_source,
            text_limit=args.text_limit,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-review-packet-extractor] error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output is not None:
        write_markdown_packets(payload, args.markdown_output)
    print(
        json.dumps(
            {
                "packet_count": payload["packet_count"],
                "ready_packet_count": payload["ready_packet_count"],
                "packet_readiness_blockers": payload["packet_readiness_blockers"],
                "missing_source_logs": payload["missing_source_logs"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

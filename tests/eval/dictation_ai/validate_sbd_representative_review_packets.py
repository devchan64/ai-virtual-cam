#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_EVENT_KINDS = ("raw_chunks", "transcripts", "final_events", "performance_events")
REVIEW_PACKET_VERSION = 1


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalized_blocker(value: object) -> dict[str, object]:
    blocker = _as_dict(value)
    return {
        "id": str(blocker.get("id", "")).strip(),
        "source_log": str(blocker.get("source_log", "")).strip(),
        "missing_event_kinds": sorted(str(item) for item in _as_list(blocker.get("missing_event_kinds"))),
    }


def _manifest_language_counts(payload: dict[str, Any]) -> dict[str, int]:
    source_manifest = _as_dict(payload.get("source_manifest"))
    selected_source_counts = _as_dict(source_manifest.get("selected_source_counts"))
    return {
        str(language): int(count)
        for language, count in selected_source_counts.items()
        if str(language).strip()
    }


def _manifest_summary(payload: dict[str, Any]) -> dict[str, object]:
    source_manifest = _as_dict(payload.get("source_manifest"))
    return {
        "sampling_unit": str(source_manifest.get("sampling_unit", "")).strip(),
        "sampling_rule": str(source_manifest.get("sampling_rule", "")).strip(),
        "selected_source_count": int(source_manifest.get("selected_source_count", 0)),
        "selected_source_counts": _manifest_language_counts(payload),
    }


def _validate_source_window_filter(packet: dict[str, Any], *, packet_id: str) -> bool:
    started_at = str(packet.get("source_started_at", "")).strip()
    ended_at = str(packet.get("source_ended_at", "")).strip()
    window_filter = _as_dict(packet.get("source_window_filter"))
    if not window_filter:
        raise ValueError(f"packet {packet_id!r} missing source_window_filter")
    applied = bool(window_filter.get("applied", False))
    if (started_at or ended_at) and not applied:
        raise ValueError(f"packet {packet_id!r} source_window_filter must be applied")
    filter_started_at = str(window_filter.get("started_at", "")).strip()
    filter_ended_at = str(window_filter.get("ended_at", "")).strip()
    if filter_started_at != started_at:
        raise ValueError(f"packet {packet_id!r} source_window_filter started_at mismatch")
    if filter_ended_at != ended_at:
        raise ValueError(f"packet {packet_id!r} source_window_filter ended_at mismatch")
    return applied


def validate_review_packets(
    payload: dict[str, Any],
    *,
    allow_not_ready: bool = False,
    allow_missing_source_logs: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("review packet root must be a JSON object")
    version = int(payload.get("representative_review_packet_version", -1))
    if version != REVIEW_PACKET_VERSION:
        raise ValueError(
            f"unsupported representative review packet version: {version}; expected {REVIEW_PACKET_VERSION}"
        )
    if bool(_as_dict(payload.get("interpretation")).get("paper_evidence", True)):
        raise ValueError("review packet payload must not be paper evidence")
    if bool(_as_dict(payload.get("interpretation")).get("case_generation", True)):
        raise ValueError("review packet payload must not be case generation")
    if bool(_as_dict(payload.get("interpretation")).get("expected_final_generated", True)):
        raise ValueError("review packet payload must not generate expected_final")

    packets = _as_list(payload.get("packets"))
    packet_count = int(payload.get("packet_count", -1))
    if packet_count != len(packets):
        raise ValueError(f"packet_count mismatch: packet_count={packet_count} actual={len(packets)}")
    source_manifest = _as_dict(payload.get("source_manifest"))
    selected_source_count = int(source_manifest.get("selected_source_count", len(packets)))
    if selected_source_count != len(packets):
        raise ValueError(
            "source manifest selected_source_count mismatch: "
            f"selected_source_count={selected_source_count} packet_count={len(packets)}"
        )

    missing_source_logs = [str(item) for item in _as_list(payload.get("missing_source_logs"))]
    if missing_source_logs and not allow_missing_source_logs:
        raise ValueError("review packet payload has missing source logs: " + ", ".join(missing_source_logs))

    not_ready_packets: list[dict[str, object]] = []
    language_counts: Counter[str] = Counter()
    event_totals: Counter[str] = Counter()
    source_window_filter_applied_count = 0
    for index, packet_value in enumerate(packets, start=1):
        packet = _as_dict(packet_value)
        packet_id = str(packet.get("id", "")).strip()
        if not packet_id:
            raise ValueError(f"packet #{index} missing id")
        if bool(packet.get("paper_evidence", True)):
            raise ValueError(f"packet {packet_id!r} must not be paper evidence")
        if bool(packet.get("case_generation", True)):
            raise ValueError(f"packet {packet_id!r} must not be case generation")
        if bool(packet.get("expected_final_generated", True)):
            raise ValueError(f"packet {packet_id!r} must not generate expected_final")
        if _validate_source_window_filter(packet, packet_id=packet_id):
            source_window_filter_applied_count += 1

        language = str(packet.get("language", "")).strip() or "unknown"
        language_counts[language] += 1
        event_counts = _as_dict(packet.get("event_counts"))
        for kind in REQUIRED_EVENT_KINDS:
            event_totals[kind] += int(event_counts.get(kind, 0))

        readiness = _as_dict(packet.get("review_readiness"))
        ready = bool(readiness.get("ready_for_human_review", False))
        missing = [str(item) for item in _as_list(readiness.get("missing_event_kinds"))]
        if not ready:
            not_ready_packets.append(
                {
                    "id": packet_id,
                    "source_log": str(packet.get("source_log", "")),
                    "missing_event_kinds": sorted(missing),
                }
            )
    manifest_language_counts = _manifest_language_counts(payload)
    if manifest_language_counts and manifest_language_counts != dict(sorted(language_counts.items())):
        raise ValueError(
            "source manifest selected_source_counts mismatch: "
            f"selected_source_counts={manifest_language_counts} packet_language_counts={dict(sorted(language_counts.items()))}"
        )
    ready_packet_count = int(payload.get("ready_packet_count", -1))
    actual_ready_count = len(packets) - len(not_ready_packets)
    if ready_packet_count != actual_ready_count:
        raise ValueError(
            f"ready_packet_count mismatch: ready_packet_count={ready_packet_count} actual={actual_ready_count}"
        )
    declared_blockers = _as_list(payload.get("packet_readiness_blockers"))
    if len(declared_blockers) != len(not_ready_packets):
        raise ValueError(
            "packet_readiness_blockers mismatch: "
            f"declared={len(declared_blockers)} actual={len(not_ready_packets)}"
        )
    normalized_declared_blockers = sorted(
        (_normalized_blocker(item) for item in declared_blockers),
        key=lambda item: (str(item["id"]), str(item["source_log"])),
    )
    normalized_actual_blockers = sorted(
        (_normalized_blocker(item) for item in not_ready_packets),
        key=lambda item: (str(item["id"]), str(item["source_log"])),
    )
    if normalized_declared_blockers != normalized_actual_blockers:
        raise ValueError("packet_readiness_blockers content mismatch")
    if not_ready_packets and not allow_not_ready:
        raise ValueError("review packet payload has not-ready packets")
    return {
        "source_manifest": _manifest_summary(payload),
        "packet_count": len(packets),
        "ready_packet_count": actual_ready_count,
        "not_ready_packet_count": len(not_ready_packets),
        "missing_source_log_count": len(missing_source_logs),
        "language_counts": dict(sorted(language_counts.items())),
        "event_totals": dict(sorted(event_totals.items())),
        "source_window_filter_applied_count": source_window_filter_applied_count,
        "not_ready_packets": not_ready_packets,
        "missing_source_logs": missing_source_logs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dictation AI representative source review packets.")
    parser.add_argument("review_packets", type=Path)
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--allow-missing-source-logs", action="store_true")
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        payload = json.loads(args.review_packets.read_text(encoding="utf-8"))
        summary = validate_review_packets(
            payload,
            allow_not_ready=args.allow_not_ready,
            allow_missing_source_logs=args.allow_missing_source_logs,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-review-packet-validator] error: {exc}", file=sys.stderr)
        return 1
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

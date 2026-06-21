#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.dictation_ai.cases.sbd_case_paths import iter_case_paths
from tests.eval.dictation_ai.cases.validate_sbd_case_files import validate_case_files


TRANSLATION_REPLAY_REQUIRED_SIGNALS = (
    "final segment id",
    "translation diagnostic segment id",
    "translation output segment id",
    "final/transcript/translation segment linkage",
)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _marker_count(summary: dict[str, Any], key: str) -> int:
    marker_counts = summary.get("marker_counts", {})
    if not isinstance(marker_counts, dict):
        return 0
    value = marker_counts.get(key, 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _source_can_seed_representative_candidates(source_audit: dict[str, Any]) -> bool:
    readiness = source_audit.get("representative_readiness", {})
    if isinstance(readiness, dict):
        return bool(readiness.get("can_seed_representative_candidates", False))
    return bool(source_audit.get("can_seed_representative_candidates", False))


def _representative_case_summary(
    cases: Path,
    *,
    review_packets: Path | None,
) -> dict[str, Any]:
    paths = iter_case_paths([cases])
    if not paths:
        return {
            "case_file_count": 0,
            "case_count": 0,
            "expected_final_case_count": 0,
            "draft_count": 0,
            "language_counts": {},
            "validation_error": "no representative JSONL case files matched",
        }
    try:
        summary = validate_case_files([cases], review_packets=review_packets)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "case_file_count": len(paths),
            "case_count": 0,
            "expected_final_case_count": 0,
            "draft_count": 0,
            "language_counts": {},
            "validation_error": str(exc),
        }
    return {
        "case_file_count": len(paths),
        "case_count": int(summary.get("case_count", 0)),
        "expected_final_case_count": int(summary.get("expected_final_case_count", 0)),
        "draft_count": int(summary.get("draft_count", 0)),
        "language_counts": summary.get("language_counts", {}),
        "representative_metadata": summary.get("representative_metadata", {}),
        "representative_review_packet_validation": summary.get(
            "representative_review_packet_validation",
            {},
        ),
        "validation_error": "",
    }


def _representative_status(
    *,
    source_audit: dict[str, Any],
    packet_validation: dict[str, Any],
    case_summary: dict[str, Any],
) -> str:
    if not _source_can_seed_representative_candidates(source_audit):
        return "blocked_on_source_logs"
    if int(packet_validation.get("ready_packet_count", 0)) <= 0:
        return "blocked_on_review_packets"
    if case_summary.get("validation_error"):
        if int(case_summary.get("case_file_count", 0)) == 0:
            return "blocked_on_human_expected_final"
        return "blocked_on_representative_case_validation"
    if int(case_summary.get("expected_final_case_count", 0)) <= 0:
        return "blocked_on_human_expected_final"
    return "ready_for_pilot_representative_replay"


def _draft_validation_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = _load_json_object(path)
    review_packet_validation = payload.get("representative_review_packet_validation", {})
    if not isinstance(review_packet_validation, dict):
        review_packet_validation = {}
    case_count = int(payload.get("case_count", 0))
    draft_count = int(payload.get("draft_count", 0))
    expected_final_case_count = int(payload.get("expected_final_case_count", 0))
    matched_case_count = int(review_packet_validation.get("matched_case_count", 0))
    return {
        "path": str(path),
        "case_count": case_count,
        "draft_count": draft_count,
        "expected_final_case_count": expected_final_case_count,
        "language_counts": payload.get("language_counts", {}),
        "matched_case_count": matched_case_count,
        "review_packet_count": int(review_packet_validation.get("packet_count", 0)),
        "ready_packet_count": int(review_packet_validation.get("ready_packet_count", 0)),
        "traceable": draft_count > 0 and matched_case_count == case_count,
    }


def _translation_status(source_audit: dict[str, Any]) -> dict[str, Any]:
    translation_count = _marker_count(source_audit, "translation")
    diagnostic_count = _marker_count(source_audit, "translation_diagnostic")
    has_translation_logs = translation_count > 0
    has_translation_diagnostics = diagnostic_count > 0
    segment_linkage = source_audit.get("segment_linkage", {})
    if not isinstance(segment_linkage, dict):
        segment_linkage = {}
    final_segment_count = int(segment_linkage.get("finalize_segment_count", 0))
    diagnostic_segment_count = int(segment_linkage.get("translation_diagnostic_segment_count", 0))
    output_segment_count = int(segment_linkage.get("translation_segment_count", 0))
    linked_output_count = int(segment_linkage.get("final_translation_linked_segment_count", 0))
    linked_diagnostic_count = int(segment_linkage.get("final_translation_diagnostic_linked_segment_count", 0))
    missing_required_signals: list[str] = []
    if final_segment_count <= 0:
        missing_required_signals.append("final segment id")
    if diagnostic_segment_count <= 0:
        missing_required_signals.append("translation diagnostic segment id")
    if output_segment_count <= 0:
        missing_required_signals.append("translation output segment id")
    if linked_output_count <= 0:
        missing_required_signals.append("final/transcript/translation segment linkage")
    if linked_output_count > 0:
        status = "ready_for_translation_replay_case_building"
    elif linked_diagnostic_count > 0:
        status = "blocked_on_translation_output_linkage"
    elif has_translation_logs or has_translation_diagnostics:
        status = "blocked_on_translation_replay_linkage"
    else:
        status = "blocked_on_translation_logs"
    return {
        "has_translation_logs": has_translation_logs,
        "translation_event_count": translation_count,
        "has_translation_diagnostics": has_translation_diagnostics,
        "translation_diagnostic_count": diagnostic_count,
        "segment_linkage": segment_linkage,
        "missing_required_signals": missing_required_signals,
        "status": status,
    }


def audit_followup_readiness(
    *,
    source_audit_path: Path,
    review_packet_validation_path: Path,
    representative_cases: Path,
    review_packets: Path | None = None,
    representative_draft_validation: Path | None = None,
) -> dict[str, Any]:
    source_audit = _load_json_object(source_audit_path)
    packet_validation = _load_json_object(review_packet_validation_path)
    draft_summary = _draft_validation_summary(representative_draft_validation)
    case_summary = _representative_case_summary(
        representative_cases,
        review_packets=review_packets,
    )
    representative_status = _representative_status(
        source_audit=source_audit,
        packet_validation=packet_validation,
        case_summary=case_summary,
    )
    translation = _translation_status(source_audit)
    next_actions: list[str] = []
    if representative_status == "blocked_on_human_expected_final":
        if bool(draft_summary.get("traceable", False)):
            next_actions.append("fill expected_final in traceable representative drafts and promote reviewed JSONL cases")
        else:
            next_actions.append("create human-reviewed representative JSONL cases from ready review packets")
    elif representative_status == "ready_for_pilot_representative_replay":
        next_actions.append("run pilot representative replay with explicit min expected-final case count")
    else:
        next_actions.append("fix representative source or packet readiness before paper-evidence replay")
    if translation["status"] == "blocked_on_translation_replay_linkage":
        next_actions.append("add final-event to translation request/output linkage before translation claims")
    elif translation["status"] == "blocked_on_translation_output_linkage":
        next_actions.append("collect segment-linked translation output logs before translation claims")
    elif translation["status"] == "blocked_on_translation_logs":
        next_actions.append("collect translation logs before translation replay")
    return {
        "source_audit": str(source_audit_path),
        "review_packet_validation": str(review_packet_validation_path),
        "representative_cases": str(representative_cases),
        "representative": {
            "source_can_seed_candidates": _source_can_seed_representative_candidates(source_audit),
            "packet_count": int(packet_validation.get("packet_count", 0)),
            "ready_packet_count": int(packet_validation.get("ready_packet_count", 0)),
            "source_window_filter_applied_count": int(
                packet_validation.get("source_window_filter_applied_count", 0)
            ),
            "case_summary": case_summary,
            "draft_summary": draft_summary,
            "status": representative_status,
        },
        "translation": translation,
        "next_actions": next_actions,
        "paper_evidence_ready": (
            representative_status == "ready_for_pilot_representative_replay"
            and translation["status"] not in {
                "blocked_on_translation_replay_linkage",
                "blocked_on_translation_logs",
            }
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit readiness for representative and translation follow-up replay.",
    )
    parser.add_argument(
        "--source-audit",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-source-audit.json"),
    )
    parser.add_argument(
        "--review-packet-validation",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json"),
    )
    parser.add_argument(
        "--representative-cases",
        type=Path,
        default=Path("tests/eval/dictation_ai/sbd_representative_cases"),
    )
    parser.add_argument(
        "--review-packets",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-source-review-packets.json"),
    )
    parser.add_argument(
        "--representative-draft-validation",
        type=Path,
        default=None,
        help="Optional validation summary for .tmp representative draft JSONL templates.",
    )
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = audit_followup_readiness(
            source_audit_path=args.source_audit,
            review_packet_validation_path=args.review_packet_validation,
            representative_cases=args.representative_cases,
            review_packets=args.review_packets,
            representative_draft_validation=args.representative_draft_validation,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[dictation-ai-sbd-followup-readiness] error: {exc}", file=sys.stderr)
        return 2
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

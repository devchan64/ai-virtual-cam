#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.dictation_ai.cases.sbd_case_paths import (
    case_corpus_role,
    iter_case_paths,
    representative_metadata_record,
    summarize_representative_metadata,
    validate_representative_payload,
)
from tests.eval.dictation_ai.representative.validate_sbd_representative_review_packets import validate_review_packets


TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def _validated_case_paths(inputs: Iterable[Path]) -> list[Path]:
    unique = iter_case_paths(inputs)
    if not unique:
        raise ValueError(f"no SBD case files matched: {', '.join(str(item) for item in inputs)}")
    missing = [path for path in unique if not path.is_file()]
    if missing:
        raise ValueError("SBD case files not found: " + ", ".join(str(path) for path in missing))
    if not unique:
        raise ValueError("no SBD case files matched")
    return unique


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_review_packet_index(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = validate_review_packets(payload)
    packets: dict[str, dict[str, Any]] = {}
    for packet_value in payload.get("packets", []):
        packet = _as_dict(packet_value)
        packet_id = str(packet.get("id", "")).strip()
        if packet_id:
            packets[packet_id] = packet
    return packets, summary


def _timestamp_like(value: str) -> bool:
    return bool(TIMESTAMP_RE.match(value.strip()))


def _validate_case_range_inside_packet_window(
    payload: dict[str, object],
    *,
    packet: dict[str, Any],
    path: Path,
    line_no: int,
    case_id: str,
    review_packet_id: str,
) -> None:
    case_started_at = str(payload.get("source_started_at", "")).strip()
    case_ended_at = str(payload.get("source_ended_at", "")).strip()
    if not (_timestamp_like(case_started_at) and _timestamp_like(case_ended_at)):
        return
    source_window_filter = _as_dict(packet.get("source_window_filter"))
    packet_started_at = str(source_window_filter.get("started_at") or packet.get("source_started_at", "")).strip()
    packet_ended_at = str(source_window_filter.get("ended_at") or packet.get("source_ended_at", "")).strip()
    if not (_timestamp_like(packet_started_at) and _timestamp_like(packet_ended_at)):
        return
    if case_started_at < packet_started_at or case_ended_at > packet_ended_at:
        raise ValueError(
            f"{path}:{line_no} case {case_id!r} source range outside review packet window "
            f"{review_packet_id!r}: case={case_started_at!r}..{case_ended_at!r} "
            f"packet={packet_started_at!r}..{packet_ended_at!r}"
        )
    if case_started_at > case_ended_at:
        raise ValueError(
            f"{path}:{line_no} case {case_id!r} source range starts after it ends: "
            f"{case_started_at!r}..{case_ended_at!r}"
        )


def _validate_review_packet_link(
    payload: dict[str, object],
    *,
    packet_index: dict[str, dict[str, Any]],
    path: Path,
    line_no: int,
    case_id: str,
) -> None:
    review_packet_id = str(payload.get("review_packet_id", "")).strip()
    packet = packet_index.get(review_packet_id)
    if packet is None:
        raise ValueError(f"{path}:{line_no} case {case_id!r} unknown review_packet_id: {review_packet_id!r}")
    source_log = str(payload.get("source_log", "")).strip()
    packet_source_log = str(packet.get("source_log", "")).strip()
    if source_log != packet_source_log:
        raise ValueError(
            f"{path}:{line_no} case {case_id!r} source_log mismatch for review_packet_id "
            f"{review_packet_id!r}: case={source_log!r} packet={packet_source_log!r}"
        )
    language = str(payload.get("language", "")).strip().lower()
    packet_language = str(packet.get("language", "")).strip().lower()
    if language != packet_language:
        raise ValueError(
            f"{path}:{line_no} case {case_id!r} language mismatch for review_packet_id "
            f"{review_packet_id!r}: case={language!r} packet={packet_language!r}"
        )
    _validate_case_range_inside_packet_window(
        payload,
        packet=packet,
        path=path,
        line_no=line_no,
        case_id=case_id,
        review_packet_id=review_packet_id,
    )


def validate_case_files(
    inputs: Iterable[Path],
    *,
    allow_drafts: bool = False,
    require_expected_final: bool = False,
    review_packets: Path | None = None,
    corpus_role_override: str | None = None,
) -> dict[str, object]:
    input_list = list(inputs)
    corpus_role = corpus_role_override or case_corpus_role(input_list)
    if corpus_role_override is not None and corpus_role_override != "representative":
        raise ValueError(f"unsupported corpus_role override: {corpus_role_override}")
    review_packet_index: dict[str, dict[str, Any]] | None = None
    review_packet_summary: dict[str, Any] | None = None
    if review_packets is not None:
        if corpus_role != "representative":
            raise ValueError("--review-packets can only be used with representative corpus")
        review_packet_index, review_packet_summary = _load_review_packet_index(review_packets)
    seen_ids: dict[str, str] = {}
    language_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    representative_records: list[dict[str, object]] = []
    draft_count = 0
    case_count = 0
    expected_final_case_count = 0
    sources: list[str] = []
    for path in _validated_case_paths(input_list):
        sources.append(str(path))
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                payload = json.loads(line)
                case_id = str(payload.get("id") or "").strip()
                if not case_id:
                    raise ValueError(f"{path}:{line_no} missing case id")
                previous = seen_ids.get(case_id)
                if previous is not None:
                    raise ValueError(f"duplicate SBD case id {case_id!r}: {previous} and {path}:{line_no}")
                seen_ids[case_id] = f"{path}:{line_no}"
                chunks = payload.get("chunks")
                if chunks is None:
                    chunks = [payload.get("text", "")]
                if not any(str(chunk).strip() for chunk in chunks):
                    raise ValueError(f"{path}:{line_no} case {case_id!r} has no text chunks")
                is_draft = bool(payload.get("draft_expected_final_required", False))
                if corpus_role == "representative":
                    validate_representative_payload(
                        payload,
                        path=path,
                        line_no=line_no,
                        case_id=case_id,
                        allow_draft=is_draft and allow_drafts,
                    )
                    if review_packet_index is not None:
                        _validate_review_packet_link(
                            payload,
                            packet_index=review_packet_index,
                            path=path,
                            line_no=line_no,
                            case_id=case_id,
                        )
                has_expected_final = any(str(item).strip() for item in payload.get("expected_final", []))
                if is_draft:
                    draft_count += 1
                    if not allow_drafts:
                        raise ValueError(
                            f"{path}:{line_no} case {case_id!r} is an unreviewed draft. "
                            "Fill expected_final and remove draft_expected_final_required before registering it."
                        )
                elif (require_expected_final or corpus_role == "representative") and not has_expected_final:
                    raise ValueError(f"{path}:{line_no} case {case_id!r} has no expected_final")
                if has_expected_final:
                    expected_final_case_count += 1
                case_count += 1
                language_counts[str(payload.get("language", "")).strip().lower() or "en"] += 1
                tag_counts.update(str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip())
                if corpus_role == "representative":
                    representative_records.append(representative_metadata_record(payload))
    summary: dict[str, object] = {
        "case_count": case_count,
        "corpus_role": corpus_role,
        "draft_count": draft_count,
        "expected_final_case_count": expected_final_case_count,
        "language_counts": dict(sorted(language_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "sources": sources,
    }
    if corpus_role == "representative":
        summary["representative_metadata"] = summarize_representative_metadata(representative_records)
        if review_packet_summary is not None:
            summary["representative_review_packet_validation"] = {
                "review_packet_file": str(review_packets),
                "packet_count": review_packet_summary["packet_count"],
                "ready_packet_count": review_packet_summary["ready_packet_count"],
                "matched_case_count": len(representative_records),
                "source_manifest": review_packet_summary["source_manifest"],
            }
    return summary


def enforce_case_thresholds(
    summary: dict[str, object],
    *,
    min_cases: int | None = None,
    min_expected_final_cases: int | None = None,
    max_drafts: int | None = None,
) -> None:
    case_count = int(summary.get("case_count", 0))
    draft_count = int(summary.get("draft_count", 0))
    expected_final_case_count = int(summary.get("expected_final_case_count", 0))
    if min_cases is not None and case_count < min_cases:
        raise ValueError(f"SBD case count below target: case_count={case_count} min_cases={min_cases}")
    if min_expected_final_cases is not None and expected_final_case_count < min_expected_final_cases:
        raise ValueError(
            "SBD expected-final case count below target: "
            f"expected_final_case_count={expected_final_case_count} "
            f"min_expected_final_cases={min_expected_final_cases}"
        )
    if max_drafts is not None and draft_count > max_drafts:
        raise ValueError(f"SBD draft count above limit: draft_count={draft_count} max_drafts={max_drafts}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate reviewed Dictation AI SBD benchmark case files.")
    parser.add_argument("cases", nargs="+", type=Path)
    parser.add_argument("--allow-drafts", action="store_true", help="Report draft counts without failing.")
    parser.add_argument(
        "--require-expected-final",
        action="store_true",
        help="Fail when a non-draft case has no expected_final. Use for reviewed finalization datasets.",
    )
    parser.add_argument("--min-cases", type=int, default=None, help="Fail when loaded case count is below this value.")
    parser.add_argument(
        "--min-expected-final-cases",
        type=int,
        default=None,
        help="Fail when non-empty expected_final case count is below this value.",
    )
    parser.add_argument("--max-drafts", type=int, default=None, help="Fail when draft marker count is above this value.")
    parser.add_argument(
        "--review-packets",
        type=Path,
        default=None,
        help="For representative cases, validate review_packet_id/source_log/language against this packet JSON.",
    )
    parser.add_argument(
        "--corpus-role",
        choices=("representative",),
        default=None,
        help="Explicitly validate an out-of-tree file as a representative corpus, e.g. .tmp draft JSONL.",
    )
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        summary = validate_case_files(
            args.cases,
            allow_drafts=args.allow_drafts,
            require_expected_final=args.require_expected_final,
            review_packets=args.review_packets,
            corpus_role_override=args.corpus_role,
        )
        enforce_case_thresholds(
            summary,
            min_cases=args.min_cases,
            min_expected_final_cases=args.min_expected_final_cases,
            max_drafts=args.max_drafts,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-case-validator] error: {exc}", file=sys.stderr)
        return 1
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

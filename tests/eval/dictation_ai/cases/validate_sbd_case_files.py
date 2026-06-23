#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.dictation_ai.cases.sbd_case_paths import (
    case_corpus_role,
    iter_case_paths,
    representative_metadata_record,
    summarize_representative_metadata,
    validate_representative_payload,
)
from tests.eval.dictation_ai.cases.sbd_input_evidence import case_input_evidence
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
    require_source_trace: bool = False,
    require_input_evidence: bool = False,
    require_observed_input_evidence: bool = False,
    require_stable_repeat_evidence: bool = False,
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
    expected_no_final_case_count = 0
    unmarked_no_expected_final_case_count = 0
    unmarked_no_expected_final_examples: list[dict[str, object]] = []
    source_trace_case_count = 0
    missing_source_trace_case_count = 0
    missing_source_trace_by_file: Counter[str] = Counter()
    missing_source_trace_examples: list[dict[str, object]] = []
    input_unsupported_case_count = 0
    input_unsupported_by_file: Counter[str] = Counter()
    input_unsupported_examples: list[dict[str, object]] = []
    input_unobserved_case_count = 0
    input_unobserved_by_file: Counter[str] = Counter()
    input_unobserved_examples: list[dict[str, object]] = []
    stable_repeat_unsupported_case_count = 0
    stable_repeat_unsupported_by_file: Counter[str] = Counter()
    stable_repeat_unsupported_examples: list[dict[str, object]] = []
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
                    if not bool(payload.get("expected_no_final", False)):
                        raise ValueError(f"{path}:{line_no} case {case_id!r} has no expected_final")
                if bool(payload.get("expected_no_final", False)):
                    if has_expected_final:
                        raise ValueError(
                            f"{path}:{line_no} case {case_id!r} cannot set expected_no_final with expected_final"
                        )
                    expected_no_final_case_count += 1
                elif not has_expected_final:
                    unmarked_no_expected_final_case_count += 1
                    if len(unmarked_no_expected_final_examples) < 8:
                        unmarked_no_expected_final_examples.append(
                            {
                                "id": case_id,
                                "path": str(path),
                                "line_no": line_no,
                                "language": str(payload.get("language", "")).strip().lower() or "en",
                            }
                        )
                if has_expected_final:
                    expected_final_case_count += 1
                    input_evidence = case_input_evidence(payload)
                    if not bool(input_evidence.get("fully_supported", False)):
                        input_unsupported_case_count += 1
                        input_unsupported_by_file[str(path)] += 1
                        if len(input_unsupported_examples) < 8:
                            input_unsupported_examples.append(
                                {
                                    "id": case_id,
                                    "path": str(path),
                                    "line_no": line_no,
                                    "language": str(payload.get("language", "")).strip().lower() or "en",
                                    "expected_count": int(input_evidence.get("expected_count", 0)),
                                    "covered_count": int(input_evidence.get("covered_count", 0)),
                                    "observed_count": int(input_evidence.get("observed_count", 0)),
                                    "coverage_min": float(input_evidence.get("coverage_min", 0.0)),
                                    "coverage_avg": float(input_evidence.get("coverage_avg", 0.0)),
                                }
                            )
                        if require_input_evidence:
                            raise ValueError(
                                f"{path}:{line_no} case {case_id!r} expected_final is not fully supported "
                                "by replay chunks: "
                                f"covered={input_evidence.get('covered_count', 0)}/"
                                f"{input_evidence.get('expected_count', 0)} "
                                f"coverage_min={float(input_evidence.get('coverage_min', 0.0)):.3f}"
                            )
                    if not bool(input_evidence.get("observed_fully_supported", False)):
                        input_unobserved_case_count += 1
                        input_unobserved_by_file[str(path)] += 1
                        if len(input_unobserved_examples) < 8:
                            input_unobserved_examples.append(
                                {
                                    "id": case_id,
                                    "path": str(path),
                                    "line_no": line_no,
                                    "language": str(payload.get("language", "")).strip().lower() or "en",
                                    "expected_count": int(input_evidence.get("expected_count", 0)),
                                    "observed_count": int(input_evidence.get("observed_count", 0)),
                                    "covered_count": int(input_evidence.get("covered_count", 0)),
                                    "coverage_min": float(input_evidence.get("coverage_min", 0.0)),
                                    "coverage_avg": float(input_evidence.get("coverage_avg", 0.0)),
                                }
                            )
                        if require_observed_input_evidence:
                            raise ValueError(
                                f"{path}:{line_no} case {case_id!r} expected_final is not observed as raw STT "
                                "text in replay chunks: "
                                f"observed={input_evidence.get('observed_count', 0)}/"
                                f"{input_evidence.get('expected_count', 0)} "
                                f"coverage_avg={float(input_evidence.get('coverage_avg', 0.0)):.3f}"
                            )
                    if not bool(input_evidence.get("stable_repeat_fully_supported", False)):
                        stable_repeat_unsupported_case_count += 1
                        stable_repeat_unsupported_by_file[str(path)] += 1
                        if len(stable_repeat_unsupported_examples) < 8:
                            stable_repeat_unsupported_examples.append(
                                {
                                    "id": case_id,
                                    "path": str(path),
                                    "line_no": line_no,
                                    "language": str(payload.get("language", "")).strip().lower() or "en",
                                    "expected_count": int(input_evidence.get("expected_count", 0)),
                                    "stable_repeat_count": int(input_evidence.get("stable_repeat_count", 0)),
                                    "required_repeat_observations": int(
                                        input_evidence.get("required_repeat_observations", 0)
                                    ),
                                    "repeat_count_min": int(input_evidence.get("repeat_count_min", 0)),
                                    "repeat_count_avg": float(input_evidence.get("repeat_count_avg", 0.0)),
                                    "repeat_count_max": int(input_evidence.get("repeat_count_max", 0)),
                                    "stable_group_count_min": int(input_evidence.get("stable_group_count_min", 0)),
                                    "stable_group_count_avg": float(input_evidence.get("stable_group_count_avg", 0.0)),
                                    "stable_group_count_max": int(input_evidence.get("stable_group_count_max", 0)),
                                    "stable_candidate_count": int(input_evidence.get("stable_candidate_count", 0)),
                                    "stable_candidate_examples": input_evidence.get("stable_candidate_examples", []),
                                    "expected_sentence_evidence": input_evidence.get("expected_sentence_evidence", []),
                                }
                            )
                        if require_stable_repeat_evidence:
                            raise ValueError(
                                f"{path}:{line_no} case {case_id!r} expected_final is not supported by "
                                "repeated token-sentence candidates: "
                                f"stable_repeat={input_evidence.get('stable_repeat_count', 0)}/"
                                f"{input_evidence.get('expected_count', 0)} "
                                f"required_observations={input_evidence.get('required_repeat_observations', 0)} "
                                f"stable_group_min={input_evidence.get('stable_group_count_min', 0)}"
                            )
                    source_log = str(payload.get("source_log", "")).strip()
                    has_source_chunk = payload.get("source_chunk") is not None
                    if source_log and has_source_chunk:
                        source_trace_case_count += 1
                    else:
                        missing_source_trace_case_count += 1
                        missing_source_trace_by_file[str(path)] += 1
                        if len(missing_source_trace_examples) < 8:
                            missing_source_trace_examples.append(
                                {
                                    "id": case_id,
                                    "path": str(path),
                                    "line_no": line_no,
                                    "language": str(payload.get("language", "")).strip().lower() or "en",
                                    "review_source_file": str(payload.get("review_source_file", "")).strip(),
                                }
                            )
                        if require_source_trace:
                            missing_parts = []
                            if not source_log:
                                missing_parts.append("source_log")
                            if not has_source_chunk:
                                missing_parts.append("source_chunk")
                            raise ValueError(
                                f"{path}:{line_no} case {case_id!r} missing source trace metadata: "
                                + ", ".join(missing_parts)
                            )
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
        "expected_no_final_case_count": expected_no_final_case_count,
        "unmarked_no_expected_final_case_count": unmarked_no_expected_final_case_count,
        "unmarked_no_expected_final_examples": unmarked_no_expected_final_examples,
        "source_trace_case_count": source_trace_case_count,
        "missing_source_trace_case_count": missing_source_trace_case_count,
        "missing_source_trace_by_file": dict(sorted(missing_source_trace_by_file.items())),
        "missing_source_trace_examples": missing_source_trace_examples,
        "input_unsupported_case_count": input_unsupported_case_count,
        "input_unsupported_by_file": dict(sorted(input_unsupported_by_file.items())),
        "input_unsupported_examples": input_unsupported_examples,
        "input_unobserved_case_count": input_unobserved_case_count,
        "input_unobserved_by_file": dict(sorted(input_unobserved_by_file.items())),
        "input_unobserved_examples": input_unobserved_examples,
        "stable_repeat_unsupported_case_count": stable_repeat_unsupported_case_count,
        "stable_repeat_unsupported_by_file": dict(sorted(stable_repeat_unsupported_by_file.items())),
        "stable_repeat_unsupported_examples": stable_repeat_unsupported_examples,
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
    parser.add_argument(
        "--require-source-trace",
        action="store_true",
        help="Fail when an expected_final case has no source_log/source_chunk trace metadata.",
    )
    parser.add_argument(
        "--require-input-evidence",
        action="store_true",
        help="Fail when expected_final is not fully supported by the case replay chunks.",
    )
    parser.add_argument(
        "--require-observed-input-evidence",
        action="store_true",
        help="Fail when expected_final is not observed as raw STT text in the case replay chunks.",
    )
    parser.add_argument(
        "--require-stable-repeat-evidence",
        action="store_true",
        help=(
            "Fail when any expected_final sentence is not supported by token-sentence candidates repeated "
            "at least sentence_finalize_age times."
        ),
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
            require_source_trace=args.require_source_trace,
            require_input_evidence=args.require_input_evidence,
            require_observed_input_evidence=args.require_observed_input_evidence,
            require_stable_repeat_evidence=args.require_stable_repeat_evidence,
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

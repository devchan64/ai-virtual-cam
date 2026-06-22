#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.sentence_boundary import normalized_text
from tests.eval.dictation_ai.cases.sbd_expected_quality import expected_quality_flags
from tests.eval.dictation_ai.cases.sbd_case_paths import iter_case_paths
from tests.eval.dictation_ai.cases.sbd_input_evidence import case_input_evidence


DEFAULT_MIN_PREFIX_UNITS = 12
DEFAULT_PREVIEW_UNITS = 80
DEFAULT_WORST_CASE_LIMIT = 20
DEFAULT_WORST_GROUP_LIMIT = 12
DEFAULT_DUPLICATE_GROUP_LIMIT = 20


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _normalized_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalized_text(item) for item in value if normalized_text(item)]


def _prefix_preview(text: str, *, preview_units: int) -> str:
    text = normalized_text(text)
    if len(text) <= preview_units:
        return text
    return text[:preview_units]


def _find_first_expected_offset(chunks: list[str], first_expected: str) -> tuple[int, int] | None:
    for index, chunk in enumerate(chunks):
        offset = chunk.find(first_expected)
        if offset >= 0:
            return index, offset
    return None


def _audit_payload(
    payload: dict[str, Any],
    *,
    path: Path,
    line_no: int,
    min_prefix_units: int,
    preview_units: int,
) -> dict[str, Any] | None:
    initial_final = _normalized_list(payload.get("initial_final", []))
    expected_final = _normalized_list(payload.get("expected_final", []))
    if initial_final or not expected_final:
        return None
    raw_chunks = payload.get("chunks")
    if raw_chunks is None:
        raw_chunks = [payload.get("text", "")]
    if not isinstance(raw_chunks, list):
        return None
    chunks = [normalized_text(chunk) for chunk in raw_chunks if normalized_text(chunk)]
    if not chunks:
        return None

    first_expected = expected_final[0]
    location = _find_first_expected_offset(chunks, first_expected)
    if location is None:
        return None
    chunk_index, offset = location
    if offset < min_prefix_units:
        return None
    prefix = chunks[chunk_index][:offset]
    return {
        "id": str(payload.get("id") or f"{path.name}:{line_no}").strip(),
        "language": str(payload.get("language", "")).strip().lower() or "en",
        "path": str(path),
        "line_no": line_no,
        "chunk_index": chunk_index,
        "prefix_units": offset,
        "first_expected": first_expected,
        "prefix_preview": _prefix_preview(prefix, preview_units=preview_units),
        "chunk_preview": _prefix_preview(chunks[chunk_index], preview_units=preview_units),
        "source_log": str(payload.get("source_log", "")).strip(),
        "source_chunk": payload.get("source_chunk"),
        "review_group_id": str(payload.get("review_group_id", "")).strip(),
        "tags": [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()],
    }


def _average_score(cases: list[dict[str, Any]], *, score_key: str, metric_key: str) -> float:
    if not cases:
        return 0.0
    return sum(_as_float(dict(case.get(score_key, {})).get(metric_key)) for case in cases) / len(cases)


def _score_group_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(cases),
        "expected_sentence_count": sum(len(case.get("expected_final", [])) for case in cases),
        "actual_sentence_count": sum(len(case.get("actual_final", [])) for case in cases),
        "final_precision_avg": _average_score(cases, score_key="final_score", metric_key="precision"),
        "final_recall_avg": _average_score(cases, score_key="final_score", metric_key="recall"),
        "final_f1_avg": _average_score(cases, score_key="final_score", metric_key="f1"),
        "final_boundary_f1_avg": _average_score(cases, score_key="final_boundary_score", metric_key="f1"),
    }


def _case_score_record(case: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    final_score = dict(case.get("final_score", {}))
    boundary_score = dict(case.get("final_boundary_score", {}))
    return {
        "id": case.get("id", ""),
        "language": case.get("language") or candidate.get("language", ""),
        "final_f1": final_score.get("f1"),
        "final_precision": final_score.get("precision"),
        "final_recall": final_score.get("recall"),
        "final_boundary_f1": boundary_score.get("f1"),
        "expected_sentence_count": len(case.get("expected_final", [])),
        "actual_sentence_count": len(case.get("actual_final", [])),
        "source_log": candidate.get("source_log", ""),
        "source_chunk": candidate.get("source_chunk"),
        "review_group_id": candidate.get("review_group_id", ""),
        "prefix_units": candidate.get("prefix_units"),
        "first_expected": candidate.get("first_expected", ""),
        "prefix_preview": candidate.get("prefix_preview", ""),
        "tags": list(candidate.get("tags", [])),
    }


def _worst_candidate_scores(
    cases: list[dict[str, Any]],
    candidates_by_id: dict[str, dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        candidate = candidates_by_id.get(case_id)
        if candidate is None:
            continue
        records.append(_case_score_record(case, candidate))
    return sorted(
        records,
        key=lambda item: (
            _as_float(item.get("final_f1")),
            _as_float(item.get("final_boundary_f1")),
            str(item.get("id", "")),
        ),
    )[:limit]


def _source_chunk_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _group_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("language", "")),
        str(record.get("source_log", "")),
        str(record.get("review_group_id", "")),
    )


def _expected_group_key(record: dict[str, Any]) -> str:
    return json.dumps(
        {
            "language": str(record.get("language", "")),
            "expected_final": list(record.get("expected_final_normalized", [])),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _case_definition_record(payload: dict[str, Any], *, path: Path, line_no: int) -> dict[str, Any]:
    expected_final = _normalized_list(payload.get("expected_final", []))
    raw_chunks = payload.get("chunks")
    if raw_chunks is None:
        raw_chunks = [payload.get("text", "")]
    chunks = [normalized_text(chunk) for chunk in raw_chunks if normalized_text(chunk)] if isinstance(raw_chunks, list) else []
    nested_expected_pairs: list[list[int]] = []
    for left_index, left in enumerate(expected_final):
        for right_index, right in enumerate(expected_final):
            if left_index >= right_index:
                continue
            if left and right and (left in right or right in left):
                nested_expected_pairs.append([left_index, right_index])
    return {
        "id": str(payload.get("id") or f"{path.name}:{line_no}").strip(),
        "language": str(payload.get("language", "")).strip().lower() or "en",
        "path": str(path),
        "line_no": line_no,
        "source_log": str(payload.get("source_log", "")).strip(),
        "source_chunk": payload.get("source_chunk"),
        "review_group_id": str(payload.get("review_group_id", "")).strip(),
        "expected_final_normalized": expected_final,
        "expected_sentence_count": len(expected_final),
        "chunk_count": len(chunks),
        "duplicate_expected_count": max(len(expected_final) - len(set(expected_final)), 0),
        "nested_expected_pairs": nested_expected_pairs,
        "expected_quality_flags": expected_quality_flags(expected_final),
        "input_evidence": case_input_evidence({"expected_final": expected_final, "chunks": chunks}),
    }


def _case_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id", ""),
        "language": record.get("language", ""),
        "path": record.get("path", ""),
        "line_no": record.get("line_no"),
        "source_log": record.get("source_log", ""),
        "source_chunk": record.get("source_chunk"),
        "review_group_id": record.get("review_group_id", ""),
        "expected_sentence_count": record.get("expected_sentence_count", 0),
        "expected_quality_flags": list(record.get("expected_quality_flags", [])),
        "input_evidence": dict(record.get("input_evidence", {})),
    }


def _case_definition_action_payload(record: dict[str, Any], *, action: str, reason: str) -> dict[str, Any]:
    return {
        **_case_payload(record),
        "action": action,
        "reason": reason,
        "expected_final_preview": list(record.get("expected_final_normalized", []))[:5],
    }


def _case_definition_action_summary(
    records: list[dict[str, Any]],
    *,
    mid_stream_candidates: list[dict[str, Any]],
    duplicate_group_limit: int,
) -> dict[str, Any]:
    """Classify case-definition review work before using cases as tuning evidence."""
    repeated_case_ids: set[str] = set()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("expected_final_normalized"):
            grouped[_expected_group_key(record)].append(record)
    for items in grouped.values():
        if len(items) > 1:
            repeated_case_ids.update(str(item.get("id", "")) for item in items)

    mid_stream_ids = {str(candidate.get("id", "")) for candidate in mid_stream_candidates}
    by_action: dict[str, dict[str, Any]] = {}

    def add(record: dict[str, Any], *, action: str, reason: str) -> None:
        bucket = by_action.setdefault(
            action,
            {
                "case_count": 0,
                "reason": reason,
                "language_counts": Counter(),
                "examples": [],
            },
        )
        bucket["case_count"] += 1
        bucket["language_counts"][str(record.get("language", ""))] += 1
        if len(bucket["examples"]) < duplicate_group_limit:
            bucket["examples"].append(
                _case_definition_action_payload(record, action=action, reason=reason)
            )

    logic_ready_count = 0
    for record in records:
        expected_count = int(record.get("expected_sentence_count", 0))
        if expected_count <= 0:
            continue
        record_id = str(record.get("id", ""))
        input_evidence = dict(record.get("input_evidence", {}))
        if not bool(input_evidence.get("fully_supported")):
            action = "remove_or_recut_expected_outside_replay_input"
            reason = (
                "expected_final is not fully represented in this case's replay chunks; "
                "do not use it as app-logic tuning evidence until the window or labels are fixed."
            )
            add(record, action=action, reason=reason)
            continue
        if not bool(input_evidence.get("observed_fully_supported", True)):
            action = "rewrite_expected_final_to_observed_stt_text"
            reason = (
                "expected_final has enough partial unit coverage but is not observed as raw STT text "
                "in the replay chunks; rewrite labels to observed STT text or recut the case."
            )
            add(record, action=action, reason=reason)
            continue
        if record_id in mid_stream_ids:
            action = "add_initial_final_or_recut_mid_stream_case"
            reason = (
                "the first expected sentence starts after a non-trivial replay prefix while "
                "initial_final is empty; verify whether the prefix was already finalized."
            )
            add(record, action=action, reason=reason)
            continue
        if record.get("expected_quality_flags"):
            action = "rewrite_expected_final_to_final_sentence_boundary"
            reason = (
                "expected_final has fragment or boundary-quality flags and may not match the "
                "final-only translation queue definition."
            )
            add(record, action=action, reason=reason)
            continue
        if record_id in repeated_case_ids:
            action = "deduplicate_or_justify_shifted_window_repeat"
            reason = (
                "the same expected_final group appears in multiple cases; keep only cases that "
                "add a distinct lifecycle failure."
            )
            add(record, action=action, reason=reason)
            continue
        logic_ready_count += 1

    ordered_actions = {
        action: {
            **bucket,
            "language_counts": dict(sorted(bucket["language_counts"].items())),
        }
        for action, bucket in sorted(
            by_action.items(),
            key=lambda item: (-int(item[1]["case_count"]), item[0]),
        )
    }
    review_case_count = sum(int(bucket["case_count"]) for bucket in ordered_actions.values())
    return {
        "interpretation": (
            "Actions are ordered by review priority. They are not app-logic failures; they mark "
            "cases that should be fixed, removed, or explicitly justified before being used as "
            "pipeline tuning evidence."
        ),
        "review_case_count": review_case_count,
        "logic_tuning_candidate_count": logic_ready_count,
        "by_action": ordered_actions,
    }


def _case_definition_review_summary(
    records: list[dict[str, Any]],
    *,
    duplicate_group_limit: int,
) -> dict[str, Any]:
    duplicate_expected_cases = [
        record
        for record in records
        if int(record.get("duplicate_expected_count", 0)) > 0
    ]
    nested_expected_cases = [
        record
        for record in records
        if record.get("nested_expected_pairs")
    ]
    weak_input_evidence_cases = [
        record
        for record in records
        if int(dict(record.get("input_evidence", {})).get("expected_count", 0)) > 0
        and not bool(dict(record.get("input_evidence", {})).get("has_evidence"))
    ]
    partial_input_evidence_cases = [
        record
        for record in records
        if bool(dict(record.get("input_evidence", {})).get("has_evidence"))
        and not bool(dict(record.get("input_evidence", {})).get("fully_supported"))
    ]
    unobserved_stt_text_cases = [
        record
        for record in records
        if bool(dict(record.get("input_evidence", {})).get("fully_supported"))
        and not bool(dict(record.get("input_evidence", {})).get("observed_fully_supported", True))
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("expected_final_normalized"):
            grouped[_expected_group_key(record)].append(record)
    repeated_groups = [items for items in grouped.values() if len(items) > 1]
    repeated_groups.sort(
        key=lambda items: (
            -len(items),
            str(items[0].get("language", "")),
            str(items[0].get("id", "")),
        )
    )
    return {
        "interpretation": (
            "These are case-definition review signals, not automatic deletion rules. "
            "Duplicate or nested expected sentences may be real repeated speech; repeated expected groups "
            "usually mean shifted-window samples from the same log region and should be deduplicated only "
            "after checking that they add no distinct lifecycle failure. Weak or partial input evidence "
            "means expected_final is not sufficiently represented in the replay chunks and should be "
            "fixed before using the case as app logic tuning evidence. Fully covered but unobserved STT "
            "text usually means expected_final was human-corrected away from the raw STT input."
        ),
        "duplicate_expected_case_count": len(duplicate_expected_cases),
        "nested_expected_case_count": len(nested_expected_cases),
        "repeated_expected_group_count": len(repeated_groups),
        "repeated_expected_case_count": sum(len(items) for items in repeated_groups),
        "weak_input_evidence_case_count": len(weak_input_evidence_cases),
        "partial_input_evidence_case_count": len(partial_input_evidence_cases),
        "unobserved_stt_text_case_count": len(unobserved_stt_text_cases),
        "duplicate_expected_cases": [
            {
                **_case_payload(record),
                "duplicate_expected_count": record.get("duplicate_expected_count", 0),
                "expected_final_preview": list(record.get("expected_final_normalized", []))[:8],
            }
            for record in duplicate_expected_cases[:duplicate_group_limit]
        ],
        "nested_expected_cases": [
            {
                **_case_payload(record),
                "nested_expected_pairs": list(record.get("nested_expected_pairs", [])),
                "expected_final_preview": list(record.get("expected_final_normalized", []))[:8],
            }
            for record in nested_expected_cases[:duplicate_group_limit]
        ],
        "weak_input_evidence_cases": [
            {
                **_case_payload(record),
                "expected_final_preview": list(record.get("expected_final_normalized", []))[:5],
            }
            for record in sorted(
                weak_input_evidence_cases,
                key=lambda item: (
                    float(dict(item.get("input_evidence", {})).get("coverage_avg", 0.0)),
                    str(item.get("language", "")),
                    str(item.get("id", "")),
                ),
            )[:duplicate_group_limit]
        ],
        "partial_input_evidence_cases": [
            {
                **_case_payload(record),
                "expected_final_preview": list(record.get("expected_final_normalized", []))[:5],
            }
            for record in sorted(
                partial_input_evidence_cases,
                key=lambda item: (
                    float(dict(item.get("input_evidence", {})).get("coverage_avg", 0.0)),
                    str(item.get("language", "")),
                    str(item.get("id", "")),
                ),
            )[:duplicate_group_limit]
        ],
        "unobserved_stt_text_cases": [
            {
                **_case_payload(record),
                "expected_final_preview": list(record.get("expected_final_normalized", []))[:5],
            }
            for record in sorted(
                unobserved_stt_text_cases,
                key=lambda item: (
                    int(dict(item.get("input_evidence", {})).get("unobserved_count", 0)),
                    str(item.get("language", "")),
                    str(item.get("id", "")),
                ),
                reverse=True,
            )[:duplicate_group_limit]
        ],
        "repeated_expected_groups": [
            {
                "case_count": len(items),
                "language": str(items[0].get("language", "")),
                "expected_sentence_count": int(items[0].get("expected_sentence_count", 0)),
                "expected_quality_flags": dict(
                    sorted(
                        Counter(
                            flag
                            for item in items
                            for flag in item.get("expected_quality_flags", [])
                        ).items()
                    )
                ),
                "cases": [_case_payload(item) for item in items[:duplicate_group_limit]],
                "expected_final_preview": list(items[0].get("expected_final_normalized", []))[:5],
            }
            for items in repeated_groups[:duplicate_group_limit]
        ],
    }


def _candidate_score_groups(records: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(_group_key(record), []).append(record)
    summaries: list[dict[str, Any]] = []
    for (language, source_log, review_group_id), items in grouped.items():
        chunks = [
            chunk
            for chunk in (_source_chunk_value(item.get("source_chunk")) for item in items)
            if chunk is not None
        ]
        final_f1_avg = sum(_as_float(item.get("final_f1")) for item in items) / len(items)
        boundary_f1_avg = sum(_as_float(item.get("final_boundary_f1")) for item in items) / len(items)
        review_priority_score = len(items) * (1.0 - final_f1_avg) + (1.0 - boundary_f1_avg)
        summaries.append(
            {
                "language": language,
                "source_log": source_log,
                "review_group_id": review_group_id,
                "case_count": len(items),
                "source_chunk_min": min(chunks) if chunks else None,
                "source_chunk_max": max(chunks) if chunks else None,
                "final_f1_avg": final_f1_avg,
                "final_boundary_f1_avg": boundary_f1_avg,
                "review_priority_score": review_priority_score,
                "worst_case_id": min(
                    items,
                    key=lambda item: (
                        _as_float(item.get("final_f1")),
                        _as_float(item.get("final_boundary_f1")),
                        str(item.get("id", "")),
                    ),
                ).get("id", ""),
                "first_expected_samples": list(dict.fromkeys(str(item.get("first_expected", "")) for item in items))[:3],
            }
        )
    return sorted(
        summaries,
        key=lambda item: (
            -_as_float(item.get("review_priority_score")),
            _as_float(item.get("final_f1_avg")),
            _as_float(item.get("final_boundary_f1_avg")),
            str(item.get("language", "")),
            str(item.get("source_log", "")),
            str(item.get("review_group_id", "")),
        ),
    )[:limit]


def _candidate_group_metadata(cases: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    metadata: dict[tuple[str, str, str], dict[str, Any]] = {}
    for case in cases:
        key = _group_key(case)
        item = metadata.setdefault(
            key,
            {
                "total_case_count": 0,
                "source_chunks": [],
                "expected_quality_flags": Counter(),
                "expected_quality_case_count": 0,
            },
        )
        item["total_case_count"] += 1
        flags = [str(flag) for flag in case.get("expected_quality_flags", []) if str(flag)]
        if flags:
            item["expected_quality_case_count"] += 1
            item["expected_quality_flags"].update(flags)
        chunk = _source_chunk_value(case.get("source_chunk"))
        if chunk is not None:
            item["source_chunks"].append(chunk)
    return metadata


def _attach_group_metadata(
    groups: list[dict[str, Any]],
    group_metadata: dict[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for group in groups:
        item = dict(group)
        metadata = group_metadata.get(_group_key(item), {})
        total_case_count = int(metadata.get("total_case_count", 0))
        item["total_case_count"] = total_case_count
        item["candidate_case_ratio"] = item["case_count"] / total_case_count if total_case_count else 0.0
        expected_quality_case_count = int(metadata.get("expected_quality_case_count", 0))
        item["expected_quality_case_count"] = expected_quality_case_count
        item["expected_quality_case_ratio"] = (
            expected_quality_case_count / total_case_count if total_case_count else 0.0
        )
        quality_flags = metadata.get("expected_quality_flags", Counter())
        item["expected_quality_flags"] = dict(sorted(dict(quality_flags).items()))
        source_chunks = [
            chunk
            for chunk in metadata.get("source_chunks", [])
            if isinstance(chunk, int) and not isinstance(chunk, bool)
        ]
        item["group_source_chunk_min"] = min(source_chunks) if source_chunks else None
        item["group_source_chunk_max"] = max(source_chunks) if source_chunks else None
        updated.append(item)
    return updated


def _load_candidate_score_summary(
    benchmark_report: Path,
    candidates: list[dict[str, Any]],
    all_cases: list[dict[str, Any]],
    *,
    worst_limit: int,
    worst_group_limit: int,
) -> dict[str, Any]:
    payload = json.loads(benchmark_report.read_text(encoding="utf-8"))
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)]
    candidates_by_id = {str(candidate["id"]): candidate for candidate in candidates}
    quality_flags_by_id = {
        str(case.get("id", "")).strip(): list(case.get("expected_quality_flags", []))
        for case in all_cases
        if str(case.get("id", "")).strip()
    }
    candidate_cases: list[dict[str, Any]] = []
    non_candidate_cases: list[dict[str, Any]] = []
    expected_quality_cases: list[dict[str, Any]] = []
    without_expected_quality_cases: list[dict[str, Any]] = []
    candidate_expected_quality_cases: list[dict[str, Any]] = []
    candidate_without_expected_quality_cases: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        has_expected_quality_flags = bool(quality_flags_by_id.get(case_id))
        if has_expected_quality_flags:
            expected_quality_cases.append(case)
        else:
            without_expected_quality_cases.append(case)
        if case_id in candidates_by_id:
            candidate_cases.append(case)
            if has_expected_quality_flags:
                candidate_expected_quality_cases.append(case)
            else:
                candidate_without_expected_quality_cases.append(case)
        else:
            non_candidate_cases.append(case)
    candidate_records = [
        _case_score_record(case, candidates_by_id[str(case.get("id", "")).strip()])
        for case in candidate_cases
        if str(case.get("id", "")).strip() in candidates_by_id
    ]
    worst_groups = _candidate_score_groups(candidate_records, limit=worst_group_limit)
    return {
        "benchmark_report": str(benchmark_report),
        "candidate": _score_group_summary(candidate_cases),
        "non_candidate": _score_group_summary(non_candidate_cases),
        "expected_quality": _score_group_summary(expected_quality_cases),
        "without_expected_quality": _score_group_summary(without_expected_quality_cases),
        "candidate_expected_quality": _score_group_summary(candidate_expected_quality_cases),
        "candidate_without_expected_quality": _score_group_summary(candidate_without_expected_quality_cases),
        "worst_candidates": _worst_candidate_scores(cases, candidates_by_id, limit=worst_limit),
        "worst_groups": _attach_group_metadata(worst_groups, _candidate_group_metadata(all_cases)),
    }


def audit_initial_final_context(
    inputs: list[Path],
    *,
    min_prefix_units: int = DEFAULT_MIN_PREFIX_UNITS,
    preview_units: int = DEFAULT_PREVIEW_UNITS,
    benchmark_report: Path | None = None,
    worst_limit: int = DEFAULT_WORST_CASE_LIMIT,
    worst_group_limit: int = DEFAULT_WORST_GROUP_LIMIT,
    duplicate_group_limit: int = DEFAULT_DUPLICATE_GROUP_LIMIT,
) -> dict[str, Any]:
    paths = iter_case_paths(inputs)
    all_case_metadata: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    candidate_language_counts: Counter[str] = Counter()
    case_count = 0
    expected_final_case_count = 0
    initial_final_case_count = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                payload = json.loads(line)
                expected_final = _normalized_list(payload.get("expected_final", []))
                case_count += 1
                if expected_final:
                    expected_final_case_count += 1
                if _normalized_list(payload.get("initial_final", [])):
                    initial_final_case_count += 1
                all_case_metadata.append(
                    {
                        "id": str(payload.get("id") or f"{path.name}:{line_no}").strip(),
                        "language": str(payload.get("language", "")).strip().lower() or "en",
                        "source_log": str(payload.get("source_log", "")).strip(),
                        "source_chunk": payload.get("source_chunk"),
                        "review_group_id": str(payload.get("review_group_id", "")).strip(),
                        "expected_quality_flags": expected_quality_flags(expected_final),
                    }
                )
                all_case_metadata[-1].update(
                    _case_definition_record(payload, path=path, line_no=line_no)
                )
                candidate = _audit_payload(
                    payload,
                    path=path,
                    line_no=line_no,
                    min_prefix_units=min_prefix_units,
                    preview_units=preview_units,
                )
                if candidate is not None:
                    candidates.append(candidate)
                    candidate_language_counts[str(candidate.get("language", ""))] += 1
    summary: dict[str, Any] = {
        "case_count": case_count,
        "expected_final_case_count": expected_final_case_count,
        "initial_final_case_count": initial_final_case_count,
        "candidate_count": len(candidates),
        "candidate_language_counts": dict(sorted(candidate_language_counts.items())),
        "min_prefix_units": min_prefix_units,
        "interpretation": (
            "Candidates are cases whose first expected_final sentence appears after a non-trivial "
            "prefix inside an STT context window while initial_final is empty. They require log review "
            "before editing cases; this audit does not prove the prefix was already finalized."
        ),
        "case_definition_review": _case_definition_review_summary(
            all_case_metadata,
            duplicate_group_limit=duplicate_group_limit,
        ),
        "case_definition_action_summary": _case_definition_action_summary(
            all_case_metadata,
            mid_stream_candidates=candidates,
            duplicate_group_limit=duplicate_group_limit,
        ),
        "candidates": candidates,
    }
    if benchmark_report is not None:
        summary["score_summary"] = _load_candidate_score_summary(
            benchmark_report,
            candidates,
            all_case_metadata,
            worst_limit=worst_limit,
            worst_group_limit=worst_group_limit,
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit SBD cases that may need initial_final context for mid-stream replay."
    )
    parser.add_argument("cases", nargs="+", type=Path)
    parser.add_argument("--min-prefix-units", type=int, default=DEFAULT_MIN_PREFIX_UNITS)
    parser.add_argument("--preview-units", type=int, default=DEFAULT_PREVIEW_UNITS)
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        default=None,
        help="Optional CUDA benchmark report JSON used to compare candidate and non-candidate score strata.",
    )
    parser.add_argument("--worst-limit", type=int, default=DEFAULT_WORST_CASE_LIMIT)
    parser.add_argument("--worst-group-limit", type=int, default=DEFAULT_WORST_GROUP_LIMIT)
    parser.add_argument("--duplicate-group-limit", type=int, default=DEFAULT_DUPLICATE_GROUP_LIMIT)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    try:
        summary = audit_initial_final_context(
            args.cases,
            min_prefix_units=args.min_prefix_units,
            preview_units=args.preview_units,
            benchmark_report=args.benchmark_report,
            worst_limit=args.worst_limit,
            worst_group_limit=args.worst_group_limit,
            duplicate_group_limit=args.duplicate_group_limit,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-initial-final-audit] error: {exc}", file=sys.stderr)
        return 1

    output = dict(summary)
    if args.limit is not None:
        output["candidates"] = list(output["candidates"])[: args.limit]
        review = dict(output.get("case_definition_review", {}))
        for key in (
            "duplicate_expected_cases",
            "nested_expected_cases",
            "weak_input_evidence_cases",
            "partial_input_evidence_cases",
            "unobserved_stt_text_cases",
            "repeated_expected_groups",
        ):
            if isinstance(review.get(key), list):
                review[key] = list(review[key])[: args.limit]
        output["case_definition_review"] = review
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

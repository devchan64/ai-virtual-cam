#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPRESENTATIVE_MANIFEST_VERSION = 1
SAMPLING_RULE_PREFIX = "session-hash-v1"


def _as_counter(payload: object) -> Counter[str]:
    return Counter({str(key): int(value) for key, value in dict(payload or {}).items()})


def _dominant_key(counter_payload: object) -> str:
    counter = _as_counter(counter_payload)
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _has_marker(file_summary: dict[str, object], marker: str) -> bool:
    return int(dict(file_summary.get("marker_counts", {})).get(marker, 0)) > 0


def _has_runtime_metadata(file_summary: dict[str, object]) -> bool:
    return all(
        bool(dict(file_summary.get(field, {})))
        for field in (
            "stt_backend_counts",
            "stt_model_counts",
            "boundary_backend_counts",
            "window_seconds_counts",
            "step_seconds_counts",
            "sentence_finalize_age_counts",
        )
    )


def _canonical_runtime_values(counter_payload: object) -> set[str]:
    values: set[str] = set()
    for key in dict(counter_payload or {}):
        value = str(key).strip()
        if value.endswith("s"):
            value = value[:-1]
        try:
            values.add(str(float(value)))
        except ValueError:
            values.add(value)
    return values


def _has_single_runtime_value(file_summary: dict[str, object]) -> bool:
    runtime_fields = (
        "stt_backend_counts",
        "stt_model_counts",
        "window_seconds_counts",
        "step_seconds_counts",
        "sentence_finalize_age_counts",
    )
    return all(len(_canonical_runtime_values(file_summary.get(field))) == 1 for field in runtime_fields)


def _selection_hash(*, seed: str, language: str, path: str) -> str:
    return hashlib.sha256(f"{seed}\0{language}\0{path}".encode("utf-8")).hexdigest()


def _review_id(language: str, digest: str) -> str:
    return f"{language}_representative_review_{digest[:12]}"


def eligible_file_summaries(
    audit_summary: dict[str, object],
    *,
    require_runtime_metadata: bool,
    require_single_runtime: bool,
) -> list[dict[str, object]]:
    eligible: list[dict[str, object]] = []
    for file_summary in list(audit_summary.get("files", [])):
        if not isinstance(file_summary, dict):
            continue
        language = _dominant_key(file_summary.get("language_counts"))
        if not language:
            continue
        if not (
            _has_marker(file_summary, "stt_raw")
            and _has_marker(file_summary, "transcript")
            and _has_marker(file_summary, "finalize_event")
        ):
            continue
        if require_runtime_metadata and not _has_runtime_metadata(file_summary):
            continue
        if require_single_runtime and not _has_single_runtime_value(file_summary):
            continue
        eligible.append(file_summary)
    return eligible


def _candidate_record(
    file_summary: dict[str, object],
    *,
    seed: str,
    sampling_rule: str,
) -> dict[str, object]:
    language = _dominant_key(file_summary.get("language_counts"))
    path = str(file_summary.get("path", ""))
    digest = _selection_hash(seed=seed, language=language, path=path)
    return {
        "id": _review_id(language, digest),
        "corpus_role": "representative",
        "sampling_unit": "session-window",
        "sampling_rule": sampling_rule,
        "selection_hash": digest,
        "source_log": path,
        "source_started_at": str(file_summary.get("first_timestamp") or ""),
        "source_ended_at": str(file_summary.get("last_timestamp") or ""),
        "language": language,
        "stt_backend_candidates": dict(file_summary.get("stt_backend_counts", {})),
        "stt_model_candidates": dict(file_summary.get("stt_model_counts", {})),
        "boundary_backend_candidates": dict(file_summary.get("boundary_backend_counts", {})),
        "boundary_model_candidates": dict(file_summary.get("boundary_model_counts", {})),
        "translation_backend_candidates": dict(file_summary.get("translation_backend_counts", {})),
        "translation_model_candidates": dict(file_summary.get("translation_model_counts", {})),
        "window_seconds_candidates": dict(file_summary.get("window_seconds_counts", {})),
        "step_seconds_candidates": dict(file_summary.get("step_seconds_counts", {})),
        "sentence_finalize_age_candidates": dict(file_summary.get("sentence_finalize_age_counts", {})),
        "marker_counts": dict(file_summary.get("marker_counts", {})),
        "line_count": int(file_summary.get("line_count", 0)),
        "timestamped_line_count": int(file_summary.get("timestamped_line_count", 0)),
        "review_status": "requires_expected_final_review",
        "notes": [
            "This is a representative source review candidate, not a benchmark case.",
            "Confirm runtime metadata in the selected source window before creating a representative JSONL case.",
            "Do not copy Dictation AI transcript as expected_final without human review.",
        ],
    }


def select_representative_sources(
    audit_summary: dict[str, object],
    *,
    per_language: int,
    seed: str,
    require_runtime_metadata: bool = True,
    require_single_runtime: bool = True,
) -> dict[str, object]:
    sampling_rule = f"{SAMPLING_RULE_PREFIX}:seed={seed}:per_language={per_language}"
    eligible = eligible_file_summaries(
        audit_summary,
        require_runtime_metadata=require_runtime_metadata,
        require_single_runtime=require_single_runtime,
    )
    eligible_by_language: dict[str, list[tuple[str, dict[str, object]]]] = {}
    for file_summary in eligible:
        language = _dominant_key(file_summary.get("language_counts"))
        path = str(file_summary.get("path", ""))
        digest = _selection_hash(seed=seed, language=language, path=path)
        eligible_by_language.setdefault(language, []).append((digest, file_summary))

    selected: list[dict[str, object]] = []
    eligible_counts: Counter[str] = Counter()
    selected_counts: Counter[str] = Counter()
    for language, candidates in sorted(eligible_by_language.items()):
        ordered = sorted(candidates, key=lambda item: (item[0], str(item[1].get("path", ""))))
        eligible_counts[language] = len(ordered)
        for digest, file_summary in ordered[:per_language]:
            record = _candidate_record(file_summary, seed=seed, sampling_rule=sampling_rule)
            record["selection_hash"] = digest
            selected.append(record)
            selected_counts[language] += 1

    return {
        "representative_sampling_manifest_version": REPRESENTATIVE_MANIFEST_VERSION,
        "sampling_unit": "session-window",
        "sampling_rule": sampling_rule,
        "seed": seed,
        "per_language": per_language,
        "require_runtime_metadata": require_runtime_metadata,
        "require_single_runtime": require_single_runtime,
        "source_audit": {
            "source_count": audit_summary.get("source_count"),
            "first_timestamp": audit_summary.get("first_timestamp"),
            "last_timestamp": audit_summary.get("last_timestamp"),
            "representative_readiness": audit_summary.get("representative_readiness", {}),
        },
        "eligible_source_counts": dict(sorted(eligible_counts.items())),
        "selected_source_counts": dict(sorted(selected_counts.items())),
        "selected_source_count": len(selected),
        "selected_sources": selected,
        "interpretation": {
            "paper_evidence": False,
            "case_generation": False,
            "requires_human_expected_final": True,
            "claim_scope": "representative source review manifest only",
        },
    }


def write_markdown_manifest(manifest: dict[str, object], path: Path) -> None:
    rows = [
        "| id | language | source_log | started | ended | stt_backend | stt_model | windows | finalize_age |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in list(manifest.get("selected_sources", [])):
        if not isinstance(record, dict):
            continue
        rows.append(
            "| {id} | {language} | {source_log} | {source_started_at} | {source_ended_at} | {stt_backend} | {stt_model} | {windows} | {age} |".format(
                id=record.get("id", ""),
                language=record.get("language", ""),
                source_log=record.get("source_log", ""),
                source_started_at=record.get("source_started_at", ""),
                source_ended_at=record.get("source_ended_at", ""),
                stt_backend=", ".join(sorted(dict(record.get("stt_backend_candidates", {})).keys())),
                stt_model=", ".join(sorted(dict(record.get("stt_model_candidates", {})).keys())),
                windows=", ".join(sorted(dict(record.get("window_seconds_candidates", {})).keys())),
                age=", ".join(sorted(dict(record.get("sentence_finalize_age_candidates", {})).keys())),
            )
        )
    lines = [
        "# Representative Source Review Manifest",
        "",
        f"- sampling_unit: `{manifest.get('sampling_unit')}`",
        f"- sampling_rule: `{manifest.get('sampling_rule')}`",
        f"- selected_source_count: `{manifest.get('selected_source_count')}`",
        f"- eligible_source_counts: `{manifest.get('eligible_source_counts')}`",
        f"- selected_source_counts: `{manifest.get('selected_source_counts')}`",
        "- paper_evidence: `false`",
        "- case_generation: `false`",
        "- requires_human_expected_final: `true`",
        "",
        *rows,
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select representative Dictation AI source logs for human review.")
    parser.add_argument("audit_summary", type=Path, help="JSON output from audit_sbd_representative_sources.py")
    parser.add_argument("--per-language", type=int, default=2)
    parser.add_argument("--seed", default="20260621-representative-v1")
    parser.add_argument("--allow-missing-runtime-metadata", action="store_true")
    parser.add_argument("--allow-mixed-runtime", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, default=None)
    args = parser.parse_args()

    if args.per_language < 1:
        print("[dictation-ai-sbd-representative-selector] error: --per-language must be >= 1", file=sys.stderr)
        return 1
    try:
        audit_summary = json.loads(args.audit_summary.read_text(encoding="utf-8"))
        manifest = select_representative_sources(
            audit_summary,
            per_language=args.per_language,
            seed=args.seed,
            require_runtime_metadata=not args.allow_missing_runtime_metadata,
            require_single_runtime=not args.allow_mixed_runtime,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-representative-selector] error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output is not None:
        write_markdown_manifest(manifest, args.markdown_output)
    print(json.dumps({key: manifest[key] for key in ("selected_source_count", "eligible_source_counts", "selected_source_counts")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

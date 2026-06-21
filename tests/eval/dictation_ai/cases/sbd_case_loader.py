from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.app.sentence_boundary import normalized_text
from tests.eval.dictation_ai.cases.sbd_case_paths import (
    case_corpus_role,
    iter_case_paths,
    representative_metadata_record,
    validate_representative_payload,
)


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
    metadata: dict[str, object] | None = None


def _validated_case_paths(case_inputs: list[Path]) -> list[Path]:
    unique_paths = iter_case_paths(case_inputs)
    if not unique_paths:
        raise ValueError(f"no SBD benchmark case files matched: {', '.join(str(item) for item in case_inputs)}")
    missing = [path for path in unique_paths if not path.is_file()]
    if missing:
        raise ValueError("SBD benchmark case files not found: " + ", ".join(str(path) for path in missing))
    return unique_paths


def _load_case_file(path: Path, *, corpus_role: str) -> list[SbdCase]:
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
            normalized_chunks = [normalized_text(chunk) for chunk in chunks]
            if not any(normalized_chunks):
                raise ValueError(f"{path}:{line_no} case {case_id!r} has no text chunks")
            if bool(payload.get("draft_expected_final_required", False)):
                raise ValueError(
                    f"{path}:{line_no} case {case_id!r} is a draft case. "
                    "Review source logs and fill expected_final before using it in the benchmark."
                )
            if corpus_role == "representative":
                validate_representative_payload(payload, path=path, line_no=line_no, case_id=case_id)
                if not any(str(item).strip() for item in payload.get("expected_final", [])):
                    raise ValueError(f"{path}:{line_no} representative case {case_id!r} has no expected_final")
            metadata = representative_metadata_record(payload) if corpus_role == "representative" else None
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
                    metadata=metadata,
                )
            )
    if not cases:
        raise ValueError(f"no SBD benchmark cases loaded from {path}")
    return cases


def load_cases(case_inputs: list[Path]) -> tuple[list[SbdCase], list[str]]:
    cases: list[SbdCase] = []
    sources: list[str] = []
    seen_ids: dict[str, str] = {}
    corpus_role = case_corpus_role(case_inputs)
    for path in _validated_case_paths(case_inputs):
        loaded = _load_case_file(path, corpus_role=corpus_role)
        for case in loaded:
            previous = seen_ids.get(case.id)
            if previous is not None:
                raise ValueError(f"duplicate SBD benchmark case id {case.id!r}: {previous} and {path}")
            seen_ids[case.id] = str(path)
            cases.append(case)
        sources.append(str(path))
    if not cases:
        raise ValueError("no SBD benchmark cases loaded")
    return cases, sources

from __future__ import annotations

import re
from typing import Any

from src.app.dictation_transcript_logic import _word_units
from src.app.sentence_boundary import normalized_text


MIN_INPUT_EVIDENCE_COVERAGE = 0.60
OBSERVED_TEXT_RE = re.compile(r"[0-9A-Za-z가-힣\u3400-\u9fff]+")


def chunk_input_texts(case: dict[str, Any]) -> list[str]:
    chunks = case.get("chunks", [])
    if not isinstance(chunks, list):
        return []
    texts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            text = str(chunk.get("input", "")).strip()
        else:
            text = str(chunk).strip()
        if text:
            texts.append(text)
    return texts


def best_common_unit_run(left: list[str], right: list[str]) -> int:
    if not left or not right:
        return 0
    best = 0
    previous: dict[int, int] = {}
    for left_unit in left:
        current: dict[int, int] = {}
        for right_index, right_unit in enumerate(right):
            if left_unit != right_unit:
                continue
            run = previous.get(right_index - 1, 0) + 1
            current[right_index] = run
            best = max(best, run)
        previous = current
    return best


def expected_sentence_input_coverage(sentence: str, chunk_inputs: list[str]) -> float:
    expected_units = _word_units(normalized_text(sentence))
    if not expected_units:
        return 0.0
    best = 0.0
    for chunk_input in chunk_inputs:
        chunk_units = _word_units(normalized_text(chunk_input))
        if not chunk_units:
            continue
        run = best_common_unit_run(expected_units, chunk_units)
        best = max(best, run / max(len(expected_units), 1))
        if best >= 1.0:
            return 1.0
    return best


def compact_observed_text(text: str) -> str:
    return "".join(OBSERVED_TEXT_RE.findall(normalized_text(text).lower()))


def expected_sentence_observed(sentence: str, chunk_inputs: list[str]) -> bool:
    expected = compact_observed_text(sentence)
    if not expected:
        return False
    return any(expected in compact_observed_text(chunk_input) for chunk_input in chunk_inputs)


def case_input_evidence(case: dict[str, Any]) -> dict[str, Any]:
    expected_final = [
        str(sentence).strip()
        for sentence in case.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    chunk_inputs = chunk_input_texts(case)
    coverages = [
        expected_sentence_input_coverage(sentence, chunk_inputs)
        for sentence in expected_final
    ]
    observed = [
        expected_sentence_observed(sentence, chunk_inputs)
        for sentence in expected_final
    ]
    covered_count = sum(1 for value in coverages if value >= MIN_INPUT_EVIDENCE_COVERAGE)
    observed_count = sum(1 for value in observed if value)
    return {
        "expected_count": len(expected_final),
        "covered_count": covered_count,
        "observed_count": observed_count,
        "unobserved_count": max(len(expected_final) - observed_count, 0),
        "coverage_avg": sum(coverages) / max(len(coverages), 1),
        "coverage_min": min(coverages, default=0.0),
        "coverage_max": max(coverages, default=0.0),
        "fully_supported": bool(expected_final) and covered_count == len(expected_final),
        "observed_fully_supported": bool(expected_final) and observed_count == len(expected_final),
        "has_evidence": bool(expected_final) and covered_count > 0,
    }

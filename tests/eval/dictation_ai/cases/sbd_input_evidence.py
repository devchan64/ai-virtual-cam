from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from src.app.dictation_pipeline_settings import SENTENCE_CONFIRM_MAX_AGE_CHUNKS
from src.app.dictation_transcript_logic import _word_units
from src.app.sentence_boundary import normalized_text, sentence_end_count, split_punctuated_text


MIN_INPUT_EVIDENCE_COVERAGE = 0.60
MIN_REPEAT_SIMILARITY = 0.70
DEFAULT_REPEAT_OBSERVATIONS = SENTENCE_CONFIRM_MAX_AGE_CHUNKS
OBSERVED_TEXT_RE = re.compile(r"[0-9A-Za-z가-힣\u3400-\u9fff]+")
STABLE_CANDIDATE_EXAMPLE_LIMIT = 5


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


def has_observed_text_units(text: str) -> bool:
    return bool(OBSERVED_TEXT_RE.search(normalized_text(text)))


def chunk_sentence_candidates(chunk_input: str) -> list[str]:
    result = split_punctuated_text(chunk_input, "case-evidence")
    candidates = [
        sentence
        for sentence in result.completed
        if sentence and has_observed_text_units(sentence)
    ]
    pending = normalized_text(result.pending)
    if pending and has_observed_text_units(pending):
        candidates.append(pending)
    normalized_input = normalized_text(chunk_input)
    if not candidates and normalized_input and has_observed_text_units(normalized_input):
        candidates.append(normalized_input)
    return candidates


def chunk_input_sentence_candidates(chunk_inputs: list[str]) -> list[str]:
    candidates: list[str] = []
    for chunk_input in chunk_inputs:
        candidates.extend(chunk_sentence_candidates(chunk_input))
    return candidates


def expected_sentence_candidate_similarity(sentence: str, candidate: str) -> float:
    expected_units = _word_units(normalized_text(sentence))
    candidate_units = _word_units(normalized_text(candidate))
    if expected_units and candidate_units:
        matcher = SequenceMatcher(None, expected_units, candidate_units, autojunk=False)
        ratio = matcher.ratio()
        common_run = max((block.size for block in matcher.get_matching_blocks()), default=0)
        coverage = common_run / max(len(expected_units), 1)
        return max(ratio, coverage)
    return SequenceMatcher(None, normalized_text(sentence), normalized_text(candidate), autojunk=False).ratio()


def expected_sentence_repeat_count(sentence: str, sentence_candidates: list[str]) -> int:
    return sum(
        1
        for candidate in sentence_candidates
        if expected_sentence_candidate_similarity(sentence, candidate) >= MIN_REPEAT_SIMILARITY
    )


def expected_sentence_stable_group_count(sentence: str, stable_candidates: list[dict[str, Any]]) -> int:
    best_count = 0
    for candidate in stable_candidates:
        text = str(candidate.get("text", "")).strip()
        if not text:
            continue
        if expected_sentence_candidate_similarity(sentence, text) >= MIN_REPEAT_SIMILARITY:
            best_count = max(best_count, int(candidate.get("count", 0)))
    return best_count


def stable_candidate_representative_score(text: str) -> tuple[int, int]:
    normalized = normalized_text(text)
    has_terminal = 1 if sentence_end_count(normalized) > 0 else 0
    return has_terminal, len(_word_units(normalized))


def stable_repeated_sentence_candidates(
    sentence_candidates: list[str],
    *,
    min_observations: int = DEFAULT_REPEAT_OBSERVATIONS,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for index, candidate in enumerate(sentence_candidates):
        text = normalized_text(candidate)
        if not text or not has_observed_text_units(text):
            continue
        for group in groups:
            if expected_sentence_candidate_similarity(str(group["text"]), text) < MIN_REPEAT_SIMILARITY:
                continue
            group["count"] = int(group["count"]) + 1
            group["last_index"] = index
            if stable_candidate_representative_score(text) >= stable_candidate_representative_score(str(group["text"])):
                group["text"] = text
            break
        else:
            groups.append({"text": text, "count": 1, "first_index": index, "last_index": index})
    stable = [group for group in groups if int(group["count"]) >= min_observations]
    stable.sort(key=lambda group: (int(group["first_index"]), -int(group["count"]), str(group["text"])))
    return stable


def case_repeat_observations(case: dict[str, Any]) -> int:
    value = case.get("sentence_finalize_age", DEFAULT_REPEAT_OBSERVATIONS)
    try:
        observations = int(value)
    except (TypeError, ValueError):
        return DEFAULT_REPEAT_OBSERVATIONS
    return max(1, observations)


def compact_observed_text(text: str) -> str:
    return "".join(OBSERVED_TEXT_RE.findall(normalized_text(text).lower()))


def expected_sentence_observed(sentence: str, chunk_inputs: list[str]) -> bool:
    expected = compact_observed_text(sentence)
    if not expected:
        return False
    return any(expected in compact_observed_text(chunk_input) for chunk_input in chunk_inputs)


def case_stable_sentence_candidates(case: dict[str, Any]) -> list[dict[str, Any]]:
    chunk_inputs = chunk_input_texts(case)
    sentence_candidates = chunk_input_sentence_candidates(chunk_inputs)
    return stable_repeated_sentence_candidates(
        sentence_candidates,
        min_observations=case_repeat_observations(case),
    )


def case_input_evidence(case: dict[str, Any]) -> dict[str, Any]:
    expected_final = [
        str(sentence).strip()
        for sentence in case.get("expected_final", []) or []
        if str(sentence).strip()
    ]
    chunk_inputs = chunk_input_texts(case)
    sentence_candidates = chunk_input_sentence_candidates(chunk_inputs)
    required_repeat_observations = case_repeat_observations(case)
    stable_candidates = case_stable_sentence_candidates(case)
    coverages = [
        expected_sentence_input_coverage(sentence, chunk_inputs)
        for sentence in expected_final
    ]
    observed = [
        expected_sentence_observed(sentence, chunk_inputs)
        for sentence in expected_final
    ]
    repeat_counts = [
        expected_sentence_repeat_count(sentence, sentence_candidates)
        for sentence in expected_final
    ]
    stable_group_counts = [
        expected_sentence_stable_group_count(sentence, stable_candidates)
        for sentence in expected_final
    ]
    covered_count = sum(1 for value in coverages if value >= MIN_INPUT_EVIDENCE_COVERAGE)
    observed_count = sum(1 for value in observed if value)
    stable_repeat_count = sum(1 for value in stable_group_counts if value >= required_repeat_observations)
    return {
        "expected_count": len(expected_final),
        "covered_count": covered_count,
        "observed_count": observed_count,
        "stable_repeat_count": stable_repeat_count,
        "required_repeat_observations": required_repeat_observations,
        "unobserved_count": max(len(expected_final) - observed_count, 0),
        "coverage_avg": sum(coverages) / max(len(coverages), 1),
        "coverage_min": min(coverages, default=0.0),
        "coverage_max": max(coverages, default=0.0),
        "repeat_count_avg": sum(repeat_counts) / max(len(repeat_counts), 1),
        "repeat_count_min": min(repeat_counts, default=0),
        "repeat_count_max": max(repeat_counts, default=0),
        "stable_group_count_avg": sum(stable_group_counts) / max(len(stable_group_counts), 1),
        "stable_group_count_min": min(stable_group_counts, default=0),
        "stable_group_count_max": max(stable_group_counts, default=0),
        "stable_candidate_count": len(stable_candidates),
        "stable_candidate_examples": stable_candidates[:STABLE_CANDIDATE_EXAMPLE_LIMIT],
        "fully_supported": bool(expected_final) and covered_count == len(expected_final),
        "observed_fully_supported": bool(expected_final) and observed_count == len(expected_final),
        "stable_repeat_fully_supported": bool(expected_final) and stable_repeat_count == len(expected_final),
        "has_evidence": bool(expected_final) and covered_count > 0,
    }

from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from src.app.dictation_pipeline_settings import FINAL_SENTENCE_MATCH_MIN_SIMILARITY
from src.app.dictation_revision_text import _word_units
from src.app.sentence_boundary import normalized_text


def _boundary_offsets(sentences: list[str]) -> set[int]:
    offsets: set[int] = set()
    cursor = 0
    for sentence in sentences:
        normalized = normalized_text(sentence)
        if not normalized:
            continue
        cursor += len(normalized)
        offsets.add(cursor)
        cursor += 1
    return offsets


def score_boundary_offsets(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "exact": True,
        }
    expected_offsets = _boundary_offsets(expected_normalized)
    actual_offsets = _boundary_offsets(actual_normalized)
    true_positive = len(expected_offsets & actual_offsets)
    false_positive = len(actual_offsets - expected_offsets)
    false_negative = len(expected_offsets - actual_offsets)
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact": actual_normalized == expected_normalized,
    }


def _join_sentence_group(sentences: list[str], start: int, end: int) -> str:
    return " ".join(sentence for sentence in sentences[start:end] if sentence).strip()


def _sentence_similarity(left: str, right: str) -> float:
    left_words = _word_units(left)
    right_words = _word_units(right)
    if left_words and right_words:
        return SequenceMatcher(None, left_words, right_words, autojunk=False).ratio()
    return SequenceMatcher(None, normalized_text(left), normalized_text(right), autojunk=False).ratio()


def _empty_sequence_score() -> dict[str, Any]:
    return {
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "similarity_avg": 1.0,
        "similarity_coverage": 1.0,
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "exact": True,
    }


def score_boundary_granularity_adjusted(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return _empty_sequence_score()

    @lru_cache(maxsize=None)
    def _best_alignment(
        expected_index: int,
        actual_index: int,
    ) -> tuple[int, int, float, int, int]:
        if expected_index >= len(expected_normalized) and actual_index >= len(actual_normalized):
            return (0, 0, 0.0, 0, 0)

        best = (0, 0, 0.0, 0, 0)

        def _take(candidate: tuple[int, int, float, int, int]) -> None:
            nonlocal best
            if candidate > best:
                best = candidate

        if expected_index < len(expected_normalized):
            _take(_best_alignment(expected_index + 1, actual_index))
        if actual_index < len(actual_normalized):
            _take(_best_alignment(expected_index, actual_index + 1))

        if expected_index < len(expected_normalized) and actual_index < len(actual_normalized):
            similarity = _sentence_similarity(expected_normalized[expected_index], actual_normalized[actual_index])
            if similarity >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
                tail = _best_alignment(expected_index + 1, actual_index + 1)
                _take((tail[0] + 1, tail[1] + 1, tail[2] + similarity, tail[3], tail[4]))

            for end in range(actual_index + 2, len(actual_normalized) + 1):
                grouped_actual = _join_sentence_group(actual_normalized, actual_index, end)
                similarity = _sentence_similarity(expected_normalized[expected_index], grouped_actual)
                if similarity < FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
                    continue
                span = end - actual_index
                tail = _best_alignment(expected_index + 1, end)
                _take((tail[0] + 1, tail[1] + span, tail[2] + (similarity * span), tail[3] + 1, tail[4]))

            for end in range(expected_index + 2, len(expected_normalized) + 1):
                grouped_expected = _join_sentence_group(expected_normalized, expected_index, end)
                similarity = _sentence_similarity(grouped_expected, actual_normalized[actual_index])
                if similarity < FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
                    continue
                span = end - expected_index
                tail = _best_alignment(end, actual_index + 1)
                _take((tail[0] + span, tail[1] + 1, tail[2] + (similarity * span), tail[3], tail[4] + 1))
        return best

    matched_expected, matched_actual, weighted_similarity, split_support_count, merge_support_count = _best_alignment(0, 0)
    false_positive = len(actual_normalized) - matched_actual
    false_negative = len(expected_normalized) - matched_expected
    precision = matched_actual / max(len(actual_normalized), 1)
    recall = matched_expected / max(len(expected_normalized), 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    matched_units = max(matched_expected, matched_actual, 1)
    similarity_avg = weighted_similarity / matched_units
    similarity_coverage = weighted_similarity / max(len(expected_normalized), len(actual_normalized), 1)
    return {
        "true_positive": matched_expected,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_avg": similarity_avg,
        "similarity_coverage": similarity_coverage,
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "exact": actual_normalized == expected_normalized,
        "split_support_count": split_support_count,
        "merge_support_count": merge_support_count,
    }


def score_sequence(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return _empty_sequence_score()
    used_actual: set[int] = set()
    matched_similarities: list[float] = []
    for expected_sentence in expected_normalized:
        best_index = -1
        best_similarity = 0.0
        for actual_index, actual_sentence in enumerate(actual_normalized):
            if actual_index in used_actual:
                continue
            similarity = _sentence_similarity(expected_sentence, actual_sentence)
            if similarity > best_similarity:
                best_index = actual_index
                best_similarity = similarity
        if best_index >= 0 and best_similarity >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            used_actual.add(best_index)
            matched_similarities.append(best_similarity)
    true_positive = len(matched_similarities)
    false_positive = len(actual_normalized) - len(used_actual)
    false_negative = len(expected_normalized) - true_positive
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    similarity_avg = sum(matched_similarities) / max(true_positive, 1)
    similarity_coverage = sum(matched_similarities) / max(len(expected_normalized), len(actual_normalized), 1)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_avg": similarity_avg,
        "similarity_coverage": similarity_coverage,
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "exact": actual_normalized == expected_normalized,
    }


def score_ordered_sequence(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_normalized = [normalized_text(item) for item in expected if normalized_text(item)]
    actual_normalized = [normalized_text(item) for item in actual if normalized_text(item)]
    if not expected_normalized and not actual_normalized:
        return _empty_sequence_score()
    actual_index = 0
    matched_similarities: list[float] = []
    for expected_sentence in expected_normalized:
        best_index = -1
        best_similarity = 0.0
        for index in range(actual_index, len(actual_normalized)):
            similarity = _sentence_similarity(expected_sentence, actual_normalized[index])
            if similarity > best_similarity:
                best_index = index
                best_similarity = similarity
        if best_index >= 0 and best_similarity >= FINAL_SENTENCE_MATCH_MIN_SIMILARITY:
            actual_index = best_index + 1
            matched_similarities.append(best_similarity)
    true_positive = len(matched_similarities)
    false_positive = len(actual_normalized) - true_positive
    false_negative = len(expected_normalized) - true_positive
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    similarity_avg = sum(matched_similarities) / max(true_positive, 1)
    similarity_coverage = sum(matched_similarities) / max(len(expected_normalized), len(actual_normalized), 1)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_avg": similarity_avg,
        "similarity_coverage": similarity_coverage,
        "match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
        "exact": actual_normalized == expected_normalized,
    }

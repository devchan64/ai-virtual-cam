from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.app.dictation.pipeline_settings import (
    cjk_confirm_preserve_common_run_min as _cjk_confirm_preserve_common_run_min,
    cjk_confirm_preserve_coverage_min as _cjk_confirm_preserve_coverage_min,
    cjk_confirm_preserve_prefix_growth_max_delta as _cjk_confirm_preserve_prefix_growth_max_delta,
    cjk_confirm_preserve_ratio_min as _cjk_confirm_preserve_ratio_min,
    cjk_revision_common_run_min as _cjk_revision_common_run_min,
    cjk_revision_coverage_min as _cjk_revision_coverage_min,
    cjk_revision_fallback_ratio_min as _cjk_revision_fallback_ratio_min,
    cjk_revision_max_length_delta as _cjk_revision_max_length_delta,
    cjk_revision_ratio_min as _cjk_revision_ratio_min,
    cjk_revision_short_max_units as _cjk_revision_short_max_units,
    revision_fallback_common_run_min as _revision_fallback_common_run_min,
    revision_fallback_coverage_min as _revision_fallback_coverage_min,
    revision_prefix_common_run_min as _revision_prefix_common_run_min,
    revision_prefix_run_min as _revision_prefix_run_min,
    revision_tail_best_j_max as _revision_tail_best_j_max,
    revision_tail_common_run_min as _revision_tail_common_run_min,
    short_cjk_final_units as _short_cjk_final_units,
    short_mixed_latin_zh_cjk_units as _short_mixed_latin_zh_cjk_units,
    short_mixed_latin_zh_total_units as _short_mixed_latin_zh_total_units,
    short_no_end_fragment_units as _short_no_end_fragment_units,
)
from src.app.dictation_core.sentence_boundary import sentence_end_count as _boundary_sentence_end_count


def _compact_cjk_internal_spaces(text: str) -> str:
    chars = list(text)
    compacted: list[str] = []
    for index, char in enumerate(chars):
        if char == " " and compacted and index + 1 < len(chars):
            left = compacted[-1]
            right = chars[index + 1]
            if "\u3400" <= left <= "\u9fff" and "\u3400" <= right <= "\u9fff":
                continue
        compacted.append(char)
    return "".join(compacted)


def _normalized_text(text: str) -> str:
    return _compact_cjk_internal_spaces(" ".join(str(text).split()))


def _text_units(text: str) -> tuple[list[str], str]:
    normalized = _normalized_text(text)
    if not normalized:
        return [], " "
    if " " in normalized:
        return normalized.split(), " "
    return list(normalized), ""


def _join_text_units(units: list[str], separator: str) -> str:
    return separator.join(units).strip()


def _stable_window_text(text: str, *_unused_timing_args: float) -> str:
    normalized = _normalized_text(text)
    return normalized


def _new_text_delta(committed_text: str, stable_text: str) -> str:
    committed = _normalized_text(committed_text)
    stable = _normalized_text(stable_text)
    if not stable:
        return ""
    if not committed:
        return stable
    if committed.endswith(stable):
        return ""
    committed_units, committed_separator = _text_units(committed)
    stable_units, stable_separator = _text_units(stable)
    if committed_separator != stable_separator:
        committed_units, stable_units = list(committed), list(stable)
        stable_separator = ""
    max_overlap = min(len(committed_units), len(stable_units))
    for overlap in range(max_overlap, 0, -1):
        if committed_units[-overlap:] == stable_units[:overlap]:
            return _join_text_units(stable_units[overlap:], stable_separator)
    if stable in committed:
        return ""
    return stable


_WORD_UNIT_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"\d+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"[A-Za-z가-힣]+|"
    r"[\u3400-\u4dbf\u4e00-\u9fff]"
)


def _word_units(text: str) -> list[str]:
    return [match.group(0).replace(",", "") for match in _WORD_UNIT_RE.finditer(_normalized_text(text).lower())]


def _is_subsequence_at(words: list[str], candidate: list[str], start: int) -> bool:
    return words[start : start + len(candidate)] == candidate


def _dedupe_adjacent_words(words: list[str]) -> list[str]:
    deduped: list[str] = []
    for word in words:
        if deduped and deduped[-1] == word:
            continue
        deduped.append(word)
    return deduped


def _duplicate_key_words(words: list[str]) -> list[str]:
    return _dedupe_adjacent_words(words)


def _contains_word_sequence(words: list[str], candidate: list[str]) -> bool:
    if not candidate or len(candidate) > len(words):
        return False
    for start in range(0, len(words) - len(candidate) + 1):
        if _is_subsequence_at(words, candidate, start):
            return True
    return False


def _longest_prefix_run_in_words(words: list[str], candidate: list[str]) -> int:
    best = 0
    for start in range(len(words)):
        length = 0
        while start + length < len(words) and length < len(candidate) and words[start + length] == candidate[length]:
            length += 1
        best = max(best, length)
    return best


def _longest_suffix_run_in_words(words: list[str], candidate: list[str]) -> int:
    best = 0
    for end in range(len(words), 0, -1):
        length = 0
        while end - 1 - length >= 0 and len(candidate) - 1 - length >= 0 and words[end - 1 - length] == candidate[len(candidate) - 1 - length]:
            length += 1
        best = max(best, length)
    return best


def _prefix_words_match(left: str, right: str) -> bool:
    return left == right


def _longest_prefix_revision_run(left_words: list[str], right_words: list[str]) -> int:
    length = 0
    while length < len(left_words) and length < len(right_words):
        if not _prefix_words_match(left_words[length], right_words[length]):
            break
        length += 1
    return length


_NUMERIC_FRAGMENT_PREFIXES = {"are", "is", "it", "its", "there"}
_NUMERIC_FRAGMENT_UNITS = {
    "pounds",
    "pound",
    "dollar",
    "dollars",
    "percent",
    "kg",
    "lbs",
    "kilometers",
    "miles",
    "mile",
    "hours",
    "minutes",
    "seconds",
    "degrees",
}
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?$")


def _number_runs(words: list[str]) -> list[tuple[str, int, int]]:
    runs: list[tuple[str, int, int]] = []
    i = 0
    while i < len(words):
        if _NUMBER_TOKEN_RE.fullmatch(words[i]):
            start = i
            value = words[i]
            i += 1
            while i < len(words) and _NUMBER_TOKEN_RE.fullmatch(words[i]):
                value += words[i]
                i += 1
            runs.append((value, start, i))
        else:
            i += 1
    return runs


def _extract_numeric_tokens(words: list[str]) -> set[str]:
    return {value for value, _start, _end in _number_runs(words)}


def _extract_of_numeric_tokens(words: list[str]) -> set[str]:
    values: set[str] = set()
    for value, start, _end in _number_runs(words):
        if start > 0 and words[start - 1] == "of":
            values.add(value)
    return values


def _numeric_value_sequence(words: list[str]) -> tuple[str, ...]:
    values: list[str] = []
    for word in words:
        digits = "".join(ch for ch in word if ch.isdigit())
        if digits:
            values.append(digits)
    return tuple(values)


def _share_stable_numeric_sequence(left_words: list[str], right_words: list[str]) -> bool:
    left_numbers = _numeric_value_sequence(left_words)
    right_numbers = _numeric_value_sequence(right_words)
    if len(left_numbers) < 2 or left_numbers != right_numbers:
        return False
    shorter = min(len(left_words), len(right_words))
    return shorter <= 12 and len(left_numbers) / max(shorter, 1) >= 0.25


def _hangul_compact_key(words: list[str]) -> str:
    compact = "".join(words)
    if not any("가" <= ch <= "힣" for ch in compact):
        return ""
    return compact


def _has_hangul_words(words: list[str]) -> bool:
    return any(any("가" <= ch <= "힣" for ch in word) for word in words)


def _has_latin_words(words: list[str]) -> bool:
    return any(any("a" <= ch <= "z" for ch in word.lower()) for word in words)


def _has_cjk_words(words: list[str]) -> bool:
    return any(any("\u3400" <= ch <= "\u9fff" for ch in word) for word in words)


def _is_cjk_text(text: str) -> bool:
    return _has_cjk_words(_word_units(text))


def _short_hangul_containment_revision(left_words: list[str], right_words: list[str]) -> bool:
    if not (1 <= len(left_words) <= 4 and len(right_words) > len(left_words)):
        return False
    if not _has_hangul_words(left_words) or not _has_hangul_words(right_words):
        return False
    left_key = _hangul_compact_key(left_words)
    if len(left_key) < 5:
        return False
    for start in range(0, len(right_words) - len(left_words) + 1):
        if _is_subsequence_at(right_words, left_words, start):
            return len(right_words) <= len(left_words) + 3
    return False


def _hangul_compact_revision_match(left_words: list[str], right_words: list[str]) -> bool:
    left_key = _hangul_compact_key(left_words)
    right_key = _hangul_compact_key(right_words)
    if not left_key or not right_key:
        return False
    shorter_len = min(len(left_key), len(right_key))
    if shorter_len < 8:
        return False
    if left_key == right_key:
        return True
    if shorter_len >= 8 and (left_key in right_key or right_key in left_key):
        return True
    matcher = SequenceMatcher(None, left_key, right_key)
    ratio = matcher.ratio()
    max_block = max((block.size for block in matcher.get_matching_blocks()), default=0)
    prefix_chars = 0
    while prefix_chars < shorter_len and left_key[prefix_chars] == right_key[prefix_chars]:
        prefix_chars += 1
    if prefix_chars >= 4 and max_block >= 5 and ratio >= 0.50:
        return True
    return max_block >= 5 and ratio >= 0.85


def _best_common_word_run(a_words: list[str], b_words: list[str]) -> tuple[int, int, int]:
    best_i = 0
    best_j = 0
    best_len = 0
    for i in range(len(a_words)):
        for j in range(len(b_words)):
            length = 0
            while i + length < len(a_words) and j + length < len(b_words) and a_words[i + length] == b_words[j + length]:
                length += 1
            if length > best_len:
                best_i = i
                best_j = j
                best_len = length
    return best_i, best_j, best_len


def _common_word_run(a_words: list[str], b_words: list[str]) -> int:
    _best_i, _best_j, best_len = _best_common_word_run(a_words, b_words)
    return best_len


def _sentence_delta_from_words(words: list[str]) -> str:
    return " ".join(words).strip()


def _korean_revision_delta(committed_words: list[str], sentence_words: list[str]) -> str | None:
    if not _has_hangul_words(committed_words) or not _has_hangul_words(sentence_words):
        return None

    if 1 <= len(committed_words) <= 4:
        committed_len = len(committed_words)
        for start in range(0, len(sentence_words) - committed_len + 1):
            if not _is_subsequence_at(sentence_words, committed_words, start):
                continue
            suffix_words = sentence_words[start + committed_len :]
            return _sentence_delta_from_words(suffix_words) if suffix_words else ""

    best_i, best_j, best_len = _best_common_word_run(committed_words, sentence_words)
    if best_len < 5:
        return None

    shorter = min(len(committed_words), len(sentence_words))
    suffix_words = sentence_words[best_j + best_len :]
    overlap_rate = best_len / max(shorter, 1)
    if best_i <= 1 and best_j <= 1 and overlap_rate >= 0.70 and len(suffix_words) <= 2:
        return ""
    if best_i + best_len == len(committed_words) and best_len >= 8 and len(suffix_words) <= 6:
        return _sentence_delta_from_words(suffix_words) if suffix_words else ""
    return None


def _cjk_delta_from_words(words: list[str]) -> str:
    return "".join(words).strip()


def _cjk_revision_delta(committed_words: list[str], sentence_words: list[str]) -> str | None:
    if not _has_cjk_words(committed_words) or not _has_cjk_words(sentence_words):
        return None
    committed_cjk_count = sum(1 for word in committed_words if _has_cjk_words([word]))
    sentence_cjk_count = sum(1 for word in sentence_words if _has_cjk_words([word]))
    if committed_cjk_count < 12 or sentence_cjk_count < 12:
        return None

    internal_blocks = [
        block
        for block in SequenceMatcher(None, committed_words, sentence_words, autojunk=False).get_matching_blocks()
        if (
            block.size >= 24
            and block.b >= 8
            and block.a + block.size < len(committed_words)
            and block.size / max(len(sentence_words), 1) >= 0.25
        )
    ]
    if internal_blocks:
        return ""

    tail_blocks = [
        block
        for block in SequenceMatcher(None, committed_words, sentence_words, autojunk=False).get_matching_blocks()
        if block.size >= 8 and block.a + block.size == len(committed_words)
    ]
    if tail_blocks:
        block = max(tail_blocks, key=lambda item: (item.size, item.b))
        suffix_words = sentence_words[block.b + block.size :]
        return _cjk_delta_from_words(suffix_words) if suffix_words else ""

    best_i, best_j, best_len = _best_common_word_run(committed_words, sentence_words)
    if best_len < 12:
        return None
    suffix_words = sentence_words[best_j + best_len :]
    if best_i + best_len == len(committed_words):
        return _cjk_delta_from_words(suffix_words) if suffix_words else ""
    coverage = best_len / max(len(sentence_words), 1)
    if coverage >= 0.85:
        return ""
    return None


def _is_numeric_fragment_echo(candidate_words: list[str], committed_words: list[str]) -> bool:
    if len(candidate_words) > 4 or not candidate_words:
        return False
    if candidate_words[0] not in _NUMERIC_FRAGMENT_PREFIXES:
        return False
    if len(candidate_words) < 3:
        return False

    numeric_words = _extract_numeric_tokens(candidate_words)
    if len(numeric_words) != 1:
        return False
    number = next(iter(numeric_words))

    committed_numbers = _extract_of_numeric_tokens(committed_words)
    if number not in committed_numbers:
        return False

    if candidate_words[-1] not in _NUMERIC_FRAGMENT_UNITS:
        return False
    return True


def _sentence_output_delta(committed_text: str, sentence: str) -> str:
    normalized = _normalized_text(sentence)
    if not normalized:
        return ""
    committed_normalized = _normalized_text(committed_text)
    if (
        committed_normalized
        and normalized.startswith(committed_normalized)
        and (_is_cjk_text(committed_normalized) or _is_cjk_text(normalized))
    ):
        return normalized[len(committed_normalized) :].lstrip(" ，,").strip()
    committed_words = _word_units(committed_text)
    sentence_words = _word_units(normalized)
    if not committed_words or not sentence_words:
        return normalized
    if _is_numeric_fragment_echo(sentence_words, committed_words):
        return ""
    korean_delta = _korean_revision_delta(committed_words, sentence_words)
    if korean_delta is not None:
        return korean_delta
    cjk_delta = _cjk_revision_delta(committed_words, sentence_words)
    if cjk_delta is not None:
        return cjk_delta
    if len(sentence_words) <= len(committed_words):
        for start in range(0, len(committed_words) - len(sentence_words) + 1):
            if _is_subsequence_at(committed_words, sentence_words, start):
                return ""

    if 1 <= len(committed_words) <= 4:
        for start in range(0, len(sentence_words) - len(committed_words) + 1):
            if _is_subsequence_at(sentence_words, committed_words, start):
                suffix_words = sentence_words[start + len(committed_words) :]
                if len(suffix_words) >= 3:
                    return _sentence_delta_from_words(suffix_words)

    committed_key_words = _duplicate_key_words(committed_words)
    sentence_key_words = _duplicate_key_words(sentence_words)
    if len(sentence_key_words) >= 5 and (
        _contains_word_sequence(committed_key_words, sentence_key_words)
        or _contains_word_sequence(sentence_key_words, committed_key_words)
    ):
        length_ratio = min(len(committed_key_words), len(sentence_key_words)) / max(len(committed_key_words), len(sentence_key_words), 1)
        if length_ratio >= 0.9:
            return ""

    prefix_len = max(
        _longest_prefix_run_in_words(committed_words, sentence_words),
        _longest_prefix_revision_run(committed_words, sentence_words),
    )
    suffix_len = _longest_suffix_run_in_words(committed_words, sentence_words)
    if prefix_len >= 3 or suffix_len >= 3:
        start = prefix_len if prefix_len >= 3 else 0
        end = len(sentence_words) - suffix_len if suffix_len >= 3 else len(sentence_words)
        if start >= end:
            return ""
        middle_words = sentence_words[start:end]
        if prefix_len >= 5 and len(committed_words) <= 10:
            return _sentence_delta_from_words(middle_words)
        if len(middle_words) <= max(2, len(sentence_words) // 2):
            return _sentence_delta_from_words(middle_words)

    best_i, best_j, best_len = _best_common_word_run(committed_words, sentence_words)
    coverage = best_len / max(len(sentence_words), 1)
    if coverage >= 0.85:
        return ""
    is_cjk_overlap = _has_cjk_words(committed_words) and _has_cjk_words(sentence_words)
    if best_j == 0 and best_len >= 4:
        suffix_words = sentence_words[best_len:]
        overlap_coverage = best_len / max(len(sentence_words), 1)
        if (not is_cjk_overlap) or best_i <= 1 or overlap_coverage >= 0.6:
            if len(suffix_words) >= 3:
                return _sentence_delta_from_words(suffix_words)
            return ""
    if best_i + best_len == len(committed_words) and 0 < best_j <= 3 and best_len >= 8:
        suffix_words = sentence_words[best_j + best_len :]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and best_j == 1 and best_len >= 4:
        overlap_coverage = best_len / max(len(sentence_words), 1)
        if is_cjk_overlap and overlap_coverage < 0.45:
            return normalized
        suffix_words = sentence_words[best_j + best_len :]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and best_j == 0 and best_len >= 2:
        suffix_words = sentence_words[best_len:]
        overlap_coverage = best_len / max(len(sentence_words), 1)
        if ((not is_cjk_overlap) or best_i <= 1 or overlap_coverage >= 0.6 or len(suffix_words) <= best_len) and (
            best_len >= 3 or len(suffix_words) >= 5
        ):
            return _sentence_delta_from_words(suffix_words)
    return normalized


def _revision_token_sentence_similarity(left_words: list[str], right_words: list[str]) -> tuple[float, int, float, int]:
    if not left_words or not right_words:
        return 0.0, 0, 0.0, 0
    matcher = SequenceMatcher(None, left_words, right_words, autojunk=False)
    ratio = matcher.ratio()
    common_run = max((block.size for block in matcher.get_matching_blocks()), default=0)
    shorter = min(len(left_words), len(right_words))
    longer = max(len(left_words), len(right_words))
    coverage = common_run / max(shorter, 1)
    length_delta = longer - shorter
    return ratio, common_run, coverage, length_delta


def _cjk_revision_similarity(left_words: list[str], right_words: list[str]) -> tuple[float, int, float, int]:
    if not (_has_cjk_words(left_words) and _has_cjk_words(right_words)):
        return 0.0, 0, 0.0, 0
    return _revision_token_sentence_similarity(left_words, right_words)


def _cjk_sentences_are_similar_revisions(left_words: list[str], right_words: list[str]) -> bool:
    ratio, common_run, coverage, length_delta = _cjk_revision_similarity(left_words, right_words)
    shorter = min(len(left_words), len(right_words))
    max_length_delta = _cjk_revision_max_length_delta()
    if shorter <= _cjk_revision_short_max_units() and common_run == shorter and length_delta <= max_length_delta:
        return True
    if shorter > _cjk_revision_short_max_units() and ratio >= _cjk_revision_ratio_min() and length_delta <= max_length_delta:
        return True
    if (
        common_run >= _cjk_revision_common_run_min()
        and coverage >= _cjk_revision_coverage_min()
        and ratio >= _cjk_revision_fallback_ratio_min()
        and length_delta <= max_length_delta
    ):
        return True
    return False


def _should_preserve_revision_confirmation_by_token_sentence(previous: str, preferred: str) -> bool:
    previous_words = _word_units(previous)
    preferred_words = _word_units(preferred)
    if not previous_words or not preferred_words:
        return False
    ratio, common_run, coverage, length_delta = _revision_token_sentence_similarity(previous_words, preferred_words)
    if (
        _has_cjk_words(previous_words)
        and _has_cjk_words(preferred_words)
        and previous_words == preferred_words[: len(previous_words)]
        and common_run == len(previous_words)
        and length_delta <= _cjk_confirm_preserve_prefix_growth_max_delta()
    ):
        return True
    if length_delta > _cjk_revision_max_length_delta():
        return False
    return ratio >= _cjk_confirm_preserve_ratio_min() or (
        common_run >= _cjk_confirm_preserve_common_run_min()
        and coverage >= _cjk_confirm_preserve_coverage_min()
    )


def _is_cjk_prefixed_truncated_revision(left: str, right: str) -> bool:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if not (_is_cjk_text(normalized_left) or _is_cjk_text(normalized_right)):
        return False
    if _boundary_sentence_end_count(normalized_left) == 0 or _boundary_sentence_end_count(normalized_right) == 0:
        return False
    left_words = _word_units(normalized_left)
    right_words = _word_units(normalized_right)
    if len(left_words) < 10 or len(right_words) < 9:
        return False
    matcher = SequenceMatcher(None, left_words, right_words, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    if not blocks:
        return False
    first = blocks[0]
    if first.b != 0 or not (3 <= first.a <= 12):
        return False
    if first.a + first.size != len(left_words):
        return False
    left_prefix_units = left_words[: first.a]
    right_suffix_units = right_words[first.size :]
    if not all(_has_cjk_words([word]) for word in left_prefix_units):
        return False
    return first.size >= 6 and len(right_suffix_units) >= 3


def _sentences_are_revisions(left: str, right: str) -> bool:
    left_words = _word_units(left)
    right_words = _word_units(right)
    if not left_words or not right_words:
        return False
    if left_words == right_words:
        return True
    if 1 <= len(left_words) <= 4 and len(right_words) > len(left_words):
        if all(_prefix_words_match(left_word, right_word) for left_word, right_word in zip(left_words, right_words)):
            return True
    if _share_stable_numeric_sequence(left_words, right_words):
        return True
    if _short_hangul_containment_revision(left_words, right_words):
        return True
    if _hangul_compact_revision_match(left_words, right_words):
        return True
    shorter = min(len(left_words), len(right_words))
    best_i, best_j, common_run = _best_common_word_run(left_words, right_words)
    prefix_run = _longest_prefix_revision_run(left_words, right_words)
    if _has_cjk_words(left_words) and _has_cjk_words(right_words):
        if _is_cjk_prefixed_truncated_revision(left, right) or _is_cjk_prefixed_truncated_revision(right, left):
            return True
        if _cjk_sentences_are_similar_revisions(left_words, right_words):
            return True
        tail_blocks = [
            block
            for block in SequenceMatcher(None, left_words, right_words, autojunk=False).get_matching_blocks()
            if block.size >= _revision_tail_common_run_min() and block.a + block.size == len(left_words)
        ]
        if tail_blocks:
            return True
    if (
        common_run >= _revision_tail_common_run_min()
        and best_i + common_run == len(left_words)
        and best_j <= _revision_tail_best_j_max()
    ):
        return True
    if (
        prefix_run >= _revision_prefix_run_min()
        and common_run >= _revision_prefix_common_run_min()
        and len(right_words) >= len(left_words)
    ):
        return True
    return common_run >= _revision_fallback_common_run_min() and common_run / max(shorter, 1) >= _revision_fallback_coverage_min()


def _has_unstable_mixed_latin_for_zh(words: list[str]) -> bool:
    latin_words = [word for word in words if any("a" <= ch <= "z" for ch in word.lower())]
    return len(latin_words) >= 2 or any(len(word) >= 4 for word in latin_words)


def _looks_like_open_latin_clause(text: str, words: list[str]) -> bool:
    if _boundary_sentence_end_count(text) > 0:
        return False
    if len(words) < 4 or not _has_latin_words(words) or _has_hangul_words(words):
        return False
    return True


def _has_cjk_internal_space_gap(text: str) -> bool:
    chars = list(text)
    for index, char in enumerate(chars):
        if char != " ":
            continue
        left_index = index - 1
        right_index = index + 1
        if left_index < 0 or right_index >= len(chars):
            continue
        left = chars[left_index]
        right = chars[right_index]
        if "\u3400" <= left <= "\u9fff" and "\u3400" <= right <= "\u9fff":
            return True
    return False


def _has_repeated_cjk_ngram(words: list[str]) -> bool:
    cjk_units = [word for word in words if _has_cjk_words([word])]
    if 4 <= len(cjk_units) <= _short_cjk_final_units() and len(set(cjk_units)) == 1:
        return True
    if len(cjk_units) < 40:
        return False
    for size in (14, 12, 10, 8):
        seen: dict[tuple[str, ...], int] = {}
        for index in range(0, len(cjk_units) - size + 1):
            ngram = tuple(cjk_units[index : index + size])
            if len(set(ngram)) < max(4, size // 3):
                continue
            previous = seen.get(ngram)
            if previous is not None and index - previous >= size:
                return True
            seen.setdefault(ngram, index)
    return False


def _has_repeated_word_ngram(words: list[str]) -> bool:
    if len(words) < 12:
        return False
    for size in (12, 10, 9, 8, 7, 6):
        seen: dict[tuple[str, ...], int] = {}
        for index in range(0, len(words) - size + 1):
            ngram = tuple(words[index : index + size])
            if len(set(ngram)) < max(4, size // 2):
                continue
            previous = seen.get(ngram)
            if previous is not None and index - previous >= size:
                return True
            seen.setdefault(ngram, index)
    return False


def _final_sentence_diagnostic_flags(sentence: str, language: str) -> tuple[str, ...]:
    normalized = _normalized_text(sentence)
    words = _word_units(normalized)
    flags: list[str] = []
    if not words:
        return ("empty",)
    if normalized.endswith("...") or normalized.endswith("…"):
        flags.append("trailing_ellipsis")
    normalized_language = str(language or "").strip().lower()
    has_cjk = _has_cjk_words(words)
    has_latin = _has_latin_words(words)
    cjk_units = [word for word in words if _has_cjk_words([word])]
    if _has_repeated_word_ngram(words):
        flags.append("repeated_word_ngram")
    if normalized_language == "zh" or has_cjk:
        if 0 < len(cjk_units) <= _short_cjk_final_units():
            flags.append("short_cjk")
        if 0 < len(cjk_units) <= 3 and _boundary_sentence_end_count(normalized) == 0:
            flags.append("low_value_cjk_fragment")
        text_units, separator = _text_units(normalized)
        cjk_text_units = [unit for unit in text_units if _has_cjk_words(_word_units(unit))]
        single_cjk_text_units = [unit for unit in cjk_text_units if len(_word_units(unit)) == 1]
        if separator == " " and len(single_cjk_text_units) >= 8 and len(single_cjk_text_units) / max(len(cjk_text_units), 1) >= 0.70:
            flags.append("spaced_cjk")
        if _has_cjk_internal_space_gap(normalized):
            flags.append("cjk_internal_gap")
        if _has_repeated_cjk_ngram(words):
            flags.append("cjk_repeated_ngram")
    if normalized_language == "zh" and has_latin and not has_cjk:
        flags.append("latin_only_for_zh")
    elif normalized_language == "zh" and has_latin and has_cjk and _has_unstable_mixed_latin_for_zh(words):
        flags.append("mixed_latin_zh")
        if (
            0 < len(cjk_units) <= _short_mixed_latin_zh_cjk_units()
            and len(words) <= _short_mixed_latin_zh_total_units()
        ):
            flags.append("short_mixed_latin_zh")
    if _boundary_sentence_end_count(normalized) == 0:
        flags.append("no_end_marker")
        if len(words) <= _short_no_end_fragment_units() or (
            has_cjk and 0 < len(cjk_units) <= _short_cjk_final_units()
        ):
            flags.append("short_no_end_fragment")
    return tuple(flags)

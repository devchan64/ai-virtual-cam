from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.app.dictation_pipeline_settings import (
    CJK_REVISION_INTERNAL_STABILITY_MID_RATIO,
    CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS,
    CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO,
    FAST_PENDING_OVERRUN_CHARS,
    FAST_PENDING_OVERRUN_CHUNKS,
    MAX_PENDING_SENTENCE_CHARS,
    PENDING_OVERRUN_CHUNKS,
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
    forced_sentence_confirm_chunks as _forced_sentence_confirm_chunks,
    forced_sentence_confirm_max_age_chunks as _forced_sentence_confirm_max_age_chunks,
    revision_fallback_common_run_min as _revision_fallback_common_run_min,
    revision_fallback_coverage_min as _revision_fallback_coverage_min,
    revision_prefix_common_run_min as _revision_prefix_common_run_min,
    revision_prefix_run_min as _revision_prefix_run_min,
    revision_similarity_policy as _revision_similarity_policy,
    revision_tail_best_j_max as _revision_tail_best_j_max,
    revision_tail_common_run_min as _revision_tail_common_run_min,
    recent_final_extension_min_prefix_units as _recent_final_extension_min_prefix_units,
    recent_final_extension_min_suffix_units as _recent_final_extension_min_suffix_units,
    recent_final_fragment_echo_coverage_min as _recent_final_fragment_echo_coverage_min,
    recent_final_fragment_echo_max_length_ratio as _recent_final_fragment_echo_max_length_ratio,
    recent_final_fragment_echo_max_unmatched_units as _recent_final_fragment_echo_max_unmatched_units,
    recent_final_fragment_echo_min_units as _recent_final_fragment_echo_min_units,
    recent_final_no_end_suffix_echo_coverage_min as _recent_final_no_end_suffix_echo_coverage_min,
    recent_final_no_end_suffix_echo_min_units as _recent_final_no_end_suffix_echo_min_units,
    recent_final_no_end_suffix_echo_similarity_min as _recent_final_no_end_suffix_echo_similarity_min,
    recent_final_tail_anchor_min_units as _recent_final_tail_anchor_min_units,
    sentence_confirm_chunks as _sentence_confirm_chunks,
    sentence_confirm_max_age_chunks as _sentence_confirm_max_age_chunks,
    short_cjk_confirm_extra_chunks as _short_cjk_confirm_extra_chunks,
    short_cjk_final_units as _short_cjk_final_units,
    short_cjk_replacement_hold_chunks as _short_cjk_replacement_hold_chunks,
    short_mixed_latin_zh_cjk_units as _short_mixed_latin_zh_cjk_units,
    short_mixed_latin_zh_total_units as _short_mixed_latin_zh_total_units,
    short_no_end_fragment_units as _short_no_end_fragment_units,
)
from src.app.sentence_boundary import (
    sentence_end_count as _boundary_sentence_end_count,
    split_completed_sentences as _boundary_split_completed_sentences,
)


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


def _has_hangul_words(words: list[str]) -> bool:
    return any(any("가" <= ch <= "힣" for ch in word) for word in words)


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

def _sentence_delta_from_words(words: list[str]) -> str:
    return " ".join(words).strip()


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

    best_i = 0
    best_j = 0
    best_len = 0
    for i in range(len(committed_words)):
        for j in range(len(sentence_words)):
            length = 0
            while (
                i + length < len(committed_words)
                and j + length < len(sentence_words)
                and committed_words[i + length] == sentence_words[j + length]
            ):
                length += 1
            if length > best_len:
                best_i = i
                best_j = j
                best_len = length
    coverage = best_len / max(len(sentence_words), 1)
    if coverage >= 0.85:
        return ""
    if best_j == 0 and best_len >= 4:
        suffix_words = sentence_words[best_len:]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and 0 < best_j <= 3 and best_len >= 8:
        suffix_words = sentence_words[best_j + best_len :]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and best_j == 1 and best_len >= 4:
        suffix_words = sentence_words[best_j + best_len :]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and best_j == 0 and best_len >= 2:
        suffix_words = sentence_words[best_len:]
        if best_len >= 3 or len(suffix_words) >= 5:
            return _sentence_delta_from_words(suffix_words)
    return normalized


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


def _sentence_required_confirmations(forced: bool) -> int:
    return _forced_sentence_confirm_chunks() if forced else _sentence_confirm_chunks()


def _sentence_max_age_chunks(forced: bool, base_age: int | None = None) -> int:
    if base_age is None:
        return _forced_sentence_confirm_max_age_chunks() if forced else _sentence_confirm_max_age_chunks()
    normalized_base_age = max(1, int(base_age))
    return normalized_base_age + 1 if forced else normalized_base_age


def _stage_quality_block_age_limit(sentence: str, language: str, forced: bool, base_age: int | None = None) -> int:
    limit = _sentence_max_age_chunks(forced, base_age)
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if (
        _is_cjk_text(sentence)
        and "short_cjk" in flags
        and not flags.intersection({"no_end_marker", "short_no_end_fragment", "low_value_cjk_fragment"})
    ):
        return limit + _short_cjk_replacement_hold_chunks()
    return limit


def _has_latin_words(words: list[str]) -> bool:
    return any(any("a" <= ch <= "z" for ch in word.lower()) for word in words)


def _has_unstable_mixed_latin_for_zh(words: list[str]) -> bool:
    latin_words = [word for word in words if any("a" <= ch <= "z" for ch in word.lower())]
    return len(latin_words) >= 2 or any(len(word) >= 4 for word in latin_words)


def _looks_like_open_latin_clause(text: str, words: list[str]) -> bool:
    if _boundary_sentence_end_count(text) > 0:
        return False
    if len(words) < 4 or not _has_latin_words(words) or _has_hangul_words(words):
        return False
    return True


def _has_cjk_words(words: list[str]) -> bool:
    return any(any("\u3400" <= ch <= "\u9fff" for ch in word) for word in words)


def _is_cjk_text(text: str) -> bool:
    return _has_cjk_words(_word_units(text))


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


def _has_later_completed_extension(candidate: str, later_sentences: list[str] | tuple[str, ...]) -> bool:
    normalized_candidate = _normalized_text(candidate)
    if not normalized_candidate or _boundary_sentence_end_count(normalized_candidate) > 0:
        return False
    for sentence in later_sentences:
        normalized_later = _normalized_text(sentence)
        if _boundary_sentence_end_count(normalized_later) == 0:
            continue
        if not normalized_later.startswith(normalized_candidate):
            continue
        if len(normalized_later) - len(normalized_candidate) >= 4:
            return True
    return False


def _is_pending_prefix_mixed_candidate(candidate: str, pending_text: str) -> bool:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(pending_text)
    if (
        not normalized_candidate
        or not normalized_pending
    ):
        return False
    candidate_units = _word_units(normalized_candidate)
    pending_units = _word_units(normalized_pending)
    if len(candidate_units) < 5 or len(pending_units) < 5:
        return False
    common_prefix = 0
    for candidate_unit, pending_unit in zip(candidate_units, pending_units):
        if candidate_unit != pending_unit:
            break
        common_prefix += 1
    if common_prefix < 4:
        return False
    if common_prefix == len(candidate_units) or common_prefix == len(pending_units):
        return False
    return True


def _is_prior_pending_recent_final_mixed_candidate(
    candidate: str,
    prior_pending_text: str,
    recent_sentences: list[str] | tuple[str, ...],
    language: str,
) -> bool:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(prior_pending_text)
    if not normalized_candidate or not normalized_pending or not recent_sentences:
        return False
    candidate_words = _word_units(normalized_candidate)
    pending_words = _word_units(normalized_pending)
    if candidate_words[: len(pending_words)] != pending_words:
        return False
    suffix_words = candidate_words[len(pending_words) :]
    if len(pending_words) >= 2 and 1 <= len(suffix_words) <= 3:
        suffix_key = "".join(suffix_words).lower()
        if len(suffix_key) < 6:
            return False
        for recent in reversed(recent_sentences):
            recent_words = _word_units(recent)
            if len(recent_words) < len(suffix_words) + 2:
                continue
            recent_suffix_key = "".join(recent_words[-len(suffix_words) :]).lower()
            if SequenceMatcher(None, recent_suffix_key, suffix_key, autojunk=False).ratio() >= 0.86:
                return True
        return False
    if len(pending_words) < 3 or len(suffix_words) < 4:
        return False
    suffix_text = _sentence_delta_from_words(suffix_words)
    for recent in reversed(recent_sentences):
        recent_words = _word_units(recent)
        if len(recent_words) < len(suffix_words):
            continue
        if _recent_final_sentence_delta(suffix_text, recent, language) == "":
            return True
        ratio = SequenceMatcher(None, recent_words, suffix_words, autojunk=False).ratio()
        _best_i, best_j, common_run = _best_common_word_run(recent_words, suffix_words)
        suffix_coverage = common_run / max(len(suffix_words), 1)
        if best_j <= 3 and common_run >= 4 and (ratio >= 0.55 or suffix_coverage >= 0.55):
            return True
    return False


def _staged_sentence_required_confirmations(staged_sentence: str, staged_forced: bool) -> int:
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh" if _is_cjk_text(staged_sentence) else ""))
    required_confirmations = _sentence_required_confirmations(staged_forced)
    if "short_cjk" in flags and "no_end_marker" not in flags:
        required_confirmations += _short_cjk_confirm_extra_chunks()
    return required_confirmations


def _should_confirm_staged_sentence(
    staged_sentence: str,
    staged_confirmations: int,
    staged_forced: bool,
) -> bool:
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh" if _is_cjk_text(staged_sentence) else ""))
    if "repeated_word_ngram" in flags:
        return False
    if _is_cjk_text(staged_sentence):
        if flags.intersection({"empty", "no_end_marker", "spaced_cjk", "cjk_repeated_ngram"}):
            return False
    return staged_confirmations >= _staged_sentence_required_confirmations(staged_sentence, staged_forced)


def _should_preserve_partial_replacement(staged_sentence: str, candidate: str) -> bool:
    staged_words = _word_units(staged_sentence)
    candidate_words = _word_units(candidate)
    if len(staged_words) < 4 or len(candidate_words) < 4:
        return False
    best_i, best_j, common_run = _best_common_word_run(staged_words, candidate_words)
    if common_run < 4:
        return False
    left_tail = best_i + common_run == len(staged_words)
    right_tail = best_j + common_run == len(candidate_words)
    if left_tail and right_tail:
        return True
    return _boundary_sentence_end_count(staged_sentence) > 0 and best_j == 0 and common_run >= 5


def _should_split_terminal_tail_revision(staged_sentence: str, candidate: str) -> bool:
    staged = _normalized_text(staged_sentence)
    candidate_text = _normalized_text(candidate)
    if not staged or not candidate_text or _boundary_sentence_end_count(staged) == 0:
        return False
    staged_words = _word_units(staged)
    candidate_words = _word_units(candidate_text)
    if len(staged_words) < 5 or len(candidate_words) < len(staged_words) + 3:
        return False
    best_i, best_j, common_run = _best_common_word_run(staged_words, candidate_words)
    if common_run < min(6, len(staged_words)):
        return False
    if best_i + common_run != len(staged_words):
        return False
    if best_j < 3:
        return False
    prefix_words = candidate_words[:best_j]
    if _contains_word_sequence(staged_words, prefix_words):
        return False
    return True


def _replacement_decision_reason(
    staged_sentence: str,
    candidate: str,
    staged_confirmations: int,
    staged_forced: bool,
    staged_age: int,
    sentence_finalize_age: int | None = None,
) -> str:
    staged_words = _word_units(staged_sentence)
    if not staged_words:
        return "empty"
    if _looks_like_open_latin_clause(staged_sentence, staged_words):
        return "open_latin_clause"
    if staged_confirmations >= _staged_sentence_required_confirmations(staged_sentence, staged_forced):
        return "confirmed"
    if _has_cjk_words(staged_words):
        flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh"))
        if (
            "short_cjk" in flags
            and "no_end_marker" not in flags
            and staged_age < _sentence_max_age_chunks(staged_forced, sentence_finalize_age) + _short_cjk_replacement_hold_chunks()
        ):
            return "unconfirmed_cjk"
    if staged_age >= _sentence_max_age_chunks(staged_forced, sentence_finalize_age):
        return "aged"
    if _has_cjk_words(staged_words):
        return "unconfirmed_cjk"

    candidate_delta = _sentence_output_delta(staged_sentence, candidate)
    if candidate_delta == "":
        return "duplicate_or_suffix"
    if candidate_delta != _normalized_text(candidate):
        if _should_preserve_partial_replacement(staged_sentence, candidate):
            return "partial_preserve"
        return "partial_revision"
    return "unconfirmed"


def _should_defer_unconfirmed_replacement(replacement_reason: str) -> bool:
    return replacement_reason in {
        "open_latin_clause",
        "unconfirmed",
        "unconfirmed_cjk",
    }


def _should_finalize_replaced_sentence(
    staged_sentence: str,
    candidate: str,
    language: str,
    staged_confirmations: int,
    staged_forced: bool,
    staged_age: int,
    sentence_finalize_age: int | None = None,
) -> bool:
    reason = _replacement_decision_reason(
        staged_sentence,
        candidate,
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_finalize_age,
    )
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, language))
    if "no_end_marker" in flags and staged_confirmations < _sentence_required_confirmations(staged_forced):
        return False
    if "trailing_ellipsis" in flags:
        return False
    if reason == "confirmed":
        return _should_confirm_staged_sentence(staged_sentence, staged_confirmations, staged_forced)
    if reason == "aged" and _is_cjk_text(staged_sentence):
        if flags.intersection({"empty", "short_cjk", "spaced_cjk", "cjk_internal_gap", "cjk_repeated_ngram"}):
            return False
    if "repeated_word_ngram" in flags:
        return False
    return reason in {"aged", "duplicate_or_suffix", "partial_preserve"}


def _format_transcript_metrics(metrics: dict[str, int]) -> str:
    parts = [f"{key}={metrics[key]}" for key in sorted(metrics) if metrics[key]]
    return ",".join(parts) if parts else "none"


def _should_translate_final_sentence(sentence: str, language: str) -> bool:
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    # final까지 도달한 문장은 길이가 짧아도 실시간 번역의 소비 대상이다.
    # 여기서는 환청성/공백성 final만 제외하고, stage 품질 게이트와 분리한다.
    return not flags.intersection(
        {
            "empty",
            "cjk_repeated_ngram",
            "repeated_word_ngram",
        }
    )


def _should_stage_boundary_candidate(sentence: str, language: str) -> bool:
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    return not flags.intersection(
        {
            "empty",
            "spaced_cjk",
            "cjk_repeated_ngram",
            "repeated_word_ngram",
            "short_mixed_latin_zh",
            "low_value_cjk_fragment",
            "short_no_end_fragment",
            "trailing_ellipsis",
        }
    )


def _coalesce_completed_short_no_end_fragments(
    sentences: list[str] | tuple[str, ...],
    language: str,
) -> tuple[str, ...]:
    coalesced: list[str] = []
    index = 0
    while index < len(sentences):
        current = _normalized_text(sentences[index])
        if (
            current
            and index + 1 < len(sentences)
            and _sentence_end_count(current) == 0
            and "short_no_end_fragment" in set(_final_sentence_diagnostic_flags(current, language))
        ):
            following = _normalized_text(sentences[index + 1])
            if following and _sentence_end_count(following) > 0:
                separator = "" if _is_cjk_text(current + following) else " "
                combined = _normalized_text(f"{current}{separator}{following}")
                if _should_stage_boundary_candidate(combined, language):
                    coalesced.append(combined)
                    index += 2
                    continue
        if current:
            coalesced.append(current)
        index += 1
    return tuple(coalesced)


def _should_finalize_before_replacement(
    sentence: str,
    language: str,
    staged_confirmations: int = 0,
    staged_age: int = 0,
    sentence_finalize_age: int | None = None,
    staged_forced: bool = False,
    deferred_revision_sentences: tuple[str, ...] = (),
) -> bool:
    if _has_deferred_revision_extension(sentence, deferred_revision_sentences):
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if flags.intersection(
        {
            "empty",
            "spaced_cjk",
            "cjk_repeated_ngram",
            "repeated_word_ngram",
            "short_no_end_fragment",
        }
    ):
        return False
    if "no_end_marker" in flags and staged_confirmations < _sentence_required_confirmations(staged_forced):
        return False
    if "trailing_ellipsis" in flags:
        return False
    if _is_cjk_text(sentence):
        if flags.intersection({"short_cjk", "no_end_marker", "cjk_internal_gap"}):
            return False
    if not _should_finalize_replaced_sentence(
        sentence,
        "",
        language,
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_finalize_age,
    ):
        return False
    return True


def _should_finalize_with_right_context(
    sentence: str,
    language: str,
    deferred_revision_sentences: tuple[str, ...] = (),
) -> bool:
    if not _normalized_text(sentence):
        return False
    if not deferred_revision_sentences:
        return False
    if _has_deferred_revision_extension(sentence, deferred_revision_sentences):
        return False
    if _sentence_end_count(sentence) <= 0:
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if flags.intersection(
        {
            "empty",
            "spaced_cjk",
            "cjk_repeated_ngram",
            "repeated_word_ngram",
            "short_no_end_fragment",
            "trailing_ellipsis",
        }
    ):
        return False
    if _is_cjk_text(sentence) and flags.intersection({"short_cjk", "cjk_internal_gap"}):
        return False
    return True


def _has_deferred_revision_extension(sentence: str, deferred_revision_sentences: tuple[str, ...]) -> bool:
    normalized_sentence = _normalized_text(sentence)
    sentence_words = _word_units(normalized_sentence)
    if not sentence_words:
        return False
    for deferred in deferred_revision_sentences:
        normalized_deferred = _normalized_text(deferred)
        if normalized_deferred == normalized_sentence:
            continue
        deferred_words = _word_units(normalized_deferred)
        if len(deferred_words) <= len(sentence_words):
            continue
        if not _sentences_are_revisions(normalized_sentence, normalized_deferred):
            continue
        if _prefer_sentence_revision(normalized_sentence, normalized_deferred) == normalized_deferred:
            return True
    return False


def _should_suppress_delta_final(staged_sentence: str, output_sentence: str, language: str, reason: str) -> bool:
    staged = _normalized_text(staged_sentence)
    output = _normalized_text(output_sentence)
    if not staged or not output or staged == output:
        return False
    flags = set(_final_sentence_diagnostic_flags(output, language))
    if flags.intersection({"short_no_end_fragment", "trailing_ellipsis", "cjk_internal_gap", "spaced_cjk"}):
        return True
    if _is_cjk_text(output) and "no_end_marker" in flags:
        return True
    if reason not in {"next_completed", "confirmed", "confirmed_forced"}:
        return False
    if "no_end_marker" in flags and _boundary_sentence_end_count(staged) > _boundary_sentence_end_count(output):
        return True
    output_words = _word_units(output)
    staged_words = _word_units(staged)
    if len(output_words) > 7 or len(output) > 32:
        return False
    if len(staged_words) < len(output_words) + 3:
        return False
    return "no_end_marker" in flags


def _should_preserve_staged_output_when_delta_fragment(staged_sentence: str, output_sentence: str, language: str) -> bool:
    staged = _normalized_text(staged_sentence)
    output = _normalized_text(output_sentence)
    if not staged or not output or staged == output:
        return False
    if _sentence_end_count(staged) <= _sentence_end_count(output):
        return False
    staged_flags = set(_final_sentence_diagnostic_flags(staged, language))
    if staged_flags.intersection({"empty", "spaced_cjk", "cjk_internal_gap", "cjk_repeated_ngram", "repeated_word_ngram"}):
        return False
    output_flags = set(_final_sentence_diagnostic_flags(output, language))
    return bool(output_flags.intersection({"no_end_marker", "short_no_end_fragment", "trailing_ellipsis"}))


def _is_recent_final_echo(candidate: str, recent_sentence: str, _language: str) -> bool:
    candidate_words = _word_units(candidate)
    recent_words = _word_units(recent_sentence)
    if _compact_recent_final_delta(candidate_words, recent_words) is not None:
        return True
    if min(len(candidate_words), len(recent_words)) < 8:
        return False
    ratio = SequenceMatcher(None, recent_words, candidate_words, autojunk=False).ratio()
    if ratio >= 0.78:
        return True
    _best_i, _best_j, common_run = _best_common_word_run(recent_words, candidate_words)
    shorter = min(len(candidate_words), len(recent_words))
    longer = max(len(candidate_words), len(recent_words))
    if common_run / max(shorter, 1) >= 0.65 and (longer - common_run) <= max(8, int(longer * 0.35)):
        return True
    return False


def _compact_recent_final_delta(candidate_words: list[str], recent_words: list[str]) -> str | None:
    candidate_key = "".join(candidate_words).lower()
    recent_key = "".join(recent_words).lower()
    if min(len(candidate_key), len(recent_key)) < 8:
        return None
    if candidate_key == recent_key or candidate_key in recent_key:
        return ""
    matcher = SequenceMatcher(None, recent_key, candidate_key, autojunk=False)
    ratio = matcher.ratio()
    max_block = max((block.size for block in matcher.get_matching_blocks()), default=0)
    shorter = min(len(candidate_key), len(recent_key))
    longer = max(len(candidate_key), len(recent_key))
    if ratio >= 0.82:
        return ""
    if max_block / max(shorter, 1) >= 0.78 and (longer - max_block) <= max(6, int(longer * 0.35)):
        return ""
    return None


def _recent_final_sentence_delta(candidate: str, recent_sentence: str, language: str) -> str | None:
    delta, _reason = _recent_final_sentence_delta_with_reason(candidate, recent_sentence, language)
    return delta


def _recent_final_sentence_delta_with_reason(candidate: str, recent_sentence: str, language: str) -> tuple[str | None, str]:
    normalized_candidate = _normalized_text(candidate)
    normalized_recent = _normalized_text(recent_sentence)
    if not normalized_candidate or not normalized_recent:
        return None, "empty"
    candidate_words = _word_units(normalized_candidate)
    recent_words = _word_units(normalized_recent)
    if candidate_words and candidate_words == recent_words:
        return "", "exact"
    extension_delta = _recent_final_prefix_extension_delta(candidate_words, recent_words, normalized_candidate)
    if extension_delta is not None:
        return extension_delta, "prefix_extension"
    tail_anchor_delta = _recent_final_tail_anchor_delta(candidate_words, recent_words, normalized_candidate)
    if tail_anchor_delta is not None:
        return tail_anchor_delta, "tail_anchor"
    compact_delta = _compact_recent_final_delta(candidate_words, recent_words)
    if compact_delta is not None:
        return compact_delta, "compact"
    fragment_echo_delta = _recent_final_fragment_echo_delta(normalized_candidate, candidate_words, recent_words)
    if fragment_echo_delta is not None:
        return fragment_echo_delta, "fragment_echo"
    short_tail_delta = _recent_final_short_tail_echo_delta(candidate_words, recent_words)
    if short_tail_delta is not None:
        return short_tail_delta, "short_tail_echo"
    tail_subset_delta = _recent_final_tail_subset_echo_delta(candidate_words, recent_words)
    if tail_subset_delta is not None:
        return tail_subset_delta, "tail_subset_echo"
    fuzzy_suffix_delta = _recent_final_fuzzy_suffix_echo_delta(candidate_words, recent_words)
    if fuzzy_suffix_delta is not None:
        return fuzzy_suffix_delta, "fuzzy_suffix_echo"
    no_end_suffix_delta = _recent_final_no_end_suffix_echo_delta(
        normalized_candidate,
        candidate_words,
        recent_words,
    )
    if no_end_suffix_delta is not None:
        return no_end_suffix_delta, "no_end_suffix_echo"
    if min(len(candidate_words), len(recent_words)) < 8:
        suffix_delta = _recent_final_suffix_delta(candidate_words, recent_words)
        if suffix_delta is not None:
            return suffix_delta, "suffix"
        return None, "no_match"
    suffix_delta = _recent_final_suffix_delta(candidate_words, recent_words)
    if suffix_delta is not None:
        return suffix_delta, "suffix"
    if _contains_word_sequence(recent_words, candidate_words):
        return "", "contained_in_recent"
    if _contains_word_sequence(candidate_words, recent_words):
        for start in range(0, len(candidate_words) - len(recent_words) + 1):
            if _is_subsequence_at(candidate_words, recent_words, start):
                suffix_words = candidate_words[start + len(recent_words) :]
                if not suffix_words:
                    return "", "contains_recent"
                if _has_cjk_words(candidate_words) and len(suffix_words) < 4:
                    return "", "contains_recent_short_cjk_suffix"
                delta = _cjk_delta_from_words(suffix_words) if _has_cjk_words(candidate_words) else _sentence_delta_from_words(suffix_words)
                return _with_candidate_terminal(delta, normalized_candidate), "contains_recent"
    matcher = SequenceMatcher(None, recent_words, candidate_words, autojunk=False)
    prefix_blocks = [
        block
        for block in matcher.get_matching_blocks()
        if block.size and block.a <= len(recent_words) and block.b <= len(candidate_words)
    ]
    if prefix_blocks and prefix_blocks[0].a <= 1 and prefix_blocks[0].b <= 1:
        covered_recent = 0
        last_candidate_end = 0
        previous_recent_end = 0
        previous_candidate_end = 0
        for block in prefix_blocks:
            if block.a - previous_recent_end > 2 or block.b - previous_candidate_end > 2:
                break
            covered_recent += block.size
            previous_recent_end = block.a + block.size
            previous_candidate_end = block.b + block.size
            last_candidate_end = previous_candidate_end
        if covered_recent / max(len(recent_words), 1) >= 0.80 and last_candidate_end >= len(recent_words) - 2:
            suffix_words = candidate_words[last_candidate_end:]
            if not suffix_words:
                return "", "prefix_block"
            if _has_cjk_words(candidate_words) and len(suffix_words) < 4:
                return "", "prefix_block_short_cjk_suffix"
            delta = _cjk_delta_from_words(suffix_words) if _has_cjk_words(candidate_words) else _sentence_delta_from_words(suffix_words)
            return _with_candidate_terminal(delta, normalized_candidate), "prefix_block"
    if _has_cjk_words(candidate_words) and _has_cjk_words(recent_words):
        cjk_blocks = [
            block
            for block in matcher.get_matching_blocks()
            if block.size >= 2
        ]
        matched_recent = sum(block.size for block in cjk_blocks)
        if matched_recent >= 10 and matched_recent / max(len(recent_words), 1) >= 0.55:
            last_candidate_end = max((block.b + block.size for block in cjk_blocks), default=0)
            suffix_words = candidate_words[last_candidate_end:]
            if not suffix_words:
                return "", "cjk_block"
            if len(suffix_words) < 4:
                return "", "cjk_block_short_suffix"
            return _with_candidate_terminal(_cjk_delta_from_words(suffix_words), normalized_candidate), "cjk_block"
        best_i, best_j, best_len = _best_common_word_run(recent_words, candidate_words)
        recent_coverage = best_len / max(len(recent_words), 1)
        if best_len >= 10 and recent_coverage >= 0.45:
            suffix_words = candidate_words[best_j + best_len :]
            if not suffix_words:
                return "", "cjk_common_run"
            if len(suffix_words) < 4:
                return "", "cjk_common_run_short_suffix"
            return _with_candidate_terminal(_cjk_delta_from_words(suffix_words), normalized_candidate), "cjk_common_run"
    if not _is_recent_final_echo(normalized_candidate, normalized_recent, language):
        return None, "no_match"
    blocks = [
        block
        for block in matcher.get_matching_blocks()
        if block.size >= 8 and block.a <= 3 and block.b <= 3
    ]
    if not blocks:
        return "", "echo"
    block = max(blocks, key=lambda item: item.size)
    if block.size / max(len(recent_words), 1) < 0.60:
        return "", "echo_low_coverage"
    suffix_words = candidate_words[block.b + block.size :]
    if not suffix_words:
        return "", "echo"
    if _has_cjk_words(candidate_words) and len(suffix_words) < 4:
        return "", "echo_short_cjk_suffix"
    delta = _cjk_delta_from_words(suffix_words) if _has_cjk_words(candidate_words) else _sentence_delta_from_words(suffix_words)
    return _with_candidate_terminal(delta, normalized_candidate), "echo"


def _recent_final_prefix_extension_delta(
    candidate_words: list[str],
    recent_words: list[str],
    normalized_candidate: str,
) -> str | None:
    if len(candidate_words) <= len(recent_words) or not recent_words:
        return None
    if len(recent_words) < _recent_final_extension_min_prefix_units():
        return None
    if not _is_subsequence_at(candidate_words, recent_words, 0):
        return None
    suffix_words = candidate_words[len(recent_words) :]
    if len(suffix_words) < _recent_final_extension_min_suffix_units():
        return ""
    if _has_cjk_words(candidate_words):
        return _with_candidate_terminal(_cjk_delta_from_words(suffix_words), normalized_candidate)
    return _with_candidate_terminal(_sentence_delta_from_words(suffix_words), normalized_candidate)


def _recent_final_tail_anchor_delta(
    candidate_words: list[str],
    recent_words: list[str],
    normalized_candidate: str,
) -> str | None:
    if len(candidate_words) < 8 or len(recent_words) < 8:
        return None
    if not (_has_cjk_words(candidate_words) and _has_cjk_words(recent_words)):
        return None
    max_tail_len = min(8, len(recent_words), len(candidate_words) - 4)
    min_tail_len = _recent_final_tail_anchor_min_units()
    for tail_len in range(max_tail_len, min_tail_len - 1, -1):
        recent_tail = recent_words[-tail_len:]
        if candidate_words[:tail_len] != recent_tail:
            continue
        suffix_words = candidate_words[tail_len:]
        if len(suffix_words) < 4:
            return ""
        return _with_candidate_terminal(_cjk_delta_from_words(suffix_words), normalized_candidate)
    return None


def _recent_final_tail_subset_echo_delta(candidate_words: list[str], recent_words: list[str]) -> str | None:
    if len(candidate_words) < 8 or len(candidate_words) >= len(recent_words):
        return None
    if not (_has_cjk_words(candidate_words) and _has_cjk_words(recent_words)):
        return None
    candidate_key = "".join(candidate_words).lower()
    if len(candidate_key) < 10:
        return None
    expected_start = len(recent_words) - len(candidate_words)
    best_ratio = 0.0
    best_end_gap = len(recent_words)
    for start in range(
        max(0, expected_start - 4),
        min(len(recent_words) - len(candidate_words), expected_start + 4) + 1,
    ):
        recent_slice_key = "".join(recent_words[start : start + len(candidate_words)]).lower()
        ratio = SequenceMatcher(None, recent_slice_key, candidate_key, autojunk=False).ratio()
        end_gap = len(recent_words) - (start + len(candidate_words))
        if ratio > best_ratio or (ratio == best_ratio and end_gap < best_end_gap):
            best_ratio = ratio
            best_end_gap = end_gap
    if best_ratio >= 0.90 and best_end_gap <= 2:
        return ""
    return None


def _recent_final_fragment_echo_delta(
    normalized_candidate: str,
    candidate_words: list[str],
    recent_words: list[str],
) -> str | None:
    if _boundary_sentence_end_count(normalized_candidate) <= 0:
        return None
    if not candidate_words or len(candidate_words) >= len(recent_words):
        return None
    min_units = _recent_final_fragment_echo_min_units()
    if len(candidate_words) < min_units or len(recent_words) < min_units + 3:
        return None
    max_candidate_len = max(min_units, int(len(recent_words) * _recent_final_fragment_echo_max_length_ratio()))
    if len(candidate_words) > max_candidate_len:
        return None
    _best_i, best_j, common_run = _best_common_word_run(recent_words, candidate_words)
    if common_run < min_units:
        return None
    unmatched = len(candidate_words) - common_run
    if unmatched > _recent_final_fragment_echo_max_unmatched_units():
        return None
    if common_run / max(len(candidate_words), 1) < _recent_final_fragment_echo_coverage_min():
        return None
    candidate_run_touches_edge = best_j <= 1 or best_j + common_run >= len(candidate_words) - 1
    if not candidate_run_touches_edge:
        return None
    return ""


def _recent_final_fuzzy_suffix_echo_delta(candidate_words: list[str], recent_words: list[str]) -> str | None:
    if len(candidate_words) < 8 or len(candidate_words) >= len(recent_words):
        return None
    if not (_has_cjk_words(candidate_words) and _has_cjk_words(recent_words)):
        return None
    matcher = SequenceMatcher(None, recent_words, candidate_words, autojunk=False)
    for block in sorted(matcher.get_matching_blocks(), key=lambda item: item.size, reverse=True):
        if block.size < 6:
            continue
        recent_end_gap = len(recent_words) - (block.a + block.size)
        candidate_end_gap = len(candidate_words) - (block.b + block.size)
        if recent_end_gap > 1 or candidate_end_gap > 1:
            continue
        if block.size / max(len(candidate_words), 1) < 0.50:
            continue
        return ""
    return None


def _recent_final_no_end_suffix_echo_delta(
    normalized_candidate: str,
    candidate_words: list[str],
    recent_words: list[str],
) -> str | None:
    if _boundary_sentence_end_count(normalized_candidate) > 0:
        return None
    if len(candidate_words) >= len(recent_words):
        return None
    min_units = _recent_final_no_end_suffix_echo_min_units()
    if len(candidate_words) < min_units or len(recent_words) < min_units + 2:
        return None
    matcher = SequenceMatcher(None, recent_words, candidate_words, autojunk=False)
    best_suffix_block = None
    for block in matcher.get_matching_blocks():
        if block.size < min_units:
            continue
        recent_end_gap = len(recent_words) - (block.a + block.size)
        candidate_end_gap = len(candidate_words) - (block.b + block.size)
        if recent_end_gap > 1 or candidate_end_gap > 1:
            continue
        if best_suffix_block is None or block.size > best_suffix_block.size:
            best_suffix_block = block
    if best_suffix_block is None:
        return None
    coverage = best_suffix_block.size / max(len(candidate_words), 1)
    if coverage < _recent_final_no_end_suffix_echo_coverage_min():
        return None
    expected_start = max(0, len(recent_words) - len(candidate_words))
    best_ratio = 0.0
    for start in range(
        max(0, expected_start - 3),
        min(len(recent_words) - len(candidate_words), expected_start + 3) + 1,
    ):
        recent_slice = recent_words[start : start + len(candidate_words)]
        ratio = SequenceMatcher(None, recent_slice, candidate_words, autojunk=False).ratio()
        best_ratio = max(best_ratio, ratio)
    if best_ratio < _recent_final_no_end_suffix_echo_similarity_min():
        return None
    return ""


def _recent_final_short_tail_echo_delta(candidate_words: list[str], recent_words: list[str]) -> str | None:
    if len(candidate_words) == 1:
        if len(recent_words) < 4:
            return None
        candidate_key = "".join(candidate_words).lower()
        recent_key = recent_words[-1].lower()
        if len(candidate_key) >= 6 and SequenceMatcher(None, recent_key, candidate_key, autojunk=False).ratio() >= 0.86:
            return ""
        return None
    if len(candidate_words) < 2 or len(candidate_words) > 5:
        return None
    if len(recent_words) < len(candidate_words) + 2:
        return None
    for suffix_len in range(min(len(candidate_words), 4), 1, -1):
        candidate_suffix = candidate_words[-suffix_len:]
        recent_suffix = recent_words[-suffix_len:]
        candidate_key = "".join(candidate_suffix).lower()
        recent_key = "".join(recent_suffix).lower()
        if len(candidate_key) < 6:
            continue
        if SequenceMatcher(None, recent_key, candidate_key, autojunk=False).ratio() >= 0.86:
            return ""
    return None


def _recent_final_suffix_delta(candidate_words: list[str], recent_words: list[str]) -> str | None:
    if len(candidate_words) <= len(recent_words) or not recent_words:
        return None
    recent_key = "".join(recent_words).lower()
    if len(recent_key) < 6:
        return None
    expected_start = len(candidate_words) - len(recent_words)
    for start in range(max(1, expected_start - 2), min(len(candidate_words), expected_start + 3)):
        suffix_words = candidate_words[start:]
        suffix_key = "".join(suffix_words).lower()
        if len(suffix_key) < 6:
            continue
        ratio = SequenceMatcher(None, recent_key, suffix_key, autojunk=False).ratio()
        if ratio < 0.78:
            continue
        prefix_words = candidate_words[:start]
        if len(prefix_words) < 4:
            return ""
        if _has_cjk_words(candidate_words):
            return _cjk_delta_from_words(prefix_words)
        return _sentence_delta_from_words(prefix_words)
    for suffix_len in range(min(5, len(candidate_words) - 4), 1, -1):
        suffix_words = candidate_words[-suffix_len:]
        suffix_key = "".join(suffix_words).lower()
        if len(suffix_key) < 6:
            continue
        for recent_len in range(suffix_len, min(len(recent_words), suffix_len + 1) + 1):
            recent_tail_key = "".join(recent_words[-recent_len:]).lower()
            ratio = SequenceMatcher(None, recent_tail_key, suffix_key, autojunk=False).ratio()
            if ratio < 0.84:
                continue
            prefix_words = candidate_words[:-suffix_len]
            if len(prefix_words) < 4:
                return ""
            if _has_cjk_words(candidate_words):
                return _cjk_delta_from_words(prefix_words)
            return _sentence_delta_from_words(prefix_words)
    return None


def _with_candidate_terminal(delta: str, candidate: str) -> str:
    normalized_delta = _normalized_text(delta)
    if not normalized_delta or _boundary_sentence_end_count(normalized_delta) > 0:
        return normalized_delta
    normalized_candidate = _normalized_text(candidate)
    if normalized_candidate and normalized_candidate[-1] in ".!?。？！":
        return normalized_delta + normalized_candidate[-1]
    return normalized_delta


def _recent_final_output_delta(candidate: str, recent_sentences: list[str] | tuple[str, ...], language: str) -> tuple[str, str | None]:
    delta, recent, _reason = _recent_final_output_delta_with_reason(candidate, recent_sentences, language)
    return delta, recent


def _recent_final_output_delta_with_reason(
    candidate: str,
    recent_sentences: list[str] | tuple[str, ...],
    language: str,
) -> tuple[str, str | None, str]:
    normalized = _normalized_text(candidate)
    if not normalized:
        return "", None, "empty"
    for recent in reversed(recent_sentences):
        delta, reason = _recent_final_sentence_delta_with_reason(normalized, recent, language)
        if delta is None:
            continue
        return delta, recent, reason
    return normalized, None, "no_match"


def _strip_prior_pending_prefix_revision(staged_sentence: str, candidate: str, prior_pending_text: str) -> str:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(prior_pending_text)
    if not normalized_candidate or not normalized_pending:
        return normalized_candidate
    if _boundary_sentence_end_count(normalized_pending) > 0:
        return normalized_candidate
    candidate_words = _word_units(normalized_candidate)
    pending_words = _word_units(normalized_pending)
    if not candidate_words or not pending_words:
        return normalized_candidate
    if len(pending_words) > 12 or len(pending_words) >= len(candidate_words):
        return normalized_candidate
    if candidate_words[: len(pending_words)] != pending_words:
        return normalized_candidate
    suffix_words = candidate_words[len(pending_words) :]
    if len(suffix_words) < 4:
        return normalized_candidate
    suffix = _cjk_delta_from_words(suffix_words) if _has_cjk_words(candidate_words) else _sentence_delta_from_words(suffix_words)
    if not suffix:
        return normalized_candidate
    if staged_sentence and not _sentences_are_revisions(staged_sentence, suffix):
        staged_words = _word_units(staged_sentence)
        suffix_words = _word_units(suffix)
        _best_i, _best_j, best_len = _best_common_word_run(staged_words, suffix_words)
        if best_len / max(min(len(staged_words), len(suffix_words)), 1) < 0.60:
            return normalized_candidate
    return _with_candidate_terminal(suffix, normalized_candidate)


def _is_short_staged_suffix_repeat(staged_sentence: str, pending_text: str) -> bool:
    staged_words = _word_units(staged_sentence)
    pending_words = _word_units(pending_text)
    if not staged_words or not pending_words:
        return False
    if len(pending_words) > 8 or len(pending_words) >= len(staged_words):
        return False
    return staged_words[-len(pending_words) :] == pending_words


def _should_age_staged_sentence(staged_sentence: str, pending_text: str) -> bool:
    if not staged_sentence:
        return False
    if pending_text and _is_short_staged_suffix_repeat(staged_sentence, pending_text):
        return True
    if pending_text and _sentences_are_revisions(staged_sentence, pending_text):
        return False
    return True


def _find_word_sequence(words: list[str], needle: list[str], start: int) -> int:
    if not needle or start >= len(words):
        return -1
    end = len(words) - len(needle) + 1
    for index in range(max(0, start), max(start, end)):
        if words[index : index + len(needle)] == needle:
            return index
    return -1


def _strip_leading_word_units(text: str, count: int) -> str:
    if count <= 0:
        return text
    seen = 0
    for match in _WORD_UNIT_RE.finditer(text):
        seen += 1
        if seen == count:
            return text[match.end() :].lstrip(" ，,")
    return text


def _trim_repeated_cjk_revision_prefix(left: str, right: str) -> str:
    normalized = _normalized_text(right)
    if not (_is_cjk_text(left) and _is_cjk_text(normalized)):
        return normalized
    left_words = _word_units(left)
    right_words = _word_units(normalized)
    if len(left_words) < 24 or len(right_words) <= len(left_words):
        return normalized

    blocks = [
        block
        for block in SequenceMatcher(None, left_words, right_words, autojunk=False).get_matching_blocks()
        if block.size >= 16 and block.b > 0
    ]
    if not blocks:
        return normalized
    block = min(blocks, key=lambda item: item.b)
    prefix_words = right_words[: block.b]
    if not (4 <= len(prefix_words) <= 48):
        return normalized
    if not all(_has_cjk_words([word]) for word in prefix_words):
        return normalized
    repeated_at = _find_word_sequence(right_words, prefix_words, block.b + block.size)
    if repeated_at < 0:
        return normalized

    prefix_text = "".join(prefix_words)
    normalized_prefix = "".join(_word_units(normalized[: max(len(prefix_text) * 2, len(prefix_text))]))
    if not normalized_prefix.startswith(prefix_text):
        return normalized
    return _strip_leading_word_units(normalized, len(prefix_words))


def _is_prefix_inserted_staged_tail_revision(left: str, right: str) -> bool:
    normalized_right = _normalized_text(right)
    if _boundary_sentence_end_count(normalized_right) > 0:
        return False
    left_words = _word_units(left)
    right_words = _word_units(normalized_right)
    if len(left_words) < 10 or len(right_words) <= len(left_words):
        return False
    for block in SequenceMatcher(None, left_words, right_words, autojunk=False).get_matching_blocks():
        if block.size < 8:
            continue
        if block.a > 2:
            continue
        if not (1 <= block.b <= 8):
            continue
        if block.a + block.size < len(left_words) - 2:
            continue
        if block.size / max(len(left_words), 1) >= 0.65:
            return True
    return False


def _is_cjk_shifted_prefix_dangling_tail_revision(left: str, right: str) -> bool:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if not (_is_cjk_text(normalized_left) or _is_cjk_text(normalized_right)):
        return False
    if _boundary_sentence_end_count(normalized_left) == 0 or _boundary_sentence_end_count(normalized_right) == 0:
        return False
    left_words = _word_units(normalized_left)
    right_words = _word_units(normalized_right)
    if len(left_words) < 8 or len(left_words) != len(right_words) + 1:
        return False
    if left_words[1:-1] != right_words[1:]:
        return False
    return len(left_words[1:-1]) >= 6


def _is_cjk_prefixed_stale_revision(left: str, right: str) -> bool:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if not (_is_cjk_text(normalized_left) or _is_cjk_text(normalized_right)):
        return False
    if _boundary_sentence_end_count(normalized_right) == 0:
        return False
    left_words = _word_units(normalized_left)
    right_words = _word_units(normalized_right)
    if len(left_words) <= len(right_words) or len(right_words) < 8:
        return False
    matcher = SequenceMatcher(None, left_words, right_words, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    if not blocks:
        return False
    first = blocks[0]
    best_i, best_j, common_run = first.a, first.b, first.size
    if best_j != 0 or not (2 <= best_i <= 10):
        return False
    matched_units = sum(block.size for block in blocks)
    right_coverage = matched_units / max(len(right_words), 1)
    left_prefix_units = left_words[:best_i]
    if not all(_has_cjk_words([word]) for word in left_prefix_units):
        return False
    return common_run >= 8 and right_coverage >= 0.70


def _is_prefix_dropped_revision(left: str, right: str) -> bool:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if _boundary_sentence_end_count(normalized_left) == 0 or _boundary_sentence_end_count(normalized_right) == 0:
        return False
    left_words = _word_units(normalized_left)
    right_words = _word_units(normalized_right)
    if len(left_words) <= len(right_words) or len(right_words) < 8:
        return False
    matcher = SequenceMatcher(None, left_words, right_words, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    if not blocks:
        return False
    first = blocks[0]
    if first.b != 0 or not (2 <= first.a <= 10):
        return False
    matched_units = sum(block.size for block in blocks)
    right_coverage = matched_units / max(len(right_words), 1)
    return first.size >= 8 and right_coverage >= 0.70


def _should_finalize_confirmed_before_prefix_drop_revision(
    staged_sentence: str,
    candidate: str,
    staged_confirmations: int,
    staged_forced: bool,
) -> bool:
    if not _should_confirm_staged_sentence(staged_sentence, staged_confirmations, staged_forced):
        return False
    if not _is_prefix_dropped_revision(staged_sentence, candidate):
        return False
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh" if _is_cjk_text(staged_sentence) else ""))
    return not flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "repeated_word_ngram"})


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


def _prefer_sentence_revision(left: str, right: str) -> str:
    right = _trim_repeated_cjk_revision_prefix(left, right)
    left_words = _word_units(left)
    right_words = _word_units(right)
    left_flags = set(_final_sentence_diagnostic_flags(left, "zh" if _is_cjk_text(left) else ""))
    right_flags = set(_final_sentence_diagnostic_flags(right, "zh" if _is_cjk_text(right) else ""))
    if "repeated_word_ngram" in right_flags and "repeated_word_ngram" not in left_flags:
        return _normalized_text(left)
    if "repeated_word_ngram" in left_flags and "repeated_word_ngram" not in right_flags:
        return _normalized_text(right)
    if _is_prefix_inserted_staged_tail_revision(left, right):
        return _normalized_text(left)
    if _is_cjk_text(left) or _is_cjk_text(right):
        if _is_cjk_shifted_prefix_dangling_tail_revision(left, right):
            return _normalized_text(right)
        if _is_cjk_prefixed_truncated_revision(left, right):
            return _normalized_text(right)
        if _is_cjk_prefixed_stale_revision(left, right):
            return _normalized_text(right)
        if "cjk_repeated_ngram" in right_flags and "cjk_repeated_ngram" not in left_flags:
            return _normalized_text(left)
        if "cjk_repeated_ngram" in left_flags and "cjk_repeated_ngram" not in right_flags:
            return _normalized_text(right)
        if (
            right_words
            and len(left_words) > len(right_words)
            and left_words[: len(right_words)] == right_words
            and 2 <= len(left_words) - len(right_words) <= 8
            and _boundary_sentence_end_count(right) > 0
            and not ("mixed_latin_zh" in left_flags and "mixed_latin_zh" in right_flags)
        ):
            return _normalized_text(right)
    if _share_stable_numeric_sequence(left_words, right_words):
        if _sentence_end_count(right) > _sentence_end_count(left):
            return _normalized_text(right)
        if len(right_words) > len(left_words):
            return _normalized_text(right)
        return _normalized_text(left)
    if len(right_words) > len(left_words):
        return _normalized_text(right)
    if _sentence_end_count(right) > _sentence_end_count(left):
        return _normalized_text(right)
    return _normalized_text(left)


def _should_preserve_revision_confirmation_from_internal_stability(
    previous: str,
    preferred: str,
    stable_internal_ratio: float = 0.0,
    stable_internal_chars: int = 0,
    stable_overlap_source: str = "",
) -> bool:
    if preferred == _normalized_text(previous):
        return False
    if not (_is_cjk_text(previous) or _is_cjk_text(preferred)):
        return False
    return (
        stable_overlap_source == "none"
        and stable_internal_ratio >= CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO
        and stable_internal_chars >= CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS
    )


def _revision_internal_stability_bucket(stable_internal_ratio: float = 0.0, stable_internal_chars: int = 0) -> str:
    if (
        stable_internal_chars >= CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS
        and stable_internal_ratio >= CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO
    ):
        return "high"
    if (
        stable_internal_chars >= CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS
        and stable_internal_ratio >= CJK_REVISION_INTERNAL_STABILITY_MID_RATIO
    ):
        return "mid"
    return "low"


def _next_revision_confirmation_count(
    previous: str,
    preferred: str,
    current_confirmations: int,
    stable_internal_ratio: float = 0.0,
    stable_internal_chars: int = 0,
    stable_overlap_source: str = "",
) -> int:
    normalized_previous = _normalized_text(previous)
    normalized_preferred = _normalized_text(preferred)
    if preferred != _normalized_text(previous):
        if _should_preserve_revision_confirmation_by_token_sentence(previous, preferred):
            return current_confirmations + 1
        if _should_preserve_revision_confirmation_from_internal_stability(
            previous,
            preferred,
            stable_internal_ratio,
            stable_internal_chars,
            stable_overlap_source,
        ):
            return max(current_confirmations, 1)
        return 1
    return current_confirmations + 1


def _should_defer_token_sentence_revision(
    previous: str,
    preferred: str,
    current_confirmations: int,
    staged_forced: bool,
    stable_internal_ratio: float = 0.0,
    stable_internal_chars: int = 0,
    stable_overlap_source: str = "",
) -> bool:
    normalized_previous = _normalized_text(previous)
    normalized_preferred = _normalized_text(preferred)
    if normalized_previous == normalized_preferred:
        return False
    if _word_units(normalized_previous) == _word_units(normalized_preferred):
        return False
    if _should_reset_revision_age(
        normalized_previous,
        normalized_preferred,
        stable_internal_ratio,
        stable_internal_chars,
        stable_overlap_source,
    ):
        return True
    required_confirmations = _staged_sentence_required_confirmations(normalized_preferred, staged_forced)
    revision_required_confirmations = max(required_confirmations, 2)
    next_confirmations = _next_revision_confirmation_count(
        normalized_previous,
        normalized_preferred,
        current_confirmations,
        stable_internal_ratio,
        stable_internal_chars,
        stable_overlap_source,
    )
    return current_confirmations < revision_required_confirmations <= next_confirmations


def _should_reset_revision_age(
    previous: str,
    preferred: str,
    stable_internal_ratio: float = 0.0,
    stable_internal_chars: int = 0,
    stable_overlap_source: str = "",
) -> bool:
    normalized_previous = _normalized_text(previous)
    normalized_preferred = _normalized_text(preferred)
    if normalized_preferred == normalized_previous:
        return False
    if _should_preserve_revision_confirmation_by_token_sentence(previous, preferred):
        return False
    if _should_preserve_revision_confirmation_from_internal_stability(
        previous,
        preferred,
        stable_internal_ratio,
        stable_internal_chars,
        stable_overlap_source,
    ):
        return False
    if _boundary_sentence_end_count(normalized_previous) > 0 and _boundary_sentence_end_count(normalized_preferred) == 0:
        return True
    return True


def _split_completed_sentences(pending_text: str, new_text: str) -> tuple[list[str], str]:
    return _boundary_split_completed_sentences(pending_text, new_text)


def _sentence_end_count(text: str) -> int:
    return _boundary_sentence_end_count(text)


def _has_unstable_numeric_tail(text: str) -> bool:
    words = _word_units(text)
    return bool(len(words) >= 2 and words[-1].isdigit() and words[-2] in {"from", "to"})


def _pending_overrun_reason(pending_text: str, pending_chunks: int) -> str:
    normalized = _normalized_text(pending_text)
    if not normalized:
        return ""
    pending_chars = len(normalized)
    standard_overrun = pending_chunks >= PENDING_OVERRUN_CHUNKS and pending_chars >= MAX_PENDING_SENTENCE_CHARS
    fast_overrun = pending_chunks >= FAST_PENDING_OVERRUN_CHUNKS and pending_chars >= FAST_PENDING_OVERRUN_CHARS
    if not standard_overrun and not fast_overrun:
        return ""
    if _sentence_end_count(normalized) > 0:
        return "with_end_mark"
    if _has_unstable_numeric_tail(normalized):
        return "unstable_numeric_tail"
    return "long_no_boundary"


def _pending_text_diagnostic_flags(pending_text: str, language: str, pending_chunks: int) -> tuple[str, ...]:
    normalized = _normalized_text(pending_text)
    if not normalized:
        return ()
    flags: list[str] = []
    normalized_language = str(language or "").strip().lower()
    words = _word_units(normalized)
    if _has_repeated_word_ngram(words):
        flags.append("repeated_word_ngram")
    if (normalized_language == "zh" or _has_cjk_words(words)) and _has_repeated_cjk_ngram(words):
        flags.append("cjk_repeated_ngram")
    overrun = _pending_overrun_reason(normalized, pending_chunks)
    if overrun:
        flags.append(f"overrun_{overrun}")
    return tuple(flags)


def _diagnostic_tail(text: str, limit: int = 90) -> str:
    normalized = _normalized_text(text)
    if len(normalized) > limit:
        normalized = "..." + normalized[-limit:]
    return repr(normalized)

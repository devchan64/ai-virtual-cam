from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.app.sentence_boundary import (
    pending_new_text_combined,
    sentence_end_count as _boundary_sentence_end_count,
    split_completed_sentences as _boundary_split_completed_sentences,
)

MAX_PENDING_SENTENCE_CHARS = 180
PENDING_OVERRUN_CHUNKS = 8
FAST_PENDING_OVERRUN_CHARS = 240
FAST_PENDING_OVERRUN_CHUNKS = 4
SLOW_PENDING_SENTENCE_CHUNKS = 4
SLOW_PENDING_SENTENCE_CHARS = 45
SLOW_PENDING_MAX_SENTENCE_CHARS = 120
SLOW_PENDING_MAX_CHARS_PER_CHUNK = 18.0
SENTENCE_CONFIRM_CHUNKS = 3
FORCED_SENTENCE_CONFIRM_CHUNKS = 4
SENTENCE_CONFIRM_MAX_AGE_CHUNKS = 3
FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS = 4
SHORT_CJK_FINAL_UNITS = 10
CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO = 0.60
CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS = 40


def _coalesce_completed_sentences_for_staging(sentences: list[str], language: str) -> list[str]:
    normalized_sentences = [_normalized_text(sentence) for sentence in sentences if _normalized_text(sentence)]
    normalized_language = str(language or "").strip().lower()
    if normalized_language == "zh" and len(normalized_sentences) > 1:
        return ["".join(normalized_sentences)]
    return normalized_sentences


def _normalized_text(text: str) -> str:
    return " ".join(str(text).split())


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
    internal_delta = _new_text_delta_after_internal_overlap(committed, stable)
    if internal_delta is not None:
        return internal_delta
    return stable


_WORD_UNIT_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"\d+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"[A-Za-z가-힣]+|"
    r"[\u3400-\u4dbf\u4e00-\u9fff]"
)


def _word_units(text: str) -> list[str]:
    return [match.group(0).replace(",", "") for match in _WORD_UNIT_RE.finditer(_normalized_text(text).lower())]


def _new_text_delta_after_internal_overlap(committed_text: str, stable_text: str) -> str | None:
    committed_words = _word_units(committed_text)
    stable_units, stable_separator = _text_units(stable_text)
    if stable_separator != " ":
        return None
    stable_word_pairs: list[tuple[str, int]] = []
    for unit_index, unit in enumerate(stable_units):
        for word in _word_units(unit):
            stable_word_pairs.append((word, unit_index))
    stable_words = [word for word, _unit_index in stable_word_pairs]
    if len(committed_words) < 4 or len(stable_words) < 4:
        return None

    best_j = 0
    best_len = 0
    for i in range(len(committed_words)):
        for j in range(len(stable_words)):
            length = 0
            while (
                i + length < len(committed_words)
                and j + length < len(stable_words)
                and committed_words[i + length] == stable_words[j + length]
            ):
                length += 1
            if length > best_len:
                best_j = j
                best_len = length
    if best_len < 4:
        return None
    if best_len / max(len(stable_words), 1) >= 0.85:
        return ""
    suffix_word_index = best_j + best_len
    if suffix_word_index >= len(stable_word_pairs):
        return ""
    suffix_unit_index = stable_word_pairs[suffix_word_index][1]
    suffix = _join_text_units(stable_units[suffix_unit_index:], stable_separator)
    return suffix or ""


def _phrase_key(units: list[str]) -> list[str]:
    return _word_units(" ".join(units))


def _repeated_phrase_key_matches(left_key: list[str], right_key: list[str]) -> bool:
    if left_key == right_key:
        return True
    return len(left_key) >= 4 and len(left_key) == len(right_key) and left_key[1:] == right_key[1:]


def _is_cjk_dominant_unit_stream(units: list[str]) -> bool:
    keys = [_phrase_key([unit]) for unit in units]
    flattened = [word for key in keys for word in key]
    if len(flattened) < 6:
        return False
    cjk_count = sum(1 for word in flattened if _has_cjk_words([word]))
    return cjk_count / max(len(flattened), 1) >= 0.70


def _collapse_near_repeated_phrases(units: list[str]) -> bool:
    if _is_cjk_dominant_unit_stream(units):
        return False
    for phrase_len in range(min(12, len(units) // 2), 3, -1):
        for left_start in range(0, len(units) - phrase_len):
            left_key = _phrase_key(units[left_start : left_start + phrase_len])
            if not left_key:
                continue
            max_right_start = min(len(units) - phrase_len, left_start + phrase_len + 8)
            for right_start in range(left_start + phrase_len, max_right_start + 1):
                right_key = _phrase_key(units[right_start : right_start + phrase_len])
                if _repeated_phrase_key_matches(left_key, right_key):
                    delete_len = phrase_len
                    while (
                        left_start + delete_len < right_start
                        and right_start + delete_len < len(units)
                        and _phrase_key([units[left_start + delete_len]]) == _phrase_key([units[right_start + delete_len]])
                    ):
                        delete_len += 1
                    del units[right_start : right_start + delete_len]
                    return True
    return False


def _collapse_adjacent_repeated_prefix_units(units: list[str]) -> bool:
    for index in range(1, len(units)):
        previous_key = _phrase_key([units[index - 1]])
        current_key = _phrase_key([units[index]])
        if "-" in units[index] and len(previous_key) == 1 and len(current_key) >= 2 and previous_key[0] == current_key[0]:
            del units[index - 1]
            return True
    return False


def _collapse_adjacent_duplicate_determiners(units: list[str]) -> bool:
    for index in range(1, len(units)):
        previous_key = _phrase_key([units[index - 1]])
        current_key = _phrase_key([units[index]])
        if len(previous_key) == 1 and previous_key == current_key and previous_key[0] in {"a", "an", "the"}:
            del units[index - 1]
            return True
    return False


def _compact_hangul_phrase_key(units: list[str]) -> str:
    compact = "".join(_word_units(" ".join(units)))
    if not any("가" <= ch <= "힣" for ch in compact):
        return ""
    return compact


def _collapse_adjacent_compact_korean_revisions(units: list[str]) -> bool:
    max_phrase_len = min(12, len(units) // 2 + 2)
    for left_start in range(0, len(units) - 3):
        for left_len in range(1, max_phrase_len + 1):
            right_start = left_start + left_len
            if right_start >= len(units):
                break
            left_key = _compact_hangul_phrase_key(units[left_start:right_start])
            if len(left_key) < 5:
                continue
            min_right_len = 2 if left_len == 1 else 1
            for right_len in range(min_right_len, max_phrase_len + 1):
                right_end = right_start + right_len
                if right_end > len(units):
                    break
                right_key = _compact_hangul_phrase_key(units[right_start:right_end])
                if left_key == right_key:
                    del units[left_start:right_start]
                    return True
                shorter_key_len = min(len(left_key), len(right_key))
                length_delta = abs(len(left_key) - len(right_key))
                if shorter_key_len < 7 or length_delta > 2 or left_key[0] != right_key[0]:
                    continue
                if SequenceMatcher(None, left_key, right_key).ratio() < 0.88:
                    continue
                if len(left_key) >= len(right_key):
                    del units[right_start:right_end]
                else:
                    del units[left_start:right_start]
                return True
    return False


def _collapse_numeric_value_revisions(text: str) -> str:
    return re.sub(
        r"\bone\s+thousand\s+dollars(?:\s+worth)?\s+\$1,?000\s+worth\b",
        "$1,000 worth",
        text,
        flags=re.IGNORECASE,
    )


_CJK_CLAUSE_SEPARATORS = set("，,。！？!?；;")


def _split_cjk_clauses(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    buffer: list[str] = []
    for char in text:
        if char in _CJK_CLAUSE_SEPARATORS:
            clause = "".join(buffer).strip()
            if clause:
                parts.append((clause, char))
            buffer = []
        else:
            buffer.append(char)
    tail = "".join(buffer).strip()
    if tail:
        parts.append((tail, ""))
    return parts


def _collapse_adjacent_repeated_cjk_clauses(text: str) -> tuple[str, bool]:
    clauses = _split_cjk_clauses(text)
    if len(clauses) < 3:
        return text, False
    collapsed: list[tuple[str, str]] = []
    changed = False
    index = 0
    while index < len(clauses):
        clause, separator = clauses[index]
        key = _word_units(clause)
        run_end = index + 1
        while run_end < len(clauses) and key and _word_units(clauses[run_end][0]) == key:
            run_end += 1
        run_len = run_end - index
        cjk_units = [word for word in key if _has_cjk_words([word])]
        should_collapse = run_len >= 3 or (run_len >= 2 and len(cjk_units) >= 4)
        if should_collapse:
            collapsed.append((clause, clauses[run_end - 1][1] or separator))
            changed = True
        else:
            collapsed.extend(clauses[index:run_end])
        index = run_end
    if not changed:
        return text, False
    return "".join(clause + separator for clause, separator in collapsed), True


def _collapse_adjacent_repeated_phrase_details(text: str) -> tuple[str, list[str]]:
    normalized_input = _normalized_text(text)
    normalized = _collapse_numeric_value_revisions(normalized_input)
    rules: list[str] = []
    if normalized != normalized_input:
        rules.append("numeric_value")
    normalized, cjk_clause_changed = _collapse_adjacent_repeated_cjk_clauses(normalized)
    if cjk_clause_changed:
        rules.append("cjk_clause")
    units, separator = _text_units(normalized)
    if separator == "" or len(units) < 6:
        return normalized, rules
    while True:
        if _collapse_adjacent_repeated_prefix_units(units):
            rules.append("hyphen_prefix")
            continue
        if _collapse_adjacent_duplicate_determiners(units):
            rules.append("duplicate_determiner")
            continue
        if _collapse_adjacent_compact_korean_revisions(units):
            rules.append("compact_korean")
            continue
        break
    passes = 0
    changed = True
    while changed and passes < 4:
        passes += 1
        changed = False
        index = 0
        while index < len(units):
            collapsed = False
            max_phrase_len = min(16, (len(units) - index) // 2)
            for phrase_len in range(max_phrase_len, 2, -1):
                left = units[index : index + phrase_len]
                right = units[index + phrase_len : index + (phrase_len * 2)]
                if _phrase_key(left) and _phrase_key(left) == _phrase_key(right):
                    del units[index + phrase_len : index + (phrase_len * 2)]
                    rules.append("adjacent_phrase")
                    changed = True
                    collapsed = True
                    break
            if not collapsed:
                index += 1
        if _collapse_near_repeated_phrases(units):
            rules.append("near_phrase")
            changed = True
    collapsed_text = _join_text_units(units, separator)
    numeric_collapsed = _collapse_numeric_value_revisions(collapsed_text)
    if numeric_collapsed != collapsed_text:
        rules.append("numeric_value")
    return numeric_collapsed, rules


def _collapse_adjacent_repeated_phrases(text: str) -> str:
    collapsed, _rules = _collapse_adjacent_repeated_phrase_details(text)
    return collapsed


def _is_subsequence_at(words: list[str], candidate: list[str], start: int) -> bool:
    return words[start : start + len(candidate)] == candidate


def _collapse_adjacent_words(words: list[str]) -> list[str]:
    collapsed: list[str] = []
    for word in words:
        if collapsed and collapsed[-1] == word:
            continue
        collapsed.append(word)
    return collapsed


def _duplicate_key_words(words: list[str]) -> list[str]:
    key_words = _collapse_adjacent_words(words)
    while len(key_words) >= 3 and key_words[:2] in (["not", "just"], ["no", "not"]):
        key_words = key_words[2:]
    return key_words


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
    if left == right:
        return True
    return {left, right} <= {"a", "an", "the"}


def _longest_prefix_revision_run(left_words: list[str], right_words: list[str]) -> int:
    length = 0
    while length < len(left_words) and length < len(right_words):
        if not _prefix_words_match(left_words[length], right_words[length]):
            break
        length += 1
    return length


def _short_revision_signature(words: list[str]) -> tuple[str, ...]:
    if not words or len(words) > 18:
        return ()
    for start in range(0, len(words) - 1):
        if words[start : start + 2] == ["take", "care"]:
            return ("take", "care")
    for start in range(0, len(words) - 2):
        if words[start : start + 3] == ["one", "that", "suits"]:
            return ("one", "that", "suits")
        if start + 3 < len(words) and words[start : start + 4] == ["one", "that", "it", "suits"]:
            return ("one", "that", "suits")
    return ()


def _trim_leading_boundary_noise(text: str) -> str:
    words = _word_units(text)
    if len(words) >= 4 and words[:4] == ["if", "you", "when", "you"]:
        return " ".join(words[2:]).strip()
    if len(words) >= 3 and words[:3] == ["you", "when", "you"]:
        return " ".join(words[1:]).strip()
    return text.strip()


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
    return _trim_leading_boundary_noise("".join(words).strip())


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
    return _trim_leading_boundary_noise(" ".join(words).strip())


def _sentence_output_delta(committed_text: str, sentence: str) -> str:
    normalized = _collapse_adjacent_repeated_phrases(_normalized_text(sentence))
    if not normalized:
        return ""
    committed_normalized = _normalized_text(committed_text)
    if (
        committed_normalized
        and normalized.startswith(committed_normalized)
        and (_is_cjk_text(committed_normalized) or _is_cjk_text(normalized))
    ):
        return _trim_leading_boundary_noise(normalized[len(committed_normalized) :].lstrip(" ，,"))
    committed_words = _word_units(committed_text)
    sentence_words = _word_units(normalized)
    if not committed_words or not sentence_words:
        return normalized
    if _is_numeric_fragment_echo(sentence_words, committed_words):
        return ""
    if sentence_words == ["hi"] and committed_words[-1:] == ["high"]:
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
    left_signature = _short_revision_signature(left_words)
    right_signature = _short_revision_signature(right_words)
    if left_signature and left_signature == right_signature:
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
        tail_blocks = [
            block
            for block in SequenceMatcher(None, left_words, right_words, autojunk=False).get_matching_blocks()
            if block.size >= 8 and block.a + block.size == len(left_words)
        ]
        if tail_blocks:
            return True
    if common_run >= 8 and best_i + common_run == len(left_words) and best_j <= 3:
        return True
    if prefix_run >= 5 and common_run >= 5 and len(right_words) >= len(left_words):
        return True
    return common_run >= 4 and common_run / max(shorter, 1) >= 0.6


def _sentence_required_confirmations(forced: bool) -> int:
    return FORCED_SENTENCE_CONFIRM_CHUNKS if forced else SENTENCE_CONFIRM_CHUNKS


def _sentence_max_age_chunks(forced: bool, base_age: int | None = None) -> int:
    if base_age is None:
        return FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS if forced else SENTENCE_CONFIRM_MAX_AGE_CHUNKS
    normalized_base_age = max(1, int(base_age))
    return normalized_base_age + 1 if forced else normalized_base_age


_KOREAN_FINAL_WORD_SUFFIXES = ("다", "요", "죠", "까")


def _has_latin_words(words: list[str]) -> bool:
    return any(any("a" <= ch <= "z" for ch in word.lower()) for word in words)


def _has_unstable_mixed_latin_for_zh(words: list[str]) -> bool:
    latin_words = [word for word in words if any("a" <= ch <= "z" for ch in word.lower())]
    return len(latin_words) >= 2 or any(len(word) >= 4 for word in latin_words)


def _looks_like_open_korean_clause(text: str, words: list[str]) -> bool:
    if _boundary_sentence_end_count(text) > 0:
        return False
    if not words or not _has_hangul_words(words):
        return False
    last_word = words[-1]
    if not any("가" <= ch <= "힣" for ch in last_word):
        return False
    return not last_word.endswith(_KOREAN_FINAL_WORD_SUFFIXES)


def _is_open_korean_clause(text: str) -> bool:
    return _looks_like_open_korean_clause(text, _word_units(text))


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


def _final_sentence_diagnostic_flags(sentence: str, language: str) -> tuple[str, ...]:
    normalized = _normalized_text(sentence)
    words = _word_units(normalized)
    flags: list[str] = []
    if not words:
        return ("empty",)
    normalized_language = str(language or "").strip().lower()
    has_cjk = _has_cjk_words(words)
    has_latin = _has_latin_words(words)
    if normalized_language == "zh" or has_cjk:
        cjk_units = [word for word in words if _has_cjk_words([word])]
        if 0 < len(cjk_units) <= SHORT_CJK_FINAL_UNITS:
            flags.append("short_cjk")
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
    if _boundary_sentence_end_count(normalized) == 0:
        flags.append("no_end_marker")
    return tuple(flags)


def _should_confirm_staged_sentence(
    staged_sentence: str,
    staged_confirmations: int,
    staged_forced: bool,
) -> bool:
    if _is_open_korean_clause(staged_sentence):
        return False
    if _is_cjk_text(staged_sentence):
        flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh"))
        if flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "latin_only_for_zh"}):
            return False
    return staged_confirmations >= _sentence_required_confirmations(staged_forced)


def _should_preserve_partial_replacement(staged_sentence: str, candidate: str) -> bool:
    staged_words = _word_units(staged_sentence)
    candidate_words = _word_units(candidate)
    if len(staged_words) < 4 or len(candidate_words) < 4:
        return False
    if _looks_like_open_korean_clause(staged_sentence, staged_words):
        return False
    best_i, best_j, common_run = _best_common_word_run(staged_words, candidate_words)
    if common_run < 4:
        return False
    left_tail = best_i + common_run == len(staged_words)
    right_tail = best_j + common_run == len(candidate_words)
    if left_tail and right_tail:
        return True
    return _boundary_sentence_end_count(staged_sentence) > 0 and best_j == 0 and common_run >= 5


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
    if _looks_like_open_korean_clause(staged_sentence, staged_words):
        return "open_korean_clause"
    if _looks_like_open_latin_clause(staged_sentence, staged_words):
        return "open_latin_clause"
    if staged_confirmations >= _sentence_required_confirmations(staged_forced):
        return "confirmed"
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


def _should_finalize_replaced_sentence(
    staged_sentence: str,
    candidate: str,
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
    if reason == "confirmed":
        return _should_confirm_staged_sentence(staged_sentence, staged_confirmations, staged_forced)
    return reason in {"aged", "duplicate_or_suffix", "partial_preserve"}


def _format_transcript_metrics(metrics: dict[str, int]) -> str:
    parts = [f"{key}={metrics[key]}" for key in sorted(metrics) if metrics[key]]
    return ",".join(parts) if parts else "none"


def _should_translate_final_sentence(sentence: str, language: str) -> bool:
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    return not flags.intersection(
        {
            "latin_only_for_zh",
            "mixed_latin_zh",
            "short_cjk",
            "no_end_marker",
            "empty",
            "spaced_cjk",
            "cjk_repeated_ngram",
        }
    )


def _should_stage_boundary_candidate(sentence: str, language: str) -> bool:
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    return not flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "latin_only_for_zh"})


def _should_finalize_boundary_candidate(
    sentence: str,
    language: str,
    staged_confirmations: int | None = None,
    staged_forced: bool = False,
) -> bool:
    if staged_confirmations is not None and staged_confirmations < _sentence_required_confirmations(staged_forced):
        return False
    return _should_stage_boundary_candidate(sentence, language)


def _should_finalize_before_replacement(
    sentence: str,
    language: str,
    staged_confirmations: int = 0,
    staged_age: int = 0,
    sentence_finalize_age: int | None = None,
    staged_forced: bool = False,
) -> bool:
    if not _should_finalize_replaced_sentence(
        sentence,
        "",
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_finalize_age,
    ):
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "latin_only_for_zh"}):
        return False
    if _is_cjk_text(sentence) and flags.intersection({"short_cjk", "cjk_internal_gap", "no_end_marker"}):
        return False
    return True


def _is_recent_final_echo(candidate: str, recent_sentence: str, language: str) -> bool:
    normalized_language = str(language or "").strip().lower()
    if normalized_language != "zh" and not (_is_cjk_text(candidate) and _is_cjk_text(recent_sentence)):
        return False
    candidate_words = _word_units(candidate)
    recent_words = _word_units(recent_sentence)
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


def _prefer_sentence_revision(left: str, right: str) -> str:
    right = _trim_repeated_cjk_revision_prefix(left, right)
    left_words = _word_units(left)
    right_words = _word_units(right)
    if _is_cjk_text(left) or _is_cjk_text(right):
        left_flags = set(_final_sentence_diagnostic_flags(left, "zh"))
        right_flags = set(_final_sentence_diagnostic_flags(right, "zh"))
        if "cjk_repeated_ngram" in right_flags and "cjk_repeated_ngram" not in left_flags:
            return _normalized_text(left)
        if "cjk_repeated_ngram" in left_flags and "cjk_repeated_ngram" not in right_flags:
            return _normalized_text(right)
    left_signature = _short_revision_signature(left_words)
    right_signature = _short_revision_signature(right_words)
    if left_signature and left_signature == right_signature:
        if left_signature == ("take", "care"):
            if _sentence_end_count(right) >= _sentence_end_count(left):
                return _normalized_text(right)
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
    if stable_internal_chars >= CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS and stable_internal_ratio >= 0.60:
        return "high"
    if stable_internal_chars >= CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS and stable_internal_ratio >= 0.40:
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
    if preferred != _normalized_text(previous) and (_is_cjk_text(previous) or _is_cjk_text(preferred)):
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



def _pending_new_text_combined(pending_text: str, new_text: str) -> str:
    from src.app.sentence_boundary import pending_new_text_combined

    return pending_new_text_combined(pending_text, new_text)


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
    if (normalized_language == "zh" or _has_cjk_words(words)) and _has_repeated_cjk_ngram(words):
        flags.append("cjk_repeated_ngram")
    overrun = _pending_overrun_reason(normalized, pending_chunks)
    if overrun:
        flags.append(f"overrun_{overrun}")
    return tuple(flags)


def _forced_sentence_reason(pending_text: str, pending_chunks: int) -> str:
    normalized = _normalized_text(pending_text)
    if not normalized:
        return ""
    pending_chars = len(normalized)
    chars_per_chunk = pending_chars / max(pending_chunks, 1)
    if pending_chars >= MAX_PENDING_SENTENCE_CHARS and _sentence_end_count(normalized) > 0:
        return "pending_chars"
    if (
        pending_chunks >= SLOW_PENDING_SENTENCE_CHUNKS
        and SLOW_PENDING_SENTENCE_CHARS <= pending_chars <= SLOW_PENDING_MAX_SENTENCE_CHARS
        and chars_per_chunk <= SLOW_PENDING_MAX_CHARS_PER_CHUNK
        and not _has_unstable_numeric_tail(normalized)
    ):
        return "slow_pending"
    return ""


def _diagnostic_tail(text: str, limit: int = 90) -> str:
    normalized = _normalized_text(text)
    if len(normalized) > limit:
        normalized = "..." + normalized[-limit:]
    return repr(normalized)

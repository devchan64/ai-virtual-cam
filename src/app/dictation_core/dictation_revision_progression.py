from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.app.dictation.pipeline_settings import (
    CJK_REVISION_INTERNAL_STABILITY_MID_RATIO,
    CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS,
    CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO,
    FAST_PENDING_OVERRUN_CHARS,
    FAST_PENDING_OVERRUN_CHUNKS,
    MAX_PENDING_SENTENCE_CHARS,
    PENDING_OVERRUN_CHUNKS,
)
from src.app.dictation_core.dictation_revision_text import (
    _final_sentence_diagnostic_flags,
    _has_cjk_words,
    _has_hangul_words,
    _has_repeated_cjk_ngram,
    _has_repeated_word_ngram,
    _is_cjk_text,
    _normalized_text,
    _sentences_are_revisions,
    _share_stable_numeric_sequence,
    _should_preserve_revision_confirmation_by_token_sentence,
    _word_units,
)
from src.app.dictation_core.sentence_boundary import (
    sentence_end_count as _boundary_sentence_end_count,
    split_completed_sentences as _boundary_split_completed_sentences,
)

_WORD_UNIT_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"\d+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"[A-Za-z가-힣]+|"
    r"[\u3400-\u4dbf\u4e00-\u9fff]"
)


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
        if block.size < 8 or block.a > 2 or not (1 <= block.b <= 8):
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
    if left_words[0] == right_words[0]:
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


def _is_short_closed_cjk_suffix_revision(left: str, right: str) -> bool:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    left_words = _word_units(normalized_left)
    right_words = _word_units(normalized_right)
    if not (
        _is_cjk_text(normalized_left)
        or _is_cjk_text(normalized_right)
        or _has_hangul_words(left_words)
        or _has_hangul_words(right_words)
    ):
        return False
    if _boundary_sentence_end_count(normalized_left) == 0 or _boundary_sentence_end_count(normalized_right) == 0:
        return False
    if len(right_words) < 5 or len(right_words) > 5 or len(right_words) >= len(left_words):
        return False
    if len(left_words) - len(right_words) < 6:
        return False
    return left_words[-len(right_words) :] == right_words


def _is_closed_hangul_inserted_middle_revision(left: str, right: str) -> bool:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    left_words = _word_units(normalized_left)
    right_words = _word_units(normalized_right)
    if not (_has_hangul_words(left_words) and _has_hangul_words(right_words)):
        return False
    if _boundary_sentence_end_count(normalized_left) == 0 or _boundary_sentence_end_count(normalized_right) == 0:
        return False
    if len(right_words) < 7 or len(left_words) - len(right_words) < 6:
        return False
    prefix_len = 0
    for left_word, right_word in zip(left_words, right_words):
        if left_word != right_word:
            break
        prefix_len += 1
    if prefix_len < 4:
        return False
    suffix_len = 0
    max_suffix = len(right_words) - prefix_len
    while suffix_len < max_suffix and left_words[-(suffix_len + 1)] == right_words[-(suffix_len + 1)]:
        suffix_len += 1
    if suffix_len < 3:
        return False
    return prefix_len + suffix_len >= len(right_words)


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
    if (
        _is_cjk_text(left)
        or _is_cjk_text(right)
        or _has_hangul_words(left_words)
        or _has_hangul_words(right_words)
    ):
        if _is_cjk_shifted_prefix_dangling_tail_revision(left, right):
            return _normalized_text(right)
        if _is_cjk_prefixed_truncated_revision(left, right):
            return _normalized_text(right)
        if _is_cjk_prefixed_stale_revision(left, right):
            return _normalized_text(right)
        if _is_short_closed_cjk_suffix_revision(left, right):
            return _normalized_text(right)
        if _is_closed_hangul_inserted_middle_revision(left, right):
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
    staged_sentence_required_confirmations: int,
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
    revision_required_confirmations = max(staged_sentence_required_confirmations, 2)
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

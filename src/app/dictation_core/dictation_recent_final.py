from __future__ import annotations

from difflib import SequenceMatcher

from src.app.dictation.pipeline_settings import (
    recent_final_compact_common_coverage_min as _recent_final_compact_common_coverage_min,
    recent_final_compact_max_extra_ratio as _recent_final_compact_max_extra_ratio,
    recent_final_compact_similarity_min as _recent_final_compact_similarity_min,
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
)
from src.app.dictation_core.dictation_revision_text import (
    _best_common_word_run,
    _hangul_compact_key,
    _has_cjk_words,
    _has_hangul_words,
    _is_subsequence_at,
    _normalized_text,
    _sentence_delta_from_words,
    _word_units,
)
from src.app.dictation_core.sentence_boundary import sentence_end_count as _boundary_sentence_end_count


def _cjk_delta_from_words(words: list[str]) -> str:
    return "".join(words).strip()


_CJK_BOUNDARY_CHARS = "，,。！？?!、；;：:"


def _is_cjk_boundary_char(char: str) -> bool:
    return char in _CJK_BOUNDARY_CHARS


def _contains_word_sequence(words: list[str], candidate: list[str]) -> bool:
    if not candidate or len(candidate) > len(words):
        return False
    for start in range(0, len(words) - len(candidate) + 1):
        if _is_subsequence_at(words, candidate, start):
            return True
    return False


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
    candidate_hangul_key = _hangul_compact_key(candidate_words) if _has_hangul_words(candidate_words) else ""
    recent_hangul_key = _hangul_compact_key(recent_words) if _has_hangul_words(recent_words) else ""
    if candidate_hangul_key and candidate_hangul_key == recent_hangul_key and len(candidate_hangul_key) >= 2:
        return ""
    if min(len(candidate_key), len(recent_key)) < 8:
        return None
    if candidate_key == recent_key or candidate_key in recent_key:
        return ""
    matcher = SequenceMatcher(None, recent_key, candidate_key, autojunk=False)
    ratio = matcher.ratio()
    max_block = max((block.size for block in matcher.get_matching_blocks()), default=0)
    shorter = min(len(candidate_key), len(recent_key))
    longer = max(len(candidate_key), len(recent_key))
    if ratio >= _recent_final_compact_similarity_min():
        return ""
    if max_block / max(shorter, 1) >= _recent_final_compact_common_coverage_min() and (
        longer - max_block
    ) <= max(6, int(longer * _recent_final_compact_max_extra_ratio())):
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
    if _should_keep_closed_cjk_candidate_against_recent(
        normalized_candidate,
        candidate_words,
        normalized_recent,
        recent_words,
    ):
        return None, "keep_closed_cjk_candidate"
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
        cjk_blocks = [block for block in matcher.get_matching_blocks() if block.size >= 2]
        matched_recent = sum(block.size for block in cjk_blocks)
        if matched_recent >= 10 and matched_recent / max(len(recent_words), 1) >= 0.55:
            last_candidate_end = max((block.b + block.size for block in cjk_blocks), default=0)
            suffix_words = candidate_words[last_candidate_end:]
            if not suffix_words:
                return "", "cjk_block"
            if len(suffix_words) < 4:
                return "", "cjk_block_short_suffix"
            return _with_candidate_terminal(_cjk_delta_from_words(suffix_words), normalized_candidate), "cjk_block"
        _best_i, best_j, best_len = _best_common_word_run(recent_words, candidate_words)
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


def _should_keep_closed_cjk_candidate_against_recent(
    normalized_candidate: str,
    candidate_words: list[str],
    normalized_recent: str,
    recent_words: list[str],
) -> bool:
    if not (_has_cjk_words(candidate_words) and _has_cjk_words(recent_words)):
        return False
    if _boundary_sentence_end_count(normalized_candidate) <= 0 or _boundary_sentence_end_count(normalized_recent) <= 0:
        return False
    if len(candidate_words) < 8 or len(recent_words) < 8:
        return False

    recent_contains_candidate = normalized_recent.find(normalized_candidate)
    if recent_contains_candidate >= 0 and len(recent_words) >= len(candidate_words) + 6:
        before = normalized_recent[recent_contains_candidate - 1] if recent_contains_candidate > 0 else ""
        after_index = recent_contains_candidate + len(normalized_candidate)
        after = normalized_recent[after_index] if after_index < len(normalized_recent) else ""
        if recent_contains_candidate == 0 and after and _is_cjk_boundary_char(after):
            return True
        if recent_contains_candidate > 0 and _is_cjk_boundary_char(before):
            return True

    candidate_contains_recent = normalized_candidate.find(normalized_recent)
    if candidate_contains_recent > 0 and len(candidate_words) - len(recent_words) <= 4:
        if candidate_contains_recent <= 2:
            return True
        before = normalized_candidate[candidate_contains_recent - 1]
        if _is_cjk_boundary_char(before):
            return True

    if len(recent_words) >= len(candidate_words) + 6:
        best_i, best_j, best_len = _best_common_word_run(recent_words, candidate_words)
        if best_j == 0 and best_i >= 4 and best_len >= max(8, len(candidate_words) - 1):
            return True

    return False


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

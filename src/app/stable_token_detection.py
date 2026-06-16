from __future__ import annotations

from dataclasses import dataclass
import re


_WORD_UNIT_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"\d+(?:\.\d+)?[A-Za-z가-힣]*|"
    r"[A-Za-z가-힣]+|"
    r"[\u3400-\u4dbf\u4e00-\u9fff]"
)


@dataclass(frozen=True)
class StableWindowAnalysis:
    previous_text: str
    current_text: str
    stable_prefix_text: str
    unstable_tail_text: str
    stable_units: int
    current_units: int
    stable_prefix_chars: int
    unstable_tail_chars: int
    stable_internal_units: int
    stable_internal_chars: int
    stable_internal_ratio: float
    stable_token_ratio: float
    stable_overlap_source: str
    stage_support_score: float
    stage_support_bucket: str
    boundary_confidence: float | None


def normalized_text(text: str) -> str:
    return " ".join(str(text).split())


def has_cjk_chars(text: str) -> bool:
    return any("\u3400" <= ch <= "\u4dbf" or "\u4e00" <= ch <= "\u9fff" for ch in text)


def word_units(text: str) -> list[str]:
    return [match.group(0).replace(",", "").lower() for match in _WORD_UNIT_RE.finditer(normalized_text(text))]


def text_units(text: str, language: str) -> tuple[list[str], str]:
    normalized = normalized_text(text)
    if not normalized:
        return [], " "
    if str(language or "").strip().lower() == "zh" or has_cjk_chars(normalized):
        return list(normalized.replace(" ", "")), ""
    return word_units(normalized), " "


def join_units(units: list[str], separator: str) -> str:
    return separator.join(units).strip()


def stable_prefix_units(previous_units: list[str], current_units: list[str]) -> int:
    limit = min(len(previous_units), len(current_units))
    matched = 0
    while matched < limit and previous_units[matched] == current_units[matched]:
        matched += 1
    return matched


def suffix_prefix_overlap_units(previous_units: list[str], current_units: list[str]) -> int:
    limit = min(len(previous_units), len(current_units))
    for overlap in range(limit, 0, -1):
        if previous_units[-overlap:] == current_units[:overlap]:
            return overlap
    return 0


def longest_common_contiguous_units(previous_units: list[str], current_units: list[str]) -> tuple[int, int]:
    if not previous_units or not current_units:
        return 0, 0
    previous_match_lengths = [0] * (len(current_units) + 1)
    best_length = 0
    best_current_end = 0
    for previous_unit in previous_units:
        current_match_lengths = [0] * (len(current_units) + 1)
        for current_index, current_unit in enumerate(current_units, start=1):
            if previous_unit == current_unit:
                current_match_lengths[current_index] = previous_match_lengths[current_index - 1] + 1
                if current_match_lengths[current_index] > best_length:
                    best_length = current_match_lengths[current_index]
                    best_current_end = current_index
        previous_match_lengths = current_match_lengths
    return best_length, max(best_current_end - best_length, 0)


def stable_overlap_units(previous_units: list[str], current_units: list[str]) -> tuple[int, str]:
    prefix_units = stable_prefix_units(previous_units, current_units)
    suffix_units = suffix_prefix_overlap_units(previous_units, current_units)
    if suffix_units > prefix_units:
        return suffix_units, "suffix_prefix"
    if prefix_units > 0:
        return prefix_units, "common_prefix"
    return 0, "none"


def stable_stage_support_score(
    *,
    stable_token_ratio: float,
    stable_internal_ratio: float,
    stable_prefix_chars: int,
    unstable_tail_chars: int,
    stable_internal_chars: int,
    stable_overlap_source: str,
) -> float:
    prefix_score = stable_token_ratio
    internal_score = 0.0
    if stable_overlap_source == "none" and stable_internal_chars >= 18:
        internal_score = min(stable_internal_ratio, 0.85)
    score = max(prefix_score, internal_score)
    if score <= 0.0:
        return 0.0
    if stable_prefix_chars >= 12 and unstable_tail_chars <= 12:
        score += 0.10
    elif unstable_tail_chars > max(stable_prefix_chars, stable_internal_chars, 1):
        score -= 0.15
    return max(0.0, min(1.0, score))


def stable_stage_support_bucket(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.55:
        return "mid"
    if score > 0.0:
        return "low"
    return "none"


def analyze_stable_window(previous_text: str, current_text: str, language: str) -> StableWindowAnalysis:
    previous = normalized_text(previous_text)
    current = normalized_text(current_text)
    current_units, separator = text_units(current, language)
    previous_units, previous_separator = text_units(previous, language)
    if separator != previous_separator:
        previous_units, current_units, separator = list(previous), list(current), ""
    stable_units, stable_overlap_source = (
        stable_overlap_units(previous_units, current_units) if previous_units and current_units else (0, "none")
    )
    stable_prefix = join_units(current_units[:stable_units], separator)
    unstable_tail = join_units(current_units[stable_units:], separator)
    stable_internal_units, stable_internal_start = longest_common_contiguous_units(previous_units, current_units)
    stable_internal_text = join_units(
        current_units[stable_internal_start : stable_internal_start + stable_internal_units],
        separator,
    )
    ratio = stable_units / max(len(current_units), 1)
    stable_internal_ratio = stable_internal_units / max(len(current_units), 1)
    confidence: float | None
    if not previous_units or not current_units:
        confidence = None
    elif ratio >= 0.80:
        confidence = 0.85
    elif ratio >= 0.60:
        confidence = 0.70
    elif ratio >= 0.40:
        confidence = 0.55
    else:
        confidence = 0.35
    support_score = stable_stage_support_score(
        stable_token_ratio=ratio,
        stable_internal_ratio=stable_internal_ratio,
        stable_prefix_chars=len(stable_prefix),
        unstable_tail_chars=len(unstable_tail),
        stable_internal_chars=len(stable_internal_text),
        stable_overlap_source=stable_overlap_source,
    )
    return StableWindowAnalysis(
        previous_text=previous,
        current_text=current,
        stable_prefix_text=stable_prefix,
        unstable_tail_text=unstable_tail,
        stable_units=stable_units,
        current_units=len(current_units),
        stable_prefix_chars=len(stable_prefix),
        unstable_tail_chars=len(unstable_tail),
        stable_internal_units=stable_internal_units,
        stable_internal_chars=len(stable_internal_text),
        stable_internal_ratio=stable_internal_ratio,
        stable_token_ratio=ratio,
        stable_overlap_source=stable_overlap_source,
        stage_support_score=support_score,
        stage_support_bucket=stable_stage_support_bucket(support_score),
        boundary_confidence=confidence,
    )


def combine_boundary_confidence(
    segment_confidence: float | None,
    stability_confidence: float | None,
) -> float | None:
    if segment_confidence is None:
        return stability_confidence
    if stability_confidence is None:
        return segment_confidence
    return min(segment_confidence, stability_confidence)

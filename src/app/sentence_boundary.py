from __future__ import annotations

import re
from dataclasses import dataclass


SENTENCE_END_PATTERN = r"(?:(?<!\d)\.(?!\d)|[!?。！？…]+)"
SENTENCE_END_RE = re.compile(rf"(.+?{SENTENCE_END_PATTERN})(?=\s+|$)")
SENTENCE_END_MARK_RE = re.compile(SENTENCE_END_PATTERN)
SOFT_BOUNDARY_RE = re.compile(
    r"\s+(?=(?:But now|But if|And the|And you|So if|So it|So really|Here is|here is|Once you|once you|Now|Then|This|That|When|If|I like|You can|We can|They can)\b)"
)
MIN_SOFT_BOUNDARY_PREFIX_CHARS = 80
MIN_SOFT_BOUNDARY_SUFFIX_CHARS = 24


@dataclass(frozen=True)
class SentenceCandidate:
    text: str
    complete: bool
    confidence: float | None = None


@dataclass(frozen=True)
class SentenceBoundaryResult:
    completed: list[str]
    pending: str
    backend: str
    boundary_count: int
    soft_boundary_count: int = 0


def normalized_text(text: str) -> str:
    return " ".join(str(text).split())


def word_units(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", normalized_text(text).lower())


def text_units(text: str) -> tuple[list[str], str]:
    normalized = normalized_text(text)
    if not normalized:
        return [], " "
    if " " in normalized:
        return normalized.split(), " "
    return list(normalized), ""


def join_text_units(units: list[str], separator: str) -> str:
    return separator.join(units).strip()


def pending_new_text_combined(pending_text: str, new_text: str) -> str:
    pending = normalized_text(pending_text)
    new = normalized_text(new_text)
    if not pending:
        return new
    if not new:
        return pending
    pending_words = word_units(pending)
    new_words = word_units(new)
    if pending_words and new_words[: len(pending_words)] == pending_words:
        return new
    dangling_connectives = {"and", "but", "so", "or"}
    if len(pending_words) == 1 and pending_words[0] in dangling_connectives and new_words:
        return new
    if pending_words and len(pending_words) <= 4:
        max_start = len(new_words) - len(pending_words)
        for start in range(1, max_start + 1):
            if new_words[start : start + len(pending_words)] == pending_words:
                return new
    connective_words = {"and", "but", "because", "so", "or"}
    if pending_words and new_words and len(pending_words) <= 2 and pending_words[0] in connective_words and new_words[0] in connective_words:
        return new
    pending_units, pending_separator = text_units(pending)
    new_units, new_separator = text_units(new)
    if pending_separator != new_separator:
        return normalized_text(f"{pending} {new}")
    max_overlap = min(len(pending_units), len(new_units))
    for overlap in range(max_overlap, 0, -1):
        if pending_units[-overlap:] == new_units[:overlap]:
            return join_text_units(pending_units + new_units[overlap:], pending_separator)
    return normalized_text(f"{pending} {new}")


def sentence_end_count(text: str) -> int:
    return len(SENTENCE_END_MARK_RE.findall(text or ""))


class SentenceBoundaryDetector:
    backend = "base"

    def split(self, pending_text: str, new_text: str, language: str = "auto") -> SentenceBoundaryResult:
        raise NotImplementedError


class RegexSentenceBoundaryDetector(SentenceBoundaryDetector):
    backend = "regex"

    def split(self, pending_text: str, new_text: str, language: str = "auto") -> SentenceBoundaryResult:
        combined = pending_new_text_combined(pending_text, new_text)
        if not combined:
            return SentenceBoundaryResult([], "", self.backend, 0, 0)
        completed: list[str] = []
        consumed_end = 0
        for match in SENTENCE_END_RE.finditer(combined):
            sentence = match.group(1).strip()
            if sentence:
                completed.append(sentence)
            consumed_end = match.end(1)
        if consumed_end > 0:
            return SentenceBoundaryResult(completed, combined[consumed_end:].strip(), self.backend, len(completed), 0)
        soft_completed, soft_pending = self._split_soft_boundary(combined, language)
        if soft_completed:
            return SentenceBoundaryResult(soft_completed, soft_pending, self.backend, len(soft_completed), len(soft_completed))
        return SentenceBoundaryResult([], combined, self.backend, 0, 0)

    def _split_soft_boundary(self, text: str, language: str) -> tuple[list[str], str]:
        if language not in {"en", "auto"}:
            return [], text
        normalized = normalized_text(text)
        if len(normalized) < MIN_SOFT_BOUNDARY_PREFIX_CHARS + MIN_SOFT_BOUNDARY_SUFFIX_CHARS:
            return [], normalized
        candidates: list[tuple[int, str, str]] = []
        for match in SOFT_BOUNDARY_RE.finditer(normalized):
            index = match.start()
            left = normalized[:index].strip()
            right = normalized[index:].strip()
            left_lower = left.lower()
            right_lower = right.lower()
            if right_lower.startswith("now ") and left_lower.endswith(" but"):
                continue
            min_prefix_chars = 50 if right_lower.startswith("once you ") else MIN_SOFT_BOUNDARY_PREFIX_CHARS
            if len(left) < min_prefix_chars or len(right) < MIN_SOFT_BOUNDARY_SUFFIX_CHARS:
                continue
            if sentence_end_count(left) > 0:
                continue
            candidates.append((index, left, right))
        if not candidates:
            return [], normalized
        _index, left, right = candidates[-1]
        return [left], right


def split_completed_sentences(pending_text: str, new_text: str, language: str = "auto") -> tuple[list[str], str]:
    result = RegexSentenceBoundaryDetector().split(pending_text, new_text, language)
    return result.completed, result.pending

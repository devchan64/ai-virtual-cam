from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import Protocol

from src.app.model_cache import require_hf_repo_cached


SENTENCE_END_PATTERN = r"(?:(?<!\d)\.(?!\d)|[!?。！？…]+)"
SENTENCE_END_RE = re.compile(rf"(.+?{SENTENCE_END_PATTERN})(?=\s+|$)")
SENTENCE_END_MARK_RE = re.compile(SENTENCE_END_PATTERN)
SOFT_BOUNDARY_RE = re.compile(
    r"\s+(?=(?:But now|But if|And the|And you|So if|So it|So really|Here is|here is|Once you|once you|Now|Then|The|This|That|When|If|I like|You can|We can|They can)\b)"
)
MIN_SOFT_BOUNDARY_PREFIX_CHARS = 80
MIN_SOFT_BOUNDARY_SUFFIX_CHARS = 24
MIN_SOFT_BOUNDARY_CONFIDENCE = 0.55
SOFT_BOUNDARY_INCOMPLETE_TAIL_WORDS = {
    "a",
    "an",
    "and",
    "because",
    "but",
    "if",
    "or",
    "that",
    "the",
    "to",
    "which",
    "with",
}
ACK_SENTENCE_WORDS = {
    "okay",
    "ok",
    "right",
    "yeah",
    "yes",
    "no",
}
SENTENCE_BOUNDARY_BACKENDS = {"sat", "mock"}
DEFAULT_SAT_MODEL = "sat-3l-sm"


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


class SentenceBoundaryDetector(Protocol):
    backend: str

    def split(
        self,
        pending_text: str,
        new_text: str,
        language: str = "en",
        *,
        boundary_confidence: float | None = None,
    ) -> SentenceBoundaryResult:
        ...


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


def strip_incomplete_tail(text: str) -> str:
    normalized = normalized_text(text)
    units, separator = text_units(normalized)
    if separator != " " or not units:
        return normalized
    words = word_units(units[-1])
    if words and words[-1] in SOFT_BOUNDARY_INCOMPLETE_TAIL_WORDS:
        return join_text_units(units[:-1], separator)
    return normalized


def has_incomplete_tail(text: str) -> bool:
    words = word_units(text)
    return bool(words and words[-1] in SOFT_BOUNDARY_INCOMPLETE_TAIL_WORDS)


def starts_with_ack_sentence(text: str) -> bool:
    normalized = normalized_text(text)
    match = SENTENCE_END_RE.match(normalized)
    if not match:
        return False
    words = word_units(match.group(1))
    return len(words) == 1 and words[0] in ACK_SENTENCE_WORDS


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
    if has_incomplete_tail(pending) and starts_with_ack_sentence(new):
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


class SatSentenceBoundaryDetector:
    backend = "sat"

    def __init__(self, model: str | None = None, device: str = "cuda", compute_type: str = "float16") -> None:
        self.model = str(model or DEFAULT_SAT_MODEL).strip() or DEFAULT_SAT_MODEL
        self.device = str(device or "cuda").strip().lower()
        self.compute_type = str(compute_type or "float16").strip().lower()
        try:
            from wtpsplit import SaT
        except Exception as exc:
            raise ImportError(
                "sentence boundary backend 'sat' requires wtpsplit. "
                "Run ./bin/avc setup or install wtpsplit; regex fallback is intentionally disabled."
            ) from exc
        require_hf_repo_cached(self.model, purpose="SaT sentence boundary")
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*hf_xet\.download_files\(\) is deprecated.*",
                    category=DeprecationWarning,
                )
                self._segmenter = SaT(self.model)
            if self.compute_type == "float16":
                self._segmenter.half()
            if self.device != "cpu":
                self._segmenter.to(self.device)
        except Exception as exc:
            raise RuntimeError(
                "sentence boundary backend 'sat' initialization failed: "
                f"model={self.model} device={self.device} compute={self.compute_type}. "
                "Fail-Fast: fix the model/device/runtime instead of falling back to regex."
            ) from exc

    def split(
        self,
        pending_text: str,
        new_text: str,
        language: str = "en",
        *,
        boundary_confidence: float | None = None,
    ) -> SentenceBoundaryResult:
        del language
        del boundary_confidence
        combined = pending_new_text_combined(pending_text, new_text)
        if not combined:
            return SentenceBoundaryResult([], "", self.backend, 0, 0)
        normalized = normalized_text(combined)
        try:
            raw_segments = list(self._segmenter.split(normalized))
        except Exception as exc:
            raise RuntimeError(
                f"sat sentence segmentation failed: model={self.model} device={self.device} "
                f"compute={self.compute_type}. cause={type(exc).__name__}: {exc}. "
                "Fail-Fast: inspect wtpsplit/CUDA logs and fix the configured backend."
            ) from exc
        segments = [normalized_text(segment) for segment in raw_segments if normalized_text(segment)]
        if not segments:
            return SentenceBoundaryResult([], normalized, self.backend, 0, 0)
        if len(segments) == 1:
            only = segments[0]
            if sentence_end_count(only) > 0:
                return SentenceBoundaryResult([only], "", self.backend, 1, 0)
            return SentenceBoundaryResult([], only, self.backend, 0, 0)
        completed = segments[:-1]
        pending = segments[-1]
        if sentence_end_count(pending) > 0:
            completed.append(pending)
            pending = ""
        return SentenceBoundaryResult(completed, pending, self.backend, len(completed), 0)


def split_punctuated_text(text: str, backend: str) -> SentenceBoundaryResult:
    normalized = normalized_text(text)
    if not normalized:
        return SentenceBoundaryResult([], "", backend, 0, 0)
    completed: list[str] = []
    start = 0
    for match in SENTENCE_END_MARK_RE.finditer(normalized):
        end = match.end()
        sentence = normalized[start:end].strip()
        if sentence:
            completed.append(sentence)
        start = end
    if completed:
        return SentenceBoundaryResult(completed, normalized[start:].strip(), backend, len(completed), 0)
    return SentenceBoundaryResult([], normalized, backend, 0, 0)


class LegacyRegexSentenceBoundaryDetector:
    backend = "legacy-regex"

    def split(
        self,
        pending_text: str,
        new_text: str,
        language: str = "en",
        *,
        boundary_confidence: float | None = None,
    ) -> SentenceBoundaryResult:
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
        soft_completed, soft_pending = self._split_soft_boundary(
            combined, language, boundary_confidence=boundary_confidence
        )
        if soft_completed:
            return SentenceBoundaryResult(soft_completed, soft_pending, self.backend, len(soft_completed), len(soft_completed))
        return SentenceBoundaryResult([], combined, self.backend, 0, 0)

    def _split_soft_boundary(
        self,
        text: str,
        language: str,
        boundary_confidence: float | None = None,
    ) -> tuple[list[str], str]:
        if language != "en":
            return [], text
        if boundary_confidence is not None and boundary_confidence < MIN_SOFT_BOUNDARY_CONFIDENCE:
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
            left = strip_incomplete_tail(left)
            if len(left) < min_prefix_chars:
                continue
            candidates.append((index, left, right))
        if not candidates:
            return [], normalized
        _index, left, right = candidates[-1]
        return [left], right


class MockSentenceBoundaryDetector:
    backend = "mock"

    def split(
        self,
        pending_text: str,
        new_text: str,
        language: str = "en",
        *,
        boundary_confidence: float | None = None,
    ) -> SentenceBoundaryResult:
        del language
        del boundary_confidence
        combined = pending_new_text_combined(pending_text, new_text)
        return SentenceBoundaryResult([], combined, self.backend, 0, 0)


def create_sentence_boundary_detector(
    backend: str,
    *,
    model: str | None = None,
    device: str = "cuda",
    compute_type: str = "float16",
    language: str | None = None,
) -> SentenceBoundaryDetector:
    del language
    normalized_backend = str(backend or "sat").strip().lower()
    if normalized_backend == "sat":
        return SatSentenceBoundaryDetector(model=model, device=device, compute_type=compute_type)
    if normalized_backend == "mock":
        return MockSentenceBoundaryDetector()
    raise ValueError(
        f"unsupported sentence boundary backend: {backend!r}. "
        "Use one of: sat, mock"
    )


def split_completed_sentences(
    pending_text: str,
    new_text: str,
    language: str = "en",
    *,
    boundary_confidence: float | None = None,
) -> tuple[list[str], str]:
    # Legacy regression helper. Runtime code must use create_sentence_boundary_detector().
    result = LegacyRegexSentenceBoundaryDetector().split(
        pending_text,
        new_text,
        language,
        boundary_confidence=boundary_confidence,
    )
    return result.completed, result.pending

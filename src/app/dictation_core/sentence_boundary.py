from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import Protocol

from src.app.models.model_cache import require_hf_repo_cached


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
    end_mark_count: int = 0
    right_context_start_count: int = 0


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


def boundary_input_text(pending_text: str, new_text: str) -> str:
    pending = normalized_text(pending_text)
    new = normalized_text(new_text)
    if not pending:
        return new
    if not new:
        return pending
    return normalized_text(f"{pending} {new}")


def sentence_end_count(text: str) -> int:
    return len(SENTENCE_END_MARK_RE.findall(text or ""))


def _right_context_start_count(completed: list[str], pending: str, soft_boundary_count: int) -> int:
    hard_contexts = max(0, len(completed) - 1)
    if completed and normalized_text(pending):
        hard_contexts += 1
    return max(hard_contexts, soft_boundary_count)


def _boundary_result(
    completed: list[str],
    pending: str,
    backend: str,
    *,
    boundary_count: int | None = None,
    soft_boundary_count: int = 0,
    source_text: str = "",
) -> SentenceBoundaryResult:
    normalized_pending = normalized_text(pending)
    normalized_completed = [normalized_text(sentence) for sentence in completed if normalized_text(sentence)]
    count = len(normalized_completed) if boundary_count is None else int(boundary_count)
    signal_text = source_text or " ".join([*normalized_completed, normalized_pending]).strip()
    end_marks = sentence_end_count(signal_text)
    right_contexts = _right_context_start_count(normalized_completed, normalized_pending, soft_boundary_count)
    return SentenceBoundaryResult(
        normalized_completed,
        normalized_pending,
        backend,
        count,
        soft_boundary_count,
        end_marks,
        right_contexts,
    )


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
        combined = boundary_input_text(pending_text, new_text)
        if not combined:
            return _boundary_result([], "", self.backend)
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
            return _boundary_result([], normalized, self.backend, source_text=normalized)
        if len(segments) == 1:
            only = segments[0]
            if sentence_end_count(only) > 0:
                return _boundary_result([only], "", self.backend, boundary_count=1, source_text=normalized)
            return _boundary_result([], only, self.backend, source_text=normalized)
        completed = segments[:-1]
        pending = segments[-1]
        if sentence_end_count(pending) > 0:
            completed.append(pending)
            pending = ""
        return _boundary_result(completed, pending, self.backend, source_text=normalized)


def split_punctuated_text(text: str, backend: str) -> SentenceBoundaryResult:
    normalized = normalized_text(text)
    if not normalized:
        return _boundary_result([], "", backend)
    completed: list[str] = []
    start = 0
    for match in SENTENCE_END_MARK_RE.finditer(normalized):
        end = match.end()
        sentence = normalized[start:end].strip()
        if sentence:
            completed.append(sentence)
        start = end
    if completed:
        return _boundary_result(completed, normalized[start:].strip(), backend, source_text=normalized)
    return _boundary_result([], normalized, backend, source_text=normalized)


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
        combined = boundary_input_text(pending_text, new_text)
        if not combined:
            return _boundary_result([], "", self.backend)
        completed: list[str] = []
        consumed_end = 0
        for match in SENTENCE_END_RE.finditer(combined):
            sentence = match.group(1).strip()
            if sentence:
                completed.append(sentence)
            consumed_end = match.end(1)
        if consumed_end > 0:
            return _boundary_result(completed, combined[consumed_end:].strip(), self.backend, source_text=combined)
        soft_completed, soft_pending = self._split_soft_boundary(
            combined, language, boundary_confidence=boundary_confidence
        )
        if soft_completed:
            return _boundary_result(
                soft_completed,
                soft_pending,
                self.backend,
                soft_boundary_count=len(soft_completed),
                source_text=combined,
            )
        return _boundary_result([], combined, self.backend, source_text=combined)

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
        combined = boundary_input_text(pending_text, new_text)
        return _boundary_result([], combined, self.backend, source_text=combined)


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

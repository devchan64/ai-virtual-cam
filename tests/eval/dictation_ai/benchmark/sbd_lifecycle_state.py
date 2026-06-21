from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class LifecycleState:
    language: str = ""
    committed_text: str = ""
    pending_text: str = ""
    pending_chunks: int = 0
    staged_sentence: str = ""
    staged_confirmations: int = 0
    staged_age: int = 0
    staged_forced: bool = False
    staged_deferred_age_chunk: int = -1
    staged_delta_suppressed_chunks: int = 0
    staged_delta_suppressed_chunk_index: int = -1
    no_text_stage_skip_chunks: int = 0
    staged_queue: deque[dict[str, object]] | None = None
    final_sentences: list[str] | None = None
    metrics: dict[str, int] | None = None
    previous_window_text: str = ""
    stable_analysis: Any = None

    def __post_init__(self) -> None:
        if self.staged_queue is None:
            self.staged_queue = deque()
        if self.final_sentences is None:
            self.final_sentences = []
        if self.metrics is None:
            self.metrics = {}

    def count(self, name: str, amount: int = 1) -> None:
        assert self.metrics is not None
        self.metrics[name] = self.metrics.get(name, 0) + amount


def _stable_internal_ratio(state: LifecycleState) -> float:
    return float(getattr(state.stable_analysis, "stable_internal_ratio", 0.0) or 0.0)


def _stable_internal_chars(state: LifecycleState) -> int:
    return int(getattr(state.stable_analysis, "stable_internal_chars", 0) or 0)


def _stable_overlap_source(state: LifecycleState) -> str:
    return str(getattr(state.stable_analysis, "stable_overlap_source", "") or "")

from __future__ import annotations
"""Shared state container for stage loop facade helpers."""

from dataclasses import dataclass
from typing import Callable

from src.app.dictation.pipeline_runtime_support import RuntimeLoopSupport
from src.app.dictation.pipeline_types import ActiveStage, CommitBufferNode, StableAnalysis, TranscriptWorkerLike
from src.app.dictation_core.dictation_revision_progression import _revision_internal_stability_bucket


@dataclass(slots=True)
class StageFacadeContext:
    worker: TranscriptWorkerLike
    loop_support: RuntimeLoopSupport
    active_stage: ActiveStage
    commit_buffer_node: CommitBufferNode
    sentence_finalize_age: int
    staged_queue_max_promotion_age_chunks: Callable[[], int]
    delta_suppressed_stage_max_chunks: Callable[[], int]
    no_text_stale_stage_suppress_chunks: Callable[[], int]
    chunk_index: int = 0
    committed_text: str = ""
    next_final_segment_id: int = 1
    stable_analysis: StableAnalysis | None = None
    queue_promotion_backlog_boost_remaining: int = 0
    prepared_candidate_recent_final_trimmed: bool = False

    def sync_chunk(
        self,
        *,
        chunk_index: int,
        committed_text: str,
        stable_analysis: StableAnalysis,
    ) -> None:
        self.chunk_index = chunk_index
        self.committed_text = committed_text
        self.stable_analysis = stable_analysis

    def count_metric(self, name: str, amount: int = 1) -> None:
        self.loop_support.count_metric(name, amount)

    def count_segment_state(self, state: str, amount: int = 1) -> None:
        self.loop_support.count_segment_state(state, amount)

    def is_repeated_hallucination(self, text: str) -> bool:
        return self.loop_support.is_repeated_hallucination(text)

    def remember_transcript(self, text: str) -> None:
        self.loop_support.remember_transcript(text)

    def require_stable_analysis(self) -> StableAnalysis:
        if self.stable_analysis is None:
            raise RuntimeError("stable_analysis must be synced before stage operations")
        return self.stable_analysis

    def count_recent_final_stable_internal_suppression(self, prefix: str) -> None:
        stable_analysis = self.require_stable_analysis()
        bucket = _revision_internal_stability_bucket(
            stable_analysis.stable_internal_ratio,
            stable_analysis.stable_internal_chars,
        )
        self.count_metric(f"{prefix}_stable_internal_{bucket}", 1)

    def set_prepared_candidate_recent_final_trimmed(self, value: bool) -> None:
        self.prepared_candidate_recent_final_trimmed = value

from __future__ import annotations

from collections import deque
from typing import Any, Callable

from src.app.dictation_pipeline_contracts import ActiveSentenceCandidate
from src.app.dictation_transcript_logic import (
    _next_revision_confirmation_count,
    _prefer_sentence_revision,
    _sentences_are_revisions,
    _should_reset_revision_age,
)


MetricCounter = Callable[[str, int], None]


class SentenceCandidateCommitBufferNode:
    def __init__(self, max_size: int) -> None:
        self.active = ActiveSentenceCandidate()
        self._queue: deque[dict[str, object]] = deque()
        self._max_size = max_size

    def __len__(self) -> int:
        return len(self._queue)

    def enqueue_or_revision(
        self,
        *,
        candidate: str,
        forced: bool,
        chunk_index: int,
        stable_analysis: Any,
        count_metric: MetricCounter,
        count_segment_state: MetricCounter,
    ) -> None:
        for entry in self._queue:
            queued_sentence = str(entry["sentence"])
            if not _sentences_are_revisions(queued_sentence, candidate):
                continue
            preferred = _prefer_sentence_revision(queued_sentence, candidate)
            reset_age = _should_reset_revision_age(
                queued_sentence,
                preferred,
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            )
            entry["sentence"] = preferred
            entry["confirmations"] = _next_revision_confirmation_count(
                queued_sentence,
                preferred,
                int(entry["confirmations"]),
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            )
            entry["age"] = 0 if reset_age else int(entry["age"]) + 1
            entry["forced"] = bool(entry["forced"]) or forced
            entry["deferred_age_chunk"] = chunk_index
            count_metric("stage_queue_revision", 1)
            if reset_age:
                count_metric("stage_queue_revision_age_reset", 1)
            count_metric("stage_age_tick", 1)
            return

        if len(self._queue) >= self._max_size:
            self._queue.popleft()
            count_metric("stage_queue_drop_oldest", 1)
        self._queue.append(
            {
                "sentence": candidate,
                "confirmations": 1,
                "age": 0,
                "forced": forced,
                "deferred_age_chunk": chunk_index,
            }
        )
        count_metric("stage_queue_enqueue", 1)
        count_segment_state("staged", 1)

    def promote_if_idle(
        self,
        *,
        chunk_index: int,
        count_metric: MetricCounter,
        count_segment_state: MetricCounter,
    ) -> bool:
        if self.active.sentence or not self._queue:
            return False
        entry = self._queue.popleft()
        deferred_age_chunk = int(entry["deferred_age_chunk"])
        if deferred_age_chunk < 0:
            entry["deferred_age_chunk"] = chunk_index
        else:
            entry["age"] = max(int(entry["age"]), chunk_index - deferred_age_chunk)
        self.active.apply_buffer_entry(entry)
        count_metric("stage_queue_promote", 1)
        count_metric("stage_start", 1)
        count_segment_state("staged", 1)
        return True

from __future__ import annotations

from collections import deque
from typing import Any, Callable

from src.app.dictation_pipeline_contracts import ActiveSentenceCandidate
from src.app.dictation_transcript_logic import (
    _next_revision_confirmation_count,
    _prefer_sentence_revision,
    _sentence_end_count,
    _sentences_are_revisions,
    _should_reset_revision_age,
    _staged_sentence_required_confirmations,
)


MetricCounter = Callable[[str, int], None]


class SentenceCandidateCommitBufferNode:
    def __init__(self, max_size: int) -> None:
        self.active = ActiveSentenceCandidate()
        self._queue: deque[dict[str, object]] = deque()
        self._max_size = max_size

    def __len__(self) -> int:
        return len(self._queue)

    def queued_sentences(self) -> tuple[str, ...]:
        return tuple(str(entry["sentence"]) for entry in self._queue)

    def prefer_queued_revision_for_active(
        self,
        *,
        chunk_index: int,
        max_promotion_age_chunks: int,
        count_metric: MetricCounter,
        count_segment_state: MetricCounter,
        finalize_reason: str = "",
    ) -> bool:
        active_sentence = self.active.sentence
        if not active_sentence:
            return False
        index = 0
        while index < len(self._queue):
            entry = self._queue[index]
            queued_deferred_age_chunk = int(entry["deferred_age_chunk"])
            queued_age = int(entry["age"])
            if queued_deferred_age_chunk >= 0:
                queued_age = max(queued_age, chunk_index - queued_deferred_age_chunk)
            entry["age"] = queued_age
            if queued_age > max_promotion_age_chunks:
                del self._queue[index]
                count_metric("stage_queue_stale_promote_suppressed", 1)
                count_segment_state("suppressed", 1)
                continue
            queued_sentence = str(entry["sentence"])
            if not _sentences_are_revisions(active_sentence, queued_sentence):
                index += 1
                continue
            preferred = _prefer_sentence_revision(active_sentence, queued_sentence)
            if preferred == active_sentence:
                index += 1
                continue
            queued_confirmations = int(entry["confirmations"])
            queued_forced = bool(entry["forced"]) or self.active.forced
            # 확정 가능한 active 문장은 더 강한 boundary 근거가 없는 낮은
            # confirmation queued revision에 append-only 순서를 빼앗기지 않는다.
            if (
                _sentence_end_count(active_sentence) > 0
                and _sentence_end_count(preferred) <= _sentence_end_count(active_sentence)
                and queued_confirmations < _staged_sentence_required_confirmations(preferred, queued_forced)
            ):
                count_metric("stage_queue_revision_preempt_deferred", 1)
                if finalize_reason:
                    count_metric(f"stage_queue_revision_preempt_deferred_{finalize_reason}", 1)
                index += 1
                continue
            entry["sentence"] = preferred
            self.active.apply_buffer_entry(entry)
            del self._queue[index]
            count_metric("stage_finalize_deferred_for_queue_revision", 1)
            count_metric("stage_revision", 1)
            count_segment_state("revised", 1)
            return True
        return False

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
            if reset_age:
                # 같은 queued 발화의 불안정한 revision은 새 세그먼트로 분리하지 않는다.
                count_metric("stage_queue_revision_token_sentence_deferred", 1)
                return
            entry["sentence"] = preferred
            entry["confirmations"] = _next_revision_confirmation_count(
                queued_sentence,
                preferred,
                int(entry["confirmations"]),
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            )
            entry["age"] = int(entry["age"]) + 1
            entry["forced"] = bool(entry["forced"]) or forced
            entry["deferred_age_chunk"] = chunk_index
            count_metric("stage_queue_revision", 1)
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
        max_promotion_age_chunks: int,
        count_metric: MetricCounter,
        count_segment_state: MetricCounter,
    ) -> bool:
        if self.active.sentence or not self._queue:
            return False
        while self._queue:
            entry = self._queue.popleft()
            deferred_age_chunk = int(entry["deferred_age_chunk"])
            if deferred_age_chunk < 0:
                entry["deferred_age_chunk"] = chunk_index
            else:
                entry["age"] = max(int(entry["age"]), chunk_index - deferred_age_chunk)
            if int(entry["age"]) > max_promotion_age_chunks:
                count_metric("stage_queue_stale_promote_suppressed", 1)
                count_segment_state("suppressed", 1)
                continue
            self.active.apply_buffer_entry(entry)
            count_metric("stage_queue_promote", 1)
            count_metric("stage_start", 1)
            count_segment_state("staged", 1)
            return True
        return False

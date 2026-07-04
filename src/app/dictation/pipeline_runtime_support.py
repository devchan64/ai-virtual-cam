from __future__ import annotations
"""Shared runtime state helpers for the dictation loop.

This module owns recent-transcript memory and lifecycle metric aggregation.
It is the first place to inspect when a change is about metric shape,
hallucination repetition tracking, or runtime stability summaries rather than
sentence lifecycle policy itself.
"""

from collections import deque


RUNTIME_STABILITY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "lifecycle",
        (
            "replace",
            "replaced_unconfirmed",
            "revision",
            "revision_changed",
            "finalized",
            "stage_start",
            "finalized_per_stage_start",
            "replace_unconfirmed_rate",
        ),
    ),
    (
        "queue",
        (
            "stage_queue_enqueue",
            "stage_queue_promote",
            "stage_queue_revision",
            "stage_queue_revision_token_sentence_deferred",
            "stage_replace_deferred_same_chunk",
            "stage_queue_len",
        ),
    ),
    (
        "finalize",
        (
            "finalize_before_replace",
            "age_finalize",
            "age_quality_blocked",
            "age_no_text_skipped",
            "no_text_stale_suppressed",
            "unconfirmed_replacement_suppressed",
        ),
    ),
    (
        "suppression",
        (
            "duplicate_suppressed",
            "finalize_delta_suppressed_stage_retained",
            "finalize_delta_suppressed_stage_dropped",
            "finalize_delta_fragment_preserved",
            "delta_trimmed",
        ),
    ),
    (
        "quality",
        (
            "stage_candidate_quality_blocked",
            "stage_candidate_quality",
            "final_quality",
            "translation_skip",
            "raw_without_final",
        ),
    ),
    (
        "state",
        (
            "segment_state_pending",
            "segment_state_staged",
            "segment_state_final",
            "segment_state_suppressed",
            "segment_state_revised",
        ),
    ),
    (
        "stability",
        (
            "stable_prefix_chars",
            "unstable_tail_chars",
            "stable_internal_chars",
            "stable_internal_ratio",
            "stable_token_ratio",
            "input_queue_size_peak",
            "input_queue_backlog",
            "decision_count",
        ),
    ),
)


def format_runtime_stability_groups(metrics: dict[str, object]) -> str:
    sections: list[str] = []
    for label, keys in RUNTIME_STABILITY_GROUPS:
        parts = [f"{key}={metrics[key]}" for key in keys if key in metrics]
        if parts:
            sections.append(f"{label}[{' '.join(parts)}]")
    return " ".join(sections)


class RuntimeLoopSupport:
    def __init__(self, *, max_recent_short_text_repeats: int, recent_transcript_window: int) -> None:
        self.lifecycle_metrics: dict[str, int] = {}
        self.chunk_lifecycle_metrics: dict[str, int] = {}
        self.recent_transcripts: deque[str] = deque(maxlen=recent_transcript_window)
        self._max_recent_short_text_repeats = max_recent_short_text_repeats

    def count_metric(self, name: str, amount: int = 1) -> None:
        self.lifecycle_metrics[name] = self.lifecycle_metrics.get(name, 0) + amount
        self.chunk_lifecycle_metrics[name] = self.chunk_lifecycle_metrics.get(name, 0) + amount

    def count_segment_state(self, state: str, amount: int = 1) -> None:
        self.count_metric(f"segment_state_{state}", amount)

    def clear_chunk_metrics(self) -> None:
        self.chunk_lifecycle_metrics.clear()

    def observe_input_queue(
        self,
        *,
        current_queue_size: int,
        chunk_audio_queue_drops: int,
        backlog_threshold: int,
    ) -> None:
        self.chunk_lifecycle_metrics["input_queue_size_peak"] = max(
            self.chunk_lifecycle_metrics.get("input_queue_size_peak", 0),
            current_queue_size,
        )
        self.lifecycle_metrics["input_queue_size_peak"] = max(
            self.lifecycle_metrics.get("input_queue_size_peak", 0),
            current_queue_size,
        )
        if current_queue_size >= backlog_threshold:
            self.count_metric("input_queue_backlog_chunk")
        if chunk_audio_queue_drops:
            self.chunk_lifecycle_metrics["input_queue_drops"] = chunk_audio_queue_drops
            self.lifecycle_metrics["input_queue_drops"] = (
                self.lifecycle_metrics.get("input_queue_drops", 0) + chunk_audio_queue_drops
            )

    def build_runtime_stability_metrics(
        self,
        *,
        queue_len: int,
        raw_window_has_text: bool,
        final_segments_count: int,
    ) -> dict[str, object]:
        metrics = self.chunk_lifecycle_metrics
        raw_without_final_count = 1 if raw_window_has_text and not final_segments_count else 0
        if raw_without_final_count:
            self.count_metric("raw_without_final")
        stage_decision_count = sum(
            value for key, value in metrics.items() if key.startswith("stage_replace_decision_")
        )
        stage_candidate_quality_count = sum(
            value
            for key, value in metrics.items()
            if key.startswith("stage_candidate_quality_") and key != "stage_candidate_quality_blocked"
        )
        final_quality_count = sum(
            value for key, value in metrics.items() if key.startswith("final_quality_")
        )
        return {
            "replace": metrics.get("stage_replace", 0),
            "replaced_unconfirmed": metrics.get("stage_replaced_unconfirmed", 0),
            "revision": metrics.get("stage_revision", 0),
            "revision_changed": metrics.get("stage_revision_changed", 0),
            "finalized": metrics.get("finalized", 0),
            "stage_start": metrics.get("stage_start", 0),
            "finalized_per_stage_start": (
                f"{metrics.get('finalized', 0) / max(metrics.get('stage_start', 0), 1):.2f}"
            ),
            "replace_unconfirmed_rate": (
                f"{metrics.get('stage_replaced_unconfirmed', 0) / max(metrics.get('stage_replace', 0), 1):.2f}"
            ),
            "stage_queue_enqueue": metrics.get("stage_queue_enqueue", 0),
            "stage_queue_promote": metrics.get("stage_queue_promote", 0),
            "stage_queue_revision": metrics.get("stage_queue_revision", 0),
            "stage_queue_revision_token_sentence_deferred": metrics.get(
                "stage_queue_revision_token_sentence_deferred",
                0,
            ),
            "stage_replace_deferred_same_chunk": metrics.get("stage_replace_deferred_same_chunk", 0),
            "stage_queue_len": queue_len,
            "finalize_before_replace": metrics.get("stage_finalize_before_replace", 0),
            "age_finalize": metrics.get("stage_age_finalize", 0),
            "age_quality_blocked": metrics.get("stage_age_quality_blocked", 0),
            "age_no_text_skipped": metrics.get("stage_age_no_text_skipped", 0),
            "no_text_stale_suppressed": metrics.get("stage_no_text_stale_suppressed", 0),
            "unconfirmed_replacement_suppressed": metrics.get(
                "stage_unconfirmed_replacement_suppressed",
                0,
            ),
            "duplicate_suppressed": metrics.get("candidate_duplicate_suppressed", 0),
            "finalize_delta_suppressed_stage_retained": metrics.get(
                "finalize_delta_suppressed_stage_retained",
                0,
            ),
            "finalize_delta_suppressed_stage_dropped": metrics.get(
                "finalize_delta_suppressed_stage_dropped",
                0,
            ),
            "finalize_delta_fragment_preserved": metrics.get("finalize_delta_fragment_preserved", 0),
            "delta_trimmed": metrics.get("candidate_delta_trimmed", 0),
            "stage_candidate_quality_blocked": metrics.get("stage_candidate_quality_blocked", 0),
            "stage_candidate_quality": stage_candidate_quality_count,
            "segment_state_pending": metrics.get("segment_state_pending", 0),
            "segment_state_staged": metrics.get("segment_state_staged", 0),
            "segment_state_final": metrics.get("segment_state_final", 0),
            "segment_state_suppressed": metrics.get("segment_state_suppressed", 0),
            "segment_state_revised": metrics.get("segment_state_revised", 0),
            "final_quality": final_quality_count,
            "translation_skip": metrics.get("translation_skip_final_quality", 0),
            "raw_without_final": raw_without_final_count,
            "stable_prefix_chars": metrics.get("stable_prefix_chars", 0),
            "unstable_tail_chars": metrics.get("unstable_tail_chars", 0),
            "stable_internal_chars": metrics.get("stable_internal_chars", 0),
            "stable_internal_ratio": f"{metrics.get('stable_internal_ratio_per_1000', 0) / 1000:.3f}",
            "stable_token_ratio": f"{metrics.get('stable_token_ratio_per_1000', 0) / 1000:.3f}",
            "input_queue_size_peak": metrics.get("input_queue_size_peak", 0),
            "input_queue_backlog": metrics.get("input_queue_backlog_chunk", 0),
            "decision_count": stage_decision_count,
        }

    def is_repeated_hallucination(self, text: str) -> bool:
        normalized = " ".join(text.split())
        if not normalized:
            return False
        repeats = sum(1 for item in self.recent_transcripts if item == normalized)
        return len(normalized) <= 24 and repeats >= self._max_recent_short_text_repeats

    def remember_transcript(self, text: str) -> None:
        normalized = " ".join(text.split())
        if normalized:
            self.recent_transcripts.append(normalized)

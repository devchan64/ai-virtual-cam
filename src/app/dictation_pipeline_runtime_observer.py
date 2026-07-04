from __future__ import annotations
"""Chunk-level runtime observation helpers for the realtime dictation loop."""

from dataclasses import dataclass

from src.app.dictation_pipeline_runtime_support import RuntimeLoopSupport


@dataclass(frozen=True, slots=True)
class ChunkRuntimeObservation:
    current_audio_queue_drops: int
    chunk_audio_queue_drops: int
    current_queue_size: int
    runtime_stability_metrics: dict[str, object]


def observe_chunk_runtime(
    *,
    loop_support: RuntimeLoopSupport,
    current_audio_queue_drops: int,
    last_audio_queue_drops: int,
    current_queue_size: int,
    backlog_threshold: int,
    queue_len: int,
    raw_window_has_text: bool,
    final_segments_count: int,
) -> ChunkRuntimeObservation:
    chunk_audio_queue_drops = current_audio_queue_drops - last_audio_queue_drops
    loop_support.observe_input_queue(
        current_queue_size=current_queue_size,
        chunk_audio_queue_drops=chunk_audio_queue_drops,
        backlog_threshold=backlog_threshold,
    )
    runtime_stability_metrics = loop_support.build_runtime_stability_metrics(
        queue_len=queue_len,
        raw_window_has_text=raw_window_has_text,
        final_segments_count=final_segments_count,
    )
    return ChunkRuntimeObservation(
        current_audio_queue_drops=current_audio_queue_drops,
        chunk_audio_queue_drops=chunk_audio_queue_drops,
        current_queue_size=current_queue_size,
        runtime_stability_metrics=runtime_stability_metrics,
    )

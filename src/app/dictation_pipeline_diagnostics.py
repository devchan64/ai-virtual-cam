from __future__ import annotations
"""Diagnostic and runtime log assembly for the dictation pipeline.

Metrics and status lines are kept here so lifecycle logic can stay focused on
state transitions. When adding or removing operator-facing logs, update this
module and the design document's observation contract together.
"""

from typing import Callable

from src.app.dictation_revision_progression import _diagnostic_tail, _pending_text_diagnostic_flags, _sentence_end_count
from src.app.dictation_transcript_logic import _format_transcript_metrics, _normalized_text, _pending_overrun_reason
from src.app.dictation_pipeline_types import StableAnalysis, TranscriptWorkerLike
from src.app.transcript_revision import revision_lifecycle_context as _revision_lifecycle_context


def record_pending_diagnostics(
    *,
    count_metric: Callable[[str, int], None],
    detected: str,
    pending_transcript_text: str,
    pending_chunks: int,
) -> tuple[str | None, list[str]]:
    pending_overrun_reason = _pending_overrun_reason(pending_transcript_text, pending_chunks)
    if pending_overrun_reason:
        count_metric("pending_overrun")
        count_metric(f"pending_overrun_reason_{pending_overrun_reason}")
    pending_quality_flags = _pending_text_diagnostic_flags(
        pending_transcript_text,
        detected,
        pending_chunks,
    )
    for flag in pending_quality_flags:
        count_metric(f"pending_quality_{flag}")
    return pending_overrun_reason, pending_quality_flags


def emit_sentence_diagnostics(
    *,
    worker: TranscriptWorkerLike,
    chunk_index: int,
    completed_count: int,
    final_count: int,
    pending_overrun_reason: str | None,
    pending_quality_flags: list[str],
    detected: str,
    pending_transcript_text: str,
    pending_chunks: int,
    window_text: str,
    stable_text: str,
    delta_text: str,
    stable_analysis: StableAnalysis,
    committed_text: str,
    active_stage_sentence: str,
    boundary_complete: int,
    boundary_soft: int,
    boundary_confidence_display: str,
    boundary_end_marks: int,
    boundary_right_context_starts: int,
    boundary_conf_segment: object,
    boundary_conf_stable: object,
    chunk_metrics: dict[str, int],
    lifecycle_metrics: dict[str, int],
    staged_confirmations: int,
    staged_age: int,
    staged_forced: bool,
) -> None:
    worker._emit(
        "status",
        "받아쓰기 AI 문장 진단: "
        f"chunk={chunk_index} completed={completed_count} final={final_count} "
        f"pending_overrun={pending_overrun_reason or 'none'} "
        f"pending_quality={','.join(pending_quality_flags) or 'none'} "
        f"boundary_backend={worker._sentence_boundary_detector.backend} "
        f"boundary_complete={boundary_complete} boundary_soft={boundary_soft} boundary_conf={boundary_confidence_display} "
        f"boundary_end_marks={boundary_end_marks} boundary_right_context={boundary_right_context_starts} "
        f"boundary_conf_segment={boundary_conf_segment if boundary_conf_segment is not None else 'n/a'} "
        f"boundary_conf_stable={boundary_conf_stable if boundary_conf_stable is not None else 'n/a'} "
        f"pending_chars={len(pending_transcript_text)} pending_chunks={pending_chunks} "
        f"pending_chars_per_chunk={len(pending_transcript_text) / max(pending_chunks, 1):.1f} "
        f"window_chars={len(_normalized_text(window_text))} stable_chars={len(_normalized_text(stable_text))} "
        f"stable_prefix_chars={stable_analysis.stable_prefix_chars} "
        f"unstable_tail_chars={stable_analysis.unstable_tail_chars} "
        f"stable_internal_chars={stable_analysis.stable_internal_chars} "
        f"stable_internal_ratio={stable_analysis.stable_internal_ratio:.3f} "
        f"stable_token_ratio={stable_analysis.stable_token_ratio:.3f} "
        f"stable_overlap_source={stable_analysis.stable_overlap_source} "
        f"delta_chars={len(_normalized_text(delta_text))} "
        f"end_marks_window={_sentence_end_count(window_text)} end_marks_stable={_sentence_end_count(stable_text)} "
        f"end_marks_delta={_sentence_end_count(delta_text)} "
        f"stable_tail={_diagnostic_tail(stable_text)} delta_tail={_diagnostic_tail(delta_text)} "
        f"pending_tail={_diagnostic_tail(pending_transcript_text)} "
        f"revision_context_chars={len(_normalized_text(_revision_lifecycle_context(committed_text, active_stage_sentence, pending_transcript_text)))} "
        f"chunk_metrics={_format_transcript_metrics(chunk_metrics)} "
        f"lifecycle_metrics={_format_transcript_metrics(lifecycle_metrics)} "
        f"staged_confirmations={staged_confirmations} staged_age={staged_age} staged_forced={staged_forced} "
        f"staged_tail={_diagnostic_tail(active_stage_sentence)}",
        display=False,
    )


def emit_runtime_performance(
    *,
    worker: TranscriptWorkerLike,
    chunk_index: int,
    step_seconds: float,
    window_seconds: float,
    chunk_audio_seconds: float,
    stt_elapsed: float,
    translation_elapsed: float,
    translation_enabled: bool,
    total_elapsed: float,
    audio_rms_db: float,
    audio_peak_db: float,
    chunk_audio_queue_drops: int,
    current_audio_queue_drops: int,
    current_queue_size: int,
    queue_peak: int,
    text_chars: int,
) -> None:
    worker._emit(
        "status",
        "받아쓰기 AI 성능: "
        f"chunk={chunk_index} step={step_seconds:.2f}s window={window_seconds:.2f}s "
        f"audio={chunk_audio_seconds:.2f}s "
        f"stt={stt_elapsed:.2f}s stt_rtf={stt_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
        f"stt_step_load={stt_elapsed / max(step_seconds, 0.001):.2f} "
        f"translation={translation_elapsed:.2f}s translation_enabled={translation_enabled} "
        f"total={total_elapsed:.2f}s total_rtf={total_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
        f"total_step_load={total_elapsed / max(step_seconds, 0.001):.2f} "
        f"effective_latency_estimate={window_seconds + total_elapsed:.2f}s "
        f"audio_rms_db={audio_rms_db:.1f} audio_peak_db={audio_peak_db:.1f} "
        f"input_queue_drops={chunk_audio_queue_drops} input_queue_drops_total={current_audio_queue_drops} "
        f"queue_size={current_queue_size} queue_peak={queue_peak} "
        f"beam={worker._cfg.beamSize} max_tokens={worker._cfg.maxNewTokens} text_chars={text_chars}",
        display=False,
    )

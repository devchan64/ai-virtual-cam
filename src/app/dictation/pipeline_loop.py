from __future__ import annotations
import queue
import time
import traceback
from typing import Any
from src.app.dictation.audio_window import SlidingAudioWindow
from src.app.dictation.pipeline_audio_runtime import prepare_chunk_audio
from src.app.dictation.pipeline_settings import (
    INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS,
    SAMPLE_RATE,
    delta_suppressed_stage_max_chunks,
    no_text_stale_stage_suppress_chunks,
    staged_queue_max_promotion_age_chunks,
)
from src.app.dictation.pipeline_diagnostics import (
    emit_runtime_performance,
    emit_sentence_diagnostics,
    record_pending_diagnostics,
)
from src.app.dictation.pipeline_chunk_interpreter import process_chunk_sentence_flow
from src.app.dictation.pipeline_stage_facade import StageLoopFacade
from src.app.dictation.pipeline_setup import create_transcribe_loop_setup
from src.app.dictation.pipeline_stt_runtime import recognize_chunk
from src.app.dictation.pipeline_runtime_support import (
    format_runtime_stability_groups,
)
from src.app.dictation.pipeline_runtime_observer import observe_chunk_runtime
from src.app.dictation.pipeline_translation import (
    collect_translation_jobs,
    execute_translation_jobs,
)
from src.app.dictation.pipeline_types import SttModelLike, TextTranslatorLike, TranscriptWorkerLike
from src.app.dictation_core.dictation_transcript_logic import (
    _diagnostic_tail,
)
from src.app.dictation_core.transcript_revision import (
    consume_committed_prefix as _consume_committed_prefix,
)


def _validate_final_segments(final_segments: list[object], *, chunk_index: int) -> list[tuple[int, str]]:
    normalized: list[tuple[int, str]] = []
    for index, item in enumerate(final_segments):
        if not isinstance(item, tuple) or len(item) != 2:
            raise RuntimeError(
                "final_segments contract violation: "
                f"chunk={chunk_index} index={index} type={type(item).__name__} value={item!r}"
            )
        segment_id, sentence = item
        normalized.append((int(segment_id), str(sentence)))
    return normalized

def run_transcribe_loop(
    worker: TranscriptWorkerLike,
    model: SttModelLike,
    np: Any,
    text_translator: TextTranslatorLike | None = None,
) -> None:
    setup = create_transcribe_loop_setup(worker)
    step_seconds = setup.step_seconds
    window_seconds = setup.window_seconds
    sentence_finalize_age = setup.sentence_finalize_age
    audio_window = setup.audio_window
    language = setup.language
    chunks = 0
    translation_failed = False
    committed_text = ""
    committed_translation_text = ""
    pending_transcript_text = ""
    pending_chunks = 0
    loop_support = setup.loop_support
    last_audio_queue_drops = setup.last_audio_queue_drops
    recognition_node = setup.recognition_node
    candidate_node = setup.candidate_node
    commit_buffer_node = setup.commit_buffer_node
    active_stage = setup.active_stage
    no_text_stage_skip_chunks = 0
    stage_facade = StageLoopFacade(
        worker=worker,
        loop_support=loop_support,
        active_stage=active_stage,
        commit_buffer_node=commit_buffer_node,
        sentence_finalize_age=sentence_finalize_age,
        staged_queue_max_promotion_age_chunks=staged_queue_max_promotion_age_chunks,
        delta_suppressed_stage_max_chunks=delta_suppressed_stage_max_chunks,
        no_text_stale_stage_suppress_chunks=no_text_stale_stage_suppress_chunks,
    )
    worker._emit(
        "status",
        f"받아쓰기 AI 전사 루프 시작: step_seconds={step_seconds} window_seconds={window_seconds} "
        f"language={worker._cfg.language} "
        f"stt_backend={worker._stt_settings_for_language()[0]} stt_model={worker._stt_settings_for_language()[1]} "
        f"translation_enabled={worker._cfg.translationEnabled} "
        f"translation_backend={worker._cfg.translationBackend} "
        f"translation_target={worker._cfg.translationTargetLanguage} beam_size={worker._cfg.beamSize} "
        f"max_new_tokens={worker._cfg.maxNewTokens} temperature={worker._cfg.temperature} "
        f"sentence_finalize_age={sentence_finalize_age} "
        f"without_timestamps=True translation_beam_size={worker._cfg.translationBeamSize} "
        f"translation_max_new_tokens={worker._cfg.translationMaxNewTokens}",
    )
    # Main chunk loop: recognize -> interpret candidates -> coordinate stage lifecycle -> emit final-only sinks.
    while not worker._stop.is_set():
        try:
            block = worker._audio_queue.get(timeout=INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS)
        except queue.Empty:
            continue
        if not audio_window.append(block):
            continue
        chunks += 1
        loop_support.clear_chunk_metrics()
        worker._emit(
            "status",
            f"받아쓰기 AI 전사 요청: chunk={chunks} samples={audio_window.buffered_samples}",
            display=False,
        )
        chunk_audio = prepare_chunk_audio(audio_window, np)
        audio = chunk_audio.audio
        chunk_audio_seconds = chunk_audio.chunk_audio_seconds
        audio_rms_db = chunk_audio.audio_rms_db
        audio_peak_db = chunk_audio.audio_peak_db
        chunk_started_at = chunk_audio.chunk_started_at
        translation_elapsed = 0.0
        translation_attempted = False
        translation_started_at = chunk_started_at
        text = ""
        try:
            recognition = recognize_chunk(
                recognition_node=recognition_node,
                chunk_index=chunks,
                input_device=str(worker._cfg.inputDevice),
                sample_rate=SAMPLE_RATE,
                window_seconds=window_seconds,
                step_seconds=step_seconds,
                audio=audio,
                queue_drops=worker._audio_queue_drop_count() - last_audio_queue_drops,
                model=model,
                stream_block=block,
                committed_text=committed_text,
                pending_text=pending_transcript_text,
            )
            hypothesis = recognition.hypothesis
            raw_window_text = hypothesis.rawText
            if raw_window_text:
                worker._emit(
                    "stt_raw",
                    raw_window_text,
                    log_text=f"[{language} raw] {raw_window_text}",
                    final=True,
                )
            window_text = hypothesis.windowText
            stable_text = hypothesis.stableText
            stable_analysis = hypothesis.stability
            if stable_analysis is None:
                raise RuntimeError("RecognitionHypothesis.stability must be populated")
            stage_facade.sync_chunk(
                chunk_index=chunks,
                committed_text=committed_text,
                stable_analysis=stable_analysis,
            )
            if stable_analysis.current_units:
                stage_facade.count_metric("stable_window_observed")
                stage_facade.count_metric("stable_prefix_chars", stable_analysis.stable_prefix_chars)
                stage_facade.count_metric("unstable_tail_chars", stable_analysis.unstable_tail_chars)
                stage_facade.count_metric("stable_internal_chars", stable_analysis.stable_internal_chars)
                stage_facade.count_metric(
                    "stable_internal_ratio_per_1000",
                    int(round(stable_analysis.stable_internal_ratio * 1000)),
                )
                stage_facade.count_metric(
                    "stable_token_ratio_per_1000",
                    int(round(stable_analysis.stable_token_ratio * 1000)),
                )
                stage_facade.count_metric(f"stable_overlap_source_{stable_analysis.stable_overlap_source}")
            adjusted_boundary_confidence = hypothesis.boundaryConfidence
            text = hypothesis.deltaText
            stt_elapsed = hypothesis.elapsedSeconds
            detected = hypothesis.language
            if hypothesis.rejectedReasons:
                worker._emit(
                    "status",
                    f"받아쓰기 AI 전사 후보 무시: chunk={chunks} reasons={'; '.join(hypothesis.rejectedReasons)}",
                    display=False,
                )
            boundary_confidence_display = (
                f"{adjusted_boundary_confidence:.2f}" if adjusted_boundary_confidence is not None else "n/a"
            )
            if text and stage_facade.is_repeated_hallucination(text):
                stage_facade.count_segment_state("suppressed")
                worker._emit("status", f"받아쓰기 AI 반복 전사 무시: chunk={chunks} text={text!r}", display=False)
                text = ""
            sentence_flow = process_chunk_sentence_flow(
                candidate_node=candidate_node,
                hypothesis=hypothesis,
                detected=detected,
                text=text,
                chunk_index=chunks,
                committed_text=committed_text,
                pending_transcript_text=pending_transcript_text,
                pending_chunks=pending_chunks,
                no_text_stage_skip_chunks=no_text_stage_skip_chunks,
                active_stage_sentence=active_stage.sentence,
                window_text=window_text,
                stable_text=stable_text,
                count_metric=stage_facade.count_metric,
                count_segment_state=stage_facade.count_segment_state,
                stage_completed_sentence=lambda sentence, detected, pending_transcript_text, later_completed_sentences, prior_pending_text: (
                    stage_facade.stage_completed_sentence(
                        sentence,
                        detected,
                        pending_transcript_text=pending_transcript_text,
                        later_completed_sentences=later_completed_sentences,
                        prior_pending_text=prior_pending_text,
                    )
                ),
                finalize_right_context_staged_sentences=stage_facade.finalize_right_context_staged_sentences,
                age_staged_sentence=stage_facade.age_staged_sentence,
                suppress_stale_no_text_stage=stage_facade.suppress_stale_no_text_stage,
                consume_committed_prefix=_consume_committed_prefix,
                emit_status=lambda status: worker._emit("status", status, display=False),
            )
            pending_transcript_text = sentence_flow.pending_transcript_text
            pending_chunks = sentence_flow.pending_chunks
            no_text_stage_skip_chunks = sentence_flow.no_text_stage_skip_chunks
            committed_text = stage_facade.committed_text
            completed_sentences = sentence_flow.completed_sentences
            final_segments = _validate_final_segments(sentence_flow.final_segments, chunk_index=chunks)
            boundary_complete = sentence_flow.boundary_complete
            boundary_soft = sentence_flow.boundary_soft
            boundary_end_marks = sentence_flow.boundary_end_marks
            boundary_right_context_starts = sentence_flow.boundary_right_context_starts
            pending_overrun_reason, pending_quality_flags = record_pending_diagnostics(
                count_metric=stage_facade.count_metric,
                detected=detected,
                pending_transcript_text=pending_transcript_text,
                pending_chunks=pending_chunks,
            )
            emit_sentence_diagnostics(
                worker=worker,
                chunk_index=chunks,
                completed_count=len(completed_sentences),
                final_count=len(final_segments),
                pending_overrun_reason=pending_overrun_reason,
                pending_quality_flags=pending_quality_flags,
                detected=detected,
                pending_transcript_text=pending_transcript_text,
                pending_chunks=pending_chunks,
                window_text=window_text,
                stable_text=stable_text,
                delta_text=text,
                stable_analysis=stable_analysis,
                committed_text=committed_text,
                active_stage_sentence=active_stage.sentence,
                boundary_complete=boundary_complete,
                boundary_soft=boundary_soft,
                boundary_confidence_display=boundary_confidence_display,
                boundary_end_marks=boundary_end_marks,
                boundary_right_context_starts=boundary_right_context_starts,
                boundary_conf_segment=hypothesis.segmentBoundaryConfidence,
                boundary_conf_stable=hypothesis.stableBoundaryConfidence,
                chunk_metrics=loop_support.chunk_lifecycle_metrics,
                lifecycle_metrics=loop_support.lifecycle_metrics,
                staged_confirmations=active_stage.confirmations,
                staged_age=active_stage.age,
                staged_forced=active_stage.forced,
            )
            translation_jobs = collect_translation_jobs(
                final_segments=final_segments,
                detected=detected,
                chunk_index=chunks,
                count_metric=stage_facade.count_metric,
                worker=worker,
            )
            if worker._cfg.translationEnabled and not translation_failed and translation_jobs:
                try:
                    committed_translation_text, translation_elapsed, translation_attempted = execute_translation_jobs(
                        worker=worker,
                        model=model,
                        text_translator=text_translator,
                        audio=audio,
                        language=language,
                        detected=detected,
                        window_seconds=window_seconds,
                        chunk_index=chunks,
                        translation_jobs=translation_jobs,
                        committed_translation_text=committed_translation_text,
                    )
                except Exception as exc:
                    translation_elapsed = time.perf_counter() - translation_started_at if translation_attempted else 0.0
                    translation_failed = True
                    worker._emit(
                        "error",
                        "받아쓰기 AI 번역 실패: "
                        f"{exc}. 번역을 이번 세션에서 중지합니다. STT 전사는 계속됩니다.",
                    )
            total_elapsed = time.perf_counter() - chunk_started_at
            runtime_observation = observe_chunk_runtime(
                loop_support=loop_support,
                current_audio_queue_drops=worker._audio_queue_drop_count(),
                last_audio_queue_drops=last_audio_queue_drops,
                current_queue_size=worker._audio_queue.qsize(),
                backlog_threshold=max(5, int(round(window_seconds / max(step_seconds, 0.001)))),
                queue_len=len(commit_buffer_node),
                raw_window_has_text=bool(raw_window_text),
                final_segments_count=len(final_segments),
            )
            last_audio_queue_drops = runtime_observation.current_audio_queue_drops
            runtime_stability_metrics = runtime_observation.runtime_stability_metrics
            worker._emit(
                "status",
                "받아쓰기 AI 안정성 지표: "
                f"chunk={chunks} {format_runtime_stability_groups(runtime_stability_metrics)}",
                display=False,
            )
            emit_runtime_performance(
                worker=worker,
                chunk_index=chunks,
                step_seconds=step_seconds,
                window_seconds=window_seconds,
                chunk_audio_seconds=chunk_audio_seconds,
                stt_elapsed=stt_elapsed,
                translation_elapsed=translation_elapsed,
                translation_enabled=worker._cfg.translationEnabled and not translation_failed,
                total_elapsed=total_elapsed,
                audio_rms_db=audio_rms_db,
                audio_peak_db=audio_peak_db,
                chunk_audio_queue_drops=runtime_observation.chunk_audio_queue_drops,
                current_audio_queue_drops=runtime_observation.current_audio_queue_drops,
                current_queue_size=runtime_observation.current_queue_size,
                queue_peak=int(runtime_stability_metrics.get("input_queue_size_peak", 0)),
                text_chars=len(text),
            )
        except Exception as exc:
            worker._emit(
                "status",
                "받아쓰기 AI 전사 traceback:\n" + traceback.format_exc(),
                display=False,
            )
            worker._emit("error", f"받아쓰기 AI 전사 실패: {exc}")
            worker._stop.set()
            raise

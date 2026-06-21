from __future__ import annotations
import queue
import time
from collections import deque
from typing import Any
from src.app.dictation_audio_window import SlidingAudioWindow
from src.app.dictation_node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation_node_speech_evidence_to_stt_hypothesis import SpeechEvidenceToSttHypothesisNode
from src.app.dictation_node_stt_hypothesis_to_sentence_candidate import SttHypothesisToSentenceCandidateNode
from src.app.dictation_pipeline_contracts import AudioEvidence, UncommittedContext
from src.app.dictation_pipeline_settings import (
    INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS,
    MAX_RECENT_SHORT_TEXT_REPEATS,
    RECENT_TRANSCRIPT_WINDOW,
    SAMPLE_RATE,
    delta_suppressed_stage_max_chunks,
    max_staged_sentence_queue,
    no_text_stale_stage_suppress_chunks,
)
from src.app.dictation_transcript_logic import (
    _diagnostic_tail,
    _final_sentence_diagnostic_flags,
    _format_transcript_metrics,
    _has_later_completed_extension,
    _is_cjk_text,
    _is_pending_prefix_mixed_candidate,
    _is_prior_pending_recent_final_mixed_candidate,
    _new_text_delta,
    _next_revision_confirmation_count,
    _normalized_text,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _prefer_sentence_revision,
    _recent_final_output_delta,
    _replacement_decision_reason,
    _revision_internal_stability_bucket,
    _sentence_end_count,
    _sentence_max_age_chunks,
    _sentence_output_delta,
    _sentences_are_revisions,
    _staged_sentence_required_confirmations,
    _should_age_staged_sentence,
    _should_confirm_staged_sentence,
    _should_defer_unconfirmed_replacement,
    _should_finalize_before_replacement,
    _should_finalize_replaced_sentence,
    _should_preserve_revision_confirmation_from_internal_stability,
    _should_reset_revision_age,
    _should_split_terminal_tail_revision,
    _should_stage_boundary_candidate,
    _should_suppress_delta_final,
    _should_translate_final_sentence,
    _stable_window_text,
    _strip_prior_pending_prefix_revision,
)
from src.app.transcript_revision import (
    append_context as _append_committed_text,
    consume_committed_prefix as _consume_committed_prefix,
    revision_lifecycle_context as _revision_lifecycle_context,
)
from src.app.translation_model import TranslationRequest
def run_transcribe_loop(
    worker: Any,
    model: Any,
    np: Any,
    text_translator: Any = None,
) -> None:
    step_seconds = float(worker._cfg.stepSeconds)
    window_seconds = float(worker._cfg.windowSeconds)
    sentence_finalize_age = int(getattr(worker._cfg, "sentenceFinalizeAge", 3))
    step_samples = int(SAMPLE_RATE * step_seconds)
    window_samples = int(SAMPLE_RATE * window_seconds)
    audio_window = SlidingAudioWindow(window_samples=window_samples, step_samples=step_samples)
    language = worker._cfg.language
    chunks = 0
    next_final_segment_id = 1
    translation_failed = False
    committed_text = ""
    committed_translation_text = ""
    pending_transcript_text = ""
    pending_chunks = 0
    recent_transcripts: deque[str] = deque(maxlen=RECENT_TRANSCRIPT_WINDOW)
    lifecycle_metrics: dict[str, int] = {}
    chunk_lifecycle_metrics: dict[str, int] = {}
    last_audio_queue_drops = worker._audio_queue_drop_count()
    recognition_node = SpeechEvidenceToSttHypothesisNode(worker._cfg)
    candidate_node = SttHypothesisToSentenceCandidateNode(worker._sentence_boundary_detector_for)
    commit_buffer_node = SentenceCandidateCommitBufferNode(max_staged_sentence_queue())
    active_stage = commit_buffer_node.active
    no_text_stage_skip_chunks = 0
    def count_metric(name: str, amount: int = 1) -> None:
        lifecycle_metrics[name] = lifecycle_metrics.get(name, 0) + amount
        chunk_lifecycle_metrics[name] = chunk_lifecycle_metrics.get(name, 0) + amount
    def count_segment_state(state: str, amount: int = 1) -> None:
        count_metric(f"segment_state_{state}", amount)
    def is_repeated_hallucination(text: str) -> bool:
        normalized = " ".join(text.split())
        if not normalized:
            return False
        repeats = sum(1 for item in recent_transcripts if item == normalized)
        return len(normalized) <= 24 and repeats >= MAX_RECENT_SHORT_TEXT_REPEATS
    def remember_transcript(text: str) -> None:
        normalized = " ".join(text.split())
        if normalized:
            recent_transcripts.append(normalized)
    def promote_next_staged_sentence(detected: str) -> None:
        while True:
            promoted = commit_buffer_node.promote_if_idle(
                chunk_index=chunks,
                count_metric=count_metric,
                count_segment_state=count_segment_state,
            )
            if not promoted:
                return
            promoted_sentence, recent_source = _recent_final_output_delta(
                active_stage.sentence,
                tuple(recent_transcripts),
                detected,
            )
            if recent_source is None:
                break
            if promoted_sentence and _should_stage_boundary_candidate(promoted_sentence, detected):
                active_stage.sentence = promoted_sentence
                active_stage.deltaSuppressedChunks = 0
                active_stage.deltaSuppressedChunkIndex = -1
                count_metric("stage_queue_recent_final_delta_trimmed", 1)
                break
            count_metric("stage_queue_recent_final_suppressed", 1)
            count_segment_state("suppressed", 1)
            worker._emit(
                "status",
                "받아쓰기 AI stage 큐 최근 final 중복 폐기: "
                f"chunk={chunks} recent_tail={_diagnostic_tail(recent_source)} "
                f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
                display=False,
            )
            active_stage.clear()
        worker._emit(
            "status",
            "받아쓰기 AI stage 큐 승격: "
            f"chunk={chunks} queue_remaining={len(commit_buffer_node)} "
            f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} "
            f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
            display=False,
        )
        worker._emit("transcript", active_stage.sentence, log_text=f"[{detected}] {active_stage.sentence}", final=False)
    def queue_staged_sentence(candidate: str, forced: bool) -> None:
        commit_buffer_node.enqueue_or_revision(
            candidate=candidate,
            forced=forced,
            chunk_index=chunks,
            stable_analysis=stable_analysis,
            count_metric=count_metric,
            count_segment_state=count_segment_state,
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
    def finalize_staged_sentence(detected: str, reason: str) -> list[tuple[int, str]]:
        nonlocal committed_text, next_final_segment_id
        if not active_stage.sentence:
            return []
        count_metric("finalize_attempt")
        count_metric(f"finalize_reason_{reason}")
        output_sentence = _sentence_output_delta(committed_text, active_stage.sentence)
        staged_before = active_stage.sentence
        committed_before_chars = len(_normalized_text(committed_text))
        if not output_sentence:
            active_stage.clear()
            count_metric("finalize_duplicate_suppressed")
            count_segment_state("suppressed")
            worker._emit(
                "status",
                f"받아쓰기 AI 확정 후보 중복 무시: chunk={chunks} reason={reason} text={staged_before!r}",
                display=False,
            )
            promote_next_staged_sentence(detected)
            return []
        recent_adjusted_sentence, echo_source = _recent_final_output_delta(
            output_sentence,
            tuple(recent_transcripts),
            detected,
        )
        if echo_source is not None:
            if recent_adjusted_sentence:
                count_metric("finalize_recent_delta_trimmed")
                worker._emit(
                    "status",
                    "받아쓰기 AI 확정 후보 최근 final 중복 제거: "
                    f"chunk={chunks} reason={reason} recent={echo_source!r} "
                    f"before={output_sentence!r} after={recent_adjusted_sentence!r}",
                    display=False,
                )
                output_sentence = recent_adjusted_sentence
            else:
                active_stage.clear()
                count_metric("finalize_recent_echo_suppressed")
                count_segment_state("suppressed")
                worker._emit(
                    "status",
                    "받아쓰기 AI 확정 후보 유사 대안 무시: "
                    f"chunk={chunks} reason={reason} text={output_sentence!r} recent={echo_source!r}",
                    display=False,
                )
                promote_next_staged_sentence(detected)
                return []
        if not output_sentence:
            active_stage.clear()
            count_metric("finalize_recent_echo_suppressed")
            count_segment_state("suppressed")
            worker._emit(
                "status",
                "받아쓰기 AI 확정 후보 유사 대안 무시: "
                f"chunk={chunks} reason={reason} text={staged_before!r}",
                display=False,
            )
            promote_next_staged_sentence(detected)
            return []
        if _should_suppress_delta_final(staged_before, output_sentence, detected, reason):
            count_metric("finalize_delta_suppressed")
            if active_stage.deltaSuppressedChunkIndex != chunks:
                active_stage.deltaSuppressedChunks += 1
            active_stage.deltaSuppressedChunkIndex = chunks
            if active_stage.deltaSuppressedChunks >= delta_suppressed_stage_max_chunks():
                suppress_chunks = active_stage.deltaSuppressedChunks
                active_stage.clear()
                count_metric("finalize_delta_suppressed_stage_dropped")
                count_segment_state("suppressed")
                worker._emit(
                    "status",
                    "받아쓰기 AI delta 보류 stage 폐기: "
                    f"chunk={chunks} reason={reason} suppress_chunks={suppress_chunks} "
                    f"staged_tail={_diagnostic_tail(staged_before)} output={output_sentence!r}",
                    display=False,
                )
                promote_next_staged_sentence(detected)
                return []
            count_metric("finalize_delta_suppressed_stage_retained")
            worker._emit(
                "status",
                "받아쓰기 AI delta 확정 보류: "
                f"suppress_chunks={active_stage.deltaSuppressedChunks} "
                f"chunk={chunks} reason={reason} staged_tail={_diagnostic_tail(staged_before)} "
                f"output={output_sentence!r}",
                display=False,
            )
            return []
        active_stage.clear()
        count_metric("finalized")
        count_segment_state("final")
        segment_id = next_final_segment_id
        next_final_segment_id += 1
        final_quality_flags = _final_sentence_diagnostic_flags(output_sentence, detected)
        for flag in final_quality_flags:
            count_metric(f"final_quality_{flag}")
        committed_text = _append_committed_text(committed_text, output_sentence)
        remember_transcript(output_sentence)
        worker._emit(
            "status",
            "받아쓰기 AI 문장 확정: "
            f"chunk={chunks} segment_id={segment_id} reason={reason} committed_before_chars={committed_before_chars} "
            f"output_chars={len(_normalized_text(output_sentence))} "
            f"quality_flags={','.join(final_quality_flags) or 'none'} "
            f"staged_tail={_diagnostic_tail(staged_before)} text={output_sentence!r}",
            display=False,
        )
        worker._emit(
            "transcript",
            output_sentence,
            log_text=f"[{detected}#{segment_id}] {output_sentence}",
            final=True,
            segment_id=segment_id,
        )
        promote_next_staged_sentence(detected)
        return [(segment_id, output_sentence)]
    def stage_completed_sentence(
        sentence: str,
        detected: str,
        *,
        forced: bool = False,
        later_completed_sentences: list[str] | tuple[str, ...] = (),
        prior_pending_text: str = "",
    ) -> list[str]:
        normalized_sentence = _normalized_text(sentence)
        candidate = _sentence_output_delta(committed_text, sentence)
        if active_stage.sentence and prior_pending_text and candidate:
            stripped_candidate = _strip_prior_pending_prefix_revision(
                active_stage.sentence,
                candidate,
                prior_pending_text,
            )
            if stripped_candidate != candidate:
                count_metric("candidate_prior_pending_prefix_trimmed")
                worker._emit(
                    "status",
                    "받아쓰기 AI prior pending prefix 후보 정리: "
                    f"chunk={chunks} prior_pending={_diagnostic_tail(prior_pending_text)} "
                    f"before={_diagnostic_tail(candidate)} after={_diagnostic_tail(stripped_candidate)}",
                    display=False,
                )
                candidate = stripped_candidate
        if candidate and candidate != normalized_sentence:
            count_metric("candidate_delta_trimmed")
            if _is_cjk_text(normalized_sentence):
                count_metric("candidate_delta_trimmed_cjk")
        recent_candidate, recent_source = _recent_final_output_delta(
            normalized_sentence,
            tuple(recent_transcripts),
            detected,
        )
        if recent_source is not None and recent_candidate != candidate:
            candidate = recent_candidate
            count_metric("candidate_recent_final_delta_trimmed")
        if not candidate:
            count_metric("candidate_duplicate_suppressed")
            count_segment_state("suppressed")
            worker._emit("status", f"받아쓰기 AI 중복 문장 무시: chunk={chunks} text={sentence!r}", display=False)
            return []
        if _is_pending_prefix_mixed_candidate(candidate, pending_transcript_text):
            count_metric("candidate_pending_prefix_mixed_suppressed")
            count_segment_state("suppressed")
            worker._emit(
                "status",
                "받아쓰기 AI pending prefix 혼합 후보 무시: "
                f"chunk={chunks} candidate_tail={_diagnostic_tail(candidate)} "
                f"pending_tail={_diagnostic_tail(pending_transcript_text)}",
                display=False,
            )
            return []
        if _is_prior_pending_recent_final_mixed_candidate(
            candidate,
                prior_pending_text,
                tuple(recent_transcripts),
                detected,
            ):
            count_metric("candidate_prior_pending_recent_final_mixed_suppressed")
            count_segment_state("suppressed")
            worker._emit(
                "status",
                "받아쓰기 AI prior pending/recent final 혼합 후보 무시: "
                f"chunk={chunks} candidate_tail={_diagnostic_tail(candidate)} "
                f"prior_pending_tail={_diagnostic_tail(prior_pending_text)}",
                display=False,
            )
            return []
        if not _should_stage_boundary_candidate(candidate, detected):
            count_metric("stage_candidate_quality_blocked")
            count_segment_state("suppressed")
            candidate_quality_flags = _final_sentence_diagnostic_flags(candidate, detected)
            for flag in candidate_quality_flags:
                count_metric(f"stage_candidate_quality_{flag}")
            worker._emit(
                "status",
                "받아쓰기 AI stage 후보 품질 차단: "
                f"chunk={chunks} flags={','.join(candidate_quality_flags) or 'none'} "
                f"candidate_tail={_diagnostic_tail(candidate)}",
                display=False,
            )
            return []
        if not active_stage.sentence:
            promote_next_staged_sentence(detected)
        if not active_stage.sentence:
            count_metric("stage_start")
            count_segment_state("staged")
            active_stage.start(candidate, forced=forced, chunk_index=chunks)
            worker._emit(
                "status",
                "받아쓰기 AI stage 시작: "
                f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                display=False,
            )
            worker._emit("transcript", active_stage.sentence, log_text=f"[{detected}] {active_stage.sentence}", final=False)
            return []
        if _should_confirm_staged_sentence(
            active_stage.sentence,
            active_stage.confirmations,
            active_stage.forced,
        ) and _should_split_terminal_tail_revision(active_stage.sentence, candidate):
            count_metric("stage_revision_terminal_tail_split")
            finalized = finalize_staged_sentence(detected, "terminal_tail_revision_split")
            if not active_stage.sentence:
                promote_next_staged_sentence(detected)
            if active_stage.sentence:
                queue_staged_sentence(candidate, forced)
                return finalized
            count_metric("stage_start")
            count_segment_state("staged")
            active_stage.start(candidate, forced=forced, chunk_index=chunks)
            worker._emit(
                "status",
                "받아쓰기 AI stage 시작: "
                f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                display=False,
            )
            worker._emit("transcript", active_stage.sentence, log_text=f"[{detected}] {active_stage.sentence}", final=False)
            return finalized
        is_revision = _sentences_are_revisions(active_stage.sentence, candidate)
        if is_revision:
            count_metric("stage_revision")
            count_segment_state("revised")
            staged_before = active_stage.sentence
            preferred = _prefer_sentence_revision(active_stage.sentence, candidate)
            preferred_changed = preferred != staged_before
            if preferred_changed:
                count_metric("stage_revision_changed")
                if _is_cjk_text(staged_before) or _is_cjk_text(preferred):
                    count_metric(
                        "stage_revision_internal_stability_"
                        + _revision_internal_stability_bucket(
                            stable_analysis.stable_internal_ratio,
                            stable_analysis.stable_internal_chars,
                        )
                    )
                    if _should_preserve_revision_confirmation_from_internal_stability(
                        staged_before,
                        preferred,
                        stable_analysis.stable_internal_ratio,
                        stable_analysis.stable_internal_chars,
                        stable_analysis.stable_overlap_source,
                    ):
                        count_metric("stage_revision_confirmation_preserved_internal")
                    else:
                        count_metric("stage_revision_confirmation_reset")
            else:
                candidate_flags = set(_final_sentence_diagnostic_flags(candidate, detected))
                staged_flags = set(_final_sentence_diagnostic_flags(staged_before, detected))
                if (
                    "cjk_repeated_ngram" in candidate_flags
                    and "cjk_repeated_ngram" not in staged_flags
                ) or (
                    "repeated_word_ngram" in candidate_flags
                    and "repeated_word_ngram" not in staged_flags
                ):
                    count_metric("stage_revision_candidate_quality_blocked")
            preferred_changed = preferred != staged_before
            active_stage.sentence = preferred
            if preferred_changed:
                active_stage.deltaSuppressedChunks = 0
                active_stage.deltaSuppressedChunkIndex = -1
            active_stage.confirmations = _next_revision_confirmation_count(
                staged_before,
                preferred,
                active_stage.confirmations,
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            )
            if _should_reset_revision_age(
                staged_before,
                preferred,
                stable_analysis.stable_internal_ratio,
                stable_analysis.stable_internal_chars,
                stable_analysis.stable_overlap_source,
            ):
                active_stage.age = 0
                count_metric("stage_revision_age_reset")
            else:
                active_stage.age += 1
            active_stage.deferredAgeChunk = chunks
            count_metric("stage_age_tick")
            active_stage.forced = active_stage.forced or forced
            required_confirmations = _staged_sentence_required_confirmations(active_stage.sentence, active_stage.forced)
            worker._emit(
                "status",
                "받아쓰기 AI stage 리비전: "
                f"chunk={chunks} confirmations={active_stage.confirmations}/{required_confirmations} "
                f"staged_age={active_stage.age} "
                f"forced={active_stage.forced} preferred_changed={preferred_changed} "
                f"staged_before={_diagnostic_tail(staged_before)} candidate={_diagnostic_tail(candidate)} "
                f"preferred={_diagnostic_tail(preferred)}",
                display=False,
            )
            defer_for_later_extension = _has_later_completed_extension(active_stage.sentence, later_completed_sentences)
            if defer_for_later_extension:
                count_metric("stage_confirm_deferred_later_extension")
                worker._emit(
                    "status",
                    "받아쓰기 AI stage 확정 보류: "
                    f"chunk={chunks} reason=later_completed_extension staged_tail={_diagnostic_tail(active_stage.sentence)}",
                    display=False,
                )
            if not defer_for_later_extension and _should_confirm_staged_sentence(
                active_stage.sentence,
                active_stage.confirmations,
                active_stage.forced,
            ):
                return finalize_staged_sentence(detected, "confirmed_forced" if active_stage.forced else "confirmed")
            if not defer_for_later_extension and _should_finalize_before_replacement(
                active_stage.sentence,
                detected,
                active_stage.confirmations,
                active_stage.age,
                sentence_finalize_age,
                active_stage.forced,
            ):
                max_age = _sentence_max_age_chunks(active_stage.forced, sentence_finalize_age)
                if active_stage.age >= max_age:
                    count_metric("stage_age_finalize")
                    reason = "aged_forced" if active_stage.forced else "aged"
                else:
                    count_metric("stage_finalize_before_replace")
                    reason = "next_completed"
                return finalize_staged_sentence(detected, reason)
            if not defer_for_later_extension and active_stage.age >= _sentence_max_age_chunks(active_stage.forced, sentence_finalize_age):
                count_metric("stage_age_quality_blocked")
                count_segment_state("suppressed")
                flags = _final_sentence_diagnostic_flags(active_stage.sentence, detected)
                worker._emit(
                    "status",
                    "받아쓰기 AI stage 리비전 품질 차단: "
                    f"chunk={chunks} flags={','.join(flags) or 'none'} "
                    f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
                    display=False,
                )
                active_stage.clear()
                promote_next_staged_sentence(detected)
                return []
            worker._emit("transcript", active_stage.sentence, log_text=f"[{detected}] {active_stage.sentence}", final=False)
            return []
        count_metric("stage_replace")
        replacement_reason = _replacement_decision_reason(
            active_stage.sentence,
            candidate,
            active_stage.confirmations,
            active_stage.forced,
            active_stage.age,
            sentence_finalize_age,
        )
        count_metric(f"stage_replace_decision_{replacement_reason}")
        if _should_defer_unconfirmed_replacement(replacement_reason):
            queue_staged_sentence(candidate, forced)
            count_metric("stage_replace_deferred")
            if active_stage.deferredAgeChunk != chunks:
                active_stage.age += 1
                active_stage.deferredAgeChunk = chunks
                count_metric("stage_age_tick")
            worker._emit(
                "status",
                "받아쓰기 AI stage 교체 보류: "
                f"chunk={chunks} decision={replacement_reason} staged_confirmations={active_stage.confirmations} "
                f"staged_age={active_stage.age} staged_tail={_diagnostic_tail(active_stage.sentence)} "
                f"candidate_tail={_diagnostic_tail(candidate)}",
                display=False,
            )
            if (
                active_stage.age >= _sentence_max_age_chunks(active_stage.forced, sentence_finalize_age)
                and _should_finalize_before_replacement(
                    active_stage.sentence,
                    detected,
                    active_stage.confirmations,
                    active_stage.age,
                    sentence_finalize_age,
                    active_stage.forced,
                )
            ):
                count_metric("stage_age_finalize")
                worker._emit(
                    "status",
                    "받아쓰기 AI stage 보류 후보 순서 확정: "
                    f"chunk={chunks} decision={replacement_reason} staged_confirmations={active_stage.confirmations} "
                    f"staged_age={active_stage.age} staged_tail={_diagnostic_tail(active_stage.sentence)} "
                    f"candidate_tail={_diagnostic_tail(candidate)}",
                    display=False,
                )
                finalized = finalize_staged_sentence(detected, "aged_forced" if active_stage.forced else "aged")
                promote_next_staged_sentence(detected)
                return finalized
            if active_stage.age >= _sentence_max_age_chunks(active_stage.forced, sentence_finalize_age):
                count_metric("stage_age_quality_blocked")
                count_segment_state("suppressed")
                worker._emit(
                    "status",
                    "받아쓰기 AI stage 보류 후보 품질 차단: "
                    f"chunk={chunks} decision={replacement_reason} staged_confirmations={active_stage.confirmations} "
                    f"staged_age={active_stage.age} staged_tail={_diagnostic_tail(active_stage.sentence)}",
                    display=False,
                )
                active_stage.clear()
                promote_next_staged_sentence(detected)
            return []
        if active_stage.deferredAgeChunk == chunks:
            queue_staged_sentence(candidate, forced)
            count_metric("stage_replace_deferred_same_chunk")
            worker._emit(
                "status",
                "받아쓰기 AI stage 교체 보류: "
                f"chunk={chunks} decision={replacement_reason} same_chunk=True "
                f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} "
                f"staged_tail={_diagnostic_tail(active_stage.sentence)} "
                f"candidate_tail={_diagnostic_tail(candidate)}",
                display=False,
            )
            return []
        worker._emit(
            "status",
            "받아쓰기 AI stage 교체: "
            f"chunk={chunks} reason=revision_false decision={replacement_reason} forced={forced} "
            f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} "
            f"staged_tail={_diagnostic_tail(active_stage.sentence)} candidate_tail={_diagnostic_tail(candidate)}",
            display=False,
        )
        if _should_finalize_replaced_sentence(
            active_stage.sentence,
            candidate,
            detected,
            active_stage.confirmations,
            active_stage.forced,
            active_stage.age,
            sentence_finalize_age,
        ):
            finalized = finalize_staged_sentence(detected, f"replaced_{replacement_reason}")
        elif _should_finalize_before_replacement(
            active_stage.sentence,
            detected,
            active_stage.confirmations,
            active_stage.age,
            sentence_finalize_age,
            active_stage.forced,
        ):
            count_metric("stage_finalize_before_replace")
            finalized = finalize_staged_sentence(detected, "next_completed")
        else:
            count_metric("stage_replaced_unconfirmed")
            count_segment_state("suppressed")
            required_confirmations = _staged_sentence_required_confirmations(active_stage.sentence, active_stage.forced)
            worker._emit(
                "status",
                "받아쓰기 AI stage 미확정 교체: "
                f"chunk={chunks} decision={replacement_reason} "
                f"staged_confirmations={active_stage.confirmations} required={required_confirmations} "
                f"staged_forced={active_stage.forced} staged_tail={_diagnostic_tail(active_stage.sentence)} "
                f"candidate_tail={_diagnostic_tail(candidate)}",
                display=False,
            )
            finalized = []
            active_stage.clear()
        if not active_stage.sentence:
            promote_next_staged_sentence(detected)
        if active_stage.sentence:
            queue_staged_sentence(candidate, forced)
            return finalized
        count_metric("stage_start")
        count_segment_state("staged")
        active_stage.start(candidate, forced=forced, chunk_index=chunks)
        worker._emit(
            "status",
            "받아쓰기 AI stage 시작: "
                f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                display=False,
            )
        worker._emit("transcript", active_stage.sentence, log_text=f"[{detected}] {active_stage.sentence}", final=False)
        return finalized
    def age_staged_sentence(detected: str, pending_text: str = "") -> list[str]:
        if not active_stage.sentence:
            return []
        if active_stage.deferredAgeChunk == chunks:
            count_metric("stage_age_same_chunk_skipped")
            return []
        if not _should_age_staged_sentence(active_stage.sentence, pending_text):
            count_metric("stage_age_hold")
            worker._emit(
                "status",
                "받아쓰기 AI staged aging 보류: "
                f"chunk={chunks} staged={active_stage.sentence!r} pending={pending_text!r}",
                display=False,
            )
            return []
        active_stage.age += 1
        active_stage.deferredAgeChunk = chunks
        count_metric("stage_age_tick")
        max_age = _sentence_max_age_chunks(active_stage.forced, sentence_finalize_age)
        if active_stage.age >= max_age:
            if not _should_finalize_before_replacement(
                active_stage.sentence,
                detected,
                active_stage.confirmations,
                active_stage.age,
                sentence_finalize_age,
                active_stage.forced,
            ):
                count_metric("stage_age_quality_blocked")
                count_segment_state("suppressed")
                flags = _final_sentence_diagnostic_flags(active_stage.sentence, detected)
                worker._emit(
                    "status",
                    "받아쓰기 AI staged age 확정 차단: "
                    f"chunk={chunks} flags={','.join(flags) or 'none'} "
                    f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
                    display=False,
                )
                active_stage.clear()
                promote_next_staged_sentence(detected)
                return []
            count_metric("stage_age_finalize")
            return finalize_staged_sentence(detected, "aged_forced" if active_stage.forced else "aged")
        return []
    def suppress_stale_no_text_stage(detected: str) -> None:
        nonlocal no_text_stage_skip_chunks
        if not active_stage.sentence:
            no_text_stage_skip_chunks = 0
            return
        required_confirmations = _staged_sentence_required_confirmations(active_stage.sentence, active_stage.forced)
        if active_stage.confirmations >= required_confirmations:
            return
        if no_text_stage_skip_chunks < no_text_stale_stage_suppress_chunks():
            return
        count_metric("stage_no_text_stale_suppressed")
        count_segment_state("suppressed")
        worker._emit(
            "status",
            "받아쓰기 AI 무텍스트 stale stage 폐기: "
            f"chunk={chunks} no_text_chunks={no_text_stage_skip_chunks} "
            f"staged_confirmations={active_stage.confirmations}/{required_confirmations} "
            f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
            display=False,
        )
        active_stage.clear()
        no_text_stage_skip_chunks = 0
        promote_next_staged_sentence(detected)
    while not worker._stop.is_set():
        try:
            block = worker._audio_queue.get(timeout=INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS)
        except queue.Empty:
            continue
        if not audio_window.append(block):
            continue
        chunks += 1
        chunk_lifecycle_metrics.clear()
        worker._emit(
            "status",
            f"받아쓰기 AI 전사 요청: chunk={chunks} samples={audio_window.buffered_samples}",
            display=False,
        )
        audio = audio_window.concatenate(np).astype(np.float32, copy=False)
        chunk_audio_seconds = float(audio.shape[0]) / float(SAMPLE_RATE)
        audio_rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        audio_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        audio_rms_db = 20.0 * float(np.log10(max(audio_rms, 1e-12)))
        audio_peak_db = 20.0 * float(np.log10(max(audio_peak, 1e-12)))
        chunk_started_at = time.perf_counter()
        translation_elapsed = 0.0
        translation_attempted = False
        translation_started_at = chunk_started_at
        text = ""
        try:
            evidence = AudioEvidence(
                chunkIndex=chunks,
                inputDevice=str(worker._cfg.inputDevice),
                sampleRate=SAMPLE_RATE,
                windowSeconds=window_seconds,
                stepSeconds=step_seconds,
                audioWindow=audio,
                queueDrops=worker._audio_queue_drop_count() - last_audio_queue_drops,
            )
            hypothesis = recognition_node.recognize(
                evidence=evidence,
                model=model,
                stream_block=block,
                committed_text=committed_text,
                pending_text=pending_transcript_text,
            )
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
            if stable_analysis.current_units:
                count_metric("stable_window_observed")
                count_metric("stable_prefix_chars", stable_analysis.stable_prefix_chars)
                count_metric("unstable_tail_chars", stable_analysis.unstable_tail_chars)
                count_metric("stable_internal_chars", stable_analysis.stable_internal_chars)
                count_metric(
                    "stable_internal_ratio_per_1000",
                    int(round(stable_analysis.stable_internal_ratio * 1000)),
                )
                count_metric("stable_token_ratio_per_1000", int(round(stable_analysis.stable_token_ratio * 1000)))
                count_metric(f"stable_overlap_source_{stable_analysis.stable_overlap_source}")
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
            completed_sentences: list[str] = []
            final_segments: list[tuple[int, str]] = []
            boundary_complete = 0
            boundary_soft = 0
            boundary_end_marks = 0
            boundary_right_context_starts = 0
            boundary_confidence_display = (
                f"{adjusted_boundary_confidence:.2f}" if adjusted_boundary_confidence is not None else "n/a"
            )
            if text and is_repeated_hallucination(text):
                count_segment_state("suppressed")
                worker._emit("status", f"받아쓰기 AI 반복 전사 무시: chunk={chunks} text={text!r}", display=False)
                text = ""
            if text:
                no_text_stage_skip_chunks = 0
                prior_pending_transcript_text = pending_transcript_text
                candidate_set = candidate_node.interpret(
                    hypothesis=hypothesis,
                    context=UncommittedContext(
                        committedText=committed_text,
                        pendingText=pending_transcript_text,
                    ),
                )
                completed_sentences = list(candidate_set.completedCandidates)
                pending_transcript_text = candidate_set.pendingTail
                boundary_complete = int(candidate_set.boundarySignals.get("boundary_count", 0))
                boundary_soft = int(candidate_set.boundarySignals.get("soft_boundary_count", 0))
                boundary_end_marks = int(candidate_set.boundarySignals.get("end_mark_count", 0))
                boundary_right_context_starts = int(
                    candidate_set.boundarySignals.get("right_context_start_count", 0)
                )
                if boundary_end_marks:
                    count_metric("boundary_end_marks", boundary_end_marks)
                if boundary_right_context_starts:
                    count_metric("boundary_right_context_starts", boundary_right_context_starts)
                if completed_sentences:
                    pending_chunks = 0
                elif pending_transcript_text:
                    pending_chunks += 1
                for sentence_index, sentence in enumerate(completed_sentences):
                    produced_segments = stage_completed_sentence(
                        sentence,
                        detected,
                        later_completed_sentences=completed_sentences[sentence_index + 1 :],
                        prior_pending_text=prior_pending_transcript_text,
                    )
                    final_segments.extend(produced_segments)
                    for _segment_id, produced_sentence in produced_segments:
                        pending_transcript_text = _consume_committed_prefix(pending_transcript_text, produced_sentence)
                        if not pending_transcript_text:
                            pending_chunks = 0
                if completed_sentences:
                    final_segments.extend(age_staged_sentence(detected, pending_transcript_text))
                if pending_transcript_text:
                    count_segment_state("pending")
                    worker._emit(
                        "status",
                        "받아쓰기 AI pending tail: "
                        f"chunk={chunks} language={detected} text={pending_transcript_text!r}",
                        display=False,
                    )
                elif not completed_sentences:
                    final_segments.extend(age_staged_sentence(detected, pending_transcript_text))
            else:
                preview_chars = max(0, len(_normalized_text(window_text)) - len(_normalized_text(stable_text)))
                worker._emit(
                    "status",
                    f"받아쓰기 AI 전사 결과 없음: chunk={chunks} preview_chars={preview_chars}",
                    display=False,
                )
                if pending_transcript_text:
                    count_segment_state("pending")
                    pending_chunks += 1
                count_metric("stage_age_no_text_skipped")
                if active_stage.sentence and not pending_transcript_text:
                    no_text_stage_skip_chunks += 1
                    suppress_stale_no_text_stage(detected)
                else:
                    no_text_stage_skip_chunks = 0
            pending_overrun_reason = _pending_overrun_reason(pending_transcript_text, pending_chunks)
            if pending_overrun_reason:
                count_metric("pending_overrun")
                count_metric(f"pending_overrun_reason_{pending_overrun_reason}")
            pending_quality_flags = _pending_text_diagnostic_flags(pending_transcript_text, detected, pending_chunks)
            for flag in pending_quality_flags:
                count_metric(f"pending_quality_{flag}")
            worker._emit(
                "status",
                "받아쓰기 AI 문장 진단: "
                f"chunk={chunks} completed={len(completed_sentences)} final={len(final_segments)} "
                f"pending_overrun={pending_overrun_reason or 'none'} "
                f"pending_quality={','.join(pending_quality_flags) or 'none'} "
                f"boundary_backend={worker._sentence_boundary_detector.backend} "
                f"boundary_complete={boundary_complete} boundary_soft={boundary_soft} boundary_conf={boundary_confidence_display} "
                f"boundary_end_marks={boundary_end_marks} boundary_right_context={boundary_right_context_starts} "
                f"boundary_conf_segment={hypothesis.segmentBoundaryConfidence if hypothesis.segmentBoundaryConfidence is not None else 'n/a'} "
                f"boundary_conf_stable={hypothesis.stableBoundaryConfidence if hypothesis.stableBoundaryConfidence is not None else 'n/a'} "
                f"pending_chars={len(pending_transcript_text)} pending_chunks={pending_chunks} "
                f"pending_chars_per_chunk={len(pending_transcript_text) / max(pending_chunks, 1):.1f} "
                f"window_chars={len(_normalized_text(window_text))} stable_chars={len(_normalized_text(stable_text))} "
                f"stable_prefix_chars={stable_analysis.stable_prefix_chars} "
                f"unstable_tail_chars={stable_analysis.unstable_tail_chars} "
                f"stable_internal_chars={stable_analysis.stable_internal_chars} "
                f"stable_internal_ratio={stable_analysis.stable_internal_ratio:.3f} "
                f"stable_token_ratio={stable_analysis.stable_token_ratio:.3f} "
                f"stable_overlap_source={stable_analysis.stable_overlap_source} "
                f"delta_chars={len(_normalized_text(text))} "
                f"end_marks_window={_sentence_end_count(window_text)} end_marks_stable={_sentence_end_count(stable_text)} "
                f"end_marks_delta={_sentence_end_count(text)} "
                f"stable_tail={_diagnostic_tail(stable_text)} delta_tail={_diagnostic_tail(text)} "
                f"pending_tail={_diagnostic_tail(pending_transcript_text)} "
                f"revision_context_chars={len(_normalized_text(_revision_lifecycle_context(committed_text, active_stage.sentence, pending_transcript_text)))} "
                f"chunk_metrics={_format_transcript_metrics(chunk_lifecycle_metrics)} "
                f"lifecycle_metrics={_format_transcript_metrics(lifecycle_metrics)} "
                f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} staged_forced={active_stage.forced} "
                f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
                display=False,
            )
            translation_jobs: list[tuple[int, str]] = []
            for segment_id, sentence in final_segments:
                if _should_translate_final_sentence(sentence, detected):
                    translation_jobs.append((segment_id, sentence))
                else:
                    count_metric("translation_skip_final_quality")
                    worker._emit(
                        "status",
                        "받아쓰기 AI 번역 생략: "
                        f"chunk={chunks} segment_id={segment_id} reason=final_quality "
                        f"flags={','.join(_final_sentence_diagnostic_flags(sentence, detected))} "
                        f"text={sentence!r}",
                        display=False,
                    )
            if worker._cfg.translationEnabled and not translation_failed and translation_jobs:
                try:
                    translation_attempted = True
                    request_label = "Whisper 백엔드 내장 번역 요청" if text_translator is None else "외부 텍스트 번역 요청"
                    target_language = worker._cfg.translationTargetLanguage
                    source_language = detected if detected in {"ko", "en", "zh"} else worker._cfg.language
                    for segment_id, sentence in translation_jobs:
                        translation_started_at = time.perf_counter()
                        worker._emit(
                            "status",
                            f"{request_label}: chunk={chunks} segment_id={segment_id} final=True",
                            display=False,
                        )
                        translated_text = ""
                        if text_translator is None:
                            translated_segments, _translated_info = model.transcribe(
                                audio,
                                language=language,
                                task="translate",
                                                beam_size=worker._cfg.beamSize,
                                temperature=worker._cfg.temperature,
                                max_new_tokens=worker._cfg.maxNewTokens,
                                without_timestamps=True,
                                condition_on_previous_text=False,
                            )
                            translated_window_text = " ".join(
                                segment.text.strip() for segment in translated_segments if segment.text.strip()
                            ).strip()
                            translated_stable_text = _stable_window_text(
                                translated_window_text,
                                0.0,
                                window_seconds,
                            )
                            translated_text = _new_text_delta(committed_translation_text, translated_stable_text)
                            target_language = "en"
                        else:
                            translated_text = text_translator.translate(
                                TranslationRequest(
                                    text=sentence,
                                    source_language=source_language,
                                    target_language=target_language,
                                )
                            )
                        translation_elapsed += time.perf_counter() - translation_started_at
                        if translated_text:
                            worker._emit(
                                "status",
                                "받아쓰기 AI 번역 진단: "
                                f"chunk={chunks} segment_id={segment_id} final=True "
                                f"source_lang={source_language} target_lang={target_language} "
                                f"source_chars={len(_normalized_text(sentence))} "
                                f"target_chars={len(_normalized_text(translated_text))} "
                                f"backend={worker._cfg.translationBackend} model={worker._cfg.translationModel}",
                                display=False,
                            )
                            committed_translation_text = _append_committed_text(committed_translation_text, translated_text)
                            worker._emit(
                                "translation",
                                translated_text,
                                log_text=f"[{detected}->{target_language}#{segment_id}] {translated_text}",
                                final=True,
                                segment_id=segment_id,
                            )
                        else:
                            worker._emit("status", f"받아쓰기 AI 번역 결과 없음: chunk={chunks}", display=False)
                except Exception as exc:
                    translation_elapsed = time.perf_counter() - translation_started_at if translation_attempted else 0.0
                    translation_failed = True
                    worker._emit(
                        "error",
                        "받아쓰기 AI 번역 실패: "
                        f"{exc}. 번역을 이번 세션에서 중지합니다. STT 전사는 계속됩니다.",
                    )
            total_elapsed = time.perf_counter() - chunk_started_at
            current_audio_queue_drops = worker._audio_queue_drop_count()
            chunk_audio_queue_drops = current_audio_queue_drops - last_audio_queue_drops
            last_audio_queue_drops = current_audio_queue_drops
            current_queue_size = worker._audio_queue.qsize()
            chunk_lifecycle_metrics["input_queue_size_peak"] = max(
                chunk_lifecycle_metrics.get("input_queue_size_peak", 0),
                current_queue_size,
            )
            lifecycle_metrics["input_queue_size_peak"] = max(
                lifecycle_metrics.get("input_queue_size_peak", 0),
                current_queue_size,
            )
            if current_queue_size >= max(5, int(round(window_seconds / max(step_seconds, 0.001)))):
                count_metric("input_queue_backlog_chunk")
            if chunk_audio_queue_drops:
                chunk_lifecycle_metrics["input_queue_drops"] = chunk_audio_queue_drops
                lifecycle_metrics["input_queue_drops"] = lifecycle_metrics.get("input_queue_drops", 0) + chunk_audio_queue_drops
            stage_decision_count = sum(
                value for key, value in chunk_lifecycle_metrics.items() if key.startswith("stage_replace_decision_")
            )
            stage_replace_count = chunk_lifecycle_metrics.get("stage_replace", 0)
            stage_replaced_unconfirmed_count = chunk_lifecycle_metrics.get("stage_replaced_unconfirmed", 0)
            stage_revision_count = chunk_lifecycle_metrics.get("stage_revision", 0)
            stage_revision_changed_count = chunk_lifecycle_metrics.get("stage_revision_changed", 0)
            stage_revision_reset_count = chunk_lifecycle_metrics.get("stage_revision_confirmation_reset", 0)
            stage_revision_preserved_internal_count = chunk_lifecycle_metrics.get(
                "stage_revision_confirmation_preserved_internal",
                0,
            )
            stage_revision_internal_high_count = chunk_lifecycle_metrics.get(
                "stage_revision_internal_stability_high",
                0,
            )
            stage_revision_internal_mid_count = chunk_lifecycle_metrics.get(
                "stage_revision_internal_stability_mid",
                0,
            )
            stage_revision_internal_low_count = chunk_lifecycle_metrics.get(
                "stage_revision_internal_stability_low",
                0,
            )
            stage_queue_enqueue_count = chunk_lifecycle_metrics.get("stage_queue_enqueue", 0)
            stage_queue_promote_count = chunk_lifecycle_metrics.get("stage_queue_promote", 0)
            stage_queue_revision_count = chunk_lifecycle_metrics.get("stage_queue_revision", 0)
            stage_queue_drop_oldest_count = chunk_lifecycle_metrics.get("stage_queue_drop_oldest", 0)
            stage_queue_recent_final_suppressed_count = chunk_lifecycle_metrics.get(
                "stage_queue_recent_final_suppressed",
                0,
            )
            stage_queue_recent_final_delta_trimmed_count = chunk_lifecycle_metrics.get(
                "stage_queue_recent_final_delta_trimmed",
                0,
            )
            stage_replace_deferred_same_chunk_count = chunk_lifecycle_metrics.get(
                "stage_replace_deferred_same_chunk",
                0,
            )
            stage_finalize_before_replace_count = chunk_lifecycle_metrics.get("stage_finalize_before_replace", 0)
            stage_age_finalize_count = chunk_lifecycle_metrics.get("stage_age_finalize", 0)
            stage_age_quality_blocked_count = chunk_lifecycle_metrics.get("stage_age_quality_blocked", 0)
            stage_age_no_text_skipped_count = chunk_lifecycle_metrics.get("stage_age_no_text_skipped", 0)
            stage_no_text_stale_suppressed_count = chunk_lifecycle_metrics.get("stage_no_text_stale_suppressed", 0)
            stage_unconfirmed_replacement_suppressed_count = chunk_lifecycle_metrics.get(
                "stage_unconfirmed_replacement_suppressed",
                0,
            )
            stage_start_count = chunk_lifecycle_metrics.get("stage_start", 0)
            finalize_count = chunk_lifecycle_metrics.get("finalized", 0)
            duplicate_suppressed_count = chunk_lifecycle_metrics.get("candidate_duplicate_suppressed", 0)
            prior_pending_prefix_trimmed_count = chunk_lifecycle_metrics.get("candidate_prior_pending_prefix_trimmed", 0)
            recent_echo_suppressed_count = chunk_lifecycle_metrics.get("finalize_recent_echo_suppressed", 0)
            delta_suppressed_stage_retained_count = chunk_lifecycle_metrics.get(
                "finalize_delta_suppressed_stage_retained",
                0,
            )
            delta_suppressed_stage_dropped_count = chunk_lifecycle_metrics.get(
                "finalize_delta_suppressed_stage_dropped",
                0,
            )
            delta_trimmed_count = chunk_lifecycle_metrics.get("candidate_delta_trimmed", 0)
            stable_prefix_chars = chunk_lifecycle_metrics.get("stable_prefix_chars", 0)
            unstable_tail_chars = chunk_lifecycle_metrics.get("unstable_tail_chars", 0)
            stable_internal_chars = chunk_lifecycle_metrics.get("stable_internal_chars", 0)
            stable_internal_ratio_per_1000 = chunk_lifecycle_metrics.get("stable_internal_ratio_per_1000", 0)
            stable_token_ratio_per_1000 = chunk_lifecycle_metrics.get("stable_token_ratio_per_1000", 0)
            stage_candidate_quality_blocked_count = chunk_lifecycle_metrics.get("stage_candidate_quality_blocked", 0)
            stage_candidate_quality_count = sum(
                value
                for key, value in chunk_lifecycle_metrics.items()
                if key.startswith("stage_candidate_quality_") and key != "stage_candidate_quality_blocked"
            )
            stage_candidate_quality_cjk_internal_gap_count = chunk_lifecycle_metrics.get(
                "stage_candidate_quality_cjk_internal_gap",
                0,
            )
            stage_candidate_quality_mixed_latin_count = chunk_lifecycle_metrics.get(
                "stage_candidate_quality_mixed_latin_zh",
                0,
            )
            segment_state_pending_count = chunk_lifecycle_metrics.get("segment_state_pending", 0)
            segment_state_staged_count = chunk_lifecycle_metrics.get("segment_state_staged", 0)
            segment_state_final_count = chunk_lifecycle_metrics.get("segment_state_final", 0)
            segment_state_suppressed_count = chunk_lifecycle_metrics.get("segment_state_suppressed", 0)
            segment_state_revised_count = chunk_lifecycle_metrics.get("segment_state_revised", 0)
            final_quality_count = sum(
                value for key, value in chunk_lifecycle_metrics.items() if key.startswith("final_quality_")
            )
            revision_confirmation_observed_count = (
                stage_revision_reset_count + stage_revision_preserved_internal_count
            )
            input_queue_size_peak = chunk_lifecycle_metrics.get("input_queue_size_peak", 0)
            input_queue_backlog_count = chunk_lifecycle_metrics.get("input_queue_backlog_chunk", 0)
            raw_without_final_count = 1 if raw_window_text and not final_segments else 0
            if raw_without_final_count:
                count_metric("raw_without_final")
            translation_skip_count = chunk_lifecycle_metrics.get("translation_skip_final_quality", 0)
            worker._emit(
                "status",
                "받아쓰기 AI 안정성 지표: "
                f"chunk={chunks} replace={stage_replace_count} replaced_unconfirmed={stage_replaced_unconfirmed_count} "
                f"revision={stage_revision_count} revision_changed={stage_revision_changed_count} "
                f"revision_reset={stage_revision_reset_count} "
                f"revision_preserved_internal={stage_revision_preserved_internal_count} finalized={finalize_count} "
                f"revision_internal_high={stage_revision_internal_high_count} "
                f"revision_internal_mid={stage_revision_internal_mid_count} "
                f"revision_internal_low={stage_revision_internal_low_count} "
                f"stage_queue_enqueue={stage_queue_enqueue_count} "
                f"stage_queue_promote={stage_queue_promote_count} "
                f"stage_queue_revision={stage_queue_revision_count} "
                f"stage_queue_drop_oldest={stage_queue_drop_oldest_count} "
                f"stage_queue_recent_final_suppressed={stage_queue_recent_final_suppressed_count} "
                f"stage_queue_recent_final_delta_trimmed={stage_queue_recent_final_delta_trimmed_count} "
                f"stage_replace_deferred_same_chunk={stage_replace_deferred_same_chunk_count} "
                f"stage_queue_len={len(commit_buffer_node)} "
                f"finalize_before_replace={stage_finalize_before_replace_count} "
                f"age_finalize={stage_age_finalize_count} "
                f"age_quality_blocked={stage_age_quality_blocked_count} "
                f"age_no_text_skipped={stage_age_no_text_skipped_count} "
                f"no_text_stale_suppressed={stage_no_text_stale_suppressed_count} "
                f"unconfirmed_replacement_suppressed={stage_unconfirmed_replacement_suppressed_count} "
                f"stage_start={stage_start_count} "
                f"duplicate_suppressed={duplicate_suppressed_count} "
                f"prior_pending_prefix_trimmed={prior_pending_prefix_trimmed_count} "
                f"recent_echo_suppressed={recent_echo_suppressed_count} "
                f"finalize_delta_suppressed_stage_retained={delta_suppressed_stage_retained_count} "
                f"finalize_delta_suppressed_stage_dropped={delta_suppressed_stage_dropped_count} "
                f"delta_trimmed={delta_trimmed_count} "
                f"stable_prefix_chars={stable_prefix_chars} unstable_tail_chars={unstable_tail_chars} "
                f"stable_internal_chars={stable_internal_chars} "
                f"stable_internal_ratio={stable_internal_ratio_per_1000 / 1000:.3f} "
                f"stable_token_ratio={stable_token_ratio_per_1000 / 1000:.3f} "
                f"stage_candidate_quality_blocked={stage_candidate_quality_blocked_count} "
                f"stage_candidate_quality={stage_candidate_quality_count} "
                f"stage_candidate_quality_cjk_internal_gap={stage_candidate_quality_cjk_internal_gap_count} "
                f"stage_candidate_quality_mixed_latin_zh={stage_candidate_quality_mixed_latin_count} "
                f"segment_state_pending={segment_state_pending_count} "
                f"segment_state_staged={segment_state_staged_count} "
                f"segment_state_final={segment_state_final_count} "
                f"segment_state_suppressed={segment_state_suppressed_count} "
                f"segment_state_revised={segment_state_revised_count} "
                f"final_quality={final_quality_count} translation_skip={translation_skip_count} "
                f"raw_without_final={raw_without_final_count} "
                f"finalized_per_stage_start={finalize_count / max(stage_start_count, 1):.2f} "
                f"revision_preserve_rate={stage_revision_preserved_internal_count / max(revision_confirmation_observed_count, 1):.2f} "
                f"replace_unconfirmed_rate={stage_replaced_unconfirmed_count / max(stage_replace_count, 1):.2f} "
                f"input_queue_size_peak={input_queue_size_peak} "
                f"input_queue_backlog={input_queue_backlog_count} "
                f"decision_count={stage_decision_count}",
                display=False,
            )
            worker._emit(
                "status",
                "받아쓰기 AI 성능: "
                f"chunk={chunks} step={step_seconds:.2f}s window={window_seconds:.2f}s "
                f"audio={chunk_audio_seconds:.2f}s "
                f"stt={stt_elapsed:.2f}s stt_rtf={stt_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                f"stt_step_load={stt_elapsed / max(step_seconds, 0.001):.2f} "
                f"translation={translation_elapsed:.2f}s translation_enabled={worker._cfg.translationEnabled and not translation_failed} "
                f"total={total_elapsed:.2f}s total_rtf={total_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                f"total_step_load={total_elapsed / max(step_seconds, 0.001):.2f} "
                f"effective_latency_estimate={window_seconds + total_elapsed:.2f}s "
                f"audio_rms_db={audio_rms_db:.1f} audio_peak_db={audio_peak_db:.1f} "
                f"input_queue_drops={chunk_audio_queue_drops} input_queue_drops_total={current_audio_queue_drops} "
                f"queue_size={current_queue_size} queue_peak={input_queue_size_peak} "
                f"beam={worker._cfg.beamSize} max_tokens={worker._cfg.maxNewTokens} text_chars={len(text)}",
                display=False,
            )
        except Exception as exc:
            worker._emit("error", f"받아쓰기 AI 전사 실패: {exc}")
            worker._stop.set()
            raise

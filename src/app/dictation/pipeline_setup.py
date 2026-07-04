from __future__ import annotations
"""Bootstrap helpers for the realtime dictation loop.

This module groups the one-time setup performed before the per-chunk loop
starts. It exists to keep `run_transcribe_loop` focused on runtime flow rather
than object construction details.
"""

from dataclasses import dataclass

from src.app.dictation.audio_window import SlidingAudioWindow
from src.app.dictation.node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation.node_speech_evidence_to_stt_hypothesis import SpeechEvidenceToSttHypothesisNode
from src.app.dictation.node_stt_hypothesis_to_sentence_candidate import SttHypothesisToSentenceCandidateNode
from src.app.dictation.pipeline_runtime_support import RuntimeLoopSupport
from src.app.dictation.pipeline_settings import (
    MAX_RECENT_SHORT_TEXT_REPEATS,
    RECENT_TRANSCRIPT_WINDOW,
    SAMPLE_RATE,
    max_staged_sentence_queue,
)
from src.app.dictation.pipeline_types import ActiveStage, TranscriptWorkerLike


@dataclass(slots=True)
class TranscribeLoopSetup:
    step_seconds: float
    window_seconds: float
    sentence_finalize_age: int
    audio_window: SlidingAudioWindow
    language: str
    loop_support: RuntimeLoopSupport
    last_audio_queue_drops: int
    recognition_node: SpeechEvidenceToSttHypothesisNode
    candidate_node: SttHypothesisToSentenceCandidateNode
    commit_buffer_node: SentenceCandidateCommitBufferNode
    active_stage: ActiveStage


def create_transcribe_loop_setup(worker: TranscriptWorkerLike) -> TranscribeLoopSetup:
    step_seconds = float(worker._cfg.stepSeconds)
    window_seconds = float(worker._cfg.windowSeconds)
    sentence_finalize_age = int(getattr(worker._cfg, "sentenceFinalizeAge", 3))
    step_samples = int(SAMPLE_RATE * step_seconds)
    window_samples = int(SAMPLE_RATE * window_seconds)
    audio_window = SlidingAudioWindow(window_samples=window_samples, step_samples=step_samples)
    loop_support = RuntimeLoopSupport(
        max_recent_short_text_repeats=MAX_RECENT_SHORT_TEXT_REPEATS,
        recent_transcript_window=RECENT_TRANSCRIPT_WINDOW,
    )
    commit_buffer_node = SentenceCandidateCommitBufferNode(max_staged_sentence_queue())
    return TranscribeLoopSetup(
        step_seconds=step_seconds,
        window_seconds=window_seconds,
        sentence_finalize_age=sentence_finalize_age,
        audio_window=audio_window,
        language=worker._cfg.language,
        loop_support=loop_support,
        last_audio_queue_drops=worker._audio_queue_drop_count(),
        recognition_node=SpeechEvidenceToSttHypothesisNode(worker._cfg),
        candidate_node=SttHypothesisToSentenceCandidateNode(worker._sentence_boundary_detector_for),
        commit_buffer_node=commit_buffer_node,
        active_stage=commit_buffer_node.active,
    )

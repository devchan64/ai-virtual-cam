from __future__ import annotations
"""STT request/response helpers for the realtime dictation loop."""

from dataclasses import dataclass
from typing import Any

from src.app.dictation_node_speech_evidence_to_stt_hypothesis import SpeechEvidenceToSttHypothesisNode
from src.app.dictation_pipeline_contracts import AudioEvidence, RecognitionHypothesis
from src.app.dictation_pipeline_types import SttModelLike


@dataclass(frozen=True, slots=True)
class ChunkRecognitionRuntime:
    evidence: AudioEvidence
    hypothesis: RecognitionHypothesis


def recognize_chunk(
    *,
    recognition_node: SpeechEvidenceToSttHypothesisNode,
    chunk_index: int,
    input_device: str,
    sample_rate: int,
    window_seconds: float,
    step_seconds: float,
    audio: Any,
    queue_drops: int,
    model: SttModelLike,
    stream_block: Any,
    committed_text: str,
    pending_text: str,
) -> ChunkRecognitionRuntime:
    evidence = AudioEvidence(
        chunkIndex=chunk_index,
        inputDevice=input_device,
        sampleRate=sample_rate,
        windowSeconds=window_seconds,
        stepSeconds=step_seconds,
        audioWindow=audio,
        queueDrops=queue_drops,
    )
    hypothesis = recognition_node.recognize(
        evidence=evidence,
        model=model,
        stream_block=stream_block,
        committed_text=committed_text,
        pending_text=pending_text,
    )
    return ChunkRecognitionRuntime(evidence=evidence, hypothesis=hypothesis)

from __future__ import annotations
"""Shared typing contracts for the dictation pipeline helpers."""

from queue import Queue
from threading import Event
from typing import Any, Iterable, Protocol

from src.app.dictation.node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation.pipeline_contracts import ActiveSentenceCandidate
from src.app.dictation_core.stable_token_detection import StableWindowAnalysis
from src.app.models.stt_model import SttInfo, SttSegment
from src.app.models.translation_model import TranslationRequest
from src.domain.config import DictationAiConfig


class TranscriptWorkerLike(Protocol):
    _cfg: DictationAiConfig
    _audio_queue: Queue[object]
    _sentence_boundary_detector: Any
    _stop: Event

    def _audio_queue_drop_count(self) -> int: ...

    def _emit(
        self,
        kind: str,
        text: str,
        *,
        display: bool = True,
        log_text: str | None = None,
        final: bool = True,
        segment_id: int | None = None,
    ) -> None: ...

    def _sentence_boundary_detector_for(self, detected_language: str) -> Any: ...

    def _stt_settings_for_language(self) -> tuple[str, str]: ...


class SttModelLike(Protocol):
    streaming: bool

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Iterable[SttSegment], SttInfo]: ...


class TextTranslatorLike(Protocol):
    def translate(self, request: TranslationRequest) -> str: ...


ActiveStage = ActiveSentenceCandidate
CommitBufferNode = SentenceCandidateCommitBufferNode
StableAnalysis = StableWindowAnalysis

from __future__ import annotations

from typing import Any, Callable

from src.app.dictation_pipeline_contracts import RecognitionHypothesis, SentenceCandidateSet, UncommittedContext
from src.app.dictation_transcript_logic import _normalized_text


SentenceBoundaryProvider = Callable[[str], Any]


class SttHypothesisToSentenceCandidateNode:
    def __init__(self, boundary_provider: SentenceBoundaryProvider) -> None:
        self._boundary_provider = boundary_provider

    def interpret(
        self,
        *,
        hypothesis: RecognitionHypothesis,
        context: UncommittedContext,
    ) -> SentenceCandidateSet:
        detector = self._boundary_provider(hypothesis.language)
        boundary_result = detector.split(
            context.pendingText,
            hypothesis.deltaText,
            hypothesis.language,
            boundary_confidence=hypothesis.boundaryConfidence,
        )
        completed = tuple(_normalized_text(sentence) for sentence in boundary_result.completed)
        return SentenceCandidateSet(
            chunkIndex=hypothesis.chunkIndex,
            language=hypothesis.language,
            completedCandidates=completed,
            pendingTail=_normalized_text(boundary_result.pending),
            priorPendingText=context.pendingText,
            boundarySignals={
                "boundary_count": boundary_result.boundary_count,
                "soft_boundary_count": boundary_result.soft_boundary_count,
                "end_mark_count": boundary_result.end_mark_count,
                "right_context_start_count": boundary_result.right_context_start_count,
                "boundary_confidence": hypothesis.boundaryConfidence
                if hypothesis.boundaryConfidence is not None
                else "n/a",
                "boundary_backend": getattr(detector, "backend", ""),
            },
            textDelta=hypothesis.deltaText,
        )

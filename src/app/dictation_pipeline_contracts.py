from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AudioEvidence:
    chunkIndex: int
    inputDevice: str
    sampleRate: int
    windowSeconds: float
    stepSeconds: float
    audioWindow: Any
    queueDrops: int = 0


@dataclass(frozen=True)
class RecognitionHypothesis:
    chunkIndex: int
    language: str
    rawText: str
    windowText: str
    stableText: str
    deltaText: str
    acceptedSegments: tuple[str, ...] = ()
    rejectedReasons: tuple[str, ...] = ()
    stability: Any = None
    boundaryConfidence: float | None = None
    segmentBoundaryConfidence: float | None = None
    stableBoundaryConfidence: float | None = None
    elapsedSeconds: float = 0.0


@dataclass(frozen=True)
class UncommittedContext:
    committedText: str
    pendingText: str


@dataclass(frozen=True)
class SentenceCandidateSet:
    chunkIndex: int
    language: str
    completedCandidates: tuple[str, ...] = ()
    pendingTail: str = ""
    priorPendingText: str = ""
    boundarySignals: dict[str, int | float | str] = field(default_factory=dict)
    candidateQualityFlags: tuple[str, ...] = ()
    textDelta: str = ""


@dataclass
class CommitState:
    committedText: str = ""
    candidateBuffer: list[dict[str, Any]] = field(default_factory=list)
    revisionHashIndex: dict[str, int] = field(default_factory=dict)
    consumeSequence: int = 0
    recentFinals: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommittedTranscriptEvent:
    consumeSequence: int
    createdSequence: int
    revisionHash: str
    chunkIndex: int
    language: str
    text: str
    qualityFlags: tuple[str, ...] = ()
    final: bool = True


@dataclass(frozen=True)
class SuppressedCandidate:
    chunkIndex: int
    language: str
    text: str
    reason: str

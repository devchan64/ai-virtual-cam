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
class ActiveSentenceCandidate:
    sentence: str = ""
    confirmations: int = 0
    age: int = 0
    forced: bool = False
    deferredAgeChunk: int = -1
    deltaSuppressedChunks: int = 0
    deltaSuppressedChunkIndex: int = -1

    def clear(self) -> None:
        self.sentence = ""
        self.confirmations = 0
        self.age = 0
        self.forced = False
        self.deferredAgeChunk = -1
        self.deltaSuppressedChunks = 0
        self.deltaSuppressedChunkIndex = -1

    def start(self, sentence: str, *, forced: bool, chunk_index: int) -> None:
        self.sentence = sentence
        self.confirmations = 1
        self.age = 0
        self.forced = forced
        self.deferredAgeChunk = chunk_index
        self.deltaSuppressedChunks = 0
        self.deltaSuppressedChunkIndex = -1

    def apply_buffer_entry(self, entry: dict[str, object]) -> None:
        self.sentence = str(entry["sentence"])
        self.confirmations = int(entry["confirmations"])
        self.age = int(entry["age"])
        self.forced = bool(entry["forced"])
        self.deferredAgeChunk = int(entry["deferred_age_chunk"])
        self.deltaSuppressedChunks = 0
        self.deltaSuppressedChunkIndex = -1


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

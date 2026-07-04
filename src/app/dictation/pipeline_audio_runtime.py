from __future__ import annotations
"""Audio chunk preparation helpers for the realtime dictation loop."""

from dataclasses import dataclass
import time
from typing import Any

from src.app.dictation.audio_window import SlidingAudioWindow
from src.app.dictation.pipeline_settings import SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class ChunkAudioRuntime:
    audio: Any
    chunk_audio_seconds: float
    audio_rms_db: float
    audio_peak_db: float
    chunk_started_at: float


def prepare_chunk_audio(audio_window: SlidingAudioWindow, np: Any) -> ChunkAudioRuntime:
    audio = audio_window.concatenate(np).astype(np.float32, copy=False)
    chunk_audio_seconds = float(audio.shape[0]) / float(SAMPLE_RATE)
    audio_rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    audio_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return ChunkAudioRuntime(
        audio=audio,
        chunk_audio_seconds=chunk_audio_seconds,
        audio_rms_db=20.0 * float(np.log10(max(audio_rms, 1e-12))),
        audio_peak_db=20.0 * float(np.log10(max(audio_peak, 1e-12))),
        chunk_started_at=time.perf_counter(),
    )

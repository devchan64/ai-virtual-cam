from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.config import AudioGateConfig


class GateState(str, Enum):
    CLOSED = "closed"
    ATTACK = "attack"
    OPEN = "open"
    HOLD = "hold"
    RELEASE = "release"


@dataclass(frozen=True)
class GateStepResult:
    state: GateState
    gain: float
    inputLevelDb: float
    voiceBandRatio: float


class NoiseGate:
    """Gate state machine for microphone level control."""

    def __init__(self, config: AudioGateConfig, frame_ms: int) -> None:
        self._cfg = config
        self._frame_ms = max(1, frame_ms)
        self._state = GateState.CLOSED
        self._gain = config.closedGain
        self._hold_left_ms = 0

    def step(self, input_level_db: float, voice_band_ratio: float = 1.0) -> GateStepResult:
        if not self._cfg.enabled:
            return GateStepResult(
                state=GateState.OPEN,
                gain=self._cfg.openGain,
                inputLevelDb=input_level_db,
                voiceBandRatio=voice_band_ratio,
            )

        open_thr = self._cfg.thresholdDb
        close_thr = open_thr - self._cfg.hysteresisDb
        has_voice = voice_band_ratio >= self._cfg.minVoiceBandRatio
        above_open = input_level_db >= open_thr and has_voice
        below_close = input_level_db < close_thr

        if self._state == GateState.CLOSED:
            if above_open:
                self._state = GateState.ATTACK
        elif self._state == GateState.ATTACK:
            if below_close:
                self._state = GateState.RELEASE
            elif self._gain >= self._cfg.openGain - 1e-6:
                self._state = GateState.OPEN
        elif self._state == GateState.OPEN:
            if below_close:
                self._state = GateState.HOLD
                self._hold_left_ms = self._cfg.holdMs
        elif self._state == GateState.HOLD:
            if above_open:
                self._state = GateState.OPEN
            else:
                self._hold_left_ms -= self._frame_ms
                if self._hold_left_ms <= 0:
                    self._state = GateState.RELEASE
        elif self._state == GateState.RELEASE:
            if above_open:
                self._state = GateState.ATTACK
            elif self._gain <= self._cfg.closedGain + 1e-6:
                self._state = GateState.CLOSED

        self._gain = self._advance_gain(self._state)
        return GateStepResult(
            state=self._state,
            gain=self._gain,
            inputLevelDb=input_level_db,
            voiceBandRatio=voice_band_ratio,
        )

    def _advance_gain(self, state: GateState) -> float:
        if state in {GateState.OPEN, GateState.HOLD}:
            return self._cfg.openGain
        if state == GateState.CLOSED:
            return self._cfg.closedGain
        if state == GateState.ATTACK:
            return _ramp_towards(self._gain, self._cfg.openGain, self._cfg.attackMs, self._frame_ms)
        if state == GateState.RELEASE:
            return _ramp_towards(self._gain, self._cfg.closedGain, self._cfg.releaseMs, self._frame_ms)
        return self._gain


def _ramp_towards(current: float, target: float, duration_ms: int, frame_ms: int) -> float:
    if duration_ms <= 0:
        return target
    step = (target - current) * min(1.0, float(frame_ms) / float(duration_ms))
    out = current + step
    if target >= current:
        return min(target, out)
    return max(target, out)

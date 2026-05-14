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
        self._state_elapsed_ms = 0
        self._state_start_gain = config.closedGain

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
                self._enter_state(GateState.ATTACK)
        elif self._state == GateState.ATTACK:
            if below_close:
                self._enter_state(GateState.RELEASE)
            elif self._state_elapsed_ms >= self._cfg.attackMs:
                self._enter_state(GateState.OPEN)
        elif self._state == GateState.OPEN:
            if below_close:
                self._enter_state(GateState.HOLD)
                self._hold_left_ms = self._cfg.holdMs
        elif self._state == GateState.HOLD:
            if above_open:
                self._enter_state(GateState.OPEN)
            else:
                self._hold_left_ms -= self._frame_ms
                if self._hold_left_ms <= 0:
                    self._enter_state(GateState.RELEASE)
        elif self._state == GateState.RELEASE:
            if above_open:
                self._enter_state(GateState.ATTACK)
            elif self._state_elapsed_ms >= self._cfg.releaseMs:
                self._enter_state(GateState.CLOSED)
        else:
            self._enter_state(GateState.CLOSED)

        if self._state == GateState.OPEN or self._state == GateState.HOLD:
            self._gain = self._cfg.openGain
        elif self._state == GateState.CLOSED:
            self._gain = self._cfg.closedGain
        elif self._state == GateState.ATTACK:
            self._state_elapsed_ms += self._frame_ms
            self._gain = _ramp_towards(
                self._state_start_gain,
                self._cfg.openGain,
                self._cfg.attackMs,
                self._state_elapsed_ms,
            )
        elif self._state == GateState.RELEASE:
            self._state_elapsed_ms += self._frame_ms
            self._gain = _ramp_towards(
                self._state_start_gain,
                self._cfg.closedGain,
                self._cfg.releaseMs,
                self._state_elapsed_ms,
            )
        else:
            self._gain = self._cfg.closedGain
        return GateStepResult(
            state=self._state,
            gain=self._gain,
            inputLevelDb=input_level_db,
            voiceBandRatio=voice_band_ratio,
        )

    def _enter_state(self, state: GateState) -> None:
        if self._state != state:
            self._state = state
            self._state_elapsed_ms = 0
            self._state_start_gain = self._gain


def _ramp_towards(start: float, target: float, duration_ms: int, elapsed_ms: int) -> float:
    if duration_ms <= 0:
        return target
    ratio = min(1.0, float(elapsed_ms) / float(duration_ms))
    return start + (target - start) * ratio

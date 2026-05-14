from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from src.audio.gate import NoiseGate
from src.domain.config import AudioMixerConfig


@dataclass
class GateStepResult:
    stream_open: bool
    gate_state: str
    level_db: float
    voice_ratio: float
    gain: float


class AudioMixerCore:
    """Shared gate/mixing logic independent from device runtime."""

    def __init__(self, config: AudioMixerConfig) -> None:
        self._cfg = config
        self._gate = NoiseGate(config.gate, frame_ms=config.frameMs)
        self.steps = 0
        self.stream_open = False
        self.last_gate_state = "closed"
        self._denoise_warned = False

    def step_gate(self, level_db: float, voice_ratio: float) -> GateStepResult:
        gate = self._gate.step(level_db, voice_band_ratio=voice_ratio)
        gate_state = gate.state.value
        stream_open = gate_state in {"attack", "open", "hold", "release"}
        self.steps += 1
        self.last_gate_state = gate_state
        self.stream_open = stream_open
        return GateStepResult(
            stream_open=stream_open,
            gate_state=gate_state,
            level_db=float(gate.inputLevelDb),
            voice_ratio=float(gate.voiceBandRatio),
            gain=float(gate.gain),
        )

    def process_audio_block(self, data: np.ndarray, *, sample_rate: int, out_channels: int) -> tuple[np.ndarray, GateStepResult]:
        mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
        mono = np.clip(mono, -1.0, 1.0)
        level_db = self.rms_dbfs(mono)
        voice_ratio = self.voice_band_ratio(mono, sample_rate)
        gate_step = self.step_gate(level_db, voice_ratio)

        processed = self.apply_denoise(data, sample_rate=sample_rate)
        if processed.shape[1] != out_channels:
            base = processed.mean(axis=1, keepdims=True)
            processed = base if out_channels == 1 else np.repeat(base, out_channels, axis=1)

        if gate_step.stream_open:
            out = processed * gate_step.gain
        else:
            out = np.zeros_like(processed)
        np.clip(out, -1.0, 1.0, out=out)
        return out, gate_step

    def apply_denoise(self, data: np.ndarray, *, sample_rate: int) -> np.ndarray:
        _ = sample_rate
        if not self._cfg.denoiseEnabled or self._cfg.denoiseBackend == "none":
            return data
        if not self._denoise_warned:
            print(
                "[audio] denoise runtime hook is currently pass-through. "
                "Keep denoise.enabled=false or set backend='none' for real output now.",
                flush=True,
            )
            self._denoise_warned = True
        return data

    @staticmethod
    def rms_dbfs(mono: np.ndarray) -> float:
        if mono.size == 0:
            return -120.0
        mono = np.asarray(mono, dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
        return float(20.0 * np.log10(max(rms, 1e-12)))

    @staticmethod
    def voice_band_ratio(mono: np.ndarray, sample_rate: int) -> float:
        if mono.size < 32:
            return 0.0
        window = np.hanning(mono.size).astype(np.float32)
        spec = np.fft.rfft((mono.astype(np.float32) * window))
        power = np.abs(spec) ** 2
        freqs = np.fft.rfftfreq(mono.size, d=1.0 / float(sample_rate))

        total_band = (freqs >= 80.0) & (freqs <= 8000.0)
        voice_band = (freqs >= 300.0) & (freqs <= 3400.0)
        total_power = float(np.sum(power[total_band]))
        if total_power <= 1e-12:
            return 0.0
        voice_power = float(np.sum(power[voice_band]))
        return float(max(0.0, min(1.0, voice_power / total_power)))

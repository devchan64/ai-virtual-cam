from __future__ import annotations

import time

from src.audio.gate import NoiseGate
from src.domain.config import AudioMixerConfig


class VirtualAudioMixer:
    """Virtual audio mixer scaffold.

    Phase 1 scope:
    - define gate behavior/state transition
    - keep runtime contract and logs ready for real I/O integration
    """

    def __init__(self, config: AudioMixerConfig) -> None:
        self._cfg = config
        self._gate = NoiseGate(config.gate, frame_ms=config.frameMs)
        self._running = False

    def run(self, max_steps: int = 0) -> None:
        print(
            "[audio] mixer starting: "
            f"in={self._cfg.inputDevice} out={self._cfg.outputDevice} "
            f"{self._cfg.sampleRate}Hz/{self._cfg.channels}ch frame={self._cfg.frameMs}ms",
            flush=True,
        )
        print(
            "[audio] denoise config: "
            f"enabled={self._cfg.denoiseEnabled} backend={self._cfg.denoiseBackend} strength={self._cfg.denoiseStrength:.2f}",
            flush=True,
        )
        print(
            "[audio] gate config: "
            f"enabled={self._cfg.gate.enabled} thresholdDb={self._cfg.gate.thresholdDb} "
            f"hysteresisDb={self._cfg.gate.hysteresisDb} attack={self._cfg.gate.attackMs}ms "
            f"hold={self._cfg.gate.holdMs}ms release={self._cfg.gate.releaseMs}ms "
            f"minVoiceBandRatio={self._cfg.gate.minVoiceBandRatio:.2f}",
            flush=True,
        )
        self._running = True
        steps = 0
        while self._running:
            # TODO: replace with real microphone RMS/peak + spectral voice-band ratio.
            level_db = -90.0
            voice_band_ratio = 0.0
            gate = self._gate.step(level_db, voice_band_ratio=voice_band_ratio)
            steps += 1
            if steps == 1 or steps % 50 == 0:
                print(
                    f"[audio] gate heartbeat: step={steps} levelDb={gate.inputLevelDb:.1f} "
                    f"voiceRatio={gate.voiceBandRatio:.2f} state={gate.state.value} gain={gate.gain:.2f}",
                    flush=True,
                )
            if max_steps > 0 and steps >= max_steps:
                break
            time.sleep(max(0.001, self._cfg.frameMs / 1000.0))
        print("[audio] mixer stopped", flush=True)

    def stop(self) -> None:
        self._running = False

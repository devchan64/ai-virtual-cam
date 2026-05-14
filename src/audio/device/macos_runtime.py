from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
from src.audio.core import AudioMixerCore
from src.domain.config import AudioMixerConfig

try:
    import sounddevice as sd
except ModuleNotFoundError:
    sd = None


class MacOSAudioRuntime:
    def __init__(self, config: AudioMixerConfig, on_stream_state: Callable[[bool, str, int], None] | None = None) -> None:
        self._cfg = config
        self._core = AudioMixerCore(config)
        self._on_stream_state = on_stream_state
        self._running = False

    def _resolve_default_sounddevice(self, configured: str, *, kind: str) -> str:
        name = str(configured).strip()
        if name.lower() != "default" or sd is None:
            return name
        try:
            default_pair = sd.default.device
            index_pos = 0 if kind == "input" else 1
            default_index = int(default_pair[index_pos]) if default_pair and default_pair[index_pos] is not None else -1
            if default_index < 0:
                return name
            info = sd.query_devices(default_index, kind=kind)
            resolved = str(info.get("name", "")).strip()
            return resolved or name
        except Exception:
            return name

    def run(self, max_steps: int = 0) -> None:
        if sd is None:
            raise RuntimeError("sounddevice 모듈이 필요합니다. ./bin/avc setup 후 다시 시도하세요.")

        frame_samples = max(1, int(self._cfg.sampleRate * self._cfg.frameMs / 1000.0))
        configured_input = str(self._cfg.inputDevice).strip() or "default"
        configured_output = str(self._cfg.outputDevice).strip() or "default"
        input_device = self._resolve_default_sounddevice(configured_input, kind="input")
        output_device = self._resolve_default_sounddevice(configured_output, kind="output")
        in_channels = int(self._cfg.channels)
        out_channels = int(self._cfg.channels)

        try:
            input_info = sd.query_devices(input_device, kind="input")
        except Exception as exc:
            raise RuntimeError(f"audio input device open failed: configured input '{input_device}': {exc}") from exc
        try:
            output_info = sd.query_devices(output_device, kind="output")
        except Exception as exc:
            raise RuntimeError(f"audio output device open failed: configured output '{output_device}': {exc}") from exc

        if in_channels > int(input_info.get("max_input_channels", in_channels)):
            in_channels = int(input_info.get("max_input_channels", in_channels))
        if out_channels > int(output_info.get("max_output_channels", out_channels)):
            out_channels = int(output_info.get("max_output_channels", out_channels))
        if in_channels <= 0 or out_channels <= 0:
            raise RuntimeError("selected input/output device has no usable channels")

        print(
            "[audio] mixer starting (sounddevice): "
            f"in={input_device} out={output_device} "
            f"{self._cfg.sampleRate}Hz/{in_channels}->{out_channels}ch frame={self._cfg.frameMs}ms",
            flush=True,
        )
        if configured_input != input_device:
            print(f"[audio] input device resolved: configured='{configured_input}' runtime='{input_device}'", flush=True)
        if configured_output != output_device:
            print(f"[audio] output device resolved: configured='{configured_output}' runtime='{output_device}'", flush=True)
        print("[audio] policy: system default sink/source is not modified by this process", flush=True)

        self._running = True
        self._core.steps = 0
        self._core.stream_open = False
        self._core.last_gate_state = "closed"

        def callback(
            indata: np.ndarray,
            outdata: np.ndarray,
            frames: int,
            _time: dict[str, Any],
            status: sd.CallbackFlags,
        ) -> None:
            if status.input_overflow:
                print("[audio] input overflow", flush=True)
            if status.output_underflow:
                print("[audio] output underflow", flush=True)
            if frames <= 0 or not self._running:
                outdata.fill(0.0)
                return

            step_before = self._core.last_gate_state
            stream_before = self._core.stream_open
            out, gate_step = self._core.process_audio_block(
                indata.astype(np.float32, copy=True),
                sample_rate=self._cfg.sampleRate,
                out_channels=outdata.shape[1],
            )
            outdata[:] = out

            if gate_step.gate_state != step_before:
                print(
                    f"[audio] gate transition: step={self._core.steps} "
                    f"{step_before} -> {gate_step.gate_state} "
                    f"levelDb={gate_step.level_db:.1f} voiceRatio={gate_step.voice_ratio:.2f}",
                    flush=True,
                )
            if stream_before != gate_step.stream_open and self._on_stream_state is not None:
                self._on_stream_state(gate_step.stream_open, gate_step.gate_state, self._core.steps)

            if max_steps > 0 and self._core.steps >= max_steps:
                self._running = False
                raise sd.CallbackStop

        try:
            with sd.Stream(
                samplerate=self._cfg.sampleRate,
                blocksize=frame_samples,
                dtype="float32",
                channels=(in_channels, out_channels),
                device=(input_device, output_device),
                callback=callback,
            ):
                while self._running:
                    time.sleep(max(0.001, self._cfg.frameMs / 1000.0))
        finally:
            self._running = False
            if self._on_stream_state is not None:
                self._on_stream_state(False, "stop", self._core.steps)
            print("[audio] mixer stopped (sounddevice)", flush=True)

    def stop(self) -> None:
        self._running = False

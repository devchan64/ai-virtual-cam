from __future__ import annotations

import platform
import subprocess
import threading
import time
from typing import Any, Callable

import numpy as np
from src.audio.gate import NoiseGate
from src.domain.config import AudioMixerConfig

try:
    import sounddevice as sd
    SOUNDDEVICE_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    sd = None
    SOUNDDEVICE_IMPORT_ERROR = exc


class VirtualAudioMixer:
    """Virtual audio mixer implementation.

    Current scope:
    - real-time capture/playback via sounddevice
    - level + voice-band metrics feeding existing gate state machine
    - log output for troubleshooting
    """

    def __init__(
        self,
        config: AudioMixerConfig,
        on_stream_state: Callable[[bool, str, int], None] | None = None,
    ) -> None:
        self._cfg = config
        self._gate = NoiseGate(config.gate, frame_ms=config.frameMs)
        self._running = False
        self._steps = 0
        self._stream = None
        self._denoise_warned = False
        self._on_stream_state = on_stream_state
        self._stream_open = False
        self._last_gate_state = "closed"

    def run(self, max_steps: int = 0) -> None:
        if sd is None:
            raise RuntimeError(
                "sounddevice is required for audio mixer. Install via: ./bin/avc setup"
            ) from SOUNDDEVICE_IMPORT_ERROR

        frame_samples = max(1, int(self._cfg.sampleRate * self._cfg.frameMs / 1000.0))
        configured_input = str(self._cfg.inputDevice).strip()
        configured_output = str(self._cfg.outputDevice).strip()
        if self._is_virtual_mic_sink_available() and configured_input.lower() == "default":
            raise RuntimeError(
                "audio input is ambiguous. configured input='default'. "
                "가상 마이크 경로에서는 inputDevice를 monitor/source ID로 명시하세요 "
                "(예: ai-virtual-cam.monitor 또는 alsa_input...__source)."
            )
        if self._is_virtual_mic_sink_available() and not self._is_virtual_mic_output_selected(configured_output):
            raise RuntimeError(
                "audio output is not virtual-mic sink. "
                f"configured='{configured_output}'. "
                "가상 마이크로 전달하려면 outputDevice를 'ai-virtual-cam'으로 설정하세요."
            )
        input_device = self._resolve_sounddevice_input_device(configured_input)
        output_device = self._resolve_sounddevice_output_device(configured_output)
        in_channels = self._cfg.channels
        out_channels = self._cfg.channels

        try:
            input_info = sd.query_devices(input_device, kind="input")
        except Exception as exc:
            raise RuntimeError(f"audio input device open failed: configured input '{input_device}': {exc}") from exc

        try:
            output_info = sd.query_devices(output_device, kind="output")
        except Exception as exc:
            try:
                output_names = [
                    str(device.get("name", "")).strip()
                    for device in sd.query_devices()
                    if int(device.get("max_output_channels", 0)) > 0
                ]
                output_names = [name for name in output_names if name]
            except Exception:
                output_names = []
            raise RuntimeError(
                f"audio output device open failed: configured output '{output_device}': {exc}. "
                f"Available output devices: {output_names or ['<none>']}"
            ) from exc

        try:
            if int(output_info.get("max_output_channels", 0)) <= 0:
                raise RuntimeError(f"configured output device '{output_device}' has no output channels")
            if in_channels > int(input_info.get("max_input_channels", in_channels)):
                in_channels = int(input_info.get("max_input_channels", in_channels))
                print(
                    f"[audio] adjusted input channels to {in_channels} (device max)",
                    flush=True,
                )
            if out_channels > int(output_info.get("max_output_channels", out_channels)):
                out_channels = int(output_info.get("max_output_channels", out_channels))
                print(
                    f"[audio] adjusted output channels to {out_channels} (device max)",
                    flush=True,
                )
            if in_channels <= 0 or out_channels <= 0:
                raise RuntimeError("selected input/output device has no usable channels")
        except Exception as exc:
            raise RuntimeError(f"audio device open failed: {exc}") from exc

        if in_channels != self._cfg.channels or out_channels != self._cfg.channels:
            print(
                "[audio] channel mismatch: "
                f"configured={self._cfg.channels}, in={in_channels}, out={out_channels}",
                flush=True,
            )

        if input_device != configured_input:
            print(
                f"[audio] input device resolved: configured='{configured_input}' runtime='{input_device}'",
                flush=True,
            )
        if output_device != configured_output:
            print(
                f"[audio] output device resolved: configured='{configured_output}' runtime='{output_device}'",
                flush=True,
            )

        print(
            "[audio] mixer starting: "
            f"in={input_device} out={output_device} "
            f"{self._cfg.sampleRate}Hz/{in_channels}->{out_channels}ch "
            f"frame={self._cfg.frameMs}ms ({frame_samples}frames)",
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
        if self._cfg.denoiseEnabled and self._cfg.denoiseBackend != "none":
            print(
                f"[audio] denoise requested but runtime backend is placeholder: {self._cfg.denoiseBackend}",
                flush=True,
            )

        self._running = True
        self._steps = 0
        self._stream_open = False
        self._last_gate_state = "closed"

        def _report_stream_state(opened: bool, state: str) -> None:
            if not self._running:
                return
            self._stream_open = opened
            if self._on_stream_state is not None:
                self._on_stream_state(opened, state, self._steps)

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

            if not self._running:
                outdata.fill(0.0)
                return

            data = indata.astype(np.float32, copy=True)
            mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
            mono = np.clip(mono, -1.0, 1.0)

            level_db = self._rms_dbfs(mono)
            voice_band_ratio = self._voice_band_ratio(mono, self._cfg.sampleRate)
            if self._steps == 0 or self._steps % 50 == 0:
                print(
                    f"[audio] input heartbeat: step={self._steps} "
                    f"levelDb={level_db:.1f} voiceRatio={voice_band_ratio:.2f}",
                    flush=True,
                )
            gate = self._gate.step(level_db, voice_band_ratio=voice_band_ratio)
            gain = float(gate.gain)
            current_gate_state = gate.state.value
            if current_gate_state != self._last_gate_state:
                prev_gate_state = self._last_gate_state
                self._last_gate_state = current_gate_state
                if self._on_stream_state is not None:
                    opened_for_event = current_gate_state in {"attack", "open", "hold", "release"}
                    self._on_stream_state(opened_for_event, current_gate_state, self._steps)
                print(
                    f"[audio] gate transition: step={self._steps} "
                    f"{prev_gate_state} -> {current_gate_state} "
                    f"levelDb={gate.inputLevelDb:.1f} voiceRatio={gate.voiceBandRatio:.2f}",
                    flush=True,
                )
            # Keep stream open during RELEASE to preserve tail-ramp behavior.
            stream_open = (
                current_gate_state in {"attack", "open", "hold", "release"}
                if self._cfg.gate.enabled
                else True
            )
            if stream_open != self._stream_open:
                _report_stream_state(stream_open, gate.state.value)

            processed = self._apply_denoise(data, sample_rate=self._cfg.sampleRate)
            if processed.shape[1] != outdata.shape[1]:
                base = processed.mean(axis=1, keepdims=True)
                if outdata.shape[1] == 1:
                    processed = base
                else:
                    processed = np.repeat(base, outdata.shape[1], axis=1)
            if stream_open:
                outdata[:] = processed * gain
            else:
                outdata.fill(0.0)
            np.clip(outdata, -1.0, 1.0, out=outdata)

            self._steps += 1
            if self._steps == 1 or self._steps % 50 == 0:
                print(
                    f"[audio] gate heartbeat: step={self._steps} levelDb={gate.inputLevelDb:.1f} "
                    f"voiceRatio={gate.voiceBandRatio:.2f} state={gate.state.value} gain={gate.gain:.2f}",
                    flush=True,
                )
                print(
                    f"[audio] stream state: {'open' if self._stream_open else 'closed'}",
                    flush=True,
                )

            if max_steps > 0 and self._steps >= max_steps:
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
                if max_steps > 0:
                    print(f"[audio] reached max_steps={max_steps}, stopping", flush=True)
        finally:
            # Explicitly clear mixer state on stream termination.
            self._running = False
            if self._stream_open:
                _report_stream_state(False, "stop")
        print("[audio] mixer stopped", flush=True)

    def _is_virtual_mic_sink_available(self) -> bool:
        if platform.system() != "Linux":
            return False
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode != 0:
                return False
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                if parts[1].strip() == "ai-virtual-cam":
                    return True
        except Exception:
            return False
        return False

    def _is_virtual_mic_output_selected(self, configured_output: str) -> bool:
        lowered = str(configured_output).strip().lower()
        if not lowered:
            return False
        if lowered == "ai-virtual-cam":
            return True
        return lowered.endswith("ai-virtual-cam")

    def stop(self) -> None:
        self._running = False

    def _resolve_sounddevice_input_device(self, configured: str) -> str:
        name = str(configured).strip()
        if platform.system() != "Linux" or sd is None or not name:
            return name
        if name.lower() == "default":
            return "default"
        try:
            sd.query_devices(name, kind="input")
            return name
        except Exception:
            pass
        return name

    def _pick_preferred_monitor_source(self) -> str | None:
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode != 0:
                return None
            source_names = []
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                source_names.append(parts[1].strip())
            for candidate in source_names:
                if candidate == "ai-virtual-cam.monitor":
                    return candidate
            for candidate in source_names:
                if candidate.endswith(".monitor"):
                    return candidate
        except Exception:
            return None
        return None

    def _resolve_sounddevice_output_device(self, configured: str) -> str:
        name = str(configured).strip()
        if platform.system() != "Linux" or sd is None or not name:
            return name
        if name.lower() == "default":
            return "default"
        try:
            sd.query_devices(name, kind="output")
            return name
        except Exception:
            pass
        return name

    def _apply_denoise(self, data: np.ndarray, sample_rate: int) -> np.ndarray:
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

    def _rms_dbfs(self, mono: np.ndarray) -> float:
        if mono.size == 0:
            return -120.0
        mono = np.asarray(mono, dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
        return float(20.0 * np.log10(max(rms, 1e-12)))

    def _voice_band_ratio(self, mono: np.ndarray, sample_rate: int) -> float:
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

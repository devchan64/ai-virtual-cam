from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from typing import Callable

from src.audio.core import AudioMixerCore
from src.domain.config import AudioMixerConfig


class LinuxAudioRuntime:
    def __init__(self, config: AudioMixerConfig, on_stream_state: Callable[[bool, str, int], None] | None = None) -> None:
        self._cfg = config
        self._core = AudioMixerCore(config)
        self._on_stream_state = on_stream_state
        self._running = False
        self._gst_proc: subprocess.Popen | None = None
        self._forward_proc: subprocess.Popen | None = None
        self._forward_mode: str | None = None

    def can_run(self) -> bool:
        return shutil.which("gst-launch-1.0") is not None

    def run(self, max_steps: int = 0) -> None:
        if not self.can_run():
            raise RuntimeError("gst-launch-1.0 is required for audio mixer runtime. Run ./bin/avc setup.")

        input_device = str(self._cfg.inputDevice).strip() or "default"
        output_device = str(self._cfg.outputDevice).strip() or "default"

        monitor_cmd = ["gst-launch-1.0", "-m", "-e"]
        monitor_cmd.extend(self._build_gst_input_src_tokens(input_device))
        monitor_cmd.extend(
            [
                "!",
                "audioconvert",
                "!",
                "audioresample",
                "!",
                f"audio/x-raw,rate={int(self._cfg.sampleRate)},channels={int(self._cfg.channels)}",
                "!",
                "level",
                "message=true",
                f"interval={int(self._cfg.frameMs) * 1000000}",
                "!",
                "fakesink",
            ]
        )

        print(
            "[audio] mixer starting (gstreamer): "
            f"in={input_device} out={output_device} "
            f"{self._cfg.sampleRate}Hz/{self._cfg.channels}ch frame={self._cfg.frameMs}ms",
            flush=True,
        )
        print(f"[audio] gst monitor cmd: {' '.join(monitor_cmd)}", flush=True)
        print("[audio] policy: system default sink/source is not modified by this process", flush=True)

        self._running = True
        self._core.steps = 0
        self._core.stream_open = False
        self._core.last_gate_state = "closed"
        self._start_forward_pipeline(input_device, output_device, mode="silence")
        if self._on_stream_state is not None:
            self._on_stream_state(False, "closed", 0)

        try:
            self._gst_proc = subprocess.Popen(
                monitor_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            def _reader() -> None:
                proc = self._gst_proc
                if proc is None or proc.stdout is None:
                    return
                while self._running:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    if "level" not in line.lower():
                        continue
                    parsed_level = self._parse_level_db_from_gst_line(line)
                    if parsed_level is None:
                        continue
                    level_db = max(parsed_level, -120.0)

                    prev_state = self._core.last_gate_state
                    prev_stream_open = self._core.stream_open
                    step = self._core.step_gate(level_db, voice_ratio=1.0)

                    if step.gate_state != prev_state:
                        print(
                            f"[audio] gate transition: step={self._core.steps} "
                            f"{prev_state} -> {step.gate_state} levelDb={level_db:.1f}",
                            flush=True,
                        )
                    if prev_stream_open != step.stream_open:
                        self._switch_forward_mode(input_device, output_device, "mic" if step.stream_open else "silence")
                        if self._on_stream_state is not None:
                            self._on_stream_state(step.stream_open, step.gate_state, self._core.steps)

            reader_thread = threading.Thread(target=_reader, daemon=True)
            reader_thread.start()

            if max_steps > 0:
                timeout_sec = max(1, int((max_steps * self._cfg.frameMs) / 1000))
                end_at = time.time() + timeout_sec
                while self._running and self._gst_proc.poll() is None and time.time() < end_at:
                    time.sleep(0.1)
                self.stop()
            else:
                no_signal_deadline = time.time() + 3.0
                while self._running and self._gst_proc.poll() is None:
                    if self._core.steps <= 0 and time.time() >= no_signal_deadline:
                        raise RuntimeError(
                            "audio input signal was not detected from gstreamer level messages within 3s. "
                            f"configured input='{input_device}', output='{output_device}'. "
                            "입력 장치 ID를 config에서 다시 선택하고 저장한 뒤 재시도하세요."
                        )
                    time.sleep(0.2)
            reader_thread.join(timeout=0.5)
        finally:
            self._running = False
            proc = self._gst_proc
            self._gst_proc = None
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=1.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            self._stop_forward_pipeline()
            if self._on_stream_state is not None:
                self._on_stream_state(False, "stop", 0)
            print("[audio] mixer stopped (gstreamer)", flush=True)

    def stop(self) -> None:
        self._running = False
        proc = self._gst_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self._stop_forward_pipeline()

    def _parse_level_db_from_gst_line(self, line: str) -> float | None:
        text = str(line)
        value = self._extract_gst_level_value(text, "rms")
        if value is not None:
            return value
        value = self._extract_gst_level_value(text, "peak")
        if value is not None:
            return value
        return None

    def _extract_gst_level_value(self, text: str, field: str) -> float | None:
        marker = f"{field}=(GValueArray)<"
        low = text.lower()
        idx = low.find(marker.lower())
        if idx < 0:
            return None
        tail = text[idx + len(marker):]
        end_idx = tail.find(">")
        if end_idx < 0:
            return None
        token = tail[:end_idx].strip().split(",")[0].strip().lower()
        if not token:
            return None
        if token in {"-inf", "inf", "+inf", "-nan", "nan", "+nan"}:
            return -120.0
        try:
            return float(token)
        except Exception:
            return None

    def _build_forward_cmd(self, input_device: str, output_device: str, mode: str) -> list[str]:
        cmd = ["gst-launch-1.0", "-q", "-e"]
        if mode == "mic":
            cmd.extend(self._build_gst_input_src_tokens(input_device))
        else:
            cmd.extend(["audiotestsrc", "is-live=true", "wave=silence"])
        cmd.extend(
            [
                "!",
                "audioconvert",
                "!",
                "audioresample",
                "!",
                f"audio/x-raw,rate={int(self._cfg.sampleRate)},channels={int(self._cfg.channels)}",
                "!",
                "queue",
                "!",
                "pulsesink",
            ]
        )
        if output_device.lower() not in {"default"}:
            cmd.append(f"device={output_device}")
        return cmd

    def _build_gst_input_src_tokens(self, input_device: str) -> list[str]:
        raw = str(input_device).strip()
        lowered = raw.lower()
        if not raw or lowered in {"default", "pulse"}:
            return ["pulsesrc"]
        hw = self._extract_alsa_hw_device(raw)
        if hw is not None:
            return ["alsasrc", f"device={hw}"]
        return ["pulsesrc", f"device={raw}"]

    def _extract_alsa_hw_device(self, value: str) -> str | None:
        text = str(value)
        m = re.search(r"\((hw:[0-9]+,[0-9]+)\)", text)
        if m is not None:
            return m.group(1)
        m2 = re.search(r"\b(hw:[0-9]+,[0-9]+)\b", text)
        if m2 is not None:
            return m2.group(1)
        return None

    def _start_forward_pipeline(self, input_device: str, output_device: str, mode: str) -> None:
        cmd = self._build_forward_cmd(input_device, output_device, mode)
        self._forward_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self._forward_mode = mode
        print(f"[audio] forward stream mode={mode}", flush=True)

    def _stop_forward_pipeline(self) -> None:
        proc = self._forward_proc
        self._forward_proc = None
        self._forward_mode = None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _switch_forward_mode(self, input_device: str, output_device: str, mode: str) -> None:
        if self._forward_mode == mode and self._forward_proc is not None and self._forward_proc.poll() is None:
            return
        self._stop_forward_pipeline()
        self._start_forward_pipeline(input_device, output_device, mode)

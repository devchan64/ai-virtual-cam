#!/usr/bin/env python3

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


from src.domain.config import AppConfig, WhisperConfig


SAMPLE_RATE = 16000
CHUNK_SECONDS = 5.0


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show local Whisper transcript window.")
    parser.add_argument("--config", default="~/.avc/setting.json", help="Path to the JSON config file.")
    return parser.parse_args()


def _sounddevice_device_name(configured: str) -> str | None:
    value = str(configured).strip()
    if not value or value.lower() == "default":
        return None
    return value


class WhisperTranscriptWorker:
    def __init__(self, config: WhisperConfig, events: queue.Queue[TranscriptEvent]) -> None:
        self._cfg = config
        self._events = events
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[object] = queue.Queue(maxsize=120)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            if self._cfg.backend == "mock":
                self._run_mock()
                return
            if self._cfg.backend != "faster-whisper":
                raise RuntimeError(
                    "지원하지 않는 whisper.backend입니다: "
                    f"{self._cfg.backend}. 현재 창 출력은 faster-whisper 또는 mock만 지원합니다."
                )

            try:
                import numpy as np
            except ModuleNotFoundError as exc:
                raise RuntimeError("numpy 모듈이 없습니다. ./bin/avc setup 실행 후 재시도하세요.") from exc
            try:
                import sounddevice as sd
            except ModuleNotFoundError as exc:
                raise RuntimeError("sounddevice 모듈이 없습니다. ./bin/avc setup 실행 후 재시도하세요.") from exc
            try:
                from faster_whisper import WhisperModel
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "faster-whisper 모듈이 없습니다. 로컬 Whisper를 사용하려면 faster-whisper와 CUDA 런타임을 설치하세요."
                ) from exc

            self._events.put(
                TranscriptEvent(
                    "status",
                    "Whisper 모델 로딩 중: "
                    f"backend={self._cfg.backend} model={self._cfg.model} "
                    f"device={self._cfg.device} compute={self._cfg.computeType}",
                )
            )
            model = WhisperModel(
                self._cfg.model,
                device=self._cfg.device,
                compute_type=self._cfg.computeType,
            )
            self._events.put(TranscriptEvent("status", f"입력 장치 열기: {self._cfg.inputDevice}"))

            def callback(indata, frames, time_info, status) -> None:
                if status:
                    self._events.put(TranscriptEvent("status", f"오디오 입력 상태: {status}"))
                mono = np.asarray(indata, dtype=np.float32)
                if mono.ndim == 2:
                    mono = mono[:, 0]
                try:
                    self._audio_queue.put_nowait(mono.copy())
                except queue.Full:
                    self._events.put(TranscriptEvent("status", "Whisper 입력 버퍼가 가득 차 오디오 프레임을 건너뜁니다."))

            device = _sounddevice_device_name(self._cfg.inputDevice)
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=device,
                callback=callback,
            ):
                self._events.put(TranscriptEvent("status", "Whisper 전사 시작"))
                self._transcribe_loop(model, np)
        except Exception as exc:
            self._events.put(TranscriptEvent("error", str(exc)))

    def _transcribe_loop(self, model, np) -> None:
        samples: list[object] = []
        target_samples = int(SAMPLE_RATE * CHUNK_SECONDS)
        buffered = 0
        language = None if self._cfg.language == "auto" else self._cfg.language
        while not self._stop.is_set():
            try:
                block = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            samples.append(block)
            buffered += int(block.shape[0])
            if buffered < target_samples:
                continue

            audio = np.concatenate(samples).astype(np.float32, copy=False)
            samples.clear()
            buffered = 0
            try:
                segments, info = model.transcribe(
                    audio,
                    language=language,
                    task=self._cfg.task,
                    vad_filter=self._cfg.vadFilter,
                    beam_size=5,
                    condition_on_previous_text=False,
                )
                text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
                if text:
                    detected = getattr(info, "language", self._cfg.language)
                    self._events.put(TranscriptEvent("transcript", f"[{detected}] {text}"))
            except Exception as exc:
                self._events.put(TranscriptEvent("error", f"Whisper 전사 실패: {exc}"))

    def _run_mock(self) -> None:
        self._events.put(TranscriptEvent("status", "Whisper mock 출력 시작"))
        index = 1
        while not self._stop.is_set():
            self._events.put(TranscriptEvent("transcript", f"[mock] sample transcript {index}"))
            index += 1
            self._stop.wait(2.0)


class WhisperTranscriptWindow:
    def __init__(self, app_config: AppConfig) -> None:
        if not app_config.whisper.enabled:
            raise RuntimeError("whisper.enabled=false 입니다. config에서 Whisper STT를 켠 뒤 serve를 실행하세요.")
        try:
            import tkinter as tk
            from tkinter import ttk
        except ModuleNotFoundError as exc:
            raise RuntimeError("Tkinter가 없습니다. Whisper 출력 창을 열 수 없습니다.") from exc

        self._tk = tk
        self._ttk = ttk
        self._events: queue.Queue[TranscriptEvent] = queue.Queue()
        self._worker = WhisperTranscriptWorker(app_config.whisper, self._events)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._root = tk.Tk()
        self._root.title("ai-virtual-cam Whisper")
        self._root.geometry("780x420")
        self._root.minsize(520, 280)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._text = tk.Text(frame, wrap="word", undo=False)
        self._text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self._text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._text.configure(yscrollcommand=scrollbar.set)
        self._text.bind("<Key>", self._on_text_key)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=self._copy_all)
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=self._clear)
        clear_btn.grid(row=0, column=2, sticky="e")

        self._root.protocol("WM_DELETE_WINDOW", self._close)

    def run(self) -> int:
        self._thread.start()
        self._root.after(100, self._poll_events)
        self._root.mainloop()
        return 0

    def _on_text_key(self, event) -> str | None:
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a"}:
            if event.keysym.lower() == "a":
                self._text.tag_add("sel", "1.0", "end-1c")
                return "break"
            return None
        return "break"

    def _append(self, line: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self._text.insert("end", f"[{timestamp}] {line}\n")
        self._text.see("end")

    def _poll_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            prefix = "ERROR: " if event.kind == "error" else ""
            self._append(prefix + event.text)
        self._root.after(100, self._poll_events)

    def _copy_all(self) -> None:
        text = self._text.get("1.0", "end-1c")
        self._root.clipboard_clear()
        self._root.clipboard_append(text)

    def _clear(self) -> None:
        self._text.delete("1.0", "end")

    def _close(self) -> None:
        self._worker.stop()
        self._root.after(100, self._root.destroy)


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser()
    app_config = AppConfig.load(config_path)
    window = WhisperTranscriptWindow(app_config)
    return window.run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[avc] whisper window failed: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)

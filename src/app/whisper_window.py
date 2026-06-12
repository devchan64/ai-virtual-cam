#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


from src.app.translation_model import TranslationRequest, build_text_translator
from src.domain.config import AppConfig, WhisperConfig


SAMPLE_RATE = 16000
DEFAULT_CHUNK_SECONDS = 5.0
DEFAULT_WINDOW_GEOMETRY = "780x420"
MIN_WINDOW_WIDTH = 520
MIN_WINDOW_HEIGHT = 280
_WINDOW_GEOMETRY_RE = re.compile(
    r"^(?P<width>\d+)x(?P<height>\d+)(?P<x_sign>[+-])(?P<x>\d+)(?P<y_sign>[+-])(?P<y>\d+)$"
)


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str
    display: bool = True
    log_text: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show local Whisper transcript window.")
    parser.add_argument("--config", default="~/.avc/setting.json", help="Path to the JSON config file.")
    return parser.parse_args()


def _log_line(message: str, *, file=None) -> None:
    target = sys.stdout if file is None else file
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", file=target, flush=True)


def _parse_window_geometry(geometry: object) -> dict[str, int] | None:
    if not isinstance(geometry, str):
        return None
    match = _WINDOW_GEOMETRY_RE.match(geometry.strip())
    if match is None:
        return None
    x = int(match.group("x"))
    y = int(match.group("y"))
    if match.group("x_sign") == "-":
        x = -x
    if match.group("y_sign") == "-":
        y = -y
    return {
        "width": int(match.group("width")),
        "height": int(match.group("height")),
        "x": x,
        "y": y,
    }


def _format_window_geometry(parts: dict[str, int]) -> str:
    x = int(parts["x"])
    y = int(parts["y"])
    return f'{int(parts["width"])}x{int(parts["height"])}{x:+d}{y:+d}'


def _sanitize_window_geometry(geometry: object, screen_width: int, screen_height: int) -> str | None:
    parts = _parse_window_geometry(geometry)
    if parts is None:
        return None
    width = parts["width"]
    height = parts["height"]
    x = parts["x"]
    y = parts["y"]
    if width < MIN_WINDOW_WIDTH or height < MIN_WINDOW_HEIGHT:
        return None
    if screen_width <= 0 or screen_height <= 0:
        return _format_window_geometry(parts)
    visible_margin = 80
    if x >= screen_width - visible_margin or y >= screen_height - visible_margin:
        return None
    if x + width <= visible_margin or y + height <= visible_margin:
        return None
    return _format_window_geometry(parts)


def _load_window_geometry(config_path: Path, key: str, root) -> str | None:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        meta = raw.get("meta") or {}
        if not isinstance(meta, dict):
            return None
        return _sanitize_window_geometry(meta.get(key), root.winfo_screenwidth(), root.winfo_screenheight())
    except Exception as exc:
        _log_line(f"[avc] whisper status: window geometry load failed: {exc}")
        return None


def _save_window_geometry(
    config_path: Path,
    key: str,
    geometry: str,
    screen_width: int = 0,
    screen_height: int = 0,
) -> None:
    try:
        sanitized = _sanitize_window_geometry(geometry, screen_width, screen_height)
        if sanitized is None:
            _log_line(f"[avc] whisper status: window geometry save skipped: invalid geometry={geometry}")
            return
        raw = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        if not isinstance(raw, dict):
            return
        raw.setdefault("meta", {})[key] = sanitized
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _log_line(f"[avc] whisper status: window geometry saved: {sanitized}")
    except Exception as exc:
        _log_line(f"[avc] whisper status: window geometry save failed: {exc}")

def _sounddevice_device_name(configured: str) -> str | None:
    value = str(configured).strip()
    if not value or value.lower() == "default":
        return None
    return value


def _is_exact_pulse_source(configured: str) -> bool:
    if platform.system() != "Linux":
        return False
    value = str(configured).strip().lower()
    if not value or value == "default":
        return False
    return value.startswith("alsa_input.") or value.endswith(".monitor") or value == "ai-virtual-cam"


def _is_modal_output_event(event: TranscriptEvent) -> bool:
    return event.display and event.kind in {"transcript", "translation"}


class WhisperTranscriptWorker:
    def __init__(self, config: WhisperConfig, events: queue.Queue[TranscriptEvent]) -> None:
        self._cfg = config
        self._events = events
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[object] = queue.Queue(maxsize=120)
        self._capture_process: subprocess.Popen[bytes] | None = None
        self._capture_thread: threading.Thread | None = None

    def _emit(self, kind: str, text: str, *, display: bool = True, log_text: str | None = None) -> None:
        _log_line(f"[avc] whisper {kind}: {log_text if log_text is not None else text}")
        self._events.put(TranscriptEvent(kind, text, display, log_text))

    def stop(self) -> None:
        self._stop.set()
        process = self._capture_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

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
            sd = None
            if not _is_exact_pulse_source(self._cfg.inputDevice):
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

            self._emit(
                "status",
                "Whisper 모델 로딩 중: "
                f"backend={self._cfg.backend} model={self._cfg.model} "
                f"device={self._cfg.device} compute={self._cfg.computeType}. "
                "최초 실행이면 모델 다운로드 때문에 시간이 걸릴 수 있습니다.",
            )
            try:
                model = WhisperModel(
                    self._cfg.model,
                    device=self._cfg.device,
                    compute_type=self._cfg.computeType,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Whisper 모델 로딩 실패: "
                    f"backend={self._cfg.backend} model={self._cfg.model} "
                    f"device={self._cfg.device} computeType={self._cfg.computeType}. "
                    "float16 오류가 발생하면 config의 Whisper 장치를 cuda로 명시하고 CUDA 런타임을 확인하거나, "
                    "CPU 실행 시 computeType을 int8 또는 float32로 변경하세요. "
                    f"원인: {exc}"
                ) from exc
            self._emit("status", "Whisper 모델 로딩 완료")
            text_translator = None
            if self._cfg.translationEnabled:
                self._emit(
                    "status",
                    "Whisper 번역 창 사용: "
                    f"backend={self._cfg.translationBackend} target_language={self._cfg.translationTargetLanguage} "
                    f"model={self._cfg.translationModel} device={self._cfg.translationDevice} "
                    f"compute={self._cfg.translationComputeType}",
                )
                text_translator = build_text_translator(
                    self._cfg.translationBackend,
                    self._cfg.translationModel,
                    self._cfg.translationDevice,
                    self._cfg.translationComputeType,
                )
            self._emit("status", f"입력 장치 열기: {self._cfg.inputDevice}")

            if _is_exact_pulse_source(self._cfg.inputDevice):
                self._start_pulse_capture(np)
                self._emit("status", f"Pulse source 직접 캡처 시작: {self._cfg.inputDevice}")
                self._transcribe_loop(model, np, text_translator)
                return

            assert sd is not None

            def callback(indata, frames, time_info, status) -> None:
                if status:
                    self._emit("status", f"오디오 입력 상태: {status}")
                mono = np.asarray(indata, dtype=np.float32)
                if mono.ndim == 2:
                    mono = mono[:, 0]
                try:
                    self._audio_queue.put_nowait(mono.copy())
                except queue.Full:
                    self._emit("status", "Whisper 입력 버퍼가 가득 차 오디오 프레임을 건너뜁니다.")

            device = _sounddevice_device_name(self._cfg.inputDevice)
            self._emit("status", f"sounddevice 캡처 시작: runtime_device={device or 'default'}")
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=device,
                callback=callback,
            ):
                self._emit("status", "Whisper 전사 시작")
                self._transcribe_loop(model, np, text_translator)
        except Exception as exc:
            self._emit("error", str(exc))

    def _start_pulse_capture(self, np) -> None:
        recorder = shutil.which("parec") or shutil.which("parecord")
        if recorder is None:
            raise RuntimeError("parec/parecord command not found. Run ./bin/avc setup and try again.")
        cmd = [
            recorder,
            "--device",
            self._cfg.inputDevice,
            "--format=s16le",
            "--rate",
            str(SAMPLE_RATE),
            "--channels",
            "1",
            "--raw",
        ]
        self._emit("status", "Pulse recorder spawn: " + " ".join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._capture_process = process
        bytes_per_block = int(SAMPLE_RATE * 0.2) * 2

        def read_loop() -> None:
            assert process.stdout is not None
            self._emit("status", f"Pulse recorder reader started: pid={process.pid}")
            while not self._stop.is_set() and process.poll() is None:
                data = process.stdout.read(bytes_per_block)
                if not data:
                    break
                try:
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    self._audio_queue.put(samples, timeout=0.2)
                except queue.Full:
                    self._emit("status", "Whisper 입력 버퍼가 가득 차 Pulse 프레임을 건너뜁니다.")
                except Exception as exc:
                    self._emit("error", f"Pulse 캡처 처리 실패: {exc}")
                    break
            if process.poll() not in (None, 0) and not self._stop.is_set():
                stderr = ""
                try:
                    stderr = (process.stderr.read() if process.stderr is not None else b"").decode(errors="replace").strip()
                except Exception:
                    stderr = ""
                self._emit("error", stderr or f"Pulse recorder exited with code {process.returncode}")
            else:
                self._emit("status", f"Pulse recorder reader stopped: pid={process.pid} code={process.poll()}")

        self._capture_thread = threading.Thread(target=read_loop, daemon=True)
        self._capture_thread.start()

    def _transcribe_loop(self, model, np, text_translator=None) -> None:
        samples: list[object] = []
        chunk_seconds = float(self._cfg.chunkSeconds or DEFAULT_CHUNK_SECONDS)
        target_samples = int(SAMPLE_RATE * chunk_seconds)
        buffered = 0
        language = None if self._cfg.language == "auto" else self._cfg.language
        chunks = 0
        translation_failed = False
        self._emit(
            "status",
            f"Whisper 전사 루프 시작: chunk_seconds={chunk_seconds} language={self._cfg.language} "
            f"translation_enabled={self._cfg.translationEnabled} "
            f"translation_backend={self._cfg.translationBackend} "
            f"translation_target={self._cfg.translationTargetLanguage} beam_size={self._cfg.beamSize}",
        )
        while not self._stop.is_set():
            try:
                block = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            samples.append(block)
            buffered += int(block.shape[0])
            if buffered < target_samples:
                continue

            chunks += 1
            self._emit("status", f"Whisper 전사 요청: chunk={chunks} samples={buffered}", display=False)
            audio = np.concatenate(samples).astype(np.float32, copy=False)
            samples.clear()
            buffered = 0
            try:
                segments, info = model.transcribe(
                    audio,
                    language=language,
                    task="transcribe",
                    vad_filter=self._cfg.vadFilter,
                    beam_size=self._cfg.beamSize,
                    condition_on_previous_text=False,
                )
                text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
                detected = getattr(info, "language", self._cfg.language)
                if text:
                    self._emit("transcript", text, log_text=f"[{detected}] {text}")
                else:
                    self._emit("status", f"Whisper 전사 결과 없음: chunk={chunks}", display=False)
                if self._cfg.translationEnabled and not translation_failed:
                    try:
                        self._emit("status", f"Whisper 번역 요청: chunk={chunks}", display=False)
                        translated_text = ""
                        target_language = self._cfg.translationTargetLanguage
                        if text_translator is None:
                            translated_segments, _translated_info = model.transcribe(
                                audio,
                                language=language,
                                task="translate",
                                vad_filter=self._cfg.vadFilter,
                                beam_size=self._cfg.beamSize,
                                condition_on_previous_text=False,
                            )
                            translated_text = " ".join(
                                segment.text.strip() for segment in translated_segments if segment.text.strip()
                            ).strip()
                            target_language = "en"
                        elif text:
                            source_language = detected if detected in {"ko", "en", "zh"} else self._cfg.language
                            translated_text = text_translator.translate(
                                TranslationRequest(
                                    text=text,
                                    source_language=source_language,
                                    target_language=target_language,
                                )
                            )
                        if translated_text:
                            self._emit(
                                "translation",
                                translated_text,
                                log_text=f"[{detected}->{target_language}] {translated_text}",
                            )
                        else:
                            self._emit("status", f"Whisper 번역 결과 없음: chunk={chunks}", display=False)
                    except Exception as exc:
                        translation_failed = True
                        self._emit(
                            "error",
                            "Whisper 번역 실패: "
                            f"{exc}. 번역을 이번 세션에서 중지합니다. STT 전사는 계속됩니다.",
                        )
            except Exception as exc:
                self._emit("error", f"Whisper 전사 실패: {exc}")

    def _run_mock(self) -> None:
        self._emit("status", "Whisper mock 출력 시작")
        index = 1
        while not self._stop.is_set():
            self._emit("transcript", f"[mock] sample transcript {index}")
            if self._cfg.translationEnabled:
                self._emit("translation", f"translated mock sample {index}", log_text=f"[mock->{self._cfg.translationTargetLanguage}] translated mock sample {index}")
            index += 1
            self._stop.wait(2.0)


class WhisperTranscriptWindow:
    def __init__(self, app_config: AppConfig, config_path: Path) -> None:
        if not app_config.whisper.enabled:
            raise RuntimeError("whisper.enabled=false 입니다. config에서 Whisper STT를 켠 뒤 serve를 실행하세요.")
        try:
            import tkinter as tk
            from tkinter import ttk
        except ModuleNotFoundError as exc:
            raise RuntimeError("Tkinter가 없습니다. Whisper 출력 창을 열 수 없습니다.") from exc

        self._tk = tk
        self._ttk = ttk
        self._config_path = config_path
        self._whisper_config = app_config.whisper
        self._geometry_save_after_id: str | None = None
        self._translation_geometry_save_after_id: str | None = None
        self._translation_root = None
        self._translation_text = None
        self._context_text = None
        self._events: queue.Queue[TranscriptEvent] = queue.Queue()
        self._worker = WhisperTranscriptWorker(app_config.whisper, self._events)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._root = tk.Tk()
        self._root.title("ai-virtual-cam Whisper Transcript")
        restored_geometry = _load_window_geometry(self._config_path, "whisperWindowGeometry", self._root)
        self._root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
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
        self._text.bind("<Button-3>", self._show_context_menu)
        self._text.bind("<Control-Button-1>", self._show_context_menu)
        self._context_menu = tk.Menu(self._root, tearoff=False)
        self._context_menu.add_command(label="Copy", command=self._copy_selection)
        self._context_menu.add_command(label="Copy All", command=self._copy_all)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Clear", command=self._clear)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=lambda: self._copy_all(self._text))
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=lambda: self._clear(self._text))
        clear_btn.grid(row=0, column=2, sticky="e")

        if self._whisper_config.translationEnabled:
            self._create_translation_window()

        self._root.bind("<Configure>", self._on_configure)
        self._root.protocol("WM_DELETE_WINDOW", self._close)


    def _create_translation_window(self) -> None:
        tk = self._tk
        ttk = self._ttk
        self._translation_root = tk.Toplevel(self._root)
        self._translation_root.title("ai-virtual-cam Whisper Translation")
        restored_geometry = _load_window_geometry(
            self._config_path, "whisperTranslationWindowGeometry", self._translation_root
        )
        self._translation_root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._translation_root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._translation_root.columnconfigure(0, weight=1)
        self._translation_root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._translation_root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._translation_text = tk.Text(frame, wrap="word", undo=False)
        self._translation_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self._translation_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._translation_text.configure(yscrollcommand=scrollbar.set)
        self._translation_text.bind("<Key>", self._on_text_key)
        self._translation_text.bind("<Button-3>", self._show_context_menu)
        self._translation_text.bind("<Control-Button-1>", self._show_context_menu)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=lambda: self._copy_all(self._translation_text))
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=lambda: self._clear(self._translation_text))
        clear_btn.grid(row=0, column=2, sticky="e")

        self._translation_root.bind("<Configure>", self._on_translation_configure)
        self._translation_root.protocol("WM_DELETE_WINDOW", self._hide_translation_window)

    def run(self) -> int:
        self._thread.start()
        self._root.after(100, self._poll_events)
        self._root.mainloop()
        return 0

    def _on_text_key(self, event) -> str | None:
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a"}:
            if event.keysym.lower() == "a":
                event.widget.tag_add("sel", "1.0", "end-1c")
                return "break"
            return None
        return "break"

    def _append(self, line: str, text_widget=None) -> None:
        target = text_widget if text_widget is not None else self._text
        target.insert("end", f"{line}\n")
        target.see("end")

    def _poll_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if not _is_modal_output_event(event):
                continue
            if event.kind == "translation" and self._translation_text is not None:
                self._append(event.text, self._translation_text)
            elif event.kind == "transcript":
                self._append(event.text, self._text)
        self._root.after(100, self._poll_events)

    def _on_configure(self, event) -> None:
        if event.widget != self._root:
            return
        if self._geometry_save_after_id is not None:
            try:
                self._root.after_cancel(self._geometry_save_after_id)
            except Exception:
                pass
        self._geometry_save_after_id = self._root.after(600, self._save_geometry)

    def _on_translation_configure(self, event) -> None:
        if self._translation_root is None or event.widget != self._translation_root:
            return
        if self._translation_geometry_save_after_id is not None:
            try:
                self._translation_root.after_cancel(self._translation_geometry_save_after_id)
            except Exception:
                pass
        self._translation_geometry_save_after_id = self._translation_root.after(600, self._save_translation_geometry)

    def _current_geometry(self) -> str:
        try:
            self._root.update_idletasks()
        except Exception:
            pass
        return self._root.winfo_geometry()

    def _save_geometry(self) -> None:
        self._geometry_save_after_id = None
        _save_window_geometry(
            self._config_path,
            "whisperWindowGeometry",
            self._current_geometry(),
            self._root.winfo_screenwidth(),
            self._root.winfo_screenheight(),
        )

    def _save_translation_geometry(self) -> None:
        self._translation_geometry_save_after_id = None
        if self._translation_root is None:
            return
        _save_window_geometry(
            self._config_path,
            "whisperTranslationWindowGeometry",
            self._translation_root.winfo_geometry(),
            self._translation_root.winfo_screenwidth(),
            self._translation_root.winfo_screenheight(),
        )

    def _show_context_menu(self, event) -> str:
        self._context_text = event.widget
        try:
            has_selection = bool(event.widget.tag_ranges("sel"))
            self._context_menu.entryconfigure("Copy", state="normal" if has_selection else "disabled")
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()
        return "break"

    def _copy_selection(self) -> None:
        target = self._context_text if self._context_text is not None else self._text
        try:
            text = target.get("sel.first", "sel.last")
        except Exception:
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(text)

    def _copy_all(self, text_widget=None) -> None:
        target = text_widget if text_widget is not None else (self._context_text or self._text)
        text = target.get("1.0", "end-1c")
        self._root.clipboard_clear()
        self._root.clipboard_append(text)

    def _clear(self, text_widget=None) -> None:
        target = text_widget if text_widget is not None else (self._context_text or self._text)
        target.delete("1.0", "end")

    def _hide_translation_window(self) -> None:
        if self._translation_root is not None:
            self._save_translation_geometry()
            self._translation_root.withdraw()

    def _close(self) -> None:
        if self._geometry_save_after_id is not None:
            try:
                self._root.after_cancel(self._geometry_save_after_id)
            except Exception:
                pass
            self._geometry_save_after_id = None
        if self._translation_geometry_save_after_id is not None and self._translation_root is not None:
            try:
                self._translation_root.after_cancel(self._translation_geometry_save_after_id)
            except Exception:
                pass
            self._translation_geometry_save_after_id = None
        self._save_geometry()
        self._save_translation_geometry()
        self._worker.stop()
        if self._translation_root is not None:
            try:
                self._translation_root.destroy()
            except Exception:
                pass
        self._root.after(100, self._root.destroy)


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser()
    app_config = AppConfig.load(config_path)
    window = WhisperTranscriptWindow(app_config, config_path)
    return window.run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _log_line(f"[avc] whisper window failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

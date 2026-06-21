#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


from src.app.rotating_log import install_rotating_stdout_log
from src.app.dictation_pipeline_loop import run_transcribe_loop
from src.app.dictation_pipeline_settings import (
    INPUT_AUDIO_QUEUE_MAX_SIZE,
    INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS,
    PULSE_CAPTURE_BLOCK_SECONDS,
    SAMPLE_RATE,
)
from src.app.dictation_window_events import TranscriptEvent, is_modal_output_event as _is_modal_output_event
from src.app.dictation_window_titles import dictation_window_title, supported_dictation_window_languages
from src.app.sentence_boundary import create_sentence_boundary_detector
from src.app.stt_model import build_stt_model
from src.app.translation_model import build_text_translator


from src.domain.dictation_ai_defaults import dictation_ai_default
from src.domain.config import AppConfig, DictationAiConfig
from src.domain.contracts.window_geometry import (
    DEFAULT_WINDOW_GEOMETRY_META,
    DICTATION_AI_DEFAULT_WINDOW_GEOMETRY as DEFAULT_WINDOW_GEOMETRY,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    WINDOW_GEOMETRY_FILE_NAME,
    format_window_geometry as _format_window_geometry,
    parse_window_geometry as _parse_window_geometry,
    read_legacy_window_geometry_meta as _read_legacy_window_geometry_meta,
    read_window_geometry_file as _read_window_geometry_file,
    sanitize_window_geometry as _sanitize_window_geometry,
    window_geometry_path as _window_geometry_path,
    window_manager_geometry as _window_manager_geometry,
    window_restore_extent as _window_restore_extent,
    write_window_geometry_file as _write_window_geometry_file,
)


DEFAULT_CHUNK_SECONDS = float(dictation_ai_default("chunkSeconds"))
STARTUP_AUDIO_DRAIN_SECONDS = 1.0
PULSE_CAPTURE_LATENCY_MSEC = 20
FINAL_TEXT_TAG = "final_text"
PARTIAL_TEXT_TAG = "partial_text"
ERROR_TEXT_TAG = "error_text"
FINAL_TEXT_COLOR = "black"
PARTIAL_TEXT_COLOR = "#008000"
ERROR_TEXT_COLOR = "#b00020"
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show local Dictation AI transcript window.")
    parser.add_argument("--config", default="~/.avc/setting.json", help="Path to the JSON config file.")
    return parser.parse_args()


def _log_line(message: str, *, file=None) -> None:
    target = sys.stdout if file is None else file
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", file=target, flush=True)


def _load_ui_language(config_path: Path) -> str:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log_line(f"[avc] Dictation AI status: UI language load failed: {exc}")
        return "en"
    if not isinstance(raw, dict):
        return "en"
    meta = raw.get("meta") or {}
    if not isinstance(meta, dict):
        return "en"
    language = str(meta.get("language", "en")).strip().lower()
    return language if language in supported_dictation_window_languages() else "en"


def _require_linux_cuda_runtime(config: DictationAiConfig) -> None:
    if platform.system() != "Linux":
        raise RuntimeError(
            "받아쓰기 AI는 Linux + NVIDIA CUDA 전용입니다. "
            f"currentOS={platform.system()} 설정값=dictationAi.enabled={config.enabled}"
        )
    required_cuda_devices = (
        ("dictationAi.device", config.device),
        ("dictationAi.sentenceBoundaryDevice", config.sentenceBoundaryDevice),
    )
    if config.translationEnabled:
        required_cuda_devices = required_cuda_devices + (
            ("dictationAi.translationDevice", config.translationDevice),
        )
    for path, device in required_cuda_devices:
        if device != "cuda":
            raise RuntimeError(
                f"받아쓰기 AI는 CUDA 전용입니다. {path}={device} 설정값을 cuda로 변경하세요."
            )
    try:
        import torch
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "받아쓰기 AI는 CUDA 사용 가능 PyTorch가 필요합니다. torch 설치와 CUDA 런타임을 확인하세요."
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError(
            "받아쓰기 AI는 CUDA 전용입니다. torch.cuda.is_available()=false. "
            "NVIDIA 드라이버, CUDA 런타임, PyTorch CUDA 빌드를 확인하세요."
        )


def _load_window_geometry(config_path: Path, key: str, root) -> str | None:
    default_geometry = DEFAULT_WINDOW_GEOMETRY_META.get(key)
    try:
        screen_width, screen_height = _window_restore_extent(root)
        geometry_file = _read_window_geometry_file(config_path)
        saved = geometry_file.get(key)
        source = WINDOW_GEOMETRY_FILE_NAME
        if saved is None:
            legacy_meta = _read_legacy_window_geometry_meta(config_path)
            saved = legacy_meta.get(key)
            source = "setting.json:meta"
        restored = _sanitize_window_geometry(saved, screen_width, screen_height)
        if restored:
            _log_line(
                f"[avc] Dictation AI status: window geometry restored: key={key} source={source} geometry={restored} "
                f"extent={screen_width}x{screen_height}"
            )
            return restored
        if default_geometry is not None:
            _log_line(
                f"[avc] Dictation AI status: window geometry defaulted: key={key} "
                f"saved={saved!r} default={default_geometry} extent={screen_width}x{screen_height}"
            )
            return default_geometry
        _log_line(
            f"[avc] Dictation AI status: window geometry restore skipped: key={key} "
            f"saved={saved!r} extent={screen_width}x{screen_height}"
        )
        return None
    except Exception as exc:
        _log_line(f"[avc] Dictation AI status: window geometry load failed: {exc}")
        return default_geometry


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
            _log_line(f"[avc] Dictation AI status: window geometry cache skipped: key={key} invalid_geometry={geometry}")
            return
        saved = dict(DEFAULT_WINDOW_GEOMETRY_META)
        try:
            saved.update(_read_legacy_window_geometry_meta(config_path))
        except Exception:
            pass
        try:
            saved.update(_read_window_geometry_file(config_path))
        except Exception:
            pass
        saved[key] = sanitized
        path = _write_window_geometry_file(config_path, saved)
        _log_line(f"[avc] Dictation AI status: window geometry cached: key={key} geometry={sanitized} path={path}")
    except Exception as exc:
        _log_line(f"[avc] Dictation AI status: window geometry cache failed: key={key} error={exc}")

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


def _pulse_source_kind(configured: str) -> str:
    value = str(configured).strip().lower()
    if value.endswith(".monitor"):
        return "monitor"
    if value.startswith("alsa_input.") or value == "ai-virtual-cam":
        return "source"
    return "runtime"


class WhisperTranscriptWorker:
    def __init__(self, config: DictationAiConfig, events: queue.Queue[TranscriptEvent]) -> None:
        self._cfg = config
        self._events = events
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[object] = queue.Queue(maxsize=INPUT_AUDIO_QUEUE_MAX_SIZE)
        self._capture_process: subprocess.Popen[bytes] | None = None
        self._capture_thread: threading.Thread | None = None
        self._audio_queue_drops = 0
        self._audio_queue_drop_lock = threading.Lock()
        self._sentence_boundary_backend = str(getattr(config, "sentenceBoundaryBackend", "sat")).strip() or "sat"
        self._sentence_boundary_model = getattr(config, "sentenceBoundaryModel", None)
        self._boundary_detector_language = str(getattr(config, "language", "en")).strip().lower()
        self._boundary_detector_backend = self._sentence_boundary_backend
        self._boundary_detector_model = self._sentence_boundary_model
        self._sentence_boundary_detector = None

    def _record_audio_queue_drop(self) -> int:
        with self._audio_queue_drop_lock:
            self._audio_queue_drops += 1
            return self._audio_queue_drops

    def _audio_queue_drop_count(self) -> int:
        with self._audio_queue_drop_lock:
            return self._audio_queue_drops

    def _stt_settings_for_language(self) -> tuple[str, str]:
        language = str(getattr(self._cfg, "language", "en")).strip().lower()
        suffix_by_language = {"en": "En", "ko": "Ko", "zh": "Zh"}
        suffix = suffix_by_language.get(language)
        if suffix is None:
            return str(self._cfg.backend).strip(), str(self._cfg.model).strip()
        backend = str(getattr(self._cfg, f"sttBackend{suffix}", self._cfg.backend)).strip()
        model = str(getattr(self._cfg, f"sttModel{suffix}", self._cfg.model)).strip()
        return backend or str(self._cfg.backend).strip(), model or str(self._cfg.model).strip()

    def _sentence_boundary_settings_for_language(self, detected_language: str) -> tuple[str, str | None]:
        del detected_language
        return self._sentence_boundary_backend, self._sentence_boundary_model

    def _preload_sentence_boundary_detector(self) -> None:
        language = str(getattr(self._cfg, "language", "en")).strip().lower()
        self._sync_sentence_boundary_detector(language)

    def _build_sentence_boundary_detector(self, detected_language: str) -> object:
        device = str(getattr(self._cfg, "sentenceBoundaryDevice", "cuda"))
        compute_type = str(getattr(self._cfg, "sentenceBoundaryComputeType", "float16"))
        backend, model = self._sentence_boundary_settings_for_language(detected_language)
        self._emit(
            "status",
            "STT 결과 문장 경계 처리 모델 로딩 중: "
            f"profile={getattr(self._cfg, 'postProcessingProfile', 'manual')} backend={backend} model={model} "
            f"device={device} compute={compute_type} language={detected_language}. "
            "Serve 실행 중 다운로드는 하지 않으며, 캐시에 없으면 실패합니다.",
            display=False,
        )
        detector = create_sentence_boundary_detector(
            backend,
            model=model,
            device=device,
            compute_type=compute_type,
            language=detected_language,
        )
        self._emit(
            "status",
            "STT 결과 문장 경계 처리 모델 로딩 완료: "
            f"profile={getattr(self._cfg, 'postProcessingProfile', 'manual')} backend={backend} model={model} "
            f"device={device} compute={compute_type} language={detected_language}",
            display=False,
        )
        self._boundary_detector_backend = backend
        self._boundary_detector_model = model
        return detector

    def _emit(
        self,
        kind: str,
        text: str,
        *,
        display: bool = True,
        log_text: str | None = None,
        final: bool = True,
        segment_id: int | None = None,
    ) -> None:
        _log_line(f"[avc] Dictation AI {kind}: {log_text if log_text is not None else text}")
        self._events.put(TranscriptEvent(kind, text, display, log_text, final, segment_id))

    def _sync_sentence_boundary_detector(self, detected_language: str) -> None:
        normalized = str(detected_language or "en").strip().lower()
        backend, model = self._sentence_boundary_settings_for_language(normalized)
        if self._sentence_boundary_detector is None:
            self._sentence_boundary_detector = self._build_sentence_boundary_detector(normalized)
            self._boundary_detector_language = normalized
            return
        if (
            self._boundary_detector_language == normalized
            and self._boundary_detector_backend == backend
            and self._boundary_detector_model == model
        ):
            return
        self._sentence_boundary_detector = self._build_sentence_boundary_detector(normalized)
        self._boundary_detector_language = normalized

    def _sentence_boundary_detector_for(self, detected_language: str):
        self._sync_sentence_boundary_detector(detected_language)
        return self._sentence_boundary_detector

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
            stt_backend, stt_model = self._stt_settings_for_language()
            if stt_backend == "mock":
                self._run_mock()
                return
            if self._cfg.translationEnabled and self._cfg.translationBackend == "whisper" and stt_backend != "faster-whisper":
                raise RuntimeError(
                    "dictationAi.translationBackend=whisper는 faster-whisper STT backend에서만 지원됩니다. "
                    f"현재 STT backend={stt_backend}. NLLB 번역을 사용하거나 언어별 STT backend를 faster-whisper로 변경하세요."
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

            self._emit(
                "status",
                "STT 서비스 대기: 사용 모델 다운로드/로딩이 끝나기 전까지 입력 캡처와 전사를 시작하지 않습니다.",
            )
            self._emit(
                "status",
                "STT 모델 로딩 중: "
                f"profile={getattr(self._cfg, 'postProcessingProfile', 'manual')} backend={stt_backend} model={stt_model} "
                f"device={self._cfg.device} compute={self._cfg.computeType} language={self._cfg.language}. "
                "Serve 실행 중 다운로드는 하지 않으며, 캐시에 없으면 실패합니다.",
            )
            try:
                model = build_stt_model(
                    backend=stt_backend,
                    model_name=stt_model,
                    device=self._cfg.device,
                    compute_type=self._cfg.computeType,
                    language=self._cfg.language,
                    status_callback=lambda message: self._emit("status", message, display=False),
                )
            except Exception as exc:
                raise RuntimeError(
                    "STT 모델 로딩 실패: "
                    f"backend={stt_backend} model={stt_model} device={self._cfg.device} "
                    f"computeType={self._cfg.computeType} language={self._cfg.language}. "
                    "Fail-Fast: 설정한 STT backend/model/device를 수정하세요. qwen3-asr-vllm-streaming은 공유 .venv에서 vLLM/mediapipe 의존성 충돌로 지원하지 않습니다. 현재는 qwen3-asr-transformers를 사용하세요. "
                    f"원인: {exc}"
                ) from exc
            self._emit("status", "STT 모델 로딩 완료")
            text_translator = None
            self._emit("status", "받아쓰기 AI 모델 준비 시작: 전사/번역은 모든 모델 로딩이 끝난 뒤 시작됩니다.")
            if self._cfg.translationEnabled:
                translation_status = (
                    "Whisper 백엔드 내장 영어 번역 창 사용"
                    if self._cfg.translationBackend == "whisper"
                    else "외부 텍스트 번역 창 사용"
                )
                self._emit(
                    "status",
                    f"{translation_status}: "
                    f"backend={self._cfg.translationBackend} target_language={self._cfg.translationTargetLanguage} "
                    f"model={self._cfg.translationModel} device={self._cfg.translationDevice} "
                    f"compute={self._cfg.translationComputeType} translation_beam={self._cfg.translationBeamSize} "
                    f"translation_max_tokens={self._cfg.translationMaxNewTokens}",
                )
                text_translator = build_text_translator(
                    self._cfg.translationBackend,
                    self._cfg.translationModel,
                    self._cfg.translationDevice,
                    self._cfg.translationComputeType,
                    self._cfg.translationBeamSize,
                    self._cfg.translationMaxNewTokens,
                )
            self._preload_sentence_boundary_detector()
            self._emit("status", "받아쓰기 AI 모델 준비 완료: 입력 캡처와 전사를 시작합니다.")
            self._emit("status", f"입력 장치 열기: {self._cfg.inputDevice}")

            if _is_exact_pulse_source(self._cfg.inputDevice):
                self._start_pulse_capture(np)
                self._emit(
                    "status",
                    "Pulse source 직접 캡처 시작: "
                    f"{self._cfg.inputDevice} kind={_pulse_source_kind(self._cfg.inputDevice)} "
                    f"latency_msec={PULSE_CAPTURE_LATENCY_MSEC}",
                )
                self._drain_startup_audio()
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
                    self._record_audio_queue_drop()
                    self._emit("status", "받아쓰기 AI 입력 버퍼가 가득 차 오디오 프레임을 건너뜁니다.")

            device = _sounddevice_device_name(self._cfg.inputDevice)
            self._emit("status", f"sounddevice 캡처 시작: runtime_device={device or 'default'}")
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=device,
                callback=callback,
            ):
                self._drain_startup_audio()
                self._emit("status", "받아쓰기 AI 전사 시작")
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
            "--latency-msec",
            str(PULSE_CAPTURE_LATENCY_MSEC),
            "--raw",
        ]
        self._emit("status", "Pulse recorder spawn: " + " ".join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._capture_process = process
        bytes_per_block = int(SAMPLE_RATE * PULSE_CAPTURE_BLOCK_SECONDS) * 2

        def read_loop() -> None:
            assert process.stdout is not None
            self._emit("status", f"Pulse recorder reader started: pid={process.pid}")
            while not self._stop.is_set() and process.poll() is None:
                data = process.stdout.read(bytes_per_block)
                if not data:
                    break
                try:
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    self._audio_queue.put(samples, timeout=INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS)
                except queue.Full:
                    self._record_audio_queue_drop()
                    self._emit("status", "받아쓰기 AI 입력 버퍼가 가득 차 Pulse 프레임을 건너뜁니다.")
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

    def _drain_startup_audio(self) -> None:
        deadline = time.monotonic() + STARTUP_AUDIO_DRAIN_SECONDS
        drained_blocks = 0
        drained_samples = 0
        while time.monotonic() < deadline and not self._stop.is_set():
            timeout = max(0.01, min(INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS, deadline - time.monotonic()))
            try:
                block = self._audio_queue.get(timeout=timeout)
            except queue.Empty:
                continue
            drained_blocks += 1
            try:
                drained_samples += int(block.shape[0])
            except Exception:
                pass
        while True:
            try:
                block = self._audio_queue.get_nowait()
            except queue.Empty:
                break
            drained_blocks += 1
            try:
                drained_samples += int(block.shape[0])
            except Exception:
                pass
        self._emit(
            "status",
            "받아쓰기 AI 시작 오디오 drain 완료: "
            f"seconds={STARTUP_AUDIO_DRAIN_SECONDS:.1f} blocks={drained_blocks} samples={drained_samples}",
            display=False,
        )

    def _transcribe_loop(self, model, np, text_translator=None) -> None:
        run_transcribe_loop(
            self,
            model,
            np,
            text_translator,
        )

    def _run_mock(self) -> None:
        self._emit("status", "받아쓰기 AI mock 출력 시작")
        index = 1
        while not self._stop.is_set():
            self._emit("transcript", f"[mock] sample transcript {index}", segment_id=index)
            if self._cfg.translationEnabled:
                self._emit(
                    "translation",
                    f"translated mock sample {index}",
                    log_text=f"[mock->{self._cfg.translationTargetLanguage}#{index}] translated mock sample {index}",
                    segment_id=index,
                )
            index += 1
            self._stop.wait(2.0)


class WhisperTranscriptWindow:
    def __init__(self, app_config: AppConfig, config_path: Path) -> None:
        if not app_config.dictationAi.enabled:
            raise RuntimeError("dictationAi.enabled=false 입니다. config에서 받아쓰기 AI 전사를 켠 뒤 serve를 실행하세요.")
        _require_linux_cuda_runtime(app_config.dictationAi)
        try:
            import tkinter as tk
            from tkinter import ttk
        except ModuleNotFoundError as exc:
            raise RuntimeError("Tkinter가 없습니다. 받아쓰기 AI 출력 창을 열 수 없습니다.") from exc

        self._tk = tk
        self._ttk = ttk
        self._config_path = config_path
        self._ui_language = _load_ui_language(config_path)
        self._whisper_config = app_config.dictationAi
        self._geometry_save_after_id: str | None = None
        self._translation_geometry_save_after_id: str | None = None
        self._stt_status_geometry_save_after_id: str | None = None
        self._translation_root = None
        self._translation_text = None
        self._stt_status_root = None
        self._stt_status_text = None
        self._line_number_widgets = {}
        self._line_number_labels = {}
        self._context_text = None
        self._transcript_partial_active = False
        self._translation_partial_active = False
        self._events: queue.Queue[TranscriptEvent] = queue.Queue()
        self._worker = WhisperTranscriptWorker(app_config.dictationAi, self._events)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._root = tk.Tk()
        self._root.title(dictation_window_title("transcript", self._ui_language))
        restored_geometry = _load_window_geometry(self._config_path, "dictationAiWindowGeometry", self._root)
        self._root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self._text = self._create_numbered_text(frame, 0)
        self._context_menu = tk.Menu(self._root, tearoff=False)
        self._context_menu.add_command(label="Copy", command=self._copy_selection)
        self._context_menu.add_command(label="Copy All", command=self._copy_all)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Clear", command=self._clear)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=lambda: self._copy_all(self._text))
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=lambda: self._clear(self._text))
        clear_btn.grid(row=0, column=2, sticky="e")

        if self._whisper_config.showSttStatusWindow:
            self._create_stt_status_window()

        if self._whisper_config.translationEnabled:
            self._create_translation_window()

        self._root.bind("<Configure>", self._on_configure)
        self._root.protocol("WM_DELETE_WINDOW", self._close)

    def _create_stt_status_window(self) -> None:
        tk = self._tk
        ttk = self._ttk
        self._stt_status_root = tk.Toplevel(self._root)
        self._stt_status_root.title(dictation_window_title("sttStatus", self._ui_language))
        restored_geometry = _load_window_geometry(
            self._config_path, "dictationAiSttStatusWindowGeometry", self._stt_status_root
        )
        self._stt_status_root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._stt_status_root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._stt_status_root.columnconfigure(0, weight=1)
        self._stt_status_root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._stt_status_root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self._stt_status_text = self._create_numbered_text(frame, 0)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(
            actions, text="Copy All", command=lambda: self._copy_all(self._stt_status_text)
        )
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(
            actions, text="Clear", command=lambda: self._clear(self._stt_status_text)
        )
        clear_btn.grid(row=0, column=2, sticky="e")

        self._stt_status_root.bind("<Configure>", self._on_stt_status_configure)
        self._stt_status_root.protocol("WM_DELETE_WINDOW", self._hide_stt_status_window)

    def _create_translation_window(self) -> None:
        tk = self._tk
        ttk = self._ttk
        self._translation_root = tk.Toplevel(self._root)
        self._translation_root.title(dictation_window_title("translation", self._ui_language))
        restored_geometry = _load_window_geometry(
            self._config_path, "dictationAiTranslationWindowGeometry", self._translation_root
        )
        self._translation_root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._translation_root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._translation_root.columnconfigure(0, weight=1)
        self._translation_root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._translation_root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self._translation_text = self._create_numbered_text(frame, 0)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=lambda: self._copy_all(self._translation_text))
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=lambda: self._clear(self._translation_text))
        clear_btn.grid(row=0, column=2, sticky="e")

        self._translation_root.bind("<Configure>", self._on_translation_configure)
        self._translation_root.protocol("WM_DELETE_WINDOW", self._hide_translation_window)

    def _create_numbered_text(self, parent, row: int):
        tk = self._tk
        ttk = self._ttk
        line_numbers = tk.Canvas(parent, width=self._line_number_width(1), highlightthickness=0, takefocus=False)
        line_numbers.grid(row=row, column=0, sticky="ns")
        text_widget = tk.Text(parent, wrap="word", undo=False)
        self._configure_transcript_text_tags(text_widget)
        text_widget.grid(row=row, column=1, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text_widget.yview)
        scrollbar.grid(row=row, column=2, sticky="ns")

        def yscroll(first: str, last: str) -> None:
            scrollbar.set(first, last)
            self._update_line_numbers(text_widget)

        text_widget.configure(yscrollcommand=yscroll)
        text_widget.bind("<Key>", self._on_text_key)
        text_widget.bind("<Button-3>", self._show_context_menu)
        text_widget.bind("<Control-Button-1>", self._show_context_menu)
        text_widget.bind("<Configure>", lambda _event: self._update_line_numbers(text_widget))
        self._configure_line_number_text(line_numbers)
        self._line_number_widgets[text_widget] = line_numbers
        self._line_number_labels[text_widget] = {}
        return text_widget

    def _configure_line_number_text(self, line_numbers) -> None:
        line_numbers.configure(background="#f0f0f0")

    def _line_number_width(self, max_line: int) -> int:
        digits = max(1, len(str(max_line)))
        return max(42, (digits * 9) + 16)

    def _line_number_x(self, max_line: int) -> int:
        return self._line_number_width(max_line) - 6

    def _line_number_display_width(self, text_widget, fallback_max_line: int) -> int:
        labels = getattr(self, "_line_number_labels", {}).get(text_widget, {})
        max_digits = max(
            [len(str(fallback_max_line))]
            + [len(str(label)) for label in labels.values() if str(label)]
        )
        return max(42, (max_digits * 9) + 16)

    def _line_number_display_x(self, width: int) -> int:
        return width - 6

    def _update_line_numbers(self, text_widget) -> None:
        line_numbers = getattr(self, "_line_number_widgets", {}).get(text_widget)
        if line_numbers is None:
            return
        line_numbers.delete("all")
        labels = getattr(self, "_line_number_labels", {}).get(text_widget, {})
        try:
            index = text_widget.index("@0,0")
            visible_lines: list[tuple[str, int]] = []
            while True:
                info = text_widget.dlineinfo(index)
                if info is None:
                    break
                line = index.split(".", 1)[0]
                visible_lines.append((line, info[1]))
                next_index = text_widget.index(f"{index}+1line")
                if next_index == index:
                    break
                index = next_index
            max_line = max((int(line) for line, _y in visible_lines), default=1)
            width = self._line_number_display_width(text_widget, max_line)
            line_numbers.configure(width=width)
            x = self._line_number_display_x(width)
            seen_lines: set[int] = set()
            for line, y in visible_lines:
                line_number = int(line)
                label = "" if line_number in seen_lines else str(labels.get(line_number, line))
                seen_lines.add(line_number)
                line_numbers.create_text(x, y, anchor="ne", text=label, fill="#777777")
        except Exception:
            content = text_widget.get("1.0", "end-1c")
            line_count = 0 if not content else content.count("\n") + 1
            width = self._line_number_display_width(text_widget, line_count)
            line_numbers.configure(width=width)
            x = self._line_number_display_x(width)
            for line in range(1, line_count + 1):
                label = str(labels.get(line, line))
                line_numbers.create_text(x, (line - 1) * 17, anchor="ne", text=label, fill="#777777")

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

    def _configure_transcript_text_tags(self, text_widget) -> None:
        text_widget.tag_configure(FINAL_TEXT_TAG, foreground=FINAL_TEXT_COLOR)
        text_widget.tag_configure(PARTIAL_TEXT_TAG, foreground=PARTIAL_TEXT_COLOR)
        text_widget.tag_configure(ERROR_TEXT_TAG, foreground=ERROR_TEXT_COLOR)

    def _append_stt_status_transcript(self, line: str) -> None:
        if self._stt_status_text is None:
            return
        self._append(line, self._stt_status_text, final=True)

    def _append(
        self,
        line: str,
        text_widget=None,
        *,
        final: bool = True,
        tag: str | None = None,
        line_label: str | None = None,
    ) -> None:
        target = text_widget if text_widget is not None else self._text
        partial_attr = None
        if target is self._text:
            partial_attr = "_transcript_partial_active"
        elif target is self._translation_text:
            partial_attr = "_translation_partial_active"
        elif target is self._stt_status_text:
            partial_attr = None
        if partial_attr is not None and getattr(self, partial_attr):
            target.delete("end-1c linestart", "end-1c")
        insert_line = int(target.index("end-1c linestart").split(".", 1)[0])
        if final:
            target.insert("end", f"{line}\n", tag or FINAL_TEXT_TAG)
            if line_label is not None:
                self._line_number_labels.setdefault(target, {})[insert_line] = str(line_label)
            if partial_attr is not None:
                setattr(self, partial_attr, False)
        else:
            target.insert("end", line, PARTIAL_TEXT_TAG)
            if partial_attr is not None:
                setattr(self, partial_attr, True)
        self._update_line_numbers(target)
        target.see("end")

    def _format_error_for_modal(self, message: str) -> str:
        prefix = "오류" if self._ui_language == "ko" else "Error"
        return f"{prefix}: {message}"

    def _poll_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event.kind == "transcript":
                if not event.final:
                    continue
            if event.kind == "stt_raw":
                if event.display:
                    self._append_stt_status_transcript(event.text)
                continue
            if not _is_modal_output_event(event):
                continue
            if event.kind == "translation" and self._translation_text is not None:
                line_label = str(event.segment_id) if event.segment_id is not None and event.final else None
                self._append(event.text, self._translation_text, final=event.final, line_label=line_label)
            elif event.kind == "error":
                self._append(self._format_error_for_modal(event.text), self._text, final=True, tag=ERROR_TEXT_TAG)
                if self._translation_text is not None:
                    self._append(self._format_error_for_modal(event.text), self._translation_text, final=True, tag=ERROR_TEXT_TAG)
            elif event.kind == "transcript":
                line_label = str(event.segment_id) if event.segment_id is not None and event.final else None
                self._append(event.text, self._text, final=event.final, line_label=line_label)
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

    def _on_stt_status_configure(self, event) -> None:
        if self._stt_status_root is None or event.widget != self._stt_status_root:
            return
        if self._stt_status_geometry_save_after_id is not None:
            try:
                self._stt_status_root.after_cancel(self._stt_status_geometry_save_after_id)
            except Exception:
                pass
        self._stt_status_geometry_save_after_id = self._stt_status_root.after(
            600, self._save_stt_status_geometry
        )

    def _current_geometry(self) -> str:
        try:
            self._root.update_idletasks()
        except Exception:
            pass
        return _window_manager_geometry(self._root)

    def _save_geometry(self) -> None:
        self._geometry_save_after_id = None
        _save_window_geometry(
            self._config_path,
            "dictationAiWindowGeometry",
            self._current_geometry(),
            *_window_restore_extent(self._root),
        )

    def _save_translation_geometry(self) -> None:
        self._translation_geometry_save_after_id = None
        if self._translation_root is None:
            return
        _save_window_geometry(
            self._config_path,
            "dictationAiTranslationWindowGeometry",
            _window_manager_geometry(self._translation_root),
            *_window_restore_extent(self._translation_root),
        )

    def _save_stt_status_geometry(self) -> None:
        self._stt_status_geometry_save_after_id = None
        if self._stt_status_root is None:
            return
        _save_window_geometry(
            self._config_path,
            "dictationAiSttStatusWindowGeometry",
            _window_manager_geometry(self._stt_status_root),
            *_window_restore_extent(self._stt_status_root),
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
        self._line_number_labels[target] = {}
        self._update_line_numbers(target)
        if target is self._text:
            self._transcript_partial_active = False
        elif target is self._translation_text:
            self._translation_partial_active = False

    def _hide_stt_status_window(self) -> None:
        if self._stt_status_root is not None:
            self._save_stt_status_geometry()
            self._stt_status_root.withdraw()

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
        if self._stt_status_geometry_save_after_id is not None and self._stt_status_root is not None:
            try:
                self._stt_status_root.after_cancel(self._stt_status_geometry_save_after_id)
            except Exception:
                pass
            self._stt_status_geometry_save_after_id = None
        self._save_geometry()
        self._save_translation_geometry()
        self._save_stt_status_geometry()
        self._worker.stop()
        if self._translation_root is not None:
            try:
                self._translation_root.destroy()
            except Exception:
                pass
        if self._stt_status_root is not None:
            try:
                self._stt_status_root.destroy()
            except Exception:
                pass
        self._root.after(100, self._root.destroy)


def main() -> int:
    log_path = install_rotating_stdout_log("avc-whisper")
    _log_line(f"[avc] Dictation AI rotating log file: {log_path}")
    args = parse_args()
    config_path = Path(args.config).expanduser()
    app_config = AppConfig.load(config_path)
    window = WhisperTranscriptWindow(app_config, config_path)
    return window.run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _log_line(f"[avc] Dictation AI window failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

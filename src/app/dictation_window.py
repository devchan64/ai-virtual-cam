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
from collections import deque
from dataclasses import dataclass
from pathlib import Path


from src.app.rotating_log import install_rotating_stdout_log
from src.app.sentence_boundary import create_sentence_boundary_detector
from src.app.stable_token_detection import analyze_stable_window, combine_boundary_confidence
from src.app.stt_model import build_stt_model
from src.app.translation_model import TranslationRequest, build_text_translator
from src.app.transcript_revision import append_context as _append_committed_text, consume_committed_prefix as _consume_committed_prefix, revision_lifecycle_context as _revision_lifecycle_context
from src.app.dictation_transcript_logic import (
    _diagnostic_tail,
    _final_sentence_diagnostic_flags,
    _new_text_delta,
    _next_revision_confirmation_count,
    _normalized_text,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _format_transcript_metrics,
    _is_cjk_text,
    _prefer_sentence_revision,
    _sentence_end_count,
    _sentence_max_age_chunks,
    _sentence_output_delta,
    _sentence_required_confirmations,
    _sentences_are_revisions,
    _replacement_decision_reason,
    _should_finalize_replaced_sentence,
    _should_confirm_staged_sentence,
    _should_age_staged_sentence,
    _should_finalize_before_replacement,
    _should_stage_boundary_candidate,
    _should_preserve_revision_confirmation_from_internal_stability,
    _revision_internal_stability_bucket,
    _is_recent_final_echo,
    _should_translate_final_sentence,
    _split_completed_sentences,
    _stable_window_text,
    _word_units,
)


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


SAMPLE_RATE = 16000
DEFAULT_CHUNK_SECONDS = float(dictation_ai_default("chunkSeconds"))
FINAL_TEXT_TAG = "final_text"
PARTIAL_TEXT_TAG = "partial_text"
ERROR_TEXT_TAG = "error_text"
FINAL_TEXT_COLOR = "black"
PARTIAL_TEXT_COLOR = "#008000"
ERROR_TEXT_COLOR = "#b00020"
MIN_SEGMENT_AVG_LOGPROB = -1.0
MAX_SEGMENT_NO_SPEECH_PROB = 0.75
MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB = 0.90
MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE = 12
RECENT_TRANSCRIPT_WINDOW = 8
MAX_RECENT_SHORT_TEXT_REPEATS = 2
_WINDOW_TITLES = {
    "en": {
        "transcript": "ai-virtual-cam Dictation AI Transcript",
        "translation": "ai-virtual-cam Dictation AI Translation",
        "sttStatus": "ai-virtual-cam Dictation AI STT Raw Transcript",
    },
    "ko": {
        "transcript": "ai-virtual-cam 받아쓰기 AI 전사",
        "translation": "ai-virtual-cam 받아쓰기 AI 번역",
        "sttStatus": "ai-virtual-cam 받아쓰기 AI STT 원문창",
    },
}
@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str
    display: bool = True
    log_text: str | None = None
    final: bool = True


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
    return language if language in _WINDOW_TITLES else "en"


def _window_title(kind: str, language: str) -> str:
    titles = _WINDOW_TITLES.get(language) or _WINDOW_TITLES["en"]
    return titles.get(kind, _WINDOW_TITLES["en"].get(kind, "ai-virtual-cam"))


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


def _is_modal_output_event(event: TranscriptEvent) -> bool:
    return event.display and event.kind in {"transcript", "translation", "error"}




class WhisperTranscriptWorker:
    def __init__(self, config: DictationAiConfig, events: queue.Queue[TranscriptEvent]) -> None:
        self._cfg = config
        self._events = events
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[object] = queue.Queue(maxsize=120)
        self._capture_process: subprocess.Popen[bytes] | None = None
        self._capture_thread: threading.Thread | None = None
        self._recent_transcripts: deque[str] = deque(maxlen=RECENT_TRANSCRIPT_WINDOW)
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
    ) -> None:
        _log_line(f"[avc] Dictation AI {kind}: {log_text if log_text is not None else text}")
        self._events.put(TranscriptEvent(kind, text, display, log_text, final))

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

    def _cjk_char_count(self, text: str) -> int:
        return sum(1 for char in str(text or "") if "\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff")

    def _should_accept_high_no_speech_segment(self, text: str, avg_logprob: float, no_speech_prob: float) -> bool:
        language = str(getattr(self._cfg, "language", "en") or "en").strip().lower()
        if language != "zh":
            return False
        if no_speech_prob >= MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB:
            return False
        if avg_logprob <= MIN_SEGMENT_AVG_LOGPROB:
            return False
        return self._cjk_char_count(text) >= MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE

    def _accepted_segment_texts(self, segments) -> tuple[list[str], list[str], float | None]:
        texts: list[str] = []
        accepted_scores: list[tuple[float, float]] = []
        rejected: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
            no_speech_prob = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
            if no_speech_prob >= MAX_SEGMENT_NO_SPEECH_PROB and not self._should_accept_high_no_speech_segment(
                text, avg_logprob, no_speech_prob
            ):
                rejected.append(f"no_speech text={text!r} prob={no_speech_prob:.2f}")
                continue
            if avg_logprob <= MIN_SEGMENT_AVG_LOGPROB:
                rejected.append(f"low_logprob text={text!r} avg_logprob={avg_logprob:.2f}")
                continue
            texts.append(text)
            accepted_scores.append((avg_logprob, no_speech_prob))
        if not accepted_scores:
            return texts, rejected, None

        avg_logprob = sum(score for score, _ in accepted_scores) / len(accepted_scores)
        avg_no_speech = sum(no_speech for _, no_speech in accepted_scores) / len(accepted_scores)
        # Convert model-native metrics to a boundary confidence score in [0,1].
        # - avg_logprob: higher is better, with -1.5 treated as near-zero and -0.1 near-one
        # - no_speech_prob: lower is better, 0..MAX_SEGMENT_NO_SPEECH_PROB
        logprob_score = max(0.0, min(1.0, (avg_logprob + 1.5) / 1.4))
        no_speech_score = max(0.0, min(1.0, 1.0 - (avg_no_speech / MAX_SEGMENT_NO_SPEECH_PROB)))
        confidence = 0.7 * logprob_score + 0.3 * no_speech_score
        return texts, rejected, confidence

    def _is_repeated_hallucination(self, text: str) -> bool:
        normalized = " ".join(text.split())
        if not normalized:
            return False
        repeats = sum(1 for item in self._recent_transcripts if item == normalized)
        return len(normalized) <= 24 and repeats >= MAX_RECENT_SHORT_TEXT_REPEATS

    def _remember_transcript(self, text: str) -> None:
        normalized = " ".join(text.split())
        if normalized:
            self._recent_transcripts.append(normalized)

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

    def _transcribe_loop(self, model, np, text_translator=None) -> None:
        audio_blocks: deque[object] = deque()
        buffered = 0
        pending_step = 0
        step_seconds = float(self._cfg.stepSeconds)
        window_seconds = float(self._cfg.windowSeconds)
        sentence_finalize_age = int(getattr(self._cfg, "sentenceFinalizeAge", 3))
        step_samples = int(SAMPLE_RATE * step_seconds)
        window_samples = int(SAMPLE_RATE * window_seconds)
        language = self._cfg.language
        chunks = 0
        translation_failed = False
        committed_text = ""
        committed_translation_text = ""
        pending_transcript_text = ""
        pending_chunks = 0
        staged_sentence = ""
        staged_confirmations = 0
        staged_age = 0
        staged_forced = False
        staged_deferred_age_chunk = -1
        previous_window_text = ""
        lifecycle_metrics: dict[str, int] = {}
        chunk_lifecycle_metrics: dict[str, int] = {}
        last_audio_queue_drops = self._audio_queue_drop_count()

        def count_metric(name: str, amount: int = 1) -> None:
            lifecycle_metrics[name] = lifecycle_metrics.get(name, 0) + amount
            chunk_lifecycle_metrics[name] = chunk_lifecycle_metrics.get(name, 0) + amount

        def count_segment_state(state: str, amount: int = 1) -> None:
            count_metric(f"segment_state_{state}", amount)

        self._emit(
            "status",
            f"받아쓰기 AI 전사 루프 시작: step_seconds={step_seconds} window_seconds={window_seconds} "
            f"language={self._cfg.language} "
            f"stt_backend={self._stt_settings_for_language()[0]} stt_model={self._stt_settings_for_language()[1]} "
            f"translation_enabled={self._cfg.translationEnabled} "
            f"translation_backend={self._cfg.translationBackend} "
            f"translation_target={self._cfg.translationTargetLanguage} beam_size={self._cfg.beamSize} "
            f"max_new_tokens={self._cfg.maxNewTokens} temperature={self._cfg.temperature} "
            f"sentence_finalize_age={sentence_finalize_age} "
            f"without_timestamps=True translation_beam_size={self._cfg.translationBeamSize} "
            f"translation_max_new_tokens={self._cfg.translationMaxNewTokens}",
        )

        def trim_audio_window() -> None:
            nonlocal buffered
            while buffered > window_samples and audio_blocks:
                excess = buffered - window_samples
                oldest = audio_blocks[0]
                oldest_len = int(oldest.shape[0])
                if oldest_len <= excess:
                    audio_blocks.popleft()
                    buffered -= oldest_len
                    continue
                audio_blocks[0] = oldest[excess:]
                buffered -= excess
                break

        def finalize_staged_sentence(detected: str, reason: str) -> list[str]:
            nonlocal committed_text, staged_sentence, staged_confirmations, staged_age, staged_forced, staged_deferred_age_chunk
            if not staged_sentence:
                return []
            count_metric("finalize_attempt")
            count_metric(f"finalize_reason_{reason}")
            output_sentence = _sentence_output_delta(committed_text, staged_sentence)
            staged_before = staged_sentence
            committed_before_chars = len(_normalized_text(committed_text))
            staged_sentence = ""
            staged_confirmations = 0
            staged_age = 0
            staged_forced = False
            staged_deferred_age_chunk = -1
            if not output_sentence:
                count_metric("finalize_duplicate_suppressed")
                count_segment_state("suppressed")
                self._emit(
                    "status",
                    f"받아쓰기 AI 확정 후보 중복 무시: chunk={chunks} reason={reason} text={staged_before!r}",
                    display=False,
                )
                return []
            echo_source = next(
                (
                    recent
                    for recent in reversed(self._recent_transcripts)
                    if _is_recent_final_echo(output_sentence, recent, detected)
                ),
                None,
            )
            if echo_source is not None:
                count_metric("finalize_recent_echo_suppressed")
                count_segment_state("suppressed")
                self._emit(
                    "status",
                    "받아쓰기 AI 확정 후보 유사 대안 무시: "
                    f"chunk={chunks} reason={reason} text={output_sentence!r} recent={echo_source!r}",
                    display=False,
                )
                return []
            count_metric("finalized")
            count_segment_state("final")
            final_quality_flags = _final_sentence_diagnostic_flags(output_sentence, detected)
            for flag in final_quality_flags:
                count_metric(f"final_quality_{flag}")
            committed_text = _append_committed_text(committed_text, output_sentence)
            self._remember_transcript(output_sentence)
            self._emit(
                "status",
                "받아쓰기 AI 문장 확정: "
                f"chunk={chunks} reason={reason} committed_before_chars={committed_before_chars} "
                f"output_chars={len(_normalized_text(output_sentence))} "
                f"quality_flags={','.join(final_quality_flags) or 'none'} "
                f"staged_tail={_diagnostic_tail(staged_before)} text={output_sentence!r}",
                display=False,
            )
            self._emit("transcript", output_sentence, log_text=f"[{detected}] {output_sentence}", final=True)
            return [output_sentence]

        def stage_completed_sentence(sentence: str, detected: str, *, forced: bool = False) -> list[str]:
            nonlocal staged_sentence, staged_confirmations, staged_age, staged_forced, staged_deferred_age_chunk
            normalized_sentence = _normalized_text(sentence)
            candidate = _sentence_output_delta(committed_text, sentence)
            if candidate and candidate != normalized_sentence:
                count_metric("candidate_delta_trimmed")
                if _is_cjk_text(normalized_sentence):
                    count_metric("candidate_delta_trimmed_cjk")
            if not candidate:
                count_metric("candidate_duplicate_suppressed")
                count_segment_state("suppressed")
                self._emit("status", f"받아쓰기 AI 중복 문장 무시: chunk={chunks} text={sentence!r}", display=False)
                return []
            if not _should_stage_boundary_candidate(candidate, detected):
                count_metric("stage_candidate_quality_blocked")
                count_segment_state("suppressed")
                candidate_quality_flags = _final_sentence_diagnostic_flags(candidate, detected)
                for flag in candidate_quality_flags:
                    count_metric(f"stage_candidate_quality_{flag}")
                self._emit(
                    "status",
                    "받아쓰기 AI stage 후보 품질 차단: "
                    f"chunk={chunks} flags={','.join(candidate_quality_flags) or 'none'} "
                    f"candidate_tail={_diagnostic_tail(candidate)}",
                    display=False,
                )
                return []
            if not staged_sentence:
                count_metric("stage_start")
                count_segment_state("staged")
                staged_sentence = candidate
                staged_confirmations = 1
                staged_age = 0
                staged_forced = forced
                self._emit(
                    "status",
                    "받아쓰기 AI stage 시작: "
                    f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                    f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                    display=False,
                )
                self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                return []
            is_revision = _sentences_are_revisions(staged_sentence, candidate)
            if is_revision:
                count_metric("stage_revision")
                count_segment_state("revised")
                staged_before = staged_sentence
                preferred = _prefer_sentence_revision(staged_sentence, candidate)
                preferred_changed = preferred != staged_before
                if preferred_changed:
                    count_metric("stage_revision_changed")
                    if _is_cjk_text(staged_before) or _is_cjk_text(preferred):
                        count_metric(
                            "stage_revision_internal_stability_"
                            + _revision_internal_stability_bucket(
                                stable_analysis.stable_internal_ratio,
                                stable_analysis.stable_internal_chars,
                            )
                        )
                        if _should_preserve_revision_confirmation_from_internal_stability(
                            staged_before,
                            preferred,
                            stable_analysis.stable_internal_ratio,
                            stable_analysis.stable_internal_chars,
                            stable_analysis.stable_overlap_source,
                        ):
                            count_metric("stage_revision_confirmation_preserved_internal")
                        else:
                            count_metric("stage_revision_confirmation_reset")
                else:
                    candidate_flags = set(_final_sentence_diagnostic_flags(candidate, detected))
                    staged_flags = set(_final_sentence_diagnostic_flags(staged_before, detected))
                    if "cjk_repeated_ngram" in candidate_flags and "cjk_repeated_ngram" not in staged_flags:
                        count_metric("stage_revision_candidate_quality_blocked")
                staged_sentence = preferred
                staged_confirmations = _next_revision_confirmation_count(
                    staged_before,
                    preferred,
                    staged_confirmations,
                    stable_analysis.stable_internal_ratio,
                    stable_analysis.stable_internal_chars,
                    stable_analysis.stable_overlap_source,
                )
                staged_age += 1
                count_metric("stage_age_tick")
                staged_forced = staged_forced or forced
                required_confirmations = _sentence_required_confirmations(staged_forced)
                self._emit(
                    "status",
                    "받아쓰기 AI stage 리비전: "
                    f"chunk={chunks} confirmations={staged_confirmations}/{required_confirmations} "
                    f"staged_age={staged_age} "
                    f"forced={staged_forced} preferred_changed={preferred_changed} "
                    f"staged_before={_diagnostic_tail(staged_before)} candidate={_diagnostic_tail(candidate)} "
                    f"preferred={_diagnostic_tail(preferred)}",
                    display=False,
                )
                if _should_confirm_staged_sentence(
                    staged_sentence,
                    staged_confirmations,
                    staged_forced,
                ):
                    return finalize_staged_sentence(detected, "confirmed_forced" if staged_forced else "confirmed")
                if _should_finalize_before_replacement(
                    staged_sentence,
                    detected,
                    staged_confirmations,
                    staged_age,
                    sentence_finalize_age,
                    staged_forced,
                ):
                    max_age = _sentence_max_age_chunks(staged_forced, sentence_finalize_age)
                    if staged_age >= max_age:
                        count_metric("stage_age_finalize")
                        reason = "aged_forced" if staged_forced else "aged"
                    else:
                        count_metric("stage_finalize_before_replace")
                        reason = "next_completed"
                    return finalize_staged_sentence(detected, reason)
                self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                return []
            count_metric("stage_replace")
            replacement_reason = _replacement_decision_reason(
                staged_sentence,
                candidate,
                staged_confirmations,
                staged_forced,
                staged_age,
                sentence_finalize_age,
            )
            count_metric(f"stage_replace_decision_{replacement_reason}")
            if replacement_reason == "unconfirmed_cjk":
                count_metric("stage_replace_deferred")
                if staged_deferred_age_chunk != chunks:
                    staged_age += 1
                    staged_deferred_age_chunk = chunks
                    count_metric("stage_age_tick")
                self._emit(
                    "status",
                    "받아쓰기 AI stage 교체 보류: "
                    f"chunk={chunks} decision={replacement_reason} staged_confirmations={staged_confirmations} "
                    f"staged_age={staged_age} staged_tail={_diagnostic_tail(staged_sentence)} "
                    f"candidate_tail={_diagnostic_tail(candidate)}",
                    display=False,
                )
                if _should_finalize_before_replacement(
                    staged_sentence,
                    detected,
                    staged_confirmations,
                    staged_age,
                    sentence_finalize_age,
                    staged_forced,
                ):
                    count_metric("stage_age_finalize")
                    return finalize_staged_sentence(detected, "aged")
                return []
            self._emit(
                "status",
                "받아쓰기 AI stage 교체: "
                f"chunk={chunks} reason=revision_false decision={replacement_reason} forced={forced} "
                f"staged_confirmations={staged_confirmations} staged_age={staged_age} "
                f"staged_tail={_diagnostic_tail(staged_sentence)} candidate_tail={_diagnostic_tail(candidate)}",
                display=False,
            )
            if _should_finalize_replaced_sentence(
                staged_sentence,
                candidate,
                staged_confirmations,
                staged_forced,
                staged_age,
                sentence_finalize_age,
            ):
                finalized = finalize_staged_sentence(detected, f"replaced_{replacement_reason}")
            elif _should_finalize_before_replacement(
                staged_sentence,
                detected,
                staged_confirmations,
                staged_age,
                sentence_finalize_age,
                staged_forced,
            ):
                count_metric("stage_finalize_before_replace")
                finalized = finalize_staged_sentence(detected, "next_completed")
            else:
                count_metric("stage_replaced_unconfirmed")
                count_segment_state("suppressed")
                required_confirmations = _sentence_required_confirmations(staged_forced)
                self._emit(
                    "status",
                    "받아쓰기 AI stage 미확정 교체: "
                    f"chunk={chunks} decision={replacement_reason} "
                    f"staged_confirmations={staged_confirmations} required={required_confirmations} "
                    f"staged_forced={staged_forced} staged_tail={_diagnostic_tail(staged_sentence)} "
                    f"candidate_tail={_diagnostic_tail(candidate)}",
                    display=False,
                )
                finalized = []
                staged_sentence = ""
                staged_confirmations = 0
                staged_age = 0
                staged_forced = False
                staged_deferred_age_chunk = -1
            count_metric("stage_start")
            count_segment_state("staged")
            staged_sentence = candidate
            staged_confirmations = 1
            staged_age = 0
            staged_forced = forced
            staged_deferred_age_chunk = -1
            self._emit(
                "status",
                "받아쓰기 AI stage 시작: "
                    f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                    f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                    display=False,
                )
            self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
            return finalized

        def age_staged_sentence(detected: str, pending_text: str = "") -> list[str]:
            nonlocal staged_sentence, staged_confirmations, staged_age, staged_forced
            if not staged_sentence:
                return []
            if not _should_age_staged_sentence(staged_sentence, pending_text):
                count_metric("stage_age_hold")
                staged_age = 0
                self._emit(
                    "status",
                    "받아쓰기 AI staged aging 보류: "
                    f"chunk={chunks} staged={staged_sentence!r} pending={pending_text!r}",
                    display=False,
                )
                return []
            staged_age += 1
            count_metric("stage_age_tick")
            max_age = _sentence_max_age_chunks(staged_forced, sentence_finalize_age)
            if staged_age >= max_age:
                if not _should_finalize_before_replacement(
                    staged_sentence,
                    detected,
                    staged_confirmations,
                    staged_age,
                    sentence_finalize_age,
                    staged_forced,
                ):
                    count_metric("stage_age_quality_blocked")
                    count_segment_state("suppressed")
                    flags = _final_sentence_diagnostic_flags(staged_sentence, detected)
                    self._emit(
                        "status",
                        "받아쓰기 AI staged age 확정 차단: "
                        f"chunk={chunks} flags={','.join(flags) or 'none'} "
                        f"staged_tail={_diagnostic_tail(staged_sentence)}",
                        display=False,
                    )
                    staged_sentence = ""
                    staged_confirmations = 0
                    staged_age = 0
                    staged_forced = False
                    return []
                count_metric("stage_age_finalize")
                return finalize_staged_sentence(detected, "aged_forced" if staged_forced else "aged")
            return []

        while not self._stop.is_set():
            try:
                block = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            audio_blocks.append(block)
            block_len = int(block.shape[0])
            buffered += block_len
            pending_step += block_len
            trim_audio_window()
            if buffered < window_samples or pending_step < step_samples:
                continue
            pending_step = 0

            chunks += 1
            chunk_lifecycle_metrics.clear()
            self._emit("status", f"받아쓰기 AI 전사 요청: chunk={chunks} samples={buffered}", display=False)
            audio = np.concatenate(list(audio_blocks)).astype(np.float32, copy=False)
            chunk_audio_seconds = float(audio.shape[0]) / float(SAMPLE_RATE)
            chunk_started_at = time.perf_counter()
            translation_elapsed = 0.0
            translation_attempted = False
            translation_started_at = chunk_started_at
            text = ""
            try:
                stt_started_at = time.perf_counter()
                transcribe_kwargs = {
                    "language": language,
                    "task": "transcribe",
                    "beam_size": self._cfg.beamSize,
                    "temperature": self._cfg.temperature,
                    "max_new_tokens": self._cfg.maxNewTokens,
                    "without_timestamps": True,
                    "condition_on_previous_text": False,
                }
                if getattr(model, "streaming", False):
                    transcribe_kwargs["stream_audio"] = block.astype(np.float32, copy=False)
                    transcribe_kwargs["stream_chunk_seconds"] = self._cfg.stepSeconds
                    transcribe_kwargs["stream_context_seconds"] = self._cfg.windowSeconds
                segments, info = model.transcribe(audio, **transcribe_kwargs)
                segment_list = list(segments)
                accepted_texts, rejected_reasons, boundary_confidence = self._accepted_segment_texts(segment_list)
                raw_window_text = " ".join(accepted_texts).strip()
                if raw_window_text:
                    self._emit(
                        "stt_raw",
                        raw_window_text,
                        log_text=f"[{language} raw] {raw_window_text}",
                        final=True,
                    )
                window_text = _normalized_text(raw_window_text)
                stable_text = _stable_window_text(window_text, 0.0, window_seconds)
                stable_analysis = analyze_stable_window(previous_window_text, window_text, language)
                previous_window_text = window_text
                if stable_analysis.current_units:
                    count_metric("stable_window_observed")
                    count_metric("stable_prefix_chars", stable_analysis.stable_prefix_chars)
                    count_metric("unstable_tail_chars", stable_analysis.unstable_tail_chars)
                    count_metric("stable_internal_chars", stable_analysis.stable_internal_chars)
                    count_metric(
                        "stable_internal_ratio_per_1000",
                        int(round(stable_analysis.stable_internal_ratio * 1000)),
                    )
                    count_metric("stable_token_ratio_per_1000", int(round(stable_analysis.stable_token_ratio * 1000)))
                    count_metric(f"stable_overlap_source_{stable_analysis.stable_overlap_source}")
                adjusted_boundary_confidence = combine_boundary_confidence(
                    boundary_confidence,
                    stable_analysis.boundary_confidence,
                )
                delta_base_text = _append_committed_text(committed_text, pending_transcript_text)
                text = _new_text_delta(delta_base_text, stable_text)
                stt_elapsed = time.perf_counter() - stt_started_at
                detected = getattr(info, "language", self._cfg.language)
                self._sync_sentence_boundary_detector(str(detected))
                if rejected_reasons:
                    self._emit(
                        "status",
                        f"받아쓰기 AI 전사 후보 무시: chunk={chunks} reasons={'; '.join(rejected_reasons)}",
                        display=False,
                    )
                completed_sentences: list[str] = []
                final_sentences: list[str] = []
                boundary_complete = 0
                boundary_soft = 0
                boundary_end_marks = 0
                boundary_right_context_starts = 0
                boundary_confidence_display = (
                    f"{adjusted_boundary_confidence:.2f}" if adjusted_boundary_confidence is not None else "n/a"
                )
                if text and self._is_repeated_hallucination(text):
                    count_segment_state("suppressed")
                    self._emit("status", f"받아쓰기 AI 반복 전사 무시: chunk={chunks} text={text!r}", display=False)
                    text = ""
                if text:
                    boundary_result = self._sentence_boundary_detector.split(
                        pending_transcript_text,
                        text,
                        detected,
                        boundary_confidence=adjusted_boundary_confidence,
                    )
                    completed_sentences = []
                    for sentence in boundary_result.completed:
                        completed_sentences.append(_normalized_text(sentence))
                    pending_transcript_text = _normalized_text(boundary_result.pending)
                    boundary_complete = boundary_result.boundary_count
                    boundary_soft = boundary_result.soft_boundary_count
                    boundary_end_marks = boundary_result.end_mark_count
                    boundary_right_context_starts = boundary_result.right_context_start_count
                    if boundary_end_marks:
                        count_metric("boundary_end_marks", boundary_end_marks)
                    if boundary_right_context_starts:
                        count_metric("boundary_right_context_starts", boundary_right_context_starts)
                    if completed_sentences:
                        pending_chunks = 0
                    elif pending_transcript_text:
                        pending_chunks += 1
                    for sentence in completed_sentences:
                        produced_sentences = stage_completed_sentence(sentence, detected)
                        final_sentences.extend(produced_sentences)
                        for produced_sentence in produced_sentences:
                            pending_transcript_text = _consume_committed_prefix(pending_transcript_text, produced_sentence)
                            if not pending_transcript_text:
                                pending_chunks = 0
                    if pending_transcript_text:
                        count_segment_state("pending")
                        self._emit(
                            "status",
                            "받아쓰기 AI pending tail: "
                            f"chunk={chunks} language={detected} text={pending_transcript_text!r}",
                            display=False,
                        )
                    elif not completed_sentences:
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                else:
                    preview_chars = max(0, len(_normalized_text(window_text)) - len(_normalized_text(stable_text)))
                    self._emit(
                        "status",
                        f"받아쓰기 AI 전사 결과 없음: chunk={chunks} preview_chars={preview_chars}",
                        display=False,
                    )
                    if pending_transcript_text:
                        count_segment_state("pending")
                        pending_chunks += 1
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                    else:
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                pending_overrun_reason = _pending_overrun_reason(pending_transcript_text, pending_chunks)
                if pending_overrun_reason:
                    count_metric("pending_overrun")
                    count_metric(f"pending_overrun_reason_{pending_overrun_reason}")
                pending_quality_flags = _pending_text_diagnostic_flags(pending_transcript_text, detected, pending_chunks)
                for flag in pending_quality_flags:
                    count_metric(f"pending_quality_{flag}")
                self._emit(
                    "status",
                    "받아쓰기 AI 문장 진단: "
                    f"chunk={chunks} completed={len(completed_sentences)} final={len(final_sentences)} "
                    f"pending_overrun={pending_overrun_reason or 'none'} "
                    f"pending_quality={','.join(pending_quality_flags) or 'none'} "
                    f"boundary_backend={self._sentence_boundary_detector.backend} "
                    f"boundary_complete={boundary_complete} boundary_soft={boundary_soft} boundary_conf={boundary_confidence_display} "
                    f"boundary_end_marks={boundary_end_marks} boundary_right_context={boundary_right_context_starts} "
                    f"boundary_conf_segment={boundary_confidence if boundary_confidence is not None else 'n/a'} "
                    f"boundary_conf_stable={stable_analysis.boundary_confidence if stable_analysis.boundary_confidence is not None else 'n/a'} "
                    f"pending_chars={len(pending_transcript_text)} pending_chunks={pending_chunks} "
                    f"pending_chars_per_chunk={len(pending_transcript_text) / max(pending_chunks, 1):.1f} "
                    f"window_chars={len(_normalized_text(window_text))} stable_chars={len(_normalized_text(stable_text))} "
                    f"stable_prefix_chars={stable_analysis.stable_prefix_chars} "
                    f"unstable_tail_chars={stable_analysis.unstable_tail_chars} "
                    f"stable_internal_chars={stable_analysis.stable_internal_chars} "
                    f"stable_internal_ratio={stable_analysis.stable_internal_ratio:.3f} "
                    f"stable_token_ratio={stable_analysis.stable_token_ratio:.3f} "
                    f"stable_overlap_source={stable_analysis.stable_overlap_source} "
                    f"delta_chars={len(_normalized_text(text))} "
                    f"end_marks_window={_sentence_end_count(window_text)} end_marks_stable={_sentence_end_count(stable_text)} "
                    f"end_marks_delta={_sentence_end_count(text)} "
                    f"stable_tail={_diagnostic_tail(stable_text)} delta_tail={_diagnostic_tail(text)} "
                    f"pending_tail={_diagnostic_tail(pending_transcript_text)} "
                    f"revision_context_chars={len(_normalized_text(_revision_lifecycle_context(committed_text, staged_sentence, pending_transcript_text)))} "
                    f"chunk_metrics={_format_transcript_metrics(chunk_lifecycle_metrics)} "
                    f"lifecycle_metrics={_format_transcript_metrics(lifecycle_metrics)} "
                    f"staged_confirmations={staged_confirmations} staged_age={staged_age} staged_forced={staged_forced} "
                    f"staged_tail={_diagnostic_tail(staged_sentence)}",
                    display=False,
                )
                translation_jobs: list[str] = []
                for sentence in final_sentences:
                    if _should_translate_final_sentence(sentence, detected):
                        translation_jobs.append(sentence)
                    else:
                        count_metric("translation_skip_final_quality")
                        self._emit(
                            "status",
                            "받아쓰기 AI 번역 생략: "
                            f"chunk={chunks} reason=final_quality flags={','.join(_final_sentence_diagnostic_flags(sentence, detected))} "
                            f"text={sentence!r}",
                            display=False,
                        )
                if self._cfg.translationEnabled and not translation_failed and translation_jobs:
                    try:
                        translation_attempted = True
                        request_label = "Whisper 백엔드 내장 번역 요청" if text_translator is None else "외부 텍스트 번역 요청"
                        target_language = self._cfg.translationTargetLanguage
                        source_language = detected if detected in {"ko", "en", "zh"} else self._cfg.language
                        for sentence in translation_jobs:
                            translation_started_at = time.perf_counter()
                            self._emit("status", f"{request_label}: chunk={chunks} final=True", display=False)
                            translated_text = ""
                            if text_translator is None:
                                translated_segments, _translated_info = model.transcribe(
                                    audio,
                                    language=language,
                                    task="translate",
                                                    beam_size=self._cfg.beamSize,
                                    temperature=self._cfg.temperature,
                                    max_new_tokens=self._cfg.maxNewTokens,
                                    without_timestamps=True,
                                    condition_on_previous_text=False,
                                )
                                translated_window_text = " ".join(
                                    segment.text.strip() for segment in translated_segments if segment.text.strip()
                                ).strip()
                                translated_stable_text = _stable_window_text(
                                    translated_window_text,
                                    0.0,
                                    window_seconds,
                                )
                                translated_text = _new_text_delta(committed_translation_text, translated_stable_text)
                                target_language = "en"
                            else:
                                translated_text = text_translator.translate(
                                    TranslationRequest(
                                        text=sentence,
                                        source_language=source_language,
                                        target_language=target_language,
                                    )
                                )
                            translation_elapsed += time.perf_counter() - translation_started_at
                            if translated_text:
                                self._emit(
                                    "status",
                                    "받아쓰기 AI 번역 진단: "
                                    f"chunk={chunks} final=True "
                                    f"source_lang={source_language} target_lang={target_language} "
                                    f"source_chars={len(_normalized_text(sentence))} "
                                    f"target_chars={len(_normalized_text(translated_text))} "
                                    f"backend={self._cfg.translationBackend} model={self._cfg.translationModel}",
                                    display=False,
                                )
                                committed_translation_text = _append_committed_text(committed_translation_text, translated_text)
                                self._emit(
                                    "translation",
                                    translated_text,
                                    log_text=f"[{detected}->{target_language}] {translated_text}",
                                    final=True,
                                )
                            else:
                                self._emit("status", f"받아쓰기 AI 번역 결과 없음: chunk={chunks}", display=False)
                    except Exception as exc:
                        translation_elapsed = time.perf_counter() - translation_started_at if translation_attempted else 0.0
                        translation_failed = True
                        self._emit(
                            "error",
                            "받아쓰기 AI 번역 실패: "
                            f"{exc}. 번역을 이번 세션에서 중지합니다. STT 전사는 계속됩니다.",
                        )
                total_elapsed = time.perf_counter() - chunk_started_at
                current_audio_queue_drops = self._audio_queue_drop_count()
                chunk_audio_queue_drops = current_audio_queue_drops - last_audio_queue_drops
                last_audio_queue_drops = current_audio_queue_drops
                current_queue_size = self._audio_queue.qsize()
                chunk_lifecycle_metrics["input_queue_size_peak"] = max(
                    chunk_lifecycle_metrics.get("input_queue_size_peak", 0),
                    current_queue_size,
                )
                lifecycle_metrics["input_queue_size_peak"] = max(
                    lifecycle_metrics.get("input_queue_size_peak", 0),
                    current_queue_size,
                )
                if current_queue_size >= max(5, int(round(window_seconds / max(step_seconds, 0.001)))):
                    count_metric("input_queue_backlog_chunk")
                if chunk_audio_queue_drops:
                    chunk_lifecycle_metrics["input_queue_drops"] = chunk_audio_queue_drops
                    lifecycle_metrics["input_queue_drops"] = lifecycle_metrics.get("input_queue_drops", 0) + chunk_audio_queue_drops
                stage_decision_count = sum(
                    value for key, value in chunk_lifecycle_metrics.items() if key.startswith("stage_replace_decision_")
                )
                stage_replace_count = chunk_lifecycle_metrics.get("stage_replace", 0)
                stage_replaced_unconfirmed_count = chunk_lifecycle_metrics.get("stage_replaced_unconfirmed", 0)
                stage_revision_count = chunk_lifecycle_metrics.get("stage_revision", 0)
                stage_revision_changed_count = chunk_lifecycle_metrics.get("stage_revision_changed", 0)
                stage_revision_reset_count = chunk_lifecycle_metrics.get("stage_revision_confirmation_reset", 0)
                stage_revision_preserved_internal_count = chunk_lifecycle_metrics.get(
                    "stage_revision_confirmation_preserved_internal",
                    0,
                )
                stage_revision_internal_high_count = chunk_lifecycle_metrics.get(
                    "stage_revision_internal_stability_high",
                    0,
                )
                stage_revision_internal_mid_count = chunk_lifecycle_metrics.get(
                    "stage_revision_internal_stability_mid",
                    0,
                )
                stage_revision_internal_low_count = chunk_lifecycle_metrics.get(
                    "stage_revision_internal_stability_low",
                    0,
                )
                stage_finalize_before_replace_count = chunk_lifecycle_metrics.get("stage_finalize_before_replace", 0)
                stage_age_finalize_count = chunk_lifecycle_metrics.get("stage_age_finalize", 0)
                stage_age_quality_blocked_count = chunk_lifecycle_metrics.get("stage_age_quality_blocked", 0)
                stage_start_count = chunk_lifecycle_metrics.get("stage_start", 0)
                finalize_count = chunk_lifecycle_metrics.get("finalized", 0)
                duplicate_suppressed_count = chunk_lifecycle_metrics.get("candidate_duplicate_suppressed", 0)
                recent_echo_suppressed_count = chunk_lifecycle_metrics.get("finalize_recent_echo_suppressed", 0)
                delta_trimmed_count = chunk_lifecycle_metrics.get("candidate_delta_trimmed", 0)
                stable_prefix_chars = chunk_lifecycle_metrics.get("stable_prefix_chars", 0)
                unstable_tail_chars = chunk_lifecycle_metrics.get("unstable_tail_chars", 0)
                stable_internal_chars = chunk_lifecycle_metrics.get("stable_internal_chars", 0)
                stable_internal_ratio_per_1000 = chunk_lifecycle_metrics.get("stable_internal_ratio_per_1000", 0)
                stable_token_ratio_per_1000 = chunk_lifecycle_metrics.get("stable_token_ratio_per_1000", 0)
                stage_candidate_quality_blocked_count = chunk_lifecycle_metrics.get("stage_candidate_quality_blocked", 0)
                stage_candidate_quality_count = sum(
                    value
                    for key, value in chunk_lifecycle_metrics.items()
                    if key.startswith("stage_candidate_quality_") and key != "stage_candidate_quality_blocked"
                )
                stage_candidate_quality_cjk_internal_gap_count = chunk_lifecycle_metrics.get(
                    "stage_candidate_quality_cjk_internal_gap",
                    0,
                )
                stage_candidate_quality_mixed_latin_count = chunk_lifecycle_metrics.get(
                    "stage_candidate_quality_mixed_latin_zh",
                    0,
                )
                segment_state_pending_count = chunk_lifecycle_metrics.get("segment_state_pending", 0)
                segment_state_staged_count = chunk_lifecycle_metrics.get("segment_state_staged", 0)
                segment_state_final_count = chunk_lifecycle_metrics.get("segment_state_final", 0)
                segment_state_suppressed_count = chunk_lifecycle_metrics.get("segment_state_suppressed", 0)
                segment_state_revised_count = chunk_lifecycle_metrics.get("segment_state_revised", 0)
                final_quality_count = sum(
                    value for key, value in chunk_lifecycle_metrics.items() if key.startswith("final_quality_")
                )
                revision_confirmation_observed_count = (
                    stage_revision_reset_count + stage_revision_preserved_internal_count
                )
                input_queue_size_peak = chunk_lifecycle_metrics.get("input_queue_size_peak", 0)
                input_queue_backlog_count = chunk_lifecycle_metrics.get("input_queue_backlog_chunk", 0)
                raw_without_final_count = 1 if raw_window_text and not final_sentences else 0
                if raw_without_final_count:
                    count_metric("raw_without_final")
                translation_skip_count = chunk_lifecycle_metrics.get("translation_skip_final_quality", 0)
                self._emit(
                    "status",
                    "받아쓰기 AI 안정성 지표: "
                    f"chunk={chunks} replace={stage_replace_count} replaced_unconfirmed={stage_replaced_unconfirmed_count} "
                    f"revision={stage_revision_count} revision_changed={stage_revision_changed_count} "
                    f"revision_reset={stage_revision_reset_count} "
                    f"revision_preserved_internal={stage_revision_preserved_internal_count} finalized={finalize_count} "
                    f"revision_internal_high={stage_revision_internal_high_count} "
                    f"revision_internal_mid={stage_revision_internal_mid_count} "
                    f"revision_internal_low={stage_revision_internal_low_count} "
                    f"finalize_before_replace={stage_finalize_before_replace_count} "
                    f"age_finalize={stage_age_finalize_count} "
                    f"age_quality_blocked={stage_age_quality_blocked_count} "
                    f"stage_start={stage_start_count} "
                    f"duplicate_suppressed={duplicate_suppressed_count} recent_echo_suppressed={recent_echo_suppressed_count} "
                    f"delta_trimmed={delta_trimmed_count} "
                    f"stable_prefix_chars={stable_prefix_chars} unstable_tail_chars={unstable_tail_chars} "
                    f"stable_internal_chars={stable_internal_chars} "
                    f"stable_internal_ratio={stable_internal_ratio_per_1000 / 1000:.3f} "
                    f"stable_token_ratio={stable_token_ratio_per_1000 / 1000:.3f} "
                    f"stage_candidate_quality_blocked={stage_candidate_quality_blocked_count} "
                    f"stage_candidate_quality={stage_candidate_quality_count} "
                    f"stage_candidate_quality_cjk_internal_gap={stage_candidate_quality_cjk_internal_gap_count} "
                    f"stage_candidate_quality_mixed_latin_zh={stage_candidate_quality_mixed_latin_count} "
                    f"segment_state_pending={segment_state_pending_count} "
                    f"segment_state_staged={segment_state_staged_count} "
                    f"segment_state_final={segment_state_final_count} "
                    f"segment_state_suppressed={segment_state_suppressed_count} "
                    f"segment_state_revised={segment_state_revised_count} "
                    f"final_quality={final_quality_count} translation_skip={translation_skip_count} "
                    f"raw_without_final={raw_without_final_count} "
                    f"finalized_per_stage_start={finalize_count / max(stage_start_count, 1):.2f} "
                    f"revision_preserve_rate={stage_revision_preserved_internal_count / max(revision_confirmation_observed_count, 1):.2f} "
                    f"replace_unconfirmed_rate={stage_replaced_unconfirmed_count / max(stage_replace_count, 1):.2f} "
                    f"input_queue_size_peak={input_queue_size_peak} "
                    f"input_queue_backlog={input_queue_backlog_count} "
                    f"decision_count={stage_decision_count}",
                    display=False,
                )
                self._emit(
                    "status",
                    "받아쓰기 AI 성능: "
                    f"chunk={chunks} step={step_seconds:.2f}s window={window_seconds:.2f}s "
                    f"audio={chunk_audio_seconds:.2f}s "
                    f"stt={stt_elapsed:.2f}s stt_rtf={stt_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                    f"stt_step_load={stt_elapsed / max(step_seconds, 0.001):.2f} "
                    f"translation={translation_elapsed:.2f}s translation_enabled={self._cfg.translationEnabled and not translation_failed} "
                    f"total={total_elapsed:.2f}s total_rtf={total_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                    f"total_step_load={total_elapsed / max(step_seconds, 0.001):.2f} "
                    f"effective_latency_estimate={window_seconds + total_elapsed:.2f}s "
                    f"input_queue_drops={chunk_audio_queue_drops} input_queue_drops_total={current_audio_queue_drops} "
                    f"queue_size={current_queue_size} queue_peak={input_queue_size_peak} "
                    f"beam={self._cfg.beamSize} max_tokens={self._cfg.maxNewTokens} text_chars={len(text)}",
                    display=False,
                )
            except Exception as exc:
                self._emit("error", f"받아쓰기 AI 전사 실패: {exc}")
                self._stop.set()
                raise

    def _run_mock(self) -> None:
        self._emit("status", "받아쓰기 AI mock 출력 시작")
        index = 1
        while not self._stop.is_set():
            self._emit("transcript", f"[mock] sample transcript {index}")
            if self._cfg.translationEnabled:
                self._emit("translation", f"translated mock sample {index}", log_text=f"[mock->{self._cfg.translationTargetLanguage}] translated mock sample {index}")
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
        self._context_text = None
        self._transcript_partial_active = False
        self._translation_partial_active = False
        self._events: queue.Queue[TranscriptEvent] = queue.Queue()
        self._worker = WhisperTranscriptWorker(app_config.dictationAi, self._events)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._root = tk.Tk()
        self._root.title(_window_title("transcript", self._ui_language))
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
        self._stt_status_root.title(_window_title("sttStatus", self._ui_language))
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
        self._translation_root.title(_window_title("translation", self._ui_language))
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
        return text_widget

    def _configure_line_number_text(self, line_numbers) -> None:
        line_numbers.configure(background="#f0f0f0")

    def _line_number_width(self, max_line: int) -> int:
        digits = max(1, len(str(max_line)))
        return max(42, (digits * 9) + 16)

    def _line_number_x(self, max_line: int) -> int:
        return self._line_number_width(max_line) - 6

    def _update_line_numbers(self, text_widget) -> None:
        line_numbers = getattr(self, "_line_number_widgets", {}).get(text_widget)
        if line_numbers is None:
            return
        line_numbers.delete("all")
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
            line_numbers.configure(width=self._line_number_width(max_line))
            x = self._line_number_x(max_line)
            for line, y in visible_lines:
                line_numbers.create_text(x, y, anchor="ne", text=line, fill="#777777")
        except Exception:
            content = text_widget.get("1.0", "end-1c")
            line_count = 0 if not content else content.count("\n") + 1
            line_numbers.configure(width=self._line_number_width(line_count))
            x = self._line_number_x(line_count)
            for line in range(1, line_count + 1):
                line_numbers.create_text(x, (line - 1) * 17, anchor="ne", text=str(line), fill="#777777")

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

    def _append(self, line: str, text_widget=None, *, final: bool = True, tag: str | None = None) -> None:
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
        if final:
            target.insert("end", f"{line}\n", tag or FINAL_TEXT_TAG)
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
                self._append(event.text, self._translation_text, final=event.final)
            elif event.kind == "error":
                self._append(self._format_error_for_modal(event.text), self._text, final=True, tag=ERROR_TEXT_TAG)
                if self._translation_text is not None:
                    self._append(self._format_error_for_modal(event.text), self._translation_text, final=True, tag=ERROR_TEXT_TAG)
            elif event.kind == "transcript":
                self._append(event.text, self._text, final=event.final)
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

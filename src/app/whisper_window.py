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
from collections import deque
from dataclasses import dataclass
from pathlib import Path


from src.app.rotating_log import install_rotating_stdout_log
from src.app.sentence_boundary import create_sentence_boundary_detector
from src.app.stt_model import build_stt_model
from src.app.translation_model import TranslationRequest, build_text_translator
from src.app.transcript_revision import append_context as _append_committed_text, consume_committed_prefix as _consume_committed_prefix, revision_lifecycle_context as _revision_lifecycle_context
from src.app.whisper_transcript_logic import (
    _collapse_adjacent_repeated_phrase_details,
    _collapse_adjacent_repeated_phrases,
    _coalesce_completed_sentences_for_staging,
    _diagnostic_tail,
    _final_sentence_diagnostic_flags,
    _forced_sentence_reason,
    _new_text_delta,
    _normalized_text,
    _pending_new_text_combined,
    _pending_overrun_reason,
    _format_transcript_metrics,
    _prefer_sentence_revision,
    _sentence_end_count,
    _sentence_max_age_chunks,
    _sentence_output_delta,
    _sentence_required_confirmations,
    _sentences_are_revisions,
    _replacement_decision_reason,
    _should_finalize_replaced_sentence,
    _should_stage_replacement_candidate,
    _should_confirm_staged_sentence,
    _should_age_staged_sentence,
    _should_translate_staged_sentence,
    _should_translate_final_sentence,
    _split_completed_sentences,
    _stable_window_text,
    _word_units,
)


from src.domain.whisper_defaults import whisper_default
from src.domain.config import AppConfig, WhisperConfig


SAMPLE_RATE = 16000
DEFAULT_CHUNK_SECONDS = float(whisper_default("chunkSeconds"))
DEFAULT_WINDOW_GEOMETRY = "780x420"
DEFAULT_WINDOW_GEOMETRY_META = {
    "whisperWindowGeometry": "780x420+50+119",
    "whisperTranslationWindowGeometry": "780x420+860+119",
    "whisperSttStatusWindowGeometry": "780x420+50+560",
}
MIN_WINDOW_WIDTH = 520
MIN_WINDOW_HEIGHT = 280
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
        "transcript": "ai-virtual-cam Audio AI Transcript",
        "translation": "ai-virtual-cam Audio AI Translation",
        "sttStatus": "ai-virtual-cam Audio AI STT Raw Transcript",
    },
    "ko": {
        "transcript": "ai-virtual-cam 오디오 AI 전사",
        "translation": "ai-virtual-cam 오디오 AI 번역",
        "sttStatus": "ai-virtual-cam 오디오 AI STT 원문창",
    },
}
_WINDOW_GEOMETRY_RE = re.compile(
    r"^(?P<width>\d+)x(?P<height>\d+)(?P<x_sign>[+-])(?P<x>\d+)(?P<y_sign>[+-])(?P<y>\d+)$"
)


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str
    display: bool = True
    log_text: str | None = None
    final: bool = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show local Whisper transcript window.")
    parser.add_argument("--config", default="~/.avc/setting.json", help="Path to the JSON config file.")
    return parser.parse_args()


def _log_line(message: str, *, file=None) -> None:
    target = sys.stdout if file is None else file
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", file=target, flush=True)


def _load_ui_language(config_path: Path) -> str:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log_line(f"[avc] whisper status: UI language load failed: {exc}")
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


def _window_restore_extent(root) -> tuple[int, int]:
    width = 0
    height = 0
    for width_name, height_name in (("winfo_vrootwidth", "winfo_vrootheight"), ("winfo_screenwidth", "winfo_screenheight")):
        try:
            width = max(width, int(getattr(root, width_name)()))
            height = max(height, int(getattr(root, height_name)()))
        except Exception:
            pass
    # Some X11/Tk setups report only the primary monitor before the window is mapped.
    # Allow the common two-monitor desktop extent so saved secondary-monitor windows reopen in place.
    if width > 0:
        width *= 2
    if height > 0:
        height *= 2
    return width, height


def _window_manager_geometry(window) -> str:
    try:
        geometry = window.geometry()
        if isinstance(geometry, str) and geometry.strip():
            return geometry
    except TypeError:
        pass
    except Exception:
        pass
    return window.winfo_geometry()


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
    default_geometry = DEFAULT_WINDOW_GEOMETRY_META.get(key)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            _log_line(
                f"[avc] whisper status: window geometry defaulted: key={key} "
                f"reason=invalid_config default={default_geometry}"
            )
            return default_geometry
        meta = raw.get("meta") or {}
        if not isinstance(meta, dict):
            _log_line(
                f"[avc] whisper status: window geometry defaulted: key={key} "
                f"reason=invalid_meta default={default_geometry}"
            )
            return default_geometry
        screen_width, screen_height = _window_restore_extent(root)
        saved = meta.get(key)
        restored = _sanitize_window_geometry(saved, screen_width, screen_height)
        if restored:
            _log_line(
                f"[avc] whisper status: window geometry restored: key={key} geometry={restored} "
                f"extent={screen_width}x{screen_height}"
            )
            return restored
        if default_geometry is not None:
            _log_line(
                f"[avc] whisper status: window geometry defaulted: key={key} "
                f"saved={saved!r} default={default_geometry} extent={screen_width}x{screen_height}"
            )
            return default_geometry
        _log_line(
            f"[avc] whisper status: window geometry restore skipped: key={key} "
            f"saved={saved!r} extent={screen_width}x{screen_height}"
        )
        return None
    except Exception as exc:
        _log_line(f"[avc] whisper status: window geometry load failed: {exc}")
        return default_geometry


def _save_window_geometry(
    config_path: Path,
    key: str,
    geometry: str,
    screen_width: int = 0,
    screen_height: int = 0,
) -> None:
    del config_path
    try:
        sanitized = _sanitize_window_geometry(geometry, screen_width, screen_height)
        if sanitized is None:
            _log_line(f"[avc] whisper status: window geometry cache skipped: key={key} invalid_geometry={geometry}")
            return
        _log_line(f"[avc] whisper status: window geometry cached: key={key} geometry={sanitized}")
    except Exception as exc:
        _log_line(f"[avc] whisper status: window geometry cache failed: key={key} error={exc}")

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
    def __init__(self, config: WhisperConfig, events: queue.Queue[TranscriptEvent]) -> None:
        self._cfg = config
        self._events = events
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[object] = queue.Queue(maxsize=120)
        self._capture_process: subprocess.Popen[bytes] | None = None
        self._capture_thread: threading.Thread | None = None
        self._recent_transcripts: deque[str] = deque(maxlen=RECENT_TRANSCRIPT_WINDOW)
        self._sentence_boundary_backend = str(getattr(config, "sentenceBoundaryBackend", "sat")).strip() or "sat"
        self._sentence_boundary_model = getattr(config, "sentenceBoundaryModel", None)
        self._boundary_detector_language = str(getattr(config, "language", "en")).strip().lower()
        self._boundary_detector_backend = self._sentence_boundary_backend
        self._boundary_detector_model = self._sentence_boundary_model
        self._sentence_boundary_detector = None

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
        download_source = "Hugging Face 또는 FunASR/ModelScope"
        self._emit(
            "status",
            "문장 경계 모델 로딩 중: "
            f"profile={getattr(self._cfg, 'postProcessingProfile', 'manual')} backend={backend} model={model} "
            f"device={device} compute={compute_type} language={detected_language}. "
            f"캐시에 없으면 {download_source} 모델 다운로드가 진행될 수 있습니다.",
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
            "문장 경계 모델 로딩 완료: "
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
        _log_line(f"[avc] whisper {kind}: {log_text if log_text is not None else text}")
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
                    "whisper.translationBackend=whisper는 faster-whisper STT backend에서만 지원됩니다. "
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
                "캐시에 없으면 Hugging Face 또는 FunASR/ModelScope 모델 다운로드가 진행될 수 있습니다.",
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
                    "Fail-Fast: 설정한 STT backend/model/device를 수정하거나 ./bin/avc setup으로 의존성과 모델을 준비하세요. "
                    f"원인: {exc}"
                ) from exc
            self._emit("status", "STT 모델 로딩 완료")
            text_translator = None
            self._emit("status", "Whisper 전처리 모델 준비 시작: 전사/번역은 모든 모델 로딩이 끝난 뒤 시작됩니다.")
            if self._cfg.translationEnabled:
                translation_status = (
                    "Whisper 내장 영어 번역 창 사용"
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
            self._emit("status", "Whisper 전처리 모델 준비 완료: 입력 캡처와 전사를 시작합니다.")
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
                    self._emit("status", "오디오 AI 입력 버퍼가 가득 차 오디오 프레임을 건너뜁니다.")

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
                    self._emit("status", "오디오 AI 입력 버퍼가 가득 차 Pulse 프레임을 건너뜁니다.")
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
        commit_lag_seconds = float(self._cfg.commitLagSeconds)
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
        staged_translation_pending = False
        staged_forced = False
        lifecycle_metrics: dict[str, int] = {}
        chunk_lifecycle_metrics: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            lifecycle_metrics[name] = lifecycle_metrics.get(name, 0) + amount
            chunk_lifecycle_metrics[name] = chunk_lifecycle_metrics.get(name, 0) + amount

        self._emit(
            "status",
            f"Whisper 전사 루프 시작: step_seconds={step_seconds} window_seconds={window_seconds} "
            f"commit_lag_seconds={commit_lag_seconds} language={self._cfg.language} "
            f"stt_backend={self._stt_settings_for_language()[0]} stt_model={self._stt_settings_for_language()[1]} "
            f"translation_enabled={self._cfg.translationEnabled} "
            f"translation_backend={self._cfg.translationBackend} "
            f"translation_target={self._cfg.translationTargetLanguage} beam_size={self._cfg.beamSize} "
            f"max_new_tokens={self._cfg.maxNewTokens} temperature={self._cfg.temperature} "
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
            nonlocal committed_text, staged_sentence, staged_confirmations, staged_age, staged_forced
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
            if not output_sentence:
                count_metric("finalize_duplicate_suppressed")
                self._emit(
                    "status",
                    f"Whisper 확정 후보 중복 무시: chunk={chunks} reason={reason} text={staged_before!r}",
                    display=False,
                )
                return []
            count_metric("finalized")
            final_quality_flags = _final_sentence_diagnostic_flags(output_sentence, detected)
            for flag in final_quality_flags:
                count_metric(f"final_quality_{flag}")
            committed_text = _append_committed_text(committed_text, output_sentence)
            self._remember_transcript(output_sentence)
            self._emit(
                "status",
                "Whisper 문장 확정: "
                f"chunk={chunks} reason={reason} committed_before_chars={committed_before_chars} "
                f"output_chars={len(_normalized_text(output_sentence))} "
                f"quality_flags={','.join(final_quality_flags) or 'none'} "
                f"staged_tail={_diagnostic_tail(staged_before)} text={output_sentence!r}",
                display=False,
            )
            self._emit("transcript", output_sentence, log_text=f"[{detected}] {output_sentence}", final=True)
            return [output_sentence]

        def stage_completed_sentence(sentence: str, detected: str, *, forced: bool = False) -> list[str]:
            nonlocal staged_sentence, staged_confirmations, staged_age, staged_translation_pending, staged_forced
            candidate = _sentence_output_delta(committed_text, sentence)
            if not candidate:
                count_metric("candidate_duplicate_suppressed")
                self._emit("status", f"Whisper 중복 문장 무시: chunk={chunks} text={sentence!r}", display=False)
                return []
            if not staged_sentence:
                count_metric("stage_start")
                staged_sentence = candidate
                staged_confirmations = 1
                staged_age = 0
                staged_translation_pending = True
                staged_forced = forced
                self._emit(
                    "status",
                    "Whisper stage 시작: "
                    f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                    f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                    display=False,
                )
                self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                return []
            is_revision = _sentences_are_revisions(staged_sentence, candidate)
            if is_revision:
                count_metric("stage_revision")
                staged_before = staged_sentence
                preferred = _prefer_sentence_revision(staged_sentence, candidate)
                if preferred != staged_before:
                    count_metric("stage_revision_changed")
                staged_sentence = preferred
                staged_confirmations += 1
                staged_age = 0
                staged_forced = staged_forced or forced
                required_confirmations = _sentence_required_confirmations(staged_forced)
                self._emit(
                    "status",
                    "Whisper stage 리비전: "
                    f"chunk={chunks} confirmations={staged_confirmations}/{required_confirmations} "
                    f"forced={staged_forced} preferred_changed={preferred != staged_before} "
                    f"staged_before={_diagnostic_tail(staged_before)} candidate={_diagnostic_tail(candidate)} "
                    f"preferred={_diagnostic_tail(preferred)}",
                    display=False,
                )
                if _should_confirm_staged_sentence(staged_sentence, staged_confirmations, staged_forced):
                    return finalize_staged_sentence(detected, "confirmed_forced" if staged_forced else "confirmed")
                staged_translation_pending = True
                self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                return []
            count_metric("stage_replace")
            replacement_reason = _replacement_decision_reason(
                staged_sentence,
                candidate,
                staged_confirmations,
                staged_forced,
                staged_age,
            )
            count_metric(f"stage_replace_decision_{replacement_reason}")
            self._emit(
                "status",
                "Whisper stage 교체: "
                f"chunk={chunks} reason=revision_false decision={replacement_reason} forced={forced} "
                f"staged_confirmations={staged_confirmations} staged_age={staged_age} "
                f"staged_tail={_diagnostic_tail(staged_sentence)} candidate_tail={_diagnostic_tail(candidate)}",
                display=False,
            )
            if _should_finalize_replaced_sentence(staged_sentence, candidate, staged_confirmations, staged_forced, staged_age):
                finalized = finalize_staged_sentence(detected, f"replaced_{replacement_reason}")
            else:
                count_metric("stage_discard")
                count_metric(f"stage_discard_reason_{replacement_reason}")
                max_age = _sentence_max_age_chunks(staged_forced)
                should_stage_candidate = _should_stage_replacement_candidate(
                    staged_sentence,
                    candidate,
                    replacement_reason,
                    staged_age,
                    max_age,
                )
                self._emit(
                    "status",
                    "Whisper stage 폐기: "
                    f"chunk={chunks} reason=replaced_unconfirmed "
                    f"staged_confirmations={staged_confirmations} required={_sentence_required_confirmations(staged_forced)} "
                    f"staged_age={staged_age} max_age={max_age} "
                    f"staged_forced={staged_forced} staged_tail={_diagnostic_tail(staged_sentence)} "
                    f"candidate_tail={_diagnostic_tail(candidate)} candidate_stage={should_stage_candidate}",
                    display=False,
                )
                finalized = []
                if not should_stage_candidate:
                    count_metric("stage_candidate_suppressed")
                    count_metric(f"stage_candidate_suppressed_reason_{replacement_reason}")
                    if staged_age >= max_age:
                        count_metric("stage_candidate_suppressed_age_overrun")
                    staged_age += 1
                    staged_translation_pending = True
                    self._emit(
                        "status",
                        "Whisper stage 후보 보류: "
                        f"chunk={chunks} reason={replacement_reason} staged_age={staged_age} "
                        f"staged_tail={_diagnostic_tail(staged_sentence)} candidate_tail={_diagnostic_tail(candidate)}",
                        display=False,
                    )
                    self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                    return finalized
                staged_sentence = ""
                staged_confirmations = 0
                staged_age = 0
                staged_forced = False
            count_metric("stage_start")
            staged_sentence = candidate
            staged_confirmations = 1
            staged_age = 0
            staged_translation_pending = True
            staged_forced = forced
            self._emit(
                "status",
                "Whisper stage 시작: "
                f"chunk={chunks} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
                f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
                display=False,
            )
            self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
            return finalized

        def log_collapse_diagnostic(scope: str, before: str, after: str, rules: list[str]) -> None:
            if not rules:
                return
            self._emit(
                "status",
                "Whisper collapse 진단: "
                f"chunk={chunks} scope={scope} rules={','.join(rules)} "
                f"before_chars={len(_normalized_text(before))} after_chars={len(_normalized_text(after))} "
                f"before_tail={_diagnostic_tail(before)} after_tail={_diagnostic_tail(after)}",
                display=False,
            )

        def age_staged_sentence(detected: str, pending_text: str = "") -> list[str]:
            nonlocal staged_age
            if not staged_sentence:
                return []
            if not _should_age_staged_sentence(staged_sentence, pending_text):
                count_metric("stage_age_hold")
                staged_age = 0
                self._emit(
                    "status",
                    f"Whisper staged aging 보류: chunk={chunks} staged={staged_sentence!r} pending={pending_text!r}",
                    display=False,
                )
                return []
            staged_age += 1
            count_metric("stage_age_tick")
            max_age = _sentence_max_age_chunks(staged_forced)
            if staged_age >= max_age:
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
            self._emit("status", f"Whisper 전사 요청: chunk={chunks} samples={buffered}", display=False)
            audio = np.concatenate(list(audio_blocks)).astype(np.float32, copy=False)
            chunk_audio_seconds = float(audio.shape[0]) / float(SAMPLE_RATE)
            chunk_started_at = time.perf_counter()
            translation_elapsed = 0.0
            translation_attempted = False
            translation_started_at = chunk_started_at
            text = ""
            staged_translation_pending = False
            try:
                stt_started_at = time.perf_counter()
                segments, info = model.transcribe(
                    audio,
                    language=language,
                    task="transcribe",
                    beam_size=self._cfg.beamSize,
                    temperature=self._cfg.temperature,
                    max_new_tokens=self._cfg.maxNewTokens,
                    without_timestamps=True,
                    condition_on_previous_text=False,
                )
                segment_list = list(segments)
                accepted_texts, rejected_reasons, boundary_confidence = self._accepted_segment_texts(segment_list)
                raw_window_text = " ".join(accepted_texts).strip()
                window_text, repeat_collapse_rules = _collapse_adjacent_repeated_phrase_details(raw_window_text)
                log_collapse_diagnostic("window", raw_window_text, window_text, repeat_collapse_rules)
                repeat_collapse_chars = max(0, len(_normalized_text(raw_window_text)) - len(_normalized_text(window_text)))
                stable_text = _stable_window_text(window_text, commit_lag_seconds, window_seconds)
                delta_base_text = _append_committed_text(committed_text, pending_transcript_text)
                text = _new_text_delta(delta_base_text, stable_text)
                stt_elapsed = time.perf_counter() - stt_started_at
                detected = getattr(info, "language", self._cfg.language)
                self._sync_sentence_boundary_detector(str(detected))
                if rejected_reasons:
                    self._emit(
                        "status",
                        f"Whisper 전사 후보 무시: chunk={chunks} reasons={'; '.join(rejected_reasons)}",
                        display=False,
                    )
                completed_sentences: list[str] = []
                final_sentences: list[str] = []
                forced_by = ""
                forced_candidate_pending = False
                boundary_complete = 0
                boundary_soft = 0
                boundary_confidence_display = f"{boundary_confidence:.2f}" if boundary_confidence is not None else "n/a"
                if text and self._is_repeated_hallucination(text):
                    self._emit("status", f"Whisper 반복 전사 무시: chunk={chunks} text={text!r}", display=False)
                    text = ""
                if text:
                    boundary_result = self._sentence_boundary_detector.split(
                        pending_transcript_text,
                        text,
                        detected,
                        boundary_confidence=boundary_confidence,
                    )
                    completed_sentences = []
                    for sentence in boundary_result.completed:
                        collapsed_sentence, sentence_collapse_rules = _collapse_adjacent_repeated_phrase_details(sentence)
                        if sentence_collapse_rules:
                            log_collapse_diagnostic("sentence", sentence, collapsed_sentence, sentence_collapse_rules)
                            repeat_collapse_rules.extend(f"sentence_{rule}" for rule in sentence_collapse_rules)
                        completed_sentences.append(collapsed_sentence)
                    pending_before_collapse = boundary_result.pending
                    pending_transcript_text, pending_collapse_rules = _collapse_adjacent_repeated_phrase_details(pending_before_collapse)
                    if pending_collapse_rules:
                        log_collapse_diagnostic("pending", pending_before_collapse, pending_transcript_text, pending_collapse_rules)
                        repeat_collapse_rules.extend(f"pending_{rule}" for rule in pending_collapse_rules)
                    boundary_complete = boundary_result.boundary_count
                    boundary_soft = boundary_result.soft_boundary_count
                    if completed_sentences:
                        coalesced_completed_sentences = _coalesce_completed_sentences_for_staging(completed_sentences, str(detected))
                        if len(coalesced_completed_sentences) != len(completed_sentences):
                            count_metric("completed_coalesced")
                            count_metric(f"completed_coalesced_lang_{str(detected).strip().lower() or 'unknown'}")
                            self._emit(
                                "status",
                                "오디오 AI completed 후보 병합: "
                                f"chunk={chunks} language={detected} before={len(completed_sentences)} "
                                f"after={len(coalesced_completed_sentences)} "
                                f"tail={_diagnostic_tail(coalesced_completed_sentences[0])}",
                                display=False,
                            )
                        completed_sentences = coalesced_completed_sentences
                        pending_chunks = 0
                    elif pending_transcript_text:
                        pending_chunks += 1
                        forced_by = _forced_sentence_reason(pending_transcript_text, pending_chunks)
                        if forced_by:
                            count_metric("forced_candidate")
                            forced_before_collapse = pending_transcript_text
                            forced_sentence, forced_collapse_rules = _collapse_adjacent_repeated_phrase_details(forced_before_collapse)
                            if forced_collapse_rules:
                                log_collapse_diagnostic("forced", forced_before_collapse, forced_sentence, forced_collapse_rules)
                                repeat_collapse_rules.extend(f"forced_{rule}" for rule in forced_collapse_rules)
                            completed_sentences = [forced_sentence]
                            forced_candidate_pending = True
                    for sentence in completed_sentences:
                        produced_sentences = stage_completed_sentence(sentence, detected, forced=bool(forced_by))
                        final_sentences.extend(produced_sentences)
                        for produced_sentence in produced_sentences:
                            pending_transcript_text = _consume_committed_prefix(pending_transcript_text, produced_sentence)
                            if not pending_transcript_text:
                                pending_chunks = 0
                    if pending_transcript_text and not forced_candidate_pending:
                        self._emit(
                            "transcript",
                            pending_transcript_text,
                            log_text=f"[{detected}] {pending_transcript_text}",
                            final=False,
                        )
                    elif not completed_sentences:
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                else:
                    preview_chars = max(0, len(_normalized_text(window_text)) - len(_normalized_text(stable_text)))
                    self._emit(
                        "status",
                        f"Whisper 전사 결과 없음: chunk={chunks} preview_chars={preview_chars}",
                        display=False,
                    )
                    if pending_transcript_text:
                        pending_chunks += 1
                        forced_by = _forced_sentence_reason(pending_transcript_text, pending_chunks)
                        if forced_by:
                            count_metric("forced_candidate")
                            forced_before_collapse = pending_transcript_text
                            forced_sentence, forced_collapse_rules = _collapse_adjacent_repeated_phrase_details(forced_before_collapse)
                            if forced_collapse_rules:
                                log_collapse_diagnostic("forced", forced_before_collapse, forced_sentence, forced_collapse_rules)
                                repeat_collapse_rules.extend(f"forced_{rule}" for rule in forced_collapse_rules)
                            completed_sentences = [forced_sentence]
                            forced_candidate_pending = True
                            for sentence in completed_sentences:
                                produced_sentences = stage_completed_sentence(sentence, detected, forced=bool(forced_by))
                                final_sentences.extend(produced_sentences)
                                for produced_sentence in produced_sentences:
                                    pending_transcript_text = _consume_committed_prefix(pending_transcript_text, produced_sentence)
                                    if not pending_transcript_text:
                                        pending_chunks = 0
                        else:
                            final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                    else:
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                pending_overrun_reason = _pending_overrun_reason(pending_transcript_text, pending_chunks)
                if pending_overrun_reason:
                    count_metric("pending_overrun")
                    count_metric(f"pending_overrun_reason_{pending_overrun_reason}")
                self._emit(
                    "status",
                    "Whisper 문장 진단: "
                    f"chunk={chunks} completed={len(completed_sentences)} final={len(final_sentences)} forced_by={forced_by or 'none'} "
                    f"pending_overrun={pending_overrun_reason or 'none'} "
                    f"boundary_backend={self._sentence_boundary_detector.backend} "
                    f"boundary_complete={boundary_complete} boundary_soft={boundary_soft} boundary_conf={boundary_confidence_display} "
                    f"pending_chars={len(pending_transcript_text)} pending_chunks={pending_chunks} "
                    f"pending_chars_per_chunk={len(pending_transcript_text) / max(pending_chunks, 1):.1f} "
                    f"window_chars={len(_normalized_text(window_text))} stable_chars={len(_normalized_text(stable_text))} "
                    f"repeat_collapse_chars={repeat_collapse_chars} repeat_collapse_rules={','.join(repeat_collapse_rules) or 'none'} "
                    f"delta_chars={len(_normalized_text(text))} "
                    f"end_marks_window={_sentence_end_count(window_text)} end_marks_stable={_sentence_end_count(stable_text)} "
                    f"end_marks_delta={_sentence_end_count(text)} "
                    f"stable_tail={_diagnostic_tail(stable_text)} delta_tail={_diagnostic_tail(text)} "
                    f"pending_tail={_diagnostic_tail(pending_transcript_text)} "
                    f"revision_context_chars={len(_normalized_text(_revision_lifecycle_context(committed_text, staged_sentence, pending_transcript_text)))} "
                    f"forced_candidate_pending={forced_candidate_pending} "
                    f"chunk_metrics={_format_transcript_metrics(chunk_lifecycle_metrics)} "
                    f"lifecycle_metrics={_format_transcript_metrics(lifecycle_metrics)} "
                    f"staged_confirmations={staged_confirmations} staged_age={staged_age} staged_forced={staged_forced} "
                    f"staged_tail={_diagnostic_tail(staged_sentence)}",
                    display=False,
                )
                translation_jobs: list[tuple[str, bool]] = []
                if (
                    text_translator is not None
                    and staged_translation_pending
                    and staged_sentence
                    and _should_translate_staged_sentence(staged_sentence, staged_confirmations)
                ):
                    translation_jobs.append((staged_sentence, False))
                for sentence in final_sentences:
                    if _should_translate_final_sentence(sentence, detected):
                        translation_jobs.append((sentence, True))
                    else:
                        count_metric("translation_skip_final_quality")
                        self._emit(
                            "status",
                            "Whisper 번역 생략: "
                            f"chunk={chunks} reason=final_quality flags={','.join(_final_sentence_diagnostic_flags(sentence, detected))} "
                            f"text={sentence!r}",
                            display=False,
                        )
                if self._cfg.translationEnabled and not translation_failed and translation_jobs:
                    try:
                        translation_attempted = True
                        request_label = "Whisper 내장 번역 요청" if text_translator is None else "외부 텍스트 번역 요청"
                        target_language = self._cfg.translationTargetLanguage
                        source_language = detected if detected in {"ko", "en", "zh"} else self._cfg.language
                        for sentence, is_final_translation in translation_jobs:
                            if text_translator is None and not is_final_translation:
                                continue
                            translation_started_at = time.perf_counter()
                            self._emit("status", f"{request_label}: chunk={chunks} final={is_final_translation}", display=False)
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
                                    commit_lag_seconds,
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
                                    "Whisper 번역 진단: "
                                    f"chunk={chunks} final={is_final_translation} "
                                    f"source_lang={source_language} target_lang={target_language} "
                                    f"source_chars={len(_normalized_text(sentence))} "
                                    f"target_chars={len(_normalized_text(translated_text))} "
                                    f"backend={self._cfg.translationBackend} model={self._cfg.translationModel}",
                                    display=False,
                                )
                                if is_final_translation:
                                    committed_translation_text = _append_committed_text(committed_translation_text, translated_text)
                                self._emit(
                                    "translation",
                                    translated_text,
                                    log_text=f"[{detected}->{target_language}] {translated_text}",
                                    final=is_final_translation,
                                )
                            else:
                                self._emit("status", f"Whisper 번역 결과 없음: chunk={chunks}", display=False)
                    except Exception as exc:
                        translation_elapsed = time.perf_counter() - translation_started_at if translation_attempted else 0.0
                        translation_failed = True
                        self._emit(
                            "error",
                            "Whisper 번역 실패: "
                            f"{exc}. 번역을 이번 세션에서 중지합니다. STT 전사는 계속됩니다.",
                        )
                total_elapsed = time.perf_counter() - chunk_started_at
                stage_decision_count = sum(
                    value for key, value in chunk_lifecycle_metrics.items() if key.startswith("stage_replace_decision_")
                )
                stage_replace_count = chunk_lifecycle_metrics.get("stage_replace", 0)
                stage_discard_count = chunk_lifecycle_metrics.get("stage_discard", 0)
                stage_revision_count = chunk_lifecycle_metrics.get("stage_revision", 0)
                finalize_count = chunk_lifecycle_metrics.get("finalized", 0)
                self._emit(
                    "status",
                    "Whisper 안정성 지표: "
                    f"chunk={chunks} replace={stage_replace_count} discard={stage_discard_count} "
                    f"revision={stage_revision_count} finalized={finalize_count} "
                    f"replace_discard_rate={stage_discard_count / max(stage_replace_count, 1):.2f} "
                    f"decision_count={stage_decision_count} "
                    f"completed_coalesced={chunk_lifecycle_metrics.get('completed_coalesced', 0)}",
                    display=False,
                )
                self._emit(
                    "status",
                    "Whisper 성능: "
                    f"chunk={chunks} step={step_seconds:.2f}s window={window_seconds:.2f}s "
                    f"commit_lag={commit_lag_seconds:.2f}s audio={chunk_audio_seconds:.2f}s "
                    f"stt={stt_elapsed:.2f}s stt_rtf={stt_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                    f"translation={translation_elapsed:.2f}s translation_enabled={self._cfg.translationEnabled and not translation_failed} "
                    f"total={total_elapsed:.2f}s total_rtf={total_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                    f"beam={self._cfg.beamSize} max_tokens={self._cfg.maxNewTokens} text_chars={len(text)}",
                    display=False,
                )
            except Exception as exc:
                self._emit("error", f"Whisper 전사 실패: {exc}")
                self._stop.set()
                raise

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
            raise RuntimeError("whisper.enabled=false 입니다. config에서 오디오 AI 전사를 켠 뒤 serve를 실행하세요.")
        try:
            import tkinter as tk
            from tkinter import ttk
        except ModuleNotFoundError as exc:
            raise RuntimeError("Tkinter가 없습니다. Whisper 출력 창을 열 수 없습니다.") from exc

        self._tk = tk
        self._ttk = ttk
        self._config_path = config_path
        self._ui_language = _load_ui_language(config_path)
        self._whisper_config = app_config.whisper
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
        self._worker = WhisperTranscriptWorker(app_config.whisper, self._events)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._root = tk.Tk()
        self._root.title(_window_title("transcript", self._ui_language))
        restored_geometry = _load_window_geometry(self._config_path, "whisperWindowGeometry", self._root)
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
            self._config_path, "whisperSttStatusWindowGeometry", self._stt_status_root
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
            self._config_path, "whisperTranslationWindowGeometry", self._translation_root
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
                if event.display and not event.final:
                    self._append_stt_status_transcript(event.text)
                if not event.final:
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
            "whisperWindowGeometry",
            self._current_geometry(),
            *_window_restore_extent(self._root),
        )

    def _save_translation_geometry(self) -> None:
        self._translation_geometry_save_after_id = None
        if self._translation_root is None:
            return
        _save_window_geometry(
            self._config_path,
            "whisperTranslationWindowGeometry",
            _window_manager_geometry(self._translation_root),
            *_window_restore_extent(self._translation_root),
        )

    def _save_stt_status_geometry(self) -> None:
        self._stt_status_geometry_save_after_id = None
        if self._stt_status_root is None:
            return
        _save_window_geometry(
            self._config_path,
            "whisperSttStatusWindowGeometry",
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
    _log_line(f"[avc] whisper rotating log file: {log_path}")
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

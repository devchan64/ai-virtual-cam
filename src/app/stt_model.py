from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Iterable

from src.app.model_cache import require_funasr_model_cached
from src.domain.contracts.whisper import resolve_funasr_model_name


STT_BACKENDS = {"faster-whisper", "funasr-paraformer", "funasr-sensevoice", "mock"}


@dataclass(frozen=True)
class SttSegment:
    text: str
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass(frozen=True)
class SttInfo:
    language: str


def build_stt_model(
    *,
    backend: str,
    model_name: str,
    device: str,
    compute_type: str,
    language: str,
    status_callback=None,
):
    normalized_backend = str(backend).strip()
    if normalized_backend == "faster-whisper":
        return FasterWhisperSttModel(model_name, device, compute_type)
    if normalized_backend in {"funasr-paraformer", "funasr-sensevoice"}:
        return FunasrSttModel(normalized_backend, model_name, device, language, status_callback=status_callback)
    raise RuntimeError(
        f"지원하지 않는 whisper STT backend입니다: {backend}. "
        "Use one of: faster-whisper, funasr-paraformer, funasr-sensevoice, mock"
    )


class FasterWhisperSttModel:
    def __init__(self, model_name: str, device: str, compute_type: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "faster-whisper 모듈이 없습니다. 로컬 Whisper를 사용하려면 faster-whisper와 CUDA 런타임을 설치하세요."
            ) from exc
        self._model = WhisperModel(model_name, device=device, compute_type=compute_type, local_files_only=True)

    def transcribe(self, audio, **kwargs):
        return self._model.transcribe(audio, **kwargs)


class FunasrSttModel:
    def __init__(self, backend: str, model_name: str, device: str, language: str, *, status_callback=None) -> None:
        self.backend = backend
        self.model_name = model_name
        self.resolved_model_name = resolve_funasr_model_name(model_name)
        self.device = device
        self.language = language if language in {"ko", "en", "zh"} else "zh"
        self._status_callback = status_callback
        try:
            with _capture_model_output() as captured:
                from funasr import AutoModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"STT backend '{backend}' requires funasr. Run ./bin/avc setup or install funasr; "
                "fallback is intentionally disabled."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"STT backend '{backend}' failed while importing FunASR. "
                f"model={model_name} device={device}. 원인: {exc}"
            ) from exc
        _emit_captured_output(status_callback, "FunASR STT import", captured.getvalue())
        require_funasr_model_cached(model_name, purpose="FunASR STT")
        try:
            with _capture_model_output() as captured:
                self._model = AutoModel(model=self.resolved_model_name, device=device, disable_update=True)
        except Exception as exc:
            raise RuntimeError(
                f"FunASR STT 모델 로딩 실패: backend={backend} model={model_name} resolvedModel={self.resolved_model_name} device={device}. "
                f"원인: {exc}"
            ) from exc
        _emit_captured_output(status_callback, "FunASR STT load", captured.getvalue())

    def transcribe(self, audio, **_kwargs):
        try:
            with _capture_model_output() as captured:
                result = self._model.generate(input=audio, fs=16000)
        except Exception as exc:
            raise RuntimeError(
                f"FunASR STT 전사 실패: backend={self.backend} model={self.model_name} "
                f"resolvedModel={self.resolved_model_name} device={self.device}. 원인: {exc}"
            ) from exc
        text = funasr_generated_text(result)
        segments: Iterable[SttSegment] = [SttSegment(text=text)] if text else []
        return segments, SttInfo(language=self.language)


@contextlib.contextmanager
def _capture_model_output():
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        yield _CapturedOutput(stdout, stderr)


@dataclass(frozen=True)
class _CapturedOutput:
    stdout: io.StringIO
    stderr: io.StringIO

    def getvalue(self) -> str:
        return "\n".join(part.strip() for part in (self.stdout.getvalue(), self.stderr.getvalue()) if part.strip())


def _emit_captured_output(callback, prefix: str, output: str) -> None:
    if callback is None or not output:
        return
    trimmed = " ".join(output.split())
    if trimmed:
        callback(f"{prefix} output: {trimmed[:500]}")


def funasr_generated_text(result: object) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        text = result.get("text") or result.get("sentence") or result.get("value") or ""
        return str(text).strip()
    if isinstance(result, list):
        parts = [funasr_generated_text(item) for item in result]
        return " ".join(part for part in parts if part).strip()
    return str(result or "").strip()

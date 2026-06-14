from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Iterable

from src.app.model_cache import require_funasr_model_cache_path, require_qwen_asr_model_cached
from src.domain.contracts.whisper import resolve_funasr_model_name, resolve_qwen_asr_model_name


STT_BACKENDS = {
    "faster-whisper",
    "funasr-paraformer",
    "funasr-paraformer-streaming",
    "funasr-sensevoice",
    "qwen3-asr-transformers",
    "mock",
}


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
    if normalized_backend in {"funasr-paraformer", "funasr-paraformer-streaming", "funasr-sensevoice"}:
        return FunasrSttModel(normalized_backend, model_name, device, language, status_callback=status_callback)
    if normalized_backend == "qwen3-asr-transformers":
        return Qwen3AsrTransformersSttModel(model_name, device, compute_type, language)
    raise RuntimeError(
        f"지원하지 않는 whisper STT backend입니다: {backend}. "
        "Use one of: faster-whisper, funasr-paraformer, funasr-paraformer-streaming, "
        "funasr-sensevoice, qwen3-asr-transformers, mock"
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


class Qwen3AsrTransformersSttModel:
    def __init__(self, model_name: str, device: str, compute_type: str, language: str) -> None:
        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "qwen-asr 모듈이 없습니다. Qwen3-ASR STT를 사용하려면 ./bin/avc setup을 실행하세요. "
                f"설정값 sttBackend=qwen3-asr-transformers model={model_name}. 원인: {exc}"
            ) from exc
        self.model_name = model_name
        self.resolved_model_name = resolve_qwen_asr_model_name(model_name)
        self.device = device
        self.compute_type = compute_type
        self.language = language
        require_qwen_asr_model_cached(model_name, purpose="Qwen3-ASR STT")
        dtype = torch.bfloat16 if compute_type == "bfloat16" else torch.float16 if compute_type == "float16" else torch.float32
        try:
            self._model = Qwen3ASRModel.from_pretrained(
                self.resolved_model_name,
                dtype=dtype,
                device_map="cuda:0" if device == "cuda" else "cpu",
                local_files_only=True,
                max_inference_batch_size=8,
                max_new_tokens=256,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Qwen3-ASR STT 모델 로딩 실패: model={model_name} resolvedModel={self.resolved_model_name} "
                f"device={device} compute={compute_type}. 원인: {exc}"
            ) from exc

    def transcribe(self, audio, **kwargs):
        language_hint = _qwen_language_hint(str(kwargs.get("language") or self.language))
        max_new_tokens = int(kwargs.get("max_new_tokens") or 256)
        try:
            result = self._model.transcribe(audio=(audio, 16000), language=language_hint, max_new_tokens=max_new_tokens)
        except TypeError:
            result = self._model.transcribe(audio=(audio, 16000), language=language_hint)
        except Exception as exc:
            raise RuntimeError(
                f"Qwen3-ASR STT 전사 실패: model={self.model_name} resolvedModel={self.resolved_model_name} "
                f"device={self.device}. 원인: {exc}"
            ) from exc
        text, detected_language = qwen_asr_generated_text(result, fallback_language=self.language)
        segments: Iterable[SttSegment] = [SttSegment(text=text)] if text else []
        return segments, SttInfo(language=detected_language)


def _qwen_language_hint(language: str) -> str:
    return {"zh": "Chinese", "en": "English", "ko": "Korean"}.get(language, "Chinese")


def qwen_asr_generated_text(result: object, *, fallback_language: str) -> tuple[str, str]:
    first = result[0] if isinstance(result, list) and result else result
    text = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else None) or str(first or "")
    language = getattr(first, "language", None) or (first.get("language") if isinstance(first, dict) else None) or fallback_language
    normalized_language = {"Chinese": "zh", "English": "en", "Korean": "ko"}.get(str(language), str(language).lower())
    return str(text).strip(), normalized_language


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
        if self.backend == "funasr-paraformer-streaming" and self.model_name != "paraformer-zh-streaming":
            raise RuntimeError(
                "FunASR streaming STT backend requires model=paraformer-zh-streaming. "
                f"configuredModel={self.model_name}. Fail-Fast: select the matching streaming model."
            )
        self.local_model_path = require_funasr_model_cache_path(model_name, purpose="FunASR STT")
        if self._status_callback is not None:
            self._status_callback(f"FunASR STT 로컬 캐시 사용: model={model_name} path={self.local_model_path}")
        try:
            with _capture_model_output() as captured:
                self._model = AutoModel(model=str(self.local_model_path), device=device, disable_update=True)
        except Exception as exc:
            raise RuntimeError(
                f"FunASR STT 모델 로딩 실패: backend={backend} model={model_name} resolvedModel={self.resolved_model_name} "
                f"localPath={self.local_model_path} device={device}. 원인: {exc}"
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
        return _strip_funasr_control_tokens(result)
    if isinstance(result, dict):
        text = result.get("text") or result.get("sentence") or result.get("value") or ""
        return _strip_funasr_control_tokens(str(text))
    if isinstance(result, list):
        parts = [funasr_generated_text(item) for item in result]
        return " ".join(part for part in parts if part).strip()
    return _strip_funasr_control_tokens(str(result or ""))


def _strip_funasr_control_tokens(text: str) -> str:
    stripped = str(text or "").strip()
    while stripped.startswith("<|"):
        end = stripped.find("|>")
        if end < 0:
            break
        stripped = stripped[end + 2 :].lstrip()
    return stripped.strip()

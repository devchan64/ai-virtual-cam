from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.app.model_cache import require_qwen_asr_model_cached
from src.domain.contracts.whisper import resolve_qwen_asr_model_name


QWEN_ASR_BACKENDS = {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}
STT_BACKENDS = {
    "faster-whisper",
    *QWEN_ASR_BACKENDS,
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
    if normalized_backend == "qwen3-asr-transformers":
        return Qwen3AsrTransformersSttModel(model_name, device, compute_type, language)
    if normalized_backend == "qwen3-asr-vllm-streaming":
        return Qwen3AsrVllmStreamingSttModel(model_name, device, compute_type, language)
    raise RuntimeError(
        f"지원하지 않는 whisper STT backend입니다: {backend}. "
        "Use one of: faster-whisper, qwen3-asr-transformers, qwen3-asr-vllm-streaming, mock"
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


class Qwen3AsrBaseSttModel:
    backend_name = "qwen3-asr"

    def __init__(self, model_name: str, device: str, compute_type: str, language: str) -> None:
        self.model_name = model_name
        self.resolved_model_name = resolve_qwen_asr_model_name(model_name)
        self.device = device
        self.compute_type = compute_type
        self.language = language
        require_qwen_asr_model_cached(model_name, purpose="Qwen3-ASR STT")

    def _wrap_load_error(self, exc: Exception) -> RuntimeError:
        return RuntimeError(
            f"Qwen3-ASR STT 모델 로딩 실패: backend={self.backend_name} model={self.model_name} "
            f"resolvedModel={self.resolved_model_name} device={self.device} compute={self.compute_type}. 원인: {exc}"
        )

    def _wrap_transcribe_error(self, exc: Exception) -> RuntimeError:
        return RuntimeError(
            f"Qwen3-ASR STT 전사 실패: backend={self.backend_name} model={self.model_name} "
            f"resolvedModel={self.resolved_model_name} device={self.device}. 원인: {exc}"
        )


class Qwen3AsrTransformersSttModel(Qwen3AsrBaseSttModel):
    backend_name = "qwen3-asr-transformers"

    def __init__(self, model_name: str, device: str, compute_type: str, language: str) -> None:
        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "qwen-asr 모듈이 없습니다. Qwen3-ASR STT를 사용하려면 ./bin/avc setup을 실행하세요. "
                f"설정값 sttBackend=qwen3-asr-transformers model={model_name}. 원인: {exc}"
            ) from exc
        super().__init__(model_name, device, compute_type, language)
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
            raise self._wrap_load_error(exc) from exc

    def transcribe(self, audio, **kwargs):
        language_hint = _qwen_language_hint(str(kwargs.get("language") or self.language))
        max_new_tokens = int(kwargs.get("max_new_tokens") or 256)
        try:
            result = self._model.transcribe(audio=(audio, 16000), language=language_hint, max_new_tokens=max_new_tokens)
        except TypeError:
            result = self._model.transcribe(audio=(audio, 16000), language=language_hint)
        except Exception as exc:
            raise self._wrap_transcribe_error(exc) from exc
        text, detected_language = qwen_asr_generated_text(result, fallback_language=self.language)
        segments: Iterable[SttSegment] = [SttSegment(text=text)] if text else []
        return segments, SttInfo(language=detected_language)


class Qwen3AsrVllmStreamingSttModel(Qwen3AsrBaseSttModel):
    backend_name = "qwen3-asr-vllm-streaming"
    streaming = True

    def __init__(self, model_name: str, device: str, compute_type: str, language: str) -> None:
        if str(device).strip().lower() != "cuda":
            raise RuntimeError(
                "qwen3-asr-vllm-streaming backend은 CUDA 실행만 지원합니다. "
                f"설정값 device={device}. CPU fallback은 사용하지 않습니다."
            )
        try:
            from qwen_asr import Qwen3ASRModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "qwen-asr 모듈이 없습니다. Qwen3-ASR STT를 사용하려면 ./bin/avc setup을 실행하세요. "
                f"설정값 sttBackend=qwen3-asr-vllm-streaming model={model_name}. 원인: {exc}"
            ) from exc
        super().__init__(model_name, device, compute_type, language)
        self._state = None
        self._stream_context = ""
        dtype = _qwen_vllm_dtype(compute_type)
        try:
            self._model = Qwen3ASRModel.LLM(
                model=self.resolved_model_name,
                dtype=dtype,
                max_new_tokens=256,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Qwen3-ASR vLLM streaming 모델 로딩 실패: model={self.model_name} "
                f"resolvedModel={self.resolved_model_name} device={self.device} compute={self.compute_type}. "
                "vLLM 런타임이 필요합니다. qwen-asr[vllm] 또는 vllm 설치 상태를 확인하세요. "
                f"원인: {exc}"
            ) from exc

    def transcribe(self, audio, **kwargs):
        stream_audio = kwargs.get("stream_audio")
        if stream_audio is None:
            stream_audio = audio
        language_hint = _qwen_language_hint(str(kwargs.get("language") or self.language))
        chunk_size_sec = float(kwargs.get("stream_chunk_seconds") or 2.0)
        context_seconds = float(kwargs.get("stream_context_seconds") or 30.0)
        if self._state is None:
            try:
                self._state = self._model.init_streaming_state(
                    context=self._stream_context,
                    language=language_hint,
                    unfixed_chunk_num=2,
                    unfixed_token_num=5,
                    chunk_size_sec=chunk_size_sec,
                )
            except Exception as exc:
                raise self._wrap_transcribe_error(exc) from exc
        try:
            self._state = self._model.streaming_transcribe(stream_audio, self._state)
        except Exception as exc:
            raise self._wrap_transcribe_error(exc) from exc
        text = str(getattr(self._state, "text", "") or "").strip()
        detected_language = _qwen_detected_language(getattr(self._state, "language", None), self.language)
        if _qwen_stream_audio_seconds(self._state) >= context_seconds:
            self._stream_context = text
            self._state = None
        segments: Iterable[SttSegment] = [SttSegment(text=text)] if text else []
        return segments, SttInfo(language=detected_language)


def _qwen_language_hint(language: str) -> str:
    return {"zh": "Chinese", "en": "English", "ko": "Korean"}.get(language, "Chinese")


def _qwen_detected_language(language: object, fallback_language: str) -> str:
    return {"Chinese": "zh", "English": "en", "Korean": "ko"}.get(str(language), str(language or fallback_language).lower())


def _qwen_vllm_dtype(compute_type: str) -> str:
    normalized = str(compute_type or "").strip().lower()
    if normalized in {"float16", "bfloat16", "float32"}:
        return normalized
    return "float16"


def _qwen_stream_audio_seconds(state: object) -> float:
    audio_accum = getattr(state, "audio_accum", None)
    buffer = getattr(state, "buffer", None)
    audio_samples = int(getattr(audio_accum, "shape", (0,))[0] or 0)
    buffer_samples = int(getattr(buffer, "shape", (0,))[0] or 0)
    return float(audio_samples + buffer_samples) / 16000.0


def qwen_asr_generated_text(result: object, *, fallback_language: str) -> tuple[str, str]:
    first = result[0] if isinstance(result, list) and result else result
    text = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else None) or str(first or "")
    language = getattr(first, "language", None) or (first.get("language") if isinstance(first, dict) else None) or fallback_language
    normalized_language = _qwen_detected_language(language, fallback_language)
    return str(text).strip(), normalized_language

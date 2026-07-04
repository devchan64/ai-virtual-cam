from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.app.models.model_cache import require_qwen_asr_model_cached
from src.domain.contracts.dictation_ai import resolve_qwen_asr_model_name


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
        raise RuntimeError(
            "qwen3-asr-vllm-streaming backend은 현재 공유 .venv에서 지원하지 않습니다. "
            "vLLM은 protobuf/opencv 의존성이 mediapipe와 충돌합니다. "
            "현재는 sttBackendZh=qwen3-asr-transformers를 사용하세요. "
            "향후 별도 vLLM 격리 런타임으로 다시 제공해야 합니다."
        )


def _qwen_language_hint(language: str) -> str:
    return {"zh": "Chinese", "en": "English", "ko": "Korean"}.get(language, "Chinese")


def _qwen_detected_language(language: object, fallback_language: str) -> str:
    return {"Chinese": "zh", "English": "en", "Korean": "ko"}.get(str(language), str(language or fallback_language).lower())


def qwen_asr_generated_text(result: object, *, fallback_language: str) -> tuple[str, str]:
    first = result[0] if isinstance(result, list) and result else result
    if isinstance(first, dict):
        text = first["text"] if "text" in first else str(first or "")
        language = first.get("language") or fallback_language
    else:
        text = getattr(first, "text") if hasattr(first, "text") else str(first or "")
        language = getattr(first, "language", None) or fallback_language
    normalized_language = _qwen_detected_language(language, fallback_language)
    return str(text).strip(), normalized_language

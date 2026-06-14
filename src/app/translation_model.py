from __future__ import annotations

from dataclasses import dataclass


NLLB_LANGUAGE_CODES = {
    "en": "eng_Latn",
    "ko": "kor_Hang",
    "zh": "zho_Hans",
}

M2M100_LANGUAGE_CODES = {
    "en": "en",
    "ko": "ko",
    "zh": "zh",
}


@dataclass(frozen=True)
class TranslationRequest:
    text: str
    source_language: str
    target_language: str


class LocalTextTranslator:
    def translate(self, request: TranslationRequest) -> str:
        raise NotImplementedError


class MockTextTranslator(LocalTextTranslator):
    def translate(self, request: TranslationRequest) -> str:
        return f"[mock {request.source_language}->{request.target_language}] {request.text}"


class NllbTransformersTranslator(LocalTextTranslator):
    def __init__(self, model_name: str, device: str, compute_type: str, beam_size: int = 1, max_new_tokens: int = 128) -> None:
        if not model_name:
            raise RuntimeError("whisper.translationModel is required for nllb-transformers")
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "NLLB 번역 의존성이 없습니다. ./bin/avc setup을 실행해 transformers, torch, sentencepiece를 설치하세요. "
                f"설정값 translationBackend=nllb-transformers translationModel={model_name}. 원인: {exc}"
            ) from exc

        resolved_device = self._resolve_device(torch, device)
        torch_dtype = self._resolve_dtype(torch, compute_type, resolved_device)
        self._model_name = model_name
        self._requested_device = str(device or "auto").strip()
        self._requested_compute_type = str(compute_type or "auto").strip()
        self._beam_size = _validate_generation_int("whisper.translationBeamSize", beam_size, 1, 8)
        self._max_new_tokens = _validate_generation_int("whisper.translationMaxNewTokens", max_new_tokens, 16, 512)
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(model_name, torch_dtype=torch_dtype)
            self._model.to(resolved_device)
            self._model.eval()
        except Exception as exc:
            raise RuntimeError(
                "NLLB 번역 모델 로딩 실패: "
                f"translationModel={model_name} device={device} computeType={compute_type}. "
                "최초 실행이면 모델 다운로드가 필요합니다. CUDA/메모리/네트워크 상태를 확인하세요. "
                f"원인: {exc}"
            ) from exc
        self._torch = torch
        self._device = resolved_device

    @staticmethod
    def _resolve_device(torch, device: str) -> str:
        normalized = str(device or "").strip().lower()
        if normalized == "auto":
            raise RuntimeError("whisper.translationDevice=auto 는 실행 단계에서 허용하지 않습니다. cuda 또는 cpu를 명시하세요.")
        if normalized == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "whisper.translationDevice=cuda 이지만 torch CUDA를 사용할 수 없습니다. "
                    "CUDA 런타임과 현재 GPU를 지원하는 PyTorch/CUDA 빌드를 확인하세요."
                )
            _validate_torch_cuda_supports_current_gpu(torch)
        if normalized not in {"cpu", "cuda"}:
            raise RuntimeError(f"translation device는 cpu/cuda 중 하나여야 합니다. 설정값={device}")
        return normalized

    @staticmethod
    def _resolve_dtype(torch, compute_type: str, device: str):
        normalized = str(compute_type or "").strip().lower()
        if normalized == "auto":
            raise RuntimeError("whisper.translationComputeType=auto 는 실행 단계에서 허용하지 않습니다. float16 또는 float32를 명시하세요.")
        if normalized == "float16":
            if device != "cuda":
                raise RuntimeError("translation computeType=float16은 cuda 장치에서만 사용하세요. CPU에서는 float32를 설정하세요.")
            return torch.float16
        if normalized == "float32":
            return torch.float32
        if normalized == "int8":
            raise RuntimeError("whisper.translationComputeType=int8은 nllb-transformers에서 지원하지 않습니다. float16 또는 float32를 사용하세요.")
        raise RuntimeError(f"whisper.translationComputeType은 float16/float32 중 하나여야 합니다. 설정값={compute_type}")

    def translate(self, request: TranslationRequest) -> str:
        source = _nllb_language_code(request.source_language)
        target = _nllb_language_code(request.target_language)
        text = request.text.strip()
        if not text:
            return ""
        if source == target:
            return text
        try:
            self._tokenizer.src_lang = source
            encoded = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self._device)
            forced_bos_token_id = self._tokenizer.convert_tokens_to_ids(target)
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **encoded,
                    forced_bos_token_id=forced_bos_token_id,
                    **_nllb_generation_kwargs(self._beam_size, self._max_new_tokens),
                )
            return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
        except Exception as exc:
            detail = _translation_failure_detail(
                exc,
                model_name=self._model_name,
                device=self._requested_device,
                resolved_device=self._device,
                compute_type=self._requested_compute_type,
                source_language=request.source_language,
                target_language=request.target_language,
            )
            raise RuntimeError(detail) from exc


class M2M100TransformersTranslator(LocalTextTranslator):
    def __init__(self, model_name: str, device: str, compute_type: str, beam_size: int = 1, max_new_tokens: int = 128) -> None:
        if not model_name:
            raise RuntimeError("whisper.translationModel is required for m2m100-transformers")
        try:
            import torch
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "M2M100 번역 의존성이 없습니다. ./bin/avc setup을 실행해 transformers, torch, sentencepiece를 설치하세요. "
                f"설정값 translationBackend=m2m100-transformers translationModel={model_name}. 원인: {exc}"
            ) from exc

        resolved_device = NllbTransformersTranslator._resolve_device(torch, device)
        torch_dtype = NllbTransformersTranslator._resolve_dtype(torch, compute_type, resolved_device)
        self._model_name = model_name
        self._requested_device = str(device or "auto").strip()
        self._requested_compute_type = str(compute_type or "auto").strip()
        self._beam_size = _validate_generation_int("whisper.translationBeamSize", beam_size, 1, 8)
        self._max_new_tokens = _validate_generation_int("whisper.translationMaxNewTokens", max_new_tokens, 16, 512)
        try:
            self._tokenizer = M2M100Tokenizer.from_pretrained(model_name)
            self._model = M2M100ForConditionalGeneration.from_pretrained(model_name, torch_dtype=torch_dtype)
            self._model.to(resolved_device)
            self._model.eval()
        except Exception as exc:
            raise RuntimeError(
                "M2M100 번역 모델 로딩 실패: "
                f"translationModel={model_name} device={device} computeType={compute_type}. "
                "최초 실행이면 모델 다운로드가 필요합니다. CUDA/메모리/네트워크 상태를 확인하세요. "
                f"원인: {exc}"
            ) from exc
        self._torch = torch
        self._device = resolved_device

    def translate(self, request: TranslationRequest) -> str:
        source = _m2m100_language_code(request.source_language)
        target = _m2m100_language_code(request.target_language)
        text = request.text.strip()
        if not text:
            return ""
        if source == target:
            return text
        try:
            self._tokenizer.src_lang = source
            encoded = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self._device)
            forced_bos_token_id = self._tokenizer.get_lang_id(target)
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **encoded,
                    forced_bos_token_id=forced_bos_token_id,
                    **_translation_generation_kwargs(self._beam_size, self._max_new_tokens),
                )
            return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
        except Exception as exc:
            detail = _translation_failure_detail(
                exc,
                backend="M2M100",
                model_name=self._model_name,
                device=self._requested_device,
                resolved_device=self._device,
                compute_type=self._requested_compute_type,
                source_language=request.source_language,
                target_language=request.target_language,
            )
            raise RuntimeError(detail) from exc


def _nllb_generation_kwargs(beam_size: int, max_new_tokens: int) -> dict:
    return _translation_generation_kwargs(beam_size, max_new_tokens)


def _m2m100_generation_kwargs(beam_size: int, max_new_tokens: int) -> dict:
    return _translation_generation_kwargs(beam_size, max_new_tokens)


def _translation_generation_kwargs(beam_size: int, max_new_tokens: int) -> dict:
    return {
        "max_new_tokens": int(max_new_tokens),
        "num_beams": int(beam_size),
        "no_repeat_ngram_size": 3,
        "repetition_penalty": 1.15,
    }


def _validate_generation_int(name: str, value: int, minimum: int, maximum: int) -> int:
    try:
        normalized = int(value)
    except Exception as exc:
        raise RuntimeError(f"{name} must be an integer between {minimum} and {maximum}. 설정값={value}") from exc
    if not minimum <= normalized <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}. 설정값={value}")
    return normalized


def _torch_cuda_arch_tag(torch) -> str | None:
    try:
        major, minor = torch.cuda.get_device_capability()
    except Exception:
        return None
    return f"sm_{major}{minor}"


def _torch_supported_cuda_arches(torch) -> list[str]:
    try:
        return [str(item) for item in torch.cuda.get_arch_list()]
    except Exception:
        return []


def _torch_cuda_is_usable_for_current_gpu(torch) -> bool:
    if not torch.cuda.is_available():
        return False
    arch_tag = _torch_cuda_arch_tag(torch)
    supported_arches = _torch_supported_cuda_arches(torch)
    return torch.cuda.is_available() and (arch_tag is None or not supported_arches or arch_tag in supported_arches)


def _validate_torch_cuda_supports_current_gpu(torch) -> None:
    arch_tag = _torch_cuda_arch_tag(torch)
    supported_arches = _torch_supported_cuda_arches(torch)
    if arch_tag is None or not supported_arches or arch_tag in supported_arches:
        return
    device_name = "unknown"
    try:
        device_name = str(torch.cuda.get_device_name())
    except Exception:
        pass
    raise RuntimeError(
        "whisper.translationDevice=cuda 이지만 현재 PyTorch CUDA 빌드가 GPU 아키텍처를 지원하지 않습니다. "
        f"gpu={device_name} capability={arch_tag} supported={','.join(supported_arches)}. "
        "권장 조치: 현재 GPU 아키텍처를 지원하는 PyTorch/CUDA 빌드를 설치하세요."
    )


def _translation_failure_detail(
    exc: Exception,
    *,
    backend: str = "NLLB",
    model_name: str,
    device: str,
    resolved_device: str,
    compute_type: str,
    source_language: str,
    target_language: str,
) -> str:
    cause = str(exc)
    base = (
        f"{backend} 번역 실패: "
        f"source={source_language} target={target_language} "
        f"translationModel={model_name} translationDevice={device} "
        f"resolvedDevice={resolved_device} translationComputeType={compute_type}. "
    )
    if "no kernel image is available for execution on the device" in cause:
        return (
            base
            + "원인: 현재 torch/CUDA 빌드가 이 GPU 아키텍처의 CUDA 커널을 지원하지 않습니다. "
            + "권장 조치: 현재 GPU를 지원하는 torch/CUDA 빌드를 설치한 뒤 재시도하세요. "
            + f"원본 오류: {cause}"
        )
    return base + f"원인: {cause}"


def _nllb_language_code(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized not in NLLB_LANGUAGE_CODES:
        raise RuntimeError(f"NLLB 번역 언어는 en/ko/zh만 지원합니다. 설정값={language}")
    return NLLB_LANGUAGE_CODES[normalized]


def _m2m100_language_code(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized not in M2M100_LANGUAGE_CODES:
        raise RuntimeError(f"M2M100 번역 언어는 en/ko/zh만 지원합니다. 설정값={language}")
    return M2M100_LANGUAGE_CODES[normalized]


def build_text_translator(
    backend: str,
    model_name: str,
    device: str,
    compute_type: str,
    beam_size: int = 1,
    max_new_tokens: int = 128,
) -> LocalTextTranslator | None:
    normalized = str(backend or "whisper").strip().lower()
    if normalized == "whisper":
        return None
    if normalized == "mock":
        return MockTextTranslator()
    if normalized == "nllb-transformers":
        return NllbTransformersTranslator(model_name, device, compute_type, beam_size, max_new_tokens)
    if normalized == "m2m100-transformers":
        return M2M100TransformersTranslator(model_name, device, compute_type, beam_size, max_new_tokens)
    raise RuntimeError(f"지원하지 않는 whisper.translationBackend입니다: {backend}")

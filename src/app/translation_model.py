from __future__ import annotations

from dataclasses import dataclass


NLLB_LANGUAGE_CODES = {
    "en": "eng_Latn",
    "ko": "kor_Hang",
    "zh": "zho_Hans",
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
    def __init__(self, model_name: str, device: str, compute_type: str) -> None:
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
        normalized = str(device or "auto").strip().lower()
        if normalized == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if normalized == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("whisper.translationDevice=cuda 이지만 torch CUDA를 사용할 수 없습니다. CUDA 런타임을 확인하거나 translationDevice=cpu로 설정하세요.")
        if normalized not in {"cpu", "cuda"}:
            raise RuntimeError(f"translation device는 auto/cpu/cuda 중 하나여야 합니다. 설정값={device}")
        return normalized

    @staticmethod
    def _resolve_dtype(torch, compute_type: str, device: str):
        normalized = str(compute_type or "auto").strip().lower()
        if normalized == "auto":
            return torch.float16 if device == "cuda" else torch.float32
        if normalized == "float16":
            if device != "cuda":
                raise RuntimeError("translation computeType=float16은 cuda 장치에서만 사용하세요. CPU에서는 float32를 설정하세요.")
            return torch.float16
        if normalized == "float32":
            return torch.float32
        if normalized == "int8":
            raise RuntimeError("whisper.translationComputeType=int8은 nllb-transformers에서 지원하지 않습니다. float16 또는 float32를 사용하세요.")
        raise RuntimeError(f"whisper.translationComputeType은 auto/float16/float32 중 하나여야 합니다. 설정값={compute_type}")

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
                    max_new_tokens=256,
                    num_beams=4,
                )
            return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
        except Exception as exc:
            raise RuntimeError(
                "NLLB 번역 실패: "
                f"source={request.source_language} target={request.target_language}. 원인: {exc}"
            ) from exc


def _nllb_language_code(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized not in NLLB_LANGUAGE_CODES:
        raise RuntimeError(f"NLLB 번역 언어는 en/ko/zh만 지원합니다. 설정값={language}")
    return NLLB_LANGUAGE_CODES[normalized]


def build_text_translator(backend: str, model_name: str, device: str, compute_type: str) -> LocalTextTranslator | None:
    normalized = str(backend or "whisper").strip().lower()
    if normalized == "whisper":
        return None
    if normalized == "mock":
        return MockTextTranslator()
    if normalized == "nllb-transformers":
        return NllbTransformersTranslator(model_name, device, compute_type)
    raise RuntimeError(f"지원하지 않는 whisper.translationBackend입니다: {backend}")

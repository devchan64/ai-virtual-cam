#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.contracts.whisper import resolve_funasr_model_name
from src.domain.whisper_defaults import whisper_default


def _log(message: str) -> None:
    print(f"[ai-virtual-cam] {message}", flush=True)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def download_faster_whisper_model(model_name: str) -> None:
    _log(f"Downloading faster-whisper model: {model_name}")
    from faster_whisper.utils import download_model

    path = download_model(model_name)
    _log(f"faster-whisper model ready: {model_name} path={path}")


def download_sat_model(model_name: str) -> None:
    _log(f"Downloading SaT sentence boundary model: {model_name}")
    from wtpsplit import SaT

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*hf_xet\.download_files\(\) is deprecated.*",
            category=DeprecationWarning,
        )
        SaT(model_name)
    _log(f"SaT sentence boundary model ready: {model_name}")


def download_funasr_model(model_name: str) -> None:
    _log(f"Downloading FunASR punctuation model: {model_name}")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        from funasr import AutoModel

    resolved = resolve_funasr_model_name(model_name)
    if resolved != model_name:
        _log(f"Resolved FunASR punctuation model alias: {model_name} -> {resolved}")
    AutoModel(model=resolved, device="cpu", disable_update=True)
    _log(f"FunASR punctuation model ready: {model_name} resolved={resolved}")


def download_funasr_stt_model(model_name: str) -> None:
    _log(f"Downloading FunASR STT model: {model_name}")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        from funasr import AutoModel

    resolved = resolve_funasr_model_name(model_name)
    if resolved != model_name:
        _log(f"Resolved FunASR STT model alias: {model_name} -> {resolved}")
    AutoModel(model=resolved, device="cpu", disable_update=True)
    _log(f"FunASR STT model ready: {model_name} resolved={resolved}")


def download_nllb_model(model_name: str) -> None:
    _log(f"Downloading NLLB translation model: {model_name}")
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    AutoTokenizer.from_pretrained(model_name)
    AutoModelForSeq2SeqLM.from_pretrained(model_name)
    _log(f"NLLB translation model ready: {model_name}")


def download_m2m100_model(model_name: str) -> None:
    _log(f"Downloading M2M100 translation model: {model_name}")
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    M2M100Tokenizer.from_pretrained(model_name)
    M2M100ForConditionalGeneration.from_pretrained(model_name)
    _log(f"M2M100 translation model ready: {model_name}")


def download_translation_model(backend: str, model_name: str) -> None:
    normalized = str(backend or "").strip().lower()
    if normalized == "nllb-transformers":
        download_nllb_model(model_name)
        return
    if normalized == "m2m100-transformers":
        download_m2m100_model(model_name)
        return
    _log(f"Skipping translation model download for backend: {backend}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-download ai-virtual-cam Whisper/STT model assets")
    parser.add_argument("--skip-whisper", action="store_true", help="Skip faster-whisper model")
    parser.add_argument("--skip-boundary", action="store_true", help="Skip sentence boundary/post-processing models")
    parser.add_argument("--skip-translation", action="store_true", help="Skip translation model")
    parser.add_argument("--stt-backend", help="Download one explicit STT backend instead of all default STT models")
    parser.add_argument("--stt-model", help="Download one explicit STT model instead of all default STT models")
    parser.add_argument("--boundary-backend", help="Download one explicit sentence boundary backend instead of all defaults")
    parser.add_argument("--boundary-model", help="Download one explicit sentence boundary model instead of all defaults")
    parser.add_argument("--translation-backend", help="Download one explicit translation backend instead of the default")
    parser.add_argument("--translation-model", help="Download one explicit translation model instead of the default")
    args = parser.parse_args()

    if not args.skip_whisper:
        if args.stt_backend or args.stt_model:
            if not args.stt_backend or not args.stt_model:
                raise SystemExit("--stt-backend and --stt-model must be provided together")
            stt_backend_models = [(str(args.stt_backend), str(args.stt_model))]
        else:
            stt_backend_models = [
                (whisper_default("backend"), whisper_default("model")),
                (whisper_default("sttBackendEn"), whisper_default("sttModelEn")),
                (whisper_default("sttBackendKo"), whisper_default("sttModelKo")),
                (whisper_default("sttBackendZh"), whisper_default("sttModelZh")),
            ]
        for model_name in _unique([model for backend, model in stt_backend_models if backend == "faster-whisper"]):
            download_faster_whisper_model(model_name)
        for model_name in _unique([model for backend, model in stt_backend_models if backend.startswith("funasr-")]):
            download_funasr_stt_model(model_name)

    if not args.skip_boundary:
        if args.boundary_backend or args.boundary_model:
            if not args.boundary_backend or not args.boundary_model:
                raise SystemExit("--boundary-backend and --boundary-model must be provided together")
            backend_models = [(str(args.boundary_backend), str(args.boundary_model))]
        else:
            backend_models = [
                (whisper_default("sentenceBoundaryBackend"), whisper_default("sentenceBoundaryModel")),
                (whisper_default("sentenceBoundaryBackendEn"), whisper_default("sentenceBoundaryModelEn")),
                (whisper_default("sentenceBoundaryBackendKo"), whisper_default("sentenceBoundaryModelKo")),
                (whisper_default("sentenceBoundaryBackendZh"), whisper_default("sentenceBoundaryModelZh")),
            ]
        sat_models = _unique([model for backend, model in backend_models if backend == "sat"])
        funasr_models = _unique([model for backend, model in backend_models if backend == "funasr-ct-punc"])
        for model_name in sat_models:
            download_sat_model(model_name)
        for model_name in funasr_models:
            download_funasr_model(model_name)

    if not args.skip_translation:
        translation_backend = str(args.translation_backend or whisper_default("translationBackend"))
        translation_model = str(args.translation_model or whisper_default("translationModel"))
        download_translation_model(translation_backend, translation_model)

    _log("Whisper model pre-download completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

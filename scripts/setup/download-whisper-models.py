#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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

    AutoModel(model=model_name, device="cpu")
    _log(f"FunASR punctuation model ready: {model_name}")


def download_nllb_model(model_name: str) -> None:
    _log(f"Downloading NLLB translation model: {model_name}")
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    AutoTokenizer.from_pretrained(model_name)
    AutoModelForSeq2SeqLM.from_pretrained(model_name)
    _log(f"NLLB translation model ready: {model_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-download ai-virtual-cam Whisper/STT model assets")
    parser.add_argument("--skip-whisper", action="store_true", help="Skip faster-whisper model")
    parser.add_argument("--skip-boundary", action="store_true", help="Skip sentence boundary/post-processing models")
    parser.add_argument("--skip-translation", action="store_true", help="Skip translation model")
    args = parser.parse_args()

    if not args.skip_whisper:
        download_faster_whisper_model(str(whisper_default("model")))

    if not args.skip_boundary:
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
        download_nllb_model(str(whisper_default("translationModel")))

    _log("Whisper model pre-download completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

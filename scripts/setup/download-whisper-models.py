#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from dataclasses import dataclass

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


@dataclass(frozen=True)
class ModelAsset:
    kind: str
    backend: str
    model: str


def _asset_label(asset: ModelAsset) -> str:
    return f"{asset.kind}:{asset.backend}:{asset.model}"


def _modelscope_model_cache_dir(model_name: str) -> Path:
    return Path.home() / ".cache" / "modelscope" / "hub" / "models" / model_name


def _modelscope_legacy_cache_dir(model_name: str) -> Path:
    return Path.home() / ".cache" / "modelscope" / "hub" / model_name


def _is_funasr_model_cached(model_name: str) -> bool:
    resolved = resolve_funasr_model_name(model_name)
    candidates = (_modelscope_model_cache_dir(resolved), _modelscope_legacy_cache_dir(resolved))
    return any(path.exists() and any(path.iterdir()) for path in candidates)


def _is_hf_repo_cached(repo_id: str) -> bool:
    try:
        from huggingface_hub import scan_cache_dir
    except Exception:
        return False
    try:
        cache_info = scan_cache_dir()
    except Exception:
        return False
    normalized = str(repo_id or "").strip()
    return any(repo.repo_id == normalized or repo.repo_id.endswith(f"/{normalized}") for repo in cache_info.repos)


def check_faster_whisper_model(model_name: str) -> bool:
    try:
        from faster_whisper.utils import download_model

        download_model(model_name, local_files_only=True)
        return True
    except Exception:
        return False


def check_sat_model(model_name: str) -> bool:
    return _is_hf_repo_cached(model_name)


def check_translation_model(backend: str, model_name: str) -> bool:
    normalized = str(backend or "").strip().lower()
    if normalized == "nllb-transformers":
        try:
            from transformers import AutoConfig, AutoTokenizer

            AutoTokenizer.from_pretrained(model_name, local_files_only=True)
            AutoConfig.from_pretrained(model_name, local_files_only=True)
            return True
        except Exception:
            return False
    if normalized == "m2m100-transformers":
        try:
            from transformers import M2M100Tokenizer, AutoConfig

            M2M100Tokenizer.from_pretrained(model_name, local_files_only=True)
            AutoConfig.from_pretrained(model_name, local_files_only=True)
            return True
        except Exception:
            return False
    return True


def check_model_assets(assets: list[ModelAsset]) -> list[ModelAsset]:
    missing: list[ModelAsset] = []
    for asset in assets:
        backend = asset.backend.strip().lower()
        ready = True
        if asset.kind == "stt":
            if backend == "faster-whisper":
                ready = check_faster_whisper_model(asset.model)
            elif backend.startswith("funasr-"):
                ready = _is_funasr_model_cached(asset.model)
        elif asset.kind == "boundary":
            if backend == "sat":
                ready = check_sat_model(asset.model)
            elif backend == "funasr-ct-punc":
                ready = _is_funasr_model_cached(asset.model)
        elif asset.kind == "translation":
            ready = check_translation_model(asset.backend, asset.model)
        if ready:
            _log(f"Model cache ready: {_asset_label(asset)}")
        else:
            _log(f"Model cache missing: {_asset_label(asset)}")
            missing.append(asset)
    return missing


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
    parser.add_argument("--check-only", action="store_true", help="Only check local model cache and do not download")
    parser.add_argument("--stt-backend", action="append", help="Download an explicit STT backend. Repeat with --stt-model.")
    parser.add_argument("--stt-model", action="append", help="Download an explicit STT model. Repeat with --stt-backend.")
    parser.add_argument("--boundary-backend", action="append", help="Download an explicit sentence boundary backend. Repeat with --boundary-model.")
    parser.add_argument("--boundary-model", action="append", help="Download an explicit sentence boundary model. Repeat with --boundary-backend.")
    parser.add_argument("--translation-backend", action="append", help="Download an explicit translation backend. Repeat with --translation-model.")
    parser.add_argument("--translation-model", action="append", help="Download an explicit translation model. Repeat with --translation-backend.")
    args = parser.parse_args()

    assets: list[ModelAsset] = []

    if not args.skip_whisper:
        if args.stt_backend or args.stt_model:
            if not args.stt_backend or not args.stt_model or len(args.stt_backend) != len(args.stt_model):
                raise SystemExit("--stt-backend and --stt-model must be provided together the same number of times")
            stt_backend_models = list(zip([str(item) for item in args.stt_backend], [str(item) for item in args.stt_model]))
        else:
            stt_backend_models = [
                (whisper_default("backend"), whisper_default("model")),
                (whisper_default("sttBackendEn"), whisper_default("sttModelEn")),
                (whisper_default("sttBackendKo"), whisper_default("sttModelKo")),
                (whisper_default("sttBackendZh"), whisper_default("sttModelZh")),
            ]
        for item in _unique([f"{backend}\t{model}" for backend, model in stt_backend_models]):
            backend_name, model_name = item.split("\t", 1)
            assets.append(ModelAsset("stt", backend_name, model_name))

    if not args.skip_boundary:
        if args.boundary_backend or args.boundary_model:
            if not args.boundary_backend or not args.boundary_model or len(args.boundary_backend) != len(args.boundary_model):
                raise SystemExit("--boundary-backend and --boundary-model must be provided together the same number of times")
            backend_models = list(zip([str(item) for item in args.boundary_backend], [str(item) for item in args.boundary_model]))
        else:
            backend_models = [
                (whisper_default("sentenceBoundaryBackend"), whisper_default("sentenceBoundaryModel")),
                (whisper_default("sentenceBoundaryBackendEn"), whisper_default("sentenceBoundaryModelEn")),
                (whisper_default("sentenceBoundaryBackendKo"), whisper_default("sentenceBoundaryModelKo")),
                (whisper_default("sentenceBoundaryBackendZh"), whisper_default("sentenceBoundaryModelZh")),
            ]
        for item in _unique([f"{backend}\t{model}" for backend, model in backend_models]):
            backend_name, model_name = item.split("\t", 1)
            assets.append(ModelAsset("boundary", backend_name, model_name))

    if not args.skip_translation:
        if args.translation_backend or args.translation_model:
            if not args.translation_backend or not args.translation_model or len(args.translation_backend) != len(args.translation_model):
                raise SystemExit("--translation-backend and --translation-model must be provided together the same number of times")
            translation_backend_models = list(
                zip([str(item) for item in args.translation_backend], [str(item) for item in args.translation_model])
            )
        else:
            translation_backend_models = [(str(whisper_default("translationBackend")), str(whisper_default("translationModel")))]
        for item in _unique([f"{backend}\t{model}" for backend, model in translation_backend_models]):
            backend_name, model_name = item.split("\t", 1)
            assets.append(ModelAsset("translation", backend_name, model_name))

    if args.check_only:
        missing = check_model_assets(assets)
        if missing:
            _log("Whisper model cache check failed")
            return 3
        _log("Whisper model cache check completed")
        return 0

    for asset in assets:
        backend_name = asset.backend.strip().lower()
        if asset.kind == "stt":
            if backend_name == "faster-whisper":
                download_faster_whisper_model(asset.model)
            elif backend_name.startswith("funasr-"):
                download_funasr_stt_model(asset.model)
            else:
                _log(f"Skipping STT model download for backend: {asset.backend}")
        elif asset.kind == "boundary":
            if backend_name == "sat":
                download_sat_model(asset.model)
            elif backend_name == "funasr-ct-punc":
                download_funasr_model(asset.model)
            else:
                _log(f"Skipping sentence boundary model download for backend: {asset.backend}")
        elif asset.kind == "translation":
            download_translation_model(asset.backend, asset.model)

    _log("Whisper model pre-download completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

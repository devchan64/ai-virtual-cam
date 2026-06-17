#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import threading
import time
import warnings
from pathlib import Path
from dataclasses import dataclass

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.app.model_cache import (
    is_hf_repo_cached,
    is_qwen_asr_model_cached,
)
from src.domain.contracts.dictation_ai import resolve_qwen_asr_model_name
from src.domain.dictation_ai_defaults import dictation_ai_default


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


def _format_bytes(size: int | None) -> str:
    if size is None:
        return "unknown"
    value = float(max(0, size))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{value:.1f}TB"


def _directory_size(paths: list[Path]) -> int:
    total = 0
    seen: set[Path] = set()
    for root in paths:
        if not root.exists():
            continue
        try:
            files = root.rglob("*") if root.is_dir() else [root]
            for item in files:
                try:
                    resolved = item.resolve()
                    if resolved in seen or not item.is_file():
                        continue
                    seen.add(resolved)
                    total += item.stat().st_size
                except OSError:
                    continue
        except OSError:
            continue
    return total


def _hf_cache_dir(repo_id: str) -> Path:
    safe = str(repo_id or "").strip().replace("/", "--")
    return Path.home() / ".cache" / "huggingface" / "hub" / f"models--{safe}"


def _faster_whisper_repo_id(model_name: str) -> str:
    normalized = str(model_name or "").strip()
    if "/" in normalized:
        return normalized
    return f"Systran/faster-whisper-{normalized}"


def _sat_repo_id(model_name: str) -> str:
    normalized = str(model_name or "").strip()
    if "/" in normalized:
        return normalized
    return f"segment-any-text/{normalized}"


def _hf_model_total_size(repo_id: str) -> int | None:
    try:
        from huggingface_hub import model_info

        info = model_info(repo_id)
    except Exception:
        return None
    total = 0
    found = False
    for sibling in getattr(info, "siblings", []) or []:
        size = getattr(sibling, "size", None)
        if isinstance(size, int) and size > 0:
            found = True
            total += size
    return total if found else None



def _progress_monitor(label: str, paths: list[Path], total_size: int | None, stop_event: threading.Event) -> None:
    last_size = -1
    while not stop_event.wait(1.0):
        current_size = _directory_size(paths)
        if current_size == last_size:
            continue
        last_size = current_size
        if total_size and total_size > 0:
            percent = min(100.0, (current_size / total_size) * 100.0)
            _log(
                "Download progress: "
                f"{label} downloaded={_format_bytes(current_size)} total={_format_bytes(total_size)} percent={percent:.1f}"
            )
        else:
            _log(f"Download progress: {label} downloaded={_format_bytes(current_size)} total=unknown")


def _run_with_progress(label: str, paths: list[Path], total_size: int | None, action) -> None:
    stop_event = threading.Event()
    thread = threading.Thread(target=_progress_monitor, args=(label, paths, total_size, stop_event), daemon=True)
    thread.start()
    try:
        action()
    finally:
        stop_event.set()
        thread.join(timeout=1.5)
        current_size = _directory_size(paths)
        if total_size and total_size > 0:
            percent = min(100.0, (current_size / total_size) * 100.0)
            _log(
                "Download progress: "
                f"{label} downloaded={_format_bytes(current_size)} total={_format_bytes(total_size)} percent={percent:.1f}"
            )
        else:
            _log(f"Download progress: {label} downloaded={_format_bytes(current_size)} total=unknown")


def check_faster_whisper_model(model_name: str) -> bool:
    try:
        from faster_whisper.utils import download_model

        download_model(model_name, local_files_only=True)
        return True
    except Exception:
        return False


def check_sat_model(model_name: str) -> bool:
    return is_hf_repo_cached(model_name)


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
            elif backend in {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}:
                ready = is_qwen_asr_model_cached(asset.model)
            elif backend != "mock":
                ready = False
        elif asset.kind == "boundary":
            if backend == "sat":
                ready = check_sat_model(asset.model)
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

    repo_id = _faster_whisper_repo_id(model_name)
    total_size = _hf_model_total_size(repo_id)
    path_holder: dict[str, object] = {}

    def action() -> None:
        path_holder["path"] = download_model(model_name)

    _run_with_progress(f"faster-whisper:{model_name}", [_hf_cache_dir(repo_id)], total_size, action)
    _log(f"faster-whisper model ready: {model_name} path={path_holder.get('path')}")


def download_sat_model(model_name: str) -> None:
    _log(f"Downloading SaT sentence boundary model: {model_name}")
    from wtpsplit import SaT

    repo_id = _sat_repo_id(model_name)
    total_size = _hf_model_total_size(repo_id)

    def action() -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r".*hf_xet\.download_files\(\) is deprecated.*",
                category=DeprecationWarning,
            )
            SaT(model_name)

    _run_with_progress(f"sat:{model_name}", [_hf_cache_dir(repo_id)], total_size, action)
    _log(f"SaT sentence boundary model ready: {model_name} resolved={repo_id}")


def download_qwen_asr_model(model_name: str) -> None:
    resolved = resolve_qwen_asr_model_name(model_name)
    _log(f"Downloading Qwen3-ASR STT model: {model_name} resolved={resolved}")
    from huggingface_hub import snapshot_download

    total_size = _hf_model_total_size(resolved)

    def action() -> None:
        snapshot_download(resolved)

    _run_with_progress(f"qwen3-asr:{model_name}", [_hf_cache_dir(resolved)], total_size, action)
    _log(f"Qwen3-ASR STT model ready: {model_name} resolved={resolved}")


def download_nllb_model(model_name: str) -> None:
    _log(f"Downloading NLLB translation model: {model_name}")
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    total_size = _hf_model_total_size(model_name)

    def action() -> None:
        AutoTokenizer.from_pretrained(model_name)
        AutoModelForSeq2SeqLM.from_pretrained(model_name)

    _run_with_progress(f"nllb:{model_name}", [_hf_cache_dir(model_name)], total_size, action)
    _log(f"NLLB translation model ready: {model_name}")


def download_m2m100_model(model_name: str) -> None:
    _log(f"Downloading M2M100 translation model: {model_name}")
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    total_size = _hf_model_total_size(model_name)

    def action() -> None:
        M2M100Tokenizer.from_pretrained(model_name)
        M2M100ForConditionalGeneration.from_pretrained(model_name)

    _run_with_progress(f"m2m100:{model_name}", [_hf_cache_dir(model_name)], total_size, action)
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
                (dictation_ai_default("backend"), dictation_ai_default("model")),
                (dictation_ai_default("sttBackendEn"), dictation_ai_default("sttModelEn")),
                (dictation_ai_default("sttBackendKo"), dictation_ai_default("sttModelKo")),
                (dictation_ai_default("sttBackendZh"), dictation_ai_default("sttModelZh")),
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
                (dictation_ai_default("sentenceBoundaryBackend"), dictation_ai_default("sentenceBoundaryModel")),
                (dictation_ai_default("sentenceBoundaryBackendEn"), dictation_ai_default("sentenceBoundaryModelEn")),
                (dictation_ai_default("sentenceBoundaryBackendKo"), dictation_ai_default("sentenceBoundaryModelKo")),
                (dictation_ai_default("sentenceBoundaryBackendZh"), dictation_ai_default("sentenceBoundaryModelZh")),
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
            translation_backend_models = [(str(dictation_ai_default("translationBackend")), str(dictation_ai_default("translationModel")))]
        for item in _unique([f"{backend}\t{model}" for backend, model in translation_backend_models]):
            backend_name, model_name = item.split("\t", 1)
            assets.append(ModelAsset("translation", backend_name, model_name))

    if args.check_only:
        missing = check_model_assets(assets)
        if missing:
            _log("Dictation AI model cache check failed")
            return 3
        _log("Dictation AI model cache check completed")
        return 0

    for asset in assets:
        backend_name = asset.backend.strip().lower()
        if asset.kind == "stt":
            if backend_name == "faster-whisper":
                download_faster_whisper_model(asset.model)
            elif backend_name in {"qwen3-asr-transformers", "qwen3-asr-vllm-streaming"}:
                download_qwen_asr_model(asset.model)
            else:
                _log(f"Skipping STT model download for backend: {asset.backend}")
        elif asset.kind == "boundary":
            if backend_name == "sat":
                download_sat_model(asset.model)
            else:
                _log(f"Skipping sentence boundary model download for backend: {asset.backend}")
        elif asset.kind == "translation":
            download_translation_model(asset.backend, asset.model)

    _log("Dictation AI model pre-download completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

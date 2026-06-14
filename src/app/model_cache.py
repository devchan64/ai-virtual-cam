from __future__ import annotations

from pathlib import Path

from src.domain.contracts.whisper import resolve_funasr_model_name


def modelscope_model_cache_dir(model_name: str) -> Path:
    return Path.home() / ".cache" / "modelscope" / "hub" / "models" / model_name


def modelscope_legacy_cache_dir(model_name: str) -> Path:
    return Path.home() / ".cache" / "modelscope" / "hub" / model_name


def has_required_modelscope_files(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        files = [item for item in path.rglob("*") if item.is_file()]
    except OSError:
        return False
    if not files:
        return False
    names = {item.name for item in files}
    has_config = bool({"configuration.json", "config.json"} & names)
    weight_suffixes = {".bin", ".pt", ".pth", ".onnx", ".safetensors"}
    has_weights = any(item.suffix.lower() in weight_suffixes for item in files)
    return has_config and has_weights


def is_funasr_model_cached(model_name: str) -> bool:
    resolved = resolve_funasr_model_name(model_name)
    candidates = (modelscope_model_cache_dir(resolved), modelscope_legacy_cache_dir(resolved))
    return any(has_required_modelscope_files(path) for path in candidates)


def is_hf_repo_cached(repo_id: str) -> bool:
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


def require_funasr_model_cached(model_name: str, *, purpose: str) -> None:
    if is_funasr_model_cached(model_name):
        return
    resolved = resolve_funasr_model_name(model_name)
    raise RuntimeError(
        f"{purpose} 모델이 로컬 캐시에 없습니다: model={model_name} resolvedModel={resolved}. "
        "Serve 실행 중 다운로드는 허용하지 않습니다. config GUI의 모델 다운로드 안내창 또는 "
        "./bin/avc setup --download-whisper-models 로 먼저 다운로드하세요."
    )


def require_hf_repo_cached(model_name: str, *, purpose: str) -> None:
    if is_hf_repo_cached(model_name):
        return
    raise RuntimeError(
        f"{purpose} 모델이 로컬 캐시에 없습니다: model={model_name}. "
        "Serve 실행 중 다운로드는 허용하지 않습니다. config GUI의 모델 다운로드 안내창 또는 "
        "./bin/avc setup --download-whisper-models 로 먼저 다운로드하세요."
    )

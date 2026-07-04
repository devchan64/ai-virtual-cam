from __future__ import annotations

from pathlib import Path

from src.domain.contracts.dictation_ai import resolve_qwen_asr_model_name


def _hf_cache_dir(repo_id: str) -> Path:
    safe = str(repo_id or "").strip().replace("/", "--")
    return Path.home() / ".cache" / "huggingface" / "hub" / f"models--{safe}"


def _has_incomplete_hf_blobs(repo_id: str) -> bool:
    cache_dir = _hf_cache_dir(repo_id)
    if not cache_dir.exists():
        return False
    try:
        return any(cache_dir.rglob("*.incomplete"))
    except OSError:
        return True


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
    for repo in cache_info.repos:
        if repo.repo_id != normalized and not repo.repo_id.endswith(f"/{normalized}"):
            continue
        if _has_incomplete_hf_blobs(repo.repo_id):
            return False
        return True
    return False


def is_qwen_asr_model_cached(model_name: str) -> bool:
    return is_hf_repo_cached(resolve_qwen_asr_model_name(model_name))


def require_qwen_asr_model_cached(model_name: str, *, purpose: str) -> None:
    resolved = resolve_qwen_asr_model_name(model_name)
    if is_hf_repo_cached(resolved):
        return
    raise RuntimeError(
        f"{purpose} 모델이 로컬 캐시에 없습니다: model={model_name} resolvedModel={resolved}. "
        "Serve 실행 중 다운로드는 허용하지 않습니다. config GUI의 모델 다운로드 매니저에서 먼저 다운로드하세요."
    )


def require_hf_repo_cached(model_name: str, *, purpose: str) -> None:
    if is_hf_repo_cached(model_name):
        return
    raise RuntimeError(
        f"{purpose} 모델이 로컬 캐시에 없습니다: model={model_name}. "
        "Serve 실행 중 다운로드는 허용하지 않습니다. config GUI의 모델 다운로드 매니저에서 먼저 다운로드하세요."
    )

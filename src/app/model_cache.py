from __future__ import annotations

from src.domain.contracts.dictation_ai import resolve_qwen_asr_model_name


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


def is_qwen_asr_model_cached(model_name: str) -> bool:
    return is_hf_repo_cached(resolve_qwen_asr_model_name(model_name))


def require_qwen_asr_model_cached(model_name: str, *, purpose: str) -> None:
    resolved = resolve_qwen_asr_model_name(model_name)
    if is_hf_repo_cached(resolved):
        return
    raise RuntimeError(
        f"{purpose} 모델이 로컬 캐시에 없습니다: model={model_name} resolvedModel={resolved}. "
        "Serve 실행 중 다운로드는 허용하지 않습니다. config GUI의 모델 다운로드 안내창에서 먼저 다운로드하세요."
    )


def require_hf_repo_cached(model_name: str, *, purpose: str) -> None:
    if is_hf_repo_cached(model_name):
        return
    raise RuntimeError(
        f"{purpose} 모델이 로컬 캐시에 없습니다: model={model_name}. "
        "Serve 실행 중 다운로드는 허용하지 않습니다. config GUI의 모델 다운로드 안내창에서 먼저 다운로드하세요."
    )

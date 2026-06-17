from __future__ import annotations

import os

CJK_REVISION_SHORT_MAX_UNITS = 4
CJK_REVISION_MAX_LENGTH_DELTA = 4
CJK_REVISION_RATIO_MIN = 0.78
CJK_REVISION_COMMON_RUN_MIN = 3
CJK_REVISION_COVERAGE_MIN = 0.75
CJK_REVISION_FALLBACK_RATIO_MIN = 0.70
CJK_CONFIRM_PRESERVE_RATIO_MIN = 0.72
CJK_CONFIRM_PRESERVE_COMMON_RUN_MIN = 3
CJK_CONFIRM_PRESERVE_COVERAGE_MIN = 0.70
REVISION_TAIL_COMMON_RUN_MIN = 8
REVISION_TAIL_BEST_J_MAX = 3
REVISION_PREFIX_RUN_MIN = 5
REVISION_PREFIX_COMMON_RUN_MIN = 5
REVISION_FALLBACK_COMMON_RUN_MIN = 4
REVISION_FALLBACK_COVERAGE_MIN = 0.60


def _revision_env_int(name: str, default: int) -> int:
    env_name = f"AVC_DICTATION_{name}"
    value = os.environ.get(env_name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(f"{env_name} must be a non-negative integer, got {value!r}") from None
    if parsed < 0:
        raise ValueError(f"{env_name} must be a non-negative integer, got {value!r}")
    return parsed


def _revision_env_float(name: str, default: float) -> float:
    env_name = f"AVC_DICTATION_{name}"
    value = os.environ.get(env_name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"{env_name} must be a float between 0.0 and 1.0, got {value!r}") from None
    if not 0.0 <= parsed <= 1.0:
        raise ValueError(f"{env_name} must be a float between 0.0 and 1.0, got {value!r}")
    return parsed


def cjk_revision_short_max_units() -> int:
    return _revision_env_int("CJK_REVISION_SHORT_MAX_UNITS", CJK_REVISION_SHORT_MAX_UNITS)


def cjk_revision_max_length_delta() -> int:
    return _revision_env_int("CJK_REVISION_MAX_LENGTH_DELTA", CJK_REVISION_MAX_LENGTH_DELTA)


def cjk_revision_ratio_min() -> float:
    return _revision_env_float("CJK_REVISION_RATIO_MIN", CJK_REVISION_RATIO_MIN)


def cjk_revision_common_run_min() -> int:
    return _revision_env_int("CJK_REVISION_COMMON_RUN_MIN", CJK_REVISION_COMMON_RUN_MIN)


def cjk_revision_coverage_min() -> float:
    return _revision_env_float("CJK_REVISION_COVERAGE_MIN", CJK_REVISION_COVERAGE_MIN)


def cjk_revision_fallback_ratio_min() -> float:
    return _revision_env_float("CJK_REVISION_FALLBACK_RATIO_MIN", CJK_REVISION_FALLBACK_RATIO_MIN)


def cjk_confirm_preserve_ratio_min() -> float:
    return _revision_env_float("CJK_CONFIRM_PRESERVE_RATIO_MIN", CJK_CONFIRM_PRESERVE_RATIO_MIN)


def cjk_confirm_preserve_common_run_min() -> int:
    return _revision_env_int("CJK_CONFIRM_PRESERVE_COMMON_RUN_MIN", CJK_CONFIRM_PRESERVE_COMMON_RUN_MIN)


def cjk_confirm_preserve_coverage_min() -> float:
    return _revision_env_float("CJK_CONFIRM_PRESERVE_COVERAGE_MIN", CJK_CONFIRM_PRESERVE_COVERAGE_MIN)


def revision_tail_common_run_min() -> int:
    return _revision_env_int("REVISION_TAIL_COMMON_RUN_MIN", REVISION_TAIL_COMMON_RUN_MIN)


def revision_tail_best_j_max() -> int:
    return _revision_env_int("REVISION_TAIL_BEST_J_MAX", REVISION_TAIL_BEST_J_MAX)


def revision_prefix_run_min() -> int:
    return _revision_env_int("REVISION_PREFIX_RUN_MIN", REVISION_PREFIX_RUN_MIN)


def revision_prefix_common_run_min() -> int:
    return _revision_env_int("REVISION_PREFIX_COMMON_RUN_MIN", REVISION_PREFIX_COMMON_RUN_MIN)


def revision_fallback_common_run_min() -> int:
    return _revision_env_int("REVISION_FALLBACK_COMMON_RUN_MIN", REVISION_FALLBACK_COMMON_RUN_MIN)


def revision_fallback_coverage_min() -> float:
    return _revision_env_float("REVISION_FALLBACK_COVERAGE_MIN", REVISION_FALLBACK_COVERAGE_MIN)


def revision_similarity_policy() -> dict[str, int | float]:
    return {
        "cjk_revision_short_max_units": cjk_revision_short_max_units(),
        "cjk_revision_max_length_delta": cjk_revision_max_length_delta(),
        "cjk_revision_ratio_min": cjk_revision_ratio_min(),
        "cjk_revision_common_run_min": cjk_revision_common_run_min(),
        "cjk_revision_coverage_min": cjk_revision_coverage_min(),
        "cjk_revision_fallback_ratio_min": cjk_revision_fallback_ratio_min(),
        "cjk_confirm_preserve_ratio_min": cjk_confirm_preserve_ratio_min(),
        "cjk_confirm_preserve_common_run_min": cjk_confirm_preserve_common_run_min(),
        "cjk_confirm_preserve_coverage_min": cjk_confirm_preserve_coverage_min(),
        "revision_tail_common_run_min": revision_tail_common_run_min(),
        "revision_tail_best_j_max": revision_tail_best_j_max(),
        "revision_prefix_run_min": revision_prefix_run_min(),
        "revision_prefix_common_run_min": revision_prefix_common_run_min(),
        "revision_fallback_common_run_min": revision_fallback_common_run_min(),
        "revision_fallback_coverage_min": revision_fallback_coverage_min(),
    }

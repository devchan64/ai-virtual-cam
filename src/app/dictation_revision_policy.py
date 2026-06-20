from __future__ import annotations

# 호환성 shim. 받아쓰기 AI 튜닝값은 dictation_pipeline_settings.py로 통합했다.
# 기존 import가 계속 동작하도록 이 모듈을 유지하되, 새 코드는 통합 정책
# 모듈에서 설정을 import한다.

from src.app.dictation_pipeline_settings import (
    CJK_CONFIRM_PRESERVE_COMMON_RUN_MIN,
    CJK_CONFIRM_PRESERVE_COVERAGE_MIN,
    CJK_CONFIRM_PRESERVE_RATIO_MIN,
    CJK_REVISION_COMMON_RUN_MIN,
    CJK_REVISION_COVERAGE_MIN,
    CJK_REVISION_FALLBACK_RATIO_MIN,
    CJK_REVISION_MAX_LENGTH_DELTA,
    CJK_REVISION_RATIO_MIN,
    CJK_REVISION_SHORT_MAX_UNITS,
    REVISION_FALLBACK_COMMON_RUN_MIN,
    REVISION_FALLBACK_COVERAGE_MIN,
    REVISION_PREFIX_COMMON_RUN_MIN,
    REVISION_PREFIX_RUN_MIN,
    REVISION_TAIL_BEST_J_MAX,
    REVISION_TAIL_COMMON_RUN_MIN,
    cjk_confirm_preserve_common_run_min,
    cjk_confirm_preserve_coverage_min,
    cjk_confirm_preserve_ratio_min,
    cjk_revision_common_run_min,
    cjk_revision_coverage_min,
    cjk_revision_fallback_ratio_min,
    cjk_revision_max_length_delta,
    cjk_revision_ratio_min,
    cjk_revision_short_max_units,
    revision_fallback_common_run_min,
    revision_fallback_coverage_min,
    revision_prefix_common_run_min,
    revision_prefix_run_min,
    revision_similarity_policy,
    revision_tail_best_j_max,
    revision_tail_common_run_min,
)

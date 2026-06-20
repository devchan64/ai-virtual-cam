from __future__ import annotations

import os

from src.domain.dictation_ai_defaults import dictation_ai_default

# 받아쓰기 AI 파이프라인 튜닝 가이드
#
# 이 모듈은 실시간 STT 동작을 바꾸는 런타임 상수의 단일 온보딩 지점이다.
# 알고리즘 코드는 pipeline/transcript 모듈에 두고, 벤치로 튜닝한 임계값은
# 여기에 모아 이후 튜닝에서 이 파일과 실험일지를 함께 비교할 수 있게 한다.
#
# 튜닝 규칙:
# - 벤치 한 번에는 가능하면 값 하나만 바꾼다.
# - 언어별 문구 규칙을 여기에 추가하지 않는다.
# - final 확정, revision 매칭, 중복 억제에 영향을 주는 값을 바꾸면
#   CUDA/AI 벤치 결과를 실험일지에 남긴다.


# 오디오/입력 런타임
SAMPLE_RATE = 16000
INPUT_AUDIO_QUEUE_MAX_SIZE = 120
INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS = 0.2
PULSE_CAPTURE_BLOCK_SECONDS = 0.2


# 커밋 버퍼와 최근 final 메모리
#
# RECENT_TRANSCRIPT_WINDOW는 echo/delta 억제를 위해 final 텍스트를 얼마나
# 오래 참조할지 정한다. 값을 키우면 중복 final 후보를 더 많이 잡지만,
# 실제로 다시 말한 반복 문구까지 과하게 잘라낼 수 있다.
RECENT_TRANSCRIPT_WINDOW = 8
MAX_RECENT_SHORT_TEXT_REPEATS = 2

# MAX_STAGED_SENTENCE_QUEUE는 현재 active staged 문장을 아직 소비할 수 없을
# 때 생성순서 후보를 보존한다. 값을 키우면 SBD 출력이 몰릴 때 final 누락은
# 줄 수 있지만 stale 후보 churn은 늘어난다.
MAX_STAGED_SENTENCE_QUEUE = 12

# empty/no-speech STT chunk는 final 확정 근거가 아니다. 이 임계값은 no-text
# chunk가 반복될 때 미확정 staged 후보를 폐기하는 데만 쓰며, 이 값만으로
# 텍스트를 final 확정해서는 안 된다.
NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS = 6


# 문장 생명주기 final 확정
#
# SENTENCE_CONFIRM_CHUNKS는 지연과 중복 사이의 핵심 절충값이다. 낮추면 더
# 빨리 final이 나오고 누락이 줄지만, 높이면 반복 근거를 더 기다려 premature
# final 위험을 줄인다.
SENTENCE_CONFIRM_CHUNKS = 2
FORCED_SENTENCE_CONFIRM_CHUNKS = 3

# age는 정확한 confirmation을 계속 받지 못하는 staged 후보의 보조 확정
# 장치다. GUI의 sentenceFinalizeAge 계약과 가깝게 유지해야 한다.
SENTENCE_CONFIRM_MAX_AGE_CHUNKS = 3
FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS = 4


# pending tail 품질
#
# pending overrun 지표는 커밋 버퍼 이전에서 멈춘 텍스트를 찾기 위한 것이다.
# 이 값들은 관측/억제 임계값이며 final 출력을 강제하는 근거가 아니다.
MAX_PENDING_SENTENCE_CHARS = 180
PENDING_OVERRUN_CHUNKS = 8
FAST_PENDING_OVERRUN_CHARS = 240
FAST_PENDING_OVERRUN_CHUNKS = 4
SLOW_PENDING_SENTENCE_CHUNKS = 4
SLOW_PENDING_SENTENCE_CHARS = 45
SLOW_PENDING_MAX_SENTENCE_CHARS = 120
SLOW_PENDING_MAX_CHARS_PER_CHUNK = 18.0


# 후보 품질 게이트
#
# 이 임계값들은 낮은 가치의 조각이 stage/final 텍스트가 되는 것을 막는다.
# 구조적 기준으로만 유지하고, 관측된 단어나 문구를 여기에 넣지 않는다.
SHORT_CJK_FINAL_UNITS = 10
SHORT_NO_END_FRAGMENT_UNITS = 4
SHORT_CJK_REPLACEMENT_HOLD_CHUNKS = 2


# revision confirmation 보존
#
# internal stability는 같은 문장이 sliding window 내부에서 안정적이지만 단순
# prefix/suffix overlap이 없을 때 CJK revision의 confirmation 근거를 보존한다.
CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO = 0.60
CJK_REVISION_INTERNAL_STABILITY_MID_RATIO = 0.40
CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS = 40


# revision 유사도 정책
#
# 이 값들은 두 문장 후보가 같은 발화 구간을 나타내는지 판단한다. 로컬 벤치
# sweep에서는 AVC_DICTATION_<NAME>으로 override할 수 있다. 운영 기본값은
# 더 나은 CUDA/AI 벤치 결과가 실험일지에 기록되기 전까지 checked-in 값을 쓴다.
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


# 벤치 결과 해석
#
# SBD 벤치 기본값은 받아쓰기 AI 계약 기본값을 참조한다. 운영 기본값이
# 바뀌면 벤치도 같은 기준을 따라가야 하며, CPU/mock/smoke 경로의 벤치
# 데이터는 받아쓰기 AI 품질 튜닝 근거로 유효하지 않다.
SBD_BENCHMARK_BACKEND = str(dictation_ai_default("sentenceBoundaryBackend")).strip()
SBD_BENCHMARK_MODEL = str(dictation_ai_default("sentenceBoundaryModel")).strip()
SBD_BENCHMARK_DEVICE = str(dictation_ai_default("sentenceBoundaryDevice")).strip()
SBD_BENCHMARK_COMPUTE_TYPE = str(dictation_ai_default("sentenceBoundaryComputeType")).strip()

# 벤치는 expected/actual final 문장을 token-sentence similarity로 비교한다.
# 0.70은 STT 표기/고유명사 흔들림을 false miss로 보지 않게 하면서, 튜닝 중
# 너무 느슨하다고 확인한 0.55 범위는 피하는 기준이다.
FINAL_SENTENCE_MATCH_MIN_SIMILARITY = 0.70


def _dictation_env_int(name: str, default: int) -> int:
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


def _dictation_env_float(name: str, default: float) -> float:
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
    return _dictation_env_int("CJK_REVISION_SHORT_MAX_UNITS", CJK_REVISION_SHORT_MAX_UNITS)


def cjk_revision_max_length_delta() -> int:
    return _dictation_env_int("CJK_REVISION_MAX_LENGTH_DELTA", CJK_REVISION_MAX_LENGTH_DELTA)


def cjk_revision_ratio_min() -> float:
    return _dictation_env_float("CJK_REVISION_RATIO_MIN", CJK_REVISION_RATIO_MIN)


def cjk_revision_common_run_min() -> int:
    return _dictation_env_int("CJK_REVISION_COMMON_RUN_MIN", CJK_REVISION_COMMON_RUN_MIN)


def cjk_revision_coverage_min() -> float:
    return _dictation_env_float("CJK_REVISION_COVERAGE_MIN", CJK_REVISION_COVERAGE_MIN)


def cjk_revision_fallback_ratio_min() -> float:
    return _dictation_env_float("CJK_REVISION_FALLBACK_RATIO_MIN", CJK_REVISION_FALLBACK_RATIO_MIN)


def cjk_confirm_preserve_ratio_min() -> float:
    return _dictation_env_float("CJK_CONFIRM_PRESERVE_RATIO_MIN", CJK_CONFIRM_PRESERVE_RATIO_MIN)


def cjk_confirm_preserve_common_run_min() -> int:
    return _dictation_env_int("CJK_CONFIRM_PRESERVE_COMMON_RUN_MIN", CJK_CONFIRM_PRESERVE_COMMON_RUN_MIN)


def cjk_confirm_preserve_coverage_min() -> float:
    return _dictation_env_float("CJK_CONFIRM_PRESERVE_COVERAGE_MIN", CJK_CONFIRM_PRESERVE_COVERAGE_MIN)


def revision_tail_common_run_min() -> int:
    return _dictation_env_int("REVISION_TAIL_COMMON_RUN_MIN", REVISION_TAIL_COMMON_RUN_MIN)


def revision_tail_best_j_max() -> int:
    return _dictation_env_int("REVISION_TAIL_BEST_J_MAX", REVISION_TAIL_BEST_J_MAX)


def revision_prefix_run_min() -> int:
    return _dictation_env_int("REVISION_PREFIX_RUN_MIN", REVISION_PREFIX_RUN_MIN)


def revision_prefix_common_run_min() -> int:
    return _dictation_env_int("REVISION_PREFIX_COMMON_RUN_MIN", REVISION_PREFIX_COMMON_RUN_MIN)


def revision_fallback_common_run_min() -> int:
    return _dictation_env_int("REVISION_FALLBACK_COMMON_RUN_MIN", REVISION_FALLBACK_COMMON_RUN_MIN)


def revision_fallback_coverage_min() -> float:
    return _dictation_env_float("REVISION_FALLBACK_COVERAGE_MIN", REVISION_FALLBACK_COVERAGE_MIN)


def dictation_pipeline_policy() -> dict[str, int | float]:
    return {
        "recent_transcript_window": RECENT_TRANSCRIPT_WINDOW,
        "max_staged_sentence_queue": MAX_STAGED_SENTENCE_QUEUE,
        "no_text_stale_stage_suppress_chunks": NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS,
        "sentence_confirm_chunks": SENTENCE_CONFIRM_CHUNKS,
        "forced_sentence_confirm_chunks": FORCED_SENTENCE_CONFIRM_CHUNKS,
        "sentence_confirm_max_age_chunks": SENTENCE_CONFIRM_MAX_AGE_CHUNKS,
        "forced_sentence_confirm_max_age_chunks": FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS,
        "max_pending_sentence_chars": MAX_PENDING_SENTENCE_CHARS,
        "pending_overrun_chunks": PENDING_OVERRUN_CHUNKS,
        "fast_pending_overrun_chars": FAST_PENDING_OVERRUN_CHARS,
        "fast_pending_overrun_chunks": FAST_PENDING_OVERRUN_CHUNKS,
        "slow_pending_sentence_chunks": SLOW_PENDING_SENTENCE_CHUNKS,
        "slow_pending_sentence_chars": SLOW_PENDING_SENTENCE_CHARS,
        "slow_pending_max_sentence_chars": SLOW_PENDING_MAX_SENTENCE_CHARS,
        "slow_pending_max_chars_per_chunk": SLOW_PENDING_MAX_CHARS_PER_CHUNK,
        "short_cjk_final_units": SHORT_CJK_FINAL_UNITS,
        "short_no_end_fragment_units": SHORT_NO_END_FRAGMENT_UNITS,
        "short_cjk_replacement_hold_chunks": SHORT_CJK_REPLACEMENT_HOLD_CHUNKS,
        "cjk_revision_internal_stability_min_ratio": CJK_REVISION_INTERNAL_STABILITY_MIN_RATIO,
        "cjk_revision_internal_stability_mid_ratio": CJK_REVISION_INTERNAL_STABILITY_MID_RATIO,
        "cjk_revision_internal_stability_min_chars": CJK_REVISION_INTERNAL_STABILITY_MIN_CHARS,
        "sbd_benchmark_backend": SBD_BENCHMARK_BACKEND,
        "sbd_benchmark_model": SBD_BENCHMARK_MODEL,
        "sbd_benchmark_device": SBD_BENCHMARK_DEVICE,
        "sbd_benchmark_compute_type": SBD_BENCHMARK_COMPUTE_TYPE,
        "final_sentence_match_min_similarity": FINAL_SENTENCE_MATCH_MIN_SIMILARITY,
    }


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

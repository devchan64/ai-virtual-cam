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
# - 케이스는 앱 로그에서 수집한 실패 replay를 사람이 검토해 승격한다.
# - 파라미터 비교는 같은 reviewed case 집합에서 수행한다.
# - final 확정, revision 매칭, 중복 억제에 영향을 주는 값을 바꾸면
#   CUDA/AI 벤치 결과와 precision/recall trade-off를 실험일지에 남긴다.
# - AVC_DICTATION_* override는 로컬 sweep 용도다. 운영 기본값은 벤치 근거가
#   실험일지에 기록된 뒤 이 파일의 checked-in 상수로 반영한다.


# 오디오/입력 런타임
SAMPLE_RATE = 16000
INPUT_AUDIO_QUEUE_MAX_SIZE = 120
INPUT_AUDIO_QUEUE_TIMEOUT_SECONDS = 0.2
PULSE_CAPTURE_BLOCK_SECONDS = 0.2


# STT backend 호출 계약
#
# serve 실행에서 Whisper 계열 STT는 항상 전사만 수행한다. 번역은 final 문장만
# 별도 번역 큐에서 처리하므로 backend 호출 task를 암묵적으로 바꾸지 않는다.
STT_TRANSCRIBE_TASK = "transcribe"
STT_WITHOUT_TIMESTAMPS = True
STT_CONDITION_ON_PREVIOUS_TEXT = False
STT_STREAM_AUDIO_DTYPE = "float32"


# STT segment 품질 게이트
#
# faster-whisper류 backend가 반환하는 segment 단위 신뢰도 필터다. 낮추면
# 잔류 오디오/환청성 텍스트가 들어올 위험이 커지고, 높이면 실제 발화의
# 일부가 누락될 수 있다. no_speech override는 CJK 긴 발화에서 no_speech
# 확률이 높게 붙는 경우를 보수적으로 살리기 위한 구조적 예외다.
SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES = frozenset({"zh"})
MIN_SEGMENT_AVG_LOGPROB = -1.0
MAX_SEGMENT_NO_SPEECH_PROB = 0.75
MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB = 0.90
MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE = 12
SEGMENT_LOGPROB_SCORE_OFFSET = 1.5
SEGMENT_LOGPROB_SCORE_SCALE = 1.4
SEGMENT_LOGPROB_CONFIDENCE_WEIGHT = 0.7
SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT = 0.3
CJK_CHAR_RANGES = (("\u3400", "\u9fff"), ("\uf900", "\ufaff"))


# 커밋 버퍼와 최근 final 메모리
#
# RECENT_TRANSCRIPT_WINDOW는 echo/delta 억제를 위해 final 텍스트를 얼마나
# 오래 참조할지 정한다. 값을 키우면 중복 final 후보를 더 많이 잡지만,
# 실제로 다시 말한 반복 문구까지 과하게 잘라낼 수 있다.
RECENT_TRANSCRIPT_WINDOW = 8
MAX_RECENT_SHORT_TEXT_REPEATS = 2

# 이미 확정된 final이 후속 window에서 더 긴 문장 prefix로 다시 등장할 때
# suffix만 새 후보로 회수하는 보수 조건이다. CJK는 3글자 수준의 짧은
# 목적어/보어 확장도 번역 단위를 바꿀 수 있어 3 unit 이상부터 회수한다.
RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS = 8
RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS = 3

# MAX_STAGED_SENTENCE_QUEUE는 현재 active staged 문장을 아직 소비할 수 없을
# 때 생성순서 후보를 보존한다. 값을 키우면 SBD 출력이 몰릴 때 final 누락은
# 줄 수 있지만 stale 후보 churn은 늘어난다.
MAX_STAGED_SENTENCE_QUEUE = 20

# queued stage 후보가 너무 늦게 승격되면 현재 sliding window와 의미상 멀어진
# stale 문장이 final로 나갈 수 있다. 6 chunk는 오래된 queue 후보만 폐기해
# 생성순서 보존과 stale final 억제 사이의 절충을 둔다.
STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS = 6

# empty/no-speech STT chunk는 final 확정 근거가 아니다. 이 임계값은 no-text
# chunk가 반복될 때 미확정 staged 후보를 폐기하는 데만 쓰며, 이 값만으로
# 텍스트를 final 확정해서는 안 된다.
NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS = 6

# broken delta final을 보류할 때 active staged 후보를 잠시 유지해 후속 window
# revision으로 회복할 기회를 준다. 다만 같은 staged 후보가 여러 chunk 동안
# 같은 broken delta만 만들면 queue를 막아 누락을 만든다.
DELTA_SUPPRESSED_STAGE_MAX_CHUNKS = 2


# 문장 생명주기 final 확정
#
# SENTENCE_CONFIRM_CHUNKS는 지연과 중복 사이의 핵심 절충값이다. 낮추면 더
# 빨리 final이 나오고 누락이 줄지만, 높이면 반복 근거를 더 기다려 premature
# final 위험을 줄인다.
SENTENCE_CONFIRM_CHUNKS = 1
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
SHORT_NO_END_FRAGMENT_UNITS = 5
SHORT_CJK_REPLACEMENT_HOLD_CHUNKS = 2

# 짧은 CJK 후보는 문장부호가 있어도 다음 window에서 긴 문장으로 확장되는
# 경우가 많다. final을 막지는 않고 기본 confirmation보다 1회 더 관측해
# premature fragment final을 줄인다.
SHORT_CJK_CONFIRM_EXTRA_CHUNKS = 1

# 중국어 window에서 라틴 토큰과 1~2글자 CJK suffix만 붙은 짧은 조각은
# 고유명사/브랜드명의 불완전한 STT 후보인 경우가 많다. 전체 mixed-latin
# 문장을 막지는 않고, active stage head를 점유하기 쉬운 매우 짧은 조각만
# stage 진입 전에 차단한다.
SHORT_MIXED_LATIN_ZH_CJK_UNITS = 2
SHORT_MIXED_LATIN_ZH_TOTAL_UNITS = 5


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
REVISION_FALLBACK_COVERAGE_MIN = 0.55


# 벤치 결과 해석
#
# SBD 벤치 기본값은 받아쓰기 AI 계약 기본값을 참조한다. 운영 기본값이
# 바뀌면 벤치도 같은 기준을 따라가야 하며, CPU/mock/smoke 경로의 벤치
# 데이터는 받아쓰기 AI 품질 튜닝 근거로 유효하지 않다.
PAPER_EVIDENCE_REVIEWED_FINALIZATION_CASE_TARGET = 1000
PAPER_EVIDENCE_CASE_SOURCE = "app-log-reviewed-finalization-cases"
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


def max_staged_sentence_queue() -> int:
    return _dictation_env_int("MAX_STAGED_SENTENCE_QUEUE", MAX_STAGED_SENTENCE_QUEUE)


def staged_queue_max_promotion_age_chunks() -> int:
    return max(1, _dictation_env_int("STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS", STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS))


def no_text_stale_stage_suppress_chunks() -> int:
    return _dictation_env_int("NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS", NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS)


def delta_suppressed_stage_max_chunks() -> int:
    return _dictation_env_int("DELTA_SUPPRESSED_STAGE_MAX_CHUNKS", DELTA_SUPPRESSED_STAGE_MAX_CHUNKS)


def recent_final_extension_min_prefix_units() -> int:
    return _dictation_env_int("RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS", RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS)


def recent_final_extension_min_suffix_units() -> int:
    return _dictation_env_int("RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS", RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS)


def sentence_confirm_chunks() -> int:
    return max(1, _dictation_env_int("SENTENCE_CONFIRM_CHUNKS", SENTENCE_CONFIRM_CHUNKS))


def forced_sentence_confirm_chunks() -> int:
    return max(1, _dictation_env_int("FORCED_SENTENCE_CONFIRM_CHUNKS", FORCED_SENTENCE_CONFIRM_CHUNKS))


def sentence_confirm_max_age_chunks() -> int:
    return max(1, _dictation_env_int("SENTENCE_CONFIRM_MAX_AGE_CHUNKS", SENTENCE_CONFIRM_MAX_AGE_CHUNKS))


def forced_sentence_confirm_max_age_chunks() -> int:
    return max(1, _dictation_env_int("FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS", FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS))


def short_cjk_final_units() -> int:
    return _dictation_env_int("SHORT_CJK_FINAL_UNITS", SHORT_CJK_FINAL_UNITS)


def short_no_end_fragment_units() -> int:
    return _dictation_env_int("SHORT_NO_END_FRAGMENT_UNITS", SHORT_NO_END_FRAGMENT_UNITS)


def short_cjk_replacement_hold_chunks() -> int:
    return _dictation_env_int("SHORT_CJK_REPLACEMENT_HOLD_CHUNKS", SHORT_CJK_REPLACEMENT_HOLD_CHUNKS)


def short_cjk_confirm_extra_chunks() -> int:
    return _dictation_env_int("SHORT_CJK_CONFIRM_EXTRA_CHUNKS", SHORT_CJK_CONFIRM_EXTRA_CHUNKS)


def short_mixed_latin_zh_cjk_units() -> int:
    return _dictation_env_int("SHORT_MIXED_LATIN_ZH_CJK_UNITS", SHORT_MIXED_LATIN_ZH_CJK_UNITS)


def short_mixed_latin_zh_total_units() -> int:
    return _dictation_env_int("SHORT_MIXED_LATIN_ZH_TOTAL_UNITS", SHORT_MIXED_LATIN_ZH_TOTAL_UNITS)


def dictation_pipeline_policy() -> dict[str, object]:
    return {
        "stt_transcribe_task": STT_TRANSCRIBE_TASK,
        "stt_without_timestamps": STT_WITHOUT_TIMESTAMPS,
        "stt_condition_on_previous_text": STT_CONDITION_ON_PREVIOUS_TEXT,
        "stt_stream_audio_dtype": STT_STREAM_AUDIO_DTYPE,
        "recent_transcript_window": RECENT_TRANSCRIPT_WINDOW,
        "recent_final_extension_min_prefix_units": recent_final_extension_min_prefix_units(),
        "recent_final_extension_min_suffix_units": recent_final_extension_min_suffix_units(),
        "segment_high_no_speech_override_languages": sorted(SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES),
        "min_segment_avg_logprob": MIN_SEGMENT_AVG_LOGPROB,
        "max_segment_no_speech_prob": MAX_SEGMENT_NO_SPEECH_PROB,
        "max_segment_no_speech_cjk_override_prob": MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB,
        "min_cjk_chars_for_no_speech_override": MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE,
        "segment_logprob_score_offset": SEGMENT_LOGPROB_SCORE_OFFSET,
        "segment_logprob_score_scale": SEGMENT_LOGPROB_SCORE_SCALE,
        "segment_logprob_confidence_weight": SEGMENT_LOGPROB_CONFIDENCE_WEIGHT,
        "segment_no_speech_confidence_weight": SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT,
        "cjk_char_ranges": CJK_CHAR_RANGES,
        "max_staged_sentence_queue": max_staged_sentence_queue(),
        "staged_queue_max_promotion_age_chunks": staged_queue_max_promotion_age_chunks(),
        "no_text_stale_stage_suppress_chunks": no_text_stale_stage_suppress_chunks(),
        "delta_suppressed_stage_max_chunks": delta_suppressed_stage_max_chunks(),
        "sentence_confirm_chunks": sentence_confirm_chunks(),
        "forced_sentence_confirm_chunks": forced_sentence_confirm_chunks(),
        "sentence_confirm_max_age_chunks": sentence_confirm_max_age_chunks(),
        "forced_sentence_confirm_max_age_chunks": forced_sentence_confirm_max_age_chunks(),
        "max_pending_sentence_chars": MAX_PENDING_SENTENCE_CHARS,
        "pending_overrun_chunks": PENDING_OVERRUN_CHUNKS,
        "fast_pending_overrun_chars": FAST_PENDING_OVERRUN_CHARS,
        "fast_pending_overrun_chunks": FAST_PENDING_OVERRUN_CHUNKS,
        "slow_pending_sentence_chunks": SLOW_PENDING_SENTENCE_CHUNKS,
        "slow_pending_sentence_chars": SLOW_PENDING_SENTENCE_CHARS,
        "slow_pending_max_sentence_chars": SLOW_PENDING_MAX_SENTENCE_CHARS,
        "slow_pending_max_chars_per_chunk": SLOW_PENDING_MAX_CHARS_PER_CHUNK,
        "short_cjk_final_units": short_cjk_final_units(),
        "short_no_end_fragment_units": short_no_end_fragment_units(),
        "short_cjk_replacement_hold_chunks": short_cjk_replacement_hold_chunks(),
        "short_cjk_confirm_extra_chunks": short_cjk_confirm_extra_chunks(),
        "short_mixed_latin_zh_cjk_units": short_mixed_latin_zh_cjk_units(),
        "short_mixed_latin_zh_total_units": short_mixed_latin_zh_total_units(),
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


def lifecycle_tuning_policy() -> dict[str, int]:
    return {
        "max_staged_sentence_queue": max_staged_sentence_queue(),
        "no_text_stale_stage_suppress_chunks": no_text_stale_stage_suppress_chunks(),
        "delta_suppressed_stage_max_chunks": delta_suppressed_stage_max_chunks(),
        "sentence_confirm_chunks": sentence_confirm_chunks(),
        "forced_sentence_confirm_chunks": forced_sentence_confirm_chunks(),
        "sentence_confirm_max_age_chunks": sentence_confirm_max_age_chunks(),
        "forced_sentence_confirm_max_age_chunks": forced_sentence_confirm_max_age_chunks(),
        "short_cjk_final_units": short_cjk_final_units(),
        "short_no_end_fragment_units": short_no_end_fragment_units(),
        "short_cjk_replacement_hold_chunks": short_cjk_replacement_hold_chunks(),
        "short_cjk_confirm_extra_chunks": short_cjk_confirm_extra_chunks(),
    }


def dictation_tuning_protocol() -> dict[str, object]:
    return {
        "case_source": "app logs only",
        "draft_rule": "auto-collected drafts require human expected_final review before benchmark use",
        "benchmark_runtime": "sat + cuda + float16 only",
        "parameter_change_source": "dictation_tuning_manifest only",
        "parameter_range_rule": "sweep values must stay inside each manifest min_value/max_value range",
        "exploratory_sweep_rule": "may run on current reviewed cases, but is not paper evidence",
        "paper_evidence_case_source": PAPER_EVIDENCE_CASE_SOURCE,
        "paper_evidence_reviewed_finalization_case_target": PAPER_EVIDENCE_REVIEWED_FINALIZATION_CASE_TARGET,
        "paper_evidence_rule": (
            "run with --paper-evidence only after reviewed expected_final cases reach the target "
            "and all draft markers are removed"
        ),
        "comparison_rule": "compare one parameter at a time on the same reviewed case set",
        "promotion_rule": "checked-in defaults require repeated improvement across log-derived reviewed cases",
        "forbidden_changes": (
            "language-specific phrase rules",
            "regex sentence split baselines",
            "mock/smoke/CPU benchmark evidence",
        ),
        "primary_metrics": (
            "final_f1_avg",
            "final_precision_avg",
            "final_recall_avg",
            "final_boundary_f1_avg",
            "finalized_per_stage_start",
        ),
        "diagnostic_metrics": (
            "stage_revision",
            "stage_replace",
            "stage_replaced_unconfirmed",
            "pending_overrun",
            "language_summary residual counters",
            "tag_summary symptom counters",
            "duplicate suppression counters",
            "finalize_delta_fragment_preserved",
        ),
    }


def _tuning_manifest_entry(
    name: str,
    *,
    default: int | float,
    current: int | float,
    value_type: str,
    min_value: int | float,
    max_value: int | float,
    scope: str,
    intent: str,
) -> dict[str, int | float | str]:
    return {
        "name": name,
        "env": f"AVC_DICTATION_{name.upper()}",
        "default": default,
        "current": current,
        "value_type": value_type,
        "min_value": min_value,
        "max_value": max_value,
        "scope": scope,
        "intent": intent,
        "evidence_basis": "app-log replay benchmark",
        "external_reference_role": "problem framing and metric design, not direct threshold source",
        "change_rule": "sweep with AVC_DICTATION_* override; compare on unchanged reviewed case set",
        "default_promotion_rule": "update checked-in default only after recording CUDA benchmark evidence",
        "primary_comparison_metrics": "final_f1_avg, final_precision_avg, final_recall_avg, final_boundary_f1_avg",
    }


def dictation_tuning_manifest() -> list[dict[str, int | float | str]]:
    return [
        _tuning_manifest_entry(
            "MAX_STAGED_SENTENCE_QUEUE",
            default=MAX_STAGED_SENTENCE_QUEUE,
            current=max_staged_sentence_queue(),
            value_type="int",
            min_value=1,
            max_value=50,
            scope="lifecycle",
            intent="preserve created-order staged candidates when SBD emits multiple completed candidates before active finalization",
        ),
        _tuning_manifest_entry(
            "STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS",
            default=STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS,
            current=staged_queue_max_promotion_age_chunks(),
            value_type="int",
            min_value=1,
            max_value=30,
            scope="lifecycle",
            intent="drop queued staged candidates that are too old to represent the current sliding-window sentence stream",
        ),
        _tuning_manifest_entry(
            "NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS",
            default=NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS,
            current=no_text_stale_stage_suppress_chunks(),
            value_type="int",
            min_value=1,
            max_value=30,
            scope="lifecycle",
            intent="suppress stale unconfirmed staged candidates after repeated no-text chunks without treating silence as final evidence",
        ),
        _tuning_manifest_entry(
            "DELTA_SUPPRESSED_STAGE_MAX_CHUNKS",
            default=DELTA_SUPPRESSED_STAGE_MAX_CHUNKS,
            current=delta_suppressed_stage_max_chunks(),
            value_type="int",
            min_value=1,
            max_value=10,
            scope="lifecycle",
            intent="drop a staged candidate after repeated broken-delta suppression so it cannot block later sentence candidates",
        ),
        _tuning_manifest_entry(
            "RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS",
            default=RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS,
            current=recent_final_extension_min_prefix_units(),
            value_type="int",
            min_value=1,
            max_value=40,
            scope="duplicate-suppression",
            intent="require enough recent-final prefix evidence before recovering a later suffix extension as a new candidate",
        ),
        _tuning_manifest_entry(
            "RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS",
            default=RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS,
            current=recent_final_extension_min_suffix_units(),
            value_type="int",
            min_value=1,
            max_value=40,
            scope="duplicate-suppression",
            intent="recover only meaningful suffix extensions while keeping tiny echo corrections suppressed",
        ),
        _tuning_manifest_entry(
            "SENTENCE_CONFIRM_CHUNKS",
            default=SENTENCE_CONFIRM_CHUNKS,
            current=sentence_confirm_chunks(),
            value_type="int",
            min_value=1,
            max_value=6,
            scope="lifecycle",
            intent="balance finalization latency against duplicate and premature final risk for ordinary candidates",
        ),
        _tuning_manifest_entry(
            "FORCED_SENTENCE_CONFIRM_CHUNKS",
            default=FORCED_SENTENCE_CONFIRM_CHUNKS,
            current=forced_sentence_confirm_chunks(),
            value_type="int",
            min_value=1,
            max_value=8,
            scope="lifecycle",
            intent="require stronger observation for forced boundary candidates",
        ),
        _tuning_manifest_entry(
            "SENTENCE_CONFIRM_MAX_AGE_CHUNKS",
            default=SENTENCE_CONFIRM_MAX_AGE_CHUNKS,
            current=sentence_confirm_max_age_chunks(),
            value_type="int",
            min_value=1,
            max_value=10,
            scope="lifecycle",
            intent="allow aged staged candidates to finalize when repeated exact confirmations are not preserved",
        ),
        _tuning_manifest_entry(
            "FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS",
            default=FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS,
            current=forced_sentence_confirm_max_age_chunks(),
            value_type="int",
            min_value=1,
            max_value=12,
            scope="lifecycle",
            intent="age cap for forced boundary candidates",
        ),
        _tuning_manifest_entry(
            "SHORT_CJK_FINAL_UNITS",
            default=SHORT_CJK_FINAL_UNITS,
            current=short_cjk_final_units(),
            value_type="int",
            min_value=1,
            max_value=40,
            scope="quality-gate",
            intent="flag short CJK final candidates for false-final and fragment analysis",
        ),
        _tuning_manifest_entry(
            "SHORT_NO_END_FRAGMENT_UNITS",
            default=SHORT_NO_END_FRAGMENT_UNITS,
            current=short_no_end_fragment_units(),
            value_type="int",
            min_value=1,
            max_value=20,
            scope="quality-gate",
            intent="flag short candidates without sentence-end markers before final-only translation",
        ),
        _tuning_manifest_entry(
            "SHORT_CJK_REPLACEMENT_HOLD_CHUNKS",
            default=SHORT_CJK_REPLACEMENT_HOLD_CHUNKS,
            current=short_cjk_replacement_hold_chunks(),
            value_type="int",
            min_value=0,
            max_value=10,
            scope="quality-gate",
            intent="hold short CJK replacement candidates briefly before replacing existing staged content",
        ),
        _tuning_manifest_entry(
            "SHORT_CJK_CONFIRM_EXTRA_CHUNKS",
            default=SHORT_CJK_CONFIRM_EXTRA_CHUNKS,
            current=short_cjk_confirm_extra_chunks(),
            value_type="int",
            min_value=0,
            max_value=4,
            scope="lifecycle",
            intent="require one more observation for punctuated short CJK candidates before finalizing",
        ),
        _tuning_manifest_entry(
            "CJK_REVISION_RATIO_MIN",
            default=CJK_REVISION_RATIO_MIN,
            current=cjk_revision_ratio_min(),
            value_type="float",
            min_value=0.50,
            max_value=0.95,
            scope="revision-similarity",
            intent="classify CJK candidate revisions without language-specific phrase rules",
        ),
        _tuning_manifest_entry(
            "CJK_CONFIRM_PRESERVE_RATIO_MIN",
            default=CJK_CONFIRM_PRESERVE_RATIO_MIN,
            current=cjk_confirm_preserve_ratio_min(),
            value_type="float",
            min_value=0.50,
            max_value=0.95,
            scope="revision-similarity",
            intent="preserve confirmation count when a revised CJK candidate remains close enough to prior staged text",
        ),
        _tuning_manifest_entry(
            "REVISION_FALLBACK_COVERAGE_MIN",
            default=REVISION_FALLBACK_COVERAGE_MIN,
            current=revision_fallback_coverage_min(),
            value_type="float",
            min_value=0.40,
            max_value=0.90,
            scope="revision-similarity",
            intent="fallback coverage threshold for multilingual revision matching",
        ),
    ]

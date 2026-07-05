from __future__ import annotations

from src.app.dictation_core.dictation_revision_text import (
    _final_sentence_diagnostic_flags,
    _is_cjk_text,
    _new_text_delta,
    _normalized_text,
    _stable_window_text,
    _word_units,
)
from src.app.dictation_core.dictation_recent_final import (
    _recent_final_output_delta_with_reason,
)
from src.app.dictation_core.dictation_revision_progression import (
    _diagnostic_tail,
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _prefer_sentence_revision,
    _revision_internal_stability_bucket,
    _sentence_end_count,
    _should_age_staged_sentence,
    _should_defer_token_sentence_revision as _should_defer_token_sentence_revision_impl,
    _should_preserve_revision_confirmation_from_internal_stability,
    _should_reset_revision_age,
    _split_completed_sentences,
)
from src.app.dictation_core.dictation_pending_context import (
    _has_later_completed_extension,
    _is_pending_prefix_mixed_candidate,
    _is_prior_pending_recent_final_mixed_candidate,
    _strip_prior_pending_prefix_from_final as _strip_prior_pending_prefix_from_final_impl,
    _strip_prior_pending_prefix_revision as _strip_prior_pending_prefix_revision_impl,
)
from src.app.dictation_core.dictation_stage_policy import (
    _coalesce_completed_short_no_end_fragments as _coalesce_completed_short_no_end_fragments_impl,
    _replacement_decision_reason as _replacement_decision_reason_impl,
    _should_confirm_staged_sentence as _should_confirm_staged_sentence_impl,
    _should_defer_unconfirmed_replacement,
    _should_defer_short_closed_queue_quality_block as _should_defer_short_closed_queue_quality_block_impl,
    _should_finalize_before_replacement as _should_finalize_before_replacement_impl,
    _should_finalize_replaced_sentence as _should_finalize_replaced_sentence_impl,
    _should_enable_aged_queue_backlog_promotion_boost as _should_enable_aged_queue_backlog_promotion_boost_impl,
    _should_allow_no_text_stage_aging as _should_allow_no_text_stage_aging_impl,
    _is_ko_short_closed_sentence as _is_ko_short_closed_sentence_impl,
    _should_restore_trimmed_closed_candidate as _should_restore_trimmed_closed_candidate_impl,
    _should_suppress_ko_numeric_aged_final_with_queue as _should_suppress_ko_numeric_aged_final_with_queue_impl,
    _should_suppress_ko_pure_latin_final_with_hangul_queue as _should_suppress_ko_pure_latin_final_with_hangul_queue_impl,
    _should_suppress_ko_short_closed_final_with_stronger_queue_candidate as _should_suppress_ko_short_closed_final_with_stronger_queue_candidate_impl,
    _should_suppress_right_context_short_prefix_extension_with_single_queue as _should_suppress_right_context_short_prefix_extension_with_single_queue_impl,
    _should_suppress_aged_low_value_final as _should_suppress_aged_low_value_final_impl,
    _should_suppress_aged_no_end_marker_queue_final as _should_suppress_aged_no_end_marker_queue_final_impl,
    _should_extend_zh_long_closed_stage_age as _should_extend_zh_long_closed_stage_age_impl,
    _should_finalize_with_right_context as _should_finalize_with_right_context_impl,
    _should_preserve_staged_output_when_delta_fragment as _should_preserve_staged_output_when_delta_fragment_impl,
    _should_split_terminal_tail_revision,
    _should_stage_boundary_candidate as _should_stage_boundary_candidate_impl,
    _should_suppress_delta_final as _should_suppress_delta_final_impl,
    _should_translate_final_sentence as _should_translate_final_sentence_impl,
    _staged_sentence_required_confirmations as _staged_sentence_required_confirmations_impl,
)
from src.app.dictation.pipeline_settings import (
    forced_sentence_confirm_chunks as _forced_sentence_confirm_chunks,
    forced_sentence_confirm_max_age_chunks as _forced_sentence_confirm_max_age_chunks,
    long_no_end_replacement_early_age_min_units as _long_no_end_replacement_early_age_min_units,
    revision_similarity_policy as _revision_similarity_policy,
    sentence_confirm_chunks as _sentence_confirm_chunks,
    sentence_confirm_max_age_chunks as _sentence_confirm_max_age_chunks,
    short_cjk_replacement_hold_chunks as _short_cjk_replacement_hold_chunks,
    short_cjk_confirm_extra_chunks as _short_cjk_confirm_extra_chunks,
    aged_queue_zh_no_end_marker_max_confirmations as _aged_queue_zh_no_end_marker_max_confirmations,
    aged_queue_backlog_promotion_extra_age as _aged_queue_backlog_promotion_extra_age,
    aged_queue_backlog_promotion_min as _aged_queue_backlog_promotion_min,
    short_latin_only_zh_total_units as _short_latin_only_zh_total_units,
)


def _sentence_required_confirmations(forced: bool) -> int:
    return _forced_sentence_confirm_chunks() if forced else _sentence_confirm_chunks()


def _sentence_max_age_chunks(forced: bool, base_age: int | None = None) -> int:
    if base_age is None:
        return _forced_sentence_confirm_max_age_chunks() if forced else _sentence_confirm_max_age_chunks()
    normalized_base_age = max(1, int(base_age))
    return normalized_base_age + 1 if forced else normalized_base_age


def _stage_quality_block_age_limit(sentence: str, language: str, forced: bool, base_age: int | None = None) -> int:
    limit = _sentence_max_age_chunks(forced, base_age)
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if (
        _is_cjk_text(sentence)
        and "short_cjk" in flags
        and not flags.intersection({"no_end_marker", "short_no_end_fragment", "low_value_cjk_fragment"})
    ):
        return limit + _short_cjk_replacement_hold_chunks()
    return limit


def _stage_finalize_age_limit(
    sentence: str,
    language: str,
    forced: bool,
    base_age: int | None = None,
    queued_sentences: tuple[str, ...] = (),
) -> int:
    limit = _sentence_max_age_chunks(forced, base_age)
    if _should_extend_zh_long_closed_stage_age_impl(sentence, language, queued_sentences):
        return limit + 1
    return limit


def _staged_sentence_required_confirmations(staged_sentence: str, staged_forced: bool) -> int:
    return _staged_sentence_required_confirmations_impl(
        staged_sentence,
        staged_forced,
        _sentence_required_confirmations(staged_forced),
        _short_cjk_confirm_extra_chunks(),
    )


def _should_confirm_staged_sentence(
    staged_sentence: str,
    staged_confirmations: int,
    staged_forced: bool,
) -> bool:
    return _should_confirm_staged_sentence_impl(
        staged_sentence,
        staged_confirmations,
        staged_forced,
        _sentence_required_confirmations(staged_forced),
        _short_cjk_confirm_extra_chunks(),
    )


def _replacement_decision_reason(
    staged_sentence: str,
    candidate: str,
    staged_confirmations: int,
    staged_forced: bool,
    staged_age: int,
    sentence_finalize_age: int | None = None,
) -> str:
    return _replacement_decision_reason_impl(
        staged_sentence,
        candidate,
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_required_confirmations=_sentence_required_confirmations(staged_forced),
        sentence_max_age_chunks=_sentence_max_age_chunks(staged_forced, sentence_finalize_age),
        short_cjk_confirm_extra_chunks=_short_cjk_confirm_extra_chunks(),
        short_cjk_replacement_hold_chunks=_short_cjk_replacement_hold_chunks(),
        long_no_end_replacement_early_age_min_units=_long_no_end_replacement_early_age_min_units(),
    )


def _should_finalize_replaced_sentence(
    staged_sentence: str,
    candidate: str,
    language: str,
    staged_confirmations: int,
    staged_forced: bool,
    staged_age: int,
    sentence_finalize_age: int | None = None,
) -> bool:
    return _should_finalize_replaced_sentence_impl(
        staged_sentence,
        candidate,
        language,
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_required_confirmations=_sentence_required_confirmations(staged_forced),
        sentence_max_age_chunks=_sentence_max_age_chunks(staged_forced, sentence_finalize_age),
        short_cjk_confirm_extra_chunks=_short_cjk_confirm_extra_chunks(),
        short_cjk_replacement_hold_chunks=_short_cjk_replacement_hold_chunks(),
        long_no_end_replacement_early_age_min_units=_long_no_end_replacement_early_age_min_units(),
    )


def _format_transcript_metrics(metrics: dict[str, int]) -> str:
    parts = [f"{key}={metrics[key]}" for key in sorted(metrics) if metrics[key]]
    return ",".join(parts) if parts else "none"


def _should_translate_final_sentence(sentence: str, language: str) -> bool:
    return _should_translate_final_sentence_impl(sentence, language)


def _should_stage_boundary_candidate(sentence: str, language: str) -> bool:
    return _should_stage_boundary_candidate_impl(sentence, language)


def _should_restore_trimmed_closed_candidate(
    original_sentence: str,
    trimmed_candidate: str,
    language: str,
    recent_reason: str | None = None,
) -> bool:
    return _should_restore_trimmed_closed_candidate_impl(
        original_sentence,
        trimmed_candidate,
        language,
        recent_reason,
    )


def _is_ko_short_closed_sentence(
    sentence: str,
    language: str,
    *,
    max_units: int = 2,
) -> bool:
    return _is_ko_short_closed_sentence_impl(sentence, language, max_units=max_units)


def _should_defer_short_closed_queue_quality_block(
    sentence: str,
    language: str,
    queued_sentences: tuple[str, ...] = (),
    staged_confirmations: int = 0,
) -> bool:
    return _should_defer_short_closed_queue_quality_block_impl(
        sentence,
        language,
        queued_sentences,
        staged_confirmations,
    )


def _should_suppress_right_context_short_prefix_extension_with_single_queue(
    sentence: str,
    reason: str,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_suppress_right_context_short_prefix_extension_with_single_queue_impl(
        sentence,
        reason,
        queued_sentences,
    )


def _stale_leading_short_closed_candidate_reason(
    candidate: str,
    language: str,
    *,
    later_completed_sentences: list[str] | tuple[str, ...] = (),
    active_stage_sentence: str = "",
    recent_final_sentences: tuple[str, ...] = (),
) -> str:
    normalized_candidate = _normalized_text(candidate)
    if not normalized_candidate or _sentence_end_count(normalized_candidate) <= 0:
        return ""
    candidate_words = _word_units(normalized_candidate)
    if len(candidate_words) == 0 or len(candidate_words) > 2:
        return ""
    candidate_flags = set(_final_sentence_diagnostic_flags(normalized_candidate, language))
    if candidate_flags.intersection({"empty", "no_end_marker", "short_no_end_fragment", "trailing_ellipsis"}):
        return ""
    repeated_later_candidate = False
    for later_sentence in later_completed_sentences:
        if _normalized_text(later_sentence) == normalized_candidate:
            repeated_later_candidate = True
            break
    if repeated_later_candidate:
        return ""
    normalized_active_stage = _normalized_text(active_stage_sentence)
    normalized_recent_finals = {
        normalized
        for sentence in recent_final_sentences
        if (normalized := _normalized_text(sentence))
    }
    for later_sentence in later_completed_sentences:
        normalized_later = _normalized_text(later_sentence)
        if not normalized_later or normalized_later == normalized_candidate:
            continue
        if normalized_active_stage and normalized_later == normalized_active_stage:
            return "active_stage_later_repeat"
        if normalized_later in normalized_recent_finals:
            return "recent_final_later_repeat"
    return ""


def _coalesce_completed_short_no_end_fragments(
    sentences: list[str] | tuple[str, ...],
    language: str,
) -> tuple[str, ...]:
    return _coalesce_completed_short_no_end_fragments_impl(sentences, language)


def _should_finalize_before_replacement(
    sentence: str,
    language: str,
    staged_confirmations: int = 0,
    staged_age: int = 0,
    sentence_finalize_age: int | None = None,
    staged_forced: bool = False,
    deferred_revision_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_finalize_before_replacement_impl(
        sentence,
        language,
        staged_confirmations,
        staged_age,
        staged_forced,
        deferred_revision_sentences,
        sentence_required_confirmations=_sentence_required_confirmations(staged_forced),
        sentence_max_age_chunks=_sentence_max_age_chunks(staged_forced, sentence_finalize_age),
        short_cjk_confirm_extra_chunks=_short_cjk_confirm_extra_chunks(),
        short_cjk_replacement_hold_chunks=_short_cjk_replacement_hold_chunks(),
        long_no_end_replacement_early_age_min_units=_long_no_end_replacement_early_age_min_units(),
    )


def _should_suppress_delta_final(staged_sentence: str, output_sentence: str, language: str, reason: str) -> bool:
    return _should_suppress_delta_final_impl(staged_sentence, output_sentence, language, reason)


def _should_preserve_staged_output_when_delta_fragment(staged_sentence: str, output_sentence: str, language: str) -> bool:
    return _should_preserve_staged_output_when_delta_fragment_impl(staged_sentence, output_sentence, language)


def _should_suppress_aged_low_value_final(
    sentence: str,
    language: str,
    reason: str,
    staged_confirmations: int,
    staged_forced: bool,
    deferred_revision_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_suppress_aged_low_value_final_impl(
        sentence,
        language,
        reason,
        staged_confirmations,
        deferred_revision_sentences,
        sentence_required_confirmations=_sentence_required_confirmations(staged_forced),
        short_latin_only_zh_total_units=_short_latin_only_zh_total_units(),
    )


def _should_defer_cjk_recent_final_trimmed_queue_finalize(
    sentence: str,
    language: str,
    reason: str,
    recent_final_trimmed: bool,
    confirmed_queue_deferrals: int,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    if not recent_final_trimmed or confirmed_queue_deferrals > 0:
        return False
    if reason not in {"confirmed", "confirmed_forced", "aged", "aged_forced"}:
        return False
    if len(queued_sentences) == 0 or len(queued_sentences) > 2:
        return False
    normalized_sentence = _normalized_text(sentence)
    if not normalized_sentence or not _is_cjk_text(normalized_sentence):
        return False
    if _sentence_end_count(normalized_sentence) <= 0:
        return False
    sentence_words = _word_units(normalized_sentence)
    if len(sentence_words) < 6:
        return False
    if len(queued_sentences) == 1 and len(sentence_words) < 8:
        return False
    first_queue = _normalized_text(queued_sentences[0])
    if not first_queue or first_queue == normalized_sentence:
        return False
    if _sentence_end_count(first_queue) <= 0:
        return False
    return len(_word_units(first_queue)) >= 6


def _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
    sentence: str,
    language: str,
    reason: str,
    staged_confirmations: int,
    staged_forced: bool,
    queued_entries: tuple[dict[str, object], ...] = (),
) -> bool:
    return _should_suppress_ko_short_closed_final_with_stronger_queue_candidate_impl(
        sentence,
        language,
        reason,
        staged_confirmations,
        queued_entries,
        sentence_required_confirmations=_sentence_required_confirmations(staged_forced),
    )


def _should_suppress_ko_pure_latin_final_with_hangul_queue(
    sentence: str,
    language: str,
    reason: str,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_suppress_ko_pure_latin_final_with_hangul_queue_impl(
        sentence,
        language,
        reason,
        queued_sentences,
    )


def _should_suppress_ko_numeric_aged_final_with_queue(
    sentence: str,
    language: str,
    reason: str,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_suppress_ko_numeric_aged_final_with_queue_impl(
        sentence,
        language,
        reason,
        queued_sentences,
    )


def _should_suppress_aged_no_end_marker_queue_final(
    sentence: str,
    language: str,
    reason: str,
    staged_confirmations: int,
    deferred_revision_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_suppress_aged_no_end_marker_queue_final_impl(
        sentence,
        language,
        reason,
        staged_confirmations,
        deferred_revision_sentences,
        max_confirmations=_aged_queue_zh_no_end_marker_max_confirmations(),
    )


def _should_enable_aged_queue_backlog_promotion_boost(
    reason: str,
    queued_sentence_count: int,
    language: str,
) -> bool:
    return _should_enable_aged_queue_backlog_promotion_boost_impl(
        reason,
        queued_sentence_count,
        language,
        min_queue_size=_aged_queue_backlog_promotion_min(),
        extra_age=_aged_queue_backlog_promotion_extra_age(),
    )


def _should_allow_no_text_stage_aging(
    sentence: str,
    language: str,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    return _should_allow_no_text_stage_aging_impl(sentence, language, queued_sentences)


def _should_finalize_with_right_context(
    sentence: str,
    language: str,
    deferred_revision_sentences: tuple[str, ...] = (),
    promoted_from_queue_same_chunk: bool = False,
) -> bool:
    return _should_finalize_with_right_context_impl(
        sentence,
        language,
        deferred_revision_sentences,
        promoted_from_queue_same_chunk,
    )

def _strip_prior_pending_prefix_revision(staged_sentence: str, candidate: str, prior_pending_text: str) -> str:
    return _strip_prior_pending_prefix_revision_impl(staged_sentence, candidate, prior_pending_text)


def _strip_prior_pending_prefix_from_final(candidate: str, prior_pending_text: str) -> str:
    return _strip_prior_pending_prefix_from_final_impl(candidate, prior_pending_text, _should_stage_boundary_candidate)

def _should_defer_token_sentence_revision(
    previous: str,
    preferred: str,
    current_confirmations: int,
    staged_forced: bool,
    stable_internal_ratio: float = 0.0,
    stable_internal_chars: int = 0,
    stable_overlap_source: str = "",
) -> bool:
    required_confirmations = _staged_sentence_required_confirmations(_normalized_text(preferred), staged_forced)
    return _should_defer_token_sentence_revision_impl(
        previous,
        preferred,
        current_confirmations,
        staged_forced,
        required_confirmations,
        stable_internal_ratio,
        stable_internal_chars,
        stable_overlap_source,
    )

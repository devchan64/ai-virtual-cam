from __future__ import annotations

from src.app.dictation_core.dictation_revision_text import (
    _best_common_word_run,
    _final_sentence_diagnostic_flags,
    _has_cjk_words,
    _is_cjk_text,
    _looks_like_open_latin_clause,
    _normalized_text,
    _sentence_output_delta,
    _sentences_are_revisions,
    _word_units,
)
from src.app.dictation_core.dictation_revision_progression import _prefer_sentence_revision, _sentence_end_count
from src.app.dictation_core.sentence_boundary import sentence_end_count as _boundary_sentence_end_count


def _staged_sentence_required_confirmations(
    staged_sentence: str,
    staged_forced: bool,
    sentence_required_confirmations: int,
    short_cjk_confirm_extra_chunks: int,
) -> int:
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh" if _is_cjk_text(staged_sentence) else ""))
    required_confirmations = sentence_required_confirmations
    if "short_cjk" in flags and "no_end_marker" not in flags:
        required_confirmations += short_cjk_confirm_extra_chunks
    return required_confirmations


def _should_confirm_staged_sentence(
    staged_sentence: str,
    staged_confirmations: int,
    staged_forced: bool,
    sentence_required_confirmations: int,
    short_cjk_confirm_extra_chunks: int,
) -> bool:
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh" if _is_cjk_text(staged_sentence) else ""))
    if "repeated_word_ngram" in flags:
        return False
    if _is_cjk_text(staged_sentence) and flags.intersection({"empty", "no_end_marker", "spaced_cjk", "cjk_repeated_ngram"}):
        return False
    return staged_confirmations >= _staged_sentence_required_confirmations(
        staged_sentence,
        staged_forced,
        sentence_required_confirmations,
        short_cjk_confirm_extra_chunks,
    )


def _should_preserve_partial_replacement(staged_sentence: str, candidate: str) -> bool:
    staged_words = _word_units(staged_sentence)
    candidate_words = _word_units(candidate)
    if len(staged_words) < 4 or len(candidate_words) < 4:
        return False
    best_i, best_j, common_run = _best_common_word_run(staged_words, candidate_words)
    if common_run < 4:
        return False
    left_tail = best_i + common_run == len(staged_words)
    right_tail = best_j + common_run == len(candidate_words)
    if left_tail and right_tail:
        return True
    return _boundary_sentence_end_count(staged_sentence) > 0 and best_j == 0 and common_run >= 5


def _should_split_terminal_tail_revision(staged_sentence: str, candidate: str) -> bool:
    staged = _normalized_text(staged_sentence)
    candidate_text = _normalized_text(candidate)
    if not staged or not candidate_text or _boundary_sentence_end_count(staged) == 0:
        return False
    staged_words = _word_units(staged)
    candidate_words = _word_units(candidate_text)
    if len(staged_words) < 5 or len(candidate_words) < len(staged_words) + 3:
        return False
    best_i, best_j, common_run = _best_common_word_run(staged_words, candidate_words)
    if common_run < min(6, len(staged_words)) or best_i + common_run != len(staged_words) or best_j < 3:
        return False
    prefix_words = candidate_words[:best_j]
    for start in range(0, len(staged_words) - len(prefix_words) + 1):
        if staged_words[start : start + len(prefix_words)] == prefix_words:
            return False
    return True


def _replacement_decision_reason(
    staged_sentence: str,
    candidate: str,
    staged_confirmations: int,
    staged_forced: bool,
    staged_age: int,
    *,
    sentence_required_confirmations: int,
    sentence_max_age_chunks: int,
    short_cjk_confirm_extra_chunks: int,
    short_cjk_replacement_hold_chunks: int,
    long_no_end_replacement_early_age_min_units: int,
) -> str:
    staged_words = _word_units(staged_sentence)
    if not staged_words:
        return "empty"
    non_cjk_flags = set(_final_sentence_diagnostic_flags(staged_sentence, "en"))
    if _looks_like_open_latin_clause(staged_sentence, staged_words):
        if (
            "no_end_marker" in non_cjk_flags
            and len(staged_words) >= long_no_end_replacement_early_age_min_units
            and staged_age + 1 >= sentence_max_age_chunks
        ):
            return "aged"
        return "open_latin_clause"
    if staged_confirmations >= _staged_sentence_required_confirmations(
        staged_sentence,
        staged_forced,
        sentence_required_confirmations,
        short_cjk_confirm_extra_chunks,
    ):
        return "confirmed"
    if _has_cjk_words(staged_words):
        flags = set(_final_sentence_diagnostic_flags(staged_sentence, "zh"))
        if "short_cjk" in flags and "no_end_marker" not in flags and staged_age < sentence_max_age_chunks + short_cjk_replacement_hold_chunks:
            return "unconfirmed_cjk"
    else:
        if (
            "no_end_marker" in non_cjk_flags
            and len(staged_words) >= long_no_end_replacement_early_age_min_units
            and staged_age + 1 >= sentence_max_age_chunks
        ):
            return "aged"
    if staged_age >= sentence_max_age_chunks:
        return "aged"
    if _has_cjk_words(staged_words):
        return "unconfirmed_cjk"
    candidate_delta = _sentence_output_delta(staged_sentence, candidate)
    if candidate_delta == "":
        return "duplicate_or_suffix"
    if candidate_delta != _normalized_text(candidate):
        if _should_preserve_partial_replacement(staged_sentence, candidate):
            return "partial_preserve"
        return "partial_revision"
    return "unconfirmed"


def _should_defer_unconfirmed_replacement(replacement_reason: str) -> bool:
    return replacement_reason in {"open_latin_clause", "unconfirmed", "unconfirmed_cjk"}


def _should_finalize_replaced_sentence(
    staged_sentence: str,
    candidate: str,
    language: str,
    staged_confirmations: int,
    staged_forced: bool,
    staged_age: int,
    *,
    sentence_required_confirmations: int,
    sentence_max_age_chunks: int,
    short_cjk_confirm_extra_chunks: int,
    short_cjk_replacement_hold_chunks: int,
    long_no_end_replacement_early_age_min_units: int,
) -> bool:
    reason = _replacement_decision_reason(
        staged_sentence,
        candidate,
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_required_confirmations=sentence_required_confirmations,
        sentence_max_age_chunks=sentence_max_age_chunks,
        short_cjk_confirm_extra_chunks=short_cjk_confirm_extra_chunks,
        short_cjk_replacement_hold_chunks=short_cjk_replacement_hold_chunks,
        long_no_end_replacement_early_age_min_units=long_no_end_replacement_early_age_min_units,
    )
    flags = set(_final_sentence_diagnostic_flags(staged_sentence, language))
    if "no_end_marker" in flags and staged_confirmations < sentence_required_confirmations:
        return False
    if "trailing_ellipsis" in flags:
        return False
    if reason == "confirmed":
        return _should_confirm_staged_sentence(
            staged_sentence,
            staged_confirmations,
            staged_forced,
            sentence_required_confirmations,
            short_cjk_confirm_extra_chunks,
        )
    if reason == "aged" and _is_cjk_text(staged_sentence):
        if flags.intersection({"empty", "short_cjk", "spaced_cjk", "cjk_internal_gap", "cjk_repeated_ngram"}):
            return False
    if "repeated_word_ngram" in flags:
        return False
    return reason in {"aged", "duplicate_or_suffix", "partial_preserve"}


def _should_translate_final_sentence(sentence: str, language: str) -> bool:
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    return not flags.intersection({"empty", "cjk_repeated_ngram", "repeated_word_ngram"})


def _should_stage_boundary_candidate(sentence: str, language: str) -> bool:
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    return not flags.intersection(
        {
            "empty",
            "spaced_cjk",
            "cjk_repeated_ngram",
            "repeated_word_ngram",
            "short_mixed_latin_zh",
            "low_value_cjk_fragment",
            "short_no_end_fragment",
            "trailing_ellipsis",
        }
    )


def _coalesce_completed_short_no_end_fragments(
    sentences: list[str] | tuple[str, ...],
    language: str,
) -> tuple[str, ...]:
    coalesced: list[str] = []
    index = 0
    while index < len(sentences):
        current = _normalized_text(sentences[index])
        if current and index + 1 < len(sentences) and _sentence_end_count(current) == 0 and "short_no_end_fragment" in set(_final_sentence_diagnostic_flags(current, language)):
            following = _normalized_text(sentences[index + 1])
            if following and _sentence_end_count(following) > 0:
                separator = "" if _is_cjk_text(current + following) else " "
                combined = _normalized_text(f"{current}{separator}{following}")
                if _should_stage_boundary_candidate(combined, language):
                    coalesced.append(combined)
                    index += 2
                    continue
        if current:
            coalesced.append(current)
        index += 1
    return tuple(coalesced)


def _has_deferred_revision_extension(sentence: str, deferred_revision_sentences: tuple[str, ...]) -> bool:
    normalized_sentence = _normalized_text(sentence)
    sentence_words = _word_units(normalized_sentence)
    if not sentence_words:
        return False
    for deferred in deferred_revision_sentences:
        normalized_deferred = _normalized_text(deferred)
        if normalized_deferred == normalized_sentence:
            continue
        deferred_words = _word_units(normalized_deferred)
        if len(deferred_words) <= len(sentence_words):
            continue
        if not _sentences_are_revisions(normalized_sentence, normalized_deferred):
            continue
        if _prefer_sentence_revision(normalized_sentence, normalized_deferred) == normalized_deferred:
            return True
    return False


def _should_finalize_before_replacement(
    sentence: str,
    language: str,
    staged_confirmations: int,
    staged_age: int,
    staged_forced: bool,
    deferred_revision_sentences: tuple[str, ...],
    *,
    sentence_required_confirmations: int,
    sentence_max_age_chunks: int,
    short_cjk_confirm_extra_chunks: int,
    short_cjk_replacement_hold_chunks: int,
    long_no_end_replacement_early_age_min_units: int,
) -> bool:
    if _has_deferred_revision_extension(sentence, deferred_revision_sentences):
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "repeated_word_ngram", "short_no_end_fragment"}):
        return False
    if "no_end_marker" in flags and staged_confirmations < sentence_required_confirmations:
        return False
    if "trailing_ellipsis" in flags:
        return False
    if _is_cjk_text(sentence) and flags.intersection({"short_cjk", "no_end_marker", "cjk_internal_gap"}):
        return False
    return _should_finalize_replaced_sentence(
        sentence,
        "",
        language,
        staged_confirmations,
        staged_forced,
        staged_age,
        sentence_required_confirmations=sentence_required_confirmations,
        sentence_max_age_chunks=sentence_max_age_chunks,
        short_cjk_confirm_extra_chunks=short_cjk_confirm_extra_chunks,
        short_cjk_replacement_hold_chunks=short_cjk_replacement_hold_chunks,
        long_no_end_replacement_early_age_min_units=long_no_end_replacement_early_age_min_units,
    )


def _should_finalize_with_right_context(
    sentence: str,
    language: str,
    deferred_revision_sentences: tuple[str, ...],
) -> bool:
    if not _normalized_text(sentence) or not deferred_revision_sentences:
        return False
    if _has_deferred_revision_extension(sentence, deferred_revision_sentences):
        return False
    if _sentence_end_count(sentence) <= 0:
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if flags.intersection({"empty", "spaced_cjk", "cjk_repeated_ngram", "repeated_word_ngram", "short_no_end_fragment", "trailing_ellipsis"}):
        return False
    if _is_cjk_text(sentence) and flags.intersection({"short_cjk", "cjk_internal_gap"}):
        return False
    return True


def _should_suppress_delta_final(staged_sentence: str, output_sentence: str, language: str, reason: str) -> bool:
    staged = _normalized_text(staged_sentence)
    output = _normalized_text(output_sentence)
    if not staged or not output or staged == output:
        return False
    flags = set(_final_sentence_diagnostic_flags(output, language))
    if flags.intersection({"short_no_end_fragment", "trailing_ellipsis", "cjk_internal_gap", "spaced_cjk"}):
        return True
    if _is_cjk_text(output) and "no_end_marker" in flags:
        return True
    if reason not in {"next_completed", "confirmed", "confirmed_forced"}:
        return False
    if "no_end_marker" in flags and _boundary_sentence_end_count(staged) > _boundary_sentence_end_count(output):
        return True
    output_words = _word_units(output)
    staged_words = _word_units(staged)
    if len(output_words) > 7 or len(output) > 32:
        return False
    if len(staged_words) < len(output_words) + 3:
        return False
    return "no_end_marker" in flags


def _should_preserve_staged_output_when_delta_fragment(staged_sentence: str, output_sentence: str, language: str) -> bool:
    staged = _normalized_text(staged_sentence)
    output = _normalized_text(output_sentence)
    if not staged or not output or staged == output:
        return False
    if _sentence_end_count(staged) <= _sentence_end_count(output):
        return False
    staged_flags = set(_final_sentence_diagnostic_flags(staged, language))
    if staged_flags.intersection({"empty", "spaced_cjk", "cjk_internal_gap", "cjk_repeated_ngram", "repeated_word_ngram"}):
        return False
    output_flags = set(_final_sentence_diagnostic_flags(output, language))
    return bool(output_flags.intersection({"no_end_marker", "short_no_end_fragment", "trailing_ellipsis"}))


def _should_suppress_aged_low_value_final(
    sentence: str,
    language: str,
    reason: str,
    staged_confirmations: int,
    deferred_revision_sentences: tuple[str, ...],
    *,
    sentence_required_confirmations: int,
    short_latin_only_zh_total_units: int,
) -> bool:
    if reason not in {"aged", "aged_forced"}:
        return False
    if language != "zh" or not deferred_revision_sentences:
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if "latin_only_for_zh" not in flags:
        return False
    if staged_confirmations >= sentence_required_confirmations:
        return False
    sentence_units = _word_units(sentence)
    if len(sentence_units) > short_latin_only_zh_total_units:
        return False
    for deferred in deferred_revision_sentences:
        deferred_flags = set(_final_sentence_diagnostic_flags(deferred, language))
        if "latin_only_for_zh" not in deferred_flags:
            return True
    return False


def _should_suppress_aged_no_end_marker_queue_final(
    sentence: str,
    language: str,
    reason: str,
    staged_confirmations: int,
    deferred_revision_sentences: tuple[str, ...],
    *,
    max_confirmations: int,
) -> bool:
    if reason not in {"aged", "aged_forced"}:
        return False
    if language != "zh" or max_confirmations <= 0:
        return False
    if staged_confirmations > max_confirmations:
        return False
    if _final_sentence_diagnostic_flags(sentence, language):
        return False
    for deferred in deferred_revision_sentences:
        if "no_end_marker" in set(_final_sentence_diagnostic_flags(deferred, language)):
            return True
    return False


def _should_enable_aged_queue_backlog_promotion_boost(
    reason: str,
    queued_sentence_count: int,
    language: str,
    *,
    min_queue_size: int,
    extra_age: int,
) -> bool:
    if extra_age <= 0 or min_queue_size <= 0:
        return False
    if reason not in {"aged", "aged_forced"}:
        return False
    if language != "zh":
        return False
    return queued_sentence_count >= min_queue_size

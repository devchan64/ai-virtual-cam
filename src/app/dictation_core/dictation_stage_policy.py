from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.app.dictation_core.dictation_revision_text import (
    _best_common_word_run,
    _final_sentence_diagnostic_flags,
    _has_cjk_words,
    _has_hangul_words,
    _has_latin_words,
    _is_cjk_text,
    _looks_like_open_latin_clause,
    _normalized_text,
    _sentence_output_delta,
    _sentences_are_revisions,
    _word_units,
)
from src.app.dictation_core.dictation_revision_progression import _prefer_sentence_revision, _sentence_end_count
from src.app.dictation_core.sentence_boundary import sentence_end_count as _boundary_sentence_end_count


_DIGIT_RE = re.compile(r"\d")


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


def _should_restore_trimmed_closed_candidate(
    original_sentence: str,
    trimmed_candidate: str,
    language: str,
) -> bool:
    normalized_original = _normalized_text(original_sentence)
    normalized_trimmed = _normalized_text(trimmed_candidate)
    if not normalized_original or not normalized_trimmed or normalized_original == normalized_trimmed:
        return False
    original_words = _word_units(normalized_original)
    trimmed_words = _word_units(normalized_trimmed)
    if len(original_words) < 4 or len(original_words) > 5:
        return False
    if len(trimmed_words) > 2 or len(trimmed_words) >= len(original_words):
        return False
    if original_words[-len(trimmed_words) :] != trimmed_words:
        return False
    original_flags = set(_final_sentence_diagnostic_flags(normalized_original, language))
    trimmed_flags = set(_final_sentence_diagnostic_flags(normalized_trimmed, language))
    if original_flags:
        return False
    return trimmed_flags.issuperset({"no_end_marker", "short_no_end_fragment"})


def _should_defer_short_closed_queue_quality_block(
    sentence: str,
    language: str,
    queued_sentences: tuple[str, ...],
    staged_confirmations: int,
) -> bool:
    if language != "zh" or staged_confirmations < 2 or not queued_sentences:
        return False
    flags = set(_final_sentence_diagnostic_flags(sentence, language))
    if "short_cjk" not in flags or flags.intersection({"no_end_marker", "short_no_end_fragment", "low_value_cjk_fragment"}):
        return False
    sentence_units = _word_units(_normalized_text(sentence))
    # Single-long-queue defer is useful for very short acknowledgements and
    # closed four-unit clauses, but three-unit zh tails often behave like
    # suffix fragments and create duplicate finals.
    if len(sentence_units) == 3:
        return False
    if len(queued_sentences) == 1:
        queued = _normalized_text(queued_sentences[0])
        if not queued:
            return False
        if _should_stage_boundary_candidate(queued, language):
            queued_flags = set(_final_sentence_diagnostic_flags(queued, language))
            if not queued_flags.intersection({"no_end_marker", "short_no_end_fragment", "low_value_cjk_fragment"}):
                if "short_cjk" not in queued_flags and len(sentence_units) > 4:
                    return False
                return True
    for queued_sentence in queued_sentences:
        queued = _normalized_text(queued_sentence)
        if not queued:
            return False
        if not _should_stage_boundary_candidate(queued, language):
            return False
        queued_flags = set(_final_sentence_diagnostic_flags(queued, language))
        if "short_cjk" not in queued_flags or queued_flags.intersection({"no_end_marker", "short_no_end_fragment"}):
            return False
    return True


def _should_extend_zh_long_closed_stage_age(
    sentence: str,
    language: str,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    if language != "zh" or queued_sentences:
        return False
    normalized = _normalized_text(sentence)
    if not normalized or _sentence_end_count(normalized) <= 0:
        return False
    flags = set(_final_sentence_diagnostic_flags(normalized, language))
    if flags.intersection(
        {
            "empty",
            "short_cjk",
            "no_end_marker",
            "short_no_end_fragment",
            "low_value_cjk_fragment",
            "cjk_internal_gap",
            "cjk_repeated_ngram",
            "repeated_word_ngram",
            "trailing_ellipsis",
        }
    ):
        return False
    sentence_words = _word_units(normalized)
    if len(sentence_words) < 12:
        return False
    return _boundary_sentence_end_count(normalized) > 1 or "，" in normalized or "," in normalized


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


def _has_preferred_deferred_revision(sentence: str, deferred_revision_sentences: tuple[str, ...]) -> bool:
    normalized_sentence = _normalized_text(sentence)
    if not normalized_sentence:
        return False
    for deferred in deferred_revision_sentences:
        normalized_deferred = _normalized_text(deferred)
        if not normalized_deferred or normalized_deferred == normalized_sentence:
            continue
        if not _sentences_are_revisions(normalized_sentence, normalized_deferred):
            continue
        if _prefer_sentence_revision(normalized_sentence, normalized_deferred) == normalized_deferred:
            return True
    return False


def _has_preferred_prefix_aligned_cjk_queue_correction(
    sentence: str,
    deferred_revision_sentences: tuple[str, ...],
) -> bool:
    normalized_sentence = _normalized_text(sentence)
    if not normalized_sentence or not _is_cjk_text(normalized_sentence):
        return False
    if _sentence_end_count(normalized_sentence) <= 0:
        return False
    sentence_words = _word_units(normalized_sentence)
    if len(sentence_words) < 10:
        return False
    for deferred in deferred_revision_sentences:
        normalized_deferred = _normalized_text(deferred)
        if not normalized_deferred or normalized_deferred == normalized_sentence or not _is_cjk_text(normalized_deferred):
            continue
        if _sentence_end_count(normalized_deferred) <= 0:
            continue
        if _prefer_sentence_revision(normalized_sentence, normalized_deferred) != normalized_deferred:
            continue
        deferred_words = _word_units(normalized_deferred)
        if len(deferred_words) < 10:
            continue
        aligned_blocks = [
            block
            for block in SequenceMatcher(None, sentence_words, deferred_words, autojunk=False).get_matching_blocks()
            if block.size > 0 and block.a == block.b
        ]
        if not aligned_blocks:
            continue
        first = aligned_blocks[0]
        if first.a != 0 or first.size < 4:
            continue
        total_aligned = sum(block.size for block in aligned_blocks)
        shorter = min(len(sentence_words), len(deferred_words))
        if len(aligned_blocks) >= 2 and total_aligned >= max(8, shorter // 2):
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
    if _has_preferred_deferred_revision(sentence, deferred_revision_sentences):
        return False
    if (
        language == "zh"
        and staged_confirmations <= 1
        and _has_preferred_prefix_aligned_cjk_queue_correction(sentence, deferred_revision_sentences)
    ):
        return False
    if language == "ko" and _has_restart_like_repeat_for_next_completed(sentence):
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


def _has_restart_like_repeat_for_next_completed(sentence: str) -> bool:
    words = _word_units(sentence)
    if len(words) < 10:
        return False
    return _has_restart_prefix_run(words)


def _has_restart_prefix_run(words: list[str]) -> bool:
    if len(words) < 10:
        return False
    max_prefix = min(6, len(words) // 2)
    for size in range(max_prefix, 3, -1):
        prefix = tuple(words[:size])
        max_restart = min(len(words) - size, size + 3)
        for restart in range(size - 1, max_restart + 1):
            candidate = tuple(words[restart : restart + size])
            matches = sum(1 for left, right in zip(prefix, candidate, strict=True) if left == right)
            if matches >= size - 1:
                return True
    return False


def _should_finalize_with_right_context(
    sentence: str,
    language: str,
    deferred_revision_sentences: tuple[str, ...],
    promoted_from_queue_same_chunk: bool = False,
) -> bool:
    if not _normalized_text(sentence) or not deferred_revision_sentences:
        return False
    if promoted_from_queue_same_chunk:
        first_queued = _normalized_text(deferred_revision_sentences[0])
        if not first_queued:
            return False
        if not _sentences_are_revisions(sentence, first_queued):
            queued_flags = set(_final_sentence_diagnostic_flags(first_queued, language))
            queued_words = _word_units(first_queued)
            if (
                _sentence_end_count(first_queued) > 0
                and len(queued_words) <= 3
                and not queued_flags.intersection({"empty", "no_end_marker", "short_no_end_fragment", "trailing_ellipsis"})
            ):
                return False
    if _has_deferred_revision_extension(sentence, deferred_revision_sentences):
        return False
    if _has_preferred_deferred_revision(sentence, deferred_revision_sentences):
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
    normalized_sentence = _normalized_text(sentence)
    for deferred in deferred_revision_sentences:
        deferred_flags = set(_final_sentence_diagnostic_flags(deferred, language))
        if "no_end_marker" not in deferred_flags:
            continue
        normalized_deferred = _normalized_text(deferred)
        if not normalized_deferred:
            return True
        sentence_words = _word_units(normalized_sentence)
        deferred_words = _word_units(normalized_deferred)
        _best_i, _best_j, best_len = _best_common_word_run(sentence_words, deferred_words)
        if best_len < 4:
            return True
        if _prefer_sentence_revision(normalized_sentence, normalized_deferred) != normalized_sentence:
            return True
    return False


def _is_ko_short_closed_sentence(
    sentence: str,
    language: str,
    *,
    max_units: int = 2,
) -> bool:
    if language != "ko":
        return False
    normalized_sentence = _normalized_text(sentence)
    if not normalized_sentence or _sentence_end_count(normalized_sentence) <= 0:
        return False
    sentence_flags = set(_final_sentence_diagnostic_flags(normalized_sentence, language))
    if sentence_flags.intersection({"empty", "no_end_marker", "short_no_end_fragment", "trailing_ellipsis"}):
        return False
    sentence_units = _word_units(normalized_sentence)
    return 0 < len(sentence_units) <= max_units


def _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
    sentence: str,
    language: str,
    reason: str,
    staged_confirmations: int,
    queued_entries: tuple[dict[str, object], ...],
    *,
    sentence_required_confirmations: int,
) -> bool:
    if reason not in {"aged", "aged_forced", "next_completed"}:
        return False
    if language != "ko" or not queued_entries:
        return False
    if staged_confirmations >= sentence_required_confirmations:
        return False
    normalized_sentence = _normalized_text(sentence)
    if not _is_ko_short_closed_sentence(normalized_sentence, language):
        return False
    sentence_units = _word_units(normalized_sentence)
    clean_closed_queue_count = 0
    clean_closed_queue_word_lengths: list[int] = []
    saw_stronger_queue_candidate = False
    for entry in queued_entries:
        queued_sentence = _normalized_text(str(entry.get("sentence") or ""))
        if not queued_sentence or _sentence_end_count(queued_sentence) <= 0:
            continue
        queued_flags = set(_final_sentence_diagnostic_flags(queued_sentence, language))
        if queued_flags.intersection({"empty", "no_end_marker", "short_no_end_fragment", "trailing_ellipsis"}):
            continue
        queued_units = _word_units(queued_sentence)
        clean_closed_queue_count += 1
        clean_closed_queue_word_lengths.append(len(queued_units))
        if len(queued_units) < len(sentence_units) + 2:
            continue
        queued_confirmations = int(entry.get("confirmations", 0))
        if len(sentence_units) > 1 and queued_confirmations >= max(2, staged_confirmations + 1):
            return True
        if queued_confirmations >= max(2, staged_confirmations + 1):
            saw_stronger_queue_candidate = True
    if len(sentence_units) != 1:
        return False
    allow_next_completed_single_queue_statement = (
        reason == "next_completed"
        and staged_confirmations <= 2
        and clean_closed_queue_count == 1
        and bool(clean_closed_queue_word_lengths)
        and clean_closed_queue_word_lengths[0] >= 4
        and normalized_sentence.endswith(".")
        and len(normalized_sentence) <= 3
    )
    if staged_confirmations > 1 and not allow_next_completed_single_queue_statement:
        return False
    if clean_closed_queue_count >= 4:
        return True
    if clean_closed_queue_count == 3:
        return False
    if allow_next_completed_single_queue_statement:
        return True
    if (
        clean_closed_queue_count == 1
        and clean_closed_queue_word_lengths
        and clean_closed_queue_word_lengths[0] >= 4
        and normalized_sentence.endswith(".")
        and staged_confirmations <= 1
    ):
        return True
    return saw_stronger_queue_candidate


def _should_suppress_right_context_short_prefix_extension_with_single_queue(
    sentence: str,
    reason: str,
    queued_sentences: tuple[str, ...],
) -> bool:
    if reason != "right_context" or len(queued_sentences) != 1:
        return False
    sentence_words = _word_units(sentence)
    queued_words = _word_units(queued_sentences[0])
    if not sentence_words or len(sentence_words) > 4:
        return False
    if len(queued_words) < len(sentence_words) + 2:
        return False
    prefix_words = 0
    for sentence_word, queued_word in zip(sentence_words, queued_words):
        if sentence_word != queued_word:
            break
        prefix_words += 1
    return prefix_words >= 3


def _should_suppress_ko_pure_latin_final_with_hangul_queue(
    sentence: str,
    language: str,
    reason: str,
    queued_sentences: tuple[str, ...],
) -> bool:
    if language != "ko" or reason not in {"aged", "aged_forced", "replaced_aged", "right_context"}:
        return False
    sentence_words = _word_units(sentence)
    if not sentence_words:
        return False
    if not _has_latin_words(sentence_words) or _has_hangul_words(sentence_words) or _has_cjk_words(sentence_words):
        return False
    return any(_has_hangul_words(_word_units(queued_sentence)) for queued_sentence in queued_sentences)


def _should_suppress_ko_numeric_aged_final_with_queue(
    sentence: str,
    language: str,
    reason: str,
    queued_sentences: tuple[str, ...],
) -> bool:
    if language != "ko" or reason not in {"aged", "aged_forced"} or not queued_sentences:
        return False
    sentence_words = _word_units(sentence)
    if not sentence_words:
        return False
    digit_token_count = sum(1 for word in sentence_words if _DIGIT_RE.search(word))
    if digit_token_count < 2:
        return False
    queue_word_lengths = [len(_word_units(queued_sentence)) for queued_sentence in queued_sentences if queued_sentence]
    if not queue_word_lengths:
        return False
    return max(queue_word_lengths) <= 4


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


def _should_allow_no_text_stage_aging(
    sentence: str,
    language: str,
    queued_sentences: tuple[str, ...] = (),
) -> bool:
    normalized_sentence = _normalized_text(sentence)
    if not normalized_sentence:
        return False
    if language == "zh":
        return _should_stage_boundary_candidate(normalized_sentence, language)
    if language != "ko":
        return False
    if not _should_stage_boundary_candidate(normalized_sentence, language):
        return False
    if not queued_sentences or len(queued_sentences) > 2:
        return False
    if len(queued_sentences) == 1:
        queued_sentence = _normalized_text(queued_sentences[0])
        if not queued_sentence or not _should_stage_boundary_candidate(queued_sentence, language):
            return False
        sentence_units = len(_word_units(normalized_sentence))
        if sentence_units >= 4:
            return True
        return sentence_units >= 3 and normalized_sentence.endswith("?")
    if len(_word_units(normalized_sentence)) < 3:
        return False
    for queued_sentence in queued_sentences:
        normalized_queued = _normalized_text(queued_sentence)
        if not normalized_queued:
            return False
        if not _should_stage_boundary_candidate(normalized_queued, language):
            return False
        if len(_word_units(normalized_queued)) > 3:
            return False
    return True

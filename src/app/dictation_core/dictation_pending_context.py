from __future__ import annotations

from difflib import SequenceMatcher

from src.app.dictation_core.dictation_recent_final import _recent_final_sentence_delta, _with_candidate_terminal
from src.app.dictation_core.dictation_revision_text import (
    _best_common_word_run,
    _has_cjk_words,
    _has_repeated_cjk_ngram,
    _has_repeated_word_ngram,
    _is_cjk_text,
    _normalized_text,
    _sentence_delta_from_words,
    _sentences_are_revisions,
    _word_units,
)
from src.app.dictation_core.sentence_boundary import sentence_end_count as _boundary_sentence_end_count


def _cjk_delta_from_words(words: list[str]) -> str:
    return "".join(words).strip()


def _has_later_completed_extension(candidate: str, later_sentences: list[str] | tuple[str, ...]) -> bool:
    normalized_candidate = _normalized_text(candidate)
    if not normalized_candidate or _boundary_sentence_end_count(normalized_candidate) > 0:
        return False
    for sentence in later_sentences:
        normalized_later = _normalized_text(sentence)
        if _boundary_sentence_end_count(normalized_later) == 0:
            continue
        if not normalized_later.startswith(normalized_candidate):
            continue
        if len(normalized_later) - len(normalized_candidate) >= 4:
            return True
    return False


def _is_pending_prefix_mixed_candidate(candidate: str, pending_text: str) -> bool:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(pending_text)
    if not normalized_candidate or not normalized_pending:
        return False
    candidate_units = _word_units(normalized_candidate)
    pending_units = _word_units(normalized_pending)
    if len(candidate_units) < 5 or len(pending_units) < 5:
        return False
    common_prefix = 0
    for candidate_unit, pending_unit in zip(candidate_units, pending_units):
        if candidate_unit != pending_unit:
            break
        common_prefix += 1
    if common_prefix < 4 or common_prefix == len(candidate_units) or common_prefix == len(pending_units):
        return False
    return True


def _is_prior_pending_recent_final_mixed_candidate(
    candidate: str,
    prior_pending_text: str,
    recent_sentences: list[str] | tuple[str, ...],
    language: str,
) -> bool:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(prior_pending_text)
    if not normalized_candidate or not normalized_pending or not recent_sentences:
        return False
    candidate_words = _word_units(normalized_candidate)
    pending_words = _word_units(normalized_pending)
    if candidate_words[: len(pending_words)] != pending_words:
        return False
    suffix_words = candidate_words[len(pending_words) :]
    if len(pending_words) >= 2 and 1 <= len(suffix_words) <= 3:
        suffix_key = "".join(suffix_words).lower()
        if len(suffix_key) < 6:
            return False
        for recent in reversed(recent_sentences):
            recent_words = _word_units(recent)
            if len(recent_words) < len(suffix_words) + 2:
                continue
            recent_suffix_key = "".join(recent_words[-len(suffix_words) :]).lower()
            if SequenceMatcher(None, recent_suffix_key, suffix_key, autojunk=False).ratio() >= 0.86:
                return True
        return False
    if len(pending_words) < 3 or len(suffix_words) < 4:
        return False
    suffix_text = _sentence_delta_from_words(suffix_words)
    for recent in reversed(recent_sentences):
        recent_words = _word_units(recent)
        if len(recent_words) < len(suffix_words):
            continue
        if _recent_final_sentence_delta(suffix_text, recent, language) == "":
            return True
        ratio = SequenceMatcher(None, recent_words, suffix_words, autojunk=False).ratio()
        _best_i, best_j, common_run = _best_common_word_run(recent_words, suffix_words)
        suffix_coverage = common_run / max(len(suffix_words), 1)
        if best_j <= 3 and common_run >= 4 and (ratio >= 0.55 or suffix_coverage >= 0.55):
            return True
    return False


def _strip_prior_pending_prefix_revision(staged_sentence: str, candidate: str, prior_pending_text: str) -> str:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(prior_pending_text)
    if not normalized_candidate or not normalized_pending:
        return normalized_candidate
    if _boundary_sentence_end_count(normalized_pending) > 0:
        return normalized_candidate
    candidate_words = _word_units(normalized_candidate)
    pending_words = _word_units(normalized_pending)
    if not candidate_words or not pending_words or len(pending_words) >= len(candidate_words):
        return normalized_candidate
    if candidate_words[: len(pending_words)] != pending_words:
        return normalized_candidate
    suffix_words = candidate_words[len(pending_words) :]
    if len(suffix_words) < 4:
        return normalized_candidate
    suffix = _cjk_delta_from_words(suffix_words) if _has_cjk_words(candidate_words) else _sentence_delta_from_words(suffix_words)
    if not suffix:
        return normalized_candidate
    if len(pending_words) > 12:
        if not (_has_repeated_word_ngram(pending_words) or _has_repeated_cjk_ngram(pending_words)):
            return normalized_candidate
        if _boundary_sentence_end_count(normalized_candidate) <= _boundary_sentence_end_count(normalized_pending):
            return normalized_candidate
        if normalized_candidate.startswith(normalized_pending):
            suffix = normalized_candidate[len(normalized_pending) :].strip()
        return _with_candidate_terminal(suffix, normalized_candidate)
    if staged_sentence and not _sentences_are_revisions(staged_sentence, suffix):
        staged_words = _word_units(staged_sentence)
        suffix_words = _word_units(suffix)
        _best_i, _best_j, best_len = _best_common_word_run(staged_words, suffix_words)
        if best_len / max(min(len(staged_words), len(suffix_words)), 1) < 0.60:
            return normalized_candidate
    return _with_candidate_terminal(suffix, normalized_candidate)


def _strip_prior_pending_prefix_from_final(candidate: str, prior_pending_text: str, should_stage_boundary_candidate) -> str:
    normalized_candidate = _normalized_text(candidate)
    normalized_pending = _normalized_text(prior_pending_text)
    if not normalized_candidate or not normalized_pending:
        return normalized_candidate
    if _boundary_sentence_end_count(normalized_pending) > 0 or _boundary_sentence_end_count(normalized_candidate) <= 0:
        return normalized_candidate
    candidate_words = _word_units(normalized_candidate)
    pending_words = _word_units(normalized_pending)
    if not candidate_words or not pending_words or len(pending_words) >= len(candidate_words):
        return normalized_candidate
    if candidate_words[: len(pending_words)] != pending_words:
        return normalized_candidate
    suffix = normalized_candidate[len(normalized_pending) :].strip() if normalized_candidate.startswith(normalized_pending) else ""
    if not suffix:
        suffix_words = candidate_words[len(pending_words) :]
        suffix = _cjk_delta_from_words(suffix_words) if _has_cjk_words(candidate_words) else _sentence_delta_from_words(suffix_words)
    if not suffix or _boundary_sentence_end_count(suffix) <= 0:
        return normalized_candidate
    if not should_stage_boundary_candidate(suffix, "zh" if _is_cjk_text(suffix) else ""):
        return normalized_candidate
    return _with_candidate_terminal(suffix, normalized_candidate)

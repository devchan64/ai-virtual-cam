from __future__ import annotations

import re


def normalized_text(text: object) -> str:
    return " ".join(str(text).split())


def word_units(text: object) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", normalized_text(text).lower())


def _is_subsequence_at(words: list[str], candidate: list[str], start: int) -> bool:
    if start < 0 or start + len(candidate) > len(words):
        return False
    return words[start : start + len(candidate)] == candidate


def sentence_delta_from_words(words: list[str]) -> str:
    return " ".join(words).strip()


def append_context(committed_text: str, new_text: str, *, max_chars: int = 4000) -> str:
    combined = normalized_text(f"{committed_text} {new_text}")
    if len(combined) <= max_chars:
        return combined
    return combined[-max_chars:]


def consume_committed_prefix(pending_text: str, committed_sentence: str) -> str:
    pending = normalized_text(pending_text)
    committed = normalized_text(committed_sentence)
    if not pending or not committed:
        return pending
    pending_words = word_units(pending)
    committed_words = word_units(committed)
    if not pending_words or not committed_words:
        return pending

    leading_connectives = {"and", "but", "or", "so", "then"}
    variants: list[tuple[int, list[str]]] = [(0, pending_words)]
    if pending_words[0] in leading_connectives:
        variants.append((1, pending_words[1:]))

    for skip, pending_candidate in variants:
        if len(committed_words) >= len(pending_candidate) and _is_subsequence_at(committed_words, pending_candidate, 0):
            return ""
        if len(pending_candidate) >= len(committed_words) and _is_subsequence_at(pending_candidate, committed_words, 0):
            remaining = pending_words[skip + len(committed_words) :]
            if skip == 1 and remaining:
                return sentence_delta_from_words([pending_words[0], *remaining])
            return sentence_delta_from_words(remaining)
        max_overlap = min(len(pending_candidate), len(committed_words))
        for overlap in range(max_overlap, 0, -1):
            if pending_candidate[:overlap] == committed_words[-overlap:]:
                remaining = pending_words[skip + overlap :]
                if skip == 1 and remaining:
                    return sentence_delta_from_words([pending_words[0], *remaining])
                return sentence_delta_from_words(remaining)
    return pending


def revision_lifecycle_context(committed_text: str, staged_sentence: str, pending_text: str) -> str:
    context = committed_text
    if staged_sentence:
        context = append_context(context, staged_sentence)
    if pending_text:
        context = append_context(context, pending_text)
    return context

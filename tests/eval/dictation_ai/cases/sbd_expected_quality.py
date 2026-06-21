from __future__ import annotations


EXPECTED_TERMINAL_MARKS = (".", "?", "!", "。", "？", "！")
EXPECTED_LOWERCASE_FRAGMENT_STARTERS = {
    "and",
    "but",
    "or",
    "so",
    "that",
    "then",
    "to",
    "with",
    "when",
    "where",
    "which",
    "who",
    "you",
}


def expected_quality_flags(expected_final: list[str]) -> list[str]:
    flags: list[str] = []
    if len(expected_final) >= 6:
        flags.append("many_expected_sentences")
    short_count = 0
    no_terminal_count = 0
    lowercase_fragment_count = 0
    for sentence in expected_final:
        units = sentence.split()
        has_terminal = bool(sentence and sentence.endswith(EXPECTED_TERMINAL_MARKS))
        if not has_terminal:
            if len(sentence) < 24 or (units and len(units) <= 4):
                short_count += 1
            no_terminal_count += 1
        first = units[0].strip(".,?!:;\"'()[]{}").lower() if units else ""
        if first in EXPECTED_LOWERCASE_FRAGMENT_STARTERS or (sentence[:1].islower() and units):
            lowercase_fragment_count += 1
    if short_count:
        flags.append("short_expected_fragment")
    if no_terminal_count:
        flags.append("no_terminal_expected")
    if lowercase_fragment_count:
        flags.append("lowercase_or_connector_start")
    if expected_final and no_terminal_count == len(expected_final):
        flags.append("all_expected_no_terminal")
    return flags

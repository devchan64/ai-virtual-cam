from __future__ import annotations


SBD_DIAGNOSTIC_TAG_MARKERS = (
    "audio-residual",
    "boundary",
    "cjk-internal-gap",
    "confirmed",
    "duplicate",
    "final",
    "fragment",
    "mixed-latin",
    "missing",
    "no-end",
    "no-speech",
    "no-text",
    "pending",
    "premature",
    "queue",
    "recent-final",
    "repeated",
    "revision",
    "sentence-destruction",
    "sliding-window",
    "speaker-transition",
    "stage",
    "staged",
    "stale",
    "tail-echo",
    "terminal-tail",
    "trailing",
)


def is_diagnostic_tag(tag_name: str) -> bool:
    return any(marker in tag_name for marker in SBD_DIAGNOSTIC_TAG_MARKERS)

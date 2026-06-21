from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str
    display: bool = True
    log_text: str | None = None
    final: bool = True
    segment_id: int | None = None


def is_modal_output_event(event: TranscriptEvent) -> bool:
    return event.display and event.kind in {"transcript", "translation", "error"}

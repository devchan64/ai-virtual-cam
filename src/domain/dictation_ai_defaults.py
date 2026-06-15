from __future__ import annotations

from src.domain.contracts.dictation_ai import WHISPER_CONTRACT, whisper_default, whisper_defaults

WHISPER_DEFAULTS = whisper_defaults()

__all__ = ["WHISPER_CONTRACT", "WHISPER_DEFAULTS", "whisper_default", "whisper_defaults"]

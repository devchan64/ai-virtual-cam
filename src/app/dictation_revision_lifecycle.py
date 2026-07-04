from __future__ import annotations

from src.app.dictation_recent_final import (
    _recent_final_output_delta,
    _recent_final_output_delta_with_reason,
    _recent_final_sentence_delta,
    _with_candidate_terminal,
)
from src.app.dictation_revision_progression import (
    _diagnostic_tail,
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _prefer_sentence_revision,
    _revision_internal_stability_bucket,
    _sentence_end_count,
    _should_age_staged_sentence,
    _should_defer_token_sentence_revision,
    _should_preserve_revision_confirmation_from_internal_stability,
    _should_reset_revision_age,
    _split_completed_sentences,
)


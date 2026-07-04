from __future__ import annotations
"""Compatibility entrypoint for stage runtime helpers.

The concrete implementations now live in:
- `dictation_pipeline_stage_runtime_candidate_helpers.py`
- `dictation_pipeline_stage_runtime_finalize_helpers.py`

Keep this module as the stable import surface for existing stage helper users.
"""

from src.app.dictation_pipeline_stage_runtime_candidate_helpers import (
    prepare_stage_candidate,
    promote_next_staged_sentence,
    start_staged_sentence,
    suppress_active_stage_for_quality,
    suppress_finalize_candidate,
)
from src.app.dictation_pipeline_stage_runtime_finalize_helpers import (
    apply_delta_finalize_guard,
    apply_recent_final_finalize_adjustment,
    emit_finalized_sentence,
    finalize_staged_sentence,
    preserve_staged_output_when_delta_fragment,
)

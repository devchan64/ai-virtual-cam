from __future__ import annotations
"""Compatibility entrypoint for candidate-side stage runtime helpers.

The concrete implementations now live in:
- `dictation_pipeline_stage_runtime_queue_helpers.py`
- `dictation_pipeline_stage_runtime_candidate_prepare_helpers.py`
"""

from src.app.dictation_pipeline_stage_runtime_candidate_prepare_helpers import prepare_stage_candidate
from src.app.dictation_pipeline_stage_runtime_queue_helpers import (
    promote_next_staged_sentence,
    start_staged_sentence,
    suppress_active_stage_for_quality,
    suppress_finalize_candidate,
)

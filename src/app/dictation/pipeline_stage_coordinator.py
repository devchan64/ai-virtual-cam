from __future__ import annotations
"""Compatibility entrypoint for stage coordinator helpers.

The concrete implementations now live in:
- `dictation_pipeline_stage_revision_helpers.py`
- `dictation_pipeline_stage_replacement_helpers.py`
"""

from src.app.dictation.pipeline_stage_replacement_helpers import handle_replacement_candidate
from src.app.dictation.pipeline_stage_revision_helpers import handle_revision_candidate

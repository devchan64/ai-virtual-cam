from __future__ import annotations
"""Shared staged-sentence state mutation helpers."""

from typing import Callable

from src.app.dictation.pipeline_types import ActiveStage


def tick_stage_age(active_stage: ActiveStage, *, chunk_index: int, count_metric: Callable[[str, int], None]) -> None:
    active_stage.age += 1
    active_stage.deferredAgeChunk = chunk_index
    count_metric("stage_age_tick")


def tick_stage_age_once(
    active_stage: ActiveStage,
    *,
    chunk_index: int,
    count_metric: Callable[[str, int], None],
) -> bool:
    if active_stage.deferredAgeChunk == chunk_index:
        return False
    tick_stage_age(active_stage, chunk_index=chunk_index, count_metric=count_metric)
    return True

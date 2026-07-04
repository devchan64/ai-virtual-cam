from __future__ import annotations
"""Queue/start/suppress helpers for stage runtime."""

from typing import Callable

from src.app.dictation_core.dictation_recent_final import _recent_final_output_delta
from src.app.dictation_core.dictation_revision_progression import _diagnostic_tail
from src.app.dictation_core.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _normalized_text,
    _should_stage_boundary_candidate,
)
from src.app.dictation.pipeline_types import ActiveStage, CommitBufferNode, TranscriptWorkerLike


def promote_next_staged_sentence(
    *,
    active_stage: ActiveStage,
    commit_buffer_node: CommitBufferNode,
    detected: str,
    chunk_index: int,
    recent_transcripts: tuple[str, ...],
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    count_recent_final_stable_internal_suppression: Callable[[str], None],
    staged_queue_max_promotion_age_chunks: Callable[[], int],
    queue_promotion_backlog_boost_remaining: Callable[[], int],
    consume_queue_promotion_backlog_boost: Callable[[], None],
    queue_backlog_promotion_extra_age: Callable[[], int],
    worker: TranscriptWorkerLike,
) -> None:
    while True:
        base_max_promotion_age = staged_queue_max_promotion_age_chunks()
        boosted_max_promotion_age = base_max_promotion_age
        if queue_promotion_backlog_boost_remaining() > 0:
            boosted_max_promotion_age += max(0, queue_backlog_promotion_extra_age())
        promoted = commit_buffer_node.promote_if_idle(
            chunk_index=chunk_index,
            max_promotion_age_chunks=boosted_max_promotion_age,
            count_metric=count_metric,
            count_segment_state=count_segment_state,
        )
        if not promoted:
            return
        if active_stage.age > base_max_promotion_age:
            consume_queue_promotion_backlog_boost()
            count_metric("stage_queue_backlog_boost_promote", 1)
        promoted_quality_flags = set(_final_sentence_diagnostic_flags(active_stage.sentence, detected))
        if not _should_stage_boundary_candidate(active_stage.sentence, detected):
            count_metric("stage_queue_quality_suppressed", 1)
            count_segment_state("suppressed", 1)
            for flag in promoted_quality_flags:
                count_metric(f"stage_queue_quality_{flag}", 1)
            worker._emit(
                "status",
                "받아쓰기 AI stage 큐 품질 폐기: "
                f"chunk={chunk_index} staged_tail={_diagnostic_tail(active_stage.sentence)}",
                display=False,
            )
            active_stage.clear()
            continue
        promoted_sentence, recent_source = _recent_final_output_delta(
            active_stage.sentence,
            recent_transcripts,
            detected,
        )
        if recent_source is None:
            break
        if promoted_sentence and _should_stage_boundary_candidate(promoted_sentence, detected):
            active_stage.sentence = promoted_sentence
            active_stage.deltaSuppressedChunks = 0
            active_stage.deltaSuppressedChunkIndex = -1
            count_metric("stage_queue_recent_final_delta_trimmed", 1)
            break
        count_metric("stage_queue_recent_final_suppressed", 1)
        count_recent_final_stable_internal_suppression("stage_queue_recent_final_suppressed")
        count_segment_state("suppressed", 1)
        worker._emit(
            "status",
            "받아쓰기 AI stage 큐 최근 final 중복 폐기: "
            f"chunk={chunk_index} recent_tail={_diagnostic_tail(recent_source)} "
            f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
            display=False,
        )
        active_stage.clear()
    worker._emit(
        "status",
        "받아쓰기 AI stage 큐 승격: "
        f"chunk={chunk_index} queue_remaining={len(commit_buffer_node)} "
        f"staged_confirmations={active_stage.confirmations} staged_age={active_stage.age} "
        f"staged_tail={_diagnostic_tail(active_stage.sentence)}",
        display=False,
    )
    worker._emit(
        "transcript",
        active_stage.sentence,
        log_text=f"[{detected}] {active_stage.sentence}",
        final=False,
    )


def start_staged_sentence(
    *,
    active_stage: ActiveStage,
    candidate: str,
    forced: bool,
    detected: str,
    chunk_index: int,
    committed_text: str,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    worker: TranscriptWorkerLike,
) -> None:
    count_metric("stage_start")
    count_segment_state("staged")
    active_stage.start(candidate, forced=forced, chunk_index=chunk_index)
    worker._emit(
        "status",
        "받아쓰기 AI stage 시작: "
        f"chunk={chunk_index} forced={forced} candidate_chars={len(_normalized_text(candidate))} "
        f"candidate_tail={_diagnostic_tail(candidate)} committed_chars={len(_normalized_text(committed_text))}",
        display=False,
    )
    worker._emit(
        "transcript",
        active_stage.sentence,
        log_text=f"[{detected}] {active_stage.sentence}",
        final=False,
    )


def suppress_active_stage_for_quality(
    *,
    active_stage: ActiveStage,
    detected: str,
    chunk_index: int,
    metric_name: str,
    status_prefix: str,
    extra_status: str,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
) -> None:
    count_metric(metric_name)
    count_segment_state("suppressed")
    flags = _final_sentence_diagnostic_flags(active_stage.sentence, detected)
    worker._emit(
        "status",
        f"{status_prefix}: "
        f"chunk={chunk_index} flags={','.join(flags) or 'none'} "
        f"{extra_status}staged_tail={_diagnostic_tail(active_stage.sentence)}",
        display=False,
    )
    active_stage.clear()
    promote_next_staged_sentence(detected)


def suppress_finalize_candidate(
    *,
    active_stage: ActiveStage,
    detected: str,
    chunk_index: int,
    metric_name: str,
    reason: str,
    status_prefix: str,
    text: str,
    extra_status: str,
    count_metric: Callable[[str, int], None],
    count_segment_state: Callable[[str, int], None],
    promote_next_staged_sentence: Callable[[str], None],
    worker: TranscriptWorkerLike,
) -> list[tuple[int, str]]:
    active_stage.clear()
    count_metric(metric_name)
    count_segment_state("suppressed")
    worker._emit(
        "status",
        f"{status_prefix}: chunk={chunk_index} reason={reason} text={text!r} {extra_status}".rstrip(),
        display=False,
    )
    promote_next_staged_sentence(detected)
    return []

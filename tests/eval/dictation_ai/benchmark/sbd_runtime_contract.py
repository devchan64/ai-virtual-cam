from __future__ import annotations

import os


OFFLINE_MODEL_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}


def force_offline_model_cache_env() -> None:
    os.environ.update(OFFLINE_MODEL_ENV)


def runtime_contract() -> dict[str, object]:
    return {
        "backend": "sat",
        "device": "cuda",
        "compute_type": "float16",
        "offline_model_env": dict(OFFLINE_MODEL_ENV),
        "model_source": "local-cache-only",
    }


def lifecycle_replay_contract() -> dict[str, object]:
    """Describe how closely the text replay benchmark matches the runtime loop."""

    return {
        "scope": "text replay of SBD candidates and revision lifecycle",
        "shared_decision_helpers": [
            "src.app.dictation_transcript_logic._sentences_are_revisions",
            "src.app.dictation_transcript_logic._prefer_sentence_revision",
            "src.app.dictation_transcript_logic._next_revision_confirmation_count",
            "src.app.dictation_transcript_logic._should_reset_revision_age",
            "src.app.dictation_transcript_logic._replacement_decision_reason",
            "src.app.dictation_transcript_logic._should_defer_unconfirmed_replacement",
            "src.app.dictation_transcript_logic._should_finalize_before_replacement",
            "src.app.dictation_transcript_logic._should_stage_boundary_candidate",
            "src.app.dictation_transcript_logic._sentence_output_delta",
            "src.app.dictation_transcript_logic._recent_final_output_delta",
        ],
        "runtime_state_owner": "src.app.dictation_node_sentence_candidate_commit_buffer.SentenceCandidateCommitBufferNode",
        "replay_state_owner": "tests.eval.dictation_ai.benchmark.sbd_lifecycle_state.LifecycleState",
        "shared_state_transitions": [
            "staged queue enqueue/revision",
            "staged queue promotion",
            "queued revision pre-finalization preference",
        ],
        "state_machine_parity": "partial",
        "paper_evidence_limit": (
            "structural changes must be rechecked on the full challenge replay with sat+cuda+float16; "
            "changes that depend on runtime-only stability signals are not paper evidence from text replay alone"
        ),
        "replayed_runtime_signals": [
            "stable_analysis.stable_internal_ratio",
            "stable_analysis.stable_internal_chars",
            "stable_analysis.stable_overlap_source",
        ],
        "missing_runtime_signals": [
            "audio timestamp latency",
            "translation request/output linkage",
        ],
    }

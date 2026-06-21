from __future__ import annotations

import glob
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


SBD_CHALLENGE_CASE_DIR = Path(__file__).resolve().parent / "sbd_cases"
SBD_REPRESENTATIVE_CASE_DIR = Path(__file__).resolve().parent / "sbd_representative_cases"
SBD_CHALLENGE_LANGUAGES = ("en", "ko", "zh")
REPRESENTATIVE_REQUIRED_FIELDS = (
    "corpus_role",
    "sampling_unit",
    "sampling_rule",
    "source_log",
    "source_started_at",
    "source_ended_at",
    "language",
    "stt_backend",
    "stt_model",
    "window_seconds",
    "step_seconds",
    "sentence_finalize_age",
    "review_packet_id",
    "expected_final_reviewed_by",
    "chunks",
    "expected_final",
)
REPRESENTATIVE_SAMPLING_UNITS = ("time-window", "session-window")


def is_challenge_case_root(path: Path) -> bool:
    return path.resolve() == SBD_CHALLENGE_CASE_DIR.resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def iter_case_paths(inputs: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    for case_input in inputs:
        matches = sorted(Path(match) for match in glob.glob(str(case_input)))
        candidates = matches or [case_input]
        for candidate in candidates:
            if candidate.is_dir():
                if is_challenge_case_root(candidate):
                    for language in SBD_CHALLENGE_LANGUAGES:
                        paths.extend(sorted((candidate / language).glob("*.jsonl")))
                else:
                    paths.extend(sorted(candidate.rglob("*.jsonl")))
            else:
                paths.append(candidate)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def default_case_inputs() -> list[Path]:
    has_challenge_cases = any(
        (SBD_CHALLENGE_CASE_DIR / language).is_dir()
        and any((SBD_CHALLENGE_CASE_DIR / language).glob("*.jsonl"))
        for language in SBD_CHALLENGE_LANGUAGES
    )
    if SBD_CHALLENGE_CASE_DIR.is_dir() and has_challenge_cases:
        return [SBD_CHALLENGE_CASE_DIR]
    return []


def case_corpus_role(case_inputs: Iterable[Path]) -> str:
    resolved_inputs = {case_input.resolve() for case_input in case_inputs}
    if not resolved_inputs:
        return "exploratory"
    if all(_is_relative_to(path, SBD_CHALLENGE_CASE_DIR) for path in resolved_inputs):
        return "challenge-replay"
    if all(_is_relative_to(path, SBD_REPRESENTATIVE_CASE_DIR) for path in resolved_inputs):
        return "representative"
    return "exploratory"


def corpus_interpretation(corpus_role: str) -> str:
    if corpus_role == "challenge-replay":
        return "failure-enriched challenge replay baseline"
    if corpus_role == "representative":
        return "representative operating sample"
    return "exploratory case set"


def representative_metadata_record(payload: dict[str, object]) -> dict[str, object]:
    """Return the representative sampling fields needed for evidence summaries."""
    return {
        "sampling_unit": str(payload.get("sampling_unit", "")).strip(),
        "sampling_rule": str(payload.get("sampling_rule", "")).strip(),
        "source_log": str(payload.get("source_log", "")).strip(),
        "review_packet_id": str(payload.get("review_packet_id", "")).strip(),
        "expected_final_reviewed_by": str(payload.get("expected_final_reviewed_by", "")).strip(),
    }


def summarize_representative_metadata(records: Iterable[dict[str, object]]) -> dict[str, object]:
    sampling_unit_counts: Counter[str] = Counter()
    sampling_rule_counts: Counter[str] = Counter()
    source_log_counts: Counter[str] = Counter()
    review_packet_counts: Counter[str] = Counter()
    expected_final_reviewer_counts: Counter[str] = Counter()
    for record in records:
        sampling_unit = str(record.get("sampling_unit", "")).strip()
        sampling_rule = str(record.get("sampling_rule", "")).strip()
        source_log = str(record.get("source_log", "")).strip()
        review_packet_id = str(record.get("review_packet_id", "")).strip()
        expected_final_reviewed_by = str(record.get("expected_final_reviewed_by", "")).strip()
        if sampling_unit:
            sampling_unit_counts[sampling_unit] += 1
        if sampling_rule:
            sampling_rule_counts[sampling_rule] += 1
        if source_log:
            source_log_counts[source_log] += 1
        if review_packet_id:
            review_packet_counts[review_packet_id] += 1
        if expected_final_reviewed_by:
            expected_final_reviewer_counts[expected_final_reviewed_by] += 1
    return {
        "sampling_unit_counts": dict(sorted(sampling_unit_counts.items())),
        "sampling_rule_counts": dict(sorted(sampling_rule_counts.items())),
        "source_log_count": len(source_log_counts),
        "source_log_counts": dict(sorted(source_log_counts.items())),
        "review_packet_count": len(review_packet_counts),
        "review_packet_counts": dict(sorted(review_packet_counts.items())),
        "expected_final_reviewer_counts": dict(sorted(expected_final_reviewer_counts.items())),
    }


def build_evidence_protocol(
    *,
    case_summary: dict[str, object] | None,
    corpus_roles: list[str],
    paper_evidence: bool,
) -> dict[str, Any]:
    case_summary = case_summary or {}
    primary_role = str(case_summary.get("corpus_role") or (corpus_roles[0] if len(corpus_roles) == 1 else "mixed"))
    corpus_eligible = primary_role in {"challenge-replay", "representative"}
    if primary_role == "challenge-replay":
        experiment_stage = "challenge-replay"
        experiment_stage_description = (
            "failure reproduction and revision lifecycle trade-off analysis; "
            "not an operating-average quality estimate"
        )
        evidence_use = "failure replay lifecycle trade-off analysis"
        claim_scope_key = "failure-lifecycle-tradeoff"
        claim_scope = "failure-mode lifecycle trade-off only"
        supported_claims = [
            "revision lifecycle trade-off on observed failure cases",
            "finalization metric decomposition",
            "parameter adoption or rejection within the same challenge corpus",
        ]
        unsupported_claims = [
            "operating-average quality",
            "raw STT WER/CER improvement",
            "translation quality improvement",
            "universal threshold optimality",
        ]
        deferred_claims = [
            "operating-average finalization quality",
            "finalization latency",
            "translation-side churn reduction",
        ]
        limitations = [
            "not an operating-average quality estimate",
            "not raw STT WER/CER evidence",
            "not translation quality evidence",
        ]
        required_followup = [
            "representative operating corpus",
            "final event timestamp replay",
            "translation output replay",
        ]
    elif primary_role == "representative":
        experiment_stage = "representative-replay"
        experiment_stage_description = (
            "operating-average finalization estimate for a documented time/session sample; "
            "requires separate challenge replay regression check for parameter adoption"
        )
        evidence_use = "operating-average estimate"
        claim_scope_key = "operating-average-finalization"
        claim_scope = "operating-average finalization estimate only"
        supported_claims = [
            "operating-average finalization estimate for the sampled population",
            "representative finalization metric decomposition",
        ]
        unsupported_claims = [
            "failure-mode regression coverage",
            "raw STT WER/CER improvement",
            "translation quality improvement",
            "parameter adoption without challenge replay regression check",
        ]
        deferred_claims = [
            "translation-side churn reduction",
            "raw ASR accuracy comparison",
        ]
        limitations = [
            "not a failure-mode regression corpus",
            "does not by itself justify parameter adoption",
        ]
        required_followup = [
            "challenge replay regression check",
            "translation output replay",
        ]
    else:
        experiment_stage = "exploratory"
        experiment_stage_description = (
            "ad-hoc analysis only; rerun under challenge-replay or representative corpus before using as evidence"
        )
        evidence_use = "ad-hoc exploration"
        claim_scope_key = "no-paper-claim"
        claim_scope = "no paper claim"
        supported_claims = [
            "exploratory debugging only",
        ]
        unsupported_claims = [
            "paper evidence",
            "operating-average quality",
            "failure-mode regression coverage",
            "parameter adoption",
            "translation quality improvement",
        ]
        deferred_claims = [
            "rerun under challenge-replay or representative corpus contract",
        ]
        limitations = [
            "not paper evidence",
            "not comparable with challenge or representative summaries",
        ]
        required_followup = [
            "rerun with challenge-replay or representative corpus",
        ]
    required_evidence_fields = [
        "evidence_protocol.paper_evidence",
        "evidence_protocol.paper_evidence_eligible",
        "evidence_protocol.corpus_role",
        "evidence_protocol.experiment_stage",
        "evidence_protocol.claim_scope_key",
        "evidence_protocol.supported_claims",
        "evidence_protocol.unsupported_claims",
        "evidence_protocol.deferred_claims",
        "runtime_contract.backend",
        "runtime_contract.device",
        "runtime_contract.compute_type",
        "runtime_contract.model_source",
        "lifecycle_replay_contract.state_machine_parity",
        "lifecycle_replay_contract.shared_decision_helpers",
        "lifecycle_replay_contract.missing_runtime_signals",
        "case_summary.expected_final_case_count",
        "parameter_axes",
        "evidence_summary.results",
        "evidence_summary.adoption_review_counts",
    ]
    if primary_role == "representative":
        required_evidence_fields.extend(
            [
                "case_summary.representative_metadata.sampling_unit_counts",
                "case_summary.representative_metadata.sampling_rule_counts",
                "case_summary.representative_metadata.source_log_count",
                "case_summary.representative_metadata.review_packet_count",
                "case_summary.representative_metadata.expected_final_reviewer_counts",
                "case_summary.representative_review_packet_validation.packet_count",
                "case_summary.representative_review_packet_validation.ready_packet_count",
                "case_summary.representative_review_packet_validation.matched_case_count",
            ]
        )
    return {
        "paper_evidence": paper_evidence,
        "paper_evidence_corpus_eligible": corpus_eligible,
        "paper_evidence_eligible": paper_evidence and corpus_eligible,
        "corpus_role": primary_role,
        "corpus_roles": corpus_roles,
        "corpus_interpretation": corpus_interpretation(primary_role),
        "experiment_stage": experiment_stage,
        "experiment_stage_description": experiment_stage_description,
        "evidence_use": evidence_use,
        "claim_scope_key": claim_scope_key,
        "claim_scope": claim_scope,
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
        "deferred_claims": deferred_claims,
        "limitations": limitations,
        "required_followup": required_followup,
        "required_evidence_fields": required_evidence_fields,
    }


def _nested_evidence_value(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _has_required_evidence_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def missing_required_evidence_fields(payload: dict[str, Any]) -> list[str]:
    """Return required paper-evidence context paths that are absent or empty."""
    evidence_protocol = dict(payload.get("evidence_protocol", {}))
    required_fields = [
        str(field)
        for field in evidence_protocol.get("required_evidence_fields", [])
        if str(field).strip()
    ]
    return [
        field
        for field in required_fields
        if not _has_required_evidence_value(_nested_evidence_value(payload, field))
    ]


def _has_required_value(value: object) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    if isinstance(value, tuple):
        return any(str(item).strip() for item in value)
    return bool(str(value or "").strip())


def validate_representative_payload(
    payload: dict[str, object],
    *,
    path: Path,
    line_no: int,
    case_id: str,
    allow_draft: bool = False,
) -> None:
    optional_draft_fields = {"expected_final", "expected_final_reviewed_by"} if allow_draft else set()
    missing = [
        field
        for field in REPRESENTATIVE_REQUIRED_FIELDS
        if field not in optional_draft_fields
        if not _has_required_value(payload.get(field))
    ]
    if missing:
        raise ValueError(f"{path}:{line_no} representative case {case_id!r} missing metadata: {', '.join(missing)}")
    if str(payload.get("corpus_role", "")).strip() != "representative":
        raise ValueError(f"{path}:{line_no} representative case {case_id!r} must set corpus_role='representative'")
    sampling_unit = str(payload.get("sampling_unit", "")).strip()
    if sampling_unit not in REPRESENTATIVE_SAMPLING_UNITS:
        allowed = ", ".join(REPRESENTATIVE_SAMPLING_UNITS)
        raise ValueError(
            f"{path}:{line_no} representative case {case_id!r} has unsupported sampling_unit "
            f"{sampling_unit!r}; expected one of: {allowed}"
        )

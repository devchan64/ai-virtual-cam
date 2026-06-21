#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.dictation_ai.paper.audit_paper_claim_scope import audit_paper_claim_scope
from tests.eval.dictation_ai.paper.audit_paper_evidence_numbers import audit_paper_evidence_numbers
from tests.eval.dictation_ai.paper.audit_paper_reference_scope import audit_paper_reference_scope
from tests.eval.dictation_ai.paper.audit_sbd_followup_readiness import audit_followup_readiness
from tests.eval.dictation_ai.sweeps.validate_sbd_evidence_report import expand_report_paths, validate_reports


STRUCTURAL_PREFLIGHT_DEFAULT_OUTPUT = Path(
    ".tmp/eval/dictation-ai-sbd/structural-lifecycle-cases-baseline.json"
)


def _evidence_inventory(paths: list[Path]) -> dict[str, Any]:
    expanded = expand_report_paths(paths)
    if not expanded:
        raise ValueError("no evidence report files matched")
    summary = validate_reports(expanded)
    return {
        "report_count": summary["report_count"],
        "complete_report_count": summary["complete_report_count"],
        "paper_evidence_complete_report_count": summary["paper_evidence_complete_report_count"],
        "paper_evidence_rerun_candidate_count": summary["paper_evidence_rerun_candidate_count"],
        "complete_experiment_stage_counts": summary["complete_experiment_stage_counts"],
        "complete_claim_scope_key_counts": summary["complete_claim_scope_key_counts"],
        "complete_mixed_experiment_stage": summary["complete_mixed_experiment_stage"],
        "complete_mixed_claim_scope_key": summary["complete_mixed_claim_scope_key"],
        "ok": (
            int(summary["paper_evidence_complete_report_count"]) > 0
            and not bool(summary["complete_mixed_experiment_stage"])
            and not bool(summary["complete_mixed_claim_scope_key"])
        ),
    }


def _next_actions(followup: dict[str, Any]) -> list[str]:
    actions = list(followup.get("next_actions", []))
    if not actions:
        return ["rerun follow-up readiness audit with source and review packet artifacts"]
    return [str(action) for action in actions]


def _structural_preflight_summary(
    path: Path | None,
    *,
    result_path: Path | None = None,
) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        sources = []
    sources = [str(source).strip() for source in sources if str(source).strip()]
    case_path = sources[0] if len(sources) == 1 else ""
    expected_result_path = result_path or STRUCTURAL_PREFLIGHT_DEFAULT_OUTPUT
    result_exists = expected_result_path.exists()
    tag_counts = payload.get("tag_counts", {})
    if not isinstance(tag_counts, dict):
        tag_counts = {}
    focus_tags = {
        key: int(value)
        for key, value in tag_counts.items()
        if key
        in {
            "stage-queue",
            "missing-final",
            "staged-residue",
            "boundary-mismatch",
            "no-end-final",
            "duplicate-final",
            "false-final",
            "translation-skip",
            "structural-lifecycle",
        }
        and isinstance(value, int)
        and not isinstance(value, bool)
    }
    input_ready = (
        len(sources) == 1
        and str(payload.get("corpus_role", "")) == "exploratory"
        and int(payload.get("case_count", 0)) > 0
        and int(payload.get("expected_final_case_count", 0)) > 0
        and int(payload.get("draft_count", 0)) == 0
    )
    execution_status = "input-not-ready"
    if input_ready:
        execution_status = "result-present" if result_exists else "input-ready-not-run"
    return {
        "path": str(path),
        "sources": sources,
        "source_count": len(sources),
        "case_path": case_path,
        "expected_result_path": str(expected_result_path),
        "result_exists": result_exists,
        "execution_status": execution_status,
        "case_count": int(payload.get("case_count", 0)),
        "corpus_role": str(payload.get("corpus_role", "")),
        "expected_final_case_count": int(payload.get("expected_final_case_count", 0)),
        "draft_count": int(payload.get("draft_count", 0)),
        "language_counts": payload.get("language_counts", {}),
        "focus_tag_counts": dict(sorted(focus_tags.items())),
        "paper_evidence": False,
        "interpretation": "structural lifecycle preflight only; not paper evidence",
        "ready": input_ready,
    }


def _methodology_decision(
    *,
    inventory: dict[str, Any],
    claim_scope: dict[str, Any],
    followup: dict[str, Any],
    structural_preflight: dict[str, Any],
) -> dict[str, Any]:
    statuses = dict(claim_scope.get("claim_statuses", {}))
    representative = dict(followup.get("representative", {}))
    translation = dict(followup.get("translation", {}))
    representative_status = str(representative.get("status", ""))
    translation_status = str(translation.get("status", ""))
    complete_stage_counts = dict(inventory.get("complete_experiment_stage_counts", {}))
    complete_scope_counts = dict(inventory.get("complete_claim_scope_key_counts", {}))
    blocked_claims = [
        claim_id
        for claim_id, status in statuses.items()
        if status in {"사용 금지", "보류"}
    ]
    current_contract_rerun_needed = (
        int(inventory.get("paper_evidence_complete_report_count", 0)) <= 0
        and int(inventory.get("paper_evidence_rerun_candidate_count", 0)) > 0
    )
    if current_contract_rerun_needed:
        recommended_next_experiment = "rerun current-contract cuda challenge replay"
    elif representative_status == "blocked_on_human_expected_final":
        recommended_next_experiment = "human-review representative expected_final labels"
    elif representative_status == "ready_for_pilot_representative_replay":
        recommended_next_experiment = "run pilot representative replay"
    else:
        recommended_next_experiment = "repair representative source or packet readiness"
    if translation_status in {
        "blocked_on_translation_replay_linkage",
        "blocked_on_translation_logs",
        "blocked_on_translation_output_linkage",
    }:
        translation_next_experiment = "build translation replay linkage before translation claims"
        translation_role = "blocked until final-event to translation output linkage exists"
        translation_method_note = "add translation replay linkage before final-only translation stability claims"
    else:
        translation_next_experiment = "run translation replay"
        translation_role = "translation replay linkage is ready; run translation replay before stability claims"
        translation_method_note = "run translation replay before final-only translation stability claims"
    available_next_experiments = []
    if current_contract_rerun_needed:
        available_next_experiments.append(
            {
                "name": recommended_next_experiment,
                "role": "current-contract performance baseline",
                "paper_evidence": True,
                "blocked_by": "",
                "rerun_candidate_count": int(inventory.get("paper_evidence_rerun_candidate_count", 0)),
                "command": (
                    "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "
                    "./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py "
                    "--cases tests/eval/dictation_ai/sbd_cases --device cuda --compute-type float16 "
                    "--output .tmp/eval/dictation-ai-sbd/current-contract-challenge-replay.json"
                ),
            }
        )
    available_next_experiments.extend(
        [
            {
                "name": "human-review representative expected_final labels",
                "role": "paper-evidence expansion",
                "paper_evidence": False,
                "blocked_by": "human expected_final labels"
                if representative_status == "blocked_on_human_expected_final"
                else "",
            },
            {
            "name": translation_next_experiment,
            "role": "translation claim expansion",
            "paper_evidence": False,
            "blocked_by": translation_status
            if translation_status
            in {
                "blocked_on_translation_replay_linkage",
                "blocked_on_translation_logs",
                "blocked_on_translation_output_linkage",
            }
            else "",
            },
        ]
    )
    if bool(structural_preflight.get("ready", False)):
        structural_case_path = str(structural_preflight.get("case_path", "")).strip()
        structural_result_path = str(
            structural_preflight.get(
                "expected_result_path",
                STRUCTURAL_PREFLIGHT_DEFAULT_OUTPUT,
            )
        ).strip()
        available_next_experiments.append(
            {
                "name": "run structural lifecycle preflight on selected exploratory cases",
                "role": "logic-change preflight",
                "paper_evidence": False,
                "blocked_by": "",
                "case_count": int(structural_preflight.get("case_count", 0)),
                "case_path": structural_case_path,
                "expected_result_path": structural_result_path,
                "result_exists": bool(structural_preflight.get("result_exists", False)),
                "execution_status": str(structural_preflight.get("execution_status", "")),
                "preflight_command": (
                    "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "
                    "./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py "
                    f"--cases {structural_case_path} --device cuda --compute-type float16 "
                    f"--output {structural_result_path}"
                ),
                "promotion_requirement": (
                    "rerun the full 1113-case challenge replay with sat+cuda+float16 before using "
                    "any structural preflight result as paper evidence"
                ),
                "full_challenge_replay_command": (
                    "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "
                    "./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py "
                    "--cases tests/eval/dictation_ai/sbd_cases --device cuda --compute-type float16 "
                    "--paper-evidence --output .tmp/eval/dictation-ai-sbd/structural-lifecycle-full-challenge-replay.json"
                ),
            }
        )
    challenge_replay_valid = (
        complete_stage_counts
        == {"challenge-replay": inventory.get("complete_report_count", 0)}
        and complete_scope_counts
        == {"failure-lifecycle-tradeoff": inventory.get("complete_report_count", 0)}
    )
    return {
        "primary_interpretation": "failure-enriched challenge replay lifecycle analysis",
        "challenge_replay_valid": challenge_replay_valid,
        "threshold_sweep_role": "parameter adoption or rejection evidence, not a universal optimization claim",
        "representative_role": "blocked until human expected_final labels are promoted",
        "translation_role": translation_role,
        "blocked_claims": blocked_claims,
        "recommended_next_experiment": recommended_next_experiment,
        "translation_next_experiment": translation_next_experiment,
        "available_next_experiments": available_next_experiments,
        "method_reconstruction": [
            "keep challenge replay for observed failure lifecycle trade-off",
            "do not interpret challenge replay averages as operating average quality",
            "rerun current-contract challenge replay before optimizing from stale evidence"
            if current_contract_rerun_needed
            else "current challenge replay evidence contract is available",
            "promote traceable human-reviewed representative cases before operating-average claims",
            translation_method_note,
        ],
        "ok": challenge_replay_valid,
    }


def audit_paper_readiness(
    *,
    reports: list[Path],
    summary_path: Path,
    paper_path: Path,
    source_audit_path: Path,
    review_packet_validation_path: Path,
    representative_cases: Path,
    review_packets: Path | None,
    representative_draft_validation: Path | None = None,
    structural_preflight_validation: Path | None = None,
    structural_preflight_result: Path | None = None,
) -> dict[str, Any]:
    inventory = _evidence_inventory(reports)
    claim_scope = audit_paper_claim_scope(summary_path, paper_path)
    evidence_numbers = audit_paper_evidence_numbers(summary_path, paper_path)
    reference_scope = audit_paper_reference_scope(paper_path)
    structural_preflight = _structural_preflight_summary(
        structural_preflight_validation,
        result_path=structural_preflight_result,
    )
    followup = audit_followup_readiness(
        source_audit_path=source_audit_path,
        review_packet_validation_path=review_packet_validation_path,
        representative_cases=representative_cases,
        review_packets=review_packets,
        representative_draft_validation=representative_draft_validation,
    )
    current_claim_scope = "challenge-replay-only"
    if bool(followup.get("paper_evidence_ready", False)):
        current_claim_scope = "representative-or-translation-ready"
    methodology_decision = _methodology_decision(
        inventory=inventory,
        claim_scope=claim_scope,
        followup=followup,
        structural_preflight=structural_preflight,
    )
    checks = {
        "evidence_inventory": bool(inventory.get("ok", False)),
        "claim_scope": bool(claim_scope.get("ok", False)),
        "evidence_numbers": bool(evidence_numbers.get("ok", False)),
        "reference_scope": bool(reference_scope.get("ok", False)),
        "methodology": bool(methodology_decision.get("ok", False)),
    }
    return {
        "paper": str(paper_path),
        "summary": str(summary_path),
        "checks": checks,
        "ok": all(checks.values()),
        "current_claim_scope": current_claim_scope,
        "evidence_inventory": inventory,
        "claim_scope_audit": {
            "ok": claim_scope["ok"],
            "claim_statuses": claim_scope.get("claim_statuses", {}),
            "missing_guard_claims": claim_scope.get("missing_guard_claims", []),
            "evidence_contract": claim_scope.get("evidence_contract", {}),
        },
        "evidence_number_audit": {
            "ok": evidence_numbers["ok"],
            "missing_metrics": evidence_numbers.get("missing_metrics", []),
            "missing_counts": evidence_numbers.get("missing_counts", []),
            "inconsistent_metrics": evidence_numbers.get("inconsistent_metrics", []),
            "inconsistent_counts": evidence_numbers.get("inconsistent_counts", []),
            "evidence_contract": evidence_numbers.get("evidence_contract", {}),
        },
        "reference_scope_audit": {
            "ok": reference_scope["ok"],
            "missing_comparison_guards": reference_scope.get("missing_comparison_guards", []),
            "excluded_references": reference_scope.get("excluded_references", []),
        },
        "followup_readiness": {
            "representative_status": dict(followup.get("representative", {})).get("status", ""),
            "representative_draft_count": int(
                dict(dict(followup.get("representative", {})).get("draft_summary", {})).get(
                    "draft_count",
                    0,
                )
            ),
            "representative_draft_traceable": bool(
                dict(dict(followup.get("representative", {})).get("draft_summary", {})).get(
                    "traceable",
                    False,
                )
            ),
            "translation_status": dict(followup.get("translation", {})).get("status", ""),
            "paper_evidence_ready": bool(followup.get("paper_evidence_ready", False)),
            "next_actions": _next_actions(followup),
        },
        "structural_preflight": structural_preflight,
        "methodology_decision": methodology_decision,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Dictation AI paper readiness audit bundle.",
    )
    parser.add_argument(
        "reports",
        nargs="*",
        type=Path,
        default=[Path(".tmp/eval/dictation-ai-sbd/parameter-sweeps")],
        help="Evidence report files or directories.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json"),
    )
    parser.add_argument(
        "--paper",
        type=Path,
        default=Path("docs/paper/ko-revision-aware-realtime-stt.md"),
    )
    parser.add_argument(
        "--source-audit",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-source-audit.json"),
    )
    parser.add_argument(
        "--review-packet-validation",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json"),
    )
    parser.add_argument(
        "--representative-cases",
        type=Path,
        default=Path("tests/eval/dictation_ai/sbd_representative_cases"),
    )
    parser.add_argument(
        "--review-packets",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-source-review-packets.json"),
    )
    parser.add_argument(
        "--representative-draft-validation",
        type=Path,
        default=None,
        help="Optional validation summary for .tmp representative draft JSONL templates.",
    )
    parser.add_argument(
        "--structural-preflight-validation",
        type=Path,
        default=None,
        help="Optional validation summary for exploratory structural lifecycle case subsets.",
    )
    parser.add_argument(
        "--structural-preflight-result",
        type=Path,
        default=None,
        help="Optional expected output path for the structural lifecycle preflight run.",
    )
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = audit_paper_readiness(
            reports=args.reports,
            summary_path=args.summary,
            paper_path=args.paper,
            source_audit_path=args.source_audit,
            review_packet_validation_path=args.review_packet_validation,
            representative_cases=args.representative_cases,
            review_packets=args.review_packets,
            representative_draft_validation=args.representative_draft_validation,
            structural_preflight_validation=args.structural_preflight_validation,
            structural_preflight_result=args.structural_preflight_result,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[dictation-ai-paper-readiness] error: {exc}", file=sys.stderr)
        return 2
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

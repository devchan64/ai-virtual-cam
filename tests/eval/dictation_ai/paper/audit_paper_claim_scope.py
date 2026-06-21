#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tests.eval.dictation_ai.paper.audit_evidence_contract import audit_current_evidence_contract


RESTRICTED_CLAIM_GUARDS = {
    "operating_average_quality": [
        "운영 평균 품질 주장은 여전히 보류한다",
        "운영 평균 품질. representative corpus",
        "일반 사용자 전체 평균 품질",
    ],
    "translation_stability": [
        "translation replay 전에는 성능 주장으로 쓰지 않는다",
        "번역 안정성 주장은 final event timestamp",
        "번역 품질 개선 결과가 아니라 시스템 계약",
    ],
    "raw_stt_accuracy": [
        "raw STT 정확도 개선은 주장하지 않는다",
        "raw STT 정확도 개선, 특정 threshold의 보편 최적성",
        "SBD/finalization replay does not evaluate raw STT CER/WER",
    ],
    "runtime_loop_equivalence": [
        "end-to-end runtime 검증으로 표현하지 않는다",
        "운영 loop 전체 검증이 아니라",
        "state_machine_parity=partial",
    ],
}


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _claim_statuses(summary: dict[str, Any]) -> dict[str, str]:
    claims = summary.get("paper_claim_matrix", [])
    if not isinstance(claims, list):
        return {}
    statuses: dict[str, str] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id", ""))
        if claim_id:
            statuses[claim_id] = str(claim.get("status", ""))
    return statuses


def audit_paper_claim_scope(summary_path: Path, paper_path: Path) -> dict[str, Any]:
    summary = _load_json_object(summary_path)
    paper = paper_path.read_text(encoding="utf-8")
    statuses = _claim_statuses(summary)
    evidence_contract = audit_current_evidence_contract(summary)
    restricted_claims: list[dict[str, Any]] = []
    missing_guard_claims: list[dict[str, Any]] = []
    for claim_id, guard_phrases in RESTRICTED_CLAIM_GUARDS.items():
        status = statuses.get(claim_id, "missing")
        if status not in {"사용 금지", "보류"}:
            continue
        matched = [phrase for phrase in guard_phrases if phrase in paper]
        item = {
            "claim_id": claim_id,
            "status": status,
            "matched_guard_phrases": matched,
            "required_guard_phrases": guard_phrases,
        }
        restricted_claims.append(item)
        if not matched:
            missing_guard_claims.append(item)
    return {
        "paper": str(paper_path),
        "summary": str(summary_path),
        "claim_statuses": statuses,
        "restricted_claims": restricted_claims,
        "missing_guard_claims": missing_guard_claims,
        "evidence_contract": evidence_contract,
        "ok": not missing_guard_claims and evidence_contract["ok"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit that a paper draft carries guard text for restricted evidence claims.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json"),
        help="Complete paper evidence summary JSON.",
    )
    parser.add_argument(
        "--paper",
        type=Path,
        default=Path("docs/paper/ko-revision-aware-realtime-stt.md"),
        help="Paper draft Markdown to audit.",
    )
    args = parser.parse_args()
    try:
        result = audit_paper_claim_scope(args.summary, args.paper)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[dictation-ai-paper-claim-audit] error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

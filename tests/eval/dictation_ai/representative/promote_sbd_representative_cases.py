#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.dictation_ai.cases.sbd_case_paths import SBD_REPRESENTATIVE_CASE_DIR
from tests.eval.dictation_ai.cases.validate_sbd_case_files import validate_case_files


SUPPORTED_LANGUAGES = ("en", "ko", "zh")


def _case_hash(case_id: str) -> str:
    return hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:12]


def _load_jsonl_cases(paths: Iterable[Path]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"{path}:{line_no} case row must be a JSON object")
                cases.append(payload)
    return cases


def _target_path(case: dict[str, Any], *, output_root: Path) -> Path:
    case_id = str(case.get("id", "")).strip()
    language = str(case.get("language", "")).strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported representative case language: {language!r}")
    return output_root / language / f"reviewed-representative-{language}-{_case_hash(case_id)}.jsonl"


def promote_representative_cases(
    case_inputs: list[Path],
    *,
    review_packets: Path,
    output_root: Path = SBD_REPRESENTATIVE_CASE_DIR,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    validation = validate_case_files(
        case_inputs,
        require_expected_final=True,
        review_packets=review_packets,
        corpus_role_override="representative",
    )
    cases = _load_jsonl_cases(case_inputs)
    targets: list[dict[str, str]] = []
    seen_targets: set[Path] = set()
    for case in cases:
        target = _target_path(case, output_root=output_root)
        if target in seen_targets:
            raise ValueError(f"multiple cases resolve to the same target: {target}")
        seen_targets.add(target)
        if target.exists() and not overwrite:
            raise ValueError(f"target already exists: {target}")
        targets.append(
            {
                "id": str(case.get("id", "")).strip(),
                "language": str(case.get("language", "")).strip().lower(),
                "target": str(target),
            }
        )
    if not dry_run:
        for case, target_record in zip(cases, targets, strict=True):
            target = Path(target_record["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "promoted": not dry_run,
        "dry_run": dry_run,
        "output_root": str(output_root),
        "case_count": len(cases),
        "expected_final_case_count": int(validation.get("expected_final_case_count", 0)),
        "draft_count": int(validation.get("draft_count", 0)),
        "language_counts": validation.get("language_counts", {}),
        "targets": targets,
        "validation": validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote human-reviewed representative SBD cases into language shards.",
    )
    parser.add_argument("cases", nargs="+", type=Path)
    parser.add_argument("--review-packets", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=SBD_REPRESENTATIVE_CASE_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = promote_representative_cases(
            args.cases,
            review_packets=args.review_packets,
            output_root=args.output_root,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-representative-promote] error: {exc}", file=sys.stderr)
        return 1
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

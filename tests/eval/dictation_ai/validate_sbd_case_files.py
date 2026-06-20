#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def _iter_case_paths(inputs: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    for case_input in inputs:
        matches = sorted(Path(match) for match in glob.glob(str(case_input)))
        candidates = matches or [case_input]
        for candidate in candidates:
            if candidate.is_dir():
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
    missing = [path for path in unique if not path.is_file()]
    if missing:
        raise ValueError("SBD case files not found: " + ", ".join(str(path) for path in missing))
    if not unique:
        raise ValueError("no SBD case files matched")
    return unique


def validate_case_files(
    inputs: Iterable[Path],
    *,
    allow_drafts: bool = False,
    require_expected_final: bool = False,
) -> dict[str, object]:
    seen_ids: dict[str, str] = {}
    language_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    draft_count = 0
    case_count = 0
    expected_final_case_count = 0
    sources: list[str] = []
    for path in _iter_case_paths(inputs):
        sources.append(str(path))
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                payload = json.loads(line)
                case_id = str(payload.get("id") or "").strip()
                if not case_id:
                    raise ValueError(f"{path}:{line_no} missing case id")
                previous = seen_ids.get(case_id)
                if previous is not None:
                    raise ValueError(f"duplicate SBD case id {case_id!r}: {previous} and {path}:{line_no}")
                seen_ids[case_id] = f"{path}:{line_no}"
                chunks = payload.get("chunks")
                if chunks is None:
                    chunks = [payload.get("text", "")]
                if not any(str(chunk).strip() for chunk in chunks):
                    raise ValueError(f"{path}:{line_no} case {case_id!r} has no text chunks")
                is_draft = bool(payload.get("draft_expected_final_required", False))
                has_expected_final = any(str(item).strip() for item in payload.get("expected_final", []))
                if is_draft:
                    draft_count += 1
                    if not allow_drafts:
                        raise ValueError(
                            f"{path}:{line_no} case {case_id!r} is an unreviewed draft. "
                            "Fill expected_final and remove draft_expected_final_required before registering it."
                        )
                elif require_expected_final and not has_expected_final:
                    raise ValueError(f"{path}:{line_no} case {case_id!r} has no expected_final")
                if has_expected_final:
                    expected_final_case_count += 1
                case_count += 1
                language_counts[str(payload.get("language", "")).strip().lower() or "en"] += 1
                tag_counts.update(str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip())
    return {
        "case_count": case_count,
        "draft_count": draft_count,
        "expected_final_case_count": expected_final_case_count,
        "language_counts": dict(sorted(language_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "sources": sources,
    }


def enforce_case_thresholds(
    summary: dict[str, object],
    *,
    min_cases: int | None = None,
    min_expected_final_cases: int | None = None,
    max_drafts: int | None = None,
) -> None:
    case_count = int(summary.get("case_count", 0))
    draft_count = int(summary.get("draft_count", 0))
    expected_final_case_count = int(summary.get("expected_final_case_count", 0))
    if min_cases is not None and case_count < min_cases:
        raise ValueError(f"SBD case count below target: case_count={case_count} min_cases={min_cases}")
    if min_expected_final_cases is not None and expected_final_case_count < min_expected_final_cases:
        raise ValueError(
            "SBD expected-final case count below target: "
            f"expected_final_case_count={expected_final_case_count} "
            f"min_expected_final_cases={min_expected_final_cases}"
        )
    if max_drafts is not None and draft_count > max_drafts:
        raise ValueError(f"SBD draft count above limit: draft_count={draft_count} max_drafts={max_drafts}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate reviewed Dictation AI SBD benchmark case files.")
    parser.add_argument("cases", nargs="+", type=Path)
    parser.add_argument("--allow-drafts", action="store_true", help="Report draft counts without failing.")
    parser.add_argument(
        "--require-expected-final",
        action="store_true",
        help="Fail when a non-draft case has no expected_final. Use for reviewed finalization datasets.",
    )
    parser.add_argument("--min-cases", type=int, default=None, help="Fail when loaded case count is below this value.")
    parser.add_argument(
        "--min-expected-final-cases",
        type=int,
        default=None,
        help="Fail when non-empty expected_final case count is below this value.",
    )
    parser.add_argument("--max-drafts", type=int, default=None, help="Fail when draft marker count is above this value.")
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    summary = validate_case_files(
        args.cases,
        allow_drafts=args.allow_drafts,
        require_expected_final=args.require_expected_final,
    )
    enforce_case_thresholds(
        summary,
        min_cases=args.min_cases,
        min_expected_final_cases=args.min_expected_final_cases,
        max_drafts=args.max_drafts,
    )
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

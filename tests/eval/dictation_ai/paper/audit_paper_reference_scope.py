#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


COMPARISON_REFERENCE_GUARDS = {
    "https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf": [
        "비교 근거",
        "직접 근거로 사용하지 않는다",
        "VAD/pause 기반 구현 근거",
        "최적 segment length 근거로 쓰지는 않는다",
    ],
}

EXCLUDED_REFERENCE_URLS = {
    "https://aclanthology.org/2002.iwslt-1.15.pdf": "404 원문 링크",
    "https://arxiv.org/abs/2401.04868": "turn-taking/VAD 범위 밖",
    "https://aclanthology.org/2024.lrec-main.1036/": "turn-taking/VAD 범위 밖",
    "https://www.isca-archive.org/interspeech_2022/chang22_interspeech.pdf": "turn-taking/VAD 범위 밖",
    "https://aclanthology.org/2021.findings-acl.205/": "turn-taking/VAD 범위 밖",
}


def audit_paper_reference_scope(paper_path: Path) -> dict[str, Any]:
    paper = paper_path.read_text(encoding="utf-8")
    comparison_references: list[dict[str, Any]] = []
    missing_comparison_guards: list[dict[str, Any]] = []
    for url, guard_phrases in COMPARISON_REFERENCE_GUARDS.items():
        if url not in paper:
            continue
        matched = [phrase for phrase in guard_phrases if phrase in paper]
        item = {
            "url": url,
            "matched_guard_phrases": matched,
            "required_guard_phrases": guard_phrases,
        }
        comparison_references.append(item)
        if not matched:
            missing_comparison_guards.append(item)
    excluded_references = [
        {
            "url": url,
            "reason": reason,
        }
        for url, reason in sorted(EXCLUDED_REFERENCE_URLS.items())
        if url in paper
    ]
    return {
        "paper": str(paper_path),
        "comparison_references": comparison_references,
        "missing_comparison_guards": missing_comparison_guards,
        "excluded_references": excluded_references,
        "ok": not missing_comparison_guards and not excluded_references,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit that the paper uses comparison references only with scope guard text.",
    )
    parser.add_argument(
        "--paper",
        type=Path,
        default=Path("docs/paper/ko-revision-aware-realtime-stt.md"),
        help="Paper draft Markdown to audit.",
    )
    args = parser.parse_args()
    try:
        result = audit_paper_reference_scope(args.paper)
    except OSError as exc:
        print(f"[dictation-ai-paper-reference-audit] error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

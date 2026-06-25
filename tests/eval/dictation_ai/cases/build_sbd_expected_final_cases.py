from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tests.eval.dictation_ai.cases.sbd_case_paths import SBD_CHALLENGE_LANGUAGES, iter_case_paths
from tests.eval.dictation_ai.cases.sbd_input_evidence import (
    DEFAULT_REPEAT_OBSERVATIONS,
    case_stable_sentence_candidates,
    chunk_input_texts,
    expected_sentence_candidate_similarity,
)


DEFAULT_RECORDS_PER_SHARD = 100
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "sbd_predicted_cases"
SOURCE_SELECTION = "source-chunks-only-repeated-token-sentence"
RECORD_SCHEMA = ["language", "chunks", "expected_final"]


def _read_records(case_inputs: Iterable[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in iter_case_paths(case_inputs):
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                language = str(payload.get("language", "")).strip().lower()
                chunks = chunk_input_texts(payload)
                if language not in SBD_CHALLENGE_LANGUAGES or not chunks:
                    continue
                records.append({"language": language, "chunks": chunks})
    return records


def _dedupe_expected(sentences: Iterable[str]) -> list[str]:
    expected: list[str] = []
    for sentence in sentences:
        text = str(sentence).strip()
        if not text:
            continue
        if any(expected_sentence_candidate_similarity(text, previous) >= 0.92 for previous in expected):
            continue
        expected.append(text)
    return expected


def predict_expected_final(record: dict[str, object], *, min_observations: int = DEFAULT_REPEAT_OBSERVATIONS) -> list[str]:
    stable_candidates = case_stable_sentence_candidates(
        {
            "language": record.get("language", ""),
            "chunks": record.get("chunks", []),
            "sentence_finalize_age": min_observations,
        }
    )
    return _dedupe_expected(str(candidate.get("text", "")).strip() for candidate in stable_candidates)


def _clear_output_dir(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _write_cases(
    records: list[dict[str, object]],
    *,
    output_dir: Path,
    records_per_shard: int,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    language_counts: Counter[str] = Counter()
    written_paths: list[str] = []
    handles: dict[tuple[str, int], object] = {}
    try:
        for record in records:
            language = str(record["language"])
            index = language_counts[language]
            shard = index // records_per_shard
            language_counts[language] += 1
            path = output_dir / language / f"predicted-{language}-{shard:03d}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            key = (language, shard)
            if key not in handles:
                handles[key] = path.open("a", encoding="utf-8")
                written_paths.append(str(path))
            handles[key].write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        for handle in handles.values():
            handle.close()
    return {
        "written_case_count": len(records),
        "written_language_counts": dict(sorted(language_counts.items())),
        "written_file_count": len(written_paths),
        "written_files": sorted(written_paths),
    }


def build_cases(
    case_inputs: list[Path],
    *,
    output_dir: Path,
    min_observations: int = DEFAULT_REPEAT_OBSERVATIONS,
    records_per_shard: int = DEFAULT_RECORDS_PER_SHARD,
    replace: bool = False,
) -> dict[str, object]:
    if records_per_shard <= 0:
        raise ValueError("records_per_shard must be positive")
    if replace:
        _clear_output_dir(output_dir)
    raw_records = _read_records(case_inputs)
    skipped_by_language: Counter[str] = Counter()
    cases_by_language: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in raw_records:
        language = str(record["language"])
        expected_final = predict_expected_final(record, min_observations=min_observations)
        if not expected_final:
            skipped_by_language[language] += 1
            continue
        cases_by_language[language].append(
            {
                "language": language,
                "chunks": list(record["chunks"]),
                "expected_final": expected_final,
            }
        )
    built_records: list[dict[str, object]] = []
    for language in SBD_CHALLENGE_LANGUAGES:
        built_records.extend(cases_by_language.get(language, []))
    write_summary = _write_cases(built_records, output_dir=output_dir, records_per_shard=records_per_shard)
    return {
        "input_record_count": len(raw_records),
        "skipped_without_repeated_expected_final_count": sum(skipped_by_language.values()),
        "skipped_without_repeated_expected_final_by_language": dict(sorted(skipped_by_language.items())),
        "source_selection": SOURCE_SELECTION,
        "record_schema": RECORD_SCHEMA,
        "sbd_benchmark_output_used": False,
        "min_observations": min_observations,
        "output_dir": str(output_dir),
        **write_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build SBD benchmark cases from source chunks by predicting expected_final "
            "from repeated token-sentence candidates."
        )
    )
    parser.add_argument("cases", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-observations", type=int, default=DEFAULT_REPEAT_OBSERVATIONS)
    parser.add_argument("--records-per-shard", type=int, default=DEFAULT_RECORDS_PER_SHARD)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    summary = build_cases(
        args.cases,
        output_dir=args.output_dir,
        min_observations=args.min_observations,
        records_per_shard=args.records_per_shard,
        replace=args.replace,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

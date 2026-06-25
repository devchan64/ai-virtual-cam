from __future__ import annotations

import argparse
import json
from pathlib import Path
from tests.eval.dictation_ai.cases.sbd_case_paths import iter_case_paths


def _read_backup_records(case_inputs: list[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in iter_case_paths(case_inputs):
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                chunks = [str(item).strip() for item in payload.get("chunks", []) if str(item).strip()]
                if not chunks:
                    continue
                records.append(
                    {
                        "language": str(payload.get("language", "")).strip().lower(),
                        "chunks": chunks,
                        "expected_final": [],
                    }
                )
    return records


def _packet_from_record(record: dict[str, object]) -> dict[str, object]:
    return {
        "language": record["language"],
        "chunks": list(record["chunks"]),
        "expected_final": [],
    }


def export_packets(case_inputs: list[Path], *, output: Path) -> dict[str, object]:
    records = _read_backup_records(case_inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_packet_from_record(record), ensure_ascii=False) + "\n")
    return {
        "candidate_count": len(records),
        "output": str(output),
        "inputs": [str(item) for item in case_inputs],
        "selection_source": "chunks-only-gpt-sentence-analysis",
        "record_schema": ["language", "chunks", "expected_final"],
        "sbd_benchmark_output_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export chunks-only GPT review candidate records from legacy SBD case backups."
    )
    parser.add_argument("cases", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary = export_packets(args.cases, output=args.output)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

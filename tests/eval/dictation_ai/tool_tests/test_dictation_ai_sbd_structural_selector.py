import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.select_sbd_structural_cases import (
    render_markdown,
    select_structural_cases,
    write_case_jsonl,
)
from tests.eval.dictation_ai.sbd_case_loader import load_cases


def _case(case_id: str, *, queue_len: int, boundary_f1: float, queue_revision: int, replace_deferred: int) -> dict:
    return {
        "id": case_id,
        "language": "en",
        "tags": ["stage-queue", "missing-final"],
        "chunks": [
            {"index": 1, "input": "First sentence. Second sentence."},
            {"index": 2, "input": "Second sentence. Third sentence."},
        ],
        "expected_final": ["First sentence.", "Second sentence.", "Third sentence."],
        "expected_pending": "",
        "expected_staged": "",
        "actual_final": ["First sentence."],
        "actual_pending": "",
        "actual_staged": "Second sentence.",
        "actual_staged_queue": [f"Queued {index}." for index in range(queue_len)],
        "final_score": {"f1": 0.25},
        "final_boundary_score": {"f1": boundary_f1},
        "metrics": {
            "stage_queue_revision": queue_revision,
            "stage_replace_deferred": replace_deferred,
            "stage_candidate_quality_blocked": 3,
            "candidate_duplicate_suppressed": 4,
        },
    }


class DictationAiSbdStructuralSelectorTest(unittest.TestCase):
    def test_selects_high_queue_and_revision_cases(self) -> None:
        report = {
            "cases": [
                _case("low-queue", queue_len=0, boundary_f1=0.5, queue_revision=1, replace_deferred=1),
                _case("high-queue", queue_len=6, boundary_f1=0.0, queue_revision=20, replace_deferred=15),
                _case("high-revision", queue_len=1, boundary_f1=0.0, queue_revision=40, replace_deferred=30),
            ]
        }

        selected = select_structural_cases(report, limit=2)
        markdown = render_markdown(selected, source_report="report.json")

        self.assertEqual([case["id"] for case in selected], ["high-queue", "high-revision"])
        self.assertIn("lifecycle-focus-top", selected[0]["selection_reasons"])
        self.assertIn("- corpus_role: exploratory", markdown)
        self.assertIn("- paper_evidence: false", markdown)
        self.assertIn("structural lifecycle preflight only", markdown)
        self.assertIn("| 1 | high-queue | en |", markdown)

    def test_writes_benchmark_compatible_case_jsonl(self) -> None:
        selected = [_case("high-queue", queue_len=6, boundary_f1=0.0, queue_revision=20, replace_deferred=15)]

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "structural-cases.jsonl"
            write_case_jsonl(selected, output)
            cases, sources = load_cases([output])

            payload = json.loads(output.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(sources, [str(output)])
        self.assertEqual([case.id for case in cases], ["high-queue"])
        self.assertEqual(cases[0].chunks, ["First sentence. Second sentence.", "Second sentence. Third sentence."])
        self.assertEqual(cases[0].expected_final, ["First sentence.", "Second sentence.", "Third sentence."])
        self.assertIn("structural-lifecycle", payload["tags"])


if __name__ == "__main__":
    unittest.main()

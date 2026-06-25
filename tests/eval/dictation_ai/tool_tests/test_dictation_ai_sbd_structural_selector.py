import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.structural.select_sbd_structural_cases import (
    render_markdown,
    select_structural_cases,
    write_case_jsonl,
)
from tests.eval.dictation_ai.cases.sbd_case_loader import load_cases


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
        "actual_final": ["First sentence.", "Second sentence.", "Third sentence."],
        "actual_pending": "",
        "actual_staged": "Unrelated staged residue.",
        "actual_staged_queue": [f"Queued {index}." for index in range(queue_len)],
        "final_score": {"f1": 0.25},
        "final_boundary_score": {"f1": boundary_f1},
        "metrics": {
            "stage_queue_revision": queue_revision,
            "stage_replace_deferred": replace_deferred,
            "stage_candidate_quality_blocked": 3,
            "candidate_duplicate_suppressed": 4,
        },
        "case_metadata": {
            "source_log": ".tmp/logs/avc-whisper.log",
            "source_chunk": 1,
            "review_group_id": "group-a",
            "review_source_file": "tests/eval/dictation_ai/sbd_predicted_cases/en/predicted-en-000.jsonl",
        },
        "case_definition_flags": [],
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
        self.assertEqual(selected[0]["structural_issue_kind"], "revision_text_mismatch")
        self.assertEqual(selected[0]["expected_quality_flags"], [])
        self.assertEqual(selected[0]["input_evidence"]["covered_count"], 3)
        self.assertIn("- expected_quality_mode: exclude", markdown)
        self.assertIn("- input_evidence_mode: require", markdown)
        self.assertIn("- case_definition_mode: clean", markdown)
        self.assertIn("- source_trace_mode: require", markdown)
        self.assertIn('- issue_kind_counts: {"revision_text_mismatch": 2}', markdown)
        self.assertIn("- corpus_role: exploratory", markdown)
        self.assertIn("- paper_evidence: false", markdown)
        self.assertIn("structural lifecycle preflight only", markdown)
        self.assertIn("| 1 | high-queue | en | revision_text_mismatch |", markdown)

    def test_classifies_structural_issue_kinds(self) -> None:
        underfinal = _case("underfinal", queue_len=1, boundary_f1=0.8, queue_revision=1, replace_deferred=1)
        underfinal["actual_final"] = ["First sentence.", "Second sentence."]
        underfinal["final_score"] = {"f1": 0.8}
        overfinal = _case("overfinal", queue_len=1, boundary_f1=0.8, queue_revision=1, replace_deferred=1)
        overfinal["actual_final"] = ["First sentence.", "Second sentence.", "Third sentence.", "Fourth sentence."]
        overfinal["final_score"] = {"f1": 0.8}
        boundary = _case("boundary", queue_len=1, boundary_f1=0.0, queue_revision=1, replace_deferred=1)
        boundary["final_score"] = {"f1": 1.0}
        report = {"cases": [underfinal, overfinal, boundary]}

        selected = select_structural_cases(report, limit=3)
        issue_kinds = {case["id"]: case["structural_issue_kind"] for case in selected}

        self.assertEqual(issue_kinds["underfinal"], "underfinal_missing")
        self.assertEqual(issue_kinds["overfinal"], "overfinal_or_extra_final")
        self.assertEqual(issue_kinds["boundary"], "boundary_granularity_only")

    def test_filters_by_structural_issue_kind(self) -> None:
        underfinal = _case("underfinal", queue_len=8, boundary_f1=0.8, queue_revision=80, replace_deferred=80)
        underfinal["actual_final"] = ["First sentence.", "Second sentence."]
        underfinal["final_score"] = {"f1": 0.8}
        overfinal = _case("overfinal", queue_len=7, boundary_f1=0.8, queue_revision=70, replace_deferred=70)
        overfinal["actual_final"] = ["First sentence.", "Second sentence.", "Third sentence.", "Fourth sentence."]
        overfinal["final_score"] = {"f1": 0.8}
        boundary = _case("boundary", queue_len=6, boundary_f1=0.0, queue_revision=60, replace_deferred=60)
        boundary["final_score"] = {"f1": 1.0}
        report = {"cases": [underfinal, overfinal, boundary]}

        selected = select_structural_cases(report, limit=3, issue_kind="underfinal_missing")
        markdown = render_markdown(
            selected,
            source_report="report.json",
            issue_kind="underfinal_missing",
        )

        self.assertEqual([case["id"] for case in selected], ["underfinal"])
        self.assertEqual(selected[0]["structural_issue_kind"], "underfinal_missing")
        self.assertIn("- issue_kind_filter: underfinal_missing", markdown)
        self.assertIn('- issue_kind_counts: {"underfinal_missing": 1}', markdown)

    def test_excludes_expected_quality_review_candidates_by_default(self) -> None:
        quality_case = _case("quality-review", queue_len=8, boundary_f1=0.0, queue_revision=80, replace_deferred=80)
        quality_case["expected_final"] = ["and then unfinished"]
        clean_case = _case("clean-structural", queue_len=1, boundary_f1=0.0, queue_revision=1, replace_deferred=1)
        report = {"cases": [quality_case, clean_case]}

        selected = select_structural_cases(report, limit=2)
        included = select_structural_cases(
            report,
            limit=2,
            expected_quality_mode="include",
            input_evidence_mode="include",
            case_definition_mode="include",
        )
        quality_only = select_structural_cases(
            report,
            limit=2,
            expected_quality_mode="only",
            input_evidence_mode="include",
            case_definition_mode="include",
        )

        self.assertEqual([case["id"] for case in selected], ["clean-structural"])
        self.assertEqual([case["id"] for case in included], ["quality-review", "clean-structural"])
        self.assertEqual([case["id"] for case in quality_only], ["quality-review"])
        self.assertIn("no_terminal_expected", quality_only[0]["expected_quality_flags"])

    def test_requires_input_evidence_by_default(self) -> None:
        weak_case = _case("weak-input", queue_len=8, boundary_f1=0.0, queue_revision=80, replace_deferred=80)
        weak_case["expected_final"] = ["A sentence that never appears in any replay input."]
        partial_case = _case("partial-input", queue_len=7, boundary_f1=0.0, queue_revision=70, replace_deferred=70)
        partial_case["expected_final"] = ["First sentence.", "A sentence that never appears in any replay input."]
        unobserved_case = _case("unobserved-input", queue_len=6, boundary_f1=0.0, queue_revision=60, replace_deferred=60)
        unobserved_case["chunks"] = [{"index": 1, "input": "Tesla fraudster person waited with support."}]
        unobserved_case["expected_final"] = ["Tesla fraudulent person waited with support."]
        clean_case = _case("clean-input", queue_len=1, boundary_f1=0.0, queue_revision=1, replace_deferred=1)
        report = {"cases": [weak_case, partial_case, unobserved_case, clean_case]}

        selected = select_structural_cases(report, limit=2)
        included = select_structural_cases(
            report,
            limit=4,
            input_evidence_mode="include",
            case_definition_mode="include",
        )
        weak_only = select_structural_cases(
            report,
            limit=2,
            input_evidence_mode="weak-only",
            case_definition_mode="include",
        )

        self.assertEqual([case["id"] for case in selected], ["clean-input"])
        self.assertEqual(
            [case["id"] for case in included],
            ["weak-input", "partial-input", "unobserved-input", "clean-input"],
        )
        self.assertEqual([case["id"] for case in weak_only], ["weak-input"])
        self.assertTrue(included[1]["input_evidence"]["has_evidence"])
        self.assertFalse(included[1]["input_evidence"]["fully_supported"])
        self.assertTrue(included[2]["input_evidence"]["fully_supported"])
        self.assertFalse(included[2]["input_evidence"]["observed_fully_supported"])
        self.assertFalse(weak_only[0]["input_evidence"]["has_evidence"])

    def test_excludes_case_definition_review_candidates_by_default(self) -> None:
        review_case = _case("definition-review", queue_len=8, boundary_f1=0.0, queue_revision=80, replace_deferred=80)
        review_case["case_definition_flags"] = ["repeated_expected_group"]
        clean_case = _case("clean-structural", queue_len=1, boundary_f1=0.0, queue_revision=1, replace_deferred=1)
        report = {"cases": [review_case, clean_case]}

        selected = select_structural_cases(report, limit=2)
        included = select_structural_cases(report, limit=2, case_definition_mode="include")
        review_only = select_structural_cases(report, limit=2, case_definition_mode="review-only")

        self.assertEqual([case["id"] for case in selected], ["clean-structural"])
        self.assertEqual([case["id"] for case in included], ["definition-review", "clean-structural"])
        self.assertEqual([case["id"] for case in review_only], ["definition-review"])

    def test_requires_source_trace_by_default(self) -> None:
        missing_trace = _case("missing-trace", queue_len=8, boundary_f1=0.0, queue_revision=80, replace_deferred=80)
        missing_trace["case_metadata"] = {}
        clean_case = _case("clean-trace", queue_len=1, boundary_f1=0.0, queue_revision=1, replace_deferred=1)
        report = {"cases": [missing_trace, clean_case]}

        selected = select_structural_cases(report, limit=2)
        included = select_structural_cases(report, limit=2, source_trace_mode="include")
        missing_only = select_structural_cases(report, limit=2, source_trace_mode="missing-only")

        self.assertEqual([case["id"] for case in selected], ["clean-trace"])
        self.assertEqual([case["id"] for case in included], ["missing-trace", "clean-trace"])
        self.assertEqual([case["id"] for case in missing_only], ["missing-trace"])

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
        self.assertEqual(cases[0].metadata["source_log"], ".tmp/logs/avc-whisper.log")
        self.assertEqual(cases[0].metadata["source_chunk"], 1)
        self.assertIn("structural-lifecycle", payload["tags"])
        self.assertEqual(payload["source_log"], ".tmp/logs/avc-whisper.log")
        self.assertEqual(payload["source_chunk"], 1)


if __name__ == "__main__":
    unittest.main()

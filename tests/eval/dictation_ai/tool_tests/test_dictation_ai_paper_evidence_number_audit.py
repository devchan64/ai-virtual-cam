import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.audit_paper_evidence_numbers import (
    audit_paper_evidence_numbers,
)


class DictationAiPaperEvidenceNumberAuditTest(unittest.TestCase):
    def _write_summary(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "report_count": 23,
                    "unique_axis_count": 12,
                    "baseline_metric_summary": {
                        "final_precision_avg": {
                            "consistent": True,
                            "value": 0.6019205720812749,
                            "unique_values": [0.601920572081],
                        },
                        "final_recall_avg": {
                            "consistent": True,
                            "value": 0.43994445181910236,
                            "unique_values": [0.439944451819],
                        },
                        "final_f1_avg": {
                            "consistent": True,
                            "value": 0.48324216347151316,
                            "unique_values": [0.483242163472],
                        },
                        "final_boundary_f1_avg": {
                            "consistent": True,
                            "value": 0.10774902104020108,
                            "unique_values": [0.10774902104],
                        },
                        "finalized_per_stage_start": {
                            "consistent": True,
                            "value": 0.7115998581057112,
                            "unique_values": [0.711599858106],
                        },
                    },
                    "case_set_summary": {
                        "case_count": {
                            "consistent": True,
                            "report_count": 23,
                            "value": 1113,
                            "unique_values": [1113],
                        },
                        "expected_final_case_count": {
                            "consistent": True,
                            "report_count": 23,
                            "value": 1109,
                            "unique_values": [1109],
                        },
                        "draft_count": {
                            "consistent": True,
                            "report_count": 23,
                            "value": 4,
                            "unique_values": [4],
                        },
                        "language_counts": {
                            "en": {
                                "consistent": True,
                                "report_count": 23,
                                "value": 429,
                                "unique_values": [429],
                            },
                            "ko": {
                                "consistent": True,
                                "report_count": 23,
                                "value": 462,
                                "unique_values": [462],
                            },
                            "zh": {
                                "consistent": True,
                                "report_count": 23,
                                "value": 222,
                                "unique_values": [222],
                            },
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_audit_passes_when_paper_contains_rounded_baseline_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            paper.write_text(
                "final_precision_avg=0.602 final_recall_avg=0.440 "
                "final_f1_avg=0.483 final_boundary_f1_avg=0.108 "
                "finalized_per_stage_start=0.712 "
                "complete report 23 unique axis 12 "
                "case_count 1113 expected_final_case_count 1109 "
                "en 429 ko 462 zh 222",
                encoding="utf-8",
            )

            result = audit_paper_evidence_numbers(summary, paper)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_metrics"], [])
        self.assertEqual(result["missing_counts"], [])
        self.assertEqual(result["inconsistent_metrics"], [])
        self.assertEqual(result["inconsistent_counts"], [])

    def test_audit_reports_missing_or_stale_paper_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            paper.write_text(
                "final_precision_avg=0.602 final_recall_avg=0.440 "
                "final_f1_avg=0.481 final_boundary_f1_avg=0.108 "
                "finalized_per_stage_start=0.712 "
                "complete report 23 unique axis 12 "
                "case_count 1113 expected_final_case_count 1109 "
                "en 429 ko 462 zh 222",
                encoding="utf-8",
            )

            result = audit_paper_evidence_numbers(summary, paper)

        self.assertFalse(result["ok"])
        self.assertEqual(
            {item["metric"] for item in result["missing_metrics"]},
            {"final_f1_avg"},
        )

    def test_audit_reports_inconsistent_summary_baseline_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            payload["baseline_metric_summary"]["final_f1_avg"] = {
                "consistent": False,
                "value": None,
                "unique_values": [0.483, 0.481],
            }
            summary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            paper.write_text(
                "final_precision_avg=0.602 final_recall_avg=0.440 "
                "final_f1_avg=0.483 final_boundary_f1_avg=0.108 "
                "finalized_per_stage_start=0.712 "
                "complete report 23 unique axis 12 "
                "case_count 1113 expected_final_case_count 1109 "
                "en 429 ko 462 zh 222",
                encoding="utf-8",
            )

            result = audit_paper_evidence_numbers(summary, paper)

        self.assertFalse(result["ok"])
        self.assertEqual(
            {item["metric"] for item in result["inconsistent_metrics"]},
            {"final_f1_avg"},
        )

    def test_audit_reports_missing_or_stale_case_count_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            paper.write_text(
                "final_precision_avg=0.602 final_recall_avg=0.440 "
                "final_f1_avg=0.483 final_boundary_f1_avg=0.108 "
                "finalized_per_stage_start=0.712 "
                "complete report 23 unique axis 12 "
                "case_count 1112 expected_final_case_count 1109 "
                "en 429 ko 462 zh 222",
                encoding="utf-8",
            )

            result = audit_paper_evidence_numbers(summary, paper)

        self.assertFalse(result["ok"])
        self.assertEqual(
            {(item["kind"], item["name"]) for item in result["missing_counts"]},
            {("case_set", "case_count")},
        )


if __name__ == "__main__":
    unittest.main()

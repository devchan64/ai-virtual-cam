import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.paper.audit_length_strata_hypothesis import audit_length_strata_hypothesis


class DictationAiLengthStrataHypothesisTest(unittest.TestCase):
    def test_audit_accepts_report_when_short_and_long_strata_match_hypothesis(self) -> None:
        payload = {
            "length_strata_summary": {
                "all_cases": {"case_count": 815, "final_f1_avg": 0.666},
                "short_sentences": {
                    "case_count": 59,
                    "missing_final_rate": 0.0,
                    "duplicate_suppression_rate": 0.932,
                    "queue_bypass_rate": 0.831,
                    "merge_error_rate": 0.0,
                },
                "long_sentences": {
                    "case_count": 705,
                    "missing_final_rate": 0.153,
                    "merge_error_rate": 0.289,
                    "queue_bypass_rate": 0.735,
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_length_strata_hypothesis(report_path)

        self.assertTrue(result["hypothesis_supported"])
        self.assertTrue(all(check["passed"] for check in result["checks"]))

    def test_audit_rejects_report_when_short_sentence_consumption_is_not_good(self) -> None:
        payload = {
            "length_strata_summary": {
                "all_cases": {"case_count": 10, "final_f1_avg": 0.4},
                "short_sentences": {
                    "case_count": 3,
                    "missing_final_rate": 0.2,
                    "duplicate_suppression_rate": 0.7,
                    "queue_bypass_rate": 0.4,
                    "merge_error_rate": 0.1,
                },
                "long_sentences": {
                    "case_count": 7,
                    "missing_final_rate": 0.1,
                    "merge_error_rate": 0.1,
                    "queue_bypass_rate": 0.5,
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_length_strata_hypothesis(report_path)

        self.assertFalse(result["hypothesis_supported"])
        self.assertTrue(any(not check["passed"] for check in result["checks"]))


if __name__ == "__main__":
    unittest.main()

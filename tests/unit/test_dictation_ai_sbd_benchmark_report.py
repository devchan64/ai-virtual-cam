import unittest

from tests.eval.dictation_ai.sbd_benchmark import _summarize_results_by_language, _summarize_results_by_tag


def _score(precision: float, recall: float, f1: float, *, exact: bool = False) -> dict[str, object]:
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_coverage": f1,
        "exact": exact,
    }


class DictationAiSbdBenchmarkReportTest(unittest.TestCase):
    def test_summarizes_residual_metrics_by_language(self) -> None:
        results = [
            {
                "language": "ko",
                "tags": ["ko", "missing-final"],
                "expected_final": ["문장입니다."],
                "actual_final": ["문장입니다."],
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(0.5, 0.5, 0.5),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 2, "stage_start": 2},
            },
            {
                "language": "ko",
                "tags": ["ko", "missing-final", "stage-queue"],
                "expected_final": ["누락된 문장입니다."],
                "actual_final": [],
                "actual_staged": "누락된 문장입니다.",
                "actual_staged_queue": ["다음 문장입니다."],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_queue_enqueue": 1},
            },
            {
                "language": "en",
                "tags": ["en", "duplicate-final"],
                "expected_final": [],
                "actual_final": [],
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {},
            },
        ]

        summary = _summarize_results_by_language(results)

        self.assertEqual(set(summary), {"en", "ko"})
        self.assertEqual(summary["ko"]["case_count"], 2)
        self.assertEqual(summary["ko"]["case_exact_match"], 1)
        self.assertEqual(summary["ko"]["pending_exact_match"], 1)
        self.assertEqual(summary["ko"]["staged_exact_match"], 1)
        self.assertEqual(summary["ko"]["finalized"], 2)
        self.assertEqual(summary["ko"]["stage_start"], 3)
        self.assertAlmostEqual(summary["ko"]["finalized_per_stage_start"], 2 / 3)
        self.assertAlmostEqual(summary["ko"]["final_f1_avg"], 0.5)
        self.assertEqual(summary["ko"]["staged_residue_count"], 1)
        self.assertEqual(summary["ko"]["empty_final_count"], 1)
        self.assertEqual(summary["ko"]["expected_boundary_zero_count"], 1)
        self.assertEqual(summary["ko"]["metrics"]["stage_queue_enqueue"], 1)
        self.assertEqual(summary["en"]["empty_final_count"], 0)
        self.assertEqual(summary["en"]["expected_boundary_zero_count"], 0)

    def test_summarizes_residual_metrics_by_case_tag(self) -> None:
        results = [
            {
                "language": "ko",
                "tags": ["ko", "log-20260621", "stock-market", "missing-final"],
                "expected_final": ["누락된 문장입니다."],
                "actual_final": [],
                "actual_staged": "누락된 문장입니다.",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1},
            },
            {
                "language": "ko",
                "tags": ["ko", "war", "missing-final", "duplicate-final"],
                "expected_final": ["회수된 문장입니다."],
                "actual_final": ["회수된 문장입니다."],
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
        ]

        summary = _summarize_results_by_tag(results)

        self.assertEqual(set(summary), {"duplicate-final", "missing-final"})
        self.assertEqual(summary["missing-final"]["case_count"], 2)
        self.assertEqual(summary["missing-final"]["case_exact_match"], 1)
        self.assertAlmostEqual(summary["missing-final"]["final_f1_avg"], 0.5)
        self.assertEqual(summary["missing-final"]["empty_final_count"], 1)
        self.assertEqual(summary["missing-final"]["expected_boundary_zero_count"], 1)
        self.assertEqual(summary["duplicate-final"]["case_count"], 1)
        self.assertAlmostEqual(summary["duplicate-final"]["final_f1_avg"], 1.0)


if __name__ == "__main__":
    unittest.main()

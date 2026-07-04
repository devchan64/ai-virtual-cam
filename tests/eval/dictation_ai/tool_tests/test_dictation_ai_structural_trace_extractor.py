import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.structural.extract_sbd_case_lifecycle_trace import extract_case_lifecycle_traces, main


class DictationAiStructuralTraceExtractorTest(unittest.TestCase):
    def test_extracts_selected_case_with_metrics_and_events(self) -> None:
        report = {
            "cases": [
                {
                    "id": "ko-1",
                    "language": "ko",
                    "tags": ["queue"],
                    "case_metadata": {"source_log": "a.log", "source_chunk": 12},
                    "expected_final": ["첫 문장", "둘째 문장"],
                    "actual_final": ["첫 문장"],
                    "actual_pending": "둘째",
                    "actual_staged": "둘째 문장",
                    "actual_staged_queue": ["셋째 문장"],
                    "final_score": {"f1": 0.4},
                    "final_ordered_score": {"f1": 0.4},
                    "final_boundary_score": {"f1": 0.0},
                    "boundary_granularity_adjusted_score": {"f1": 0.8},
                    "metrics": {
                        "stage_replace_deferred": 3,
                        "stage_queue_revision": 2,
                        "stage_age_quality_blocked": 1,
                        "custom_metric": 5,
                    },
                    "chunks": [
                        {
                            "index": 0,
                            "input": "첫 청크",
                            "completed": ["첫 문장"],
                            "pending": "",
                            "staged": "",
                            "staged_confirmations": 0,
                            "staged_age": 0,
                            "finalized": ["첫 문장"],
                            "finalized_events": [
                                {"reason": "aged", "suppressed": False, "output_sentence": "첫 문장"}
                            ],
                            "boundary_count": 1,
                            "end_mark_count": 1,
                            "right_context_start_count": 0,
                        }
                    ],
                },
                {
                    "id": "en-2",
                    "language": "en",
                    "expected_final": ["other"],
                    "actual_final": ["other"],
                    "metrics": {},
                    "chunks": [],
                },
            ]
        }

        payload = extract_case_lifecycle_traces(
            report,
            case_ids=["ko-1"],
            extra_metric_keys=["custom_metric"],
        )

        self.assertEqual(payload["selected_case_count"], 1)
        self.assertEqual(payload["case_ids"], ["ko-1"])
        case = payload["cases"][0]
        self.assertEqual(case["metrics"]["stage_replace_deferred"], 3)
        self.assertEqual(case["metrics"]["stage_queue_revision"], 2)
        self.assertEqual(case["metrics"]["custom_metric"], 5)
        self.assertEqual(case["finalized_events"][0]["chunk_index"], 0)
        self.assertEqual(case["chunks"][0]["input"], "첫 청크")

    def test_main_writes_json_without_chunks_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            output_path = Path(tmpdir) / "trace.json"
            report_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "zh-1",
                                "language": "zh",
                                "expected_final": ["a"],
                                "actual_final": ["a"],
                                "metrics": {},
                                "chunks": [{"index": 0, "input": "x", "finalized_events": []}],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            original_argv = sys.argv[:]
            try:
                sys.argv = [
                    "extract_sbd_case_lifecycle_trace.py",
                    str(report_path),
                    "--case-id",
                    "zh-1",
                    "--no-chunks",
                    "--output",
                    str(output_path),
                ]
                result = main()
            finally:
                sys.argv = original_argv

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["case_ids"], ["zh-1"])
            self.assertNotIn("chunks", payload["cases"][0])


if __name__ == "__main__":
    unittest.main()

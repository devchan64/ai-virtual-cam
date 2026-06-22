import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.cases.audit_sbd_initial_final_context import audit_initial_final_context


class DictationAiSbdInitialFinalContextAuditTest(unittest.TestCase):
    def _write_case(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_reports_mid_stream_candidate_without_initial_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_case(
                path,
                {
                    "id": "case-a",
                    "language": "en",
                    "chunks": ["Already final sentence. Target sentence."],
                    "expected_final": ["Target sentence."],
                    "source_log": ".tmp/logs/avc-whisper.log",
                    "source_chunk": 42,
                    "review_group_id": "group-a",
                    "tags": ["reviewed-log"],
                },
            )

            summary = audit_initial_final_context([path], min_prefix_units=5)

        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["candidate_language_counts"], {"en": 1})
        self.assertEqual(summary["candidates"][0]["id"], "case-a")
        self.assertEqual(summary["candidates"][0]["source_log"], ".tmp/logs/avc-whisper.log")
        self.assertEqual(summary["candidates"][0]["source_chunk"], 42)
        self.assertEqual(summary["candidates"][0]["review_group_id"], "group-a")
        self.assertEqual(summary["candidates"][0]["prefix_preview"], "Already final sentence.")

    def test_ignores_cases_that_already_define_initial_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_case(
                path,
                {
                    "id": "case-a",
                    "language": "en",
                    "chunks": ["Already final sentence. Target sentence."],
                    "initial_final": ["Already final sentence."],
                    "expected_final": ["Target sentence."],
                    "tags": ["reviewed-log"],
                },
            )

            summary = audit_initial_final_context([path], min_prefix_units=5)

        self.assertEqual(summary["candidate_count"], 0)

    def test_summarizes_candidate_and_non_candidate_scores_from_benchmark_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_path = root / "cases.jsonl"
            case_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "case-a",
                                "language": "en",
                                "chunks": [
                                    "Already final sentence. This target sentence is complete enough."
                                ],
                                "expected_final": ["This target sentence is complete enough."],
                                "source_log": ".tmp/logs/avc-whisper.log",
                                "source_chunk": 42,
                                "review_group_id": "group-a",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "id": "case-c",
                                "language": "en",
                                "chunks": ["Already final sentence. and another target"],
                                "expected_final": ["and another target"],
                                "source_log": ".tmp/logs/avc-whisper.log",
                                "source_chunk": 43,
                                "review_group_id": "group-a",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "id": "case-b",
                                "language": "en",
                                "chunks": ["This is a complete reference sentence."],
                                "expected_final": ["This is a complete reference sentence."],
                                "source_log": ".tmp/logs/avc-whisper.log",
                                "source_chunk": 44,
                                "review_group_id": "group-a",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report_path = root / "benchmark.json"
            report_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "case-a",
                                "expected_final": ["This target sentence is complete enough."],
                                "actual_final": ["Wrong sentence."],
                                "final_score": {"precision": 0.25, "recall": 0.5, "f1": 0.333},
                                "final_boundary_score": {"f1": 0.0},
                            },
                            {
                                "id": "case-c",
                                "expected_final": ["and another target"],
                                "actual_final": ["Another wrong sentence."],
                                "final_score": {"precision": 0.75, "recall": 0.5, "f1": 0.6},
                                "final_boundary_score": {"f1": 0.25},
                            },
                            {
                                "id": "case-b",
                                "expected_final": ["This is a complete reference sentence."],
                                "actual_final": ["This is a complete reference sentence."],
                                "final_score": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                                "final_boundary_score": {"f1": 1.0},
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            summary = audit_initial_final_context(
                [case_path],
                min_prefix_units=5,
                benchmark_report=report_path,
                worst_group_limit=3,
            )

        self.assertEqual(summary["score_summary"]["candidate"]["case_count"], 2)
        self.assertAlmostEqual(summary["score_summary"]["candidate"]["final_f1_avg"], 0.4665)
        self.assertEqual(summary["score_summary"]["non_candidate"]["case_count"], 1)
        self.assertEqual(summary["score_summary"]["non_candidate"]["final_f1_avg"], 1.0)
        self.assertEqual(summary["score_summary"]["expected_quality"]["case_count"], 1)
        self.assertEqual(summary["score_summary"]["expected_quality"]["final_f1_avg"], 0.6)
        self.assertEqual(summary["score_summary"]["without_expected_quality"]["case_count"], 2)
        self.assertAlmostEqual(summary["score_summary"]["without_expected_quality"]["final_f1_avg"], 0.6665)
        self.assertEqual(summary["score_summary"]["candidate_expected_quality"]["case_count"], 1)
        self.assertEqual(summary["score_summary"]["candidate_without_expected_quality"]["case_count"], 1)
        self.assertEqual(summary["score_summary"]["worst_candidates"][0]["id"], "case-a")
        self.assertEqual(summary["score_summary"]["worst_candidates"][0]["source_chunk"], 42)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["case_count"], 2)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["total_case_count"], 3)
        self.assertAlmostEqual(summary["score_summary"]["worst_groups"][0]["candidate_case_ratio"], 2 / 3)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["expected_quality_case_count"], 1)
        self.assertAlmostEqual(summary["score_summary"]["worst_groups"][0]["expected_quality_case_ratio"], 1 / 3)
        self.assertEqual(
            summary["score_summary"]["worst_groups"][0]["expected_quality_flags"],
            {
                "all_expected_no_terminal": 1,
                "lowercase_or_connector_start": 1,
                "no_terminal_expected": 1,
                "short_expected_fragment": 1,
            },
        )
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["source_chunk_min"], 42)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["source_chunk_max"], 43)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["group_source_chunk_min"], 42)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["group_source_chunk_max"], 44)
        self.assertEqual(summary["score_summary"]["worst_groups"][0]["review_group_id"], "group-a")

    def test_reports_case_definition_review_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "case-a",
                                "language": "en",
                                "chunks": ["Repeated. Repeated. Longer repeated sentence."],
                                "expected_final": ["Repeated.", "Repeated.", "Longer repeated sentence."],
                                "source_log": ".tmp/logs/avc-whisper.log",
                                "source_chunk": 1,
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "id": "case-b",
                                "language": "en",
                                "chunks": ["Longer repeated sentence."],
                                "expected_final": ["Longer repeated sentence."],
                                "source_log": ".tmp/logs/avc-whisper.log",
                                "source_chunk": 2,
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "id": "case-c",
                                "language": "en",
                                "chunks": ["Longer repeated sentence."],
                                "expected_final": ["Longer repeated sentence."],
                                "source_log": ".tmp/logs/avc-whisper.log",
                                "source_chunk": 3,
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = audit_initial_final_context([path], duplicate_group_limit=5)

        review = summary["case_definition_review"]
        self.assertEqual(review["duplicate_expected_case_count"], 1)
        self.assertEqual(review["duplicate_expected_cases"][0]["id"], "case-a")
        self.assertEqual(review["duplicate_expected_cases"][0]["duplicate_expected_count"], 1)
        self.assertEqual(review["nested_expected_case_count"], 1)
        self.assertEqual(review["nested_expected_cases"][0]["id"], "case-a")
        self.assertEqual(review["repeated_expected_group_count"], 1)
        self.assertEqual(review["repeated_expected_case_count"], 2)
        self.assertEqual(
            [item["id"] for item in review["repeated_expected_groups"][0]["cases"]],
            ["case-b", "case-c"],
        )


if __name__ == "__main__":
    unittest.main()

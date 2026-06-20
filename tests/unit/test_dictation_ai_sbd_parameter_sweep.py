import unittest
import tempfile
import json
from pathlib import Path

from tests.eval.dictation_ai.run_sbd_parameter_sweep import (
    SweepJob,
    _attach_baseline_deltas,
    build_sweep_jobs,
    _load_report_summary,
    parse_sweep_parameter,
    render_markdown_summary,
    validate_sweep_case_set,
)


class DictationAiSbdParameterSweepTest(unittest.TestCase):
    def test_accepts_manifest_parameter_override(self) -> None:
        parameter = parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=3")

        self.assertEqual(parameter.name, "SENTENCE_CONFIRM_CHUNKS")
        self.assertEqual(parameter.value, "3")
        self.assertEqual(parameter.env_name, "AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS")
        self.assertEqual(parameter.label, "sentence_confirm_chunks-3")

    def test_rejects_non_manifest_parameter(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported sweep parameter"):
            parse_sweep_parameter("LANGUAGE_SPECIFIC_REGEX=1")

    def test_rejects_wrong_parameter_value_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires an integer value"):
            parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=loose")

        with self.assertRaisesRegex(ValueError, "between 0.0 and 1.0"):
            parse_sweep_parameter("REVISION_FALLBACK_COVERAGE_MIN=1.7")

    def test_rejects_parameter_outside_manifest_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be <="):
            parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=99")

        with self.assertRaisesRegex(ValueError, "must be >="):
            parse_sweep_parameter("REVISION_FALLBACK_COVERAGE_MIN=0.1")

    def test_builds_cuda_float16_benchmark_jobs_with_same_cases(self) -> None:
        jobs = build_sweep_jobs(
            python="python",
            cases=(Path("cases-a.jsonl"), Path("cases-b.jsonl")),
            output_dir=Path("out"),
            parameters=(parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=3"),),
            include_baseline=True,
        )

        self.assertEqual([job.label for job in jobs], ["baseline", "sentence_confirm_chunks-3"])
        for job in jobs:
            self.assertIn("--cases", job.argv)
            self.assertIn("cases-a.jsonl", job.argv)
            self.assertIn("cases-b.jsonl", job.argv)
            self.assertIn("--device", job.argv)
            self.assertIn("cuda", job.argv)
            self.assertIn("--compute-type", job.argv)
            self.assertIn("float16", job.argv)
        self.assertEqual(jobs[0].env_overrides, {})
        self.assertEqual(jobs[1].env_overrides, {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "3"})

    def test_load_report_summary_includes_language_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            output.write_text(
                json.dumps(
                    {
                        "case_count": 2,
                        "summary": {"final_f1_avg": 0.5},
                        "language_summary": {"ko": {"case_count": 2, "final_f1_avg": 0.5}},
                        "tag_summary": {"missing-final": {"case_count": 2, "final_f1_avg": 0.5}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            job = SweepJob(
                label="baseline",
                output=output,
                argv=("python", "benchmark.py"),
                env_overrides={},
            )

            summary = _load_report_summary(job)

            self.assertEqual(summary["language_summary"], {"ko": {"case_count": 2, "final_f1_avg": 0.5}})
            self.assertEqual(
                summary["tag_summary"],
                {"missing-final": {"case_count": 2, "final_f1_avg": 0.5}},
            )

    def test_attach_baseline_deltas_to_metrics_and_languages(self) -> None:
        results = [
            {
                "label": "baseline",
                "env_overrides": {},
                "metrics": {"final_f1_avg": 0.5, "finalized_per_stage_start": 0.7},
                "language_summary": {
                    "ko": {"case_count": 2, "final_f1_avg": 0.5, "staged_residue_count": 3}
                },
                "tag_summary": {
                    "missing-final": {"case_count": 2, "final_f1_avg": 0.5, "staged_residue_count": 3}
                },
            },
            {
                "label": "sentence_confirm_chunks-1",
                "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                "metrics": {"final_f1_avg": 0.6, "finalized_per_stage_start": 0.8},
                "language_summary": {
                    "ko": {"case_count": 2, "final_f1_avg": 0.4, "staged_residue_count": 1}
                },
                "tag_summary": {
                    "missing-final": {"case_count": 2, "final_f1_avg": 0.6, "staged_residue_count": 2}
                },
            },
        ]

        updated = _attach_baseline_deltas(results)

        self.assertEqual(updated[0]["metric_deltas"], {"final_f1_avg": 0.0, "finalized_per_stage_start": 0.0})
        self.assertEqual(
            updated[0]["language_deltas"]["ko"],
            {"case_count": 0.0, "final_f1_avg": 0.0, "staged_residue_count": 0.0},
        )
        self.assertAlmostEqual(updated[1]["metric_deltas"]["final_f1_avg"], 0.1)
        self.assertAlmostEqual(updated[1]["metric_deltas"]["finalized_per_stage_start"], 0.1)
        self.assertAlmostEqual(updated[1]["language_deltas"]["ko"]["final_f1_avg"], -0.1)
        self.assertEqual(updated[1]["language_deltas"]["ko"]["staged_residue_count"], -2.0)
        self.assertAlmostEqual(updated[1]["tag_deltas"]["missing-final"]["final_f1_avg"], 0.1)
        self.assertEqual(updated[1]["tag_deltas"]["missing-final"]["staged_residue_count"], -1.0)

    def test_render_markdown_summary_includes_metric_and_language_deltas(self) -> None:
        payload = {
            "dry_run": False,
            "jobs": [{"label": "baseline"}, {"label": "sentence_confirm_chunks-1"}],
            "results": [
                {
                    "label": "baseline",
                    "env_overrides": {},
                    "metrics": {"final_f1_avg": 0.5},
                    "metric_deltas": {"final_f1_avg": 0.0},
                    "language_summary": {"ko": {"final_f1_avg": 0.5, "staged_residue_count": 3}},
                    "language_deltas": {"ko": {"final_f1_avg": 0.0, "staged_residue_count": 0.0}},
                    "tag_summary": {"missing-final": {"case_count": 3, "final_f1_avg": 0.5}},
                    "tag_deltas": {"missing-final": {"case_count": 0.0, "final_f1_avg": 0.0}},
                },
                {
                    "label": "sentence_confirm_chunks-1",
                    "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                    "metrics": {"final_f1_avg": 0.6},
                    "metric_deltas": {"final_f1_avg": 0.1},
                    "language_summary": {"ko": {"final_f1_avg": 0.4, "staged_residue_count": 1}},
                    "language_deltas": {"ko": {"final_f1_avg": -0.1, "staged_residue_count": -2.0}},
                    "tag_summary": {"missing-final": {"case_count": 3, "final_f1_avg": 0.7}},
                    "tag_deltas": {"missing-final": {"case_count": 0.0, "final_f1_avg": 0.2}},
                },
            ],
        }

        markdown = render_markdown_summary(payload)

        self.assertIn("## Overall Metrics", markdown)
        self.assertIn("sentence_confirm_chunks-1", markdown)
        self.assertIn("0.6000 (+0.1000)", markdown)
        self.assertIn("0.4000 (-0.1000)", markdown)
        self.assertIn("1 (-2.0000)", markdown)
        self.assertIn("## Tag Metrics", markdown)
        self.assertIn("missing-final", markdown)
        self.assertIn("0.7000 (+0.2000)", markdown)

    def test_paper_evidence_mode_requires_reviewed_finalization_case_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = Path(tmp) / "cases.jsonl"
            cases.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "language": "ko",
                        "chunks": ["안녕하세요."],
                        "expected_final": ["안녕하세요."],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "expected-final case count below target"):
                validate_sweep_case_set((cases,), paper_evidence=True, min_expected_final_cases=None)

    def test_exploratory_sweep_rejects_draft_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = Path(tmp) / "cases.jsonl"
            cases.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "language": "ko",
                        "chunks": ["안녕하세요."],
                        "expected_final": ["안녕하세요."],
                        "draft_expected_final_required": True,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unreviewed draft"):
                validate_sweep_case_set((cases,), paper_evidence=False, min_expected_final_cases=None)


if __name__ == "__main__":
    unittest.main()

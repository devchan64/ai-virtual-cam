import unittest
import tempfile
import json
from pathlib import Path

from tests.eval.dictation_ai.run_sbd_parameter_sweep import (
    build_sweep_jobs,
    parse_sweep_parameter,
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

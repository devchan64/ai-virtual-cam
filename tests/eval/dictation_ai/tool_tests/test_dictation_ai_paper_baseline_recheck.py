import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.dictation_ai.paper import recheck_paper_challenge_baseline


class DictationAiPaperBaselineRecheckTest(unittest.TestCase):
    def test_parse_variant_spec_normalizes_env_names(self) -> None:
        variant = recheck_paper_challenge_baseline.parse_variant_spec(
            "confirm2:SENTENCE_CONFIRM_CHUNKS=2,AVC_DICTATION_SHORT_NO_END_FRAGMENT_UNITS=4"
        )

        self.assertEqual(variant.label, "confirm2")
        self.assertEqual(
            variant.env_overrides,
            {
                "AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "2",
                "AVC_DICTATION_SHORT_NO_END_FRAGMENT_UNITS": "4",
            },
        )

    def test_audit_paper_baseline_uses_rounded_paper_values(self) -> None:
        checks = recheck_paper_challenge_baseline._audit_paper_baseline(
            {
                "case_count": 815,
                "final_precision_avg": 0.6144,
                "final_recall_avg": 0.7856,
                "final_f1_avg": 0.6656,
                "final_boundary_f1_avg": 0.1362,
                "strict_final_f1_avg": 0.8656,
            }
        )

        self.assertTrue(all(item["matched"] for item in checks))

    def test_recheck_runs_baseline_and_comparison_and_writes_delta_summary(self) -> None:
        baseline_report = {
            "case_count": 815,
            "summary": {
                "final_precision_avg": 0.6144,
                "final_recall_avg": 0.7856,
                "final_f1_avg": 0.6656,
                "final_boundary_f1_avg": 0.1362,
            },
            "strict_logic_candidate_summary": {"summary": {"final_f1_avg": 0.8656}},
        }
        variant_report = {
            "case_count": 815,
            "summary": {
                "final_precision_avg": 0.615,
                "final_recall_avg": 0.788,
                "final_f1_avg": 0.668,
                "final_boundary_f1_avg": 0.136,
            },
            "strict_logic_candidate_summary": {"summary": {"final_f1_avg": 0.854}},
        }

        def fake_run(command, check, cwd, env):  # type: ignore[no-untyped-def]
            output_index = command.index("--output") + 1
            output_path = Path(command[output_index])
            payload = baseline_report if output_path.stem == "baseline" else variant_report
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload), encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "summary.json"
            report_dir = Path(tmpdir) / "reports"
            cases = [Path("tests/eval/dictation_ai/sbd_predicted_cases/ko/predicted-ko-000.jsonl")]
            with (
                patch.object(recheck_paper_challenge_baseline.subprocess, "run", side_effect=fake_run) as run_mock,
                patch.object(
                    recheck_paper_challenge_baseline,
                    "_git_revision_metadata",
                    return_value={
                        "worktree_head_full_hash": "abc1234def",
                        "worktree_head_short_hash": "abc1234",
                        "sample_basis_commit": {
                            "full_hash": "db5c712c3ea994bafab37dc4b395a3f061eab440",
                            "short_hash": "db5c712",
                            "committed_at": "2026-06-25",
                            "subject": "test: SBD predicted 케이스 expected final 정리",
                            "path": "tests/eval/dictation_ai/sbd_predicted_cases",
                        },
                    },
                ),
            ):
                payload = recheck_paper_challenge_baseline.recheck_paper_challenge_baseline(
                    cases=cases,
                    output_path=output_path,
                    report_dir=report_dir,
                    model="sat-3l-sm",
                    device="cuda",
                    compute_type="float16",
                    variants=[
                        recheck_paper_challenge_baseline.BenchmarkVariant(
                            label="confirm2",
                            env_overrides={"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "2"},
                        )
                    ],
                )

        self.assertEqual(run_mock.call_count, 2)
        self.assertTrue(payload["all_baseline_checks_matched"])
        self.assertEqual(payload["git_revision_metadata"]["worktree_head_short_hash"], "abc1234")
        self.assertEqual(
            payload["git_revision_metadata"]["sample_basis_commit"]["short_hash"],
            "db5c712",
        )
        self.assertEqual(payload["comparisons"][0]["label"], "confirm2")
        self.assertEqual(
            payload["comparisons"][0]["delta_vs_baseline"]["strict_final_f1_avg"],
            round(0.854 - 0.8656, 6),
        )


if __name__ == "__main__":
    unittest.main()

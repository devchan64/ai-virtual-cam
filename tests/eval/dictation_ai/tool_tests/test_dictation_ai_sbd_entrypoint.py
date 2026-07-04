import sys
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from tests.eval.dictation_ai import sbd_benchmark


class DictationAiSbdEntrypointTest(unittest.TestCase):
    def test_subcommand_inventory_covers_eval_domains(self) -> None:
        self.assertEqual(
            set(sbd_benchmark._SUBCOMMAND_TARGETS),
            {
                "audit-initial-final-context",
                "build-expected-final-cases",
                "extract-case-lifecycle-trace",
                "export-gpt-case-review-packets",
                "extract-representative-drafts",
                "extract-review-packets",
                "followup-readiness",
                "length-strata-hypothesis",
                "paper-baseline-recheck",
                "paper-claim-scope",
                "paper-evidence-numbers",
                "paper-readiness",
                "paper-reference-scope",
                "promote-representative-cases",
                "refresh-sweep",
                "representative-sources",
                "run-sweep",
                "select-representative-sources",
                "select-structural-cases",
                "summarize-evidence",
                "validate-cases",
                "validate-evidence",
                "validate-review-packets",
            },
        )

    def test_commands_prints_subcommand_list(self) -> None:
        original_argv = sys.argv[:]
        try:
            sys.argv = ["sbd_benchmark.py", "commands"]
            output = StringIO()

            with redirect_stdout(output):
                result = sbd_benchmark._dispatch_subcommand()

            self.assertEqual(result, 0)
            self.assertIn("subcommands:", output.getvalue())
            self.assertIn("run-sweep", output.getvalue())
            self.assertIn("paper-readiness", output.getvalue())
            self.assertIn("paper-baseline-recheck", output.getvalue())
        finally:
            sys.argv = original_argv

    def test_unknown_first_argument_falls_back_to_benchmark_parser(self) -> None:
        original_argv = sys.argv[:]
        try:
            sys.argv = ["sbd_benchmark.py", "--cases", "cases.jsonl"]

            self.assertIsNone(sbd_benchmark._dispatch_subcommand())
        finally:
            sys.argv = original_argv

    def test_dispatches_subcommand_and_restores_argv(self) -> None:
        module = types.SimpleNamespace(main=lambda: 7)
        original_argv = sys.argv[:]
        try:
            sys.argv = ["sbd_benchmark.py", "run-sweep", "--dry-run"]

            with patch.object(sbd_benchmark.importlib, "import_module", return_value=module) as import_module:
                result = sbd_benchmark._dispatch_subcommand()

            self.assertEqual(result, 7)
            import_module.assert_called_once_with("tests.eval.dictation_ai.sweeps.run_sbd_parameter_sweep")
            self.assertEqual(sys.argv, ["sbd_benchmark.py", "run-sweep", "--dry-run"])
        finally:
            sys.argv = original_argv

    def test_length_strata_summary_fields_extracts_short_and_long_metrics(self) -> None:
        fields = sbd_benchmark._length_strata_summary_fields(
            {
                "length_strata_summary": {
                    "short_sentences": {
                        "case_count": 59,
                        "missing_final_rate": 0.0,
                        "duplicate_suppression_rate": 0.9322,
                        "queue_bypass_rate": 0.8305,
                    },
                    "long_sentences": {
                        "case_count": 705,
                        "missing_final_rate": 0.1532,
                        "merge_error_rate": 0.2894,
                        "queue_bypass_rate": 0.7348,
                    },
                }
            }
        )

        self.assertEqual(fields["short_case_count"], 59)
        self.assertEqual(fields["short_missing_final_rate"], 0.0)
        self.assertEqual(fields["short_duplicate_suppression_rate"], 0.9322)
        self.assertEqual(fields["short_queue_bypass_rate"], 0.8305)
        self.assertEqual(fields["long_case_count"], 705)
        self.assertEqual(fields["long_missing_final_rate"], 0.1532)
        self.assertEqual(fields["long_merge_error_rate"], 0.2894)
        self.assertEqual(fields["long_queue_bypass_rate"], 0.7348)


if __name__ == "__main__":
    unittest.main()

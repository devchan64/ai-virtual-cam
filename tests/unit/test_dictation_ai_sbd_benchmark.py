import importlib.util
import sys
import unittest
from argparse import Namespace
from pathlib import Path

from src.app.sentence_boundary import split_punctuated_text


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/eval/dictation-ai-sbd-benchmark.py"
SPEC = importlib.util.spec_from_file_location("dictation_ai_sbd_benchmark", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class _PunctuatedDetector:
    backend = "punctuated-test"

    def split(self, pending_text, new_text, language="en", *, boundary_confidence=None):
        del language
        del boundary_confidence
        return split_punctuated_text(" ".join(part for part in [pending_text, new_text] if part).strip(), self.backend)


class DictationAiSbdBenchmarkTest(unittest.TestCase):
    def test_lifecycle_repeated_completed_sentence_reaches_final(self) -> None:
        case = benchmark.SbdCase(
            id="ko-test",
            language="ko",
            chunks=["문장 경계 테스트를 시작합니다."] * 3,
            expected_completed=[],
            expected_pending="",
            expected_final=["문장 경계 테스트를 시작합니다."],
            expected_staged="",
            tags=("unit",),
            sentence_finalize_age=3,
        )

        result = benchmark._run_lifecycle_case(case, _PunctuatedDetector())

        self.assertEqual(result["actual_final"], ["문장 경계 테스트를 시작합니다."])
        self.assertEqual(result["actual_pending"], "")
        self.assertEqual(result["actual_staged"], "")
        self.assertEqual(result["metrics"].get("stage_start"), 1)
        self.assertGreaterEqual(result["metrics"].get("stage_revision", 0), 1)
        self.assertEqual(result["metrics"].get("finalized"), 1)

    def test_lifecycle_keeps_tail_pending_until_boundary_repeats(self) -> None:
        case = benchmark.SbdCase(
            id="en-test",
            language="en",
            chunks=["Completed sentence. Pending tail"],
            expected_completed=["Completed sentence."],
            expected_pending="Pending tail",
            expected_final=[],
            expected_staged="Completed sentence.",
            tags=("unit",),
            sentence_finalize_age=3,
        )

        result = benchmark._run_lifecycle_case(case, _PunctuatedDetector())

        self.assertEqual(result["actual_final"], [])
        self.assertEqual(result["actual_pending"], "Pending tail")
        self.assertEqual(result["actual_staged"], "Completed sentence.")
        self.assertEqual(result["metrics"].get("segment_state_pending"), 1)
        self.assertEqual(result["metrics"].get("stage_start"), 1)

    def test_cli_benchmark_rejects_mock_or_cpu_performance_runs(self) -> None:
        with self.assertRaisesRegex(ValueError, "--backend=sat required"):
            benchmark._validate_real_ai_cuda_args(
                Namespace(backend="mock", device="cuda", compute_type="float16")
            )
        with self.assertRaisesRegex(ValueError, "--device=cuda required"):
            benchmark._validate_real_ai_cuda_args(
                Namespace(backend="sat", device="cpu", compute_type="float16")
            )
        with self.assertRaisesRegex(ValueError, "--compute-type=float16 required"):
            benchmark._validate_real_ai_cuda_args(
                Namespace(backend="sat", device="cuda", compute_type="float32")
            )

        benchmark._validate_real_ai_cuda_args(
            Namespace(backend="sat", device="cuda", compute_type="float16")
        )


if __name__ == "__main__":
    unittest.main()

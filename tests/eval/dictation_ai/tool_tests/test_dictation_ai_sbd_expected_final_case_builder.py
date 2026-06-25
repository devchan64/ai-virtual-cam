import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.cases.build_sbd_expected_final_cases import build_cases
from tests.eval.dictation_ai.cases.validate_sbd_case_files import validate_case_files


class DictationAiSbdExpectedFinalCaseBuilderTest(unittest.TestCase):
    def test_builds_three_field_cases_from_repeated_chunks_without_inheriting_legacy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            legacy = root / "legacy-name.jsonl"
            output_dir = root / "rebuilt"
            legacy.write_text(
                json.dumps(
                    {
                        "id": "legacy-case-id",
                        "language": "ko",
                        "chunks": [
                            "첫 문장입니다.",
                            "첫 문장입니다. 다음 문장입니다.",
                            "첫 문장입니다. 다음 문장입니다.",
                        ],
                        "expected_final": ["잘못된 기존 정답입니다."],
                        "actual_final": ["벤치 결과는 쓰면 안 됩니다."],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            summary = build_cases([legacy], output_dir=output_dir, records_per_shard=10, replace=True)

            self.assertEqual(summary["input_record_count"], 1)
            self.assertEqual(summary["written_case_count"], 1)
            self.assertFalse(summary["sbd_benchmark_output_used"])
            self.assertEqual(summary["record_schema"], ["language", "chunks", "expected_final"])
            files = sorted(output_dir.rglob("*.jsonl"))
            self.assertEqual([path.name for path in files], ["predicted-ko-000.jsonl"])
            payload = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(set(payload), {"language", "chunks", "expected_final"})
            self.assertEqual(payload["language"], "ko")
            self.assertIn("첫 문장입니다.", payload["expected_final"])
            self.assertNotIn("id", payload)
            self.assertNotIn("actual_final", payload)
            self.assertNotEqual(files[0].name, legacy.name)

            validation = validate_case_files([output_dir], require_expected_final=True)
            self.assertEqual(validation["case_count"], 1)
            self.assertEqual(validation["expected_final_case_count"], 1)

    def test_skips_cases_without_repeated_expected_final_prediction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            legacy = root / "legacy.jsonl"
            output_dir = root / "rebuilt"
            legacy.write_text(
                json.dumps(
                    {
                        "language": "en",
                        "chunks": ["Only once.", "Different text.", "Another sentence."],
                        "expected_final": ["Only once."],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            summary = build_cases([legacy], output_dir=output_dir, replace=True)

            self.assertEqual(summary["input_record_count"], 1)
            self.assertEqual(summary["written_case_count"], 0)
            self.assertEqual(summary["skipped_without_repeated_expected_final_count"], 1)
            self.assertEqual(sorted(output_dir.rglob("*.jsonl")), [])


if __name__ == "__main__":
    unittest.main()

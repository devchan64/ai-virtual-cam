import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.cases.export_sbd_gpt_case_review_packets import export_packets


class DictationAiSbdGptCaseReviewExporterTest(unittest.TestCase):
    def test_exports_candidate_records_with_only_language_chunks_and_expected_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_path = root / "legacy.jsonl"
            case_path.write_text(
                json.dumps(
                    {
                        "id": "case-a",
                        "language": "ko",
                        "chunks": ["첫 문장입니다.", "첫 문장입니다. 다음 문장입니다."],
                        "expected_final": ["잘못 작성된 정식 정답입니다."],
                        "actual_final": ["SBD 결과는 쓰면 안 됩니다."],
                        "sentence_finalize_age": 3,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            output = root / "packets.jsonl"

            summary = export_packets([case_path], output=output)

            self.assertEqual(summary["candidate_count"], 1)
            self.assertFalse(summary["sbd_benchmark_output_used"])
            self.assertEqual(summary["record_schema"], ["language", "chunks", "expected_final"])
            packet = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(packet), {"language", "chunks", "expected_final"})
            self.assertEqual(packet["language"], "ko")
            self.assertEqual(packet["chunks"], ["첫 문장입니다.", "첫 문장입니다. 다음 문장입니다."])
            self.assertEqual(packet["expected_final"], [])
            self.assertNotIn("actual_final", packet)
            self.assertNotIn("id", packet)


if __name__ == "__main__":
    unittest.main()

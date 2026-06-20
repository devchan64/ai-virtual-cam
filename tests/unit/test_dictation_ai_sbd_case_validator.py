import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.validate_sbd_case_files import enforce_case_thresholds, validate_case_files


class DictationAiSbdCaseValidatorTest(unittest.TestCase):
    def _write_payload(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_reports_reviewed_case_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([path])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["draft_count"], 0)
        self.assertEqual(summary["expected_final_case_count"], 1)
        self.assertEqual(summary["language_counts"], {"ko": 1})
        self.assertEqual(summary["tag_counts"], {"missing-final": 1})

    def test_loads_reviewed_cases_recursively_from_group_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            group_dir = root / "auto-groups"
            group_dir.mkdir()
            self._write_payload(
                group_dir / "reviewed-group.jsonl",
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([root])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["sources"], [str(group_dir / "reviewed-group.jsonl")])

    def test_rejects_draft_without_allow_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "drafts.jsonl"
            self._write_payload(
                path,
                {
                    "id": "draft-a",
                    "language": "en",
                    "chunks": ["Hello.", "Hello again."],
                    "expected_final": [],
                    "draft_expected_final_required": True,
                    "tags": ["log-draft"],
                },
            )

            with self.assertRaisesRegex(ValueError, "unreviewed draft"):
                validate_case_files([path])

            summary = validate_case_files([path], allow_drafts=True)

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["draft_count"], 1)
        self.assertEqual(summary["expected_final_case_count"], 0)

    def test_can_require_reviewed_case_expected_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "en",
                    "chunks": ["Hello."],
                    "expected_final": [],
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([path])
            with self.assertRaisesRegex(ValueError, "no expected_final"):
                validate_case_files([path], require_expected_final=True)

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["expected_final_case_count"], 0)

    def test_enforces_case_thresholds(self) -> None:
        summary = {"case_count": 2, "draft_count": 1, "expected_final_case_count": 1}

        enforce_case_thresholds(summary, min_cases=2, min_expected_final_cases=1, max_drafts=1)

        with self.assertRaisesRegex(ValueError, "below target"):
            enforce_case_thresholds(summary, min_cases=3)
        with self.assertRaisesRegex(ValueError, "expected-final case count below target"):
            enforce_case_thresholds(summary, min_expected_final_cases=2)
        with self.assertRaisesRegex(ValueError, "above limit"):
            enforce_case_thresholds(summary, max_drafts=0)


if __name__ == "__main__":
    unittest.main()

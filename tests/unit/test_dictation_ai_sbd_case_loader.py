import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.dictation_ai.sbd_benchmark import _default_case_inputs, _load_cases


class DictationAiSbdCaseLoaderTest(unittest.TestCase):
    def _write_case(self, path: Path, case_id: str) -> None:
        payload = {
            "id": case_id,
            "language": "en",
            "chunks": ["Hello world."],
            "expected_final": ["Hello world."],
            "expected_pending": "",
            "expected_staged": "",
            "sentence_finalize_age": 3,
            "tags": ["unit"],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def _write_draft_case(self, path: Path, case_id: str) -> None:
        payload = {
            "id": case_id,
            "language": "en",
            "chunks": ["Hello world.", "Hello world again."],
            "expected_final": [],
            "expected_pending": "",
            "expected_staged": "",
            "sentence_finalize_age": 3,
            "tags": ["log-draft"],
            "draft_expected_final_required": True,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_loads_multiple_case_files_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            self._write_case(directory / "a.jsonl", "case-a")
            self._write_case(directory / "b.jsonl", "case-b")

            cases, sources = _load_cases([directory])

        self.assertEqual([case.id for case in cases], ["case-a", "case-b"])
        self.assertEqual(len(sources), 2)

    def test_loads_case_files_recursively_from_group_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            group_dir = directory / "auto-groups"
            group_dir.mkdir()
            self._write_case(group_dir / "reviewed-group.jsonl", "case-a")

            cases, sources = _load_cases([directory])

        self.assertEqual([case.id for case in cases], ["case-a"])
        self.assertEqual(sources, [str(group_dir / "reviewed-group.jsonl")])

    def test_loads_case_files_from_glob(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            self._write_case(directory / "cases.part-0001.jsonl", "case-a")
            self._write_case(directory / "cases.part-0002.jsonl", "case-b")

            cases, sources = _load_cases([directory / "cases.part-*.jsonl"])

        self.assertEqual([case.id for case in cases], ["case-a", "case-b"])
        self.assertEqual(len(sources), 2)

    def test_default_case_inputs_use_reviewed_case_directory_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reviewed = root / "sbd_cases"
            reviewed.mkdir()
            self._write_case(reviewed / "reviewed.part-0001.jsonl", "reviewed-case")

            with patch(
                "tests.eval.dictation_ai.sbd_benchmark.SBD_REVIEWED_CASE_DIR",
                reviewed,
            ):
                inputs = _default_case_inputs()
                cases, sources = _load_cases(inputs)

        self.assertEqual(inputs, [reviewed])
        self.assertEqual([case.id for case in cases], ["reviewed-case"])
        self.assertEqual(len(sources), 1)

    def test_default_case_inputs_include_reviewed_case_directory_with_only_grouped_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reviewed = root / "sbd_cases"
            group_dir = reviewed / "auto-groups"
            group_dir.mkdir(parents=True)
            self._write_case(group_dir / "reviewed-group.jsonl", "reviewed-case")

            with patch(
                "tests.eval.dictation_ai.sbd_benchmark.SBD_REVIEWED_CASE_DIR",
                reviewed,
            ):
                inputs = _default_case_inputs()
                cases, sources = _load_cases(inputs)

        self.assertEqual(inputs, [reviewed])
        self.assertEqual([case.id for case in cases], ["reviewed-case"])
        self.assertEqual(sources, [str(group_dir / "reviewed-group.jsonl")])

    def test_default_case_inputs_empty_when_reviewed_directory_has_no_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reviewed = Path(tmpdir) / "sbd_cases"
            reviewed.mkdir()

            with patch("tests.eval.dictation_ai.sbd_benchmark.SBD_REVIEWED_CASE_DIR", reviewed):
                inputs = _default_case_inputs()

        self.assertEqual(inputs, [])

    def test_rejects_duplicate_case_ids_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            self._write_case(directory / "a.jsonl", "duplicate-case")
            self._write_case(directory / "b.jsonl", "duplicate-case")

            with self.assertRaises(ValueError):
                _load_cases([directory])

    def test_rejects_unreviewed_draft_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "drafts.jsonl"
            self._write_draft_case(path, "draft-case")

            with self.assertRaisesRegex(ValueError, "draft case"):
                _load_cases([path])

    def test_allows_cases_without_expected_final_for_pending_or_staged_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            payload = {
                "id": "empty-expected-final",
                "language": "en",
                "chunks": ["Hello world."],
                "expected_final": [],
                "expected_pending": "Hello world.",
                "sentence_finalize_age": 3,
                "tags": ["unit"],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

            cases, _sources = _load_cases([path])

        self.assertEqual(cases[0].expected_final, [])
        self.assertEqual(cases[0].expected_pending, "Hello world.")


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.dictation_ai.cases.sbd_case_loader import load_cases
from tests.eval.dictation_ai.cases.sbd_case_paths import case_corpus_role, default_case_inputs


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

            cases, sources = load_cases([directory])

        self.assertEqual([case.id for case in cases], ["case-a", "case-b"])
        self.assertEqual(len(sources), 2)

    def test_loads_case_files_recursively_from_group_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            group_dir = directory / "auto-groups"
            group_dir.mkdir()
            self._write_case(group_dir / "reviewed-group.jsonl", "case-a")

            cases, sources = load_cases([directory])

        self.assertEqual([case.id for case in cases], ["case-a"])
        self.assertEqual(sources, [str(group_dir / "reviewed-group.jsonl")])

    def test_loads_case_files_from_glob(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            self._write_case(directory / "cases.part-0001.jsonl", "case-a")
            self._write_case(directory / "cases.part-0002.jsonl", "case-b")

            cases, sources = load_cases([directory / "cases.part-*.jsonl"])

        self.assertEqual([case.id for case in cases], ["case-a", "case-b"])
        self.assertEqual(len(sources), 2)

    def test_default_case_inputs_use_reviewed_case_directory_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reviewed = root / "sbd_predicted_cases"
            language_dir = reviewed / "en"
            language_dir.mkdir(parents=True)
            self._write_case(language_dir / "predicted-en-000.jsonl", "reviewed-case")

            with patch(
                "tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR",
                reviewed,
            ):
                inputs = default_case_inputs()
                cases, sources = load_cases(inputs)

        self.assertEqual(inputs, [reviewed])
        self.assertEqual([case.id for case in cases], ["reviewed-case"])
        self.assertEqual(len(sources), 1)

    def test_default_case_inputs_ignore_non_language_grouped_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reviewed = root / "sbd_predicted_cases"
            group_dir = reviewed / "auto-groups"
            group_dir.mkdir(parents=True)
            self._write_case(group_dir / "reviewed-group.jsonl", "reviewed-case")

            with patch(
                "tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR",
                reviewed,
            ):
                inputs = default_case_inputs()

        self.assertEqual(inputs, [])

    def test_explicit_challenge_root_ignores_non_language_grouped_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reviewed = root / "sbd_predicted_cases"
            language_dir = reviewed / "en"
            group_dir = reviewed / "auto-groups"
            language_dir.mkdir(parents=True)
            group_dir.mkdir()
            self._write_case(language_dir / "predicted-en-000.jsonl", "reviewed-case")
            self._write_case(group_dir / "reviewed-group.jsonl", "ignored-case")

            with patch(
                "tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR",
                reviewed,
            ):
                cases, sources = load_cases([reviewed])

        self.assertEqual([case.id for case in cases], ["reviewed-case"])
        self.assertEqual(sources, [str(language_dir / "predicted-en-000.jsonl")])

    def test_case_corpus_role_marks_challenge_and_representative_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            challenge = root / "sbd_predicted_cases"
            representative = root / "representative_cases"
            challenge_file = challenge / "en" / "case.jsonl"
            representative_file = representative / "case.jsonl"

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR", challenge), patch(
                "tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR",
                representative,
            ):
                self.assertEqual(case_corpus_role([challenge]), "challenge-replay")
                self.assertEqual(case_corpus_role([challenge_file]), "challenge-replay")
                self.assertEqual(case_corpus_role([representative]), "representative")
                self.assertEqual(case_corpus_role([representative_file]), "representative")
                self.assertEqual(case_corpus_role([challenge, representative]), "exploratory")

    def test_default_case_inputs_empty_when_reviewed_directory_has_no_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reviewed = Path(tmpdir) / "sbd_predicted_cases"
            reviewed.mkdir()

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR", reviewed):
                inputs = default_case_inputs()

        self.assertEqual(inputs, [])

    def test_rejects_duplicate_case_ids_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            self._write_case(directory / "a.jsonl", "duplicate-case")
            self._write_case(directory / "b.jsonl", "duplicate-case")

            with self.assertRaises(ValueError):
                load_cases([directory])

    def test_rejects_unreviewed_draft_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "drafts.jsonl"
            self._write_draft_case(path, "draft-case")

            with self.assertRaisesRegex(ValueError, "draft case"):
                load_cases([path])

    def test_allows_cases_without_expected_final_for_pending_or_staged_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            payload = {
                "id": "empty-expected-final",
                "language": "en",
                "chunks": ["Hello world."],
                "expected_final": [],
                "expected_no_final": True,
                "expected_no_final_reason": "pending-only case",
                "expected_pending": "Hello world.",
                "sentence_finalize_age": 3,
                "tags": ["unit"],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

            cases, _sources = load_cases([path])

        self.assertEqual(cases[0].expected_final, [])
        self.assertEqual(cases[0].expected_pending, "Hello world.")
        self.assertEqual(cases[0].metadata["expected_no_final"], True)
        self.assertEqual(cases[0].metadata["expected_no_final_reason"], "pending-only case")

    def test_rejects_unmarked_cases_without_expected_final(self) -> None:
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

            with self.assertRaisesRegex(ValueError, "not marked expected_no_final"):
                load_cases([path])

    def test_loads_initial_final_context_for_mid_stream_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            payload = {
                "id": "initial-final-context",
                "language": "en",
                "initial_final": ["Already committed."],
                "chunks": ["Already committed. New sentence."],
                "expected_final": ["New sentence."],
                "expected_pending": "",
                "sentence_finalize_age": 3,
                "tags": ["unit"],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

            cases, _sources = load_cases([path])

        self.assertEqual(cases[0].initial_final, ("Already committed.",))
        self.assertEqual(cases[0].expected_final, ["New sentence."])

    def test_representative_benchmark_input_requires_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "representative_cases"
            root.mkdir()
            path = root / "cases.jsonl"
            self._write_case(path, "representative-case")

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata"):
                    load_cases([path])

    def test_representative_benchmark_input_accepts_reviewed_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "representative_cases"
            root.mkdir()
            path = root / "cases.jsonl"
            payload = {
                "id": "representative-case",
                "language": "en",
                "chunks": ["Hello world."],
                "expected_final": ["Hello world."],
                "expected_pending": "",
                "expected_staged": "",
                "corpus_role": "representative",
                "sampling_unit": "time-window",
                "sampling_rule": "fixed-interval-10min",
                "source_log": ".tmp/logs/avc-whisper.log",
                "source_started_at": "chunk:1",
                "source_ended_at": "chunk:3",
                "stt_backend": "faster-whisper",
                "stt_model": "large-v3",
                "window_seconds": 10.0,
                "step_seconds": 1.0,
                "sentence_finalize_age": 3,
                "review_packet_id": "en_representative_review_abc",
                "expected_final_reviewed_by": "human-reviewed",
                "tags": ["representative"],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                cases, sources = load_cases([path])

        self.assertEqual([case.id for case in cases], ["representative-case"])
        self.assertEqual(sources, [str(path)])
        self.assertEqual(
            cases[0].metadata,
            {
                "sampling_unit": "time-window",
                "sampling_rule": "fixed-interval-10min",
                "source_log": ".tmp/logs/avc-whisper.log",
                "review_packet_id": "en_representative_review_abc",
                "expected_final_reviewed_by": "human-reviewed",
            },
        )

    def test_representative_benchmark_input_rejects_unsupported_sampling_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "representative_cases"
            root.mkdir()
            path = root / "cases.jsonl"
            payload = {
                "id": "representative-case",
                "language": "en",
                "chunks": ["Hello world."],
                "expected_final": ["Hello world."],
                "corpus_role": "representative",
                "sampling_unit": "failure-cluster",
                "sampling_rule": "manual-failure-pick",
                "source_log": ".tmp/logs/avc-whisper.log",
                "source_started_at": "chunk:1",
                "source_ended_at": "chunk:3",
                "stt_backend": "faster-whisper",
                "stt_model": "large-v3",
                "window_seconds": 10.0,
                "step_seconds": 1.0,
                "sentence_finalize_age": 3,
                "review_packet_id": "en_representative_review_abc",
                "expected_final_reviewed_by": "human-reviewed",
                "tags": ["representative"],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "unsupported sampling_unit"):
                    load_cases([path])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.dictation_ai.cases.sbd_case_paths import SBD_CHALLENGE_CASE_DIR
from tests.eval.dictation_ai.cases.sbd_input_evidence import case_input_evidence
from tests.eval.dictation_ai.cases.validate_sbd_case_files import enforce_case_thresholds, validate_case_files


class DictationAiSbdCaseValidatorTest(unittest.TestCase):
    def _write_payload(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def _write_review_packets(self, path: Path, *, language: str = "ko", source_log: str = ".tmp/logs/avc-whisper.log") -> None:
        payload = {
            "representative_review_packet_version": 1,
            "source_manifest": {
                "sampling_unit": "session-window",
                "sampling_rule": "session-hash-v1:test",
                "selected_source_count": 1,
                "selected_source_counts": {language: 1},
            },
            "packet_count": 1,
            "ready_packet_count": 1,
            "missing_source_logs": [],
            "packet_readiness_blockers": [],
            "interpretation": {
                "paper_evidence": False,
                "case_generation": False,
                "expected_final_generated": False,
            },
            "packets": [
                {
                    "id": "ko_representative_review_abc",
                    "language": language,
                    "source_log": source_log,
                    "source_started_at": "2026-06-21 00:00:00",
                    "source_ended_at": "2026-06-21 00:01:00",
                    "source_window_filter": {
                        "applied": True,
                        "started_at": "2026-06-21 00:00:00",
                        "ended_at": "2026-06-21 00:01:00",
                    },
                    "event_counts": {
                        "raw_chunks": 1,
                        "transcripts": 1,
                        "final_events": 1,
                        "performance_events": 1,
                    },
                    "review_readiness": {
                        "ready_for_human_review": True,
                        "missing_event_kinds": [],
                    },
                    "paper_evidence": False,
                    "case_generation": False,
                    "expected_final_generated": False,
                }
            ],
        }
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
        self.assertEqual(summary["source_trace_case_count"], 0)
        self.assertEqual(summary["missing_source_trace_case_count"], 1)
        self.assertEqual(summary["missing_source_trace_by_file"], {str(path): 1})
        self.assertEqual(
            summary["missing_source_trace_examples"],
            [
                {
                    "id": "case-a",
                    "path": str(path),
                    "line_no": 1,
                    "language": "ko",
                    "review_source_file": "",
                }
            ],
        )
        self.assertEqual(summary["input_unsupported_case_count"], 0)
        self.assertEqual(summary["input_unsupported_by_file"], {})
        self.assertEqual(summary["input_unsupported_examples"], [])
        self.assertEqual(summary["input_unobserved_case_count"], 0)
        self.assertEqual(summary["input_unobserved_by_file"], {})
        self.assertEqual(summary["input_unobserved_examples"], [])
        self.assertEqual(summary["language_counts"], {"ko": 1})
        self.assertEqual(summary["tag_counts"], {"missing-final": 1})

    def test_reports_expected_final_without_input_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["다른 문장입니다."],
                    "expected_final": ["안녕하세요."],
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([path])

        self.assertEqual(summary["input_unsupported_case_count"], 1)
        self.assertEqual(summary["input_unsupported_by_file"], {str(path): 1})
        self.assertEqual(
            summary["input_unsupported_examples"],
            [
                {
                    "id": "case-a",
                    "path": str(path),
                    "line_no": 1,
                    "language": "ko",
                    "expected_count": 1,
                    "covered_count": 0,
                    "observed_count": 0,
                    "coverage_min": 0.0,
                    "coverage_avg": 0.0,
                }
            ],
        )
        self.assertEqual(summary["input_unobserved_case_count"], 1)
        self.assertEqual(summary["input_unobserved_by_file"], {str(path): 1})

    def test_can_require_expected_final_input_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["다른 문장입니다."],
                    "expected_final": ["안녕하세요."],
                    "tags": ["missing-final"],
                },
            )

            with self.assertRaisesRegex(ValueError, "expected_final is not fully supported"):
                validate_case_files([path], require_input_evidence=True)

    def test_can_require_expected_final_observed_input_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": [
                        "테슬라 뭐 사기꾼인 한 사람들 물론 있지만 "
                        "미국에서는 믿어주고 응원해주고 조금 기다려줬습니다."
                    ],
                    "expected_final": [
                        "테슬라 뭐 사기꾼이 한 사람들 물론 있지만 "
                        "미국에서는 믿어주고 응원해주고 조금 기다려줬습니다."
                    ],
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([path])
            with self.assertRaisesRegex(ValueError, "expected_final is not observed as raw STT text"):
                validate_case_files([path], require_observed_input_evidence=True)

        self.assertEqual(summary["input_unsupported_case_count"], 0)
        self.assertEqual(summary["input_unobserved_case_count"], 1)
        self.assertEqual(summary["input_unobserved_by_file"], {str(path): 1})
        self.assertEqual(
            summary["input_unobserved_examples"],
            [
                {
                    "id": "case-a",
                    "path": str(path),
                    "line_no": 1,
                    "language": "ko",
                    "expected_count": 1,
                    "observed_count": 0,
                    "covered_count": 1,
                    "coverage_min": 0.75,
                    "coverage_avg": 0.75,
                }
            ],
        )

    def test_reports_expected_final_without_three_repeated_sentence_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": [
                        "우리는 계속해서 미국 투자를 이어갈 것인가?",
                        "우리는 계속해서 미국 투자를 이어갈 것인가?",
                        "우리는 계속해서 미국 투자를 이어갈 것인가?",
                        "트럼프 행정부에서 지금",
                    ],
                    "sentence_finalize_age": 3,
                    "expected_final": [
                        "우리는 계속해서 미국 투자를 이어갈 것인가?",
                        "트럼프 행정부에서 지금 완전히 다른 정책을 보고 있습니다.",
                    ],
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([path])
            with self.assertRaisesRegex(ValueError, "expected_final is not supported by repeated token-sentence candidates"):
                validate_case_files([path], require_stable_repeat_evidence=True)

        self.assertEqual(summary["stable_repeat_unsupported_case_count"], 1)
        self.assertEqual(summary["stable_repeat_unsupported_by_file"], {str(path): 1})
        self.assertEqual(summary["stable_repeat_unsupported_examples"][0]["stable_repeat_count"], 1)
        self.assertEqual(summary["stable_repeat_unsupported_examples"][0]["required_repeat_observations"], 3)
        self.assertEqual(summary["stable_repeat_unsupported_examples"][0]["repeat_count_min"], 0)
        self.assertEqual(summary["stable_repeat_unsupported_examples"][0]["stable_candidate_count"], 1)
        self.assertEqual(
            summary["stable_repeat_unsupported_examples"][0]["stable_candidate_examples"],
            [{"text": "우리는 계속해서 미국 투자를 이어갈 것인가?", "count": 3, "first_index": 0, "last_index": 2}],
        )

    def test_case_input_evidence_accepts_three_repeated_sentence_candidates(self) -> None:
        evidence = case_input_evidence(
            {
                "sentence_finalize_age": 3,
                "chunks": [
                    "우리는 계속해서 미국 투자를 이어갈 것인가?",
                    "우리는 계속해서 미국 투자를 이어갈 것인가?",
                    "우리는 계속해서 미국 투자를 이어갈 것인가?",
                ],
                "expected_final": ["우리는 계속해서 미국 투자를 이어갈 것인가?"],
            }
        )

        self.assertTrue(evidence["stable_repeat_fully_supported"])
        self.assertEqual(evidence["stable_repeat_count"], 1)
        self.assertEqual(evidence["required_repeat_observations"], 3)
        self.assertEqual(evidence["repeat_count_min"], 3)
        self.assertEqual(
            evidence["stable_candidate_examples"],
            [{"text": "우리는 계속해서 미국 투자를 이어갈 것인가?", "count": 3, "first_index": 0, "last_index": 2}],
        )

    def test_case_input_evidence_accepts_repeated_expected_inside_context_windows(self) -> None:
        evidence = case_input_evidence(
            {
                "sentence_finalize_age": 3,
                "chunks": [
                    "앞선 문맥입니다. 목표 문장입니다.",
                    "다른 앞선 문맥입니다. 목표 문장입니다. 다음 문장입니다.",
                    "목표 문장입니다. 더 이어지는 문맥입니다.",
                ],
                "expected_final": ["목표 문장입니다."],
            }
        )

        self.assertTrue(evidence["stable_repeat_fully_supported"])
        self.assertEqual(evidence["stable_repeat_count"], 1)
        self.assertEqual(evidence["repeat_count_min"], 3)

    def test_case_input_evidence_ignores_punctuation_only_sentence_candidates(self) -> None:
        evidence = case_input_evidence(
            {
                "sentence_finalize_age": 3,
                "chunks": [
                    ".",
                    ".",
                    ".",
                    "실제 문장입니다.",
                    "실제 문장입니다.",
                    "실제 문장입니다.",
                ],
                "expected_final": ["실제 문장입니다."],
            }
        )

        self.assertTrue(evidence["stable_repeat_fully_supported"])
        self.assertEqual(evidence["stable_candidate_count"], 1)
        self.assertEqual(
            evidence["stable_candidate_examples"],
            [{"text": "실제 문장입니다.", "count": 3, "first_index": 0, "last_index": 2}],
        )

    def test_case_input_evidence_prefers_terminated_stable_candidate_representative(self) -> None:
        evidence = case_input_evidence(
            {
                "sentence_finalize_age": 3,
                "chunks": [
                    "반복 문장입니다 이어지는 미완성 꼬리",
                    "반복 문장입니다 이어지는 미완성 꼬리.",
                    "반복 문장입니다 이어지는 미완성 꼬리",
                    "반복 문장입니다 이어지는 미완성 꼬리.",
                    "반복 문장입니다 이어지는 미완성 꼬리.",
                ],
                "expected_final": ["반복 문장입니다 이어지는 미완성 꼬리."],
            }
        )

        self.assertTrue(evidence["stable_repeat_fully_supported"])
        self.assertEqual(
            evidence["stable_candidate_examples"],
            [{"text": "반복 문장입니다 이어지는 미완성 꼬리.", "count": 5, "first_index": 0, "last_index": 4}],
        )

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

    def test_challenge_root_only_loads_language_shards(self) -> None:
        self.assertEqual(SBD_CHALLENGE_CASE_DIR.name, "sbd_cases")
        self.assertEqual(SBD_CHALLENGE_CASE_DIR.parent.name, "dictation_ai")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_cases"
            language_dir = root / "ko"
            ignored_dir = root / "auto-groups"
            language_dir.mkdir(parents=True)
            ignored_dir.mkdir()
            self._write_payload(
                language_dir / "reviewed-context-ko-a.jsonl",
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                    "tags": ["missing-final"],
                },
            )
            self._write_payload(
                ignored_dir / "reviewed-group.jsonl",
                {
                    "id": "ignored-case",
                    "language": "ko",
                    "chunks": ["무시합니다."],
                    "expected_final": ["무시합니다."],
                    "tags": ["missing-final"],
                },
            )

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR", root):
                summary = validate_case_files([root])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["corpus_role"], "challenge-replay")
        self.assertEqual(summary["sources"], [str(language_dir / "reviewed-context-ko-a.jsonl")])

    def test_rejects_empty_case_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "empty_cases"
            root.mkdir()

            with self.assertRaisesRegex(ValueError, "no SBD case files matched"):
                validate_case_files([root])

    def test_representative_root_requires_sampling_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            self._write_payload(
                root / "cases.jsonl",
                {
                    "id": "representative-a",
                    "language": "ko",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                    "corpus_role": "representative",
                    "sampling_unit": "time-window",
                    "source_log": ".tmp/logs/avc-whisper.log",
                    "source_started_at": "chunk:1",
                    "source_ended_at": "chunk:3",
                    "stt_backend": "faster-whisper",
                    "stt_model": "large-v3",
                    "window_seconds": 10.0,
                    "step_seconds": 1.0,
                    "sentence_finalize_age": 3,
                    "tags": ["representative"],
                },
            )

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: sampling_rule"):
                    validate_case_files([root])

    def test_representative_root_reports_valid_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            self._write_payload(case_file, self._representative_payload())

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                summary = validate_case_files([root])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["corpus_role"], "representative")
        self.assertEqual(summary["expected_final_case_count"], 1)
        self.assertEqual(
            summary["representative_metadata"],
            {
                "sampling_unit_counts": {"time-window": 1},
                "sampling_rule_counts": {"fixed-interval-10min": 1},
                "source_log_count": 1,
                "source_log_counts": {".tmp/logs/avc-whisper.log": 1},
                "review_packet_count": 1,
                "review_packet_counts": {"ko_representative_review_abc": 1},
                "expected_final_reviewer_counts": {"human-reviewed": 1},
            },
        )

    def test_representative_root_rejects_unsupported_sampling_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            payload["sampling_unit"] = "failure-cluster"
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "unsupported sampling_unit"):
                    validate_case_files([root])

    def test_representative_root_requires_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            payload["language"] = ""
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: language"):
                    validate_case_files([root])

    def test_representative_root_requires_chunks_not_text_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            payload["text"] = "안녕하세요."
            del payload["chunks"]
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: chunks"):
                    validate_case_files([root])

    def test_representative_root_requires_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            del payload["stt_backend"]
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: stt_backend"):
                    validate_case_files([root])

    def test_representative_root_requires_reviewed_expected_final_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            payload["expected_final"] = []
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: expected_final"):
                    validate_case_files([root])

    def test_representative_draft_allows_missing_expected_final_only_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            payload["expected_final"] = []
            payload["expected_final_reviewed_by"] = ""
            payload["draft_expected_final_required"] = True
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: expected_final"):
                    validate_case_files([root])
                summary = validate_case_files([root], allow_drafts=True)

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["draft_count"], 1)
        self.assertEqual(summary["expected_final_case_count"], 0)
        self.assertEqual(summary["representative_metadata"]["review_packet_count"], 1)

    def test_representative_draft_can_be_validated_outside_representative_root_with_explicit_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case_file = Path(tmpdir) / "draft.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            payload = self._representative_payload()
            payload["expected_final"] = []
            payload["expected_final_reviewed_by"] = ""
            payload["draft_expected_final_required"] = True
            self._write_payload(case_file, payload)
            self._write_review_packets(review_packet_file)

            summary = validate_case_files(
                [case_file],
                allow_drafts=True,
                review_packets=review_packet_file,
                corpus_role_override="representative",
            )

        self.assertEqual(summary["corpus_role"], "representative")
        self.assertEqual(summary["draft_count"], 1)
        self.assertEqual(summary["representative_review_packet_validation"]["matched_case_count"], 1)

    def test_representative_root_requires_review_packet_traceability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            del payload["review_packet_id"]
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: review_packet_id"):
                    validate_case_files([root])

    def test_representative_root_requires_expected_final_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            payload = self._representative_payload()
            payload["expected_final_reviewed_by"] = ""
            self._write_payload(root / "cases.jsonl", payload)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "missing metadata: expected_final_reviewed_by"):
                    validate_case_files([root])

    def test_representative_file_input_requires_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            self._write_payload(case_file, self._representative_payload())

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                summary = validate_case_files([case_file])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["corpus_role"], "representative")
        self.assertEqual(summary["representative_metadata"]["sampling_unit_counts"], {"time-window": 1})

    def test_representative_review_packet_link_validation_accepts_matching_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            self._write_payload(case_file, self._representative_payload())
            self._write_review_packets(review_packet_file)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                summary = validate_case_files([case_file], review_packets=review_packet_file)

        self.assertEqual(
            summary["representative_review_packet_validation"],
            {
                "review_packet_file": str(review_packet_file),
                "packet_count": 1,
                "ready_packet_count": 1,
                "matched_case_count": 1,
                "source_manifest": {
                    "sampling_unit": "session-window",
                    "sampling_rule": "session-hash-v1:test",
                    "selected_source_count": 1,
                    "selected_source_counts": {"ko": 1},
                },
            },
        )

    def test_representative_review_packet_link_rejects_unknown_packet_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            payload = self._representative_payload()
            payload["review_packet_id"] = "unknown-packet"
            self._write_payload(case_file, payload)
            self._write_review_packets(review_packet_file)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "unknown review_packet_id"):
                    validate_case_files([case_file], review_packets=review_packet_file)

    def test_representative_review_packet_link_rejects_source_log_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            self._write_payload(case_file, self._representative_payload())
            self._write_review_packets(review_packet_file, source_log=".tmp/logs/other.log")

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "source_log mismatch"):
                    validate_case_files([case_file], review_packets=review_packet_file)

    def test_representative_review_packet_link_rejects_language_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            self._write_payload(case_file, self._representative_payload())
            self._write_review_packets(review_packet_file, language="en")

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "language mismatch"):
                    validate_case_files([case_file], review_packets=review_packet_file)

    def test_representative_review_packet_link_rejects_source_range_outside_packet_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sbd_representative_cases"
            root.mkdir()
            case_file = root / "cases.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            payload = self._representative_payload()
            payload["source_started_at"] = "2026-06-21 00:00:30"
            payload["source_ended_at"] = "2026-06-21 00:02:00"
            self._write_payload(case_file, payload)
            self._write_review_packets(review_packet_file)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "source range outside review packet window"):
                    validate_case_files([case_file], review_packets=review_packet_file)

    def test_review_packets_option_requires_representative_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            case_file = Path(tmpdir) / "cases.jsonl"
            review_packet_file = Path(tmpdir) / "review-packets.json"
            self._write_payload(
                case_file,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                },
            )
            self._write_review_packets(review_packet_file)

            with self.assertRaisesRegex(ValueError, "only be used with representative corpus"):
                validate_case_files([case_file], review_packets=review_packet_file)

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

    def test_can_require_source_trace_for_expected_final_cases(self) -> None:
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
            with self.assertRaisesRegex(ValueError, "missing source trace metadata: source_log, source_chunk"):
                validate_case_files([path], require_source_trace=True)

        self.assertEqual(summary["source_trace_case_count"], 0)
        self.assertEqual(summary["missing_source_trace_case_count"], 1)

    def test_accepts_source_trace_for_expected_final_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            self._write_payload(
                path,
                {
                    "id": "case-a",
                    "language": "ko",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                    "source_log": ".tmp/logs/avc-whisper.log",
                    "source_chunk": 0,
                    "tags": ["missing-final"],
                },
            )

            summary = validate_case_files([path], require_source_trace=True)

        self.assertEqual(summary["source_trace_case_count"], 1)
        self.assertEqual(summary["missing_source_trace_case_count"], 0)

    def test_enforces_case_thresholds(self) -> None:
        summary = {"case_count": 2, "draft_count": 1, "expected_final_case_count": 1}

        enforce_case_thresholds(summary, min_cases=2, min_expected_final_cases=1, max_drafts=1)

        with self.assertRaisesRegex(ValueError, "below target"):
            enforce_case_thresholds(summary, min_cases=3)
        with self.assertRaisesRegex(ValueError, "expected-final case count below target"):
            enforce_case_thresholds(summary, min_expected_final_cases=2)
        with self.assertRaisesRegex(ValueError, "above limit"):
            enforce_case_thresholds(summary, max_drafts=0)

    def _representative_payload(self) -> dict[str, object]:
        return {
            "id": "representative-a",
            "language": "ko",
            "chunks": ["안녕하세요."],
            "expected_final": ["안녕하세요."],
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
            "review_packet_id": "ko_representative_review_abc",
            "expected_final_reviewed_by": "human-reviewed",
            "tags": ["representative"],
        }


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.dictation_ai.audit_sbd_followup_readiness import (
    audit_followup_readiness,
)


class DictationAiSbdFollowupReadinessAuditTest(unittest.TestCase):
    def _write_source_audit(self, path: Path, *, can_seed: bool = True, translation: int = 2) -> None:
        path.write_text(
            json.dumps(
                {
                    "representative_readiness": {
                        "can_seed_representative_candidates": can_seed,
                    },
                    "marker_counts": {
                        "translation": translation,
                        "translation_diagnostic": translation,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_packet_validation(self, path: Path, *, ready_packet_count: int = 1) -> None:
        path.write_text(
            json.dumps(
                {
                    "packet_count": ready_packet_count,
                    "ready_packet_count": ready_packet_count,
                    "source_window_filter_applied_count": ready_packet_count,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_draft_validation(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "case_count": 1,
                    "corpus_role": "representative",
                    "draft_count": 1,
                    "expected_final_case_count": 0,
                    "language_counts": {"ko": 1},
                    "representative_review_packet_validation": {
                        "packet_count": 1,
                        "ready_packet_count": 1,
                        "matched_case_count": 1,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_review_packets(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "representative_review_packet_version": 1,
                    "source_manifest": {
                        "sampling_unit": "session-window",
                        "sampling_rule": "session-hash-v1:test",
                        "selected_source_count": 1,
                        "selected_source_counts": {"ko": 1},
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
                            "id": "packet-ko-1",
                            "language": "ko",
                            "source_log": ".tmp/logs/avc-whisper.log",
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
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_representative_case(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "id": "rep-ko-1",
                    "language": "ko",
                    "corpus_role": "representative",
                    "sampling_unit": "session-window",
                    "sampling_rule": "session-hash-v1:test",
                    "source_log": ".tmp/logs/avc-whisper.log",
                    "source_started_at": "2026-06-21 00:00:00",
                    "source_ended_at": "2026-06-21 00:01:00",
                    "stt_backend": "faster-whisper",
                    "stt_model": "large-v3",
                    "window_seconds": 10,
                    "step_seconds": 1,
                    "sentence_finalize_age": 3,
                    "review_packet_id": "packet-ko-1",
                    "expected_final_reviewed_by": "human",
                    "chunks": ["안녕하세요."],
                    "expected_final": ["안녕하세요."],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_reports_human_expected_final_blocker_when_no_representative_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_audit = root / "source.json"
            packet_validation = root / "packets.validation.json"
            review_packets = root / "packets.json"
            draft_validation = root / "drafts.validation.json"
            cases = root / "cases"
            cases.mkdir()
            self._write_source_audit(source_audit)
            self._write_packet_validation(packet_validation)
            self._write_review_packets(review_packets)
            self._write_draft_validation(draft_validation)

            result = audit_followup_readiness(
                source_audit_path=source_audit,
                review_packet_validation_path=packet_validation,
                representative_cases=cases,
                review_packets=review_packets,
                representative_draft_validation=draft_validation,
            )

        self.assertEqual(result["representative"]["status"], "blocked_on_human_expected_final")
        self.assertEqual(result["representative"]["source_window_filter_applied_count"], 1)
        self.assertEqual(result["representative"]["draft_summary"]["draft_count"], 1)
        self.assertTrue(result["representative"]["draft_summary"]["traceable"])
        self.assertFalse(result["paper_evidence_ready"])
        self.assertIn(
            "fill expected_final in traceable representative drafts and promote reviewed JSONL cases",
            result["next_actions"],
        )

    def test_reports_ready_for_pilot_when_representative_case_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_audit = root / "source.json"
            packet_validation = root / "packets.validation.json"
            review_packets = root / "packets.json"
            cases = root / "cases"
            self._write_source_audit(source_audit)
            self._write_packet_validation(packet_validation)
            self._write_review_packets(review_packets)
            self._write_representative_case(cases / "rep.jsonl")

            with patch("tests.eval.dictation_ai.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", cases):
                result = audit_followup_readiness(
                    source_audit_path=source_audit,
                    review_packet_validation_path=packet_validation,
                    representative_cases=cases,
                    review_packets=review_packets,
                )

        self.assertEqual(result["representative"]["status"], "ready_for_pilot_representative_replay")
        self.assertEqual(result["representative"]["case_summary"]["expected_final_case_count"], 1)
        self.assertFalse(result["paper_evidence_ready"])
        self.assertEqual(result["translation"]["status"], "blocked_on_translation_replay_linkage")

    def test_reports_source_log_blocker_before_packet_or_case_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_audit = root / "source.json"
            packet_validation = root / "packets.validation.json"
            review_packets = root / "packets.json"
            cases = root / "cases"
            cases.mkdir()
            self._write_source_audit(source_audit, can_seed=False)
            self._write_packet_validation(packet_validation, ready_packet_count=1)
            self._write_review_packets(review_packets)

            result = audit_followup_readiness(
                source_audit_path=source_audit,
                review_packet_validation_path=packet_validation,
                representative_cases=cases,
                review_packets=review_packets,
            )

        self.assertEqual(result["representative"]["status"], "blocked_on_source_logs")


if __name__ == "__main__":
    unittest.main()

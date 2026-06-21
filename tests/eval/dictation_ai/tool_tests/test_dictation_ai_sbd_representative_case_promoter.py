import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.promote_sbd_representative_cases import promote_representative_cases


class DictationAiSbdRepresentativeCasePromoterTest(unittest.TestCase):
    def _write_case(self, path: Path, *, draft: bool = False) -> None:
        payload = {
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
            "window_seconds": 10.0,
            "step_seconds": 1.0,
            "sentence_finalize_age": 3,
            "review_packet_id": "packet-ko-1",
            "expected_final_reviewed_by": "human",
            "chunks": ["안녕하세요."],
            "expected_final": ["안녕하세요."],
            "expected_final_generated": False,
        }
        if draft:
            payload["draft_expected_final_required"] = True
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def _write_review_packets(self, path: Path) -> None:
        payload = {
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
        }
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_promotes_reviewed_case_into_language_shard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_file = root / "reviewed.jsonl"
            packets = root / "packets.json"
            output_root = root / "representative"
            self._write_case(case_file)
            self._write_review_packets(packets)

            result = promote_representative_cases(
                [case_file],
                review_packets=packets,
                output_root=output_root,
            )
            target = Path(result["targets"][0]["target"])
            target_text = target.read_text(encoding="utf-8").strip()

        self.assertTrue(result["promoted"])
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["expected_final_case_count"], 1)
        self.assertEqual(target.parent.name, "ko")
        self.assertTrue(target_text)

    def test_dry_run_reports_target_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_file = root / "reviewed.jsonl"
            packets = root / "packets.json"
            output_root = root / "representative"
            self._write_case(case_file)
            self._write_review_packets(packets)

            result = promote_representative_cases(
                [case_file],
                review_packets=packets,
                output_root=output_root,
                dry_run=True,
            )

        self.assertFalse(result["promoted"])
        self.assertFalse(Path(result["targets"][0]["target"]).exists())

    def test_rejects_unreviewed_draft_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_file = root / "draft.jsonl"
            packets = root / "packets.json"
            self._write_case(case_file, draft=True)
            self._write_review_packets(packets)

            with self.assertRaisesRegex(ValueError, "unreviewed draft"):
                promote_representative_cases([case_file], review_packets=packets, output_root=root / "out")


if __name__ == "__main__":
    unittest.main()

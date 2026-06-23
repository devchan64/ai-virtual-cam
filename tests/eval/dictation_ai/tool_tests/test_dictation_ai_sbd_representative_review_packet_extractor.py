import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.representative.extract_sbd_representative_review_packets import (
    build_review_packets,
    write_markdown_packets,
)


class DictationAiSbdRepresentativeReviewPacketExtractorTest(unittest.TestCase):
    def test_extracts_review_packet_without_generating_expected_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "avc-whisper.log"
            log_path.write_text(
                "\n".join(
                    [
                        "[2026-06-20 10:00:00] [avc] Dictation AI stt_raw: [ko raw] 첫번째 raw window",
                        "[2026-06-20 10:00:01] [avc] 받아쓰기 AI 성능: chunk=1 step=1.0s window=10.0s text_chars=16 audio_rms=0.01",
                        (
                            "[2026-06-20 10:00:01] [avc] Dictation AI status: 받아쓰기 AI stage 교체 보류: "
                            "chunk=1 decision=unconfirmed_cjk staged_confirmations=1 staged_age=2 "
                            "staged_tail='이전 후보' candidate_tail='새 후보'"
                        ),
                        "[2026-06-20 10:00:02] [avc] 받아쓰기 AI 문장 확정: chunk=1 reason=age output_chars=8 text='첫 문장입니다.' staged_tail=''",
                        "[2026-06-20 10:00:03] [avc] Dictation AI transcript: [ko#7] 첫 문장입니다.",
                    ]
                ),
                encoding="utf-8",
            )
            manifest = {
                "sampling_unit": "session-window",
                "sampling_rule": "session-hash-v1:seed=test:per_language=1",
                "selected_source_count": 1,
                "selected_source_counts": {"ko": 1},
                "selected_sources": [
                    {
                        "id": "ko_representative_review_abc",
                        "language": "ko",
                        "source_log": str(log_path),
                        "source_started_at": "2026-06-20 10:00:00",
                        "source_ended_at": "2026-06-20 10:00:03",
                        "sampling_unit": "session-window",
                        "sampling_rule": "session-hash-v1:seed=test:per_language=1",
                        "stt_backend_candidates": {"faster-whisper": 1},
                        "stt_model_candidates": {"large-v3": 1},
                        "boundary_backend_candidates": {"sat": 1},
                        "boundary_model_candidates": {"sat-3l-sm": 1},
                        "window_seconds_candidates": {"10.0": 1},
                        "step_seconds_candidates": {"1.0": 1},
                        "sentence_finalize_age_candidates": {"3": 1},
                        "priority_metric": "stage_replace_deferred_per_stt_raw",
                        "priority_rank": 0,
                        "priority_ratio": 2.5,
                        "priority_marker_count": 25,
                    }
                ],
            }

            payload = build_review_packets(
                manifest,
                max_raw_chunks_per_source=10,
                max_transcripts_per_source=10,
                max_finals_per_source=10,
                max_performance_events_per_source=10,
                max_lifecycle_events_per_source=10,
                max_priority_window_suggestions=2,
                priority_window_before_seconds=10,
                priority_window_after_seconds=20,
                max_bounded_window_event_samples=4,
            )

        self.assertEqual(payload["packet_count"], 1)
        self.assertEqual(payload["ready_packet_count"], 1)
        self.assertEqual(payload["packet_readiness_blockers"], [])
        self.assertFalse(payload["interpretation"]["paper_evidence"])
        self.assertFalse(payload["interpretation"]["case_generation"])
        self.assertFalse(payload["interpretation"]["expected_final_generated"])
        packet = payload["packets"][0]
        self.assertFalse(packet["case_generation"])
        self.assertFalse(packet["expected_final_generated"])
        self.assertEqual(packet["event_counts"]["raw_chunks"], 1)
        self.assertEqual(packet["event_counts"]["final_events"], 1)
        self.assertEqual(packet["event_counts"]["transcripts"], 1)
        self.assertEqual(packet["event_counts"]["performance_events"], 1)
        self.assertEqual(packet["event_counts"]["lifecycle_events"], 1)
        self.assertEqual(packet["priority_metric"], "stage_replace_deferred_per_stt_raw")
        self.assertEqual(packet["priority_rank"], 0)
        self.assertEqual(packet["priority_ratio"], 2.5)
        self.assertEqual(packet["priority_marker_count"], 25)
        self.assertEqual(packet["priority_lifecycle_kind"], "stage_replace_deferred")
        self.assertEqual(
            packet["review_readiness"],
            {"ready_for_human_review": True, "missing_event_kinds": []},
        )
        self.assertEqual(packet["final_events_sample"][0]["text"], "첫 문장입니다.")
        self.assertEqual(packet["transcript_events_sample"][0]["segment_id"], "7")
        self.assertEqual(packet["performance_events_sample"][0]["chunk"], "1")
        self.assertEqual(packet["lifecycle_events_sample"][0]["kind"], "stage_replace_deferred")
        self.assertEqual(packet["lifecycle_events_sample"][0]["staged_tail"], "이전 후보")
        self.assertEqual(packet["lifecycle_events_sample"][0]["candidate_tail"], "새 후보")
        self.assertEqual(packet["priority_lifecycle_events_sample"][0]["kind"], "stage_replace_deferred")
        self.assertEqual(
            packet["priority_window_suggestions"][0],
            {
                "started_at": "2026-06-20 09:59:51",
                "ended_at": "2026-06-20 10:00:21",
                "anchor_timestamp": "2026-06-20 10:00:01",
                "anchor_line_number": 3,
                "anchor_kind": "stage_replace_deferred",
                "anchor_chunk": "1",
                "anchor_staged_tail": "이전 후보",
                "anchor_candidate_tail": "새 후보",
            },
        )
        candidate = packet["bounded_window_candidates"][0]
        self.assertEqual(candidate["id"], "ko_representative_review_abc_window_01")
        self.assertEqual(
            candidate["source_window_filter"],
            {
                "applied": True,
                "started_at": "2026-06-20 09:59:51",
                "ended_at": "2026-06-20 10:00:21",
            },
        )
        self.assertEqual(candidate["event_counts"]["raw_chunks"], 1)
        self.assertEqual(candidate["event_counts"]["final_events"], 1)
        self.assertEqual(candidate["event_counts"]["transcripts"], 1)
        self.assertEqual(candidate["priority_lifecycle_events_sample"][0]["kind"], "stage_replace_deferred")
        self.assertFalse(candidate["case_generation"])
        self.assertFalse(candidate["expected_final_generated"])

    def test_extracts_only_events_inside_selected_source_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "avc-whisper.log"
            log_path.write_text(
                "\n".join(
                    [
                        "[2026-06-20 09:59:59] [avc] Dictation AI stt_raw: [ko raw] 범위 밖 이전",
                        "[2026-06-20 10:00:00] [avc] Dictation AI stt_raw: [ko raw] 범위 안 raw",
                        "[2026-06-20 10:00:01] [avc] 받아쓰기 AI 성능: chunk=1 step=1.0s window=10.0s text_chars=16",
                        "[2026-06-20 10:00:02] [avc] 받아쓰기 AI 문장 확정: chunk=1 reason=age output_chars=8 text='범위 안 문장입니다.' staged_tail=''",
                        "[2026-06-20 10:00:03] [avc] Dictation AI transcript: [ko] 범위 안 문장입니다.",
                        "[2026-06-20 10:00:04] [avc] Dictation AI stt_raw: [ko raw] 범위 밖 이후",
                    ]
                ),
                encoding="utf-8",
            )
            manifest = {
                "sampling_unit": "session-window",
                "sampling_rule": "session-hash-v1:seed=test:per_language=1",
                "selected_source_count": 1,
                "selected_source_counts": {"ko": 1},
                "selected_sources": [
                    {
                        "id": "ko_representative_review_abc",
                        "language": "ko",
                        "source_log": str(log_path),
                        "source_started_at": "2026-06-20 10:00:00",
                        "source_ended_at": "2026-06-20 10:00:03",
                        "sampling_unit": "session-window",
                        "sampling_rule": "session-hash-v1:seed=test:per_language=1",
                    }
                ],
            }

            payload = build_review_packets(
                manifest,
                max_raw_chunks_per_source=10,
                max_transcripts_per_source=10,
                max_finals_per_source=10,
                max_performance_events_per_source=10,
                max_lifecycle_events_per_source=10,
                max_priority_window_suggestions=2,
                priority_window_before_seconds=10,
                priority_window_after_seconds=20,
                max_bounded_window_event_samples=4,
            )

        packet = payload["packets"][0]
        self.assertEqual(
            packet["source_window_filter"],
            {
                "applied": True,
                "started_at": "2026-06-20 10:00:00",
                "ended_at": "2026-06-20 10:00:03",
            },
        )
        self.assertEqual(packet["event_counts"]["raw_chunks"], 1)
        self.assertEqual(packet["raw_chunks_sample"][0]["text"], "범위 안 raw")
        self.assertEqual(packet["final_events_sample"][0]["text"], "범위 안 문장입니다.")

    def test_markdown_includes_review_checklist_runtime_and_performance_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "packets.md"
            payload = {
                "packet_count": 1,
                "ready_packet_count": 1,
                "packet_readiness_blockers": [],
                "missing_source_logs": [],
                "packets": [
                    {
                        "id": "ko_representative_review_abc",
                        "language": "ko",
                        "source_log": ".tmp/logs/avc-whisper.log",
                        "source_started_at": "2026-06-20 10:00:00",
                        "source_ended_at": "2026-06-20 10:01:00",
                        "source_window_filter": {
                            "applied": True,
                            "started_at": "2026-06-20 10:00:00",
                            "ended_at": "2026-06-20 10:01:00",
                        },
                        "sampling_unit": "session-window",
                        "sampling_rule": "session-hash-v1:seed=test:per_language=1",
                        "priority_metric": "stage_replace_deferred_per_stt_raw",
                        "priority_rank": 1,
                        "priority_ratio": 1.5,
                        "priority_marker_count": 15,
                        "priority_lifecycle_kind": "stage_replace_deferred",
                        "runtime_candidates": {
                            "stt_backend_candidates": {"faster-whisper": 1},
                            "stt_model_candidates": {"large-v3": 1},
                            "boundary_backend_candidates": {"sat": 1},
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
                        "raw_chunks_sample": [
                            {
                                "timestamp": "2026-06-20 10:00:00",
                                "line_number": 1,
                                "text": "첫번째 raw window",
                            }
                        ],
                        "final_events_sample": [],
                        "transcript_events_sample": [],
                        "performance_events_sample": [
                            {
                                "timestamp": "2026-06-20 10:00:01",
                                "line_number": 2,
                                "chunk": "1",
                                "window": "10.0s",
                                "stability": "0.8",
                                "stable_support": "0.7",
                                "boundary_score": "0.6",
                                "end_probability": "0.5",
                            }
                        ],
                        "lifecycle_events_sample": [
                            {
                                "timestamp": "2026-06-20 10:00:02",
                                "line_number": 3,
                                "kind": "stage_replace_deferred",
                                "chunk": "1",
                                "staged_age": "2",
                                "staged_confirmations": "1",
                                "staged_tail": "이전 후보",
                                "candidate_tail": "새 후보",
                            }
                        ],
                        "priority_lifecycle_events_sample": [
                            {
                                "timestamp": "2026-06-20 10:00:02",
                                "line_number": 3,
                                "kind": "stage_replace_deferred",
                                "chunk": "1",
                                "staged_age": "2",
                                "staged_confirmations": "1",
                                "staged_tail": "이전 후보",
                                "candidate_tail": "새 후보",
                            }
                        ],
                        "priority_window_suggestions": [
                            {
                                "started_at": "2026-06-20 09:59:52",
                                "ended_at": "2026-06-20 10:00:22",
                                "anchor_timestamp": "2026-06-20 10:00:02",
                                "anchor_line_number": 3,
                                "anchor_kind": "stage_replace_deferred",
                                "anchor_chunk": "1",
                                "anchor_staged_tail": "이전 후보",
                                "anchor_candidate_tail": "새 후보",
                            }
                        ],
                        "bounded_window_candidates": [
                            {
                                "id": "ko_representative_review_abc_window_01",
                                "source_window_filter": {
                                    "applied": True,
                                    "started_at": "2026-06-20 09:59:52",
                                    "ended_at": "2026-06-20 10:00:22",
                                },
                                "event_counts": {
                                    "raw_chunks": 1,
                                    "final_events": 1,
                                    "transcripts": 1,
                                    "lifecycle_events": 1,
                                },
                                "priority_lifecycle_events_sample": [
                                    {
                                        "kind": "stage_replace_deferred",
                                    }
                                ],
                                "anchor": {
                                    "timestamp": "2026-06-20 10:00:02",
                                    "line_number": 3,
                                },
                            }
                        ],
                    }
                ],
            }

            write_markdown_packets(payload, output)
            markdown = output.read_text(encoding="utf-8")

        self.assertIn("## Review Checklist", markdown)
        self.assertIn("Write `expected_final` by human review", markdown)
        self.assertIn("- runtime_candidates:", markdown)
        self.assertIn("priority: metric=`stage_replace_deferred_per_stt_raw` rank=`1`", markdown)
        self.assertIn("priority_lifecycle_kind: `stage_replace_deferred`", markdown)
        self.assertIn("faster-whisper", markdown)
        self.assertIn("- source_window_filter:", markdown)
        self.assertIn("'applied': True", markdown)
        self.assertIn("| suggested_window_start | suggested_window_end | anchor | line | kind |", markdown)
        self.assertIn(
            "| 2026-06-20 09:59:52 | 2026-06-20 10:00:22 | 2026-06-20 10:00:02 | 3 | stage_replace_deferred | 1 | 이전 후보 | 새 후보 |",
            markdown,
        )
        self.assertIn("| bounded_candidate | window | raw | final | transcript | priority_lifecycle | anchor |", markdown)
        self.assertIn(
            "| ko_representative_review_abc_window_01 | 2026-06-20 09:59:52..2026-06-20 10:00:22 | 1 | 1 | 1 | 1 | 2026-06-20 10:00:02 #3 |",
            markdown,
        )
        self.assertIn("| performance_timestamp | line | chunk | window | stability |", markdown)
        self.assertIn("| 2026-06-20 10:00:01 | 2 | 1 | 10.0s | 0.8 | 0.7 | 0.6 | 0.5 |", markdown)
        self.assertIn("| priority_lifecycle_timestamp | line | kind | chunk | staged_age |", markdown)
        self.assertIn("| lifecycle_timestamp | line | kind | chunk | staged_age |", markdown)
        self.assertIn("| 2026-06-20 10:00:02 | 3 | stage_replace_deferred | 1 | 2 | 1 | 이전 후보 | 새 후보 |", markdown)

    def test_downsamples_events_evenly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "avc-whisper.log"
            lines = [
                f"[2026-06-20 10:00:{index:02d}] [avc] Dictation AI stt_raw: [en raw] raw {index}"
                for index in range(5)
            ]
            log_path.write_text("\n".join(lines), encoding="utf-8")
            manifest = {
                "selected_sources": [
                    {
                        "id": "en_representative_review_abc",
                        "language": "en",
                        "source_log": str(log_path),
                    }
                ]
            }

            payload = build_review_packets(
                manifest,
                max_raw_chunks_per_source=3,
                max_transcripts_per_source=3,
                max_finals_per_source=3,
                max_performance_events_per_source=3,
                max_lifecycle_events_per_source=3,
                max_priority_window_suggestions=2,
                priority_window_before_seconds=10,
                priority_window_after_seconds=20,
                max_bounded_window_event_samples=4,
            )

        texts = [event["text"] for event in payload["packets"][0]["raw_chunks_sample"]]
        self.assertEqual(texts, ["raw 0", "raw 2", "raw 4"])
        self.assertEqual(payload["ready_packet_count"], 0)
        self.assertEqual(
            payload["packet_readiness_blockers"],
            [
                {
                    "id": "en_representative_review_abc",
                    "source_log": str(log_path),
                    "missing_event_kinds": ["transcripts", "final_events", "performance_events"],
                }
            ],
        )

    def test_records_missing_source_logs(self) -> None:
        payload = build_review_packets(
            {"selected_sources": [{"source_log": "/tmp/does-not-exist-avc-whisper.log"}]},
            max_raw_chunks_per_source=1,
            max_transcripts_per_source=1,
            max_finals_per_source=1,
            max_performance_events_per_source=1,
            max_lifecycle_events_per_source=1,
            max_priority_window_suggestions=1,
            priority_window_before_seconds=10,
            priority_window_after_seconds=20,
            max_bounded_window_event_samples=1,
        )

        self.assertEqual(payload["packet_count"], 0)
        self.assertEqual(payload["ready_packet_count"], 0)
        self.assertEqual(payload["packet_readiness_blockers"], [])
        self.assertEqual(payload["missing_source_logs"], ["/tmp/does-not-exist-avc-whisper.log"])


if __name__ == "__main__":
    unittest.main()

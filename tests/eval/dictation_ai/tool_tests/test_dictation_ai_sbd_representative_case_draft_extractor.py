import json
import unittest

from tests.eval.dictation_ai.representative.extract_sbd_representative_case_drafts import (
    build_case_drafts,
    render_jsonl,
    render_markdown,
)


class DictationAiSbdRepresentativeCaseDraftExtractorTest(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return {
            "packets": [
                {
                    "id": "ko_representative_review_abc",
                    "language": "ko",
                    "source_log": ".tmp/logs/avc-whisper.log",
                    "source_started_at": "2026-06-21 00:00:00",
                    "source_ended_at": "2026-06-21 00:01:00",
                    "source_window_filter": {
                        "applied": True,
                        "started_at": "2026-06-21 00:00:00",
                        "ended_at": "2026-06-21 00:01:00",
                    },
                    "sampling_unit": "session-window",
                    "sampling_rule": "session-hash-v1:test",
                    "priority_metric": "stage_replace_deferred_per_stt_raw",
                    "priority_rank": 0,
                    "priority_ratio": 2.5,
                    "priority_marker_count": 25,
                    "runtime_candidates": {
                        "stt_backend_candidates": {"faster-whisper": 2},
                        "stt_model_candidates": {"large-v3": 2},
                        "window_seconds_candidates": {"10.00s": 5, "10.0": 1},
                        "step_seconds_candidates": {"1.00s": 5},
                        "sentence_finalize_age_candidates": {"3": 2},
                    },
                    "review_readiness": {
                        "ready_for_human_review": True,
                        "missing_event_kinds": [],
                    },
                    "raw_chunks_sample": [
                        {"text": "첫 번째 원시 STT 가설입니다."},
                        {"text": "두 번째 원시 STT 가설입니다."},
                    ],
                },
                {
                    "id": "zh_representative_review_windowed",
                    "language": "zh",
                    "source_log": ".tmp/logs/avc-whisper.log",
                    "source_started_at": "2026-06-21 01:00:00",
                    "source_ended_at": "2026-06-21 01:10:00",
                    "source_window_filter": {
                        "applied": True,
                        "started_at": "2026-06-21 01:00:00",
                        "ended_at": "2026-06-21 01:10:00",
                    },
                    "sampling_unit": "session-window",
                    "sampling_rule": "session-hash-v1:windowed",
                    "priority_metric": "stage_replace_deferred_per_stt_raw",
                    "priority_rank": 1,
                    "priority_ratio": 1.5,
                    "priority_marker_count": 15,
                    "runtime_candidates": {
                        "stt_backend_candidates": {"qwen3-asr": 2},
                        "stt_model_candidates": {"qwen3-asr-0.6b": 2},
                        "window_seconds_candidates": {"15.00s": 5},
                        "step_seconds_candidates": {"1.00s": 5},
                        "sentence_finalize_age_candidates": {"3": 2},
                    },
                    "review_readiness": {
                        "ready_for_human_review": True,
                        "missing_event_kinds": [],
                    },
                    "raw_chunks_sample": [{"text": "source 전체 샘플은 window draft에 쓰지 않는다."}],
                    "bounded_window_candidates": [
                        {
                            "id": "window_000",
                            "anchor": "2026-06-21 01:02:00",
                            "source_started_at": "2026-06-21 01:01:30",
                            "source_ended_at": "2026-06-21 01:02:30",
                            "source_window_filter": {
                                "applied": True,
                                "started_at": "2026-06-21 01:01:30",
                                "ended_at": "2026-06-21 01:02:30",
                            },
                            "event_counts": {"stt_raw": 3, "stage_replace_deferred": 2},
                            "review_complexity": 4,
                            "priority_lifecycle_kind": "stage_replace_deferred",
                            "raw_chunks_sample": [
                                {"text": "窗口一第一条。"},
                                {"text": "窗口一第二条。"},
                            ],
                        },
                        {
                            "id": "window_001",
                            "anchor": "2026-06-21 01:04:00",
                            "source_started_at": "2026-06-21 01:03:30",
                            "source_ended_at": "2026-06-21 01:04:30",
                            "source_window_filter": {
                                "applied": True,
                                "started_at": "2026-06-21 01:03:30",
                                "ended_at": "2026-06-21 01:04:30",
                            },
                            "event_counts": {"stt_raw": 4, "final": 1},
                            "review_complexity": 3,
                            "priority_lifecycle_kind": "stage_replace_deferred",
                            "raw_chunks_sample": [{"text": "窗口二第一条。"}],
                        },
                    ],
                },
                {
                    "id": "en_not_ready",
                    "language": "en",
                    "review_readiness": {
                        "ready_for_human_review": False,
                        "missing_event_kinds": ["final_events"],
                    },
                    "raw_chunks_sample": [{"text": "ignored"}],
                },
            ]
        }

    def test_builds_manual_drafts_only_from_ready_packets(self) -> None:
        drafts_payload = build_case_drafts(self._payload())

        self.assertEqual(drafts_payload["source_review_packet_count"], 3)
        self.assertEqual(drafts_payload["ready_review_packet_count"], 2)
        self.assertEqual(drafts_payload["draft_count"], 3)
        self.assertFalse(drafts_payload["paper_evidence"])
        self.assertFalse(drafts_payload["expected_final_generated"])
        draft = drafts_payload["drafts"][0]
        self.assertEqual(draft["id"], "ko_representative_review_abc_draft")
        self.assertEqual(draft["review_scope"], "source")
        self.assertEqual(draft["corpus_role"], "representative")
        self.assertEqual(draft["priority_metric"], "stage_replace_deferred_per_stt_raw")
        self.assertEqual(draft["priority_rank"], 0)
        self.assertEqual(draft["priority_ratio"], 2.5)
        self.assertEqual(draft["priority_marker_count"], 25)
        self.assertEqual(draft["window_seconds"], 10.0)
        self.assertEqual(draft["sentence_finalize_age"], 3)
        self.assertEqual(
            draft["source_window_filter"],
            {
                "applied": True,
                "started_at": "2026-06-21 00:00:00",
                "ended_at": "2026-06-21 00:01:00",
            },
        )
        self.assertEqual(draft["expected_final"], [])
        self.assertEqual(draft["expected_final_reviewed_by"], "")
        self.assertTrue(draft["draft_expected_final_required"])

    def test_builds_bounded_window_drafts_when_candidates_exist(self) -> None:
        drafts_payload = build_case_drafts(self._payload())
        drafts_by_id = {str(draft["id"]): draft for draft in drafts_payload["drafts"]}

        draft = drafts_by_id["zh_representative_review_windowed_window_000_draft"]
        self.assertEqual(draft["review_scope"], "bounded-window")
        self.assertEqual(draft["bounded_window_id"], "window_000")
        self.assertEqual(draft["bounded_window_anchor"], "2026-06-21 01:02:00")
        self.assertEqual(draft["priority_lifecycle_kind"], "stage_replace_deferred")
        self.assertEqual(draft["bounded_window_event_counts"], {"stt_raw": 3, "stage_replace_deferred": 2})
        self.assertEqual(draft["bounded_window_review_complexity"], 4)
        self.assertEqual(
            draft["source_window_filter"],
            {
                "applied": True,
                "started_at": "2026-06-21 01:01:30",
                "ended_at": "2026-06-21 01:02:30",
            },
        )
        self.assertEqual(draft["chunks"], ["窗口一第一条。", "窗口一第二条。"])
        self.assertNotIn("source 전체 샘플은 window draft에 쓰지 않는다.", draft["chunks"])

    def test_renders_jsonl_and_markdown_without_generating_expected_final(self) -> None:
        drafts_payload = build_case_drafts(self._payload())

        jsonl = render_jsonl(drafts_payload)
        markdown = render_markdown(drafts_payload)
        records = [json.loads(line) for line in jsonl.splitlines()]

        self.assertEqual(records[0]["expected_final"], [])
        self.assertIn("expected_final_generated: `false`", markdown)
        self.assertIn("priority: metric=`stage_replace_deferred_per_stt_raw` rank=`0`", markdown)
        self.assertIn("review_scope: `bounded-window`", markdown)
        self.assertIn("bounded_window_id: `window_000`", markdown)
        self.assertIn("## Human Review Steps", markdown)
        self.assertIn("Remove `draft_expected_final_required` before promotion.", markdown)
        self.assertIn("Template fields to edit:", markdown)
        self.assertIn("STT chunk preview:", markdown)
        self.assertIn("ko_representative_review_abc_draft", markdown)


if __name__ == "__main__":
    unittest.main()

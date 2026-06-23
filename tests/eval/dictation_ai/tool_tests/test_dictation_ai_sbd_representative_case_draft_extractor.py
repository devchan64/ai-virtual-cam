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

        self.assertEqual(drafts_payload["source_review_packet_count"], 2)
        self.assertEqual(drafts_payload["ready_review_packet_count"], 1)
        self.assertEqual(drafts_payload["draft_count"], 1)
        self.assertFalse(drafts_payload["paper_evidence"])
        self.assertFalse(drafts_payload["expected_final_generated"])
        draft = drafts_payload["drafts"][0]
        self.assertEqual(draft["id"], "ko_representative_review_abc_draft")
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

    def test_renders_jsonl_and_markdown_without_generating_expected_final(self) -> None:
        drafts_payload = build_case_drafts(self._payload())

        jsonl = render_jsonl(drafts_payload)
        markdown = render_markdown(drafts_payload)
        record = json.loads(jsonl)

        self.assertEqual(record["expected_final"], [])
        self.assertIn("expected_final_generated: `false`", markdown)
        self.assertIn("priority: metric=`stage_replace_deferred_per_stt_raw` rank=`0`", markdown)
        self.assertIn("## Human Review Steps", markdown)
        self.assertIn("Remove `draft_expected_final_required` before promotion.", markdown)
        self.assertIn("Template fields to edit:", markdown)
        self.assertIn("STT chunk preview:", markdown)
        self.assertIn("ko_representative_review_abc_draft", markdown)


if __name__ == "__main__":
    unittest.main()

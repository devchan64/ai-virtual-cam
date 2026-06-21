import unittest

from tests.eval.dictation_ai.representative.validate_sbd_representative_review_packets import (
    validate_review_packets,
)


def _valid_payload() -> dict[str, object]:
    return {
        "representative_review_packet_version": 1,
        "source_manifest": {
            "sampling_unit": "session-window",
            "sampling_rule": "session-hash-v1:seed=test:per_language=1",
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
                "event_counts": {
                    "raw_chunks": 2,
                    "transcripts": 2,
                    "final_events": 1,
                    "performance_events": 2,
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


class DictationAiSbdRepresentativeReviewPacketValidatorTest(unittest.TestCase):
    def test_accepts_ready_non_case_review_packets(self) -> None:
        summary = validate_review_packets(_valid_payload())

        self.assertEqual(summary["packet_count"], 1)
        self.assertEqual(
            summary["source_manifest"],
            {
                "sampling_unit": "session-window",
                "sampling_rule": "session-hash-v1:seed=test:per_language=1",
                "selected_source_count": 1,
                "selected_source_counts": {"ko": 1},
            },
        )
        self.assertEqual(summary["ready_packet_count"], 1)
        self.assertEqual(summary["not_ready_packet_count"], 0)
        self.assertEqual(summary["missing_source_log_count"], 0)
        self.assertEqual(summary["language_counts"], {"ko": 1})
        self.assertEqual(
            summary["event_totals"],
            {
                "final_events": 1,
                "performance_events": 2,
                "raw_chunks": 2,
                "transcripts": 2,
            },
        )
        self.assertEqual(summary["source_window_filter_applied_count"], 1)

    def test_rejects_not_ready_packets_by_default(self) -> None:
        payload = _valid_payload()
        packet = payload["packets"][0]
        packet["review_readiness"] = {
            "ready_for_human_review": False,
            "missing_event_kinds": ["final_events"],
        }
        payload["ready_packet_count"] = 0
        payload["packet_readiness_blockers"] = [
            {
                "id": "ko_representative_review_abc",
                "source_log": ".tmp/logs/avc-whisper.log",
                "missing_event_kinds": ["final_events"],
            }
        ]

        with self.assertRaisesRegex(ValueError, "not-ready packets"):
            validate_review_packets(payload)

        summary = validate_review_packets(payload, allow_not_ready=True)
        self.assertEqual(summary["not_ready_packet_count"], 1)

    def test_rejects_payload_that_claims_case_generation(self) -> None:
        payload = _valid_payload()
        payload["interpretation"]["case_generation"] = True

        with self.assertRaisesRegex(ValueError, "must not be case generation"):
            validate_review_packets(payload)

    def test_rejects_packet_count_mismatch(self) -> None:
        payload = _valid_payload()
        payload["packet_count"] = 2

        with self.assertRaisesRegex(ValueError, "packet_count mismatch"):
            validate_review_packets(payload)

    def test_rejects_source_manifest_selected_source_count_mismatch(self) -> None:
        payload = _valid_payload()
        payload["source_manifest"]["selected_source_count"] = 2

        with self.assertRaisesRegex(ValueError, "selected_source_count mismatch"):
            validate_review_packets(payload)

    def test_rejects_source_manifest_language_count_mismatch(self) -> None:
        payload = _valid_payload()
        payload["source_manifest"]["selected_source_counts"] = {"en": 1}

        with self.assertRaisesRegex(ValueError, "selected_source_counts mismatch"):
            validate_review_packets(payload)

    def test_rejects_unsupported_version(self) -> None:
        payload = _valid_payload()
        payload["representative_review_packet_version"] = 999

        with self.assertRaisesRegex(ValueError, "unsupported representative review packet version"):
            validate_review_packets(payload)

    def test_rejects_stale_readiness_blocker_content(self) -> None:
        payload = _valid_payload()
        packet = payload["packets"][0]
        packet["review_readiness"] = {
            "ready_for_human_review": False,
            "missing_event_kinds": ["final_events"],
        }
        payload["ready_packet_count"] = 0
        payload["packet_readiness_blockers"] = [
            {
                "id": "wrong-id",
                "source_log": ".tmp/logs/avc-whisper.log",
                "missing_event_kinds": ["final_events"],
            }
        ]

        with self.assertRaisesRegex(ValueError, "content mismatch"):
            validate_review_packets(payload, allow_not_ready=True)

    def test_rejects_missing_source_logs_by_default(self) -> None:
        payload = _valid_payload()
        payload["missing_source_logs"] = [".tmp/logs/missing.log"]

        with self.assertRaisesRegex(ValueError, "missing source logs"):
            validate_review_packets(payload)

        summary = validate_review_packets(payload, allow_missing_source_logs=True)
        self.assertEqual(summary["missing_source_log_count"], 1)

    def test_rejects_missing_source_window_filter(self) -> None:
        payload = _valid_payload()
        del payload["packets"][0]["source_window_filter"]

        with self.assertRaisesRegex(ValueError, "missing source_window_filter"):
            validate_review_packets(payload)

    def test_rejects_unapplied_source_window_filter_when_source_range_exists(self) -> None:
        payload = _valid_payload()
        payload["packets"][0]["source_window_filter"]["applied"] = False

        with self.assertRaisesRegex(ValueError, "source_window_filter must be applied"):
            validate_review_packets(payload)

    def test_rejects_source_window_filter_range_mismatch(self) -> None:
        payload = _valid_payload()
        payload["packets"][0]["source_window_filter"]["started_at"] = "2026-06-20 10:00:01"

        with self.assertRaisesRegex(ValueError, "started_at mismatch"):
            validate_review_packets(payload)


if __name__ == "__main__":
    unittest.main()

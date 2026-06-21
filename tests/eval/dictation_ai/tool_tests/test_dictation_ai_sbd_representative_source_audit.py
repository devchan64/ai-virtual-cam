import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.representative.audit_sbd_representative_sources import (
    audit_sources,
    compact_summary,
    iter_log_paths,
)


class DictationAiSbdRepresentativeSourceAuditTest(unittest.TestCase):
    def test_iter_log_paths_loads_whisper_logs_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expected = root / "avc-whisper.log"
            rotated = root / "avc-whisper.log.1"
            ignored = root / "other.log"
            expected.write_text("", encoding="utf-8")
            rotated.write_text("", encoding="utf-8")
            ignored.write_text("", encoding="utf-8")

            paths = iter_log_paths([root])

        self.assertEqual(paths, [expected, rotated])

    def test_audit_reports_representative_source_readiness(self) -> None:
        log_text = "\n".join(
            [
                (
                    "[2026-06-20 21:22:39] [avc] Dictation AI status: 받아쓰기 AI 전사 루프 시작: "
                    "step_seconds=1.0 window_seconds=20.0 language=en stt_backend=faster-whisper "
                    "stt_model=large-v3 translation_enabled=True translation_backend=nllb-transformers "
                    "translation_target=ko sentence_finalize_age=3"
                ),
                "[2026-06-20 21:22:40] [avc] Dictation AI stt_raw: [en raw] Hello world.",
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 문장 확정: "
                    "chunk=1 segment_id=1 reason=confirmed text='Hello world.'"
                ),
                "[2026-06-20 21:22:40] [avc] Dictation AI transcript: [en#1] Hello world.",
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 문장 진단: "
                    "chunk=1 language=en boundary_backend=sat window=20.00s step=1.00s"
                ),
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 안정성 지표: "
                    "chunk=1 stage_queue_recent_final_suppressed=2 "
                    "stage_queue_recent_final_delta_trimmed=1 "
                    "finalize_delta_suppressed_stage_retained=1 "
                    "lifecycle_metrics=stage_queue_recent_final_suppressed=99,"
                    "stage_queue_recent_final_delta_trimmed=88"
                ),
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 번역 진단: "
                    "chunk=1 segment_id=1 final=True source_lang=en target_lang=ko backend=nllb-transformers "
                    "model=facebook/nllb-200-distilled-600M"
                ),
                "[2026-06-20 21:22:41] [avc] Dictation AI translation: [en->ko#1] 안녕하세요.",
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "avc-whisper.log"
            path.write_text(log_text + "\n", encoding="utf-8")

            summary = audit_sources([path])

        self.assertEqual(summary["source_count"], 1)
        self.assertEqual(summary["marker_counts"]["stt_raw"], 1)
        self.assertEqual(summary["marker_counts"]["finalize_event"], 1)
        self.assertEqual(summary["marker_counts"]["transcript"], 1)
        self.assertEqual(summary["language_counts"], {"en": 3})
        self.assertEqual(summary["backend_counts"], {"nllb-transformers": 1, "sat": 1})
        self.assertEqual(summary["model_counts"], {"facebook/nllb-200-distilled-600M": 1})
        self.assertEqual(summary["stt_backend_counts"], {"faster-whisper": 1})
        self.assertEqual(summary["stt_model_counts"], {"large-v3": 1})
        self.assertEqual(summary["boundary_backend_counts"], {"sat": 1})
        self.assertEqual(summary["translation_backend_counts"], {"nllb-transformers": 1})
        self.assertEqual(summary["window_seconds_counts"], {"20.0": 1, "20.00s": 1})
        self.assertEqual(summary["step_seconds_counts"], {"1.0": 1, "1.00s": 1})
        self.assertEqual(summary["sentence_finalize_age_counts"], {"3": 1})
        self.assertEqual(summary["marker_counts"]["stage_queue_recent_final_suppressed"], 2)
        self.assertEqual(summary["marker_counts"]["stage_queue_recent_final_delta_trimmed"], 1)
        self.assertEqual(summary["marker_counts"]["finalize_delta_suppressed_stage_retained"], 1)
        self.assertEqual(summary["finalization_observation"]["stage_queue_recent_final_suppressed_count"], 2)
        self.assertEqual(summary["finalization_observation"]["stage_queue_recent_final_delta_trimmed_count"], 1)
        self.assertEqual(summary["finalization_observation"]["finalize_delta_suppressed_stage_retained_count"], 1)
        self.assertEqual(
            summary["segment_linkage"],
            {
                "translation_enabled_source_count": 1,
                "finalize_segment_count": 1,
                "transcript_segment_count": 1,
                "translation_diagnostic_segment_count": 1,
                "translation_segment_count": 1,
                "final_transcript_linked_segment_count": 1,
                "final_translation_diagnostic_linked_segment_count": 1,
                "final_translation_linked_segment_count": 1,
                "finalize_without_transcript_count": 0,
                "transcript_without_finalize_count": 0,
                "translation_diagnostic_without_transcript_count": 0,
                "translation_without_transcript_count": 0,
                "translation_enabled_finalize_segment_count": 1,
                "translation_enabled_final_translation_linked_segment_count": 1,
                "translation_enabled_untranslated_final_segment_count": 0,
                "translation_enabled_final_translation_linked_ratio": 1.0,
                "ready_for_translation_replay_linkage": True,
                "ready_for_translation_diagnostic_linkage": True,
            },
        )
        readiness = summary["representative_readiness"]
        self.assertTrue(readiness["can_seed_representative_candidates"])
        self.assertTrue(readiness["has_runtime_metadata"])
        self.assertTrue(readiness["requires_manual_expected_final"])
        self.assertEqual(readiness["blockers"], [])

    def test_audit_blocks_sources_without_transcript_or_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "avc-whisper.log"
            path.write_text(
                "[2026-06-20 21:22:40] [avc] Dictation AI stt_raw: [ko raw] 안녕하세요.\n",
                encoding="utf-8",
            )

            summary = audit_sources([path])

        readiness = summary["representative_readiness"]
        self.assertFalse(readiness["can_seed_representative_candidates"])
        self.assertIn("transcript lines are missing", readiness["blockers"])
        self.assertIn("finalize event lines are missing", readiness["blockers"])
        self.assertIn("STT backend markers are missing", readiness["blockers"])
        self.assertIn("STT model markers are missing", readiness["blockers"])

    def test_audit_filters_selected_time_range(self) -> None:
        log_text = "\n".join(
            [
                (
                    "[2026-06-20 21:22:39] [avc] Dictation AI status: 받아쓰기 AI 전사 루프 시작: "
                    "step_seconds=1.0 window_seconds=20.0 language=en stt_backend=faster-whisper "
                    "stt_model=large-v3 translation_enabled=True sentence_finalize_age=3"
                ),
                "[2026-06-20 21:22:39] [avc] Dictation AI stt_raw: [en raw] Earlier window.",
                (
                    "[2026-06-20 21:22:39] [avc] Dictation AI status: 받아쓰기 AI 문장 확정: "
                    "chunk=1 segment_id=1 reason=confirmed text='Earlier window.'"
                ),
                "[2026-06-20 21:22:39] [avc] Dictation AI transcript: [en#1] Earlier window.",
                "[2026-06-20 21:22:40] [avc] Dictation AI stt_raw: [en raw] Selected window.",
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 문장 확정: "
                    "chunk=2 segment_id=2 reason=confirmed text='Selected window.'"
                ),
                "[2026-06-20 21:22:40] [avc] Dictation AI transcript: [en#2] Selected window.",
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "avc-whisper.log"
            path.write_text(log_text + "\n", encoding="utf-8")

            summary = audit_sources(
                [path],
                since="2026-06-20 21:22:40",
                until="2026-06-20 21:22:40",
            )

        self.assertEqual(summary["time_filter"]["applied"], True)
        self.assertEqual(summary["line_count"], 3)
        self.assertEqual(summary["first_timestamp"], "2026-06-20 21:22:40")
        self.assertEqual(summary["last_timestamp"], "2026-06-20 21:22:40")
        self.assertEqual(summary["marker_counts"]["stt_raw"], 1)
        self.assertEqual(summary["stt_backend_counts"], {"faster-whisper": 1})
        self.assertEqual(summary["stt_model_counts"], {"large-v3": 1})
        self.assertEqual(summary["sentence_finalize_age_counts"], {"3": 1})
        self.assertEqual(summary["segment_linkage"]["finalize_segment_count"], 1)
        self.assertEqual(summary["segment_linkage"]["transcript_segment_count"], 1)
        self.assertEqual(summary["files"][0]["segment_linkage"]["translation_enabled"], True)
        self.assertEqual(summary["finalization_observation"]["stt_raw_line_count"], 1)
        self.assertEqual(summary["finalization_observation"]["finalize_event_count"], 1)
        self.assertEqual(summary["finalization_observation"]["finalize_per_stt_raw"], 1.0)

    def test_compact_summary_omits_per_file_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "avc-whisper.log"
            path.write_text(
                "[2026-06-20 21:22:40] [avc] Dictation AI stt_raw: [en raw] Hello.\n",
                encoding="utf-8",
            )

            compact = compact_summary(audit_sources([path]))

        self.assertIn("source_count", compact)
        self.assertIn("representative_readiness", compact)
        self.assertIn("finalization_observation", compact)
        self.assertNotIn("files", compact)


if __name__ == "__main__":
    unittest.main()

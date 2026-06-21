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
                    "chunk=1 reason=confirmed text='Hello world.'"
                ),
                "[2026-06-20 21:22:40] [avc] Dictation AI transcript: [en] Hello world.",
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 문장 진단: "
                    "chunk=1 language=en boundary_backend=sat window=20.00s step=1.00s"
                ),
                (
                    "[2026-06-20 21:22:40] [avc] Dictation AI status: 받아쓰기 AI 번역 진단: "
                    "chunk=1 final=True source_lang=en target_lang=ko backend=nllb-transformers "
                    "model=facebook/nllb-200-distilled-600M"
                ),
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
        self.assertNotIn("files", compact)


if __name__ == "__main__":
    unittest.main()

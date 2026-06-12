import contextlib
import io
import json
import tempfile
import unittest
import queue
from types import SimpleNamespace
from pathlib import Path

from src.domain.config import WhisperConfig
from src.app.whisper_window import (
    TranscriptEvent,
    WhisperTranscriptWorker,
    _is_modal_output_event,
    _load_ui_language,
    _sanitize_window_geometry,
    _save_window_geometry,
    _window_title,
)


class WhisperWindowGeometryTest(unittest.TestCase):
    def test_saves_geometry_in_config_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"whisper": {"enabled": True}, "meta": {"language": "ko"}}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                _save_window_geometry(path, "whisperWindowGeometry", "820x460+120+80")

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"]["language"], "ko")
        self.assertEqual(raw["meta"]["whisperWindowGeometry"], "820x460+120+80")

    def test_saves_translation_geometry_in_config_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"whisper": {"enabled": True}, "meta": {"whisperWindowGeometry": "820x460+120+80"}}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                _save_window_geometry(path, "whisperTranslationWindowGeometry", "780x420+300+140")

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"]["whisperWindowGeometry"], "820x460+120+80")
        self.assertEqual(raw["meta"]["whisperTranslationWindowGeometry"], "780x420+300+140")

    def test_loads_localized_window_titles_from_config_meta_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"language": "ko"}}), encoding="utf-8")

            language = _load_ui_language(path)

        self.assertEqual(language, "ko")
        self.assertEqual(_window_title("transcript", language), "ai-virtual-cam 위스퍼 전사")
        self.assertEqual(_window_title("translation", language), "ai-virtual-cam 위스퍼 번역")

    def test_window_titles_fallback_to_english_for_unknown_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"language": "zh"}}), encoding="utf-8")

            language = _load_ui_language(path)

        self.assertEqual(language, "en")
        self.assertEqual(_window_title("transcript", language), "ai-virtual-cam Whisper Transcript")
        self.assertEqual(_window_title("translation", language), "ai-virtual-cam Whisper Translation")

    def test_skips_invalid_geometry_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"whisperWindowGeometry": "820x460+120+80"}}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                _save_window_geometry(path, "whisperWindowGeometry", "820x460+5000+80", 1920, 1080)

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"]["whisperWindowGeometry"], "820x460+120+80")

    def test_modal_output_only_allows_transcript_and_translation(self) -> None:
        self.assertTrue(_is_modal_output_event(TranscriptEvent("transcript", "hello")))
        self.assertTrue(_is_modal_output_event(TranscriptEvent("translation", "안녕")))
        self.assertFalse(_is_modal_output_event(TranscriptEvent("status", "loading")))
        self.assertFalse(_is_modal_output_event(TranscriptEvent("error", "failed")))
        self.assertFalse(_is_modal_output_event(TranscriptEvent("transcript", "hidden", display=False)))

    def test_sanitizes_geometry_before_restore(self) -> None:
        self.assertEqual(
            _sanitize_window_geometry("820x460+120+80", 1920, 1080),
            "820x460+120+80",
        )
        self.assertIsNone(_sanitize_window_geometry("200x100+120+80", 1920, 1080))
        self.assertIsNone(_sanitize_window_geometry("820x460+5000+80", 1920, 1080))
        self.assertIsNone(_sanitize_window_geometry("invalid", 1920, 1080))

    def test_filters_low_confidence_segments(self) -> None:
        worker = WhisperTranscriptWorker(WhisperConfig.from_dict({"inputDevice": "default"}), queue.Queue())
        segments = [
            SimpleNamespace(text=" 정상 문장 ", avg_logprob=-0.2, no_speech_prob=0.1),
            SimpleNamespace(text=" 무음 환각 ", avg_logprob=-0.2, no_speech_prob=0.9),
            SimpleNamespace(text=" 저신뢰 ", avg_logprob=-1.4, no_speech_prob=0.1),
        ]

        texts, rejected = worker._accepted_segment_texts(segments)

        self.assertEqual(texts, ["정상 문장"])
        self.assertEqual(len(rejected), 2)
        self.assertIn("no_speech", rejected[0])
        self.assertIn("low_logprob", rejected[1])

    def test_rejects_repeated_short_transcripts(self) -> None:
        worker = WhisperTranscriptWorker(WhisperConfig.from_dict({"inputDevice": "default"}), queue.Queue())
        worker._remember_transcript("다음 영상에서 만나요.")
        worker._remember_transcript("다음 영상에서 만나요.")

        self.assertTrue(worker._is_repeated_hallucination("다음 영상에서 만나요."))
        self.assertFalse(worker._is_repeated_hallucination("이 문장은 충분히 긴 새로운 설명이라 반복으로 보지 않습니다"))


if __name__ == "__main__":
    unittest.main()

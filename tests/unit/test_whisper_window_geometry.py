import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.app.whisper_window import (
    TranscriptEvent,
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


if __name__ == "__main__":
    unittest.main()

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
    DEFAULT_WINDOW_GEOMETRY_META,
    FINAL_TEXT_COLOR,
    FINAL_TEXT_TAG,
    PARTIAL_TEXT_COLOR,
    PARTIAL_TEXT_TAG,
    TranscriptEvent,
    WhisperTranscriptWindow,
    WhisperTranscriptWorker,
    _is_modal_output_event,
    _load_ui_language,
    _load_window_geometry,
    _window_manager_geometry,
    _sanitize_window_geometry,
    _save_window_geometry,
    _window_restore_extent,
    _window_title,
)


class WhisperWindowGeometryTest(unittest.TestCase):

    def test_window_manager_geometry_prefers_wm_geometry_over_widget_geometry(self) -> None:
        window = SimpleNamespace(
            geometry=lambda: "780x420+50+119",
            winfo_geometry=lambda: "780x420+50+156",
        )

        self.assertEqual(_window_manager_geometry(window), "780x420+50+119")

    def test_caches_geometry_by_log_without_writing_config_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"whisper": {"enabled": True}, "meta": {"language": "ko"}}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                _save_window_geometry(path, "whisperWindowGeometry", "820x460+120+80")

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"], {"language": "ko"})
        self.assertIn("window geometry cached: key=whisperWindowGeometry geometry=820x460+120+80", stdout.getvalue())

    def test_caches_translation_geometry_by_log_without_writing_config_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"whisper": {"enabled": True}, "meta": {"whisperWindowGeometry": "820x460+120+80"}}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                _save_window_geometry(path, "whisperTranslationWindowGeometry", "780x420+300+140")

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"], {"whisperWindowGeometry": "820x460+120+80"})
        self.assertIn("window geometry cached: key=whisperTranslationWindowGeometry geometry=780x420+300+140", stdout.getvalue())

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

    def test_skips_invalid_geometry_cache_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"whisperWindowGeometry": "820x460+120+80"}}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                _save_window_geometry(path, "whisperWindowGeometry", "820x460+5000+80", 1920, 1080)

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"]["whisperWindowGeometry"], "820x460+120+80")
        self.assertIn("window geometry cache skipped", stdout.getvalue())


    def test_append_styles_final_and_partial_lines(self) -> None:
        class FakeText:
            def __init__(self) -> None:
                self.tags = {}
                self.inserts = []
                self.deletes = []
                self.seen = []

            def tag_configure(self, tag: str, **kwargs) -> None:
                self.tags[tag] = kwargs

            def insert(self, index: str, text: str, tag: str | None = None) -> None:
                self.inserts.append((index, text, tag))

            def delete(self, start: str, end: str) -> None:
                self.deletes.append((start, end))

            def see(self, index: str) -> None:
                self.seen.append(index)

        widget = FakeText()
        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._text = widget
        window._translation_text = None
        window._transcript_partial_active = False
        window._translation_partial_active = False

        window._configure_transcript_text_tags(widget)
        window._append("초안 문장", widget, final=False)
        window._append("확정 문장", widget, final=True)

        self.assertEqual(widget.tags[FINAL_TEXT_TAG], {"foreground": FINAL_TEXT_COLOR})
        self.assertEqual(widget.tags[PARTIAL_TEXT_TAG], {"foreground": PARTIAL_TEXT_COLOR})
        self.assertEqual(widget.inserts[0], ("end", "초안 문장", PARTIAL_TEXT_TAG))
        self.assertEqual(widget.deletes, [("end-1c linestart", "end-1c")])
        self.assertEqual(widget.inserts[1], ("end", "확정 문장\n", FINAL_TEXT_TAG))
        self.assertFalse(window._transcript_partial_active)


    def test_load_window_geometry_uses_default_when_saved_value_missing(self) -> None:
        class Root:
            def winfo_vrootwidth(self) -> int:
                return 1920

            def winfo_vrootheight(self) -> int:
                return 1080

            def winfo_screenwidth(self) -> int:
                return 1920

            def winfo_screenheight(self) -> int:
                return 1080

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {}}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                geometry = _load_window_geometry(path, "whisperWindowGeometry", Root())

        self.assertEqual(geometry, DEFAULT_WINDOW_GEOMETRY_META["whisperWindowGeometry"])
        self.assertIn("window geometry defaulted: key=whisperWindowGeometry", stdout.getvalue())

    def test_load_window_geometry_uses_saved_value_before_default(self) -> None:
        class Root:
            def winfo_vrootwidth(self) -> int:
                return 1920

            def winfo_vrootheight(self) -> int:
                return 1080

            def winfo_screenwidth(self) -> int:
                return 1920

            def winfo_screenheight(self) -> int:
                return 1080

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"whisperWindowGeometry": "820x460+120+80"}}), encoding="utf-8")

            geometry = _load_window_geometry(path, "whisperWindowGeometry", Root())

        self.assertEqual(geometry, "820x460+120+80")

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

    def test_window_restore_extent_allows_secondary_monitor_coordinates(self) -> None:
        class Root:
            def winfo_screenwidth(self) -> int:
                return 1920

            def winfo_screenheight(self) -> int:
                return 1080

        width, height = _window_restore_extent(Root())

        self.assertEqual((width, height), (3840, 2160))
        self.assertEqual(
            _sanitize_window_geometry("780x420+2912+627", width, height),
            "780x420+2912+627",
        )

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

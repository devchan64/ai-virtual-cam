import contextlib
import io
import json
import tempfile
import unittest
import queue
from unittest import mock
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

    def test_transcript_current_geometry_uses_window_manager_geometry(self) -> None:
        root = SimpleNamespace(
            update_idletasks=lambda: None,
            geometry=lambda: "886x608+2538+510",
            winfo_geometry=lambda: "886x608+2538+547",
        )
        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._root = root

        self.assertEqual(window._current_geometry(), "886x608+2538+510")

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
        self.assertEqual(_window_title("transcript", language), "ai-virtual-cam 오디오 AI 전사")
        self.assertEqual(_window_title("translation", language), "ai-virtual-cam 오디오 AI 번역")
        self.assertEqual(_window_title("sttStatus", language), "ai-virtual-cam 오디오 AI STT 상태")

    def test_window_titles_fallback_to_english_for_unknown_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"language": "zh"}}), encoding="utf-8")

            language = _load_ui_language(path)

        self.assertEqual(language, "en")
        self.assertEqual(_window_title("transcript", language), "ai-virtual-cam Audio AI Transcript")
        self.assertEqual(_window_title("translation", language), "ai-virtual-cam Audio AI Translation")
        self.assertEqual(_window_title("sttStatus", language), "ai-virtual-cam Audio AI STT Status")

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


    def test_line_numbers_update_on_display_row_axis(self) -> None:
        class FakeContentText:
            def __init__(self) -> None:
                self.current = "1.0"

            def index(self, index: str) -> str:
                if index == "@0,0":
                    return "1.0"
                if index.endswith("+1line"):
                    line = int(index.split(".", 1)[0]) + 1
                    return f"{line}.0"
                return index

            def dlineinfo(self, index: str):
                line = int(index.split(".", 1)[0])
                if line > 102:
                    return None
                return (0, (line - 1) * 18, 100, 18, 0)

        class FakeLineNumberCanvas:
            def __init__(self) -> None:
                self.deletes = []
                self.texts = []
                self.configures = []

            def configure(self, **kwargs) -> None:
                self.configures.append(kwargs)

            def delete(self, target: str) -> None:
                self.deletes.append(target)

            def create_text(self, x: int, y: int, **kwargs) -> None:
                self.texts.append((x, y, kwargs))

        content = FakeContentText()
        line_numbers = FakeLineNumberCanvas()
        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._line_number_widgets = {content: line_numbers}

        window._update_line_numbers(content)

        self.assertEqual(line_numbers.deletes, ["all"])
        self.assertIn({"width": 43}, line_numbers.configures)
        self.assertEqual(line_numbers.texts[0], (37, 0, {"anchor": "ne", "text": "1", "fill": "#777777"}))
        self.assertEqual(line_numbers.texts[101], (37, 1818, {"anchor": "ne", "text": "102", "fill": "#777777"}))

    def test_copy_all_uses_transcript_text_without_line_numbers(self) -> None:
        class FakeRoot:
            def __init__(self) -> None:
                self.clipboard = ""

            def clipboard_clear(self) -> None:
                self.clipboard = ""

            def clipboard_append(self, text: str) -> None:
                self.clipboard += text

        class FakeContentText:
            def get(self, start: str, end: str) -> str:
                return "전사 첫 줄\n전사 둘째 줄"

        root = FakeRoot()
        content = FakeContentText()
        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._root = root
        window._text = content
        window._context_text = None

        window._copy_all(content)

        self.assertEqual(root.clipboard, "전사 첫 줄\n전사 둘째 줄")


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

    def test_load_stt_status_window_geometry_uses_default_when_saved_value_missing(self) -> None:
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
                geometry = _load_window_geometry(path, "whisperSttStatusWindowGeometry", Root())

        self.assertEqual(geometry, DEFAULT_WINDOW_GEOMETRY_META["whisperSttStatusWindowGeometry"])
        self.assertIn("window geometry defaulted: key=whisperSttStatusWindowGeometry", stdout.getvalue())

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

    def test_modal_output_allows_results_and_errors(self) -> None:
        self.assertTrue(_is_modal_output_event(TranscriptEvent("transcript", "hello")))
        self.assertTrue(_is_modal_output_event(TranscriptEvent("translation", "안녕")))
        self.assertFalse(_is_modal_output_event(TranscriptEvent("status", "loading")))
        self.assertTrue(_is_modal_output_event(TranscriptEvent("error", "failed")))
        self.assertFalse(_is_modal_output_event(TranscriptEvent("transcript", "hidden", display=False)))

    def test_polls_transcript_events_to_stt_status_window(self) -> None:
        class FakeRoot:
            def after(self, delay, callback):
                self.delay = delay
                self.callback = callback

        class FakeText:
            def __init__(self) -> None:
                self.lines = []

            def insert(self, index, text, tag=None) -> None:
                self.lines.append((index, text, tag))

            def delete(self, start, end) -> None:
                self.lines.append((start, end, "DELETE"))

            def see(self, index) -> None:
                self.lines.append((index, "SEE"))

        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._stt_status_text = FakeText()
        window._text = FakeText()
        window._translation_text = None
        window._transcript_partial_active = False
        window._translation_partial_active = False
        window._root = FakeRoot()
        window._events = queue.Queue()
        window._update_line_numbers = lambda _widget: None

        window._events.put(TranscriptEvent("transcript", "안녕하세요", display=True, final=True))
        window._poll_events()

        self.assertIn(("end", "[001] 안녕하세요\n", FINAL_TEXT_TAG), window._stt_status_text.lines)
        self.assertIn(("end", "안녕하세요\n", FINAL_TEXT_TAG), window._text.lines)


    def test_stt_status_window_numbers_each_final_transcript(self) -> None:
        class FakeRoot:
            def after(self, delay, callback):
                self.delay = delay
                self.callback = callback

        class FakeText:
            def __init__(self) -> None:
                self.lines = []

            def insert(self, index, text, tag=None) -> None:
                self.lines.append((index, text, tag))

            def delete(self, start, end) -> None:
                self.lines.append((start, end, "DELETE"))

            def see(self, index) -> None:
                self.lines.append((index, "SEE"))

        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._stt_status_text = FakeText()
        window._text = FakeText()
        window._translation_text = None
        window._transcript_partial_active = False
        window._translation_partial_active = False
        window._root = FakeRoot()
        window._events = queue.Queue()
        window._update_line_numbers = lambda _widget: None
        window._stt_status_run_index = 0

        window._events.put(TranscriptEvent("transcript", "첫 문장", display=True, final=True))
        window._events.put(TranscriptEvent("transcript", "둘째 문장", display=True, final=True))
        window._poll_events()

        self.assertIn(("end", "[001] 첫 문장\n", FINAL_TEXT_TAG), window._stt_status_text.lines)
        self.assertIn(("end", "[002] 둘째 문장\n", FINAL_TEXT_TAG), window._stt_status_text.lines)

    def test_partial_transcript_not_shown_in_stt_status_window(self) -> None:
        class FakeRoot:
            def after(self, delay, callback):
                self.delay = delay
                self.callback = callback

        class FakeText:
            def __init__(self) -> None:
                self.lines = []

            def insert(self, index, text, tag=None) -> None:
                self.lines.append((index, text, tag))

            def delete(self, start, end) -> None:
                self.lines.append((start, end, "DELETE"))

            def see(self, index) -> None:
                self.lines.append((index, "SEE"))

        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._stt_status_text = FakeText()
        window._text = FakeText()
        window._translation_text = None
        window._transcript_partial_active = False
        window._translation_partial_active = False
        window._root = FakeRoot()
        window._events = queue.Queue()
        window._update_line_numbers = lambda _widget: None

        window._events.put(TranscriptEvent("transcript", "임시 문장", display=True, final=False))
        window._poll_events()

        self.assertEqual(window._stt_status_text.lines, [])
        self.assertNotIn(("end", "임시 문장", PARTIAL_TEXT_TAG), window._text.lines)


    def test_status_events_not_forwarded_to_stt_status_window(self) -> None:
        class FakeRoot:
            def after(self, delay, callback):
                self.delay = delay
                self.callback = callback

        class FakeText:
            def __init__(self) -> None:
                self.lines = []

            def insert(self, index, text, tag=None) -> None:
                self.lines.append((index, text, tag))

            def delete(self, start, end) -> None:
                self.lines.append((start, end, "DELETE"))

            def see(self, index) -> None:
                self.lines.append((index, "SEE"))

        window = WhisperTranscriptWindow.__new__(WhisperTranscriptWindow)
        window._stt_status_text = FakeText()
        window._text = FakeText()
        window._translation_text = None
        window._transcript_partial_active = False
        window._translation_partial_active = False
        window._root = FakeRoot()
        window._events = queue.Queue()
        window._update_line_numbers = lambda _widget: None

        window._events.put(TranscriptEvent("status", "STT 모델 로딩 완료"))
        window._events.put(TranscriptEvent("status", "Whisper 문장 진단: chunk=3 completed=1 final=1"))
        window._events.put(TranscriptEvent("status", "Whisper 전사 요청: chunk=4 samples=16000"))
        window._events.put(TranscriptEvent("status", "Whisper 성능: chunk=4 step=1.5"))
        window._poll_events()

        self.assertEqual(window._stt_status_text.lines, [])


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

    def test_preloads_sentence_boundary_model_before_transcribe_loop_for_configured_language(self) -> None:
        worker = WhisperTranscriptWorker(
            WhisperConfig.from_dict({"inputDevice": "default", "language": "zh"}),
            queue.Queue(),
        )

        with mock.patch.object(worker, "_sync_sentence_boundary_detector") as sync_detector:
            worker._preload_sentence_boundary_detector()

        sync_detector.assert_called_once_with("zh")

    def test_filters_low_confidence_segments(self) -> None:
        worker = WhisperTranscriptWorker(WhisperConfig.from_dict({"inputDevice": "default"}), queue.Queue())
        segments = [
            SimpleNamespace(text=" 정상 문장 ", avg_logprob=-0.2, no_speech_prob=0.1),
            SimpleNamespace(text=" 무음 환각 ", avg_logprob=-0.2, no_speech_prob=0.9),
            SimpleNamespace(text=" 저신뢰 ", avg_logprob=-1.4, no_speech_prob=0.1),
        ]

        texts, rejected, boundary_confidence = worker._accepted_segment_texts(segments)

        self.assertEqual(texts, ["정상 문장"])
        self.assertEqual(len(rejected), 2)
        self.assertIn("no_speech", rejected[0])
        self.assertIn("low_logprob", rejected[1])
        self.assertIsNotNone(boundary_confidence)


    def test_accepts_long_chinese_segment_with_borderline_no_speech(self) -> None:
        worker = WhisperTranscriptWorker(WhisperConfig.from_dict({"inputDevice": "default", "language": "zh"}), queue.Queue())
        segments = [
            SimpleNamespace(
                text="到我和朋友兩個人臨陣起手直接唱陰謀歌好吧不陰謀的完全不點阻擋",
                avg_logprob=-0.2,
                no_speech_prob=0.86,
            ),
        ]

        texts, rejected, boundary_confidence = worker._accepted_segment_texts(segments)

        self.assertEqual(texts, [segments[0].text])
        self.assertEqual(rejected, [])
        self.assertIsNotNone(boundary_confidence)

    def test_rejects_short_chinese_segment_with_high_no_speech(self) -> None:
        worker = WhisperTranscriptWorker(WhisperConfig.from_dict({"inputDevice": "default", "language": "zh"}), queue.Queue())
        segments = [SimpleNamespace(text="片。", avg_logprob=-0.2, no_speech_prob=0.86)]

        texts, rejected, boundary_confidence = worker._accepted_segment_texts(segments)

        self.assertEqual(texts, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("no_speech", rejected[0])
        self.assertIsNone(boundary_confidence)

    def test_rejects_repeated_short_transcripts(self) -> None:
        worker = WhisperTranscriptWorker(WhisperConfig.from_dict({"inputDevice": "default"}), queue.Queue())
        worker._remember_transcript("다음 영상에서 만나요.")
        worker._remember_transcript("다음 영상에서 만나요.")

        self.assertTrue(worker._is_repeated_hallucination("다음 영상에서 만나요."))
        self.assertFalse(worker._is_repeated_hallucination("이 문장은 충분히 긴 새로운 설명이라 반복으로 보지 않습니다"))


if __name__ == "__main__":
    unittest.main()

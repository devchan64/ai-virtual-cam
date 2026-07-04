import queue
import types
import unittest

from src.app.dictation.window import WhisperTranscriptWorker
from src.app.dictation.window_events import TranscriptEvent


class DictationWindowEventTest(unittest.TestCase):
    def test_transcript_event_keeps_segment_id(self) -> None:
        event = TranscriptEvent("translation", "번역", segment_id=7)

        self.assertEqual(event.segment_id, 7)

    def test_worker_emit_preserves_segment_id_for_transcript_and_translation(self) -> None:
        events: queue.Queue[TranscriptEvent] = queue.Queue()
        cfg = types.SimpleNamespace(
            sentenceBoundaryBackend="sat",
            sentenceBoundaryModel="sat-3l-sm",
            language="ko",
        )
        worker = WhisperTranscriptWorker(cfg, events)

        worker._emit("transcript", "원문", log_text="[ko#3] 원문", segment_id=3)
        worker._emit("translation", "translation", log_text="[ko->en#3] translation", segment_id=3)

        transcript = events.get_nowait()
        translation = events.get_nowait()
        self.assertEqual(transcript.segment_id, 3)
        self.assertEqual(translation.segment_id, 3)
        self.assertEqual(transcript.kind, "transcript")
        self.assertEqual(translation.kind, "translation")


if __name__ == "__main__":
    unittest.main()

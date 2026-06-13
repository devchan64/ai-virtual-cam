import unittest

from src.app.stt_model import SttSegment, funasr_generated_text


class SttModelTest(unittest.TestCase):
    def test_funasr_generated_text_reads_list_dict_response(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "你好世界"}]), "你好世界")

    def test_funasr_generated_text_joins_multiple_items(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "你好"}, {"text": "世界"}]), "你好 世界")

    def test_stt_segment_defaults_are_accepted_by_whisper_filters(self) -> None:
        segment = SttSegment("你好世界")

        self.assertEqual(segment.text, "你好世界")
        self.assertEqual(segment.avg_logprob, 0.0)
        self.assertEqual(segment.no_speech_prob, 0.0)


if __name__ == "__main__":
    unittest.main()

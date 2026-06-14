import unittest

from src.app.stt_model import SttSegment, qwen_asr_generated_text


class SttModelTest(unittest.TestCase):
    def test_qwen_asr_generated_text_reads_object_response(self) -> None:
        class Result:
            text = "你好世界"
            language = "Chinese"

        self.assertEqual(qwen_asr_generated_text([Result()], fallback_language="zh"), ("你好世界", "zh"))

    def test_qwen_asr_generated_text_reads_dict_response(self) -> None:
        self.assertEqual(
            qwen_asr_generated_text([{"text": "hello", "language": "English"}], fallback_language="zh"),
            ("hello", "en"),
        )

    def test_stt_segment_defaults_are_accepted_by_whisper_filters(self) -> None:
        segment = SttSegment("你好世界")

        self.assertEqual(segment.text, "你好世界")
        self.assertEqual(segment.avg_logprob, 0.0)
        self.assertEqual(segment.no_speech_prob, 0.0)


if __name__ == "__main__":
    unittest.main()

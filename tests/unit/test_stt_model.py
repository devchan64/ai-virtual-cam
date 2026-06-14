import unittest

from src.app.stt_model import Qwen3AsrVllmStreamingSttModel, SttSegment, qwen_asr_generated_text


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

    def test_qwen_streaming_load_error_explains_shared_venv_conflict(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "공유 .venv") as ctx:
            Qwen3AsrVllmStreamingSttModel("qwen3-asr-0.6b", "cuda", "float16", "zh")

        self.assertIn("qwen3-asr-transformers", str(ctx.exception))
        self.assertNotIn("AVC_INSTALL_QWEN_VLLM=1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import unittest

from src.app.stt_model import FunasrSttModel, SttSegment, funasr_generated_text, qwen_asr_generated_text


class SttModelTest(unittest.TestCase):
    def test_funasr_generated_text_reads_list_dict_response(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "你好世界"}]), "你好世界")

    def test_funasr_generated_text_joins_multiple_items(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "你好"}, {"text": "世界"}]), "你好 世界")

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

    def test_funasr_transcribe_suppresses_generate_progress_output(self) -> None:
        class NoisyModel:
            def generate(self, input, fs):
                print("0%| funasr progress should not be logged")
                return [{"text": "你好世界"}]

        emitted = []
        model = FunasrSttModel.__new__(FunasrSttModel)
        model.backend = "funasr-paraformer"
        model.model_name = "paraformer-zh"
        model.resolved_model_name = "resolved"
        model.device = "cuda"
        model.language = "zh"
        model._status_callback = emitted.append
        model._model = NoisyModel()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            segments, info = model.transcribe([0.0])

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual([segment.text for segment in segments], ["你好世界"])
        self.assertEqual(info.language, "zh")
        self.assertEqual(emitted, [])


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

from src.app.stt_model import FunasrSttModel, SttSegment, funasr_generated_text, qwen_asr_generated_text


class SttModelTest(unittest.TestCase):
    def test_funasr_generated_text_reads_list_dict_response(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "你好世界"}]), "你好世界")

    def test_funasr_generated_text_joins_multiple_items(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "你好"}, {"text": "世界"}]), "你好 世界")

    def test_funasr_generated_text_strips_sensevoice_control_tokens(self) -> None:
        self.assertEqual(
            funasr_generated_text([{"text": "<|zh|><|happy|><|bgm|><|woitn|>你跟大家说再见。"}]),
            "你跟大家说再见。",
        )

    def test_funasr_generated_text_drops_control_token_only_result(self) -> None:
        self.assertEqual(funasr_generated_text([{"text": "<|zh|><|neutral|><|bgm|><|woitn|>"}]), "")

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

    def test_funasr_loader_uses_local_cache_path(self) -> None:
        automodel = mock.Mock(return_value=mock.Mock())
        fake_module = type("FakeFunasr", (), {"AutoModel": automodel})()
        local_path = Path("/tmp/funasr-cache/iic/SenseVoiceSmall")

        with mock.patch.dict("sys.modules", {"funasr": fake_module}):
            with mock.patch("src.app.stt_model.require_funasr_model_cache_path", return_value=local_path):
                FunasrSttModel(
                    backend="funasr-sensevoice",
                    model_name="iic/SenseVoiceSmall",
                    device="cuda",
                    language="zh",
                    status_callback=lambda _message: None,
                )

        automodel.assert_called_once_with(model=str(local_path), device="cuda", disable_update=True)

    def test_funasr_streaming_backend_requires_streaming_model(self) -> None:
        fake_module = type("FakeFunasr", (), {"AutoModel": mock.Mock()})()

        with mock.patch.dict("sys.modules", {"funasr": fake_module}):
            with self.assertRaisesRegex(RuntimeError, "paraformer-zh-streaming"):
                FunasrSttModel(
                    backend="funasr-paraformer-streaming",
                    model_name="paraformer-zh",
                    device="cuda",
                    language="zh",
                )


if __name__ == "__main__":
    unittest.main()

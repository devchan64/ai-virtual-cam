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

    def test_qwen_streaming_model_feeds_incremental_audio(self) -> None:
        class State:
            text = ""
            language = "Chinese"

        class FakeModel:
            def __init__(self) -> None:
                self.initialized_with = None
                self.streamed = []

            def init_streaming_state(self, **kwargs):
                self.initialized_with = kwargs
                return State()

            def streaming_transcribe(self, pcm16k, state):
                self.streamed.append(pcm16k.tolist())
                state.text = "你好"
                return state

        model = Qwen3AsrVllmStreamingSttModel.__new__(Qwen3AsrVllmStreamingSttModel)
        model.model_name = "qwen3-asr-0.6b"
        model.resolved_model_name = "Qwen/Qwen3-ASR-0.6B"
        model.device = "cuda"
        model.compute_type = "float16"
        model.language = "zh"
        model._state = None
        model._stream_context = ""
        model._model = FakeModel()

        import numpy as np

        segments, info = model.transcribe(
            np.array([0.0, 0.1, 0.2], dtype=np.float32),
            language="zh",
            stream_audio=np.array([0.2, 0.3], dtype=np.float32),
            stream_chunk_seconds=1.5,
        )

        self.assertEqual([segment.text for segment in segments], ["你好"])
        self.assertEqual(info.language, "zh")
        self.assertEqual(model._model.initialized_with["language"], "Chinese")
        self.assertEqual(model._model.initialized_with["chunk_size_sec"], 1.5)
        self.assertEqual(model._model.streamed, [[0.20000000298023224, 0.30000001192092896]])


if __name__ == "__main__":
    unittest.main()

import unittest

from src.app.whisper_window import _new_text_delta, _split_completed_sentences, _stable_window_text


class WhisperSlidingWindowTextTest(unittest.TestCase):
    def test_stable_window_holds_tail_by_commit_lag_ratio(self) -> None:
        self.assertEqual(
            _stable_window_text("Folks I was one of the first people", 1.0, 4.0),
            "Folks I was one of the",
        )


    def test_sentence_split_keeps_incomplete_tail_pending(self) -> None:
        completed, pending = _split_completed_sentences("", "Hello there. This is still")

        self.assertEqual(completed, ["Hello there."])
        self.assertEqual(pending, "This is still")

    def test_sentence_split_joins_pending_with_new_text(self) -> None:
        completed, pending = _split_completed_sentences("This is", "done! Next")

        self.assertEqual(completed, ["This is done!"])
        self.assertEqual(pending, "Next")

    def test_sentence_split_supports_cjk_sentence_marks(self) -> None:
        completed, pending = _split_completed_sentences("", "안녕하세요. 다음 문장")

        self.assertEqual(completed, ["안녕하세요."])
        self.assertEqual(pending, "다음 문장")

    def test_delta_outputs_only_new_overlap_suffix(self) -> None:
        committed = "Folks I was one of the first people"
        stable = "the first people in the United States to take delivery"

        self.assertEqual(_new_text_delta(committed, stable), "in the United States to take delivery")

    def test_delta_ignores_already_committed_text(self) -> None:
        committed = "다음 영상에서 만나요"

        self.assertEqual(_new_text_delta(committed, "다음 영상에서 만나요"), "")

    def test_delta_handles_text_without_spaces(self) -> None:
        committed = "你好世界"
        stable = "世界今天很好"

        self.assertEqual(_new_text_delta(committed, stable), "今天很好")


if __name__ == "__main__":
    unittest.main()

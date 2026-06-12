import unittest

from src.app.whisper_window import _diagnostic_tail, _forced_sentence_reason, _new_text_delta, _sentence_output_delta, _sentence_end_count, _split_completed_sentences, _stable_window_text


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


    def test_sentence_diagnostics_count_end_marks(self) -> None:
        self.assertEqual(_sentence_end_count("Hello. What? Done!"), 3)

    def test_sentence_diagnostic_tail_is_bounded(self) -> None:
        self.assertEqual(_diagnostic_tail("short text"), "'short text'")
        self.assertTrue(_diagnostic_tail("a" * 120).startswith("'..."))


    def test_sentence_split_ignores_decimal_periods(self) -> None:
        completed, pending = _split_completed_sentences("", "It costs $9.99 per month. Next")

        self.assertEqual(completed, ["It costs $9.99 per month."])
        self.assertEqual(pending, "Next")
        self.assertEqual(_sentence_end_count("It costs $9.99 per month."), 1)

    def test_forced_sentence_reason_uses_pending_limits(self) -> None:
        self.assertEqual(_forced_sentence_reason("still pending", 6), "pending_chunks")
        self.assertEqual(_forced_sentence_reason("x" * 90, 1), "pending_chars")
        self.assertEqual(_forced_sentence_reason("short", 1), "")


    def test_sentence_output_delta_ignores_committed_sentence_with_punctuation_changes(self) -> None:
        committed = "one of my favorite floor mat sets for this purpose is from today's sponsor last fit"
        sentence = "One of my favorite floor mat sets for this purpose is from today's sponsor, Last Fit."

        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_keeps_new_suffix_after_overlap(self) -> None:
        committed = "i've had these mats for a while now and they have done an excellent job of protecting"
        sentence = "I've had these mats for a while now, and they have done an excellent job of protecting the carpet underneath them."

        self.assertEqual(_sentence_output_delta(committed, sentence), "the carpet underneath them")

    def test_sentence_output_delta_keeps_distinct_sentence(self) -> None:
        sentence = "Here they are after not vacuuming for a couple weeks."

        self.assertEqual(_sentence_output_delta("already committed text", sentence), sentence)

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

import unittest

from src.app.whisper_window import _collapse_adjacent_repeated_phrases, _diagnostic_tail, _forced_sentence_reason, _new_text_delta, _pending_new_text_combined, _sentence_output_delta, _sentences_are_revisions, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


class WhisperSlidingWindowTextTest(unittest.TestCase):
    def test_stable_window_holds_tail_by_commit_lag_ratio(self) -> None:
        self.assertEqual(
            _stable_window_text("Folks I was one of the first people", 1.0, 4.0),
            "Folks I was one of the",
        )

    def test_collapse_adjacent_repeated_phrases(self) -> None:
        self.assertEqual(
            _collapse_adjacent_repeated_phrases(
                "job there we'll find out how job there we'll find out how FSD handles"
            ),
            "job there we'll find out how FSD handles",
        )

    def test_collapse_adjacent_repeated_phrases_keeps_non_adjacent_repetition(self) -> None:
        self.assertEqual(
            _collapse_adjacent_repeated_phrases("very nice no braking for the bird very good"),
            "very nice no braking for the bird very good",
        )

    def test_sentence_revision_detects_updated_completed_sentence(self) -> None:
        self.assertTrue(
            _sentences_are_revisions(
                "Now it is telling me.",
                "Now it is telling me 52 second.",
            )
        )
        self.assertEqual(
            _prefer_sentence_revision("Now it is telling me.", "Now it is telling me 52 second."),
            "Now it is telling me 52 second.",
        )

    def test_sentence_revision_rejects_distinct_sentences(self) -> None:
        self.assertFalse(_sentences_are_revisions("Tesla app.", "It was going a little fast."))


    def test_sentence_split_keeps_incomplete_tail_pending(self) -> None:
        completed, pending = _split_completed_sentences("", "Hello there. This is still")

        self.assertEqual(completed, ["Hello there."])
        self.assertEqual(pending, "This is still")

    def test_sentence_split_joins_pending_with_new_text(self) -> None:
        completed, pending = _split_completed_sentences("This is", "done! Next")

        self.assertEqual(completed, ["This is done!"])
        self.assertEqual(pending, "Next")

    def test_sentence_split_drops_short_pending_when_new_text_restarts_sentence(self) -> None:
        completed, pending = _split_completed_sentences(
            "Because",
            "But the speed profiles is the most important setting because this is what you're telling Tesla how to drive.",
        )

        self.assertEqual(
            completed,
            ["But the speed profiles is the most important setting because this is what you're telling Tesla how to drive."],
        )
        self.assertEqual(pending, "")

    def test_pending_new_text_combines_by_overlap_without_duplicate(self) -> None:
        self.assertEqual(
            _pending_new_text_combined("Because if you", "if you didn't know,"),
            "Because if you didn't know,",
        )

    def test_sentence_pending_can_accumulate_long_fast_speech(self) -> None:
        pending = "this is a quick sentence fragment that keeps going without punctuation and should not be forced too early"

        self.assertEqual(_forced_sentence_reason(pending, 4), "")

    def test_sentence_split_completes_previous_pending_text(self) -> None:
        completed, pending = _split_completed_sentences("So it is", "now reversing.")

        self.assertEqual(completed, ["So it is now reversing."])
        self.assertEqual(pending, "")

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
        self.assertEqual(_forced_sentence_reason("still pending", 10), "pending_chunks")
        self.assertEqual(_forced_sentence_reason(("x" * 180) + ".", 1), "pending_chars")
        self.assertEqual(_forced_sentence_reason("x" * 180, 1), "")
        self.assertEqual(_forced_sentence_reason("short", 1), "")

    def test_forced_sentence_reason_adapts_to_slow_speech(self) -> None:
        slow_pending = "this sentence is spoken slowly across several updates"

        self.assertEqual(_forced_sentence_reason(slow_pending, 4), "slow_pending")

    def test_forced_sentence_reason_does_not_force_fast_speech_early(self) -> None:
        fast_pending = "this sentence is spoken quickly and keeps accumulating many words across a short number of updates"

        self.assertEqual(_forced_sentence_reason(fast_pending, 4), "")


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


    def test_delta_uses_internal_overlap_for_sliding_window_revisions(self) -> None:
        committed = "Not comfortable when it went over to that railroad crossing. It was going a little fast. Didn't"
        stable = "go not comfortable when it went over to that railroad crossing it was going a little fast didn't like that so I'm"

        self.assertEqual(_new_text_delta(committed, stable), "like that so I'm")

    def test_delta_suppresses_stable_text_already_covered_by_history(self) -> None:
        committed = "Now it is telling me. 52 second. Oh my goodness. Is it true?"
        stable = "52 second. Oh my goodness. Is it true?"

        self.assertEqual(_new_text_delta(committed, stable), "")


if __name__ == "__main__":
    unittest.main()

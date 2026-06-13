import unittest

from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector
from src.app.whisper_window import _collapse_adjacent_repeated_phrase_details, _collapse_adjacent_repeated_phrases, _diagnostic_tail, _forced_sentence_reason, _pending_overrun_reason, _new_text_delta, _pending_new_text_combined, _sentence_max_age_chunks, _sentence_output_delta, _sentence_required_confirmations, _sentences_are_revisions, _should_age_staged_sentence, _should_translate_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


class WhisperSentenceForcingTest(unittest.TestCase):
    def test_forced_sentence_reason_uses_boundary_or_slow_pending_signals(self) -> None:
        self.assertEqual(_forced_sentence_reason("still pending", 10), "")
        self.assertEqual(_forced_sentence_reason(("x" * 180) + ".", 1), "pending_chars")
        self.assertEqual(_forced_sentence_reason("x" * 180, 1), "")
        self.assertEqual(_forced_sentence_reason("short", 1), "")

    def test_forced_sentence_reason_adapts_to_slow_speech(self) -> None:
        slow_pending = "this sentence is spoken slowly across several updates"

        self.assertEqual(_forced_sentence_reason(slow_pending, 4), "slow_pending")

    def test_forced_sentence_reason_does_not_force_incomplete_tail_from_log(self) -> None:
        pending = "The robot transmits ultrasonic signals in real time and feeds that data to an embedded AI processor, which utilizes dual ultrasonic sensors to"

        self.assertEqual(_forced_sentence_reason(pending, 8), "")

    def test_forced_sentence_reason_does_not_force_pending_chunks_with_incomplete_that_it_tail_from_log(self) -> None:
        pending = "So it may seem a bit backwards, but I promise you keeping it on percentage gives you more trust in it and gives you more of a feel how much range you have then keeping it on miles and always seeing that it"

        self.assertEqual(_forced_sentence_reason(pending, 10), "")

    def test_forced_sentence_reason_does_not_force_pending_chunks_with_incomplete_you_can_tail_from_log(self) -> None:
        pending = "might not be right now you can tap in this area here to pull up a bigger view of the map and it s just like an ipad you can use two fingers to zoom out to zoom in you can"

        self.assertEqual(_forced_sentence_reason(pending, 10), "")

    def test_forced_sentence_reason_does_not_force_pending_chunks_with_incomplete_if_tail_from_log(self) -> None:
        pending = "but the fast superchargers you want to enable the three bolts and that ll show you all the fast superchargers you can also view a live weather overlay for the next four hours so if"

        self.assertEqual(_forced_sentence_reason(pending, 10), "")

    def test_forced_sentence_reason_does_not_force_fast_speech_early(self) -> None:
        fast_pending = "this sentence is spoken quickly and keeps accumulating many words across a short number of updates"

        self.assertEqual(_forced_sentence_reason(fast_pending, 4), "")

    def test_forced_sentence_reason_does_not_force_numeric_range_start_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 167-171.
        pending = "charge at a supercharger quite honestly you can get from 0"

        self.assertEqual(_forced_sentence_reason(pending, 4), "")


    def test_pending_overrun_tracks_long_unpunctuated_english_from_log(self) -> None:
        pending = (
            "so as far as SpaceX the reason that there hasn't been a huge number of a big improvement "
            "in in the space industry because it is there's such a significant amount of capital that's "
            "needed to start a rocket company, and it's a very difficult technical challenge and the number "
            "of people that really understand rocketry in"
        )

        self.assertEqual(_forced_sentence_reason(pending, 13), "")
        self.assertEqual(_pending_overrun_reason(pending, 13), "long_no_boundary")

    def test_pending_overrun_reports_completed_text_that_should_force(self) -> None:
        pending = (
            "this pending text has grown beyond the normal pending size and now it finally has a sentence "
            "ending marker that can be committed safely enough for real-time translation while still "
            "preserving enough context for downstream translation quality checks."
        )

        self.assertEqual(_forced_sentence_reason(pending, 8), "pending_chars")
        self.assertEqual(_pending_overrun_reason(pending, 8), "with_end_mark")

    def test_forced_sentence_requires_extra_confirmation_and_age(self) -> None:
        self.assertGreater(_sentence_required_confirmations(True), _sentence_required_confirmations(False))
        self.assertGreater(_sentence_max_age_chunks(True), _sentence_max_age_chunks(False))


if __name__ == "__main__":
    unittest.main()

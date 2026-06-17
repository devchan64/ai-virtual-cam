import unittest

from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector
from src.app.dictation_window import _diagnostic_tail, _pending_overrun_reason, _new_text_delta, _sentence_max_age_chunks, _sentence_output_delta, _sentence_required_confirmations, _sentences_are_revisions, _should_age_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text
from src.app.dictation_transcript_logic import _should_finalize_before_replacement


class WhisperSentenceForcingTest(unittest.TestCase):
    def test_pending_overrun_tracks_long_unpunctuated_english_from_log(self) -> None:
        pending = (
            "so as far as SpaceX the reason that there hasn't been a huge number of a big improvement "
            "in in the space industry because it is there's such a significant amount of capital that's "
            "needed to start a rocket company, and it's a very difficult technical challenge and the number "
            "of people that really understand rocketry in"
        )

        self.assertEqual(_pending_overrun_reason(pending, 13), "long_no_boundary")

    def test_pending_overrun_reports_completed_text_with_end_mark(self) -> None:
        pending = (
            "this pending text has grown beyond the normal pending size and now it finally has a sentence "
            "ending marker that can be committed safely enough for real-time translation while still "
            "preserving enough context for downstream translation quality checks."
        )

        self.assertEqual(_pending_overrun_reason(pending, 8), "with_end_mark")

    def test_cjk_completed_sentence_does_not_finalize_before_replacement_after_first_observation(self) -> None:
        sentence = "现在已经到了凤恩寺站，七号出口就会直接到COEX。"

        self.assertFalse(
            _should_finalize_before_replacement(
                sentence,
                "zh",
                staged_confirmations=1,
                staged_age=0,
                sentence_finalize_age=2,
                staged_forced=False,
            )
        )
        self.assertFalse(
            _should_finalize_before_replacement(
                "这里，COEX",
                "zh",
                staged_confirmations=1,
                staged_age=0,
                sentence_finalize_age=2,
                staged_forced=False,
            )
        )


if __name__ == "__main__":
    unittest.main()

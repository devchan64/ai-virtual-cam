import unittest
from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector, split_punctuated_text
from src.app.dictation_window import _collapse_adjacent_repeated_phrase_details, _collapse_adjacent_repeated_phrases, _diagnostic_tail, _forced_sentence_reason, _new_text_delta, _sentence_max_age_chunks, _sentence_output_delta, _sentence_required_confirmations, _sentences_are_revisions, _should_age_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


class WhisperSentenceBoundaryTest(unittest.TestCase):
    def test_sentence_split_keeps_incomplete_tail_pending(self) -> None:
        completed, pending = _split_completed_sentences("", "Hello there. This is still")

        self.assertEqual(completed, ["Hello there."])
        self.assertEqual(pending, "This is still")

    def test_sentence_split_joins_pending_with_new_text(self) -> None:
        completed, pending = _split_completed_sentences("This is", "done! Next")

        self.assertEqual(completed, ["This is done!"])
        self.assertEqual(pending, "Next")

    def test_sentence_boundary_soft_splits_long_english_restart_without_punctuation(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in",
            "But now let's dive into some of the settings you have to know",
            "en",
        )

        self.assertEqual(result.completed, ["And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in"])
        self.assertEqual(result.pending, "But now let's dive into some of the settings you have to know")
        self.assertEqual(result.soft_boundary_count, 1)
        self.assertEqual(result.end_mark_count, 0)
        self.assertEqual(result.right_context_start_count, 1)

    def test_sentence_boundary_soft_splits_are_disabled_under_low_model_confidence(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in",
            "But now let's dive into some of the settings you have to know",
            "en",
            boundary_confidence=0.10,
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(
            result.pending,
            "And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in But now let's dive into some of the settings you have to know",
        )
        self.assertEqual(result.soft_boundary_count, 0)

    def test_sentence_boundary_soft_splits_remain_when_confidence_high(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in",
            "But now let's dive into some of the settings you have to know",
            "en",
            boundary_confidence=0.85,
        )

        self.assertEqual(result.completed, ["And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in"])
        self.assertEqual(result.pending, "But now let's dive into some of the settings you have to know")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_soft_split_is_not_used_for_korean(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "이 문장은 아직 끝나지 않았고 다음 내용이 계속 이어지고 있어서 경계를 확정하면 안 됩니다",
            "그런데 새 문장이 시작되는 것처럼 보여도 한국어 휴리스틱은 아직 적용하지 않습니다",
            "ko",
        )

        self.assertEqual(result.completed, [])
        self.assertIn("그런데 새 문장이", result.pending)

    def test_sentence_boundary_keeps_short_english_pending_without_restart_signal(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "This gives",
            "you a live camera option",
            "en",
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(result.pending, "This gives you a live camera option")

    def test_sentence_boundary_does_not_soft_split_lowercase_this_inside_phrase_from_log(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "If you enjoyed this video, please give it a like and subscribe for more Tesla and tech videos and send",
            "this video to others who would benefit from it if you know people",
            "en",
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(
            result.pending,
            "If you enjoyed this video, please give it a like and subscribe for more Tesla and tech videos and send this video to others who would benefit from it if you know people",
        )

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

    def test_sentence_boundary_result_tracks_punctuation_and_right_context_signals(self) -> None:
        result = split_punctuated_text("Hello. Next sentence.", "test")

        self.assertEqual(result.completed, ["Hello.", "Next sentence."])
        self.assertEqual(result.pending, "")
        self.assertEqual(result.end_mark_count, 2)
        self.assertEqual(result.right_context_start_count, 1)

if __name__ == "__main__":
    unittest.main()

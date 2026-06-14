import unittest
from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector, split_punctuated_text
from src.app.whisper_window import _collapse_adjacent_repeated_phrase_details, _collapse_adjacent_repeated_phrases, _diagnostic_tail, _forced_sentence_reason, _new_text_delta, _pending_new_text_combined, _sentence_max_age_chunks, _sentence_output_delta, _sentence_required_confirmations, _sentences_are_revisions, _should_age_staged_sentence, _should_translate_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


class WhisperSentenceBoundaryTest(unittest.TestCase):
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

    def test_pending_new_text_drops_incomplete_tail_before_ack_revision_from_log(self) -> None:
        # Regression from avc-whisper.log.1 chunks 847-848.
        self.assertEqual(
            _pending_new_text_combined(
                "It will take him probably a",
                "Okay. It will take them probably a month.",
            ),
            "Okay. It will take them probably a month.",
        )

    def test_sentence_boundary_does_not_complete_incomplete_tail_before_ack_revision_from_log(self) -> None:
        # Regression from avc-whisper.log.1 chunks 847-848.
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "It will take him probably a",
            "Okay. It will take them probably a month.",
            "en",
        )

        self.assertEqual(result.completed, ["Okay.", "It will take them probably a month."])
        self.assertEqual(result.pending, "")
        self.assertNotIn("It will take him probably a Okay.", result.completed)

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

    def test_sentence_boundary_does_not_prepend_short_pending_before_revised_completed_sentence(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "You have quick",
            "Here it shows you your vehicle. You have quick controls at the",
            "en",
        )

        self.assertEqual(result.completed, ["Here it shows you your vehicle."])
        self.assertEqual(result.pending, "You have quick controls at the")

    def test_sentence_boundary_soft_splits_here_is_restart_from_log(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "But you can add from all these different functions right here and then just hit save so it's really nice to have those shortcuts right there",
            "here is your live camera as long as you have sentry mode enabled which",
            "en",
        )

        self.assertEqual(
            result.completed,
            ["But you can add from all these different functions right here and then just hit save so it's really nice to have those shortcuts right there"],
        )
        self.assertEqual(result.pending, "here is your live camera as long as you have sentry mode enabled which")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_keeps_short_english_pending_without_restart_signal(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "This gives",
            "you a live camera option",
            "en",
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(result.pending, "This gives you a live camera option")

    def test_sentence_boundary_soft_splits_and_you_restart_from_log(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "money you've spent on charging the car and how much gas savings you've had for the year and for the month",
            "And you go in here and you can tap on",
            "en",
        )

        self.assertEqual(
            result.completed,
            ["money you've spent on charging the car and how much gas savings you've had for the year and for the month"],
        )
        self.assertEqual(result.pending, "And you go in here and you can tap on")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_soft_splits_so_it_restart_from_log(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "And you go in here and you can tap on these and change from kilowatt hours to percentage",
            "So it shows you how many kilowatt hours",
            "en",
        )

        self.assertEqual(
            result.completed,
            ["And you go in here and you can tap on these and change from kilowatt hours to percentage"],
        )
        self.assertEqual(result.pending, "So it shows you how many kilowatt hours")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_drops_dangling_and_before_revised_sentence_from_log(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "And",
            "if you ever need service, go in",
            "en",
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(result.pending, "if you ever need service, go in")

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

    def test_sentence_boundary_splits_long_driver_seat_sentence_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 23-33.
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "",
            "It is a very strange sensation to be a passenger in the car while you're in the driver's seat and having no interaction with the road whatsoever but once you get used to it it's",
            "en",
        )

        self.assertEqual(
            result.completed,
            ["It is a very strange sensation to be a passenger in the car while you're in the driver's seat and having no interaction with the road whatsoever"],
        )
        self.assertEqual(result.pending, "once you get used to it it's")

    def test_sentence_boundary_soft_split_trims_incomplete_if_tail_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 242-246.
        detector = LegacyRegexSentenceBoundaryDetector()
        result = detector.split(
            "",
            "halfway and another great new feature that came with a recent software update is the automatic turn signal if When you enable that, it'll automatically turn your turn signal off",
            "en",
        )

        self.assertEqual(
            result.completed,
            ["halfway and another great new feature that came with a recent software update is the automatic turn signal"],
        )
        self.assertEqual(result.pending, "When you enable that, it'll automatically turn your turn signal off")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_soft_splits_once_you_are_navigated_from_log(self) -> None:
        detector = LegacyRegexSentenceBoundaryDetector()

        result = detector.split(
            "going i can navigate to it and my tesla will take me there",
            "once you re navigated somewhere it ll look like this here you can play with the map",
            "en",
        )

        self.assertEqual(result.completed, ["going i can navigate to it and my tesla will take me there"])
        self.assertEqual(result.pending, "once you re navigated somewhere it ll look like this here you can play with the map")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_soft_splits_the_missing_navigation_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 700-703.
        detector = LegacyRegexSentenceBoundaryDetector()
        result = detector.split(
            "",
            "Another thing is I think the Achilles heel of the system right now is the navigation The missing on-ramps, issues with going into the right driveway or other things",
            "en",
        )

        self.assertEqual(
            result.completed,
            ["Another thing is I think the Achilles heel of the system right now is the navigation"],
        )
        self.assertEqual(
            result.pending,
            "The missing on-ramps, issues with going into the right driveway or other things",
        )
        self.assertEqual(result.soft_boundary_count, 1)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()

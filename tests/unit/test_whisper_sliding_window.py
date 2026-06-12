import unittest

from src.app.sentence_boundary import RegexSentenceBoundaryDetector
from src.app.whisper_window import _collapse_adjacent_repeated_phrases, _diagnostic_tail, _forced_sentence_reason, _new_text_delta, _pending_new_text_combined, _sentence_output_delta, _sentences_are_revisions, _should_age_staged_sentence, _should_translate_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


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

    def test_sentence_revision_detects_short_prefix_expansion_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 283-295.
        self.assertTrue(
            _sentences_are_revisions(
                "Again awesome.",
                "again awesome the location tab shows your car's live location at any time which is awesome.",
            )
        )
        self.assertEqual(
            _prefer_sentence_revision(
                "Again awesome.",
                "again awesome the location tab shows your car's live location at any time which is awesome.",
            ),
            "again awesome the location tab shows your car's live location at any time which is awesome.",
        )

    def test_sentence_revision_rejects_distinct_sentences(self) -> None:
        self.assertFalse(_sentences_are_revisions("Tesla app.", "It was going a little fast."))


    def test_staged_sentence_is_not_translated_before_final_by_default(self) -> None:
        self.assertFalse(_should_translate_staged_sentence("Again awesome.", 1))
        self.assertFalse(_should_translate_staged_sentence("Again awesome the location tab shows", 1))
        self.assertFalse(_should_translate_staged_sentence("Again awesome.", 2))


    def test_staged_sentence_waits_when_pending_extends_it_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 642-648.
        staged = "It just resets the screen in case like i said it freezes or gets a little slow."
        pending = "just resets the screen in case like I said it freezes or gets a little slow and lastly the fourth advanced feature I want to talk about the software updates As you may or"

        self.assertFalse(_should_age_staged_sentence(staged, pending))

    def test_staged_sentence_waits_when_fast_boundary_reuses_blind_spot_tail_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 226-230.
        staged = "If I want to quickly change over to the left lane without looking at my blind spot, in my blind spot I could turn on certain I can turn on certain turn signal and when that setting is enabled it automatically shows a visual of my blind spot camera and now I can easily see that nobody's in my blind spot and I"
        pending = "And now I can easily see that nobody's in my blind spot and I can easily change lanes while"

        self.assertFalse(_should_age_staged_sentence(staged, pending))

    def test_staged_sentence_waits_when_pending_reuses_self_driving_tail_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 34-39.
        staged = "It's also less fatiguing to drive when you're taking more breaks, and then you have the systems like autopilot and full self-driving in tesla vehicles specifically that help to make your drive that much less fatiguing as well"
        pending = "self-driving and Tesla vehicles specifically that help to make your drive that much less fatiguing as well and make the trade-off worth it for those couple extra minutes spent at chargers."

        self.assertTrue(_sentences_are_revisions(staged, pending))
        self.assertFalse(_should_age_staged_sentence(staged, pending))

    def test_staged_sentence_waits_when_pending_revises_youre_tail_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 81-82.
        staged = "If you just bought a Tesla or waiting for delivery or you're"
        pending = "If you just bought a Tesla are waiting for delivery or you're seriously thinking about"

        self.assertTrue(_sentences_are_revisions(staged, pending))
        self.assertFalse(_should_age_staged_sentence(staged, pending))

    def test_staged_sentence_waits_when_pending_reuses_outlet_tail_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 34-36.
        staged = "Tesla's charging cable this would be for home charging and public Chargers and tesla destination chargers not for tesla superchargers But maybe you find yourself at a location where you can park here, but the outlet is all the way over there."
        pending = "where you can park here, but the outlet is all the way over there, this will ensure that you"

        self.assertTrue(_sentences_are_revisions(staged, pending))
        self.assertFalse(_should_age_staged_sentence(staged, pending))

    def test_staged_sentence_prefers_later_range_per_hour_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 195-201.
        staged = "This is the real sweet spot for Tesla ownership because you can typically gain about 25 to 44 miles of range"
        revised = "This is the real sweet spot for Tesla ownership because you can typically gain about 25 to 44 miles of range per hour."

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)

    def test_staged_sentence_can_age_without_pending_revision(self) -> None:
        self.assertTrue(_should_age_staged_sentence("Completed sentence.", "Different topic starts here"))


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


    def test_sentence_boundary_soft_splits_long_english_restart_without_punctuation(self) -> None:
        detector = RegexSentenceBoundaryDetector()

        result = detector.split(
            "And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in",
            "But now let's dive into some of the settings you have to know",
            "en",
        )

        self.assertEqual(result.completed, ["And Tesla does use the camera so it does know if a person is using their turn signal and they are trying to merge in"])
        self.assertEqual(result.pending, "But now let's dive into some of the settings you have to know")
        self.assertEqual(result.soft_boundary_count, 1)

    def test_sentence_boundary_soft_split_is_not_used_for_korean(self) -> None:
        detector = RegexSentenceBoundaryDetector()

        result = detector.split(
            "이 문장은 아직 끝나지 않았고 다음 내용이 계속 이어지고 있어서 경계를 확정하면 안 됩니다",
            "그런데 새 문장이 시작되는 것처럼 보여도 한국어 휴리스틱은 아직 적용하지 않습니다",
            "ko",
        )

        self.assertEqual(result.completed, [])
        self.assertIn("그런데 새 문장이", result.pending)

    def test_sentence_boundary_does_not_prepend_short_pending_before_revised_completed_sentence(self) -> None:
        detector = RegexSentenceBoundaryDetector()

        result = detector.split(
            "You have quick",
            "Here it shows you your vehicle. You have quick controls at the",
            "en",
        )

        self.assertEqual(result.completed, ["Here it shows you your vehicle."])
        self.assertEqual(result.pending, "You have quick controls at the")

    def test_sentence_boundary_soft_splits_here_is_restart_from_log(self) -> None:
        detector = RegexSentenceBoundaryDetector()

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
        detector = RegexSentenceBoundaryDetector()

        result = detector.split(
            "This gives",
            "you a live camera option",
            "en",
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(result.pending, "This gives you a live camera option")

    def test_sentence_boundary_soft_splits_and_you_restart_from_log(self) -> None:
        detector = RegexSentenceBoundaryDetector()

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
        detector = RegexSentenceBoundaryDetector()

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
        detector = RegexSentenceBoundaryDetector()

        result = detector.split(
            "And",
            "if you ever need service, go in",
            "en",
        )

        self.assertEqual(result.completed, [])
        self.assertEqual(result.pending, "if you ever need service, go in")

    def test_sentence_boundary_does_not_soft_split_lowercase_this_inside_phrase_from_log(self) -> None:
        detector = RegexSentenceBoundaryDetector()

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

    def test_sentence_output_delta_suppresses_revised_floating_hoping_duplicate_from_log(self) -> None:
        committed = "floating and hoping like a spot spot up three point shooter"
        sentence = "not just floating and hoping like a spot-up three-point shooter."

        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_trims_repeated_hunting_prefix_and_suffix_from_log(self) -> None:
        committed = "It's hunting. No, it's it's honey."
        sentence = "It's hunting like a shark Now, it's hunting."

        self.assertEqual(_sentence_output_delta(committed, sentence), "like a shark now")

    def test_sentence_output_delta_suppresses_short_third_pro_tip_revision_from_log(self) -> None:
        committed = "And a third pro tip, if where like that also."
        sentence = "And the third pro tip, if where you want to go has no name or address or you're not sure if you could find it on the map,"

        self.assertEqual(_sentence_output_delta(committed, sentence), "you want to go has no name or address or you re not sure if you could find it on the map")

    def test_sentence_output_delta_trims_short_actually_driving_prefix_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 629 and 632.
        committed = "actually driving"
        sentence = "about actually driving before we get into that you may notice an alert right here tesla will send you alerts for like low tire pressure and some other random things if you tap on it it'll tell you what it's for mine says this right here which basically means it doesn't like my phone camera being"

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "before we get into that you may notice an alert right here tesla will send you alerts for like low tire pressure and some other random things if you tap on it it ll tell you what it s for mine says this right here which basically means it doesn t like my phone camera being",
        )

    def test_sentence_output_delta_trims_leading_partial_word_overlap_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 180-191.
        committed = "This is very helpful for your road trips there's no need to plug into a supercharger and charge to 100% just to get to the next one there"
        sentence = "charger and charge to 100 just to get to the next one there are plenty of superchargers in the US at least and around most places in the world where you don't need all that battery to continue your trip."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "are plenty of superchargers in the us at least and around most places in the world where you don t need all that battery to continue your trip",
        )

    def test_sentence_output_delta_trims_committed_customization_prefix_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 210-213.
        committed = "But if you want to play with the customization and the menus and all that you can play with it on your own"
        sentence = "customization and the menus and all that you can play with it on your own at the top is your car's name you can customize it in the Tesla menu."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "at the top is your car s name you can customize it in the tesla menu",
        )

    def test_sentence_output_delta_trims_short_again_awesome_prefix_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 283-295.
        committed = "Again awesome."
        sentence = "again awesome the location tab shows your car's live location at any time which is awesome."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "the location tab shows your car s live location at any time which is awesome",
        )

    def test_collapse_repeated_like_lets_say_phrase_from_log(self) -> None:
        self.assertEqual(
            _collapse_adjacent_repeated_phrases(
                "like let's say i just want to go right here I'll hold it on the map like let's say i just want to go right here i'll hold it"
            ),
            "like let's say i just want to go right here I'll hold it on the map",
        )

    def test_collapse_repeated_tap_close_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 100-102.
        text = "Just tap on that lightning bolt icon and it will automatically open your charge port and you can tap on it again to close You can tap on it again to close it."

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "Just tap on that lightning bolt icon and it will automatically open your charge port and you can tap on it again to close it.",
        )

    def test_collapse_repeated_prefix_before_hyphenated_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 592-594.
        text = "EPA estimated ranges are a best best-case scenario, so it's not really the daily reality."

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "EPA estimated ranges are a best-case scenario, so it's not really the daily reality.",
        )

    def test_collapse_repeated_phrase_with_variant_leading_word_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 132-143.
        text = "Right now, Fantech is running some fantic is running some huge discounts where you can get 45% off the X8 Apex"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "Right now, Fantech is running some huge discounts where you can get 45% off the X8 Apex",
        )

    def test_sentence_output_delta_collapses_repeated_tap_close_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 100-102.
        text = "Just tap on that lightning bolt icon and it will automatically open your charge port and you can tap on it again to close You can tap on it again to close it."

        self.assertEqual(
            _sentence_output_delta("", text),
            "Just tap on that lightning bolt icon and it will automatically open your charge port and you can tap on it again to close it.",
        )

    def test_sentence_output_delta_trims_fast_boundary_turn_signal_overlap_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 246-256.
        committed = "halfway and another great new feature that came with a recent software update is the automatic turn signal"
        sentence = "turn signal if you when you enable that it'll automatically turn your turn signal off and normally with that before that setting came, when you half-press a turn signal it would go on three blinks and then if you fully press the turn signal it stays"

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "when you enable that it ll automatically turn your turn signal off and normally with that before that setting came when you half press a turn signal it would go on three blinks and then if you fully press the turn signal it stays",
        )

    def test_sentence_output_delta_trims_self_driving_tail_reuse_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 34-39.
        committed = "It's also less fatiguing to drive when you're taking more breaks, and then you have the systems like autopilot and full self-driving in tesla vehicles specifically that help to make your drive that much less fatiguing as well"
        sentence = "self-driving and Tesla vehicles specifically that help to make your drive that much less fatiguing as well and make the trade-off worth it for those couple extra minutes spent at chargers."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "and make the trade off worth it for those couple extra minutes spent at chargers",
        )

    def test_collapse_repeated_charger_status_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 319-321.
        text = "location is, how many stalls there are, what the nearby amenities are, and if there's any broken stalls there are what the nearby amenities are and if there's any broken stalls at the current moment if there is a wait time at a particular charger, it will let you know, but a lot of times it will automatically reroute you as well, so you won't have to think about it"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "location is, how many stalls there are, what the nearby amenities are, and if there's any broken stalls at the current moment if there is a wait time at a particular charger, it will let you know, but a lot of times it will automatically reroute you as well, so you won't have to think about it",
        )

    def test_sentence_output_delta_trims_charger_status_tail_reuse_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 319-321.
        committed = "it gives you a live status But so that you can see how many chargers are available how big that particular charger location is how many stalls there are what the nearby amenities are, and if there's any broken"
        sentence = "location is, how many stalls there are, what the nearby amenities are, and if there's any broken stalls there are what the nearby amenities are and if there's any broken stalls at the current moment if there is a wait time at a particular charger, it will let you know, but a lot of times it will automatically reroute you as well, so you won't have to think about it but this also may be"

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "stalls at the current moment if there is a wait time at a particular charger it will let you know but a lot of times it will automatically reroute you as well so you won t have to think about it but this also may be",
        )

    def test_sentence_boundary_soft_split_trims_incomplete_if_tail_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 242-246.
        detector = RegexSentenceBoundaryDetector()
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
        detector = RegexSentenceBoundaryDetector()

        result = detector.split(
            "going i can navigate to it and my tesla will take me there",
            "once you re navigated somewhere it ll look like this here you can play with the map",
            "en",
        )

        self.assertEqual(result.completed, ["going i can navigate to it and my tesla will take me there"])
        self.assertEqual(result.pending, "once you re navigated somewhere it ll look like this here you can play with the map")
        self.assertEqual(result.soft_boundary_count, 1)

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

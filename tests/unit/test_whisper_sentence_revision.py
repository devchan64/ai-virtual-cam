import unittest

from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector
from src.app.whisper_window import (
    _collapse_adjacent_repeated_phrase_details,
    _collapse_adjacent_repeated_phrases,
    _diagnostic_tail,
    _final_sentence_diagnostic_flags,
    _forced_sentence_reason,
    _format_transcript_metrics,
    _new_text_delta,
    _pending_new_text_combined,
    _prefer_sentence_revision,
    _replacement_decision_reason,
    _sentence_end_count,
    _sentence_max_age_chunks,
    _sentence_output_delta,
    _sentence_required_confirmations,
    _sentences_are_revisions,
    _should_age_staged_sentence,
    _should_finalize_replaced_sentence,
    _should_confirm_staged_sentence,
    _should_translate_staged_sentence,
    _split_completed_sentences,
    _stable_window_text,
)


class WhisperSentenceRevisionTest(unittest.TestCase):
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

    def test_sentence_revision_detects_short_one_that_suits_revisions_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 154-158.
        self.assertTrue(
            _sentences_are_revisions(
                "It's me, not one that suits Joe.",
                "Yeah, it's one that it suits Joe.",
            )
        )
        self.assertEqual(
            _prefer_sentence_revision(
                "It's me, not one that suits Joe.",
                "Yeah, it's one that it suits Joe.",
            ),
            "Yeah, it's one that it suits Joe.",
        )
        self.assertTrue(
            _sentences_are_revisions(
                "Yeah, it's one that it suits Joe.",
                "Yes, one that suits mom.",
            )
        )
        self.assertEqual(
            _prefer_sentence_revision(
                "Yeah, it's one that it suits Joe.",
                "Yes, one that suits mom.",
            ),
            "Yes, one that suits mom.",
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

    def test_unconfirmed_replaced_stage_finalizes_completed_short_sentences_from_monitoring(self) -> None:
        # Regressions from 2026-06-13 monitoring. These are complete short utterances,
        # not disposable noise just because they were observed once before a replacement.
        cases = [
            ("그렇죠", "스테이블 코인인가요"),
            ("스테이블 코인인가요", "그렇죠"),
            ("그게 유럽입니다", "그게 유럽 모형이에요"),
            ("그러니까 미국이 함부로 그걸 안 하는 거죠", "그게 이런 모형이에요"),
            ("근데 요새는 다른 거 같아요", "이 신용화폐 근데 요새는 다른 것 같아요"),
            ("저는 이게 상당히 걱정이 돼요", "왜냐하면 미국인들 돈만 들어가는 게 아니라 전세계 돈이 다 빨려 들어가겠죠"),
            ("아니요", "이거는 이미 트렌드화가 돼서 5년 10년은 더 갈 것 같죠"),
        ]
        for staged, candidate in cases:
            with self.subTest(staged=staged, candidate=candidate):
                self.assertTrue(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_unconfirmed_replaced_stage_waits_on_open_latin_clause_from_monitoring(self) -> None:
        cases = [
            (
                "Currently, in the robot world, I worked as I've never",
                "It's my first",
            ),
            (
                "Like, R2D2 would beep at you and it's hard to figure out what he's talking about, to be able to translate,",
                "there are probably, I don't know, three to five robots in industry for every one that's a personal robot.",
            ),
        ]
        for staged, candidate in cases:
            with self.subTest(staged=staged):
                self.assertEqual(
                    _replacement_decision_reason(staged, candidate, 1, False, 0),
                    "open_latin_clause",
                )
                self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_unconfirmed_replaced_stage_finalizes_confirmed_sentences(self) -> None:
        self.assertTrue(_should_finalize_replaced_sentence("확정 후보입니다", "다른 후보입니다", 3, False, 0))
        self.assertTrue(_should_finalize_replaced_sentence("강제 확정 후보입니다", "다른 후보입니다", 4, True, 0))

    def test_unconfirmed_replaced_stage_waits_for_observation_age(self) -> None:
        self.assertTrue(_should_finalize_replaced_sentence("Aged candidate", "Different candidate", 1, False, 1))
        self.assertTrue(_should_finalize_replaced_sentence("Forced aged candidate", "Different candidate", 1, True, 1))

    def test_open_korean_clause_does_not_confirm_from_repeated_candidate(self) -> None:
        # Regression from 2026-06-13 monitoring chunks 54-55. The same open
        # Korean clause repeated twice, but it was only the head of the next sentence.
        self.assertFalse(_should_confirm_staged_sentence("이 두 직업은", 2, False))
        self.assertFalse(_should_confirm_staged_sentence("그런데 보면 최치PD가 등장하기", 4, True))
        self.assertTrue(_should_confirm_staged_sentence("신규 채용을 안 하고 있습니다.", 3, False))

    def test_replacement_keeps_confirmed_open_korean_clause_from_monitoring(self) -> None:
        # Regression from 2026-06-13 30-minute monitoring chunks 7-11.
        # The staged sentence had enough repeated observations to pass the
        # confirmation count, but its Korean tail was still an open clause.
        staged = "1억을 넣었을 때 2000만원이 깨지는 천만원에서 20% 빠졌을 때 200이 깨지는 느낌"
        candidate = "이런 것들을 계속해서 좀 충격도 한번 받아보고 얼마나 견뎌낼 수 있는지 그거는 사실 스스로도 몰라요."

        self.assertEqual(
            _replacement_decision_reason(staged, candidate, 4, False, 0),
            "open_korean_clause",
        )
        self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 4, False, 0))

    def test_replacement_decision_reason_exposes_runtime_diagnostics(self) -> None:
        self.assertEqual(
            _replacement_decision_reason("그 아래 3-5% 정도", "인플루언서, 유명한 사람들", 1, False, 1),
            "open_korean_clause",
        )
        self.assertEqual(
            _replacement_decision_reason("Aged candidate", "Different candidate", 1, False, 1),
            "aged",
        )
        self.assertEqual(
            _replacement_decision_reason("정부가 어떻게 보면은 자산시장 사재기에 더 집중화시키고 있는 전략일 것이다", "전략일 것이다", 1, False, 0),
            "duplicate_or_suffix",
        )


    def test_final_sentence_diagnostic_flags_identify_unstable_chinese_outputs(self) -> None:
        self.assertIn("short_cjk", _final_sentence_diagnostic_flags("蒸牛。", "zh"))
        self.assertIn("short_cjk", _final_sentence_diagnostic_flags("潇洒最好的乳团。", "zh"))
        self.assertIn("latin_only_for_zh", _final_sentence_diagnostic_flags("The.", "zh"))
        self.assertIn("mixed_latin_zh", _final_sentence_diagnostic_flags("matcha ice cream很好吃。", "zh"))
        self.assertEqual(
            _final_sentence_diagnostic_flags("看起来好好吃啊，你真的有很多小吃呢，我看到。", "zh"),
            (),
        )

    def test_transcript_metrics_format_is_stable_for_log_analysis(self) -> None:
        self.assertEqual(_format_transcript_metrics({}), "none")
        self.assertEqual(
            _format_transcript_metrics({"stage_revision": 2, "stage_start": 3, "stage_discard": 0}),
            "stage_revision=2,stage_start=3",
        )

    def test_unconfirmed_replaced_stage_waits_on_open_korean_clause_from_monitoring(self) -> None:
        # Regressions from 2026-06-13 monitoring. These candidates were replaced
        # before the next revision had a chance to complete the Korean clause.
        cases = [
            ("그 아래 3-5% 정도", "인플루언서, 유명한 사람들, 연예인들 그리고 나머지 95%"),
            ("새로운 물리학 이론을", "그건 모릅니다"),
            ("그리고 아무도 모를 때는 그냥 해보시면 되는 것", "기계가 잘하는 거 가지고 인간이 경쟁하는 건 무모한 짓이에요."),
            ("AI가 점점점 확장이 좀 확장이 되면서", "그럼 어떻게 되죠?"),
            ("앞으로 산업이 어떻게 새롭게 재편될지 그것도", "이 모든 것은 저의 개인적인 생각입니다"),
            ("뭔가 좀 꿈과 희망이 있는 많은 이야기를 해줘야 되겠다라고 생각은 했는데 또 역시 얘기를 하면서 점점 디스토피아로 가지 않을까 싶고", "이 모든 것은 저의 개인적인 생각입니다"),
        ]
        for staged, candidate in cases:
            with self.subTest(staged=staged, candidate=candidate):
                self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_sentence_confirmation_waits_for_revision_windows(self) -> None:
        self.assertEqual(_sentence_required_confirmations(False), 3)
        self.assertEqual(_sentence_max_age_chunks(False), 3)
        self.assertEqual(_sentence_required_confirmations(True), 4)
        self.assertEqual(_sentence_max_age_chunks(True), 4)

    def test_unconfirmed_replaced_stage_preserves_completed_dollar_sentence_from_log(self) -> None:
        # Regression from avc-whisper.log chunk 48 and 2026-06-13 monitoring chunks 991-992.
        # Without a semantic verifier, fail closed on dropping completed text; later candidates
        # are still staged and must earn their own confirmations.
        staged = "의장들이 나와서 달러를 홍보를 합니다"
        candidate = "빨라를 홍보를 합니다"

        self.assertFalse(_sentences_are_revisions(staged, candidate))
        self.assertTrue(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_partial_replacement_preserves_completed_staged_sentence_from_monitoring(self) -> None:
        cases = [
            (
                "특히 스웨덴의 러브블 이란 회사가 지금 제일 잘 나갑니다",
                "이걸 쓰시면 실리콘밸리 레덴의 러브오블이라는 회사가 지금 제일 잘 나갑니다.",
            ),
            (
                "그런데 공장에서 기계들이 스팀 엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도예요.",
                "엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다",
            ),
            (
                "엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다",
                "바로 다음주 수요일부터 되는 50년 정도가 더 걸렸습니다.",
            ),
        ]
        for staged, candidate in cases:
            with self.subTest(staged=staged, candidate=candidate):
                self.assertEqual(_replacement_decision_reason(staged, candidate, 1, False, 0), "partial_preserve")
                self.assertTrue(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_unconfirmed_replaced_stage_discards_tail_echo_from_log(self) -> None:
        # Regression from avc-whisper.log chunk 76. The first candidate contains prior-sentence tail echo.
        staged = "근데 우리가 그런 얘기하지 골적으로 얘기하지 않죠"
        candidate = "우리가 그런 얘기하지 않습니다"

        self.assertFalse(_sentences_are_revisions(staged, candidate))
        self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_replaced_stage_finalizes_long_sentence_from_log(self) -> None:
        # Regression from avc-whisper.log chunk 59. A single-observation but long completed sentence should not be dropped.
        staged = "이게 초래할 미래의 형국도 저는 지금의 경제 시스템으로는 감당 불가능하다"
        candidate = "여기서 이제 일론 머스크의 비판을 또 하나 좀 말씀드리는데 XG가 X지갑 만들었잖아요"

        self.assertFalse(_sentences_are_revisions(staged, candidate))
        self.assertTrue(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_replaced_stage_finalizes_suffix_candidate_from_log(self) -> None:
        # Regression from avc-whisper.log chunk 25. Suffix-only candidate means the staged sentence is already complete.
        staged = "정부가 어떻게 보면은 자산시장 사재기에 더 더 집중화시키고 있는 전략일 것이다"
        candidate = "전략일 것이다"

        self.assertFalse(_sentences_are_revisions(staged, candidate))
        self.assertTrue(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_staged_sentence_can_age_without_pending_revision(self) -> None:
        self.assertTrue(_should_age_staged_sentence("Completed sentence.", "Different topic starts here"))

    def test_staged_sentence_ages_when_pending_is_short_suffix_repeat_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 360-368.
        staged = "The GPS doesn't always take us on the best route because we could have taken the highway and just gotten off here at the exit but instead we're taking a side road to get"
        pending = "taking a side road to get"

        self.assertTrue(_sentences_are_revisions(staged, pending))
        self.assertTrue(_should_age_staged_sentence(staged, pending))

    def test_sentence_pending_can_accumulate_long_fast_speech(self) -> None:
        pending = "this is a quick sentence fragment that keeps going without punctuation and should not be forced too early"

        self.assertEqual(_forced_sentence_reason(pending, 4), "")

    def test_sentence_revision_detects_korean_tail_extension(self) -> None:
        # Regression-style Korean case: short committed tail extended by the next stable chunk.
        staged = "다음은 가장 저렴한 부분입니다."
        revised = "다음은 가장 저렴한 부분입니다. 액셀러를 누릅니다."

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)
        self.assertEqual(_new_text_delta(staged, revised), "액셀러를 누릅니다.")

    def test_sentence_revision_detects_korean_comma_number_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 8-12: 1400원 and 1,400원 are the same numeric value.
        staged = "1400원, 1220원, 이래 올라오잖아요."
        revised = "1,400원, 1,220원, 이러러 나오잖아요"

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), staged)

    def test_sentence_revision_detects_korean_compact_abenomics_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 60-63.
        staged = "아베 신조가 에나를 들이붓던 아베노믹스 라는게 있었어요"
        revised = "아베 신조가 엔화를 들이붓던 에나를 들이붓던 거였거든요."

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)

    def test_sentence_revision_keeps_longer_korean_revision_when_short_tail_reappears_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 62-63.
        staged = "아베 신조가 엔화를 들이붓던 에나를 들이붓던 거였거든요."
        revised = "아베 신조 거였거든요."

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), staged)

    def test_sentence_revision_detects_korean_spacing_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 220-223.
        staged = "그래서 아베가 엔화약세를 만들고 싶어"
        revised = "그래서 아베가 엔화 약세를 만들고 싶어 했어요"

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)

    def test_sentence_revision_detects_korean_latin_n_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 223-225 and 249-252.
        self.assertTrue(_sentences_are_revisions("그래서 엔을 뿌렸거든요.", "그래서 n을 뿌렸거든요."))
        self.assertEqual(_prefer_sentence_revision("그래서 엔을 뿌렸거든요.", "그래서 n을 뿌렸거든요."), "그래서 엔을 뿌렸거든요.")
        self.assertTrue(_sentences_are_revisions("엔화가 너무너무 약세가 되지 수 있지 않을까요", "N화가 너무너무 약세가 되지 않을까요?"))
        self.assertEqual(_prefer_sentence_revision("엔화가 너무너무 약세가 되지 수 있지 않을까요", "N화가 너무너무 약세가 되지 않을까요?"), "N화가 너무너무 약세가 되지 않을까요?")

    def test_sentence_revision_detects_korean_second_plan_extension_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 97-100.
        staged = "근데 두 번째는 뭐냐면 웃는"
        revised = "근데 두 번째 안은 뭐냐면 웃는 그날까지 던지겠습니다"

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)

    def test_sentence_revision_detects_korean_rate_cut_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 93-96 on 2026-06-13.
        staged = "본인이 당선되니까 금리 이 얘기 하고 있거든요"
        revised = "본인이 당선되니까 금리에 나와라고 그렇게 금리 인하라고 그렇게 하더라고요."

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)

    def test_staged_sentence_does_not_age_on_korean_revision_candidate(self) -> None:
        # Ensure Korean staged text waits for stabilized revision rather than aging prematurely.
        staged = "우리는 맥북을 통신으로 사용할 수 있을 것입니다"
        pending = "이는 맥북을 통신으로 사용할 수 있을 것입니다"

        self.assertTrue(_sentences_are_revisions(staged, pending))
        self.assertFalse(_should_age_staged_sentence(staged, pending))

    def test_sentence_revision_prefers_take_care_completion_from_charge_log(self) -> None:
        # Regression from avc-whisper.log chunks 567-570.
        noisy = "Do you want to connect it or sure i'll take care me to go?"
        corrected = "Sure, I'll take care of it."

        self.assertTrue(_sentences_are_revisions(noisy, corrected))
        self.assertEqual(_prefer_sentence_revision(noisy, corrected), corrected)
        self.assertEqual(_sentence_output_delta(corrected, "of it."), "")

    def test_sentence_revision_keeps_charge_of_day_context_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 571-578.
        first = "We're at our fourth charge of the day it is currently"
        revised = "charge of the day it is currently 7 30 p.m."

        self.assertTrue(_sentences_are_revisions(first, revised))
        self.assertEqual(_prefer_sentence_revision(first, revised), revised)

    def test_revision_lifecycle_simulates_revised_tail_extension(self) -> None:
        # Regression-like sequence: pending sentence tail gets expanded, then confirmed.
        completed, pending = _split_completed_sentences("", "It's like a shark now")
        self.assertEqual(completed, [])
        self.assertEqual(pending, "It's like a shark now")

        # Later revision candidate from Whisper is considered a revision of staged text.
        revised = "It's hunting like a shark Now, it's hunting."
        staged = pending
        self.assertTrue(_sentences_are_revisions(staged, revised))

        finalized = _prefer_sentence_revision(staged, revised)
        self.assertEqual(finalized, revised)

        # Sliding delta behavior for the same segment should remain minimal after confirmation.
        self.assertEqual(_new_text_delta(staged, finalized), "it's hunting.")

    def test_revision_lifecycle_simulates_connective_and_numeric_fragment_block(self) -> None:
        # sequence observed with tail fragments like numeric and connective artifacts.
        self.assertEqual(
            _sentence_output_delta(
                "charge of the day it is currently",
                "charge of the day it is currently 7 30 p.m.",
            ),
            "7 30 p m",
        )

        self.assertEqual(
            _sentence_output_delta(
                "saying dry weight is around 5,800 pounds and it has a GBWR of 6,800",
                "are 6,800 pounds.",
            ),
            "",
        )

        self.assertEqual(
            _sentence_output_delta("Let's do it now.", "do it now."),
            "",
        )


    def test_chinese_revision_uses_cjk_character_units_from_log(self) -> None:
        # Regression from 2026-06-13 zh monitoring chunks 89-91. Chinese text has
        # no spaces, so lifecycle decisions must not collapse to an empty token set.
        staged = "他给出了两个拒绝绑匪要求。"
        revised = "他给出了两个拒绝绑匪要求的理由，从。"

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)
        self.assertNotEqual(_replacement_decision_reason(staged, revised, 1, False, 0), "empty")

    def test_chinese_unconfirmed_stage_does_not_age_finalize_from_no_speech_gap(self) -> None:
        # Regression from 2026-06-13 zh monitoring chunk 94. Repeated no_speech
        # gaps must not finalize a single-observation Chinese fragment.
        staged = "他给出了两个拒绝绑匪要求的理由，从。"

        self.assertFalse(_should_age_staged_sentence(staged, ""))
        self.assertEqual(
            _replacement_decision_reason(staged, "保羅蓋蒂的這個說法是對的從古到今。", 1, False, 2),
            "unconfirmed_cjk",
        )
        self.assertFalse(
            _should_finalize_replaced_sentence(staged, "保羅蓋蒂的這個說法是對的從古到今。", 1, False, 2)
        )


    def test_chinese_short_fragments_do_not_finalize_on_replacement_from_log(self) -> None:
        # Regressions from 2026-06-13 zh monitoring chunks 81, 84, 85, and 100.
        # These fragments were model/punctuation boundary artifacts, not stable final sentences.
        cases = [
            ("为什。", "这个桥段在电影里非常重要，为什么呢？"),
            ("为什么呢？", "是因为绑匪呢？"),
            ("提出要170.为什么呢？", "是因为绑匪呢提出要1700万美金的。"),
            ("所以世。", "保羅蓋蒂的這個說法是對的從古到今。"),
        ]
        for staged, candidate in cases:
            with self.subTest(staged=staged, candidate=candidate):
                self.assertEqual(_replacement_decision_reason(staged, candidate, 1, False, 0), "unconfirmed_cjk")
                self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

    def test_chinese_confirmed_stage_can_finalize_on_replacement(self) -> None:
        staged = "如果你跟绑匪妥协的话，就会导致第二例案情的发生。"
        candidate = "所以世。"

        self.assertEqual(_replacement_decision_reason(staged, candidate, 3, False, 0), "confirmed")
        self.assertTrue(_should_finalize_replaced_sentence(staged, candidate, 3, False, 0))


if __name__ == "__main__":
    unittest.main()

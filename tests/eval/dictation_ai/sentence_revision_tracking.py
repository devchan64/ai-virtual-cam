import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector
from src.app.dictation_transcript_logic import (
    _is_recent_final_echo,
    _recent_final_output_delta,
    _should_finalize_before_replacement,
    _should_finalize_boundary_candidate,
    _should_reset_revision_age,
)
from src.app.dictation_window import (
    _diagnostic_tail,
    _final_sentence_diagnostic_flags,
    _format_transcript_metrics,
    _new_text_delta,
    _next_revision_confirmation_count,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
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
    _should_stage_boundary_candidate,
    _should_preserve_revision_confirmation_from_internal_stability,
    _revision_internal_stability_bucket,
    _should_translate_final_sentence,
    _split_completed_sentences,
    _stable_window_text,
)

# This module keeps historical sentence revision observations out of unit-test
# discovery. It is a tracking benchmark: failures indicate tuning work, not a
# general quality gate for unrelated changes.


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

    def test_cjk_revision_content_change_resets_confirmation_count_from_monitoring(self) -> None:
        # Regression from 2026-06-15 Chinese monitoring around chunks 112-114.
        # The content kept changing, but confirmations continued to accumulate and allowed
        # an unstable candidate to be finalized.
        previous = "宝宝真的是啊一看到这东西直抢趁着我这几天还能吃冰了赶紧吃"
        preferred = "宝宝真的是啊一看到这东西直抢趁着我这几天还能吃冰了赶紧吃你就比平时不能吃的时候你没少吃啊关键"

        self.assertEqual(_next_revision_confirmation_count(previous, preferred, 4), 1)
        self.assertEqual(_next_revision_confirmation_count(preferred, preferred, 4), 5)

    def test_cjk_revision_confirmation_is_preserved_for_high_internal_stability(self) -> None:
        previous = "喜欢按赞点点，可以呃分享可以。欢迎大家继续坚持，很累了，坚持到几万步，两万二。"
        preferred = "喜欢按赞点A，可以呃分享可以分享。大家现在已经接近累了，今天的几万步，两万二。"

        self.assertTrue(
            _should_preserve_revision_confirmation_from_internal_stability(
                previous,
                preferred,
                0.62,
                65,
                "none",
            )
        )
        self.assertEqual(_next_revision_confirmation_count(previous, preferred, 2, 0.62, 65, "none"), 2)
        self.assertEqual(_revision_internal_stability_bucket(0.62, 65), "high")

    def test_cjk_revision_confirmation_still_resets_for_short_internal_stability(self) -> None:
        previous = "嘛那我们就各购"
        preferred = "可以啦，阿正背影呢。隔壁就是志孝去吃的那个月岛文字烧，然后那感觉也蛮赞的嘛。那我们就各购。"

        self.assertFalse(
            _should_preserve_revision_confirmation_from_internal_stability(
                previous,
                preferred,
                0.87,
                39,
                "none",
            )
        )
        self.assertEqual(_next_revision_confirmation_count(previous, preferred, 2, 0.87, 39, "none"), 1)
        self.assertEqual(_revision_internal_stability_bucket(0.87, 39), "low")

    def test_cjk_revision_confirmation_still_resets_without_internal_stability(self) -> None:
        previous = "喜欢按赞点点，可以呃分享可以。欢迎大家继续坚持，很累了，坚持到几万步，两万二。"
        preferred = "完全不同的话题开始了。"

        self.assertFalse(
            _should_preserve_revision_confirmation_from_internal_stability(
                previous,
                preferred,
                0.40,
                65,
                "none",
            )
        )
        self.assertEqual(_next_revision_confirmation_count(previous, preferred, 2, 0.40, 65, "none"), 1)
        self.assertEqual(_revision_internal_stability_bucket(0.40, 65), "mid")

    def test_cjk_revision_trims_repeated_pending_prefix_from_monitoring(self) -> None:
        # Regression from 2026-06-15 20s Chinese monitoring chunks 1-2.
        # A pending tail was prepended before the next overlapping window, then
        # repeated again at the natural continuation point.
        previous = (
            "都是豆。所以我们之前吃的那些价格比较高的，可能都是游客点，对吧？都是网上推的。"
            "嗯。现在是十点五十，我们等到十一点的时候，隔壁那个甜甜圈都开门了，我们去买甜甜圈吃。"
        )
        candidate = (
            "你们知道小伙伴为什么那么之前吃的那些价格比较高的，可能都是游客店，对吧？都是网上推的。"
            "嗯。现在是十点五十，我们等到十一点的时候，隔壁那个甜甜圈都开门了，我们去买甜甜圈吃。"
            "你们知道小伙伴为什么那么爱撸一天九顿吗？咋了？"
        )

        preferred = _prefer_sentence_revision(previous, candidate)

        self.assertFalse(preferred.startswith("你们知道小伙伴为什么那么之前"))
        self.assertIn("你们知道小伙伴为什么那么爱撸一天九顿吗", preferred)

    def test_cjk_revision_trims_long_repeated_pending_prefix_from_monitoring(self) -> None:
        # Regression from 2026-06-15 20s Chinese monitoring chunks 47-48.
        previous = (
            "哇，提前一天约都吃不上啊，因为我约的时候，我约的后两一样，我能走。好好好好。已经打车了，"
            "五块钱打过去。五五块钱。省着命。我们下一站打算去吃大众薄饼，那个呢是得提前预约。我提前三天约。"
        )
        candidate = (
            "哇，提前一天约都吃不上啊，因为我约的时候，我约的后两天已经满了，所以好好好好。已经打车了，"
            "五块钱打过去。五五块钱。省着命。我们下一家打算去吃大众薄饼，那个那是得提前预约。我提前三天约。"
            "哇，提前一天约都吃不上啊，因为我约的时候，我约的后两天已经满了，所以就只约到了今天。真火。"
        )

        preferred = _prefer_sentence_revision(previous, candidate)

        self.assertFalse(preferred.startswith("哇，提前一天约都吃不上啊"))
        self.assertIn("哇，提前一天约都吃不上啊，因为我约的时候，我约的后两天已经满了，所以就只约到了今天", preferred)

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

    def test_final_sentence_translation_skips_unstable_chinese_outputs(self) -> None:
        self.assertFalse(_should_translate_final_sentence("Not a.", "zh"))
        self.assertFalse(_should_translate_final_sentence("蒸牛。", "zh"))
        self.assertFalse(_should_translate_final_sentence("要 去 找", "zh"))
        self.assertFalse(
            _should_translate_final_sentence(
                "它这边厉害，因为肉在这边，所以它就会变得有点难剥。对，章鱼饼超适合配G配Y T的时候吃，因为它很刷脆。",
                "zh",
            )
        )
        self.assertTrue(_should_translate_final_sentence("我跟你说，就这一 得脱鞋！哇，它是楼梯好高啊。", "zh"))
        self.assertTrue(_should_translate_final_sentence("第一个呢要登陆的呢就是滴滴，滴滴呢就是来中国，你要搭车的话，你就可以搭滴滴。", "zh"))
        self.assertTrue(_should_translate_final_sentence("面可是快速面就是它会比较q一点，这个呢是比快速。", "zh"))

    def test_stage_boundary_candidate_blocks_spaced_cjk_from_monitoring(self) -> None:
        self.assertFalse(
            _should_stage_boundary_candidate(
                "见 路 是 一 个 二 十 站 的 行 程 好 六 点 二 十 我 想 三 点 多 左 右 有 可 以 等 我 可 以 得 到 放",
                "zh",
            )
        )
        self.assertFalse(_should_stage_boundary_candidate("Good morning.", "zh"))
        self.assertTrue(_should_stage_boundary_candidate("目前是四点三十八分，所有人都是回程的，跟我们一样是要去的。", "zh"))
        self.assertTrue(_should_stage_boundary_candidate("面可是快速面就是它会比较q一点，这个呢是比快速。", "zh"))

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

    def test_unconfirmed_replaced_stage_finalizes_confirmed_sentences(self) -> None:
        self.assertTrue(_should_finalize_replaced_sentence("확정 후보입니다", "다른 후보입니다", 3, False, 0))
        self.assertTrue(_should_finalize_replaced_sentence("강제 확정 후보입니다", "다른 후보입니다", 4, True, 0))

    def test_unconfirmed_replaced_stage_waits_for_observation_age(self) -> None:
        self.assertFalse(_should_finalize_replaced_sentence("Aged candidate", "Different candidate", 1, False, 1))
        self.assertTrue(_should_finalize_replaced_sentence("Aged candidate", "Different candidate", 1, False, 3))
        self.assertFalse(_should_finalize_replaced_sentence("Forced aged candidate", "Different candidate", 1, True, 3))
        self.assertTrue(_should_finalize_replaced_sentence("Forced aged candidate", "Different candidate", 1, True, 4))

    def test_open_korean_clause_does_not_confirm_from_repeated_candidate(self) -> None:
        # Regression from 2026-06-13 monitoring chunks 54-55. The same open
        # Korean clause repeated twice, but it was only the head of the next sentence.
        self.assertFalse(_should_confirm_staged_sentence("이 두 직업은", 2, False))
        self.assertFalse(_should_confirm_staged_sentence("그런데 보면 최치PD가 등장하기", 4, True))
        self.assertTrue(_should_confirm_staged_sentence("신규 채용을 안 하고 있습니다.", 3, False))

    def test_short_cjk_without_end_marker_does_not_confirm_when_repeated(self) -> None:
        self.assertFalse(_should_confirm_staged_sentence("哇哇它为什么老麻", 3, False))
        self.assertTrue(_should_confirm_staged_sentence("哇哇它为什么老麻。", 3, False))

    def test_short_cjk_no_end_marker_does_not_finalize_from_dumpling_log(self) -> None:
        cases = [
            "它一根一半就是我的食指皮薄肉馅超级",
            "多来听一下这声音哦",
        ]
        for staged in cases:
            with self.subTest(staged=staged):
                self.assertIn("no_end_marker", _final_sentence_diagnostic_flags(staged, "zh"))
                self.assertFalse(_should_confirm_staged_sentence(staged, 3, False))
                self.assertFalse(
                    _should_finalize_before_replacement(
                        staged,
                        "zh",
                        staged_confirmations=1,
                        staged_age=3,
                        sentence_finalize_age=3,
                    )
                )

    def test_cjk_without_end_marker_does_not_confirm_by_repetition(self) -> None:
        staged = "好大一棵果然皇上的园子里都是不一般的植物我觉得大家如果来西安的话可以到这个兴庆宫逛一逛"

        self.assertFalse(_should_confirm_staged_sentence(staged, 3, False))
        self.assertFalse(_should_confirm_staged_sentence(staged, 4, True))
        self.assertFalse(
            _should_finalize_before_replacement(
                staged,
                "zh",
                staged_confirmations=1,
                staged_age=3,
                sentence_finalize_age=3,
            )
        )
        self.assertFalse(
            _should_finalize_before_replacement(
                staged,
                "zh",
                staged_confirmations=2,
                staged_age=0,
                sentence_finalize_age=3,
            )
        )

    def test_replaced_confirmed_cjk_without_end_marker_can_finalize(self) -> None:
        staged = "股东自自食其力啊它这是牛杂锅啊你滋滋声就大锅很香啊说拿这个汤泡饭很顺吃的先尝一小口哦先尝一小口"
        candidate = "这个汤泡饭很顺吃的先尝一小口哦先尝一小口之后再继续"

        self.assertEqual(_replacement_decision_reason(staged, candidate, 3, False, 0), "confirmed")
        self.assertFalse(_should_confirm_staged_sentence(staged, 3, False))
        self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 3, False, 0))

    def test_spaced_cjk_without_end_marker_does_not_finalize_from_monitoring(self) -> None:
        staged = "见 什 么 都 想 吃 这 可 怎 么 办 呀 我 看 见 大 闸 丸 了 人 刚 才 来 的 啊 肉 丸"
        candidate = "肉丸来了可以继续吃了"

        self.assertIn("spaced_cjk", _final_sentence_diagnostic_flags(staged, "zh"))
        self.assertFalse(_should_confirm_staged_sentence(staged, 3, False))
        self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 3, False, 0))

    def test_repeated_cjk_ngram_does_not_confirm_from_monitoring(self) -> None:
        # Regression from 2026-06-15 10s Chinese monitoring chunk 83.
        # The STT candidate repeated long internal spans and should not be
        # treated as a clean final sentence only because it was observed enough.
        staged = (
            "招牌咖喱面，然后再喝一个阿玛胡药招牌咖喱面，然后再喝一个阿玛胡耀诗，石耀虎胡耀诗，"
            "米然后再喝一个阿玛胡耀诗，师耀虎胡耀诗，米粉餐面，两餐，好，我再给胡药师，师咬虎胡药师，"
            "米粉掺面，两餐，好，我再给你找一家吃的啊，咱现白老师，米粉掺面，两掺。好，我再给你找一家吃的啊。"
            "咱现在还差一家，现找。"
        )

        self.assertIn("cjk_repeated_ngram", _final_sentence_diagnostic_flags(staged, "zh"))
        self.assertFalse(_should_confirm_staged_sentence(staged, 3, False))
        self.assertFalse(_should_translate_final_sentence(staged, "zh"))

    def test_cjk_revision_prefers_clean_stage_over_repeated_ngram_candidate_from_monitoring(self) -> None:
        # Regression from 2026-06-15 monitoring chunks 417-418. A later window
        # restarted inside the same utterance and produced a longer candidate,
        # but that candidate contained a repeated CJK span.
        staged = (
            "对对对，所以它比较咸，你一定要配饭吃。我再把它拿起来，来直接拿起来，然后挤。"
            "它非常制好挤。上面直接挤在这碗。对对对对。"
        )
        candidate = (
            "好你一定要配饭的吃，我再把它拿起来来直接拿起来然后挤，它非常之好挤，"
            "上面直接挤在这碗，对对对对对，好你挤吧，它它很我再把它拿起来，来直接拿起来，"
            "然后挤。它非常之好挤，上面直接挤在纸碗。对对对对。好，你挤吧。它很烂。"
        )

        self.assertTrue(_sentences_are_revisions(staged, candidate))
        self.assertIn("cjk_repeated_ngram", _final_sentence_diagnostic_flags(candidate, "zh"))
        self.assertNotIn("cjk_repeated_ngram", _final_sentence_diagnostic_flags(staged, "zh"))
        self.assertEqual(_prefer_sentence_revision(staged, candidate), staged)

    def test_pending_cjk_ngram_repetition_is_diagnosed_from_monitoring(self) -> None:
        # Regression from 2026-06-15 16s/1s Chinese monitoring chunks 26-28.
        # No completed sentence was produced, while the pending tail kept
        # accumulating repeated CJK spans.
        pending = (
            "干里面得这么吃，把干里面盛勺子里，进我这吃的就是像那觉得乒乓球一样，"
            "干面得这么吃，把干面盛勺子里，进去再快点汤手一样，干面得这么吃，"
            "把干面盛勺子里，进去再快点汤，干粒面得这么吃，把干粒面盛勺子里，进去再快点汤，"
        )

        flags = _pending_text_diagnostic_flags(pending, "zh", 4)

        self.assertIn("cjk_repeated_ngram", flags)

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
            "unconfirmed",
        )
        self.assertEqual(
            _replacement_decision_reason("Aged candidate", "Different candidate", 1, False, 3),
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
        self.assertIn("cjk_internal_gap", _final_sentence_diagnostic_flags("我跟你说，就这一 得脱鞋！哇，它是楼梯好高啊。", "zh"))
        self.assertEqual(
            _final_sentence_diagnostic_flags("看起来好好吃啊，你真的有很多小吃呢，我看到。", "zh"),
            (),
        )

    def test_transcript_metrics_format_is_stable_for_log_analysis(self) -> None:
        self.assertEqual(_format_transcript_metrics({}), "none")
        self.assertEqual(
            _format_transcript_metrics({"stage_revision": 2, "stage_start": 3, "stage_replaced_unconfirmed": 0}),
            "stage_revision=2,stage_start=3",
        )

    def test_sentence_confirmation_waits_for_revision_windows(self) -> None:
        self.assertEqual(_sentence_required_confirmations(False), 3)
        self.assertEqual(_sentence_max_age_chunks(False), 3)
        self.assertEqual(_sentence_required_confirmations(True), 4)
        self.assertEqual(_sentence_max_age_chunks(True), 4)

    def test_unconfirmed_replaced_stage_blocks_single_observation_misrecognition_from_log(self) -> None:
        # Regression from avc-whisper.log chunk 48 and 2026-06-13 monitoring chunks 991-992.
        # The staged text was a one-window misrecognition. Committing it before
        # the next revision opportunity produces duplicated final sentences.
        staged = "의장들이 나와서 달러를 홍보를 합니다"
        candidate = "빨라를 홍보를 합니다"

        self.assertFalse(_sentences_are_revisions(staged, candidate))
        self.assertEqual(_replacement_decision_reason(staged, candidate, 1, False, 0), "unconfirmed")
        self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

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

    def test_unconfirmed_replaced_stage_suppresses_tail_echo_from_log(self) -> None:
        # Regression from avc-whisper.log chunk 76. The first candidate contains prior-sentence tail echo.
        staged = "근데 우리가 그런 얘기하지 골적으로 얘기하지 않죠"
        candidate = "우리가 그런 얘기하지 않습니다"

        self.assertFalse(_sentences_are_revisions(staged, candidate))
        self.assertFalse(_should_finalize_replaced_sentence(staged, candidate, 1, False, 0))

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

    def test_sentence_pending_overrun_ignores_short_fast_fragment(self) -> None:
        pending = "this is a quick sentence fragment that keeps going without punctuation and should not be forced too early"

        self.assertEqual(_pending_overrun_reason(pending, 4), "")

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
        # no spaces, so lifecycle decisions must keep a non-empty token set.
        staged = "他给出了两个拒绝绑匪要求。"
        revised = "他给出了两个拒绝绑匪要求的理由，从。"

        self.assertTrue(_sentences_are_revisions(staged, revised))
        self.assertEqual(_prefer_sentence_revision(staged, revised), revised)
        self.assertNotEqual(_replacement_decision_reason(staged, revised, 1, False, 0), "empty")

    def test_chinese_unconfirmed_stage_can_age_finalize_from_no_speech_gap(self) -> None:
        # 2026-06-16 policy: CJK staged sentences also age. Otherwise replacement
        # churn keeps most Chinese sentences provisional and prevents final output.
        staged = "他给出了两个拒绝绑匪要求的理由，从。"

        self.assertTrue(_should_age_staged_sentence(staged, ""))
        self.assertEqual(
            _replacement_decision_reason(staged, "保羅蓋蒂的這個說法是對的從古到今。", 1, False, 2),
            "unconfirmed_cjk",
        )
        self.assertFalse(
            _should_finalize_replaced_sentence(staged, "保羅蓋蒂的這個說法是對的從古到今。", 1, False, 2)
        )
        self.assertTrue(
            _should_finalize_replaced_sentence(staged, "保羅蓋蒂的這個說法是對的從古到今。", 1, False, 3)
        )

    def test_chinese_short_fragment_waits_for_age_before_replacement_finalize(self) -> None:
        # Regression from 2026-06-16 zh monitoring. The simplified lifecycle
        # improved final generation but over-finalized short fragments before a
        # better replacement had time to appear.
        short_fragments = ["就是他", "个 吗", "排 排 排 这 个 吗"]
        for fragment in short_fragments:
            with self.subTest(fragment=fragment):
                self.assertFalse(_should_finalize_before_replacement(fragment, "zh"))
                self.assertFalse(
                    _should_finalize_replaced_sentence(
                        fragment,
                        "那个枕头有点太硬了，就是是不是以后都要自己带自己的枕头？",
                        1,
                        False,
                        2,
                    )
                )
                self.assertFalse(
                    _should_finalize_replaced_sentence(
                        fragment,
                        "那个枕头有点太硬了，就是是不是以后都要自己带自己的枕头？",
                        1,
                        False,
                        3,
                    )
                )
                self.assertFalse(
                    _should_finalize_before_replacement(
                        fragment,
                        "zh",
                        staged_confirmations=1,
                        staged_age=3,
                        sentence_finalize_age=3,
                    )
                )

    def test_short_cjk_with_end_marker_gets_extra_replacement_hold_for_confirmation(self) -> None:
        staged = "对，人好多哦。"
        candidate = "人超多。"

        self.assertEqual(_replacement_decision_reason(staged, candidate, 1, False, 2, 2), "unconfirmed_cjk")
        self.assertEqual(_replacement_decision_reason(staged, candidate, 1, False, 3, 2), "unconfirmed_cjk")
        self.assertEqual(_replacement_decision_reason(staged, candidate, 1, False, 4, 2), "aged")

    def test_cjk_similarity_drives_revision_and_confirmation_for_short_corrections(self) -> None:
        self.assertTrue(_sentences_are_revisions("对的，还超多。", "超多！"))
        self.assertTrue(_sentences_are_revisions("好好大饭，好大。", "好好大，好大。"))
        self.assertTrue(_sentences_are_revisions("现在人潮反而凶。", "现在人潮反而汹涌。"))
        self.assertTrue(_sentences_are_revisions("我的T蛮。", "我的T money。"))
        self.assertEqual(_next_revision_confirmation_count("现在人潮反而凶。", "现在人潮反而汹涌。", 1), 2)
        self.assertEqual(_next_revision_confirmation_count("我的T蛮。", "我的T money。", 1), 2)

    def test_chinese_complete_sentence_can_finalize_before_replacement(self) -> None:
        self.assertFalse(
            _should_finalize_before_replacement(
                "那个枕头有点太硬了，就是是不是以后都要自己带自己的枕头？",
                "zh",
            )
        )
        self.assertTrue(
            _should_finalize_before_replacement(
                "那个枕头有点太硬了，就是是不是以后都要自己带自己的枕头？",
                "zh",
                staged_confirmations=3,
                staged_age=0,
                sentence_finalize_age=3,
            )
        )
        self.assertFalse(
            _should_finalize_before_replacement(
                "也没有要买什么东西就只是走进去再走出来拍个照片这样拍个进去出来",
                "zh",
                staged_confirmations=2,
                staged_age=0,
                sentence_finalize_age=3,
            )
        )
        self.assertTrue(
            _should_finalize_before_replacement(
                "不重要，这种东西不用管它什么时候用得到。",
                "zh",
                staged_confirmations=1,
                staged_age=3,
                sentence_finalize_age=3,
            )
        )

    def test_chinese_similar_final_alternative_is_recent_echo_from_log(self) -> None:
        cases = [
            (
                "这个也是，这个是，这也是，这个是上面是扁的。",
                "哎，大家这边可以这个也是，这个是，这个是，这个是上面是扁的。",
            ),
            (
                "哎，那你看你刚刚帮我刷，你哇，这很有诚意吧？",
                "哎，那你要你刚刚帮我刷，你你看到台啊，这很有诚意吧？",
            ),
        ]
        for recent, candidate in cases:
            with self.subTest(candidate=candidate):
                self.assertTrue(_is_recent_final_echo(candidate, recent, "zh"))

    def test_distinct_chinese_sentence_is_not_recent_echo(self) -> None:
        self.assertFalse(
            _is_recent_final_echo(
                "六百八这样子一杯，好啦，就是当做在喝星巴克啊。",
                "对啊，星巴克的概念。",
                "zh",
            )
        )

    def test_chinese_recent_final_extension_outputs_only_new_suffix(self) -> None:
        candidate = "对，经过了无数的规毛，然后又怕发生跟外婆家一样的事件，就不要点太多。"
        recent = "对，经过了无数的龟毛，然后又怕发生跟外婆。"

        output, source = _recent_final_output_delta(candidate, (recent,), "zh")

        self.assertEqual(source, recent)
        self.assertEqual(output, "家一样的事件就不要点太多。")

    def test_chinese_recent_final_exact_echo_is_suppressed(self) -> None:
        recent = "外面的座位区差不多就是这样。"

        output, source = _recent_final_output_delta(recent, (recent,), "zh")

        self.assertEqual(source, recent)
        self.assertEqual(output, "")

    def test_chinese_recent_final_internal_overlap_suppresses_repeated_variant(self) -> None:
        recent = "哎，粉丝啊，超级松软，蛋超级多，蛋是超多，有没有选？"
        candidate = "哦，它蛋超多哎，煮丝啊，超级松软，蛋超级多，特别超多。"

        output, source = _recent_final_output_delta(candidate, (recent,), "zh")

        self.assertEqual(source, recent)
        self.assertEqual(output, "")

    def test_chinese_recent_final_internal_overlap_suppresses_no_suffix_variant(self) -> None:
        recent = "超级松软，但超级多，特别超多，有没有觉得？"
        candidate = "哦，它蛋超多哎，煮丝啊，超级松软，蛋超级多，特别超多。"

        output, source = _recent_final_output_delta(candidate, (recent,), "zh")

        self.assertEqual(source, recent)
        self.assertEqual(output, "")


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

    def test_boundary_candidate_filters_low_value_cjk_fragments(self) -> None:
        self.assertTrue(_should_finalize_boundary_candidate("西 门 泾 的", "zh"))
        self.assertTrue(_should_finalize_boundary_candidate("我现在顶", "zh", 3, False))
        self.assertFalse(_should_finalize_boundary_candidate("好 玩", "zh"))
        self.assertTrue(_should_finalize_boundary_candidate("你觉得什么西门町的？", "zh"))
        self.assertFalse(_should_finalize_boundary_candidate("你觉得什么西门町的？", "zh", 1, False))
        self.assertTrue(_should_finalize_boundary_candidate("你觉得什么西门町的？", "zh", 3, False))

    def test_committed_chinese_prefix_is_removed_from_next_output_delta(self) -> None:
        committed = "不重要，这种东西不用管它什么时候用得到。"
        candidate = "不重要，这种东西不用管它什么时候用得到。哎，好酷啊！对呀，我买的弓箭。"

        self.assertEqual(
            _sentence_output_delta(committed, candidate),
            "哎，好酷啊！对呀，我买的弓箭。",
        )

    def test_chinese_prefix_revision_prefers_extended_candidate_before_final(self) -> None:
        staged = "不重要，这种东西不用管它什么时候用得到。"
        candidate = "不重要，这种东西不用管它什么时候用得到。哎，好酷啊！等一下，有那种东西啊，什么时候？"

        self.assertTrue(_sentences_are_revisions(staged, candidate))
        self.assertEqual(_prefer_sentence_revision(staged, candidate), candidate)
        self.assertEqual(_next_revision_confirmation_count(staged, candidate, 2), 1)

    def test_changed_cjk_revision_resets_age_from_gs25_log(self) -> None:
        staged = "那个咖啡二十五是做咖啡。"
        preferred = "那个咖啡二十五是做咖啡的然后这边。"

        self.assertTrue(_sentences_are_revisions(staged, preferred))
        self.assertEqual(_next_revision_confirmation_count(staged, preferred, 2, 0.90, 69, "common_prefix"), 1)
        self.assertTrue(_should_reset_revision_age(staged, preferred, 0.90, 69, "common_prefix"))

def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WhisperSentenceRevisionTest)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors
    print(
        "[dictation-ai-sentence-revision-tracking] "
        f"cases={total} passed={passed} failures={failures} errors={errors} "
        "quality_gate=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

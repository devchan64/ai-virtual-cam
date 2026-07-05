import unittest

from src.app.dictation_core.dictation_transcript_logic import (
    _is_ko_short_closed_sentence,
    _prefer_sentence_revision,
    _stale_leading_short_closed_candidate_reason,
    _should_allow_no_text_stage_aging,
    _should_suppress_ko_numeric_aged_final_with_queue,
    _should_suppress_ko_pure_latin_final_with_hangul_queue,
    _should_suppress_right_context_short_prefix_extension_with_single_queue,
    _should_enable_aged_queue_backlog_promotion_boost,
    _should_defer_short_closed_queue_quality_block,
    _should_finalize_before_replacement,
    _should_finalize_with_right_context,
    _should_suppress_ko_short_closed_final_with_stronger_queue_candidate,
    _should_restore_trimmed_closed_candidate,
    _should_suppress_aged_low_value_final,
    _should_suppress_aged_no_end_marker_queue_final,
)


class DictationStagePolicyTest(unittest.TestCase):
    def test_prefers_compact_hangul_no_end_revision_over_stale_longer_tokenization(self) -> None:
        self.assertEqual(
            _prefer_sentence_revision(
                "패권 전쟁이 반도체 하고 ai 로 국한이 될 것이냐 아니면 전략산업으로 방법이 되지 않겠는가",
                "패권 전쟁이 반도체하고 AI로 국한이 될 것이냐 아니면 전략산업으로 확장이 될 것이냐",
            ),
            "패권 전쟁이 반도체하고 AI로 국한이 될 것이냐 아니면 전략산업으로 확장이 될 것이냐",
        )

    def test_keeps_longer_hangul_no_end_sentence_when_right_is_too_short(self) -> None:
        self.assertEqual(
            _prefer_sentence_revision(
                "심지어는 그쪽에 더 많은 인력 양성을 해야 하는 해외 학교들의 분교도 많이 생길 수밖에 없을 거예요",
                "심지어는 그쪽에 더 많은 인력 양성을 해야 하는",
            ),
            "심지어는 그쪽에 더 많은 인력 양성을 해야 하는 해외 학교들의 분교도 많이 생길 수밖에 없을 거예요",
        )

    def test_detects_ko_short_closed_sentence(self) -> None:
        self.assertTrue(_is_ko_short_closed_sentence("네.", "ko"))

    def test_ignores_ko_short_no_end_fragment_for_closed_sentence_detection(self) -> None:
        self.assertFalse(_is_ko_short_closed_sentence("어 뭐", "ko"))

    def test_suppresses_short_latin_only_zh_aged_final_with_non_latin_queue(self) -> None:
        self.assertTrue(
            _should_suppress_aged_low_value_final(
                "B T S。",
                "zh",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                deferred_revision_sentences=("带我们进不到访的B T S，就是你，就是你，就是你。",),
            )
        )

    def test_keeps_short_latin_only_zh_aged_final_with_latin_only_queue(self) -> None:
        self.assertFalse(
            _should_suppress_aged_low_value_final(
                "OK OK。",
                "zh",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                deferred_revision_sentences=("Please don't go.", "Please stay home."),
            )
        )

    def test_suppresses_no_flag_zh_aged_final_when_queue_has_no_end_marker(self) -> None:
        self.assertTrue(
            _should_suppress_aged_no_end_marker_queue_final(
                "你自己去，我要去饭店休息。",
                "zh",
                "aged",
                staged_confirmations=1,
                deferred_revision_sentences=(
                    "第一家就是了。",
                    "我本来跟雅群说啊，我好累哦，就是晚上民众的部分",
                    "然后雅群就。",
                ),
            )
        )

    def test_defers_short_closed_zh_quality_block_with_single_long_closed_queue(self) -> None:
        self.assertTrue(
            _should_defer_short_closed_queue_quality_block(
                "再点一颗。",
                "zh",
                ("然后蛋煎很好，大蒜土司，然后蛋。",),
                staged_confirmations=2,
            )
        )

    def test_does_not_defer_three_unit_short_closed_zh_quality_block_with_single_long_closed_queue(self) -> None:
        self.assertFalse(
            _should_defer_short_closed_queue_quality_block(
                "就好了。",
                "zh",
                ("但是因为我们要退税，所以我们要排队。",),
                staged_confirmations=2,
            )
        )

    def test_keeps_no_flag_zh_aged_final_when_queue_has_no_closed_sentence(self) -> None:
        self.assertFalse(
            _should_suppress_aged_no_end_marker_queue_final(
                "刚刚那一间贝狗店，我觉得蛮不错的。",
                "zh",
                "aged",
                staged_confirmations=1,
                deferred_revision_sentences=(
                    "它的贝狗不是那种特别扎实的，所以如果只是经过想要吃一个小东西，不要太饱的话，我觉得是蛮。",
                    "我点的是橄榄的，然后里面主要是油底的。",
                ),
            )
        )

    def test_enables_aged_queue_backlog_promotion_boost_for_large_backlog(self) -> None:
        self.assertTrue(_should_enable_aged_queue_backlog_promotion_boost("aged", 3, "zh"))

    def test_does_not_enable_aged_queue_backlog_promotion_boost_for_small_backlog(self) -> None:
        self.assertFalse(_should_enable_aged_queue_backlog_promotion_boost("aged", 2, "zh"))

    def test_does_not_enable_aged_queue_backlog_promotion_boost_for_non_zh(self) -> None:
        self.assertFalse(_should_enable_aged_queue_backlog_promotion_boost("aged", 3, "en"))

    def test_allows_no_text_stage_aging_for_zh_closed_stage(self) -> None:
        self.assertTrue(_should_allow_no_text_stage_aging("是我的错觉吗？", "zh", ()))

    def test_allows_no_text_stage_aging_for_ko_single_clean_queue(self) -> None:
        self.assertTrue(
            _should_allow_no_text_stage_aging(
                "그런데 갑자기 미국이 우리 안 사 해버리니까 이거 자칫 잘못하면 줄도산이 될 수 있는 거거든요.",
                "ko",
                ("그러니 어떻게든 경제성장률 10%를 우리가 달성할 수 있는 거죠.",),
            )
        )

    def test_allows_no_text_stage_aging_for_ko_three_unit_question_with_single_queue(self) -> None:
        self.assertTrue(
            _should_allow_no_text_stage_aging(
                "참내 영어 못하세요?",
                "ko",
                ("뭐가?",),
            )
        )

    def test_blocks_no_text_stage_aging_for_ko_three_unit_statement_with_single_queue(self) -> None:
        self.assertFalse(
            _should_allow_no_text_stage_aging(
                "아 씨 어떡해.",
                "ko",
                ("누구.. 어.",),
            )
        )

    def test_allows_no_text_stage_aging_for_ko_two_short_closed_queue(self) -> None:
        self.assertTrue(
            _should_allow_no_text_stage_aging(
                "참내 영어 못하세요?",
                "ko",
                ("오 라임 지렸어.", "뭐가?"),
            )
        )

    def test_blocks_no_text_stage_aging_for_ko_two_short_queue_with_single_word_stage(self) -> None:
        self.assertFalse(
            _should_allow_no_text_stage_aging(
                "90년대생이신가요?",
                "ko",
                ("맞혀보시겠어요?", "그건 아닌데."),
            )
        )

    def test_blocks_no_text_stage_aging_for_ko_long_multi_queue(self) -> None:
        self.assertFalse(
            _should_allow_no_text_stage_aging(
                "불편하시니까.",
                "ko",
                ("내가 이거보다 훨씬 안 좋았어.", "거짓말하지 마, 선배."),
            )
        )

    def test_blocks_right_context_finalize_when_queue_has_preferred_ko_revision(self) -> None:
        self.assertFalse(
            _should_finalize_with_right_context(
                "고용하고 일부 중국인들 넘어와서 베트남에 생산해서 미국에 보내고 다른 나라에 보냈던 일을 했는데 미국이 베트남 것도 보겠다는 거잖아요.",
                "ko",
                ("미국이 베트남 것도 보겠다는 거잖아요.",),
            )
        )

    def test_keeps_right_context_finalize_for_independent_ko_queue_sentence(self) -> None:
        self.assertTrue(
            _should_finalize_with_right_context(
                "사실 한국이 이미 이런 경험이 있어요.",
                "ko",
                ("80년대 후반에서 90년대 초반에 저희가 16메가 D램 공동 개발 사업이 있었습니다.",),
            )
        )

    def test_blocks_right_context_finalize_for_same_chunk_promoted_unrelated_short_queue(self) -> None:
        self.assertFalse(
            _should_finalize_with_right_context(
                "나 그냥 막 이렇게 들어왔는데 그냥 막 집에 쳐들어온다니까.",
                "ko",
                ("스토크 게임 좋아하세요?",),
                promoted_from_queue_same_chunk=True,
            )
        )

    def test_keeps_right_context_finalize_for_same_chunk_promoted_duplicate_queue(self) -> None:
        self.assertTrue(
            _should_finalize_with_right_context(
                "뷔페가 전혀 뷔페 없는 느낌인데?",
                "ko",
                ("뷔페가 전혀 뷔페 없는 느낌인데?",),
                promoted_from_queue_same_chunk=True,
            )
        )

    def test_keeps_right_context_finalize_for_same_chunk_promoted_unrelated_long_queue(self) -> None:
        self.assertTrue(
            _should_finalize_with_right_context(
                "UMC나 PSMC나 이런 벵거드.",
                "ko",
                ("사실 벵거드는 TSMC의 자회사.",),
                promoted_from_queue_same_chunk=True,
            )
        )

    def test_blocks_age_finalize_when_queue_has_preferred_ko_revision(self) -> None:
        self.assertFalse(
            _should_finalize_before_replacement(
                "고용하고 일부 중국인들 넘어와서 베트남에 생산해서 미국에 보내고 다른 나라에 보냈던 일을 했는데 미국이 베트남 것도 보겠다는 거잖아요.",
                "ko",
                staged_confirmations=1,
                staged_age=2,
                sentence_finalize_age=1,
                staged_forced=False,
                deferred_revision_sentences=("미국이 베트남 것도 보겠다는 거잖아요.",),
            )
        )

    def test_blocks_finalize_before_replacement_for_restart_like_repeat_sentence(self) -> None:
        self.assertFalse(
            _should_finalize_before_replacement(
                "그 말은 기술 차이나 성능 차이 그 말은 기술 차이나 성능 차이나 이런 것에서 차이가 날 수밖에 없다는 거죠.",
                "ko",
                staged_confirmations=1,
                staged_age=2,
                sentence_finalize_age=3,
                staged_forced=False,
                deferred_revision_sentences=(),
            )
        )

    def test_keeps_finalize_before_replacement_for_clean_sentence(self) -> None:
        self.assertTrue(
            _should_finalize_before_replacement(
                "80년대 후반에서 90년대 초반에 저희가 16메가 D램 공동 개발 사업이 있었습니다.",
                "ko",
                staged_confirmations=1,
                staged_age=1,
                sentence_finalize_age=3,
                staged_forced=False,
                deferred_revision_sentences=(),
            )
        )

    def test_keeps_finalize_before_replacement_for_non_restart_repeat_sentence(self) -> None:
        self.assertTrue(
            _should_finalize_before_replacement(
                "아니 무슨 놀이공원 집회사 집회사입니다.",
                "ko",
                staged_confirmations=1,
                staged_age=1,
                sentence_finalize_age=3,
                staged_forced=False,
                deferred_revision_sentences=(),
            )
        )

    def test_restores_trimmed_short_closed_ko_sentence(self) -> None:
        self.assertTrue(
            _should_restore_trimmed_closed_candidate(
                "1920년대 미국의 본격적인 호환기거입니다.",
                "호환기거입니다",
                "ko",
            )
        )

    def test_does_not_restore_trimmed_longer_ko_suffix_sentence(self) -> None:
        self.assertFalse(
            _should_restore_trimmed_closed_candidate(
                "지역에 따라 상품에 따라 완전히 다른 시장이에요.",
                "완전히 다른 시장이에요",
                "ko",
            )
        )

    def test_defers_short_closed_zh_queue_quality_block_for_single_short_queue(self) -> None:
        self.assertTrue(
            _should_defer_short_closed_queue_quality_block(
                "是我的错觉吗？",
                "zh",
                ("我就。",),
                staged_confirmations=2,
            )
        )

    def test_defers_short_closed_zh_queue_quality_block_for_multi_short_queue_after_repeat(self) -> None:
        self.assertTrue(
            _should_defer_short_closed_queue_quality_block(
                "是我的错觉吗？",
                "zh",
                ("我就。", "我觉得在这边。"),
                staged_confirmations=2,
            )
        )

    def test_does_not_defer_short_closed_zh_queue_quality_block_before_repeat(self) -> None:
        self.assertFalse(
            _should_defer_short_closed_queue_quality_block(
                "是我的错觉吗？",
                "zh",
                ("我就。",),
                staged_confirmations=1,
            )
        )

    def test_suppresses_short_closed_prefix_before_active_stage_repeat(self) -> None:
        self.assertEqual(
            _stale_leading_short_closed_candidate_reason(
                "있었네?",
                "ko",
                later_completed_sentences=("왜 이렇게 얼굴 보기 힘들어?",),
                active_stage_sentence="왜 이렇게 얼굴 보기 힘들어?",
                recent_final_sentences=(),
            ),
            "active_stage_later_repeat",
        )

    def test_keeps_repeated_short_closed_candidate_with_same_later_repeat(self) -> None:
        self.assertEqual(
            _stale_leading_short_closed_candidate_reason(
                "원몰!",
                "ko",
                later_completed_sentences=("원몰!", "참내 영어 못하세요?"),
                active_stage_sentence="참내 영어 못하세요?",
                recent_final_sentences=(),
            ),
            "",
        )

    def test_suppresses_short_closed_prefix_before_recent_final_repeat(self) -> None:
        self.assertEqual(
            _stale_leading_short_closed_candidate_reason(
                "쪼옹!",
                "ko",
                later_completed_sentences=("있었네?", "왜 이렇게 얼굴 보기 힘들어?"),
                active_stage_sentence="",
                recent_final_sentences=("왜 이렇게 얼굴 보기 힘들어?",),
            ),
            "recent_final_later_repeat",
        )

    def test_suppresses_short_closed_ko_aged_final_with_stronger_queue_confirmation(self) -> None:
        self.assertTrue(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "정말 맞습니다.",
                "ko",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "그래서 이런 여러 가지 각각의 이유들로 인해서 지금 동남아 국가들이 선택은 저마다 다른 거예요.", "confirmations": 2},
                    {"sentence": "상황도 다르고 대책도 다르고.", "confirmations": 1},
                ),
            )
        )

    def test_keeps_single_unit_ko_aged_final_with_only_one_stronger_queue_candidate(self) -> None:
        self.assertFalse(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "원몰!",
                "ko",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "참내 영어 못하세요?", "confirmations": 2},
                    {"sentence": "오 라임 지렸어.", "confirmations": 1},
                    {"sentence": "뭐가?", "confirmations": 1},
                ),
            )
        )

    def test_suppresses_single_unit_ko_aged_final_with_stronger_two_item_queue(self) -> None:
        self.assertTrue(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "맞습니다.",
                "ko",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "그래서 이런 여러 가지 각각의 이유들로 인해서 지금 동남아 국가들이 선택은 저마다 다른 거예요.", "confirmations": 2},
                    {"sentence": "상황도 다르고 대책도 다르고.", "confirmations": 1},
                ),
            )
        )

    def test_keeps_short_closed_ko_aged_final_without_stronger_queue_confirmation(self) -> None:
        self.assertFalse(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "아 그럼 아니에요?",
                "ko",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "그래가지고 이거 내가 한 달 동안 돈 모아가지고 산 거예요", "confirmations": 1},
                    {"sentence": "할아범 방탱이가 알코올 중독자인 줄 알아요?", "confirmations": 1},
                ),
            )
        )

    def test_suppresses_single_unit_ko_aged_final_when_clean_closed_queue_bursts(self) -> None:
        self.assertTrue(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "뭐래요!",
                "ko",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "바보같애!", "confirmations": 1},
                    {"sentence": "토익 500점이죠?", "confirmations": 1},
                    {"sentence": "아이큐가 500인데요?", "confirmations": 1},
                    {"sentence": "500은 무슨?", "confirmations": 1},
                    {"sentence": "고백이나 하지 마요.", "confirmations": 1},
                ),
            )
        )

    def test_suppresses_single_unit_ko_statement_with_single_long_queue_candidate(self) -> None:
        self.assertTrue(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "그래요.",
                "ko",
                "aged",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "약간 글로벌 탑티어 약간 이런 느낌이네요.", "confirmations": 1},
                ),
            )
        )

    def test_suppresses_single_unit_ko_next_completed_statement_with_single_long_queue_candidate(self) -> None:
        self.assertTrue(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "네.",
                "ko",
                "next_completed",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "그렇지만 상황도 크게 보면.", "confirmations": 1},
                ),
            )
        )

    def test_suppresses_single_unit_ko_next_completed_statement_with_confirmation_two(self) -> None:
        self.assertTrue(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "네.",
                "ko",
                "next_completed",
                staged_confirmations=2,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "그렇지만 상황도 크게 보면.", "confirmations": 1},
                ),
            )
        )

    def test_keeps_longer_single_unit_ko_next_completed_statement_with_confirmation_two(self) -> None:
        self.assertFalse(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "안녕하세요.",
                "ko",
                "next_completed",
                staged_confirmations=2,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "저는 성인권 대학교에서 근무하고 있는 권석준이라고 합니다.", "confirmations": 1},
                ),
            )
        )

    def test_keeps_single_unit_ko_question_with_single_long_queue_candidate(self) -> None:
        self.assertFalse(
            _should_suppress_ko_short_closed_final_with_stronger_queue_candidate(
                "뭐가?",
                "ko",
                "next_completed",
                staged_confirmations=1,
                staged_forced=False,
                queued_entries=(
                    {"sentence": "딴 거 지른 거 아니죠?", "confirmations": 1},
                ),
            )
        )

    def test_suppresses_ko_pure_latin_aged_final_when_queue_has_hangul_sentence(self) -> None:
        self.assertTrue(
            _should_suppress_ko_pure_latin_final_with_hangul_queue(
                "Come on.",
                "ko",
                "aged",
                ("시스템 효과를 노려야 됩니다.",),
            )
        )

    def test_suppresses_right_context_short_prefix_extension_with_single_queue(self) -> None:
        self.assertTrue(
            _should_suppress_right_context_short_prefix_extension_with_single_queue(
                "작년에 지금 아직 안녕하세요.",
                "right_context",
                ("작년에 지금 아직 공식 통계가 나오지 않았죠.",),
            )
        )

    def test_keeps_right_context_short_sentence_without_prefix_extension(self) -> None:
        self.assertFalse(
            _should_suppress_right_context_short_prefix_extension_with_single_queue(
                "굳이 미국에서 봐도.",
                "right_context",
                ("이거는 어쨌든 싸게 만드는 게 남는 거니까.",),
            )
        )

    def test_suppresses_ko_pure_latin_replaced_aged_final_when_queue_has_hangul_sentence(self) -> None:
        self.assertTrue(
            _should_suppress_ko_pure_latin_final_with_hangul_queue(
                "There was like, you know, Narendra Modi up there suddenly telling everyone.",
                "ko",
                "replaced_aged",
                ("시스템 효과를 노려야 됩니다.", "그러는데 병목이라는 것은 다시 말하면 병목에 대해서 사람들이 더 많은 관심을 가질 수밖에 없어요"),
            )
        )

    def test_keeps_ko_hangul_aged_final_when_queue_has_hangul_sentence(self) -> None:
        self.assertFalse(
            _should_suppress_ko_pure_latin_final_with_hangul_queue(
                "왜냐하면 레가시니까.",
                "ko",
                "aged",
                ("레가시는 통제를 하지 않습니다.",),
            )
        )

    def test_keeps_ko_pure_latin_confirmed_final_when_queue_has_hangul_sentence(self) -> None:
        self.assertFalse(
            _should_suppress_ko_pure_latin_final_with_hangul_queue(
                "Come on.",
                "ko",
                "confirmed",
                ("시스템 효과를 노려야 됩니다.",),
            )
        )

    def test_suppresses_ko_numeric_aged_final_when_queue_remains(self) -> None:
        self.assertTrue(
            _should_suppress_ko_numeric_aged_final_with_queue(
                "3, 1, 3, 11인가?",
                "ko",
                "aged",
                ("기억이 헷갈려.", "1년?"),
            )
        )

    def test_keeps_ko_numeric_confirmed_final_when_queue_remains(self) -> None:
        self.assertFalse(
            _should_suppress_ko_numeric_aged_final_with_queue(
                "3, 1, 3, 11인가?",
                "ko",
                "confirmed",
                ("기억이 헷갈려.", "1년?"),
            )
        )

    def test_keeps_ko_single_numeric_token_aged_final_when_queue_remains(self) -> None:
        self.assertFalse(
            _should_suppress_ko_numeric_aged_final_with_queue(
                "3?",
                "ko",
                "aged",
                ("3일?", "31일인가?"),
            )
        )

    def test_keeps_ko_numeric_aged_final_when_queue_contains_long_sentence(self) -> None:
        self.assertFalse(
            _should_suppress_ko_numeric_aged_final_with_queue(
                "2시간이 지났는데, 거의 10밀리언 달러가 스톡에 투입되었습니다.",
                "ko",
                "aged",
                ("그냥 씻어버렸습니다.", "테일러신 아케이디스는 금은보기 타일럿이나 케이디 씨는 금흥 목요일에서 드러눔 봤죠."),
            )
        )

if __name__ == "__main__":
    unittest.main()

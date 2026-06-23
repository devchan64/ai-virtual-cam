import unittest

from src.app.sentence_boundary import SentenceBoundaryResult
from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _next_revision_confirmation_count,
    _prefer_sentence_revision,
    _recent_final_output_delta,
    _should_reset_revision_age,
    _should_stage_boundary_candidate,
)
from src.app.stable_token_detection import analyze_stable_window
from tests.eval.dictation_ai.cases.sbd_case_loader import SbdCase
from tests.eval.dictation_ai.sbd_benchmark import (
    LifecycleState,
    _finalize_staged_sentence,
    _run_lifecycle_case,
    _stage_completed_sentence,
)


class _CompletedDetector:
    backend = "unit"

    def split(self, pending_text: str, new_text: str, language: str = "en", *, boundary_confidence: float | None = None):
        return SentenceBoundaryResult(
            completed=[new_text],
            pending="",
            backend=self.backend,
            boundary_count=1,
            end_mark_count=1,
        )


class DictationAiSbdLifecycleTest(unittest.TestCase):
    def test_initial_final_context_seeds_memory_without_counting_as_actual_final(self) -> None:
        case = SbdCase(
            id="initial-final-context",
            language="en",
            chunks=["Already committed.", "New sentence.", "New sentence."],
            expected_completed=[],
            expected_pending="",
            expected_final=["New sentence."],
            expected_staged="",
            tags=("unit",),
            sentence_finalize_age=3,
            initial_final=("Already committed.",),
        )

        lifecycle = _run_lifecycle_case(case, _CompletedDetector())

        self.assertEqual(lifecycle["initial_final"], ["Already committed."])
        self.assertEqual(lifecycle["actual_final"], ["New sentence."])
        self.assertIn("Already committed.", lifecycle["committed_text"])
        self.assertIn("New sentence.", lifecycle["committed_text"])
        self.assertEqual(lifecycle["metrics"]["candidate_duplicate_suppressed"], 1)

    def test_broken_delta_suppression_retains_staged_candidate_for_revision(self) -> None:
        state = LifecycleState(
            language="zh",
            committed_text="大家好，鸡肉拌牛肉拌，",
            staged_sentence="大家好，鸡肉拌牛肉拌，这个川菜一定要",
            staged_confirmations=3,
            staged_age=2,
            staged_deferred_age_chunk=8,
        )

        finalized = _finalize_staged_sentence(state, "zh", "aged", 9)

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "大家好，鸡肉拌牛肉拌，这个川菜一定要")
        self.assertEqual(state.staged_confirmations, 3)
        self.assertEqual(state.staged_age, 2)
        self.assertEqual(state.staged_deferred_age_chunk, 8)
        self.assertEqual(state.staged_delta_suppressed_chunk_index, 9)
        self.assertEqual(state.metrics["finalize_delta_suppressed"], 1)
        self.assertEqual(state.metrics["finalize_delta_suppressed_stage_retained"], 1)
        self.assertNotIn("segment_state_suppressed", state.metrics)

    def test_broken_delta_suppression_counts_after_same_chunk_revision(self) -> None:
        state = LifecycleState(
            language="zh",
            committed_text="大家好，鸡肉拌牛肉拌，",
            staged_sentence="大家好，鸡肉拌牛肉拌，这个川菜一定要",
            staged_confirmations=3,
            staged_age=3,
            staged_deferred_age_chunk=9,
            staged_delta_suppressed_chunk_index=8,
        )

        finalized = _finalize_staged_sentence(state, "zh", "confirmed", 9)

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "大家好，鸡肉拌牛肉拌，这个川菜一定要")
        self.assertEqual(state.staged_deferred_age_chunk, 9)
        self.assertEqual(state.staged_delta_suppressed_chunk_index, 9)
        self.assertEqual(state.staged_delta_suppressed_chunks, 1)
        self.assertEqual(state.metrics["finalize_delta_suppressed"], 1)
        self.assertEqual(state.metrics["finalize_delta_suppressed_stage_retained"], 1)

    def test_repeated_broken_delta_suppression_drops_stale_staged_candidate(self) -> None:
        state = LifecycleState(
            language="zh",
            committed_text="大家好，鸡肉拌牛肉拌，",
            staged_sentence="大家好，鸡肉拌牛肉拌，这个川菜一定要",
            staged_confirmations=14,
            staged_age=13,
            staged_deferred_age_chunk=8,
            staged_delta_suppressed_chunks=1,
            staged_delta_suppressed_chunk_index=8,
        )

        finalized = _finalize_staged_sentence(state, "zh", "replaced_confirmed", 9)

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "")
        self.assertEqual(state.staged_delta_suppressed_chunks, 0)
        self.assertEqual(state.metrics["finalize_delta_suppressed"], 1)
        self.assertEqual(state.metrics["finalize_delta_suppressed_stage_dropped"], 1)
        self.assertEqual(state.metrics["segment_state_suppressed"], 1)
        self.assertNotIn("finalize_delta_suppressed_stage_retained", state.metrics)

    def test_delta_fragment_preservation_matches_runtime_lifecycle(self) -> None:
        state = LifecycleState(
            language="zh",
            committed_text="因为蛮多教学的，跟你们分享一下，",
            staged_sentence="跟你们分享一下我点的一些吃的。",
            staged_confirmations=3,
            staged_age=2,
            staged_deferred_age_chunk=66,
            staged_delta_suppressed_chunks=1,
            staged_delta_suppressed_chunk_index=66,
        )

        finalized = _stage_completed_sentence(
            state,
            "我点的一些吃的。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=67,
        )

        self.assertEqual(finalized, ["跟你们分享一下我点的一些吃的。"])
        self.assertEqual(state.staged_sentence, "")
        self.assertEqual(state.metrics["stage_revision"], 1)
        self.assertEqual(state.metrics["finalize_delta_fragment_preserved"], 1)
        self.assertEqual(state.metrics["finalized"], 1)
        self.assertNotIn("finalize_delta_suppressed", state.metrics)
        self.assertNotIn("finalize_delta_suppressed_stage_dropped", state.metrics)

    def test_recent_final_echo_suppression_matches_runtime_lifecycle_metric(self) -> None:
        state = LifecycleState(
            language="zh",
            staged_sentence="今天就早点休息，早点养精蓄锐。",
            staged_confirmations=3,
            staged_age=2,
            staged_deferred_age_chunk=20,
        )
        assert state.final_sentences is not None
        state.final_sentences.append("今天就早点休息，早点养精蓄锐。")

        finalized = _finalize_staged_sentence(state, "zh", "confirmed", 21)

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "")
        self.assertEqual(state.metrics["finalize_recent_echo_suppressed"], 1)
        self.assertEqual(state.metrics["segment_state_suppressed"], 1)
        self.assertNotIn("finalize_duplicate_suppressed", state.metrics)

    def test_same_chunk_promoted_stage_does_not_finalize_on_replacement(self) -> None:
        state = LifecycleState(
            language="zh",
            staged_sentence="看到我了吗？",
            staged_confirmations=5,
            staged_age=4,
            staged_deferred_age_chunk=9,
        )

        finalized = _stage_completed_sentence(
            state,
            "不要了，它有脚垫，它里面又很柔软。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=9,
        )

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "看到我了吗？")
        self.assertEqual(len(state.staged_queue or ()), 1)
        self.assertEqual((state.staged_queue or ())[0]["sentence"], "不要了，它有脚垫，它里面又很柔软。")
        self.assertEqual(state.metrics["stage_replace_deferred_same_chunk"], 1)
        self.assertNotIn("finalize_reason_replaced_confirmed", state.metrics)

    def test_revised_queue_candidate_can_finalize_after_promotion(self) -> None:
        state = LifecycleState(language="zh")
        assert state.staged_queue is not None
        state.staged_queue.append(
            {
                "sentence": "可以下一个就是裤子啦。",
                "confirmations": 3,
                "age": 2,
                "forced": False,
                "deferred_age_chunk": 8,
            }
        )

        finalized = _stage_completed_sentence(
            state,
            "因为我发现网上没有买到这种加绒的运动裤。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=9,
        )

        self.assertEqual(finalized, ["可以下一个就是裤子啦。"])
        self.assertIn("可以下一个就是裤子啦。", state.final_sentences or [])
        self.assertEqual(state.metrics["stage_queue_promote"], 1)
        self.assertNotIn("stage_replace_deferred_same_chunk", state.metrics)

    def test_stale_unconfirmed_queue_candidate_does_not_block_current_sentence(self) -> None:
        state = LifecycleState(language="zh")
        assert state.staged_queue is not None
        state.staged_queue.append(
            {
                "sentence": "地铁怎么样的感觉？",
                "confirmations": 1,
                "age": 0,
                "forced": False,
                "deferred_age_chunk": 20,
            }
        )

        finalized = _stage_completed_sentence(
            state,
            "但是第三天，你觉得自由行怎么样？",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=25,
        )

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "但是第三天，你觉得自由行怎么样？")
        self.assertEqual(state.staged_age, 0)
        self.assertEqual(state.metrics["stage_queue_promote"], 1)
        self.assertEqual(state.metrics["stage_replaced_unconfirmed"], 1)
        self.assertEqual(state.metrics["segment_state_suppressed"], 1)

    def test_recent_final_suffix_recovery_runs_even_when_committed_delta_is_empty(self) -> None:
        state = LifecycleState(
            language="zh",
            committed_text=(
                "嗨，各位，welcome back to my channel. 给你们看一下我的衣服。"
                "刚呢，我就见有这个狗蹲老鼠的后。"
                "然后我本来想要拿一杯红酒的时候就不小心倒到我的衣服圈。"
            ),
        )
        assert state.final_sentences is not None
        state.final_sentences.append("然后我本来想要拿一杯红酒的时候就不小心倒到我的衣服圈。")

        finalized = _stage_completed_sentence(
            state,
            "刚呢，我就见到这个狗墩老鼠，然后我本来想要拿一杯红酒的时候，就不小心倒到我的衣服，全部都是这里这里。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=1,
        )

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "全部都是这里这里。")
        self.assertEqual(state.metrics["candidate_recent_final_delta_trimmed"], 1)
        self.assertNotIn("candidate_duplicate_suppressed", state.metrics)

    def test_candidate_committed_prefix_delta_trim_is_counted(self) -> None:
        state = LifecycleState(
            language="zh",
            committed_text="刚呢，我就见到这个狗墩老鼠，然后",
        )

        finalized = _stage_completed_sentence(
            state,
            "刚呢，我就见到这个狗墩老鼠，然后我本来想要拿一杯红酒的时候。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=1,
        )

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "我本来想要拿一杯红酒的时候。")
        self.assertEqual(state.metrics["candidate_delta_trimmed"], 1)
        self.assertEqual(state.metrics["candidate_delta_trimmed_cjk"], 1)

    def test_internal_stability_preserves_revision_confirmation_in_replay(self) -> None:
        previous = "甲这个锅底浓郁的我感觉都不用蘸底料了直接吃就非常有味道了然后这时候再来一个红糖糍粑。"
        candidate = "乙这个锅底浓郁的我感觉都不用蘸底料了直接吃就非常有味道了然后这时候再来一个红糖糍粑再最后。"
        state = LifecycleState(
            language="zh",
            staged_sentence=previous,
            staged_confirmations=2,
            staged_age=2,
            staged_deferred_age_chunk=6,
            stable_analysis=analyze_stable_window("甲" + previous, "乙" + candidate, "zh"),
        )

        finalized = _stage_completed_sentence(
            state,
            candidate,
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=7,
        )

        self.assertEqual(finalized, [candidate])
        self.assertEqual(state.staged_sentence, "")
        self.assertEqual(state.final_sentences, [candidate])
        self.assertEqual(state.metrics["stage_revision_internal_stability_high"], 1)
        self.assertEqual(state.metrics["stage_revision_confirmation_preserved_internal"], 1)
        self.assertEqual(state.metrics["finalized"], 1)
        self.assertNotIn("stage_revision_age_reset", state.metrics)

    def test_recent_final_internal_match_can_recover_following_sentence(self) -> None:
        candidate = "所以要先去吃个东西，来补充一下体力。也要逛街才有力气。"
        recent = "所以要先去吃个东西来补充一下体力。"

        delta, source = _recent_final_output_delta(candidate, (recent,), "zh")

        self.assertEqual(source, recent)
        self.assertEqual(delta, "也要逛街才有力气。")

    def test_recent_final_tail_anchor_does_not_drop_new_sentence_prefix(self) -> None:
        candidate = "这一家餐厅呢，它是有很多分店的。"
        recent = "我的父母呢，他们讲他们想要吃饭，所以我就找了一家餐厅。"

        delta, source = _recent_final_output_delta(candidate, (recent,), "zh")

        self.assertIsNone(source)
        self.assertEqual(delta, candidate)

    def test_terminal_prefix_revision_wins_over_short_appended_tail(self) -> None:
        preferred = _prefer_sentence_revision(
            "被吓到了想要炸鸡可能吃不下去了我们来看看。",
            "被吓到了想要炸鸡可能吃不下去了。",
        )

        self.assertEqual(preferred, "被吓到了想要炸鸡可能吃不下去了。")

    def test_confirmed_stage_finalizes_before_prefix_drop_revision(self) -> None:
        previous = "今天是我们在韩国第三天，应该算是第二天，第二个全天。"
        candidate = "第三天应该算是第二天，第二个全天。"
        state = LifecycleState(
            language="zh",
            staged_sentence=previous,
            staged_confirmations=2,
            staged_age=1,
            staged_deferred_age_chunk=2,
        )

        finalized = _stage_completed_sentence(
            state,
            candidate,
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=3,
        )

        self.assertEqual(finalized, [previous])
        self.assertEqual(state.final_sentences, [previous])
        self.assertEqual(state.staged_sentence, "")
        self.assertEqual(state.metrics["stage_confirmed_before_prefix_drop_revision"], 1)

    def test_shifted_cjk_revision_drops_single_dangling_tail(self) -> None:
        preferred = _prefer_sentence_revision(
            "炒饭粒粒分明，好香啊，它。",
            "他饭粒粒分明，好香啊！",
        )

        self.assertEqual(preferred, "他饭粒粒分明，好香啊！")

    def test_short_mixed_latin_zh_fragment_is_not_stageable(self) -> None:
        flags = _final_sentence_diagnostic_flags("body king的。", "zh")

        self.assertIn("mixed_latin_zh", flags)
        self.assertIn("short_mixed_latin_zh", flags)
        self.assertFalse(_should_stage_boundary_candidate("body king的。", "zh"))

    def test_reset_revision_is_deferred_until_token_sentence_repeats(self) -> None:
        state = LifecycleState(
            language="zh",
            staged_sentence="刚好明天要拍夜配，我就可以拿着这套衣服去拍我的夜。",
            staged_confirmations=1,
            staged_age=0,
            staged_deferred_age_chunk=109,
        )

        finalized = _stage_completed_sentence(
            state,
            "刚好明天要拍夜拍，我就可以拿着这套衣服去拍我的夜拍。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=110,
        )

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "刚好明天要拍夜配，我就可以拿着这套衣服去拍我的夜。")
        self.assertEqual(state.staged_age, 1)
        self.assertEqual(len(state.staged_queue or ()), 1)
        self.assertEqual(
            (state.staged_queue or ())[0]["sentence"],
            "刚好明天要拍夜拍，我就可以拿着这套衣服去拍我的夜拍。",
        )
        self.assertEqual(state.metrics["stage_revision_token_sentence_deferred"], 1)
        self.assertNotIn("finalized", state.metrics)

    def test_cjk_prefix_growth_preserves_revision_confirmation(self) -> None:
        previous = "然后呢，帮我烤的师傅还。"
        preferred = "然后呢，帮我烤的师傅还懂那个微碗饭。"

        self.assertFalse(_should_reset_revision_age(previous, preferred))
        self.assertEqual(_next_revision_confirmation_count(previous, preferred, 1), 2)

    def test_recent_final_short_tail_anchor_keeps_bridge_prefix(self) -> None:
        recent = "我的里面还有小熊猫、小浣熊，加一些豆芽菜。"
        candidate = "加一些豆芽菜，还有泡菜，还有葱，跟这个自制的萝卜。"

        delta, source = _recent_final_output_delta(candidate, [recent], "zh")

        self.assertIsNone(source)
        self.assertEqual(delta, candidate)

    def test_deferred_revision_extension_blocks_aged_fragment_final(self) -> None:
        state = LifecycleState(
            language="zh",
            staged_sentence="像是松板的部分口感上那真的就是一个。",
            staged_confirmations=1,
            staged_age=2,
            staged_deferred_age_chunk=60,
        )
        assert state.staged_queue is not None
        state.staged_queue.append(
            {
                "sentence": "像是松板的部分口感上那真的就是一个脆嫩带。",
                "confirmations": 1,
                "age": 0,
                "forced": False,
                "deferred_age_chunk": 60,
            }
        )

        finalized = _stage_completed_sentence(
            state,
            "是清蒸牛排的猪肉，你真的也是感受不到任何一丝的猪肉烧味，反而。",
            "zh",
            forced=False,
            sentence_finalize_age=3,
            chunk_index=61,
        )

        self.assertEqual(finalized, [])
        self.assertEqual(state.staged_sentence, "像是松板的部分口感上那真的就是一个脆嫩带。")
        self.assertEqual(state.metrics["stage_replace_deferred"], 1)
        self.assertEqual(state.metrics["stage_queue_promote"], 1)
        self.assertEqual(state.metrics["stage_queue_enqueue"], 1)
        self.assertNotIn("finalized", state.metrics)

    def test_longer_mixed_latin_zh_sentence_remains_stageable(self) -> None:
        sentence = "你看，我点的这个是他们家的招牌cheese。"
        flags = _final_sentence_diagnostic_flags(sentence, "zh")

        self.assertIn("mixed_latin_zh", flags)
        self.assertNotIn("short_mixed_latin_zh", flags)
        self.assertTrue(_should_stage_boundary_candidate(sentence, "zh"))


if __name__ == "__main__":
    unittest.main()

import unittest

from src.app.dictation_transcript_logic import _prefer_sentence_revision
from tests.eval.dictation_ai.sbd_benchmark import LifecycleState, _finalize_staged_sentence, _stage_completed_sentence


class DictationAiSbdLifecycleTest(unittest.TestCase):
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

    def test_terminal_prefix_revision_wins_over_short_appended_tail(self) -> None:
        preferred = _prefer_sentence_revision(
            "被吓到了想要炸鸡可能吃不下去了我们来看看。",
            "被吓到了想要炸鸡可能吃不下去了。",
        )

        self.assertEqual(preferred, "被吓到了想要炸鸡可能吃不下去了。")


if __name__ == "__main__":
    unittest.main()

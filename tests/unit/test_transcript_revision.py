import unittest

from src.app.dictation_core.dictation_recent_final import _recent_final_output_delta_with_reason
from src.app.dictation_core.dictation_revision_text import _sentence_output_delta
from src.app.dictation_core.transcript_revision import append_context, consume_committed_prefix, revision_lifecycle_context


class TranscriptRevisionLifecycleTest(unittest.TestCase):
    def test_recent_final_keeps_closed_zh_candidate_when_recent_is_shorter_suffix_variant(self) -> None:
        candidate = "今天是呃四十八小时内的最后一天，我们今天下午就要去搭飞机了。"
        recent = "是呃四十八小时内的最后一天，我们今天下午就要去搭飞机了。"
        self.assertEqual(
            _recent_final_output_delta_with_reason(candidate, [recent], "zh"),
            (candidate, None, "no_match"),
        )

    def test_recent_final_keeps_closed_zh_candidate_when_recent_overmerged_sentence_contains_it(self) -> None:
        candidate = "明明跟我们介绍来喝这个咖啡，三杯一人一杯。"
        recent = "我们到了望远市场，最有人气的市场，明明跟我们介绍来喝这个咖啡，三杯一人一。"
        self.assertEqual(
            _recent_final_output_delta_with_reason(candidate, [recent], "zh"),
            (candidate, None, "no_match"),
        )

    def test_recent_final_still_suppresses_exact_zh_duplicate(self) -> None:
        candidate = "你们三个知道他是谁吗？"
        self.assertEqual(
            _recent_final_output_delta_with_reason(candidate, [candidate], "zh"),
            ("", candidate, "exact"),
        )

    def test_sentence_output_delta_keeps_new_zh_sentence_with_repeated_prefix(self) -> None:
        self.assertEqual(
            _sentence_output_delta(
                "或者里面还有小熊猫、小浣熊，加一些豆芽菜。",
                "加一些豆芽菜，还有泡菜，还有葱，一根这个紫的萝卜。",
            ),
            "加一些豆芽菜，还有泡菜，还有葱，一根这个紫的萝卜。",
        )

    def test_sentence_output_delta_trims_true_zh_prefix_growth(self) -> None:
        self.assertEqual(
            _sentence_output_delta(
                "我的里面还有小熊猫、小浣熊，加一些豆芽菜。",
                "我的里面还有小熊猫、小浣熊，加一些豆芽菜。哦，还有泡菜，还有葱。",
            ),
            "哦，还有泡菜，还有葱。",
        )

    def test_sentence_output_delta_keeps_non_cjk_prefix_growth_trim(self) -> None:
        self.assertEqual(
            _sentence_output_delta(
                "Hope this bubble never pops.",
                "Hope this bubble never pops. Cause if it does, we're gonna drop.",
            ),
            "cause if it does we re gonna drop",
        )

    def test_final_commit_consumes_matching_pending_prefix(self) -> None:
        pending = "So we have to go somewhere else to go to the bathroom which takes even more time i have had to take it off"

        self.assertEqual(
            consume_committed_prefix(pending, "So we have to go somewhere else to go to the bathroom"),
            "which takes even more time i have had to take it off",
        )
        self.assertEqual(consume_committed_prefix(pending, pending), "")

    def test_final_commit_consumes_pending_after_leading_connective(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now.", "let's do it now."),
            "",
        )

    def test_final_commit_keeps_pending_tail_after_connective(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now again", "let's do it now"),
            "and again",
        )

    def test_revision_lifecycle_context_keeps_staged_and_pending_visible(self) -> None:
        context = revision_lifecycle_context(
            "already committed",
            "staged candidate",
            "pending revision tail",
        )

        self.assertEqual(context, "already committed staged candidate pending revision tail")

    def test_revision_context_keeps_recent_text_when_overflow(self) -> None:
        base = " ".join(["committed"] * 200)
        staged = " ".join(["staged"] * 200)
        pending = " ".join(["pending"] * 200)

        context = revision_lifecycle_context(base, staged, pending)

        self.assertTrue(len(context) <= 4000)
        self.assertIn("pending", context)
        self.assertIn("staged", context)

    def test_append_context_truncates_oldest_prefix(self) -> None:
        self.assertTrue(
            len(append_context(" ".join(["a"] * 100), " ".join(["b"] * 100), max_chars=80)) <= 80
        )

    def test_consume_committed_prefix_with_connective_and_remaining(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now", "let's do it"),
            "and now",
        )


if __name__ == "__main__":
    unittest.main()

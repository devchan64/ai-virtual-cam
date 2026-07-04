import unittest

from src.app.dictation_core.dictation_transcript_logic import (
    _should_enable_aged_queue_backlog_promotion_boost,
    _should_suppress_aged_low_value_final,
    _should_suppress_aged_no_end_marker_queue_final,
)


class DictationStagePolicyTest(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()

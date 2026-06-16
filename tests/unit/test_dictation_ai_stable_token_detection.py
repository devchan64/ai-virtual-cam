import unittest

from src.app.stable_token_detection import (
    analyze_stable_window,
    combine_boundary_confidence,
)


class StableTokenDetectionTest(unittest.TestCase):
    def test_english_stable_prefix_uses_word_units(self) -> None:
        analysis = analyze_stable_window(
            "I want to go to the station",
            "I want to go to the store now",
            "en",
        )

        self.assertEqual(analysis.stable_prefix_text, "i want to go to the")
        self.assertEqual(analysis.unstable_tail_text, "store now")
        self.assertEqual(analysis.stable_units, 6)
        self.assertEqual(analysis.current_units, 8)
        self.assertGreaterEqual(analysis.stable_token_ratio, 0.70)
        self.assertEqual(analysis.stable_overlap_source, "common_prefix")

    def test_english_sliding_window_uses_suffix_prefix_overlap(self) -> None:
        analysis = analyze_stable_window(
            "people in the United States to take delivery",
            "in the United States to take delivery of the first cars",
            "en",
        )

        self.assertEqual(analysis.stable_prefix_text, "in the united states to take delivery")
        self.assertEqual(analysis.unstable_tail_text, "of the first cars")
        self.assertEqual(analysis.stable_overlap_source, "suffix_prefix")
        self.assertGreaterEqual(analysis.stable_token_ratio, 0.60)

    def test_cjk_stable_prefix_uses_character_units_without_spaces(self) -> None:
        analysis = analyze_stable_window(
            "我想去重庆吃火锅",
            "我想去重庆吃小面",
            "zh",
        )

        self.assertEqual(analysis.stable_prefix_text, "我想去重庆吃")
        self.assertEqual(analysis.unstable_tail_text, "小面")
        self.assertEqual(analysis.stable_units, 6)
        self.assertEqual(analysis.current_units, 8)
        self.assertEqual(analysis.stable_overlap_source, "common_prefix")

    def test_cjk_sliding_window_uses_suffix_prefix_overlap(self) -> None:
        analysis = analyze_stable_window(
            "我想去重庆吃火锅",
            "重庆吃火锅然后去喝茶",
            "zh",
        )

        self.assertEqual(analysis.stable_prefix_text, "重庆吃火锅")
        self.assertEqual(analysis.unstable_tail_text, "然后去喝茶")
        self.assertEqual(analysis.stable_overlap_source, "suffix_prefix")
        self.assertEqual(analysis.stable_units, 5)

    def test_cjk_internal_overlap_is_reported_without_changing_stable_prefix(self) -> None:
        analysis = analyze_stable_window(
            "今天来总结一下我们去了横滨然后连昌江之岛",
            "回来了今天来总结一下我们去了横滨然后连昌江之岛哎",
            "zh",
        )

        self.assertEqual(analysis.stable_prefix_text, "")
        self.assertEqual(analysis.stable_units, 0)
        self.assertEqual(analysis.stable_token_ratio, 0.0)
        self.assertEqual(analysis.stable_overlap_source, "none")
        self.assertGreaterEqual(analysis.stable_internal_units, 18)
        self.assertGreaterEqual(analysis.stable_internal_ratio, 0.75)
        self.assertGreaterEqual(analysis.stable_internal_chars, 18)

    def test_first_window_has_no_stability_confidence(self) -> None:
        analysis = analyze_stable_window("", "first raw window", "en")

        self.assertIsNone(analysis.boundary_confidence)
        self.assertEqual(analysis.stable_token_ratio, 0.0)
        self.assertEqual(analysis.stable_internal_ratio, 0.0)
        self.assertEqual(analysis.unstable_tail_text, "first raw window")
        self.assertEqual(analysis.stable_overlap_source, "none")

    def test_boundary_confidence_uses_more_conservative_signal(self) -> None:
        self.assertEqual(combine_boundary_confidence(0.90, 0.55), 0.55)
        self.assertEqual(combine_boundary_confidence(None, 0.70), 0.70)
        self.assertEqual(combine_boundary_confidence(0.80, None), 0.80)
        self.assertIsNone(combine_boundary_confidence(None, None))


if __name__ == "__main__":
    unittest.main()

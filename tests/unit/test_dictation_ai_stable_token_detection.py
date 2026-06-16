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

    def test_first_window_has_no_stability_confidence(self) -> None:
        analysis = analyze_stable_window("", "first raw window", "en")

        self.assertIsNone(analysis.boundary_confidence)
        self.assertEqual(analysis.stable_token_ratio, 0.0)
        self.assertEqual(analysis.unstable_tail_text, "first raw window")

    def test_boundary_confidence_uses_more_conservative_signal(self) -> None:
        self.assertEqual(combine_boundary_confidence(0.90, 0.55), 0.55)
        self.assertEqual(combine_boundary_confidence(None, 0.70), 0.70)
        self.assertEqual(combine_boundary_confidence(0.80, None), 0.80)
        self.assertIsNone(combine_boundary_confidence(None, None))


if __name__ == "__main__":
    unittest.main()

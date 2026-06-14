import unittest

from scripts.config.components import format_slider_value, slider_decimal_places, snap_slider_value
from scripts.config.whisper_options import whisper_stt_backend_runtime_option_keys


class ConfigComponentsTest(unittest.TestCase):
    def test_slider_decimal_places_derive_from_step(self) -> None:
        self.assertEqual(slider_decimal_places(1), 0)
        self.assertEqual(slider_decimal_places(0.5), 1)
        self.assertEqual(slider_decimal_places(0.01), 2)

    def test_snap_slider_value_clamps_and_snaps_to_step(self) -> None:
        self.assertEqual(snap_slider_value(2.5517, 1.0, 10.0, 0.5), 2.5)
        self.assertEqual(snap_slider_value(2.76, 1.0, 10.0, 0.5), 3.0)
        self.assertEqual(snap_slider_value(-1, 0, 8, 1), 0)
        self.assertEqual(snap_slider_value(99, 0, 8, 1), 8)

    def test_format_slider_value_matches_step_precision(self) -> None:
        self.assertEqual(format_slider_value(3.0, 1), "3")
        self.assertEqual(format_slider_value(2.5, 0.5), "2.5")
        self.assertEqual(format_slider_value(0.25, 0.01), "0.25")

    def test_whisper_backend_runtime_option_keys_are_backend_specific(self) -> None:
        self.assertEqual(
            whisper_stt_backend_runtime_option_keys("faster-whisper"),
            ("compute_type", "beam_size", "max_new_tokens", "temperature"),
        )
        self.assertEqual(whisper_stt_backend_runtime_option_keys("funasr-paraformer"), ())
        self.assertEqual(whisper_stt_backend_runtime_option_keys("funasr-sensevoice"), ())
        self.assertEqual(whisper_stt_backend_runtime_option_keys("qwen3-asr-transformers"), ("compute_type", "max_new_tokens"))


if __name__ == "__main__":
    unittest.main()

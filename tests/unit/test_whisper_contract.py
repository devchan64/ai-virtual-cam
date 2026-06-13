import unittest

from src.domain.contracts.whisper import WHISPER_CONTRACT, whisper_allowed, whisper_default, whisper_defaults, whisper_spec


class WhisperContractTest(unittest.TestCase):
    def test_contract_defaults_match_exported_defaults(self) -> None:
        defaults = whisper_defaults()

        self.assertEqual(set(defaults), set(WHISPER_CONTRACT))
        self.assertEqual(defaults["language"], "en")
        self.assertEqual(defaults["sttBackendZh"], "funasr-paraformer")
        self.assertEqual(whisper_default("sentenceBoundaryBackendZh"), "funasr-ct-punc")

    def test_contract_exposes_allowed_values(self) -> None:
        self.assertEqual(whisper_allowed("language"), ("ko", "en", "zh"))
        self.assertIn("funasr-paraformer", whisper_allowed("sttBackendZh"))
        self.assertNotIn("auto", whisper_allowed("language"))

    def test_contract_validates_allowed_values(self) -> None:
        whisper_spec("language").validate_allowed("ko", path="whisper.language")
        with self.assertRaisesRegex(ValueError, "whisper.language"):
            whisper_spec("language").validate_allowed("auto", path="whisper.language")

    def test_contract_validates_ranges(self) -> None:
        whisper_spec("beamSize").validate_range(3, path="whisper.beamSize")
        with self.assertRaisesRegex(ValueError, "whisper.beamSize"):
            whisper_spec("beamSize").validate_range(0, path="whisper.beamSize")


if __name__ == "__main__":
    unittest.main()

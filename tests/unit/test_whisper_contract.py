import unittest

from src.domain.contracts.whisper import (
    WHISPER_CONTRACT,
    resolve_funasr_model_name,
    resolve_qwen_asr_model_name,
    whisper_stt_backends_for_language,
    whisper_allowed,
    whisper_default,
    whisper_defaults,
    whisper_spec,
)


class WhisperContractTest(unittest.TestCase):
    def test_contract_defaults_match_exported_defaults(self) -> None:
        defaults = whisper_defaults()

        self.assertEqual(set(defaults), set(WHISPER_CONTRACT))
        self.assertEqual(defaults["language"], "en")
        self.assertEqual(defaults["sttBackendZh"], "qwen3-asr-transformers")
        self.assertEqual(defaults["postProcessingProfile"], "manual")
        self.assertEqual(whisper_default("sentenceBoundaryBackendZh"), "funasr-ct-punc")

    def test_contract_exposes_allowed_values(self) -> None:
        self.assertEqual(whisper_allowed("language"), ("ko", "en", "zh"))
        self.assertIn("qwen3-asr-transformers", whisper_allowed("sttBackendZh"))
        self.assertNotIn("auto", whisper_allowed("language"))
        self.assertEqual(whisper_allowed("postProcessingProfile"), ("manual",))



    def test_contract_limits_stt_backends_by_language(self) -> None:
        self.assertEqual(whisper_stt_backends_for_language("en"), ("faster-whisper", "mock"))
        self.assertEqual(whisper_stt_backends_for_language("ko"), ("faster-whisper", "mock"))
        self.assertIn("funasr-paraformer", whisper_stt_backends_for_language("zh"))
        self.assertIn("qwen3-asr-transformers", whisper_stt_backends_for_language("zh"))

    def test_contract_resolves_funasr_model_aliases(self) -> None:
        self.assertEqual(
            resolve_funasr_model_name("paraformer-zh"),
            "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        )
        self.assertEqual(
            resolve_funasr_model_name("ct-punc-c"),
            "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
        )
        self.assertEqual(resolve_funasr_model_name("iic/custom"), "iic/custom")

    def test_contract_resolves_qwen_asr_model_aliases(self) -> None:
        self.assertEqual(resolve_qwen_asr_model_name("qwen3-asr-0.6b"), "Qwen/Qwen3-ASR-0.6B")
        self.assertEqual(resolve_qwen_asr_model_name("qwen3-asr-1.7b"), "Qwen/Qwen3-ASR-1.7B")
        self.assertEqual(resolve_qwen_asr_model_name("Qwen/custom"), "Qwen/custom")

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

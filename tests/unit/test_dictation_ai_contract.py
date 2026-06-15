import unittest

from src.domain.contracts.dictation_ai import (
    DICTATION_AI_CONTRACT,
    resolve_qwen_asr_model_name,
    dictation_ai_stt_backends_for_language,
    dictation_ai_allowed,
    dictation_ai_default,
    dictation_ai_defaults,
    dictation_ai_spec,
)


class WhisperContractTest(unittest.TestCase):
    def test_contract_defaults_match_exported_defaults(self) -> None:
        defaults = dictation_ai_defaults()

        self.assertEqual(set(defaults), set(DICTATION_AI_CONTRACT))
        self.assertEqual(defaults["language"], "en")
        self.assertEqual(defaults["sttBackendZh"], "qwen3-asr-transformers")
        self.assertEqual(defaults["sttModelZh"], "qwen3-asr-0.6b")
        self.assertEqual(defaults["stepSeconds"], 2.0)
        self.assertEqual(defaults["windowSeconds"], 7.0)
        self.assertEqual(defaults["stepSecondsEn"], 1.0)
        self.assertEqual(defaults["windowSecondsEn"], 7.0)
        self.assertEqual(defaults["stepSecondsKo"], 1.0)
        self.assertEqual(defaults["windowSecondsKo"], 7.0)
        self.assertEqual(defaults["stepSecondsZh"], 1.0)
        self.assertEqual(defaults["windowSecondsZh"], 12.0)
        self.assertEqual(defaults["commitLagSeconds"], 1.0)
        self.assertEqual(defaults["maxNewTokens"], 192)
        self.assertEqual(defaults["postProcessingProfile"], "manual")
        self.assertEqual(dictation_ai_default("sentenceBoundaryBackendZh"), "sat")

    def test_contract_exposes_allowed_values(self) -> None:
        self.assertEqual(dictation_ai_allowed("language"), ("ko", "en", "zh"))
        self.assertIn("qwen3-asr-transformers", dictation_ai_allowed("sttBackendZh"))
        self.assertIn("qwen3-asr-vllm-streaming", dictation_ai_allowed("sttBackendZh"))
        self.assertNotIn("auto", dictation_ai_allowed("language"))
        self.assertEqual(dictation_ai_allowed("postProcessingProfile"), ("manual",))



    def test_contract_limits_stt_backends_by_language(self) -> None:
        self.assertEqual(dictation_ai_stt_backends_for_language("en"), ("faster-whisper", "mock"))
        self.assertEqual(dictation_ai_stt_backends_for_language("ko"), ("faster-whisper", "mock"))
        self.assertEqual(
            dictation_ai_stt_backends_for_language("zh"),
            ("faster-whisper", "qwen3-asr-transformers", "qwen3-asr-vllm-streaming", "mock"),
        )

    def test_contract_resolves_qwen_asr_model_aliases(self) -> None:
        self.assertEqual(resolve_qwen_asr_model_name("qwen3-asr-0.6b"), "Qwen/Qwen3-ASR-0.6B")
        self.assertEqual(resolve_qwen_asr_model_name("qwen3-asr-1.7b"), "Qwen/Qwen3-ASR-1.7B")
        self.assertEqual(resolve_qwen_asr_model_name("Qwen/custom"), "Qwen/custom")

    def test_contract_validates_allowed_values(self) -> None:
        dictation_ai_spec("language").validate_allowed("ko", path="dictationAi.language")
        with self.assertRaisesRegex(ValueError, "dictationAi.language"):
            dictation_ai_spec("language").validate_allowed("auto", path="dictationAi.language")

    def test_contract_validates_ranges(self) -> None:
        dictation_ai_spec("beamSize").validate_range(3, path="dictationAi.beamSize")
        with self.assertRaisesRegex(ValueError, "dictationAi.beamSize"):
            dictation_ai_spec("beamSize").validate_range(0, path="dictationAi.beamSize")


if __name__ == "__main__":
    unittest.main()

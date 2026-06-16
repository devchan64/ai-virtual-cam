import unittest

from src.domain.contracts.camera import (
    CAMERA_FEATURE_TOGGLE_KEYS,
    camera_default,
    camera_feature_toggle_keys,
)
from src.domain.contracts.dictation_ai import (
    DICTATION_AI_CONTRACT,
    resolve_qwen_asr_model_name,
    dictation_ai_stt_backends_for_language,
    dictation_ai_allowed,
    dictation_ai_default,
    dictation_ai_defaults,
    dictation_ai_spec,
)
from src.domain.contracts.window_geometry import (
    CONFIG_DEFAULT_WINDOW_GEOMETRY,
    DEFAULT_WINDOW_GEOMETRY_META,
    DICTATION_AI_DEFAULT_WINDOW_GEOMETRY,
    WINDOW_GEOMETRY_FILE_NAME,
    sanitize_window_geometry,
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
        self.assertEqual(defaults["sentenceFinalizeAge"], 3)
        self.assertEqual(defaults["sentenceFinalizeAgeEn"], 3)
        self.assertEqual(defaults["sentenceFinalizeAgeKo"], 3)
        self.assertEqual(defaults["sentenceFinalizeAgeZh"], 3)
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
        dictation_ai_spec("sentenceFinalizeAge").validate_range(3, path="dictationAi.sentenceFinalizeAge")
        with self.assertRaisesRegex(ValueError, "dictationAi.sentenceFinalizeAge"):
            dictation_ai_spec("sentenceFinalizeAge").validate_range(0, path="dictationAi.sentenceFinalizeAge")


class CameraContractTest(unittest.TestCase):
    def test_camera_feature_contract_exposes_gui_toggle_keys(self) -> None:
        self.assertEqual(
            camera_feature_toggle_keys(),
            (
                "seg_enabled",
                "bg_enabled",
                "crop_enabled",
                "face_enhance_enabled",
                "face_deidentify_enabled",
            ),
        )
        self.assertEqual(camera_feature_toggle_keys(), CAMERA_FEATURE_TOGGLE_KEYS)

    def test_camera_feature_contract_defaults(self) -> None:
        self.assertTrue(camera_default("cameraServerEnabled"))
        self.assertTrue(camera_default("segmentationEnabled"))
        self.assertTrue(camera_default("backgroundEnabled"))
        self.assertTrue(camera_default("cropEnabled"))
        self.assertFalse(camera_default("faceEnhanceEnabled"))
        self.assertFalse(camera_default("faceDeidentifyEnabled"))


class WindowGeometryContractTest(unittest.TestCase):
    def test_window_geometry_contract_keeps_all_window_keys_together(self) -> None:
        self.assertEqual(CONFIG_DEFAULT_WINDOW_GEOMETRY, "780x900")
        self.assertEqual(DICTATION_AI_DEFAULT_WINDOW_GEOMETRY, "780x420")
        self.assertEqual(WINDOW_GEOMETRY_FILE_NAME, "window-geometry.json")
        self.assertIn("windowGeometry", DEFAULT_WINDOW_GEOMETRY_META)
        self.assertIn("previewWindowGeometry", DEFAULT_WINDOW_GEOMETRY_META)
        self.assertIn("dictationAiWindowGeometry", DEFAULT_WINDOW_GEOMETRY_META)
        self.assertIn("dictationAiTranslationWindowGeometry", DEFAULT_WINDOW_GEOMETRY_META)
        self.assertIn("dictationAiSttStatusWindowGeometry", DEFAULT_WINDOW_GEOMETRY_META)
        self.assertIn("dictationAiModelDownloadWindowGeometry", DEFAULT_WINDOW_GEOMETRY_META)

    def test_window_geometry_contract_sanitizes_visible_geometry(self) -> None:
        self.assertEqual(sanitize_window_geometry("780x420+50+119", 1920, 1080), "780x420+50+119")
        self.assertIsNone(sanitize_window_geometry("200x100+50+119", 1920, 1080))
        self.assertIsNone(sanitize_window_geometry("780x420+5000+119", 1920, 1080))


if __name__ == "__main__":
    unittest.main()

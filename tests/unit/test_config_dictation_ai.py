import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.domain.config import AppConfig, DictationAiConfig
from src.domain.contracts.dictation_ai import (
    dictation_ai_translation_backends_for_language,
    dictation_ai_translation_backends_for_target_language,
    dictation_ai_translation_models_for_backend,
    dictation_ai_translation_targets_for_backend,
)
from src.domain.dictation_ai_defaults import dictation_ai_default
from src.tools.config_builder import build_config


class CameraServerConfigTest(unittest.TestCase):
    @staticmethod
    def _build_base_config(**overrides):
        params = {
            "input_device": "0",
            "input_width": 1280,
            "input_height": 720,
            "input_fps": 30,
            "output_device": "output.mp4",
            "output_width": 1280,
            "output_height": 720,
            "output_fps": 30,
            "output_backend": "opencv",
            "segmentation_backend": "mock",
            "segmentation_threshold": 0.5,
            "background": {"mode": "chroma", "chromaColor": [0, 0, 0]},
            "crop_margin": 0.25,
            "crop_pan_smoothing": 0.85,
            "audio_input_device": "default",
            "audio_output_device": "default",
        }
        params.update(overrides)
        return build_config(**params)

    def test_build_config_includes_camera_server_enabled_by_default(self) -> None:
        config = self._build_base_config()

        self.assertEqual(config["cameraServer"], {"enabled": True})

    def test_build_config_includes_camera_pipeline_feature_enabled_flags(self) -> None:
        config = self._build_base_config(
            segmentation_enabled=False,
            background_enabled=False,
            crop_enabled=False,
            face_enhance_enabled=False,
            face_deidentify_enabled=False,
        )

        self.assertFalse(config["segmentation"]["enabled"])
        self.assertFalse(config["background"]["enabled"])
        self.assertFalse(config["crop"]["enabled"])
        self.assertFalse(config["faceEnhance"]["enabled"])
        self.assertFalse(config["faceEnhance"]["deidentify"]["enabled"])

    def test_app_config_loads_camera_server_enabled_false(self) -> None:
        config = self._build_base_config(camera_server_enabled=False)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            loaded = AppConfig.load(path)

        self.assertFalse(loaded.cameraServer.enabled)

    def test_app_config_defaults_camera_server_enabled_when_missing(self) -> None:
        config = self._build_base_config()
        config.pop("cameraServer")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            loaded = AppConfig.load(path)

        self.assertTrue(loaded.cameraServer.enabled)


class DictationAiConfigTest(unittest.TestCase):
    def test_build_config_includes_dictation_ai_settings(self) -> None:
        config = build_config(
            input_device="0",
            input_width=1280,
            input_height=720,
            input_fps=30,
            output_device="output.mp4",
            output_width=1280,
            output_height=720,
            output_fps=30,
            output_backend="opencv",
            segmentation_backend="mock",
            segmentation_threshold=0.5,
            background={"mode": "chroma", "chromaColor": [0, 0, 0]},
            crop_margin=0.25,
            crop_pan_smoothing=0.85,
            audio_input_device="default",
            audio_output_device="default",
            dictation_ai_enabled=True,
            dictation_ai_input_device="pulse",
            dictation_ai_backend="mock",
            dictation_ai_model="tiny",
            dictation_ai_stt_backend_en="faster-whisper",
            dictation_ai_stt_model_en="tiny",
            dictation_ai_stt_backend_ko="faster-whisper",
            dictation_ai_stt_model_ko="large-v3",
            dictation_ai_stt_backend_zh="qwen3-asr-transformers",
            dictation_ai_stt_model_zh="qwen3-asr-0.6b",
            dictation_ai_language="en",
            dictation_ai_task="transcribe",
            dictation_ai_translation_enabled=True,
            dictation_ai_translation_target_language="ko",
            dictation_ai_translation_backend="nllb-transformers",
            dictation_ai_translation_model="facebook/nllb-200-distilled-600M",
            dictation_ai_translation_device="cpu",
            dictation_ai_translation_compute_type="float32",
            dictation_ai_translation_beam_size=3,
            dictation_ai_translation_max_new_tokens=256,
            dictation_ai_device="cpu",
            dictation_ai_compute_type="int8",
            dictation_ai_step_seconds=1.0,
            dictation_ai_window_seconds=4.0,
            dictation_ai_sentence_finalize_age=2,
            dictation_ai_beam_size=1,
            dictation_ai_max_new_tokens=128,
            dictation_ai_temperature=0.2,
        )

        self.assertEqual(
            config["dictationAi"],
            {
                "enabled": True,
                "inputDevice": "pulse",
                "backend": "mock",
                "model": "tiny",
                "sttBackendEn": "faster-whisper",
                "sttModelEn": "tiny",
                "sttBackendKo": "faster-whisper",
                "sttModelKo": "large-v3",
                "sttBackendZh": "qwen3-asr-transformers",
                "sttModelZh": "qwen3-asr-0.6b",
                "language": "en",
                "task": "transcribe",
                "showSttStatusWindow": False,
                "translationEnabled": True,
                "translationTargetLanguage": "ko",
                "translationBackend": "nllb-transformers",
                "translationModel": "facebook/nllb-200-distilled-600M",
                "translationDevice": "cpu",
                "translationComputeType": "float32",
                "translationBeamSize": 3,
                "translationMaxNewTokens": 256,
                "translationBackendEn": "whisper",
                "translationModelEn": "",
                "translationDeviceEn": "cuda",
                "translationComputeTypeEn": "float16",
                "translationBeamSizeEn": 1,
                "translationMaxNewTokensEn": 128,
                "translationBackendKo": "nllb-transformers",
                "translationModelKo": "facebook/nllb-200-distilled-600M",
                "translationDeviceKo": "cpu",
                "translationComputeTypeKo": "float32",
                "translationBeamSizeKo": 3,
                "translationMaxNewTokensKo": 256,
                "translationBackendZh": "m2m100-transformers",
                "translationModelZh": "facebook/m2m100_1.2B",
                "translationDeviceZh": "cuda",
                "translationComputeTypeZh": "float16",
                "translationBeamSizeZh": 1,
                "translationMaxNewTokensZh": 128,
                "device": "cpu",
                "computeType": "int8",
                "chunkSeconds": 4.0,
                "stepSeconds": 1.0,
                "windowSeconds": 4.0,
                "sentenceFinalizeAge": 2,
                "beamSize": 1,
                "maxNewTokens": 128,
                "temperature": 0.2,
                "stepSecondsEn": 1.0,
                "windowSecondsEn": 4.0,
                "sentenceFinalizeAgeEn": 2,
                "beamSizeEn": 1,
                "maxNewTokensEn": 128,
                "temperatureEn": 0.2,
                "stepSecondsKo": 1.0,
                "windowSecondsKo": 7.0,
                "sentenceFinalizeAgeKo": 3,
                "beamSizeKo": 3,
                "maxNewTokensKo": 192,
                "temperatureKo": 0.0,
                "stepSecondsZh": 1.0,
                "windowSecondsZh": 12.0,
                "sentenceFinalizeAgeZh": 3,
                "beamSizeZh": 3,
                "maxNewTokensZh": 192,
                "temperatureZh": 0.0,
                "postProcessingProfile": "manual",
                "sentenceBoundaryBackend": "sat",
                "sentenceBoundaryModel": "sat-3l-sm",
                "sentenceBoundaryBackendEn": "sat",
                "sentenceBoundaryModelEn": "sat-3l-sm",
                "sentenceBoundaryBackendKo": "sat",
                "sentenceBoundaryModelKo": "sat-3l-sm",
                "sentenceBoundaryBackendZh": "sat",
                "sentenceBoundaryModelZh": "sat-3l-sm",
                "sentenceBoundaryDevice": "cuda",
                "sentenceBoundaryComputeType": "float16",
            },
        )


    def test_build_config_uses_chunk_seconds_as_legacy_window_seconds(self) -> None:
        config = build_config(
            input_device="0",
            input_width=1280,
            input_height=720,
            input_fps=30,
            output_device="output.mp4",
            output_width=1280,
            output_height=720,
            output_fps=30,
            output_backend="opencv",
            segmentation_backend="mock",
            segmentation_threshold=0.5,
            background={"mode": "chroma", "chromaColor": [0, 0, 0]},
            crop_margin=0.25,
            crop_pan_smoothing=0.85,
            audio_input_device="default",
            audio_output_device="default",
            dictation_ai_backend="mock",
            dictation_ai_chunk_seconds=2.5,
        )

        self.assertEqual(config["dictationAi"]["chunkSeconds"], 2.5)
        self.assertEqual(config["dictationAi"]["windowSeconds"], 2.5)

    def test_build_config_persists_language_specific_runtime_settings(self) -> None:
        config = build_config(
            input_device="0",
            input_width=1280,
            input_height=720,
            input_fps=30,
            output_device="output.mp4",
            output_width=1280,
            output_height=720,
            output_fps=30,
            output_backend="opencv",
            segmentation_backend="mock",
            segmentation_threshold=0.5,
            background={"mode": "chroma", "chromaColor": [0, 0, 0]},
            crop_margin=0.25,
            crop_pan_smoothing=0.85,
            audio_input_device="default",
            audio_output_device="default",
            dictation_ai_backend="mock",
            dictation_ai_language="zh",
            dictation_ai_window_seconds=12.0,
            dictation_ai_window_seconds_en=7.0,
            dictation_ai_window_seconds_ko=7.0,
            dictation_ai_window_seconds_zh=12.0,
            dictation_ai_step_seconds_zh=1.0,
            dictation_ai_sentence_finalize_age_zh=4,
        )

        self.assertEqual(config["dictationAi"]["windowSeconds"], 12.0)
        self.assertEqual(config["dictationAi"]["windowSecondsEn"], 7.0)
        self.assertEqual(config["dictationAi"]["windowSecondsKo"], 7.0)
        self.assertEqual(config["dictationAi"]["windowSecondsZh"], 12.0)
        self.assertEqual(config["dictationAi"]["stepSecondsEn"], 1.0)
        self.assertEqual(config["dictationAi"]["stepSecondsKo"], 1.0)
        self.assertEqual(config["dictationAi"]["stepSecondsZh"], 1.0)
        self.assertEqual(config["dictationAi"]["sentenceFinalizeAgeZh"], 4)

    def test_app_config_loads_dictation_ai_settings(self) -> None:
        config = build_config(
            input_device="0",
            input_width=1280,
            input_height=720,
            input_fps=30,
            output_device="output.mp4",
            output_width=1280,
            output_height=720,
            output_fps=30,
            output_backend="opencv",
            segmentation_backend="mock",
            segmentation_threshold=0.5,
            background={"mode": "chroma", "chromaColor": [0, 0, 0]},
            crop_margin=0.25,
            crop_pan_smoothing=0.85,
            audio_input_device="default",
            audio_output_device="default",
            dictation_ai_enabled=True,
            dictation_ai_input_device="pulse",
            dictation_ai_backend="mock",
            dictation_ai_model="base",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            with mock.patch("src.domain.config.platform.system", return_value="Linux"):
                loaded = AppConfig.load(path)

        self.assertTrue(loaded.dictationAi.enabled)
        self.assertEqual(loaded.dictationAi.inputDevice, "pulse")
        self.assertEqual(loaded.dictationAi.backend, "mock")
        self.assertEqual(loaded.dictationAi.model, "base")
        self.assertEqual(loaded.dictationAi.sttBackendEn, dictation_ai_default("sttBackendEn"))
        self.assertEqual(loaded.dictationAi.sttModelEn, dictation_ai_default("sttModelEn"))
        self.assertEqual(loaded.dictationAi.sttBackendZh, dictation_ai_default("sttBackendZh"))
        self.assertEqual(loaded.dictationAi.sttModelZh, dictation_ai_default("sttModelZh"))
        self.assertFalse(loaded.dictationAi.translationEnabled)
        self.assertFalse(loaded.dictationAi.showSttStatusWindow)
        self.assertEqual(loaded.dictationAi.translationTargetLanguage, dictation_ai_default("translationTargetLanguage"))
        self.assertEqual(loaded.dictationAi.translationBackend, dictation_ai_default("translationBackend"))
        self.assertEqual(loaded.dictationAi.translationModel, "facebook/nllb-200-distilled-600M")
        self.assertEqual(loaded.dictationAi.translationDevice, "cuda")
        self.assertEqual(loaded.dictationAi.translationComputeType, "float16")
        self.assertEqual(loaded.dictationAi.translationBeamSize, dictation_ai_default("translationBeamSize"))
        self.assertEqual(loaded.dictationAi.translationMaxNewTokens, dictation_ai_default("translationMaxNewTokens"))
        self.assertEqual(loaded.dictationAi.translationBackendKo, dictation_ai_default("translationBackendKo"))
        self.assertEqual(loaded.dictationAi.translationBackendZh, dictation_ai_default("translationBackendZh"))
        self.assertEqual(loaded.dictationAi.chunkSeconds, dictation_ai_default("chunkSeconds"))
        self.assertEqual(loaded.dictationAi.stepSeconds, dictation_ai_default("stepSeconds"))
        self.assertEqual(loaded.dictationAi.windowSeconds, dictation_ai_default("windowSeconds"))
        self.assertEqual(loaded.dictationAi.beamSize, dictation_ai_default("beamSize"))
        self.assertEqual(loaded.dictationAi.maxNewTokens, dictation_ai_default("maxNewTokens"))
        self.assertEqual(loaded.dictationAi.temperature, dictation_ai_default("temperature"))
        self.assertEqual(loaded.dictationAi.sentenceBoundaryBackend, dictation_ai_default("sentenceBoundaryBackend"))
        self.assertEqual(loaded.dictationAi.sentenceBoundaryModel, dictation_ai_default("sentenceBoundaryModel"))
        self.assertEqual(loaded.dictationAi.sentenceBoundaryDevice, dictation_ai_default("sentenceBoundaryDevice"))
        self.assertEqual(loaded.dictationAi.sentenceBoundaryComputeType, dictation_ai_default("sentenceBoundaryComputeType"))

    def test_dictation_ai_enabled_requires_linux(self) -> None:
        with mock.patch("src.domain.config.platform.system", return_value="Darwin"):
            with self.assertRaisesRegex(ValueError, "Linux with NVIDIA CUDA"):
                DictationAiConfig.from_dict({"enabled": True})

        with mock.patch("src.domain.config.platform.system", return_value="Darwin"):
            loaded = DictationAiConfig.from_dict({"enabled": False, "device": "cpu"})

        self.assertFalse(loaded.enabled)
        self.assertEqual(loaded.device, "cpu")

    def test_dictation_ai_enabled_requires_cuda_devices(self) -> None:
        with mock.patch("src.domain.config.platform.system", return_value="Linux"):
            with self.assertRaisesRegex(ValueError, "dictationAi.device"):
                DictationAiConfig.from_dict({"enabled": True, "device": "cpu"})
            with self.assertRaisesRegex(ValueError, "dictationAi.sentenceBoundaryDevice"):
                DictationAiConfig.from_dict({"enabled": True, "sentenceBoundaryDevice": "cpu"})
            with self.assertRaisesRegex(ValueError, "dictationAi.translationDeviceKo"):
                DictationAiConfig.from_dict({
                    "enabled": True,
                    "translationEnabled": True,
                    "translationTargetLanguage": "ko",
                    "translationDeviceKo": "cpu",
                })

    def test_dictation_ai_rejects_removed_chinese_funasr_stt_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.sttBackendZh"):
            DictationAiConfig.from_dict({
                "language": "zh",
                "postProcessingProfile": "manual",
                "sttBackendZh": "funasr-paraformer",
                "sttModelZh": "paraformer-zh",
            })

    def test_dictation_ai_supports_manual_post_processing_only(self) -> None:
        loaded = DictationAiConfig.from_dict({
            "language": "zh",
            "postProcessingProfile": "manual",
            "sentenceBoundaryBackend": "sat",
            "sentenceBoundaryModel": "sat-3l-sm",
        })

        self.assertEqual(loaded.postProcessingProfile, "manual")
        self.assertEqual(loaded.sentenceBoundaryBackend, "sat")
        self.assertEqual(loaded.sentenceBoundaryModel, "sat-3l-sm")
        with self.assertRaisesRegex(ValueError, "dictationAi.postProcessingProfile"):
            DictationAiConfig.from_dict({"postProcessingProfile": "auto-by-language"})

    def test_dictation_ai_rejects_invalid_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.backend"):
            DictationAiConfig.from_dict({"backend": "invalid"})

    def test_dictation_ai_rejects_invalid_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.language"):
            DictationAiConfig.from_dict({"language": "ja"})
        with self.assertRaisesRegex(ValueError, "dictationAi.language"):
            DictationAiConfig.from_dict({"language": "auto"})

    def test_dictation_ai_treats_legacy_translate_task_as_translation_enabled(self) -> None:
        loaded = DictationAiConfig.from_dict({"task": "translate"})

        self.assertTrue(loaded.translationEnabled)
        self.assertEqual(loaded.task, "translate")

    def test_dictation_ai_rejects_invalid_translation_target_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationTargetLanguage"):
            DictationAiConfig.from_dict({"translationTargetLanguage": "ja"})

    def test_dictation_ai_requires_english_target_for_dictation_ai_translation_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationTargetLanguage"):
            DictationAiConfig.from_dict({"translationEnabled": True, "translationBackend": "whisper", "translationTargetLanguage": "ko"})

    def test_dictation_ai_translation_contract_groups_by_language_and_backend(self) -> None:
        self.assertIn("m2m100-transformers", dictation_ai_translation_backends_for_language("zh"))
        self.assertIn("whisper", dictation_ai_translation_backends_for_target_language("en"))
        self.assertNotIn("whisper", dictation_ai_translation_backends_for_target_language("ko"))
        self.assertEqual(
            dictation_ai_translation_targets_for_backend("zh", "whisper"),
            ("en",),
        )
        self.assertIn("ko", dictation_ai_translation_targets_for_backend("zh", "m2m100-transformers"))
        self.assertEqual(
            dictation_ai_translation_models_for_backend("m2m100-transformers"),
            ("facebook/m2m100_1.2B",),
        )
        self.assertIn("facebook/nllb-200-3.3B", dictation_ai_translation_models_for_backend("nllb-transformers"))

    def test_dictation_ai_allows_multilingual_translation_target_with_nllb_backend(self) -> None:
        loaded = DictationAiConfig.from_dict({
            "translationEnabled": True,
            "translationBackend": "nllb-transformers",
            "translationTargetLanguage": "ko",
        })

        self.assertTrue(loaded.translationEnabled)
        self.assertEqual(loaded.task, "transcribe")
        self.assertEqual(loaded.translationTargetLanguage, "ko")
        self.assertEqual(loaded.translationBackend, "nllb-transformers")
        self.assertEqual(loaded.translationBackendKo, "nllb-transformers")

    def test_dictation_ai_translation_runtime_is_selected_by_target_language(self) -> None:
        loaded = DictationAiConfig.from_dict({
            "language": "zh",
            "translationEnabled": True,
            "translationTargetLanguage": "zh",
            "translationBackendKo": "nllb-transformers",
            "translationModelKo": "facebook/nllb-200-distilled-600M",
            "translationBeamSizeKo": 2,
            "translationBackendZh": "m2m100-transformers",
            "translationModelZh": "facebook/m2m100_1.2B",
            "translationBeamSizeZh": 4,
        })

        self.assertEqual(loaded.translationTargetLanguage, "zh")
        self.assertEqual(loaded.translationBackend, "m2m100-transformers")
        self.assertEqual(loaded.translationModel, "facebook/m2m100_1.2B")
        self.assertEqual(loaded.translationBeamSize, 4)
        self.assertEqual(loaded.translationBeamSizeKo, 2)

    def test_dictation_ai_validates_translation_target_language_groups(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationBackendZh"):
            DictationAiConfig.from_dict({
                "language": "zh",
                "translationEnabled": True,
                "translationTargetLanguage": "ko",
                "translationBackendZh": "whisper",
            })

        with self.assertRaisesRegex(ValueError, "dictationAi.translationDeviceKo"):
            DictationAiConfig.from_dict({
                "language": "zh",
                "translationEnabled": True,
                "translationTargetLanguage": "ko",
                "translationBackendKo": "nllb-transformers",
                "translationDeviceKo": "cpu",
            })

    def test_dictation_ai_allows_m2m100_translation_backend(self) -> None:
        loaded = DictationAiConfig.from_dict({
            "language": "zh",
            "translationEnabled": True,
            "translationBackend": "m2m100-transformers",
            "translationTargetLanguage": "ko",
            "translationModel": "facebook/m2m100_1.2B",
        })

        self.assertEqual(loaded.translationBackend, "m2m100-transformers")
        self.assertEqual(loaded.translationModel, "facebook/m2m100_1.2B")

    def test_dictation_ai_rejects_translation_model_not_allowed_for_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationModel"):
            DictationAiConfig.from_dict({
                "translationEnabled": True,
                "translationBackend": "m2m100-transformers",
                "translationTargetLanguage": "ko",
                "translationModel": "facebook/nllb-200-distilled-600M",
            })

    def test_dictation_ai_rejects_translate_task_for_nllb_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.task"):
            DictationAiConfig.from_dict({
                "task": "translate",
                "translationEnabled": True,
                "translationBackend": "nllb-transformers",
                "translationTargetLanguage": "ko",
            })

    def test_dictation_ai_rejects_cpu_for_enabled_nllb_translation(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationDevice"):
            DictationAiConfig.from_dict({
                "translationEnabled": True,
                "translationBackend": "nllb-transformers",
                "translationDevice": "cpu",
            })

    def test_dictation_ai_rejects_invalid_translation_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationBackend"):
            DictationAiConfig.from_dict({"translationBackend": "invalid"})

    def test_dictation_ai_rejects_invalid_translation_runtime_options(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.translationDevice"):
            DictationAiConfig.from_dict({"translationDevice": "auto"})
        with self.assertRaisesRegex(ValueError, "dictationAi.translationDevice"):
            DictationAiConfig.from_dict({"translationDevice": "mps"})
        with self.assertRaisesRegex(ValueError, "dictationAi.translationComputeType"):
            DictationAiConfig.from_dict({"translationComputeType": "auto"})
        with self.assertRaisesRegex(ValueError, "dictationAi.translationComputeType"):
            DictationAiConfig.from_dict({"translationComputeType": "int8"})


    def test_dictation_ai_uses_chunk_seconds_as_legacy_window_seconds(self) -> None:
        loaded = DictationAiConfig.from_dict({"chunkSeconds": 3.5})

        self.assertEqual(loaded.chunkSeconds, 3.5)
        self.assertEqual(loaded.windowSeconds, 3.5)

    def test_dictation_ai_uses_language_specific_runtime_defaults(self) -> None:
        zh = DictationAiConfig.from_dict({"language": "zh"})
        en = DictationAiConfig.from_dict({"language": "en"})
        ko = DictationAiConfig.from_dict({"language": "ko"})

        self.assertEqual(zh.stepSeconds, 1.0)
        self.assertEqual(zh.windowSeconds, 12.0)
        self.assertEqual(zh.chunkSeconds, 12.0)
        self.assertEqual(en.windowSeconds, 7.0)
        self.assertEqual(ko.windowSeconds, 7.0)

    def test_dictation_ai_selected_language_migrates_legacy_runtime_values(self) -> None:
        loaded = DictationAiConfig.from_dict({"language": "zh", "windowSeconds": 24.0, "stepSeconds": 1.0})

        self.assertEqual(loaded.windowSeconds, 24.0)
        self.assertEqual(loaded.windowSecondsZh, 24.0)
        self.assertEqual(loaded.stepSecondsZh, 1.0)
        self.assertEqual(loaded.windowSecondsEn, 7.0)

    def test_dictation_ai_rejects_invalid_speed_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "dictationAi.chunkSeconds"):
            DictationAiConfig.from_dict({"chunkSeconds": 0.5})
        with self.assertRaisesRegex(ValueError, "dictationAi.stepSeconds"):
            DictationAiConfig.from_dict({"stepSeconds": 0.25})
        with self.assertRaisesRegex(ValueError, "dictationAi.windowSeconds"):
            DictationAiConfig.from_dict({"windowSeconds": 0.5})
        with self.assertRaisesRegex(ValueError, "dictationAi.stepSeconds"):
            DictationAiConfig.from_dict({"stepSeconds": 5.0, "windowSeconds": 4.0})
        with self.assertRaisesRegex(ValueError, "dictationAi.stepSecondsZh"):
            DictationAiConfig.from_dict({"language": "zh", "stepSecondsZh": 5.0, "windowSecondsZh": 4.0})
        with self.assertRaisesRegex(ValueError, "dictationAi.beamSize"):
            DictationAiConfig.from_dict({"beamSize": 0})
        with self.assertRaisesRegex(ValueError, "dictationAi.maxNewTokens"):
            DictationAiConfig.from_dict({"maxNewTokens": 8})
        with self.assertRaisesRegex(ValueError, "dictationAi.temperature"):
            DictationAiConfig.from_dict({"temperature": 1.5})
        with self.assertRaisesRegex(ValueError, "dictationAi.postProcessingProfile"):
            DictationAiConfig.from_dict({"postProcessingProfile": "invalid"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sttBackendZh"):
            DictationAiConfig.from_dict({"sttBackendZh": "invalid"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sttBackendZh"):
            DictationAiConfig.from_dict({"sttBackendZh": "funasr-paraformer"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sttBackendEn"):
            DictationAiConfig.from_dict({"sttBackendEn": "funasr-paraformer"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sttBackendKo"):
            DictationAiConfig.from_dict({"sttBackendKo": "funasr-sensevoice"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sttModelZh"):
            DictationAiConfig.from_dict({"sttModelZh": ""})
        with self.assertRaisesRegex(ValueError, "dictationAi.sentenceBoundaryBackend"):
            DictationAiConfig.from_dict({"sentenceBoundaryBackend": "invalid"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sentenceBoundaryBackend"):
            DictationAiConfig.from_dict({"sentenceBoundaryBackend": "regex"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sentenceBoundaryBackendZh"):
            DictationAiConfig.from_dict({"sentenceBoundaryBackendZh": "regex"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sentenceBoundaryDevice"):
            DictationAiConfig.from_dict({"sentenceBoundaryDevice": "mps"})
        with self.assertRaisesRegex(ValueError, "dictationAi.sentenceBoundaryComputeType"):
            DictationAiConfig.from_dict({"sentenceBoundaryComputeType": "int8"})
        with self.assertRaisesRegex(ValueError, "dictationAi.translationBeamSize"):
            DictationAiConfig.from_dict({"translationBeamSize": 0})
        with self.assertRaisesRegex(ValueError, "dictationAi.translationMaxNewTokens"):
            DictationAiConfig.from_dict({"translationMaxNewTokens": 8})


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from src.domain.config import AppConfig, WhisperConfig
from src.domain.contracts.whisper import (
    whisper_translation_backends_for_language,
    whisper_translation_models_for_backend,
    whisper_translation_targets_for_backend,
)
from src.domain.whisper_defaults import whisper_default
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


class WhisperConfigTest(unittest.TestCase):
    def test_build_config_includes_whisper_settings(self) -> None:
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
            whisper_enabled=True,
            whisper_input_device="pulse",
            whisper_backend="mock",
            whisper_model="tiny",
            whisper_stt_backend_en="faster-whisper",
            whisper_stt_model_en="tiny",
            whisper_stt_backend_ko="faster-whisper",
            whisper_stt_model_ko="large-v3",
            whisper_stt_backend_zh="qwen3-asr-transformers",
            whisper_stt_model_zh="qwen3-asr-0.6b",
            whisper_language="en",
            whisper_task="transcribe",
            whisper_translation_enabled=True,
            whisper_translation_target_language="ko",
            whisper_translation_backend="nllb-transformers",
            whisper_translation_model="facebook/nllb-200-distilled-600M",
            whisper_translation_device="cpu",
            whisper_translation_compute_type="float32",
            whisper_translation_beam_size=3,
            whisper_translation_max_new_tokens=256,
            whisper_device="cpu",
            whisper_compute_type="int8",
            whisper_step_seconds=1.0,
            whisper_window_seconds=4.0,
            whisper_commit_lag_seconds=1.0,
            whisper_beam_size=1,
            whisper_max_new_tokens=128,
            whisper_temperature=0.2,
        )

        self.assertEqual(
            config["whisper"],
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
                "device": "cpu",
                "computeType": "int8",
                "chunkSeconds": 4.0,
                "stepSeconds": 1.0,
                "windowSeconds": 4.0,
                "commitLagSeconds": 1.0,
                "beamSize": 1,
                "maxNewTokens": 128,
                "temperature": 0.2,
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
            whisper_backend="mock",
            whisper_chunk_seconds=2.5,
        )

        self.assertEqual(config["whisper"]["chunkSeconds"], 2.5)
        self.assertEqual(config["whisper"]["windowSeconds"], 2.5)

    def test_app_config_loads_whisper_settings(self) -> None:
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
            whisper_enabled=True,
            whisper_input_device="pulse",
            whisper_backend="mock",
            whisper_model="base",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            loaded = AppConfig.load(path)

        self.assertTrue(loaded.whisper.enabled)
        self.assertEqual(loaded.whisper.inputDevice, "pulse")
        self.assertEqual(loaded.whisper.backend, "mock")
        self.assertEqual(loaded.whisper.model, "base")
        self.assertEqual(loaded.whisper.sttBackendEn, whisper_default("sttBackendEn"))
        self.assertEqual(loaded.whisper.sttModelEn, whisper_default("sttModelEn"))
        self.assertEqual(loaded.whisper.sttBackendZh, "faster-whisper")
        self.assertEqual(loaded.whisper.sttModelZh, "large-v3")
        self.assertFalse(loaded.whisper.translationEnabled)
        self.assertFalse(loaded.whisper.showSttStatusWindow)
        self.assertEqual(loaded.whisper.translationTargetLanguage, whisper_default("translationTargetLanguage"))
        self.assertEqual(loaded.whisper.translationBackend, whisper_default("translationBackend"))
        self.assertEqual(loaded.whisper.translationModel, "facebook/nllb-200-distilled-600M")
        self.assertEqual(loaded.whisper.translationDevice, "cuda")
        self.assertEqual(loaded.whisper.translationComputeType, "float16")
        self.assertEqual(loaded.whisper.translationBeamSize, whisper_default("translationBeamSize"))
        self.assertEqual(loaded.whisper.translationMaxNewTokens, whisper_default("translationMaxNewTokens"))
        self.assertEqual(loaded.whisper.chunkSeconds, whisper_default("chunkSeconds"))
        self.assertEqual(loaded.whisper.stepSeconds, whisper_default("stepSeconds"))
        self.assertEqual(loaded.whisper.windowSeconds, whisper_default("windowSeconds"))
        self.assertEqual(loaded.whisper.commitLagSeconds, whisper_default("commitLagSeconds"))
        self.assertEqual(loaded.whisper.beamSize, whisper_default("beamSize"))
        self.assertEqual(loaded.whisper.maxNewTokens, whisper_default("maxNewTokens"))
        self.assertEqual(loaded.whisper.temperature, whisper_default("temperature"))
        self.assertEqual(loaded.whisper.sentenceBoundaryBackend, whisper_default("sentenceBoundaryBackend"))
        self.assertEqual(loaded.whisper.sentenceBoundaryModel, whisper_default("sentenceBoundaryModel"))
        self.assertEqual(loaded.whisper.sentenceBoundaryDevice, whisper_default("sentenceBoundaryDevice"))
        self.assertEqual(loaded.whisper.sentenceBoundaryComputeType, whisper_default("sentenceBoundaryComputeType"))



    def test_whisper_rejects_removed_chinese_funasr_stt_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.sttBackendZh"):
            WhisperConfig.from_dict({
                "language": "zh",
                "postProcessingProfile": "manual",
                "sttBackendZh": "funasr-paraformer",
                "sttModelZh": "paraformer-zh",
            })

    def test_whisper_supports_manual_post_processing_only(self) -> None:
        loaded = WhisperConfig.from_dict({
            "language": "zh",
            "postProcessingProfile": "manual",
            "sentenceBoundaryBackend": "sat",
            "sentenceBoundaryModel": "sat-3l-sm",
        })

        self.assertEqual(loaded.postProcessingProfile, "manual")
        self.assertEqual(loaded.sentenceBoundaryBackend, "sat")
        self.assertEqual(loaded.sentenceBoundaryModel, "sat-3l-sm")
        with self.assertRaisesRegex(ValueError, "whisper.postProcessingProfile"):
            WhisperConfig.from_dict({"postProcessingProfile": "auto-by-language"})

    def test_whisper_rejects_invalid_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.backend"):
            WhisperConfig.from_dict({"backend": "invalid"})

    def test_whisper_rejects_invalid_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.language"):
            WhisperConfig.from_dict({"language": "ja"})
        with self.assertRaisesRegex(ValueError, "whisper.language"):
            WhisperConfig.from_dict({"language": "auto"})

    def test_whisper_treats_legacy_translate_task_as_translation_enabled(self) -> None:
        loaded = WhisperConfig.from_dict({"task": "translate"})

        self.assertTrue(loaded.translationEnabled)
        self.assertEqual(loaded.task, "translate")

    def test_whisper_rejects_invalid_translation_target_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.translationTargetLanguage"):
            WhisperConfig.from_dict({"translationTargetLanguage": "ja"})

    def test_whisper_requires_english_target_for_whisper_translation_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.translationTargetLanguage"):
            WhisperConfig.from_dict({"translationEnabled": True, "translationBackend": "whisper", "translationTargetLanguage": "ko"})

    def test_whisper_translation_contract_groups_by_language_and_backend(self) -> None:
        self.assertIn("m2m100-transformers", whisper_translation_backends_for_language("zh"))
        self.assertEqual(
            whisper_translation_targets_for_backend("zh", "whisper"),
            ("en",),
        )
        self.assertIn("ko", whisper_translation_targets_for_backend("zh", "m2m100-transformers"))
        self.assertEqual(
            whisper_translation_models_for_backend("m2m100-transformers"),
            ("facebook/m2m100_1.2B",),
        )
        self.assertIn("facebook/nllb-200-3.3B", whisper_translation_models_for_backend("nllb-transformers"))

    def test_whisper_allows_multilingual_translation_target_with_nllb_backend(self) -> None:
        loaded = WhisperConfig.from_dict({
            "translationEnabled": True,
            "translationBackend": "nllb-transformers",
            "translationTargetLanguage": "ko",
        })

        self.assertTrue(loaded.translationEnabled)
        self.assertEqual(loaded.task, "transcribe")
        self.assertEqual(loaded.translationTargetLanguage, "ko")
        self.assertEqual(loaded.translationBackend, "nllb-transformers")

    def test_whisper_allows_m2m100_translation_backend(self) -> None:
        loaded = WhisperConfig.from_dict({
            "language": "zh",
            "translationEnabled": True,
            "translationBackend": "m2m100-transformers",
            "translationTargetLanguage": "ko",
            "translationModel": "facebook/m2m100_1.2B",
        })

        self.assertEqual(loaded.translationBackend, "m2m100-transformers")
        self.assertEqual(loaded.translationModel, "facebook/m2m100_1.2B")

    def test_whisper_rejects_translation_model_not_allowed_for_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.translationModel"):
            WhisperConfig.from_dict({
                "translationEnabled": True,
                "translationBackend": "m2m100-transformers",
                "translationTargetLanguage": "ko",
                "translationModel": "facebook/nllb-200-distilled-600M",
            })

    def test_whisper_rejects_translate_task_for_nllb_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.task"):
            WhisperConfig.from_dict({
                "task": "translate",
                "translationEnabled": True,
                "translationBackend": "nllb-transformers",
                "translationTargetLanguage": "ko",
            })

    def test_whisper_rejects_cpu_for_enabled_nllb_translation(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.translationDevice"):
            WhisperConfig.from_dict({
                "translationEnabled": True,
                "translationBackend": "nllb-transformers",
                "translationDevice": "cpu",
            })

    def test_whisper_rejects_invalid_translation_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.translationBackend"):
            WhisperConfig.from_dict({"translationBackend": "invalid"})

    def test_whisper_rejects_invalid_translation_runtime_options(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.translationDevice"):
            WhisperConfig.from_dict({"translationDevice": "auto"})
        with self.assertRaisesRegex(ValueError, "whisper.translationDevice"):
            WhisperConfig.from_dict({"translationDevice": "mps"})
        with self.assertRaisesRegex(ValueError, "whisper.translationComputeType"):
            WhisperConfig.from_dict({"translationComputeType": "auto"})
        with self.assertRaisesRegex(ValueError, "whisper.translationComputeType"):
            WhisperConfig.from_dict({"translationComputeType": "int8"})


    def test_whisper_uses_chunk_seconds_as_legacy_window_seconds(self) -> None:
        loaded = WhisperConfig.from_dict({"chunkSeconds": 3.5})

        self.assertEqual(loaded.chunkSeconds, 3.5)
        self.assertEqual(loaded.windowSeconds, 3.5)

    def test_whisper_rejects_invalid_speed_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.chunkSeconds"):
            WhisperConfig.from_dict({"chunkSeconds": 0.5})
        with self.assertRaisesRegex(ValueError, "whisper.stepSeconds"):
            WhisperConfig.from_dict({"stepSeconds": 0.25})
        with self.assertRaisesRegex(ValueError, "whisper.windowSeconds"):
            WhisperConfig.from_dict({"windowSeconds": 0.5})
        with self.assertRaisesRegex(ValueError, "whisper.stepSeconds"):
            WhisperConfig.from_dict({"stepSeconds": 5.0, "windowSeconds": 4.0})
        with self.assertRaisesRegex(ValueError, "whisper.commitLagSeconds"):
            WhisperConfig.from_dict({"commitLagSeconds": 4.0, "windowSeconds": 4.0})
        with self.assertRaisesRegex(ValueError, "whisper.beamSize"):
            WhisperConfig.from_dict({"beamSize": 0})
        with self.assertRaisesRegex(ValueError, "whisper.maxNewTokens"):
            WhisperConfig.from_dict({"maxNewTokens": 8})
        with self.assertRaisesRegex(ValueError, "whisper.temperature"):
            WhisperConfig.from_dict({"temperature": 1.5})
        with self.assertRaisesRegex(ValueError, "whisper.postProcessingProfile"):
            WhisperConfig.from_dict({"postProcessingProfile": "invalid"})
        with self.assertRaisesRegex(ValueError, "whisper.sttBackendZh"):
            WhisperConfig.from_dict({"sttBackendZh": "invalid"})
        with self.assertRaisesRegex(ValueError, "whisper.sttBackendZh"):
            WhisperConfig.from_dict({"sttBackendZh": "funasr-paraformer"})
        with self.assertRaisesRegex(ValueError, "whisper.sttBackendEn"):
            WhisperConfig.from_dict({"sttBackendEn": "funasr-paraformer"})
        with self.assertRaisesRegex(ValueError, "whisper.sttBackendKo"):
            WhisperConfig.from_dict({"sttBackendKo": "funasr-sensevoice"})
        with self.assertRaisesRegex(ValueError, "whisper.sttModelZh"):
            WhisperConfig.from_dict({"sttModelZh": ""})
        with self.assertRaisesRegex(ValueError, "whisper.sentenceBoundaryBackend"):
            WhisperConfig.from_dict({"sentenceBoundaryBackend": "invalid"})
        with self.assertRaisesRegex(ValueError, "whisper.sentenceBoundaryBackend"):
            WhisperConfig.from_dict({"sentenceBoundaryBackend": "regex"})
        with self.assertRaisesRegex(ValueError, "whisper.sentenceBoundaryBackendZh"):
            WhisperConfig.from_dict({"sentenceBoundaryBackendZh": "regex"})
        with self.assertRaisesRegex(ValueError, "whisper.sentenceBoundaryDevice"):
            WhisperConfig.from_dict({"sentenceBoundaryDevice": "mps"})
        with self.assertRaisesRegex(ValueError, "whisper.sentenceBoundaryComputeType"):
            WhisperConfig.from_dict({"sentenceBoundaryComputeType": "int8"})
        with self.assertRaisesRegex(ValueError, "whisper.translationBeamSize"):
            WhisperConfig.from_dict({"translationBeamSize": 0})
        with self.assertRaisesRegex(ValueError, "whisper.translationMaxNewTokens"):
            WhisperConfig.from_dict({"translationMaxNewTokens": 8})


if __name__ == "__main__":
    unittest.main()

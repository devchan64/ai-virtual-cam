import json
import tempfile
import unittest
from pathlib import Path

from src.domain.config import AppConfig, WhisperConfig
from src.tools.config_builder import build_config


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
            whisper_language="en",
            whisper_task="transcribe",
            whisper_translation_enabled=True,
            whisper_translation_target_language="ko",
            whisper_translation_backend="nllb-transformers",
            whisper_translation_model="facebook/nllb-200-distilled-600M",
            whisper_translation_device="cpu",
            whisper_translation_compute_type="float32",
            whisper_device="cpu",
            whisper_compute_type="int8",
            whisper_vad_filter=False,
            whisper_chunk_seconds=2.5,
            whisper_beam_size=1,
        )

        self.assertEqual(
            config["whisper"],
            {
                "enabled": True,
                "inputDevice": "pulse",
                "backend": "mock",
                "model": "tiny",
                "language": "en",
                "task": "transcribe",
                "translationEnabled": True,
                "translationTargetLanguage": "ko",
                "translationBackend": "nllb-transformers",
                "translationModel": "facebook/nllb-200-distilled-600M",
                "translationDevice": "cpu",
                "translationComputeType": "float32",
                "device": "cpu",
                "computeType": "int8",
                "vadFilter": False,
                "chunkSeconds": 2.5,
                "beamSize": 1,
            },
        )

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
        self.assertFalse(loaded.whisper.translationEnabled)
        self.assertEqual(loaded.whisper.translationTargetLanguage, "en")
        self.assertEqual(loaded.whisper.translationBackend, "whisper")
        self.assertEqual(loaded.whisper.translationModel, "facebook/nllb-200-distilled-600M")
        self.assertEqual(loaded.whisper.translationDevice, "cuda")
        self.assertEqual(loaded.whisper.translationComputeType, "float16")
        self.assertEqual(loaded.whisper.chunkSeconds, 5.0)
        self.assertEqual(loaded.whisper.beamSize, 5)

    def test_whisper_rejects_invalid_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.backend"):
            WhisperConfig.from_dict({"backend": "invalid"})

    def test_whisper_rejects_invalid_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.language"):
            WhisperConfig.from_dict({"language": "ja"})

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

    def test_whisper_allows_multilingual_translation_target_with_nllb_backend(self) -> None:
        loaded = WhisperConfig.from_dict({
            "translationEnabled": True,
            "translationBackend": "nllb-transformers",
            "translationTargetLanguage": "ko",
        })

        self.assertTrue(loaded.translationEnabled)
        self.assertEqual(loaded.translationTargetLanguage, "ko")
        self.assertEqual(loaded.translationBackend, "nllb-transformers")

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

    def test_whisper_rejects_invalid_speed_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.chunkSeconds"):
            WhisperConfig.from_dict({"chunkSeconds": 0.5})
        with self.assertRaisesRegex(ValueError, "whisper.beamSize"):
            WhisperConfig.from_dict({"beamSize": 0})


if __name__ == "__main__":
    unittest.main()

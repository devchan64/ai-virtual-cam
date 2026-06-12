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
            whisper_task="translate",
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
                "task": "translate",
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
        self.assertEqual(loaded.whisper.chunkSeconds, 5.0)
        self.assertEqual(loaded.whisper.beamSize, 5)

    def test_whisper_rejects_invalid_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.backend"):
            WhisperConfig.from_dict({"backend": "invalid"})

    def test_whisper_rejects_invalid_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.language"):
            WhisperConfig.from_dict({"language": "ja"})

    def test_whisper_rejects_invalid_speed_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "whisper.chunkSeconds"):
            WhisperConfig.from_dict({"chunkSeconds": 0.5})
        with self.assertRaisesRegex(ValueError, "whisper.beamSize"):
            WhisperConfig.from_dict({"beamSize": 0})


if __name__ == "__main__":
    unittest.main()

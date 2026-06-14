import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "setup" / "download-whisper-models.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("download_whisper_models", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DownloadWhisperModelsTest(unittest.TestCase):
    def test_with_modelscope_file_lock_disabled_for_download_sets_and_unsets_env(self) -> None:
        module = _load_module()
        with patch.dict(module.os.environ, {}, clear=True):
            with module._with_modelscope_file_lock_disabled_for_download():
                self.assertEqual(module.os.environ.get("MODELSCOPE_HUB_FILE_LOCK"), "false")
            self.assertIsNone(module.os.environ.get("MODELSCOPE_HUB_FILE_LOCK"))

    def test_with_modelscope_file_lock_disabled_for_download_preserves_existing_value(self) -> None:
        module = _load_module()
        with patch.dict(module.os.environ, {"MODELSCOPE_HUB_FILE_LOCK": "true"}):
            with module._with_modelscope_file_lock_disabled_for_download():
                self.assertEqual(module.os.environ.get("MODELSCOPE_HUB_FILE_LOCK"), "true")
            self.assertEqual(module.os.environ.get("MODELSCOPE_HUB_FILE_LOCK"), "true")

    def test_funasr_cache_rejects_partial_modelscope_directory(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            model_dir = home / ".cache" / "modelscope" / "hub" / "models" / "iic" / "SenseVoiceSmall"
            model_dir.mkdir(parents=True)
            (model_dir / "README.md").write_text("partial", encoding="utf-8")

            with patch("src.app.model_cache.Path.home", return_value=home):
                self.assertFalse(module.is_funasr_model_cached("iic/SenseVoiceSmall"))

    def test_funasr_cache_accepts_config_and_weights(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            model_dir = home / ".cache" / "modelscope" / "hub" / "models" / "iic" / "SenseVoiceSmall"
            model_dir.mkdir(parents=True)
            (model_dir / "configuration.json").write_text("{}", encoding="utf-8")
            (model_dir / "model.pt").write_bytes(b"weights")

            with patch("src.app.model_cache.Path.home", return_value=home):
                self.assertTrue(module.is_funasr_model_cached("iic/SenseVoiceSmall"))

    def test_download_progress_reports_downloaded_and_total_bytes(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()

            def action() -> None:
                (cache_dir / "model.bin").write_bytes(b"x" * 2048)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                module._run_with_progress("test:model", [cache_dir], 4096, action)

            text = output.getvalue()
            self.assertIn("Download progress: test:model", text)
            self.assertIn("downloaded=2.0KB", text)
            self.assertIn("total=4.0KB", text)
            self.assertIn("percent=50.0", text)

    def test_download_progress_reports_unknown_total(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()

            def action() -> None:
                (cache_dir / "model.bin").write_bytes(b"x" * 1024)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                module._run_with_progress("test:model", [cache_dir], None, action)

            text = output.getvalue()
            self.assertIn("downloaded=1.0KB", text)
            self.assertIn("total=unknown", text)


if __name__ == "__main__":
    unittest.main()

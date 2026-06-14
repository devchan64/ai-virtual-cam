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
    def test_check_model_assets_marks_missing_qwen_asr_model(self) -> None:
        module = _load_module()
        asset = module.ModelAsset("stt", "qwen3-asr-transformers", "qwen3-asr-0.6b")

        with patch.object(module, "is_qwen_asr_model_cached", return_value=False):
            missing = module.check_model_assets([asset])

        self.assertEqual(missing, [asset])

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

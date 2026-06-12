import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.app.whisper_window import (
    _sanitize_window_geometry,
    _save_window_geometry,
)


class WhisperWindowGeometryTest(unittest.TestCase):
    def test_saves_geometry_in_config_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"whisper": {"enabled": True}, "meta": {"language": "ko"}}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                _save_window_geometry(path, "whisperWindowGeometry", "820x460+120+80")

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"]["language"], "ko")
        self.assertEqual(raw["meta"]["whisperWindowGeometry"], "820x460+120+80")

    def test_skips_invalid_geometry_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "setting.json"
            path.write_text(json.dumps({"meta": {"whisperWindowGeometry": "820x460+120+80"}}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                _save_window_geometry(path, "whisperWindowGeometry", "820x460+5000+80", 1920, 1080)

            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["meta"]["whisperWindowGeometry"], "820x460+120+80")

    def test_sanitizes_geometry_before_restore(self) -> None:
        self.assertEqual(
            _sanitize_window_geometry("820x460+120+80", 1920, 1080),
            "820x460+120+80",
        )
        self.assertIsNone(_sanitize_window_geometry("200x100+120+80", 1920, 1080))
        self.assertIsNone(_sanitize_window_geometry("820x460+5000+80", 1920, 1080))
        self.assertIsNone(_sanitize_window_geometry("invalid", 1920, 1080))


if __name__ == "__main__":
    unittest.main()

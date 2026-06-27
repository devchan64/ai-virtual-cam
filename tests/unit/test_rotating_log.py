import io
import logging
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app import rotating_log


class RotatingLogTest(unittest.TestCase):
    def test_default_backup_count_keeps_long_monitoring_logs(self) -> None:
        self.assertEqual(rotating_log.DEFAULT_BACKUP_COUNT, 1000)

    def test_timestamped_log_filename_includes_name_and_timestamp(self) -> None:
        filename = rotating_log._timestamped_log_filename("avc-whisper")
        self.assertRegex(filename, r"^avc-whisper-\d{8}-\d{6}\.log$")

    def test_install_rotating_stdout_log_uses_default_backup_count(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_handler(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return logging.NullHandler()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(rotating_log, "_repo_root", return_value=Path(tmpdir)):
                with patch.object(rotating_log, "RotatingFileHandler", side_effect=fake_handler):
                    with patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
                        log_path = rotating_log.install_rotating_stdout_log("avc-whisper")

        self.assertEqual(calls[0]["kwargs"]["backupCount"], 1000)
        self.assertRegex(log_path.name, r"^avc-whisper-\d{8}-\d{6}\.log$")

    def test_install_rotating_stdout_log_allows_env_backup_count_override(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_handler(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return logging.NullHandler()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(rotating_log, "_repo_root", return_value=Path(tmpdir)):
                with patch.object(rotating_log, "RotatingFileHandler", side_effect=fake_handler):
                    with patch.dict("os.environ", {"AVC_LOG_BACKUP_COUNT": "17"}):
                        with patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
                            rotating_log.install_rotating_stdout_log("avc-serve")

        self.assertEqual(calls[0]["kwargs"]["backupCount"], 17)


if __name__ == "__main__":
    unittest.main()

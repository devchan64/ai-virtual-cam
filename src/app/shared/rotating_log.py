from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 1000


class _TeeStream:
    def __init__(self, original: TextIO, logger: logging.Logger, level: int) -> None:
        self._original = original
        self._logger = logger
        self._level = level
        self._lock = threading.Lock()
        self._buffer = ""

    def write(self, data: str) -> int:
        if not data:
            return 0
        with self._lock:
            written = self._original.write(data)
            self._buffer += data
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if line:
                    self._logger.log(self._level, line)
            return written

    def flush(self) -> None:
        with self._lock:
            self._original.flush()
            if self._buffer:
                self._logger.log(self._level, self._buffer.rstrip("\n"))
                self._buffer = ""

    def isatty(self) -> bool:
        return self._original.isatty()

    @property
    def encoding(self) -> str | None:
        return self._original.encoding


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _timestamped_log_filename(name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{name}-{timestamp}.log"


def install_rotating_stdout_log(name: str) -> Path:
    log_dir = _repo_root() / ".tmp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / _timestamped_log_filename(name)

    logger = logging.getLogger(f"avc.rotating.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=_int_from_env("AVC_LOG_MAX_BYTES", DEFAULT_MAX_BYTES),
        backupCount=_int_from_env("AVC_LOG_BACKUP_COUNT", DEFAULT_BACKUP_COUNT),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    sys.stdout = _TeeStream(sys.stdout, logger, logging.INFO)  # type: ignore[assignment]
    sys.stderr = _TeeStream(sys.stderr, logger, logging.ERROR)  # type: ignore[assignment]
    return log_path

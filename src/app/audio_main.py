#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.audio.mixer import VirtualAudioMixer
from src.domain.config import AppConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run virtual audio mixer (gate scaffold).")
    parser.add_argument(
        "--config",
        default="~/.avc/setting.json",
        help="Path to the JSON config file.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Optional step limit for smoke tests. 0 means unlimited.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser()
    print(f"[audio] loading config: {config_path}", flush=True)
    config = AppConfig.load(config_path)
    if config.audio is None:
        raise RuntimeError("audio config not found. Add `audio` section to the config.")
    if not config.audio.enabled:
        raise RuntimeError("audio.enabled is false. Enable it to run mixer.")

    mixer = VirtualAudioMixer(config.audio)
    mixer.run(max_steps=args.max_steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())

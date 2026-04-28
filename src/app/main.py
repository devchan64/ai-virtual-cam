#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.adapter.capture.opencv_capture import OpenCVCapture
from src.adapter.output.opencv_output import OpenCVOutput
from src.domain.config import AppConfig
from src.pipeline.runner import PipelineRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ai-virtual-cam pipeline.")
    parser.add_argument(
        "--config",
        default="config/settings.json",
        help="Path to the JSON config file.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Optional frame limit for smoke tests. 0 means unlimited.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    config = AppConfig.load(config_path)

    capture = OpenCVCapture(config.inputCamera)
    output = OpenCVOutput(config.outputCamera)

    runner = PipelineRunner(
        config=config,
        capture=capture,
        output=output,
    )
    runner.run(max_frames=args.max_frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())

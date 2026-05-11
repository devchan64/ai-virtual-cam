#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.adapter.capture.opencv_capture import OpenCVCapture
from src.adapter.output.factory import build_output
from src.domain.config import AppConfig
from src.pipeline.runner import PipelineRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ai-virtual-cam pipeline.")
    parser.add_argument(
        "--config",
        default="~/.avc/setting.json",
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
    config_path = Path(args.config).expanduser()
    print(f"[avc] loading config: {config_path}", flush=True)
    config = AppConfig.load(config_path)
    print(
        "[avc] config loaded: "
        f"input={config.inputCamera.devicePath} "
        f"output_backend={config.outputCamera.backend} "
        f"output={config.outputCamera.width}x{config.outputCamera.height}@{config.outputCamera.fps}",
        flush=True,
    )

    print("[avc] opening input capture...", flush=True)
    capture = OpenCVCapture(config.inputCamera)
    print("[avc] creating output sink...", flush=True)
    output = build_output(config.outputCamera)
    print("[avc] pipeline starting", flush=True)
    if config.outputCamera.backend == "pyvirtualcam":
        print(
            "[avc] macOS OBS 경로 안내: serve 실행 중 Chrome/Meet가 이미 열려 있었다면 브라우저를 완전히 재시작하세요.",
            flush=True,
        )

    runner = PipelineRunner(
        config=config,
        capture=capture,
        output=output,
    )
    runner.run(max_frames=args.max_frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())

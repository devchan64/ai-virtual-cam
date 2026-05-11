#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from src.adapter.capture.opencv_capture import OpenCVCapture
from src.adapter.output.factory import build_output
from src.audio.mixer import VirtualAudioMixer
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
    parser.add_argument(
        "--audio-mode",
        choices=["auto", "on", "off"],
        default="auto",
        help="Audio mixer activation mode. auto=use config, on=force enable, off=disable.",
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
    audio_mixer: VirtualAudioMixer | None = None
    audio_thread: threading.Thread | None = None
    want_audio = args.audio_mode == "on" or (
        args.audio_mode == "auto" and config.audio is not None and config.audio.enabled
    )
    if want_audio:
        if config.audio is None:
            raise RuntimeError("audio-mode is on but audio config is missing.")
        audio_mixer = VirtualAudioMixer(config.audio)
        audio_thread = threading.Thread(target=audio_mixer.run, kwargs={"max_steps": 0}, daemon=True)
        audio_thread.start()
        print("[avc] audio mixer started (integrated with serve)", flush=True)
    else:
        print("[avc] audio mixer disabled", flush=True)

    try:
        runner.run(max_frames=args.max_frames)
    finally:
        if audio_mixer is not None:
            audio_mixer.stop()
        if audio_thread is not None:
            audio_thread.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())

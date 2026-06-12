#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path

from src.adapter.capture.opencv_capture import OpenCVCapture
from src.adapter.output.factory import build_output
from src.audio.mixer import VirtualAudioMixer
from src.domain.config import AppConfig
from src.pipeline.runner import PipelineRunner


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _nvidia_library_paths() -> list[str]:
    paths: list[str] = []
    for mod_name in ("nvidia.cublas.lib", "nvidia.cudnn.lib"):
        try:
            mod = __import__(mod_name, fromlist=["*"])
            for item in getattr(mod, "__path__", []):
                value = os.fspath(item)
                if value and value not in paths:
                    paths.append(value)
            filename = getattr(mod, "__file__", None)
            if filename:
                value = os.path.dirname(os.fspath(filename))
                if value and value not in paths:
                    paths.append(value)
        except Exception:
            continue
    return paths


def _child_env_with_nvidia_libraries() -> dict[str, str]:
    env = dict(os.environ)
    paths = _nvidia_library_paths()
    if paths:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(paths + ([existing] if existing else []))
        _log(f"[avc] whisper CUDA library path: {':'.join(paths)}")
    else:
        _log("[avc] whisper CUDA library path not found in Python environment")
    return env

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
        "--with-whisper-window",
        action="store_true",
        help="Open the selectable Whisper transcript window when whisper.enabled=true.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser()
    _log(f"[avc] loading config: {config_path}")
    config = AppConfig.load(config_path)
    _log(
        "[avc] config loaded: "
        f"input={config.inputCamera.devicePath} "
        f"output_backend={config.outputCamera.backend} "
        f"output={config.outputCamera.width}x{config.outputCamera.height}@{config.outputCamera.fps}"
    )

    _log("[avc] opening input capture...")
    capture = OpenCVCapture(config.inputCamera)
    _log("[avc] creating output sink...")
    output = build_output(config.outputCamera)
    _log("[avc] pipeline starting")
    if config.outputCamera.backend == "pyvirtualcam":
        _log(
            "[avc] macOS OBS 경로 안내: serve 실행 중 Chrome/Meet가 이미 열려 있었다면 브라우저를 완전히 재시작하세요."
        )

    runner = PipelineRunner(
        config=config,
        capture=capture,
        output=output,
    )
    whisper_process: subprocess.Popen | None = None
    if args.with_whisper_window and config.whisper.enabled:
        whisper_cmd = [sys.executable, "-m", "src.app.whisper_window", "--config", str(config_path)]
        try:
            whisper_process = subprocess.Popen(whisper_cmd, env=_child_env_with_nvidia_libraries())
            _log(f"[avc] whisper transcript window started (pid={whisper_process.pid})")
        except Exception as exc:
            raise RuntimeError(
                "Whisper 출력 창을 시작하지 못했습니다. "
                f"config whisper={config.whisper}. 실패 원인: {exc}. "
                "DISPLAY/Tkinter/CUDA/faster-whisper 설치 상태를 확인하세요."
            ) from exc
    elif args.with_whisper_window:
        _log("[avc] whisper transcript window disabled by config (whisper.enabled=false)")
    else:
        _log("[avc] whisper transcript window disabled for CLI serve (use config GUI Serve to open it)")

    audio_mixer: VirtualAudioMixer | None = None
    audio_thread: threading.Thread | None = None

    def _audio_stream_state(opened: bool, gate_state: str, step: int) -> None:
        action = "열림" if opened else "닫힘"
        _log(f"[avc] 오디오 게이트 스트림 {action}: step={step} gate_state={gate_state}")

    want_audio = config.audio is not None and config.audio.enabled
    if want_audio:
        audio_mixer = VirtualAudioMixer(config.audio, on_stream_state=_audio_stream_state)
        audio_thread = threading.Thread(target=audio_mixer.run, kwargs={"max_steps": 0}, daemon=True)
        audio_thread.start()
        _log("[avc] audio mixer enabled by config (audio.enabled=true)")
    else:
        _log("[avc] audio mixer disabled by config (audio.enabled=false)")

    def _request_shutdown(signum: int, frame_obj) -> None:
        _log(f"[avc] received signal {signum}, stopping pipeline...")
        runner.stop()
        if audio_mixer is not None:
            audio_mixer.stop()
        if whisper_process is not None and whisper_process.poll() is None:
            whisper_process.terminate()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    try:
        runner.run(max_frames=args.max_frames)
    except KeyboardInterrupt:
        runner.stop()
        if audio_mixer is not None:
            audio_mixer.stop()
        raise
    finally:
        if audio_mixer is not None:
            audio_mixer.stop()
        if audio_thread is not None:
            audio_thread.join(timeout=1.0)
        if whisper_process is not None and whisper_process.poll() is None:
            whisper_process.terminate()
            try:
                whisper_process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                whisper_process.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())

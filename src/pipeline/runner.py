from __future__ import annotations

import time

from src.domain.config import AppConfig
from src.pipeline.frame_processor import FrameProcessor


class PipelineRunner:
    def __init__(self, config: AppConfig, capture, output) -> None:
        self._config = config
        self._capture = capture
        self._output = output
        self._running = True
        self._processor = FrameProcessor(
            config.segmentation,
            config.background,
            config.crop,
            config.faceEnhance,
            config.outputCamera.width,
            config.outputCamera.height,
        )

    def stop(self) -> None:
        self._running = False
        try:
            self._capture.release()
        except Exception:
            pass

    def run(self, max_frames: int = 0) -> None:
        frame_count = 0
        start_ts = time.monotonic()
        try:
            while self._running:
                try:
                    frame = self._capture.read()
                except RuntimeError:
                    if not self._running:
                        print("[pipeline] capture stopped during shutdown", flush=True)
                        break
                    raise
                output_frame = self._processor.process(frame)
                self._output.write(output_frame)

                frame_count += 1
                if max_frames > 0 and frame_count >= max_frames:
                    print(
                        f"[pipeline] stop condition reached: max_frames={max_frames}",
                        flush=True,
                    )
                    break
        finally:
            self._capture.release()
            self._output.release()

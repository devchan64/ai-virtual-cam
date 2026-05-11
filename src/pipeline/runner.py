from __future__ import annotations

import cv2
import time

from src.domain.config import AppConfig
from src.pipeline.frame_processor import FrameProcessor


class PipelineRunner:
    def __init__(self, config: AppConfig, capture, output) -> None:
        self._config = config
        self._capture = capture
        self._output = output
        self._processor = FrameProcessor(
            config.segmentation,
            config.background,
            config.crop,
            config.outputCamera.width,
            config.outputCamera.height,
        )

    def run(self, max_frames: int = 0) -> None:
        frame_count = 0
        start_ts = time.monotonic()
        try:
            while True:
                frame = self._capture.read()
                output_frame = self._processor.process(frame)
                self._output.write(output_frame)

                frame_count += 1
                if frame_count % 120 == 0:
                    elapsed = max(time.monotonic() - start_ts, 1e-6)
                    fps = frame_count / elapsed
                    print(
                        f"[pipeline] streaming heartbeat: frames={frame_count} avg_fps={fps:.2f}",
                        flush=True,
                    )
                if max_frames > 0 and frame_count >= max_frames:
                    break
        finally:
            self._capture.release()
            self._output.release()
            cv2.destroyAllWindows()

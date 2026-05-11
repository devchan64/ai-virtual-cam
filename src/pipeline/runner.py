from __future__ import annotations

import cv2
import time

from src.domain.config import AppConfig
from src.pipeline.background import BackgroundProvider
from src.pipeline.bounds import BoundsTracker
from src.pipeline.composer import Composer
from src.pipeline.mask_processing import refine_mask
from src.pipeline.segmentation import build_segmenter
from src.utils.image import crop_and_resize


class PipelineRunner:
    def __init__(self, config: AppConfig, capture, output) -> None:
        self._config = config
        self._capture = capture
        self._output = output
        self._segmenter = build_segmenter(config.segmentation)
        self._background = BackgroundProvider(
            config.background,
            config.outputCamera.width,
            config.outputCamera.height,
        )
        self._bounds = BoundsTracker(config.crop)
        self._composer = Composer()

    def run(self, max_frames: int = 0) -> None:
        frame_count = 0
        start_ts = time.monotonic()
        try:
            while True:
                frame = self._capture.read()
                raw_mask = self._segmenter.segment(frame)
                mask = refine_mask(
                    raw_mask,
                    self._config.segmentation.threshold,
                    edge_smoothness=self._config.segmentation.edgeSmoothness,
                    blend_feather=self._config.segmentation.blendFeather,
                )
                bounds = self._bounds.update(mask)

                background = self._background.frame()
                composed = self._composer.compose(frame, mask, background)
                output_frame = crop_and_resize(
                    composed,
                    self._bounds.as_rect(bounds),
                    self._config.outputCamera.width,
                    self._config.outputCamera.height,
                )
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

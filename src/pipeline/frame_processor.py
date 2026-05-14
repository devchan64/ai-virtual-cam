from __future__ import annotations

import numpy as np

from src.domain.config import BackgroundConfig, PersonCropConfig, SegmentationConfig
from src.pipeline.background import BackgroundProvider
from src.pipeline.bounds import BoundsTracker
from src.pipeline.composer import Composer
from src.pipeline.mask_processing import refine_mask
from src.pipeline.segmentation import build_segmenter
from src.utils.image import crop_and_resize


class FrameProcessor:
    def __init__(
        self,
        segmentation: SegmentationConfig,
        background: BackgroundConfig,
        crop: PersonCropConfig,
        output_width: int,
        output_height: int,
    ) -> None:
        self._seg_cfg = segmentation
        self._segmenter = build_segmenter(segmentation)
        self._background = BackgroundProvider(background, output_width, output_height)
        self._bounds = BoundsTracker(crop, output_width, output_height)
        self._composer = Composer()
        self._output_width = output_width
        self._output_height = output_height
        self._low_mask_ratio_logged = False

    def process(self, frame: np.ndarray) -> np.ndarray:
        raw_mask = self._segmenter.segment(frame)
        mask = refine_mask(
            raw_mask,
            self._seg_cfg.threshold,
            edge_smoothness=self._seg_cfg.edgeSmoothness,
            blend_feather=self._seg_cfg.blendFeather,
        )
        foreground_ratio = float((mask > 0).mean())
        if foreground_ratio < 0.05:
            if not self._low_mask_ratio_logged:
                print(
                    "[seg] warning: segmentation mask foreground ratio is very low "
                    f"({foreground_ratio:.3f}); passthrough source frame for visibility.",
                    flush=True,
                )
                self._low_mask_ratio_logged = True
            bounds = self._bounds.update(mask)
            return crop_and_resize(
                frame,
                self._bounds.as_rect(bounds),
                self._output_width,
                self._output_height,
            )

        bounds = self._bounds.update(mask)
        background = self._background.frame()
        composed = self._composer.compose(frame, mask, background)
        # Guardrail: avoid near-black output when segmentation is unstable.
        if foreground_ratio < 0.20:
            source_mean = float(frame.mean())
            composed_mean = float(composed.mean())
            if source_mean > 20.0 and composed_mean < 8.0:
                print(
                    "[seg] warning: composed frame is too dark under low foreground ratio "
                    f"(fg={foreground_ratio:.3f}, src_mean={source_mean:.2f}, out_mean={composed_mean:.2f}); "
                    "passthrough source frame.",
                    flush=True,
                )
                return crop_and_resize(
                    frame,
                    self._bounds.as_rect(bounds),
                    self._output_width,
                    self._output_height,
                )
        return crop_and_resize(
            composed,
            self._bounds.as_rect(bounds),
            self._output_width,
            self._output_height,
        )

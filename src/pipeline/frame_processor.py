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

    def process(self, frame: np.ndarray) -> np.ndarray:
        raw_mask = self._segmenter.segment(frame)
        mask = refine_mask(
            raw_mask,
            self._seg_cfg.threshold,
            edge_smoothness=self._seg_cfg.edgeSmoothness,
            blend_feather=self._seg_cfg.blendFeather,
        )
        bounds = self._bounds.update(mask)
        background = self._background.frame()
        composed = self._composer.compose(frame, mask, background)
        return crop_and_resize(
            composed,
            self._bounds.as_rect(bounds),
            self._output_width,
            self._output_height,
        )

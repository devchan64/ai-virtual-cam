from __future__ import annotations

from functools import cached_property

import cv2
import numpy as np

from src.domain.config import BackgroundConfig
from src.utils.image import crop_and_resize


class BackgroundProvider:
    def __init__(self, config: BackgroundConfig, output_width: int, output_height: int) -> None:
        self._config = config
        self._output_width = output_width
        self._output_height = output_height

    def frame(self) -> np.ndarray:
        if self._config.mode == "chroma":
            color = np.array(self._config.chromaColor, dtype=np.uint8)
            return np.full(
                (self._output_height, self._output_width, 3),
                color,
                dtype=np.uint8,
            )

        image = self._resized_image()
        if self._config.mode == "image":
            return image

        color = np.array(self._config.chromaColor, dtype=np.uint8)
        color_bg = np.full(
            (self._output_height, self._output_width, 3),
            color,
            dtype=np.uint8,
        )
        alpha = float(self._config.colorBlendAlpha)
        return cv2.addWeighted(image, 1.0 - alpha, color_bg, alpha, 0.0)

    def _resized_image(self) -> np.ndarray:
        image = self._image.copy()
        if self._config.crop is not None:
            return crop_and_resize(image, self._config.crop, self._output_width, self._output_height)
        return cv2.resize(image, (self._output_width, self._output_height), interpolation=cv2.INTER_LINEAR)

    @cached_property
    def _image(self) -> np.ndarray:
        assert self._config.imagePath is not None
        image = cv2.imread(self._config.imagePath)
        if image is None:
            raise RuntimeError(f"Failed to load background image: {self._config.imagePath}")
        return image

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

        image = self._image.copy()
        if self._config.crop is not None:
            image = crop_and_resize(image, self._config.crop, self._output_width, self._output_height)
        else:
            image = cv2.resize(image, (self._output_width, self._output_height), interpolation=cv2.INTER_LINEAR)
        return image

    @cached_property
    def _image(self) -> np.ndarray:
        assert self._config.imagePath is not None
        image = cv2.imread(self._config.imagePath)
        if image is None:
            raise RuntimeError(f"Failed to load background image: {self._config.imagePath}")
        return image

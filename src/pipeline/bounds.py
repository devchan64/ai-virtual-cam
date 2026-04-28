from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.domain.config import PersonCropConfig, Rect
from src.utils.math import clamp_int


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


class BoundsTracker:
    def __init__(self, config: PersonCropConfig) -> None:
        self._config = config
        self._previous: Bounds | None = None

    def update(self, mask: np.ndarray) -> Bounds:
        current = self._compute(mask)
        if self._previous is None:
            self._previous = current
            return current

        alpha = self._config.smoothing
        smoothed = Bounds(
            x=int(round(self._previous.x * alpha + current.x * (1.0 - alpha))),
            y=int(round(self._previous.y * alpha + current.y * (1.0 - alpha))),
            width=int(round(self._previous.width * alpha + current.width * (1.0 - alpha))),
            height=int(round(self._previous.height * alpha + current.height * (1.0 - alpha))),
        )
        self._previous = smoothed
        return smoothed

    def _compute(self, mask: np.ndarray) -> Bounds:
        height, width = mask.shape[:2]
        points = np.argwhere(mask > 0)
        if points.size == 0:
            return Bounds(0, 0, width, height)

        y_min, x_min = points.min(axis=0)
        y_max, x_max = points.max(axis=0)

        bbox_width = max(1, int(x_max - x_min + 1))
        bbox_height = max(1, int(y_max - y_min + 1))
        margin_x = int(round(bbox_width * self._config.margin))
        margin_y = int(round(bbox_height * self._config.margin))

        x = clamp_int(int(x_min) - margin_x, 0, width - 1)
        y = clamp_int(int(y_min) - margin_y, 0, height - 1)
        max_x = clamp_int(int(x_max) + margin_x, 0, width - 1)
        max_y = clamp_int(int(y_max) + margin_y, 0, height - 1)

        return Bounds(
            x=x,
            y=y,
            width=max(1, max_x - x + 1),
            height=max(1, max_y - y + 1),
        )

    def as_rect(self, bounds: Bounds) -> Rect:
        return Rect(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height)

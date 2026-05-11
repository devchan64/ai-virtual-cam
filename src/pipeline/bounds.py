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
        self._int_x = 0.0
        self._int_y = 0.0
        self._prev_err_x = 0.0
        self._prev_err_y = 0.0

    def update(self, mask: np.ndarray) -> Bounds:
        current = self._compute(mask)
        if self._previous is None:
            self._previous = current
            return current

        err_x = float(current.x - self._previous.x)
        err_y = float(current.y - self._previous.y)
        self._int_x += err_x
        self._int_y += err_y
        self._int_x = max(-2000.0, min(2000.0, self._int_x))
        self._int_y = max(-2000.0, min(2000.0, self._int_y))

        d_x = err_x - self._prev_err_x
        d_y = err_y - self._prev_err_y
        self._prev_err_x = err_x
        self._prev_err_y = err_y

        kp = self._config.panPidKp
        ki = self._config.panPidKi
        kd = self._config.panPidKd
        pid_x = kp * err_x + ki * self._int_x + kd * d_x
        pid_y = kp * err_y + ki * self._int_y + kd * d_y

        target_x = int(round(self._previous.x + pid_x))
        target_y = int(round(self._previous.y + pid_y))

        alpha = self._config.panSmoothing
        w = int(round(self._previous.width * alpha + current.width * (1.0 - alpha)))
        h = int(round(self._previous.height * alpha + current.height * (1.0 - alpha)))
        x = int(round(self._previous.x * alpha + target_x * (1.0 - alpha)))
        y = int(round(self._previous.y * alpha + target_y * (1.0 - alpha)))
        frame_h, frame_w = mask.shape[:2]
        w = max(1, min(w, frame_w))
        h = max(1, min(h, frame_h))
        x = clamp_int(x, 0, max(0, frame_w - w))
        y = clamp_int(y, 0, max(0, frame_h - h))
        smoothed = Bounds(x=x, y=y, width=w, height=h)
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

        upper_cutoff = int(y_min + bbox_height * self._config.upperBodyRatio)
        upper_points = points[points[:, 0] <= upper_cutoff]
        center_source = upper_points if upper_points.size > 0 else points
        center_y = int(round(float(center_source[:, 0].mean())))
        center_x = int(round(float(center_source[:, 1].mean())))

        margin_x = int(round(bbox_width * self._config.margin))
        margin_y = int(round(bbox_height * self._config.margin))
        target_w = min(width, max(1, bbox_width + margin_x * 2))
        target_h = min(height, max(1, bbox_height + margin_y * 2))
        biased_center_y = int(round(center_y - bbox_height * self._config.upperBodyBias))

        x = clamp_int(center_x - target_w // 2, 0, max(0, width - target_w))
        y = clamp_int(biased_center_y - target_h // 2, 0, max(0, height - target_h))

        return Bounds(
            x=x,
            y=y,
            width=target_w,
            height=target_h,
        )

    def as_rect(self, bounds: Bounds) -> Rect:
        return Rect(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height)

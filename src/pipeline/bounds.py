from __future__ import annotations

import cv2
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
    def __init__(self, config: PersonCropConfig, target_width: int, target_height: int) -> None:
        self._config = config
        self._target_aspect = float(target_width) / float(max(1, target_height))
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

        pan_kp = self._config.panPidKp
        pan_ki = self._config.panPidKi
        pan_kd = self._config.panPidKd
        tilt_kp = self._config.tiltPidKp
        tilt_ki = self._config.tiltPidKi
        tilt_kd = self._config.tiltPidKd
        pid_x = pan_kp * err_x + pan_ki * self._int_x + pan_kd * d_x
        pid_y = tilt_kp * err_y + tilt_ki * self._int_y + tilt_kd * d_y

        target_x = int(round(self._previous.x + pid_x))
        target_y = int(round(self._previous.y + pid_y))

        pan_alpha = self._config.panSmoothing
        tilt_alpha = self._config.tiltSmoothing
        zoom_alpha = self._config.zoomSmoothing
        w = int(round(self._previous.width * zoom_alpha + current.width * (1.0 - zoom_alpha)))
        h = int(round(self._previous.height * zoom_alpha + current.height * (1.0 - zoom_alpha)))
        x = int(round(self._previous.x * pan_alpha + target_x * (1.0 - pan_alpha)))
        y = int(round(self._previous.y * tilt_alpha + target_y * (1.0 - tilt_alpha)))
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
        smoothed_mask = self._smooth_edge_mask(mask)
        points = np.argwhere(smoothed_mask > 0)
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
        target_w, target_h = self._fit_aspect(target_w, target_h, width, height)
        biased_center_y = int(round(center_y - bbox_height * self._config.upperBodyBias))
        offset_x = int(round(self._config.panTargetOffsetX * (target_w * 0.5)))
        offset_y = int(round(self._config.panTargetOffsetY * (target_h * 0.5)))
        target_center_x = center_x + offset_x
        target_center_y = biased_center_y + offset_y

        x = clamp_int(target_center_x - target_w // 2, 0, max(0, width - target_w))
        y = clamp_int(target_center_y - target_h // 2, 0, max(0, height - target_h))

        return Bounds(
            x=x,
            y=y,
            width=target_w,
            height=target_h,
        )

    def _fit_aspect(self, w: int, h: int, max_w: int, max_h: int) -> tuple[int, int]:
        current = float(w) / float(max(1, h))
        if abs(current - self._target_aspect) < 1e-6:
            return w, h
        if current < self._target_aspect:
            new_w = min(max_w, int(round(h * self._target_aspect)))
            new_h = int(round(new_w / self._target_aspect))
            new_h = min(max_h, max(1, new_h))
            return max(1, new_w), max(1, new_h)
        new_h = min(max_h, int(round(w / self._target_aspect)))
        new_w = int(round(new_h * self._target_aspect))
        new_w = min(max_w, max(1, new_w))
        return max(1, new_w), max(1, new_h)

    def _smooth_edge_mask(self, mask: np.ndarray) -> np.ndarray:
        smooth = self._config.upperBodyEdgeSmoothing
        if smooth <= 0.001:
            return (mask > 0).astype(np.uint8) * 255
        if mask.dtype != np.uint8:
            work = mask.astype(np.uint8)
        else:
            work = mask
        if work.max() <= 1:
            work = (work * 255).astype(np.uint8)
        k = int(round(3 + smooth * 8))
        if k % 2 == 0:
            k += 1
        k = max(3, k)
        blurred = cv2.GaussianBlur(work, (k, k), sigmaX=max(0.1, smooth * 2.0), sigmaY=max(0.1, smooth * 2.0))
        _, binary = cv2.threshold(blurred, 127, 255, cv2.THRESH_BINARY)
        return binary

    def as_rect(self, bounds: Bounds) -> Rect:
        return Rect(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height)

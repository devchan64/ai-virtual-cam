from __future__ import annotations

import cv2
import os
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
        self._previous_base: Bounds | None = None
        self._int_x = 0.0
        self._int_y = 0.0
        self._prev_err_x = 0.0
        self._prev_err_y = 0.0
        self._debug = os.getenv("FRAMING_DEBUG", "").strip() not in {"", "0", "false", "False"}
        self._debug_frames = 0

    def update(self, mask: np.ndarray) -> Bounds:
        current = self._compute(mask)
        if self._previous_base is None:
            self._previous_base = current
            initial = self._apply_target_offset(current, mask.shape[:2])
            self._previous = initial
            self._debug_log(mask.shape[:2], current, initial)
            return initial

        err_x = float(current.x - self._previous_base.x)
        err_y = float(current.y - self._previous_base.y)
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

        target_x = int(round(self._previous_base.x + pid_x))
        target_y = int(round(self._previous_base.y + pid_y))

        pan_alpha = self._config.panSmoothing
        tilt_alpha = self._config.tiltSmoothing
        zoom_alpha = self._config.zoomSmoothing
        w = int(round(self._previous_base.width * zoom_alpha + current.width * (1.0 - zoom_alpha)))
        h = int(round(self._previous_base.height * zoom_alpha + current.height * (1.0 - zoom_alpha)))
        x = int(round(self._previous_base.x * pan_alpha + target_x * (1.0 - pan_alpha)))
        y = int(round(self._previous_base.y * tilt_alpha + target_y * (1.0 - tilt_alpha)))
        frame_h, frame_w = mask.shape[:2]
        w = max(1, min(w, frame_w))
        h = max(1, min(h, frame_h))
        x = clamp_int(x, 0, max(0, frame_w - w))
        y = clamp_int(y, 0, max(0, frame_h - h))
        base = Bounds(x=x, y=y, width=w, height=h)
        self._previous_base = base
        output = self._apply_target_offset(base, mask.shape[:2])
        self._previous = output
        self._debug_log(mask.shape[:2], base, output)
        return output

    def _compute(self, mask: np.ndarray) -> Bounds:
        height, width = mask.shape[:2]
        smoothed_mask = self._smooth_edge_mask(mask)
        points = np.argwhere(smoothed_mask > 0)
        if points.size == 0:
            return Bounds(0, 0, width, height)

        # Robust bbox: trim tail noise so tilt can react even when mask leaks downward.
        ys = points[:, 0].astype(np.float32)
        xs = points[:, 1].astype(np.float32)
        y_min = int(np.percentile(ys, 2.0))
        y_max = int(np.percentile(ys, 92.0))
        x_min = int(np.percentile(xs, 2.0))
        x_max = int(np.percentile(xs, 98.0))
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
        target_w, target_h = self._ensure_vertical_headroom(target_w, target_h, width, height)
        biased_center_y = int(round(center_y - bbox_height * self._config.upperBodyBias))
        base_x = center_x - target_w // 2
        base_y = biased_center_y - target_h // 2
        free_x = max(0, width - target_w)
        free_y = max(0, height - target_h)
        x = clamp_int(base_x, 0, free_x)
        y = clamp_int(base_y, 0, free_y)

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

    def _ensure_vertical_headroom(self, w: int, h: int, max_w: int, max_h: int) -> tuple[int, int]:
        # If Y offset is requested but crop consumes full frame height, keep a small headroom
        # so vertical framing can move.
        wants_y_offset = abs(self._config.panTargetOffsetY) > 1e-6
        if not wants_y_offset:
            return w, h
        if h < max_h:
            return w, h
        reserve = max(8, int(round(max_h * 0.10)))
        new_h = max(1, max_h - reserve)
        new_w = int(round(new_h * self._target_aspect))
        if new_w > max_w:
            new_w = max_w
            new_h = int(round(new_w / self._target_aspect))
        return max(1, new_w), max(1, new_h)

    def _apply_target_offset(self, bounds: Bounds, shape: tuple[int, int]) -> Bounds:
        frame_h, frame_w = shape
        free_x = max(0, frame_w - bounds.width)
        free_y = max(0, frame_h - bounds.height)
        offset_x = int(round(self._config.panTargetOffsetX * (free_x * 0.5)))
        offset_y = int(round(self._config.panTargetOffsetY * (free_y * 0.5)))
        x = clamp_int(bounds.x + offset_x, 0, free_x)
        y = clamp_int(bounds.y + offset_y, 0, free_y)
        return Bounds(x=x, y=y, width=bounds.width, height=bounds.height)

    def _debug_log(self, shape: tuple[int, int], base: Bounds, output: Bounds) -> None:
        if not self._debug:
            return
        self._debug_frames += 1
        if self._debug_frames % 30 != 0:
            return
        frame_h, frame_w = shape
        free_x = max(0, frame_w - base.width)
        free_y = max(0, frame_h - base.height)
        offset_x = output.x - base.x
        offset_y = output.y - base.y
        print(
            "[frame-debug] "
            f"frame={self._debug_frames} "
            f"frame={frame_w}x{frame_h} "
            f"crop={base.width}x{base.height} "
            f"base=({base.x},{base.y}) "
            f"out=({output.x},{output.y}) "
            f"free=({free_x},{free_y}) "
            f"offset=({offset_x},{offset_y}) "
            f"targetOffset=({self._config.panTargetOffsetX:.2f},{self._config.panTargetOffsetY:.2f})",
            flush=True,
        )

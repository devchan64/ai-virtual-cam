from __future__ import annotations

import cv2
import numpy as np

from src.domain.config import Rect


def crop_and_resize(frame: np.ndarray, rect: Rect, width: int, height: int) -> np.ndarray:
    frame_h, frame_w = frame.shape[:2]
    safe_rect = _expand_rect_to_target_aspect(rect, frame_w, frame_h, width, height)
    cropped = frame[safe_rect.y : safe_rect.y + safe_rect.height, safe_rect.x : safe_rect.x + safe_rect.width]
    if cropped.size == 0:
        raise RuntimeError("Crop produced an empty frame")
    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)


def _expand_rect_to_target_aspect(
    rect: Rect,
    frame_w: int,
    frame_h: int,
    target_w: int,
    target_h: int,
) -> Rect:
    target_aspect = float(target_w) / float(target_h)
    x = max(0, min(rect.x, frame_w - 1))
    y = max(0, min(rect.y, frame_h - 1))
    w = max(1, min(rect.width, frame_w - x))
    h = max(1, min(rect.height, frame_h - y))

    current_aspect = float(w) / float(h)
    if abs(current_aspect - target_aspect) < 1e-6:
        return Rect(x=x, y=y, width=w, height=h)

    if current_aspect < target_aspect:
        desired_w = int(round(h * target_aspect))
        desired_w = min(desired_w, frame_w)
        cx = x + w // 2
        new_x = cx - desired_w // 2
        new_x = max(0, min(new_x, frame_w - desired_w))
        return Rect(x=new_x, y=y, width=desired_w, height=h)

    desired_h = int(round(w / target_aspect))
    desired_h = min(desired_h, frame_h)
    cy = y + h // 2
    new_y = cy - desired_h // 2
    new_y = max(0, min(new_y, frame_h - desired_h))
    return Rect(x=x, y=new_y, width=w, height=desired_h)

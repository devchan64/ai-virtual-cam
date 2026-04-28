from __future__ import annotations

import cv2
import numpy as np

from src.domain.config import Rect


def crop_and_resize(frame: np.ndarray, rect: Rect, width: int, height: int) -> np.ndarray:
    cropped = frame[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
    if cropped.size == 0:
        raise RuntimeError("Crop produced an empty frame")
    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)

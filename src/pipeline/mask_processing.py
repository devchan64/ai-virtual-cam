from __future__ import annotations

import cv2
import numpy as np


def refine_mask(mask: np.ndarray, threshold: float) -> np.ndarray:
    if mask.dtype != np.float32:
        mask = mask.astype(np.float32)

    mask = np.clip(mask, 0.0, 1.0)
    binary = (mask >= threshold).astype(np.uint8) * 255
    binary = cv2.GaussianBlur(binary, (11, 11), 0)
    binary = cv2.medianBlur(binary, 5)
    return binary

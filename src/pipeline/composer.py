from __future__ import annotations

import cv2
import numpy as np


class Composer:
    def compose(self, frame: np.ndarray, mask: np.ndarray, background: np.ndarray) -> np.ndarray:
        if frame.shape[:2] != background.shape[:2]:
            background = cv2.resize(background, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)

        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        foreground = frame.astype(np.float32) * alpha
        backdrop = background.astype(np.float32) * (1.0 - alpha)
        composed = foreground + backdrop
        return np.clip(composed, 0, 255).astype(np.uint8)

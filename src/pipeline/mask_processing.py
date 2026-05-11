from __future__ import annotations

import cv2
import numpy as np


def _odd_kernel_size(raw: float) -> int:
    size = int(round(raw))
    size = max(3, size)
    if size % 2 == 0:
        size += 1
    return size


def refine_mask(
    mask: np.ndarray,
    threshold: float,
    edge_smoothness: float = 0.5,
    blend_feather: float = 0.35,
) -> np.ndarray:
    if mask.dtype != np.float32:
        mask = mask.astype(np.float32)

    mask = np.clip(mask, 0.0, 1.0)
    binary = (mask >= threshold).astype(np.uint8) * 255
    edge_kernel = _odd_kernel_size(3 + edge_smoothness * 10)
    binary = cv2.medianBlur(binary, edge_kernel)
    blur_kernel = _odd_kernel_size(3 + blend_feather * 14)
    sigma = max(0.1, blend_feather * 3.5)
    binary = cv2.GaussianBlur(binary, (blur_kernel, blur_kernel), sigmaX=sigma, sigmaY=sigma)
    return binary

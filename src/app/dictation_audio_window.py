from __future__ import annotations

from collections import deque
from typing import Any


class SlidingAudioWindow:
    def __init__(self, *, window_samples: int, step_samples: int) -> None:
        if window_samples <= 0:
            raise ValueError(f"window_samples must be positive: {window_samples}")
        if step_samples <= 0:
            raise ValueError(f"step_samples must be positive: {step_samples}")
        self._window_samples = window_samples
        self._step_samples = step_samples
        self._blocks: deque[Any] = deque()
        self._buffered_samples = 0
        self._pending_step_samples = 0

    @property
    def buffered_samples(self) -> int:
        return self._buffered_samples

    def append(self, block: Any) -> bool:
        block_len = int(block.shape[0])
        self._blocks.append(block)
        self._buffered_samples += block_len
        self._pending_step_samples += block_len
        self._trim_to_window()
        if self._buffered_samples < self._window_samples or self._pending_step_samples < self._step_samples:
            return False
        self._pending_step_samples = 0
        return True

    def concatenate(self, np: Any) -> Any:
        return np.concatenate(list(self._blocks))

    def _trim_to_window(self) -> None:
        while self._buffered_samples > self._window_samples and self._blocks:
            excess = self._buffered_samples - self._window_samples
            oldest = self._blocks[0]
            oldest_len = int(oldest.shape[0])
            if oldest_len <= excess:
                self._blocks.popleft()
                self._buffered_samples -= oldest_len
                continue
            self._blocks[0] = oldest[excess:]
            self._buffered_samples -= excess
            break

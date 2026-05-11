from __future__ import annotations

import numpy as np


class OutputSink:
    def write(self, frame: np.ndarray) -> None:
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError

from __future__ import annotations

import platform
from typing import Callable

from src.audio.device import LinuxAudioRuntime, MacOSAudioRuntime
from src.domain.config import AudioMixerConfig


class VirtualAudioMixer:
    """Facade that selects per-platform audio device runtime."""

    def __init__(
        self,
        config: AudioMixerConfig,
        on_stream_state: Callable[[bool, str, int], None] | None = None,
    ) -> None:
        self._cfg = config
        self._on_stream_state = on_stream_state
        self._runtime = self._build_runtime()

    def _build_runtime(self):
        os_name = platform.system()
        if os_name == "Linux":
            return LinuxAudioRuntime(self._cfg, on_stream_state=self._on_stream_state)
        return MacOSAudioRuntime(self._cfg, on_stream_state=self._on_stream_state)

    def run(self, max_steps: int = 0) -> None:
        self._runtime.run(max_steps=max_steps)

    def stop(self) -> None:
        self._runtime.stop()

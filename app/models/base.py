"""Abstract TTS model interface.

Every concrete wrapper (Qwen3-TTS, Chatterbox, mock) must implement
this interface so the REST and WebSocket code stays model-agnostic.

Two output modes:
  * `synthesize()`  — blocking, returns full waveform. REST path uses this.
  * `stream()`      — async generator yielding float32 chunks as they're
                       generated. WebSocket path uses this and measures TTFA.

The default `stream()` implementation just calls `synthesize()` and chunks
the result — that's the "works but no streaming benefit" fallback. Concrete
subclasses should override it with native streaming inference once we've
confirmed each model's streaming API.
"""
from __future__ import annotations

import asyncio
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal, Optional

import numpy as np

from app.audio_utils import chunk_waveform


StreamFormat = Literal["pcm", "opus"]


@dataclass
class TTSRequest:
    model: str
    input: str
    voice: str = "default"
    format: StreamFormat = "pcm"
    sample_rate: int = 24000
    speed: float = 1.0


class TTSModel(ABC):
    """Base class for all TTS model wrappers."""

    name: str
    sample_rate: int

    def __init__(self, sample_rate: int = 24000, mock: bool = False) -> None:
        self.sample_rate = sample_rate
        self.mock = mock
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def load(self) -> None:
        """Download (if needed) and move weights into VRAM.

        Called once at server startup. Must be idempotent — calling twice
        is a no-op.
        """

    @abstractmethod
    def synthesize(self, request: TTSRequest) -> np.ndarray:
        """Blocking full-waveform synthesis. Returns mono float32 in [-1, 1]."""

    async def stream(self, request: TTSRequest) -> AsyncIterator[np.ndarray]:
        """Default streaming: run blocking synthesize() in a thread, then
        chunk. Subclasses should override with native streaming for real TTFA.
        """
        loop = asyncio.get_running_loop()
        waveform = await loop.run_in_executor(None, self.synthesize, request)
        for chunk in chunk_waveform(waveform, request.sample_rate, chunk_ms=200):
            yield chunk
            # Yield control so the event loop can send bytes between chunks.
            await asyncio.sleep(0)

    # ---- Mock helper used by the dev path. ----

    def _mock_waveform(self, text: str, sample_rate: int) -> np.ndarray:
        """Generate a sine wave whose duration scales with text length.

        Used when USE_MOCK_MODELS=1 so the server runs without a GPU and
        without multi-GB downloads. Not a realistic audio, but exercises
        every code path from request to encoded response.
        """
        seconds = max(0.5, min(8.0, len(text) / 15.0))
        n = int(sample_rate * seconds)
        t = np.linspace(0, seconds, n, endpoint=False, dtype=np.float32)
        freq = 220.0 + (hash(text) % 200)  # pitch varies per input
        waveform = 0.2 * np.sin(2 * math.pi * freq * t).astype(np.float32)
        # Soft attack/release envelope so playback isn't clicky.
        fade = min(int(0.02 * sample_rate), n // 4)
        if fade > 0:
            env = np.linspace(0, 1, fade, dtype=np.float32)
            waveform[:fade] *= env
            waveform[-fade:] *= env[::-1]
        return waveform

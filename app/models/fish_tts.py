"""Fish Speech S1-mini wrapper.

Status: same shape as qwen_tts.py — lifecycle plumbed, real inference call
is a Phase-1 TODO. Fish Speech ships its own `fish-speech` PyPI package and
has a documented Python API; we wire that in on the GPU VM after confirming
install.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import numpy as np

from app.models.base import TTSModel, TTSRequest

logger = logging.getLogger("tts_api.models.fish")


class FishSpeechModel(TTSModel):
    name = "fish-s1-mini"

    def __init__(
        self,
        model_id: str,
        device: str,
        sample_rate: int = 24000,
        mock: bool = False,
    ) -> None:
        super().__init__(sample_rate=sample_rate, mock=mock)
        self.model_id = model_id
        self.device = device
        self._model = None

    def load(self) -> None:
        if self._loaded:
            return

        if self.mock:
            logger.info("fish_mock_mode_enabled")
            self._loaded = True
            return

        # TODO(phase-1): import and initialize the real fish-speech model.
        # The fish-speech package exposes a loader that downloads weights
        # from HuggingFace and returns a generator object; we'll plug it in
        # once we've verified the install on the GPU VM.
        try:
            logger.info("fish_loading", extra={"model_id": self.model_id, "device": self.device})
            # Placeholder: real import would be something like
            #   from fish_speech import FishSpeechGenerator
            #   self._model = FishSpeechGenerator.from_pretrained(self.model_id).to(self.device)
            self._loaded = True
        except Exception:
            logger.exception("fish_load_failed")
            raise

    def synthesize(self, request: TTSRequest) -> np.ndarray:
        if not self._loaded:
            raise RuntimeError("FishSpeechModel.synthesize() called before load()")

        if self.mock:
            return self._mock_waveform(request.input, request.sample_rate)

        return self._generate_waveform(request)

    async def stream(self, request: TTSRequest) -> AsyncIterator[np.ndarray]:
        """Phase 3 will replace this with Fish Speech's native WebSocket
        streaming API (which emits ~200ms TTFA). For now, fall back to
        synthesize-then-chunk.
        """
        loop = asyncio.get_running_loop()
        waveform = await loop.run_in_executor(None, self.synthesize, request)
        from app.audio_utils import chunk_waveform
        for chunk in chunk_waveform(waveform, request.sample_rate, chunk_ms=150):
            yield chunk
            await asyncio.sleep(0)

    def _generate_waveform(self, request: TTSRequest) -> np.ndarray:
        raise NotImplementedError(
            "FishSpeechModel._generate_waveform is a Phase-1 TODO. "
            "Set USE_MOCK_MODELS=1 for local dev, or implement real inference "
            "once fish-speech is confirmed to load on the GPU VM."
        )

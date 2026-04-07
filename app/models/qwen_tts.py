"""Qwen3-TTS wrapper.

Status (Phase 1 scaffold): this wrapper has the full lifecycle plumbed —
loading, device placement, synthesize, stream — but the actual inference
call (`_generate_waveform`) is a TODO that needs the model's concrete
Python API. The plan's Phase 1 says "get models running" and verify with a
single audio file; that's where we fill in the real call.

Once we confirm on the GPU VM whether Qwen3-TTS ships via transformers
(AutoModel) or a dedicated QwenLM repo, update `_generate_waveform()`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

import numpy as np

from app.models.base import TTSModel, TTSRequest

logger = logging.getLogger("tts_api.models.qwen")


class QwenTTSModel(TTSModel):
    name = "qwen3-tts"

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
        self._tokenizer = None

    def load(self) -> None:
        if self._loaded:
            return

        if self.mock:
            logger.info("qwen_mock_mode_enabled")
            self._loaded = True
            return

        # TODO(phase-1): confirm the real loading API on the GPU VM. Most
        # likely path is transformers AutoModel; if Qwen ships a custom
        # loader we'll swap it in here.
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            logger.info("qwen_loading", extra={"model_id": self.model_id, "device": self.device})
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
            self._model = AutoModel.from_pretrained(
                self.model_id,
                trust_remote_code=True,
                torch_dtype=torch.float16,
            ).to(self.device)
            self._model.eval()
            self._loaded = True
        except Exception:
            logger.exception("qwen_load_failed")
            raise

    def synthesize(self, request: TTSRequest) -> np.ndarray:
        if not self._loaded:
            raise RuntimeError("QwenTTSModel.synthesize() called before load()")

        if self.mock:
            return self._mock_waveform(request.input, request.sample_rate)

        return self._generate_waveform(request)

    async def stream(self, request: TTSRequest) -> AsyncIterator[np.ndarray]:
        """Streaming path.

        Phase 1 uses the base-class fallback (synthesize-then-chunk). Phase 3
        replaces this with Qwen's native token-by-token audio streaming
        (the plan's target: 97ms TTFA).
        """
        loop = asyncio.get_running_loop()
        waveform = await loop.run_in_executor(None, self.synthesize, request)
        # Import lazily to avoid a circular dep at module import time.
        from app.audio_utils import chunk_waveform
        for chunk in chunk_waveform(waveform, request.sample_rate, chunk_ms=120):
            yield chunk
            await asyncio.sleep(0)

    def _generate_waveform(self, request: TTSRequest) -> np.ndarray:
        """TODO(phase-1): fill this in once we've verified the real inference
        call on the GPU VM. Until then, raise loudly so nobody thinks this is
        working in non-mock mode.
        """
        raise NotImplementedError(
            "QwenTTSModel._generate_waveform is a Phase-1 TODO. "
            "Set USE_MOCK_MODELS=1 for local dev, or implement real inference "
            "once Qwen3-TTS is confirmed to load on the GPU VM."
        )

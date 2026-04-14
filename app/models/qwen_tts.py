"""Qwen3-TTS wrapper."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import numpy as np

from app.audio_utils import chunk_waveform, resample_waveform, to_mono_float32
from app.models.base import TTSModel, TTSRequest

logger = logging.getLogger("tts_api.models.qwen")


class QwenTTSModel(TTSModel):
    name = "qwen3-tts"

    def __init__(
        self,
        model_id: str,
        device: str,
        speaker: str = "Aiden",
        language: str = "English",
        instruct: str = "Professional and friendly tone.",
        dtype: str = "bfloat16",
        attn_implementation: str = "flash_attention_2",
        sample_rate: int = 24000,
        mock: bool = False,
    ) -> None:
        super().__init__(sample_rate=sample_rate, mock=mock)
        self.model_id = model_id
        self.device = device
        self.speaker = speaker
        self.language = language
        self.instruct = instruct
        self.dtype = dtype
        self.attn_implementation = attn_implementation
        self._model = None

    def load(self) -> None:
        if self._loaded:
            return

        if self.mock:
            logger.info("qwen_mock_mode_enabled")
            self._loaded = True
            return

        try:
            import torch
            from qwen_tts import Qwen3TTSModel

            dtype_map = {
                "bfloat16": torch.bfloat16,
                "float16": torch.float16,
            }
            torch_dtype = dtype_map[self.dtype]
            logger.info(
                "qwen_loading",
                extra={
                    "model_id": self.model_id,
                    "device": self.device,
                    "dtype": self.dtype,
                    "attn_implementation": self.attn_implementation,
                },
            )
            self._model = Qwen3TTSModel.from_pretrained(
                self.model_id,
                device_map=self.device,
                dtype=torch_dtype,
                attn_implementation=self.attn_implementation,
            )
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
        loop = asyncio.get_running_loop()
        waveform = await loop.run_in_executor(None, self.synthesize, request)
        for chunk in chunk_waveform(waveform, request.sample_rate, chunk_ms=120):
            yield chunk
            await asyncio.sleep(0)

    def _generate_waveform(self, request: TTSRequest) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Qwen model is not loaded")

        if request.speed != 1.0:
            logger.info("qwen_speed_ignored", extra={"speed": request.speed})

        speaker = request.voice if request.voice and request.voice != "default" else self.speaker
        wavs, sample_rate = self._model.generate_custom_voice(
            text=request.input,
            language=self.language,
            speaker=speaker,
            instruct=self.instruct or None,
        )
        waveform = to_mono_float32(wavs)
        if sample_rate != request.sample_rate:
            waveform = resample_waveform(waveform, sample_rate, request.sample_rate)
        return waveform

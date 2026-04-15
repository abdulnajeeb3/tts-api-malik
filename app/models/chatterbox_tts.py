"""Chatterbox wrapper."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import numpy as np

from app.audio_utils import chunk_waveform, resample_waveform, to_mono_float32
from app.models.base import TTSModel, TTSRequest

logger = logging.getLogger("tts_api.models.chatterbox")


class ChatterboxTTSModel(TTSModel):
    name = "chatterbox"

    def __init__(
        self,
        model_id: str,
        device: str,
        mode: str = "english",
        audio_prompt: str = "",
        language_id: str = "en",
        sample_rate: int = 24000,
        mock: bool = False,
    ) -> None:
        super().__init__(sample_rate=sample_rate, mock=mock)
        self.model_id = model_id
        self.device = device
        self.mode = mode
        self.audio_prompt = audio_prompt
        self.language_id = language_id
        self._model = None

    def load(self) -> None:
        if self._loaded:
            return

        if self.mock:
            logger.info("chatterbox_mock_mode_enabled")
            self._loaded = True
            return

        logger.info(
            "chatterbox_loading",
            extra={
                "model_id": self.model_id,
                "device": self.device,
                "mode": self.mode,
                "audio_prompt": bool(self.audio_prompt),
            },
        )

        device = self._normalized_device()
        try:
            self._ensure_perth_watermarker()
            if self.mode == "english":
                from chatterbox.tts import ChatterboxTTS

                self._model = ChatterboxTTS.from_pretrained(device=device)
            elif self.mode == "multilingual":
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)
            elif self.mode == "turbo":
                from chatterbox.tts_turbo import ChatterboxTurboTTS

                self._model = ChatterboxTurboTTS.from_pretrained(device=device)
            else:
                raise ValueError(f"Unsupported chatterbox mode: {self.mode!r}")

            self.sample_rate = int(getattr(self._model, "sr", self.sample_rate))
            self._loaded = True
        except Exception:
            logger.exception("chatterbox_load_failed")
            raise

    def synthesize(self, request: TTSRequest) -> np.ndarray:
        if not self._loaded:
            raise RuntimeError("ChatterboxTTSModel.synthesize() called before load()")

        if self.mock:
            return self._mock_waveform(request.input, request.sample_rate)

        return self._generate_waveform(request)

    async def stream(self, request: TTSRequest) -> AsyncIterator[np.ndarray]:
        loop = asyncio.get_running_loop()
        waveform = await loop.run_in_executor(None, self.synthesize, request)
        for chunk in chunk_waveform(waveform, request.sample_rate, chunk_ms=150):
            yield chunk
            await asyncio.sleep(0)

    def _generate_waveform(self, request: TTSRequest) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Chatterbox model is not loaded")

        if request.voice and request.voice != "default":
            logger.info("chatterbox_voice_ignored", extra={"voice": request.voice})
        if request.speed != 1.0:
            logger.info("chatterbox_speed_ignored", extra={"speed": request.speed})

        audio_prompt = self.audio_prompt or None
        if self.mode == "turbo" and not audio_prompt:
            raise ValueError("Chatterbox turbo mode requires CHATTERBOX_AUDIO_PROMPT")

        kwargs = {"audio_prompt_path": audio_prompt}
        if self.mode == "multilingual":
            kwargs["language_id"] = self.language_id

        wav = self._model.generate(request.input, **kwargs)
        waveform = to_mono_float32(wav)
        if self.sample_rate != request.sample_rate:
            waveform = resample_waveform(waveform, self.sample_rate, request.sample_rate)
        return waveform

    def _normalized_device(self) -> str:
        return "cuda" if self.device.startswith("cuda") else self.device

    def _ensure_perth_watermarker(self) -> None:
        """Repair Perth's package-level export when it is left unset.

        On some runtime stacks, `perth.__init__` swallows an ImportError and
        leaves `PerthImplicitWatermarker = None`, even though the underlying
        implementation can still be imported directly. Chatterbox then crashes
        during startup when it blindly calls that attribute.
        """
        import perth

        if getattr(perth, "PerthImplicitWatermarker", None) is not None:
            return

        try:
            from perth.perth_net.perth_net_implicit.perth_watermarker import (
                PerthImplicitWatermarker,
            )

            perth.PerthImplicitWatermarker = PerthImplicitWatermarker
            logger.warning("chatterbox_perth_repaired_via_direct_import")
            return
        except Exception:
            logger.exception("chatterbox_perth_direct_import_failed")

        from perth.dummy_watermarker import DummyWatermarker

        perth.PerthImplicitWatermarker = DummyWatermarker
        logger.warning("chatterbox_perth_falling_back_to_dummy_watermarker")

"""TTS model wrappers and the startup-time registry builder."""
from __future__ import annotations

import logging
from typing import Dict

from app.config import Settings
from app.models.base import TTSModel
from app.models.chatterbox_tts import ChatterboxTTSModel
from app.models.qwen_tts import QwenTTSModel

logger = logging.getLogger("tts_api.models")


def build_registry(settings: Settings) -> Dict[str, TTSModel]:
    """Instantiate and load every enabled model. Called once at startup.

    Follows the current plan: load every enabled model up-front.
    """
    registry: Dict[str, TTSModel] = {}

    for name in settings.enabled_model_list:
        logger.info("loading_model", extra={"model": name})
        if name == "qwen3-tts":
            model = QwenTTSModel(
                model_id=settings.qwen_model_id,
                device=settings.qwen_device,
                speaker=settings.qwen_speaker,
                language=settings.qwen_language,
                instruct=settings.qwen_instruct,
                dtype=settings.qwen_dtype,
                attn_implementation=settings.qwen_attn_implementation,
                sample_rate=settings.default_sample_rate,
                mock=settings.use_mock_models,
            )
        elif name == "chatterbox":
            model = ChatterboxTTSModel(
                model_id=settings.chatterbox_model_id,
                device=settings.chatterbox_device,
                mode=settings.chatterbox_mode,
                audio_prompt=settings.chatterbox_audio_prompt,
                language_id=settings.chatterbox_language_id,
                sample_rate=settings.default_sample_rate,
                mock=settings.use_mock_models,
            )
        else:
            logger.warning("unknown_model_skipped", extra={"model": name})
            continue

        model.load()
        registry[name] = model
        logger.info("model_loaded", extra={"model": name})

    if not registry:
        raise RuntimeError("No models were loaded. Check ENABLED_MODELS in .env.")

    return registry

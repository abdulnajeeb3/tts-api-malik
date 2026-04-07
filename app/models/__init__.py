"""TTS model wrappers and the startup-time registry builder."""
from __future__ import annotations

import logging
from typing import Dict

from app.config import Settings
from app.models.base import TTSModel
from app.models.fish_tts import FishSpeechModel
from app.models.qwen_tts import QwenTTSModel

logger = logging.getLogger("tts_api.models")


def build_registry(settings: Settings) -> Dict[str, TTSModel]:
    """Instantiate and load every enabled model. Called once at startup.

    Follows the plan: load both into VRAM up-front. Lazy loading is banned.
    """
    registry: Dict[str, TTSModel] = {}

    for name in settings.enabled_models:
        logger.info("loading_model", extra={"model": name})
        if name == "qwen3-tts":
            model = QwenTTSModel(
                model_id=settings.qwen_model_id,
                device=settings.qwen_device,
                sample_rate=settings.default_sample_rate,
                mock=settings.use_mock_models,
            )
        elif name == "fish-s1-mini":
            model = FishSpeechModel(
                model_id=settings.fish_model_id,
                device=settings.fish_device,
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

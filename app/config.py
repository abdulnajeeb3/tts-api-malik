"""Runtime configuration loaded from environment variables.

All settings are parsed once at import time via pydantic-settings. Defaults
match .env.example; override by editing .env or exporting env vars.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal, get_args

from pydantic_settings import BaseSettings, SettingsConfigDict


ModelName = Literal["qwen3-tts", "chatterbox"]
StreamFormat = Literal["pcm", "opus"]
RestFormat = Literal["mp3", "wav", "opus", "flac"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Server ----
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # ---- Auth ----
    # We store the raw string (comma-separated) here instead of List[str] to
    # sidestep pydantic-settings' habit of JSON-decoding env values for list
    # fields. The `api_key_list` property below splits it on demand. Same trick
    # for `enabled_models` below.
    api_keys: str = "dev-local-key-change-me"

    # ---- Models ----
    enabled_models: str = "qwen3-tts"
    hf_home: str = "/models_cache/huggingface"
    transformers_cache: str = "/models_cache/huggingface"

    qwen_model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    qwen_device: str = "cuda:0"
    qwen_speaker: str = "Aiden"
    qwen_language: str = "English"
    qwen_instruct: str = "Professional and friendly tone."
    qwen_dtype: Literal["bfloat16", "float16"] = "bfloat16"
    qwen_attn_implementation: str = "flash_attention_2"

    chatterbox_model_id: str = "ResembleAI/chatterbox"
    chatterbox_device: str = "cuda:0"
    chatterbox_mode: Literal["english", "multilingual", "turbo"] = "english"
    chatterbox_audio_prompt: str = ""
    chatterbox_language_id: str = "en"

    # ---- Audio defaults ----
    default_sample_rate: int = 24000
    default_stream_format: StreamFormat = "pcm"
    default_rest_format: RestFormat = "mp3"

    # ---- Concurrency ----
    inference_workers: int = 8
    max_concurrent_streams: int = 10

    # ---- Dev ----
    # When true, models are replaced with a sine-wave generator so the server
    # boots without a GPU. Used for local dev and CI.
    use_mock_models: bool = False

    @property
    def api_key_list(self) -> List[str]:
        """Parsed view of `api_keys` (comma-separated env var)."""
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def enabled_model_list(self) -> List[ModelName]:
        """Parsed view of `enabled_models`, validated against ModelName."""
        valid = set(get_args(ModelName))
        out: List[ModelName] = []
        for raw in self.enabled_models.split(","):
            name = raw.strip()
            if not name:
                continue
            if name not in valid:
                raise ValueError(
                    f"Unknown model in ENABLED_MODELS: {name!r}. "
                    f"Valid options: {sorted(valid)}"
                )
            out.append(name)  # type: ignore[arg-type]
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""FastAPI entrypoint for the TTS API.

Routes:
  * GET  /health                — model + GPU + active-connections snapshot
  * POST /v1/audio/speech       — OpenAI-compatible REST TTS (Phase 2)
  * WS   /v1/audio/stream       — chunked streaming TTS (Phase 3)

Startup wiring:
  * Parse settings
  * Build the model registry (loads both models into VRAM)
  * Install the shared StreamingHandler

Shutdown:
  * Drop model references so CUDA frees VRAM on container stop.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Literal, Optional

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    status,
)
from pydantic import BaseModel, Field

from app.audio_utils import content_type_for, encode_waveform
from app.config import Settings, get_settings
from app.metrics import registry as metrics_registry
from app.models import build_registry
from app.models.base import TTSModel, TTSRequest
from app.streaming import StreamingHandler

logger = logging.getLogger("tts_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# ---- Lifespan: load models on startup, release on shutdown ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "startup",
        extra={"enabled_models": settings.enabled_models, "mock": settings.use_mock_models},
    )

    # Model loading is blocking + slow; run it off the event loop so the
    # health port is already bound by the time the lifespan context enters.
    loop = asyncio.get_running_loop()
    models: Dict[str, TTSModel] = await loop.run_in_executor(
        None, build_registry, settings
    )

    app.state.settings = settings
    app.state.models = models
    app.state.streaming_handler = StreamingHandler(
        models=models, settings=settings, metrics=metrics_registry
    )
    logger.info("ready", extra={"models": sorted(models)})

    try:
        yield
    finally:
        logger.info("shutdown")
        # Drop references so torch can release VRAM on container stop.
        app.state.models = {}
        app.state.streaming_handler = None


app = FastAPI(
    title="TTS API (Malik)",
    version="0.1.0",
    description="Open-source TTS API serving Qwen3-TTS and Fish Speech S1-mini.",
    lifespan=lifespan,
)


# ---- Auth: simple X-API-Key header check ----

async def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
) -> None:
    settings: Settings = request.app.state.settings
    if not settings.api_keys:
        return  # auth disabled (should never ship to prod like this)
    if x_api_key is None or x_api_key not in settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key",
        )


# ---- GET /health ----

@app.get("/health")
async def health(request: Request) -> Dict[str, Any]:
    """Unauthenticated — Azure LB probes don't send API keys."""
    models: Dict[str, TTSModel] = getattr(request.app.state, "models", {})
    gpu_used, gpu_total = _gpu_memory_snapshot()
    return {
        "status": "ok" if models else "starting",
        "models_loaded": sorted(models.keys()),
        "gpu_memory_used_gb": gpu_used,
        "gpu_memory_total_gb": gpu_total,
        "active_connections": metrics_registry.active_connections,
        "version": app.version,
    }


def _gpu_memory_snapshot() -> tuple[Optional[float], Optional[float]]:
    """Return (used_gb, total_gb) for cuda:0, or (None, None) if no GPU."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None, None
        free, total = torch.cuda.mem_get_info(0)
        used = (total - free) / (1024 ** 3)
        return round(used, 2), round(total / (1024 ** 3), 2)
    except Exception:
        return None, None


# ---- POST /v1/audio/speech (OpenAI-compatible REST) ----

class SpeechRequest(BaseModel):
    """Mirrors OpenAI's TTS request shape so `openai.audio.speech.create()`
    works with only a base_url change."""
    model: Literal["qwen3-tts", "fish-s1-mini"]
    input: str = Field(..., max_length=4096)
    voice: str = "default"
    response_format: Literal["mp3", "wav", "opus", "flac"] = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


@app.post(
    "/v1/audio/speech",
    dependencies=[Depends(require_api_key)],
    responses={
        200: {
            "content": {
                "audio/mpeg": {}, "audio/wav": {},
                "audio/ogg": {}, "audio/flac": {},
            }
        },
    },
)
async def create_speech(req: SpeechRequest, request: Request) -> Response:
    models: Dict[str, TTSModel] = request.app.state.models
    model = models.get(req.model)
    if model is None:
        raise HTTPException(
            status_code=400,
            detail=f"model {req.model!r} not loaded (available: {sorted(models)})",
        )

    settings: Settings = request.app.state.settings
    timings = metrics_registry.new_request(req.model)

    tts_request = TTSRequest(
        model=req.model,
        input=req.input,
        voice=req.voice,
        format="pcm",  # REST encodes below; stream format is irrelevant here.
        sample_rate=settings.default_sample_rate,
        speed=req.speed,
    )

    try:
        loop = asyncio.get_running_loop()
        waveform = await loop.run_in_executor(None, model.synthesize, tts_request)
        timings.mark_first_chunk()  # REST has no true TTFA; mark at inference end.
        audio_bytes = await loop.run_in_executor(
            None,
            encode_waveform,
            waveform,
            settings.default_sample_rate,
            req.response_format,
        )
        timings.bytes_out = len(audio_bytes)
        timings.mark_finished()
    except NotImplementedError as e:
        timings.mark_finished(error=str(e))
        metrics_registry.log_completion(timings)
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.exception("rest_synthesis_failed", extra={"request_id": timings.request_id})
        timings.mark_finished(error=str(e))
        metrics_registry.log_completion(timings)
        raise HTTPException(status_code=500, detail=f"synthesis_failed: {e}")

    metrics_registry.log_completion(timings)
    return Response(
        content=audio_bytes,
        media_type=content_type_for(req.response_format),
        headers={
            "X-Request-ID": timings.request_id,
            "X-TTFA-Ms": str(timings.ttfa_ms or 0),
            "X-Total-Ms": str(timings.total_ms or 0),
        },
    )


# ---- WS /v1/audio/stream ----

@app.websocket("/v1/audio/stream")
async def stream_speech(websocket: WebSocket) -> None:
    # Auth for WebSocket: support either a `?api_key=` query param or an
    # `X-API-Key` header (some clients can't set headers on WS).
    settings: Settings = websocket.app.state.settings
    if settings.api_keys:
        provided = (
            websocket.query_params.get("api_key")
            or websocket.headers.get("x-api-key")
        )
        if provided not in settings.api_keys:
            await websocket.close(code=4401)  # custom: unauthorized
            return

    handler: StreamingHandler = websocket.app.state.streaming_handler
    await handler.handle(websocket)

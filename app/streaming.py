"""WebSocket streaming handler for the TTS API.

Wire protocol (documented in README):

  1. Client opens ws://host:8000/v1/audio/stream (API key in query or header).
  2. Client sends ONE JSON text frame:
        {"model": "qwen3-tts", "input": "hello", "voice": "default",
         "format": "pcm", "sample_rate": 24000}
  3. Server streams binary frames, each containing raw audio bytes in the
     requested format (PCM16 little-endian mono, or Opus packets).
  4. Server sends ONE final JSON text frame:
        {"done": true, "ttfa_ms": 97, "total_ms": 1230, "bytes": 48000}
     OR on failure:
        {"done": true, "error": "message", "request_id": "..."}
  5. Server closes cleanly.

TTFA is measured from the moment we received the request JSON to the moment
we're about to send the first binary frame.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.audio_utils import float_to_pcm16
from app.config import Settings
from app.metrics import MetricsRegistry
from app.models.base import TTSModel, TTSRequest

logger = logging.getLogger("tts_api.streaming")


class StreamingHandler:
    """Binds together a model registry, settings, and metrics for one WS route."""

    def __init__(
        self,
        models: Dict[str, TTSModel],
        settings: Settings,
        metrics: MetricsRegistry,
    ) -> None:
        self.models = models
        self.settings = settings
        self.metrics = metrics
        self._stream_semaphore = asyncio.Semaphore(settings.max_concurrent_streams)

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        with self.metrics.track_connection():
            if self._stream_semaphore.locked():
                logger.warning("stream_semaphore_saturated")
            async with self._stream_semaphore:
                await self._run(websocket)

    async def _run(self, websocket: WebSocket) -> None:
        req_obj = None
        try:
            # First frame from client: a single JSON request.
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            req_obj = self._parse_request(payload)
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        except Exception as e:
            await self._send_error(websocket, f"bad_request: {e}")
            return

        model = self.models.get(req_obj.model)
        if model is None:
            await self._send_error(
                websocket,
                f"unknown_model: {req_obj.model} (available: {sorted(self.models)})",
            )
            return

        timings = self.metrics.new_request(req_obj.model)
        bytes_out = 0
        try:
            first = True
            async for chunk in model.stream(req_obj):
                if first:
                    timings.mark_first_chunk()
                    first = False

                if req_obj.format == "pcm":
                    payload_bytes = float_to_pcm16(chunk)
                else:
                    # Opus path: model.stream() yields already-encoded packets
                    # if format==opus; otherwise fall back to PCM. Real Opus
                    # support is wired in once we confirm each model's output.
                    payload_bytes = float_to_pcm16(chunk)

                if websocket.client_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_bytes(payload_bytes)
                bytes_out += len(payload_bytes)

            timings.bytes_out = bytes_out
            timings.mark_finished()
            await websocket.send_text(
                json.dumps({
                    "done": True,
                    "request_id": timings.request_id,
                    "ttfa_ms": timings.ttfa_ms,
                    "total_ms": timings.total_ms,
                    "bytes": bytes_out,
                })
            )
        except WebSocketDisconnect:
            timings.mark_finished(error="client_disconnected")
        except Exception as e:
            logger.exception("streaming_failed", extra={"request_id": timings.request_id})
            timings.mark_finished(error=str(e))
            await self._send_error(
                websocket,
                f"inference_failed: {e}",
                request_id=timings.request_id,
            )
        finally:
            self.metrics.log_completion(timings)
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()

    def _parse_request(self, payload: Dict[str, Any]) -> TTSRequest:
        return TTSRequest(
            model=payload["model"],
            input=payload["input"],
            voice=payload.get("voice", "default"),
            format=payload.get("format", self.settings.default_stream_format),
            sample_rate=int(payload.get("sample_rate", self.settings.default_sample_rate)),
            speed=float(payload.get("speed", 1.0)),
        )

    async def _send_error(
        self,
        websocket: WebSocket,
        message: str,
        request_id: str | None = None,
    ) -> None:
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await websocket.send_text(
                json.dumps({"done": True, "error": message, "request_id": request_id})
            )
        finally:
            await websocket.close()

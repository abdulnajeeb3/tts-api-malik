# Friend Testing Guide

> Use this when handing a live Qwen or Chatterbox endpoint to an external
> tester.
>
> **Last updated: April 14, 2026**  
> Current live endpoint details: [documentation/CURRENT_ENDPOINT.md](./CURRENT_ENDPOINT.md)

---

## Current Live URL (April 14, 2026)

**Chatterbox** is live on Vast.ai:

```
http://71.104.167.38:52328
```

API key: `dev-local-key-change-me`

Qwen3-TTS is not yet exposed via FastAPI. Pre-generated Qwen audio samples
are available under `benchmark/vast_4090_2026-04-13/qwen_full_output/` if you
want the friend to hear Qwen without waiting for a live service.

---

## Model Services

Run one model per service.

- Qwen service: `http://HOST:8000`
- Chatterbox service: `http://HOST:8001`

Do not try to run both models in one Python runtime. Their dependency stacks
conflict, and the repo is intentionally split to avoid that problem.

---

## What To Start

### Qwen

```bash
docker compose up -d --build tts-api-qwen
```

### Chatterbox

```bash
docker compose up -d --build tts-api-chatterbox
```

To stop one before exposing the other:

```bash
docker compose stop tts-api-qwen
docker compose stop tts-api-chatterbox
```

Health check:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

Only the service you started should show a loaded model.

---

## Auth

REST:

- header: `X-API-Key: <your-key>`

WebSocket:

- either `X-API-Key: <your-key>`
- or `?api_key=<your-key>` in the URL

The key comes from `API_KEYS` in `.env`.

---

## REST API

### Endpoint

`POST /v1/audio/speech`

### Request shape

```json
{
  "model": "qwen3-tts",
  "input": "Your appointment is confirmed for tomorrow at 3 PM.",
  "voice": "Aiden",
  "response_format": "mp3",
  "speed": 1.0
}
```

For Chatterbox, use:

```json
{
  "model": "chatterbox",
  "input": "Your appointment is confirmed for tomorrow at 3 PM.",
  "voice": "default",
  "response_format": "mp3",
  "speed": 1.0
}
```

Notes:

- Qwen uses `voice` as the speaker name. If `voice` is `default`, the server
  uses the configured `QWEN_SPEAKER`.
- Chatterbox currently ignores client-provided `voice` unless you later add
  server-side prompt routing.
- `speed` is accepted by the API contract, but the current model wrappers do
  not implement a real speech-rate transformation.

### Example curl

Qwen: *(not yet live via FastAPI — use pre-generated samples above)*

Chatterbox *(live now)*:

```bash
curl -X POST "http://71.104.167.38:52328/v1/audio/speech" \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "chatterbox",
    "input": "Your appointment with Doctor Smith is confirmed for Tuesday at 2:30 PM.",
    "voice": "default",
    "response_format": "wav",
    "speed": 1.0
  }' \
  --output chatterbox.wav
```

Useful response headers:

- `X-Request-ID`
- `X-TTFA-Ms`
- `X-Total-Ms`

---

## Streaming API

### Endpoint

`WS /v1/audio/stream`

### Request frame

Send one JSON frame after the socket opens:

```json
{
  "model": "qwen3-tts",
  "input": "Please hold for just a moment while I transfer you.",
  "voice": "Aiden",
  "format": "pcm",
  "sample_rate": 24000,
  "speed": 1.0
}
```

### Response flow

1. Server sends binary PCM16 audio frames.
2. Server sends one final JSON message:

```json
{
  "done": true,
  "request_id": "...",
  "ttfa_ms": 1234,
  "total_ms": 1567,
  "bytes": 48000
}
```

Important:

- The streaming route is active now.
- It currently uses synthesize-then-chunk fallback streaming, not native
  token-by-token model streaming.
- That makes it suitable for integration testing, but not yet the final
  low-latency production story.
- Use `format: "pcm"` for now.

### Minimal Python streaming client

```python
import asyncio
import json
import wave

import websockets


async def main():
    uri = "ws://71.104.167.38:52328/v1/audio/stream?api_key=dev-local-key-change-me"
    request = {
        "model": "chatterbox",
        "input": "Please hold for just a moment while I transfer you.",
        "voice": "default",
        "format": "pcm",
        "sample_rate": 24000,
        "speed": 1.0,
    }

    audio = bytearray()
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps(request))
        while True:
            message = await ws.recv()
            if isinstance(message, bytes):
                audio.extend(message)
                continue

            final = json.loads(message)
            print(final)
            break

    with wave.open("stream.wav", "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(audio)


asyncio.run(main())
```

Swap `HOST:8000` for `HOST:8001` and `qwen3-tts` for `chatterbox` when testing
the Chatterbox service.

---

## What To Tell The Friend

Use language like this:

`I’m giving you one model endpoint at a time. Hit /v1/audio/speech for full audio responses and /v1/audio/stream for WebSocket PCM streaming. Use the X-API-Key header I send you. Qwen is on :8000 and Chatterbox is on :8001, but only one may be live at a time depending on which model I’m exposing for the current test.`

---

## Current Caveats

- This is not an ElevenLabs-compatible API surface.
- Each model has its own service because shared-runtime dependency conflicts
  are real and will recur as more models are added.
- Chatterbox was validated end-to-end through the FastAPI serving path on April
  14, 2026 (all three endpoints green on RTX 4090).
- Qwen3-TTS still needs a FastAPI smoke test. The direct-package benchmark
  worked, but the FastAPI wrapper has not yet been hit on GPU.
- Pre-generated benchmark WAVs are in `benchmark/vast_4090_2026-04-13/` and
  can be shared with the friend for an initial quality listen without any live
  service.

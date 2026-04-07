# `app/` — the FastAPI application

This package is the whole server. If you're reading this to learn the codebase, read the files in this order:

1. **[config.py](config.py)** — all environment-driven settings, parsed once via `pydantic-settings`. If you want to know "what can I configure?", start here.
2. **[models/](models/)** — the TTS model wrappers (separate README inside).
3. **[audio_utils.py](audio_utils.py)** — float→PCM16 conversion, chunking, container encoding (mp3/wav/opus/flac). Pure numpy, no torch, so it's cheap to call from hot paths.
4. **[metrics.py](metrics.py)** — process-local metrics registry. Tracks active connections and per-request TTFA/total timing. Deliberately not Prometheus (v1 doesn't need it).
5. **[streaming.py](streaming.py)** — the WebSocket handler class. Parses the client's JSON, invokes `model.stream()`, encodes each chunk, sends bytes, logs timings.
6. **[main.py](main.py)** — FastAPI app, routes, lifespan, auth dependency. This is where all the other modules get wired together.

---

## File-by-file, with "why it exists" notes

### `main.py` — entrypoint
Defines three routes:
- `GET /health` — unauthenticated, returns model list + GPU mem + active connections. Unauthenticated on purpose — Azure Load Balancer health probes can't send headers.
- `POST /v1/audio/speech` — OpenAI-compatible REST. Pydantic-validates the request, runs `model.synthesize()` in the thread pool (so PyTorch doesn't block the event loop), encodes with `audio_utils.encode_waveform`, returns `Response` with the right `Content-Type`.
- `WS /v1/audio/stream` — hands the connection to the shared `StreamingHandler`.

The `lifespan` context manager is where **both models are loaded into VRAM at startup**. The plan bans lazy loading — cold-start latency would blow the sub-200ms TTFA target. `build_registry()` runs in a thread pool executor so the HTTP port binds before the slow model-download path runs.

### `config.py` — settings
Everything reads from env vars (see `.env.example` in the repo root). `get_settings()` is `lru_cache`d so there's one canonical `Settings` instance per process. Comma-separated env values (`API_KEYS`, `ENABLED_MODELS`) are split in a field validator — that's what lets `API_KEYS=a,b,c` in `.env` become a real Python list.

### `metrics.py` — TTFA + connection tracking
Two pieces:
- **`RequestTimings` dataclass** — per-request object that you `mark_first_chunk()` on when the first audio byte is about to go out, then `mark_finished()` at the end. Computes `ttfa_ms` and `total_ms` properties.
- **`MetricsRegistry` singleton** — `registry = MetricsRegistry()` at the bottom of the file. Thread-safe counter of active connections (used by `/health`) and bounded LRU of recent request timings (for debugging).

TTFA is the single most important number in this project — log it on every request so you can spot regressions in CI.

### `audio_utils.py` — encoding helpers
Four functions you'll use:
- `float_to_pcm16(waveform)` — float32 `[-1, 1]` → little-endian int16 bytes. Used for every WebSocket chunk.
- `pcm16_to_float(pcm_bytes)` — inverse, mostly for tests.
- `chunk_waveform(wave, sr, chunk_ms)` — slices a full waveform into fixed-duration pieces. Used when a model returns the full waveform and we still want to stream it to the client (Phase 3 fallback).
- `encode_waveform(wave, sr, fmt)` — full-waveform → mp3/wav/opus/flac bytes. Tries `soundfile` first, falls back to `pydub` + ffmpeg if the local libsndfile can't handle the format.

### `streaming.py` — WebSocket handler
The protocol is documented in the file's module docstring. The interesting design choices:

- **One handler, shared semaphore.** `StreamingHandler.__init__` creates an `asyncio.Semaphore(max_concurrent_streams)`. Every request acquires the semaphore so we enforce the concurrency cap globally without spinning up a dedicated queue.
- **TTFA is measured inside `_run`.** The first `async for chunk in model.stream(...)` iteration triggers `timings.mark_first_chunk()`. This is the number we're optimizing.
- **Cleanup on every exit.** Finally block calls `metrics_registry.log_completion()` and closes the socket. The plan explicitly says: "never leave the client hanging."

---

## How a single WebSocket request flows through the code

```
client ──connect──▶ main.stream_speech()                           [main.py]
                       │  auth check via query param / header
                       ▼
                   StreamingHandler.handle()                        [streaming.py]
                       │  increment active_connections
                       │  acquire concurrency semaphore
                       ▼
                   StreamingHandler._run()
                       │  parse JSON request
                       │  metrics_registry.new_request()
                       ▼
                   TTSModel.stream(request)                         [models/base.py]
                       │  (override in qwen_tts.py / fish_tts.py)
                       │  yields float32 chunks
                       ▼
                   audio_utils.float_to_pcm16(chunk)                [audio_utils.py]
                       │
                       ▼
                   websocket.send_bytes(pcm)
                       │  (first send → mark_first_chunk)
                       ▼
                   ...loop until generator exhausts...
                       │
                       ▼
                   websocket.send_text({done, ttfa_ms, total_ms})
                       │
                       ▼
                   websocket.close()
                       │
                       ▼
                   metrics_registry.log_completion()
```

# `app/` — the FastAPI application

Current status:

- The package boots and serves the API correctly in **mock mode**.
- The route contract today is **internal/OpenAI-style**, not
  ElevenLabs-compatible.
- The real inference layer is now wired for both Qwen and Chatterbox.
- The code now points at **Qwen + Chatterbox** as the target pair.
- Only **Qwen** is enabled by default in shared config.
- The intended deployment model is one service per model runtime.

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
- `GET /health` — unauthenticated, returns model list + GPU mem + active connections. Unauthenticated on purpose so load balancer or uptime probes can hit it without credentials.
- `POST /v1/audio/speech` — OpenAI-compatible REST. Pydantic-validates the request, runs `model.synthesize()` in the thread pool (so PyTorch doesn't block the event loop), encodes with `audio_utils.encode_waveform`, returns `Response` with the right `Content-Type`.
- `WS /v1/audio/stream` — hands the connection to the shared `StreamingHandler`.

The `lifespan` context manager is where **all enabled models are loaded at startup**. The original plan banned lazy loading because cold-start latency would blow the TTFA target. In practice, the latest benchmark work suggests we may need **split runtimes per model** rather than one monolith, because Qwen and Chatterbox do not currently coexist cleanly in one shared Python environment.

### `config.py` — settings
Everything reads from env vars (see `.env.example` in the repo root). `get_settings()` is `lru_cache`d so there's one canonical `Settings` instance per process. Comma-separated env values such as `API_KEYS` and `ENABLED_MODELS` are stored as raw strings and exposed through helper properties like `api_key_list` and `enabled_model_list`.

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

Important limitation:

- The WebSocket route is the repo's own protocol.
- It is **not** an ElevenLabs-compatible HTTP streaming endpoint.
- If the goal is true plug-and-play replacement for a client already using
  ElevenLabs, a compatibility shim still needs to be added above this layer.
- The current stream path is synthesize-then-chunk, not native model
  token-by-token streaming.

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
                       │  (currently qwen_tts.py / chatterbox_tts.py)
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

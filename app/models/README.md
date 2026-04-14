# `app/models/` — TTS model wrappers

Every concrete TTS model implements the same abstract interface so the rest of
the server stays model-agnostic.

Current status:

- The code here is still **transition-state code**.
- The repo currently contains wrappers for **Qwen3-TTS** and
  **Chatterbox**.
- Fish has been removed from the scaffold.
- The chosen serving architecture is now **separate per-model runtimes**.
- Real non-mock inference is now wired to the official package APIs.
- Native streaming is still unfinished; current streaming chunks completed
  waveforms.

---

## Files

### `base.py` — abstract interface
Defines:
- **`TTSRequest`** — dataclass carrying the parsed request (model, input text, voice, format, sample rate, speed).
- **`TTSModel`** — abstract base class. Every concrete wrapper must implement `load()` and `synthesize()`. A default `stream()` is provided that calls `synthesize()` and chunks the result — it's a fallback that gives correct behavior but no streaming latency benefit. Real wrappers should override `stream()` with native streaming inference once we've confirmed each model's API.
- **`_mock_waveform()`** — helper that generates a sine-wave scaled to text length. Used when `USE_MOCK_MODELS=1` so the server boots without a GPU.

### `qwen_tts.py` — Qwen3-TTS wrapper
Research target latency: **97ms TTFA** (best open source).

Status:
- `load()` — uses `qwen_tts.Qwen3TTSModel.from_pretrained(...)`
- `synthesize()` — calls `generate_custom_voice(...)`
- `stream()` — current fallback is synthesize-then-chunk
- request `voice` maps to the Qwen speaker name; `default` falls back to the
  configured speaker

Important benchmark note:

- We successfully ran Qwen through the **direct package benchmark** on Vast.ai.
- The model generated audio successfully there, but it did **not** reproduce
  the expected fast-latency story yet.
- So this wrapper now needs performance validation, not basic implementation.

### `chatterbox_tts.py` — Chatterbox wrapper

Status:

- Same serving shape as the Qwen wrapper.
- `load()` picks the configured Chatterbox runtime mode.
- `synthesize()` calls the package `generate(...)` method.
- `stream()` currently uses the synthesize-then-chunk fallback.
- This wrapper exists because the current repo direction is
  **Qwen3-TTS + Chatterbox**.
- The first successful direct-package benchmark already ran Chatterbox on the
  Vast RTX 4090.

### `__init__.py` — the registry builder
`build_registry(settings)` is the only thing in here. Called once at server startup from `app/main.py`'s lifespan context. It walks `settings.enabled_models`, instantiates each wrapper with the right model ID / device, calls `.load()`, and returns a `dict[model_name → TTSModel]`. The dict is stashed on `app.state.models` so routes can look up by name.

Current limitation:

- The registry knows about Qwen and Chatterbox now.
- Only Qwen is enabled by default in shared config, but compose runs one model
  per service so either can be exposed cleanly.

---

## Why both models share one interface

The REST and WebSocket routes in `main.py` and `streaming.py` just call `model.synthesize()` or `async for chunk in model.stream(...)`. They don't know or care which model they're talking to. That means:

- **Phase 1** (get each model running) can be done independently per file.
- **Phase 3** (real streaming) can be shipped one model at a time — whichever streams natively first becomes the fast path; the other keeps using the synth-then-chunk fallback until its native streaming is wired up.
- Benchmarking is trivial — the benchmark script just iterates over model names.

New caveat from the Vast benchmark:

- Interface-level abstraction is fine, but runtime-level abstraction is harder.
- `qwen-tts` and `chatterbox-tts` currently want incompatible dependency
  stacks.
- So "same interface" does **not** automatically mean "same process".
- The repo now treats this as a design constraint, not a temporary annoyance:
  run one model per service.

---

## Adding a new model later (hypothetical)

1. Create `app/models/your_model.py` with a class subclassing `TTSModel`.
2. Implement `load()` (idempotent, downloads/loads weights, sets `self._loaded = True`) and `synthesize()` (returns mono float32 waveform in `[-1, 1]`).
3. Optionally override `stream()` if the model supports token-by-token audio generation.
4. Add a branch to `build_registry()` in `__init__.py` and an entry in `config.py`'s `ModelName` literal.
5. Add the new name to `ENABLED_MODELS` in `.env`.

If the new model has dependency conflicts similar to Chatterbox, make it a
separate runtime/service instead of forcing it into an existing image.

---

## Mock mode

When `USE_MOCK_MODELS=1` in `.env`:
- Both wrappers skip the real `load()` path.
- `synthesize()` returns a sine wave whose duration and pitch vary with the input text.
- The server boots on any machine, no GPU, no multi-GB downloads.

Use mock mode on your MacBook to test the full request → encode → response path. Use the real VM for everything else.

For the latest real benchmark findings, see:

- [documentation/VAST_BENCHMARK_STATUS.md](../../documentation/VAST_BENCHMARK_STATUS.md)
- [documentation/PROJECT_STATUS.md](../../documentation/PROJECT_STATUS.md)

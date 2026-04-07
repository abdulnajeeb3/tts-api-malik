# `app/models/` — TTS model wrappers

Every concrete TTS model (Qwen3-TTS, Fish Speech S1-mini, the dev-mode mock) implements the same abstract interface so the rest of the server stays model-agnostic. This directory is the "plug-in" layer — adding a third model later is a matter of dropping in a new file that subclasses `TTSModel`.

---

## Files

### `base.py` — abstract interface
Defines:
- **`TTSRequest`** — dataclass carrying the parsed request (model, input text, voice, format, sample rate, speed).
- **`TTSModel`** — abstract base class. Every concrete wrapper must implement `load()` and `synthesize()`. A default `stream()` is provided that calls `synthesize()` and chunks the result — it's a fallback that gives correct behavior but no streaming latency benefit. Real wrappers should override `stream()` with native streaming inference once we've confirmed each model's API.
- **`_mock_waveform()`** — helper that generates a sine-wave scaled to text length. Used when `USE_MOCK_MODELS=1` so the server boots without a GPU.

### `qwen_tts.py` — Qwen3-TTS wrapper
Target latency from the plan: **97ms TTFA** (best open source).

Status:
- `load()` — wires up `transformers.AutoModel` loading on the configured device. Real API may need adjustment once verified on the GPU VM (some models ship with a custom loader instead of the stock transformers path).
- `synthesize()` and `stream()` — plumbed end-to-end, but `_generate_waveform()` currently raises `NotImplementedError`. Filling that in is **Phase 1** work that has to happen on the GPU VM.

### `fish_tts.py` — Fish Speech S1-mini wrapper
Target latency from the plan: **~200ms TTFA**. Smaller (500M params, ~4GB VRAM) with a mature community and a proper Python package (`fish-speech`).

Same shape as the Qwen wrapper — lifecycle plumbed, `_generate_waveform()` is a Phase 1 TODO.

### `__init__.py` — the registry builder
`build_registry(settings)` is the only thing in here. Called once at server startup from `app/main.py`'s lifespan context. It walks `settings.enabled_models`, instantiates each wrapper with the right model ID / device, calls `.load()`, and returns a `dict[model_name → TTSModel]`. The dict is stashed on `app.state.models` so routes can look up by name.

---

## Why both models share one interface

The REST and WebSocket routes in `main.py` and `streaming.py` just call `model.synthesize()` or `async for chunk in model.stream(...)`. They don't know or care which model they're talking to. That means:

- **Phase 1** (get each model running) can be done independently per file.
- **Phase 3** (real streaming) can be shipped one model at a time — whichever streams natively first becomes the fast path; the other keeps using the synth-then-chunk fallback until its native streaming is wired up.
- Benchmarking is trivial — the benchmark script just iterates over model names.

---

## Adding a new model later (hypothetical)

1. Create `app/models/your_model.py` with a class subclassing `TTSModel`.
2. Implement `load()` (idempotent, downloads/loads weights, sets `self._loaded = True`) and `synthesize()` (returns mono float32 waveform in `[-1, 1]`).
3. Optionally override `stream()` if the model supports token-by-token audio generation.
4. Add a branch to `build_registry()` in `__init__.py` and an entry in `config.py`'s `ModelName` literal.
5. Add the new name to `ENABLED_MODELS` in `.env`.

---

## Mock mode

When `USE_MOCK_MODELS=1` in `.env`:
- Both wrappers skip the real `load()` path.
- `synthesize()` returns a sine wave whose duration and pitch vary with the input text.
- The server boots on any machine, no GPU, no multi-GB downloads.

Use mock mode on your MacBook to test the full request → encode → response path. Use the real VM for everything else.

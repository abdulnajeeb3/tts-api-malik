# TTS API (Malik)

Self-hosted TTS API scaffold for replacing ElevenLabs with open-source models.
The current code direction is **Qwen3-TTS + Chatterbox**, and the runtime
architecture is now **one model per service**. Fish has been removed from the
scaffold. The app still does **not** expose a plug-and-play
ElevenLabs-compatible endpoint, but it now has real model wrapper
implementations for separate Qwen and Chatterbox services.

Start with:

- [documentation/PROJECT_STATUS.md](documentation/PROJECT_STATUS.md)
- [documentation/VAST_BENCHMARK_STATUS.md](documentation/VAST_BENCHMARK_STATUS.md)
- [documentation/TTS_MODELS_RESEARCH_V2.md](documentation/TTS_MODELS_RESEARCH_V2.md)
- [documentation/FRIEND_TESTING_GUIDE.md](documentation/FRIEND_TESTING_GUIDE.md)

---

## Current State

- The FastAPI scaffold works in **mock mode** on a laptop.
- The current API surface is:
  - `GET /health`
  - `POST /v1/audio/speech`
  - `WS /v1/audio/stream`
- That surface is **OpenAI-style/internal**, not ElevenLabs-compatible yet.
- The repo now assumes **separate per-model runtimes**, not one mixed Python
  environment.
- Real model inference is now wired through the official model packages for
  both Qwen and Chatterbox.
- The codebase now names **Qwen3-TTS + Chatterbox** as the target pair.
- Only **Qwen3-TTS** is enabled by default today.
- Chatterbox now has the same app-level serving contract as Qwen, but each
  model must run in its own service.
- WebSocket streaming is active through the existing synth-then-chunk fallback.
- Native low-TTFA streaming is still future work.
- A first real GPU benchmark was completed on Vast.ai and the outputs were
  pulled into the repo.

If your goal is "give my friend an endpoint they can swap in for ElevenLabs",
the remaining work is:

1. Boot the per-model service you want to test.
2. Expose whichever per-model service is under test.
3. Add an ElevenLabs-compatible shim layer if the friend wants drop-in swap
   behavior later.

---

## Repo Layout

```text
TTS-API-Malik/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements.runtime.txt
├── requirements.qwen.txt
├── requirements.chatterbox.txt
├── .env.example
├── app/
│   ├── README.md
│   ├── main.py
│   ├── config.py
│   ├── metrics.py
│   ├── audio_utils.py
│   ├── streaming.py
│   └── models/
│       ├── README.md
│       ├── base.py
│       ├── qwen_tts.py
│       └── chatterbox_tts.py
├── benchmark/
│   ├── README.md
│   ├── run_benchmark.py
│   ├── direct_model_bakeoff.py
│   ├── test_phrases.txt
│   └── vast_4090_2026-04-13/
└── documentation/
    ├── PROJECT_STATUS.md
    ├── VAST_BENCHMARK_STATUS.md
    ├── TTS_MODELS_RESEARCH_V2.md
    └── AZURE_SETUP.md
```

---

## API Surface Today

### Current implemented routes

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Model + GPU + connection snapshot |
| `POST` | `/v1/audio/speech` | OpenAI-style REST TTS shape |
| `WS` | `/v1/audio/stream` | Binary audio chunks over WebSocket |

Auth today:

- `X-API-Key` header for REST
- `X-API-Key` header or `?api_key=` query param for WebSocket

Important:

- This is **not** the same contract as ElevenLabs.
- A client currently using ElevenLabs endpoints will need a compatibility shim
  before it becomes plug-and-play.

---

## What Works Right Now

### Local mock mode

You can boot the full server without a GPU:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set USE_MOCK_MODELS=1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

This is useful for:

- request/response validation
- auth checks
- encoding paths
- WebSocket protocol testing

It is **not** useful for judging real voice quality or latency.

### Separate model services

The repo now uses separate dependency stacks per model.

Compose services:

- `tts-api-qwen` on host port `8000`
- `tts-api-chatterbox` on host port `8001`

Typical usage:

```bash
# Qwen service
docker compose up -d tts-api-qwen

# Chatterbox service
docker compose up -d tts-api-chatterbox

# Stop one before focusing on the other if you only want one active test target
docker compose stop tts-api-qwen
docker compose stop tts-api-chatterbox
```

This is deliberate:

- Qwen and Chatterbox do not currently coexist cleanly in one shared Python env
- the same issue would recur as more models are added
- separate model services scale better for benchmarking and testing
- the API contract stays stable even if the runtime stack changes per model

### Real serving path

Both model wrappers now call the same package-level APIs that already worked in
the direct benchmark:

- Qwen uses `qwen_tts.Qwen3TTSModel.from_pretrained(...).generate_custom_voice(...)`
- Chatterbox uses `ChatterboxTTS.from_pretrained(...).generate(...)`

The app-level contract is therefore:

- REST works through `POST /v1/audio/speech`
- streaming works through `WS /v1/audio/stream`
- each service should load exactly one model

Important caveat:

- this coding pass implemented the real wrappers, but the full FastAPI path
  still needs a fresh GPU smoke test on the target runtime
- the direct-package benchmark is still the last fully validated real run

### Real benchmark artifacts

The first real GPU comparison lives in:

- [benchmark/vast_4090_2026-04-13](benchmark/vast_4090_2026-04-13)

See:

- [benchmark/README.md](benchmark/README.md)
- [documentation/VAST_BENCHMARK_STATUS.md](documentation/VAST_BENCHMARK_STATUS.md)

---

## What Does Not Work Yet

### ElevenLabs compatibility

The repo does **not** yet expose:

- ElevenLabs-style REST paths
- ElevenLabs-style auth (`xi-api-key`)
- ElevenLabs voice ID mapping
- ElevenLabs-style HTTP streaming endpoints

### Native streaming

WebSocket streaming is active now, but it is currently the fallback path:

- synthesize the full waveform
- chunk it into PCM frames
- send those frames over the socket

That means the streaming API is usable for integration testing, but it will
not yet reproduce the low-TTFA story promised by native model streaming.

### Model tuning / validation

Fish has been removed from the scaffold.

The current target model names are:

- `qwen3-tts`
- `chatterbox`

But only `qwen3-tts` is enabled by default in shared local config. Docker
compose overrides `ENABLED_MODELS` per service.

Also:

- Chatterbox voice selection is still server-config driven, not client-driven
- Qwen voice selection maps to the request's `voice` field or the configured
  default speaker
- both real wrappers should be re-smoke-tested on GPU before treating them as
  production-ready

---

## Recommended Reading Order

1. [documentation/PROJECT_STATUS.md](documentation/PROJECT_STATUS.md)
2. [documentation/VAST_BENCHMARK_STATUS.md](documentation/VAST_BENCHMARK_STATUS.md)
3. [documentation/TTS_MODELS_RESEARCH_V2.md](documentation/TTS_MODELS_RESEARCH_V2.md)
4. [app/README.md](app/README.md)
5. [app/models/README.md](app/models/README.md)

---

## Where To Look Next

- Want current repo status:
  [documentation/PROJECT_STATUS.md](documentation/PROJECT_STATUS.md)
- Want benchmark details and remote setup findings:
  [documentation/VAST_BENCHMARK_STATUS.md](documentation/VAST_BENCHMARK_STATUS.md)
- Want code paths that still need implementation:
  [app/config.py](app/config.py),
  [app/models/__init__.py](app/models/__init__.py),
  [app/models/qwen_tts.py](app/models/qwen_tts.py),
  [app/models/chatterbox_tts.py](app/models/chatterbox_tts.py)

---

## Historical Note

Some older docs still reference **Azure** as the main path. The current working
direction is:

- benchmark on Vast.ai first
- use Chatterbox instead of Fish for the second model direction
- treat Azure as an optional later deployment target, not the current source of
  truth

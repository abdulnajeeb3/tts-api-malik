# TTS API (Malik)

Production TTS API serving two open-source models — **Qwen3-TTS** and **Fish Speech S1-mini** — behind a WebSocket streaming endpoint and an OpenAI-compatible REST endpoint. Target: sub-200ms TTFA, 5–10 concurrent streams, Dockerized, deployed on an Azure GPU VM in `eastus` (same region as the friend's voice-agent infra).

> This is a learning-oriented repo. Every subdirectory has its own `README.md` explaining what lives there and why. Start here, then drill down.

---

## Repo layout

```
TTS-API-Malik/
├── README.md                  ← you are here
├── Dockerfile                 ← CUDA 12.1 runtime image
├── docker-compose.yml         ← one-command local / VM run
├── requirements.txt           ← Python deps (torch comes from CUDA index in the Dockerfile)
├── .env.example               ← copy to .env and fill in
├── app/                       ← the FastAPI application
│   ├── README.md              ← tour of the app package
│   ├── main.py                ← FastAPI entrypoint + routes + lifespan
│   ├── config.py              ← pydantic-settings loader
│   ├── metrics.py              ← TTFA / active-connection tracking
│   ├── audio_utils.py         ← PCM conversion + container encoding
│   ├── streaming.py           ← WebSocket handler
│   └── models/                ← TTS model wrappers
│       ├── README.md
│       ├── base.py            ← abstract TTSModel + TTSRequest
│       ├── qwen_tts.py        ← Qwen3-TTS wrapper
│       └── fish_tts.py        ← Fish Speech S1-mini wrapper
├── benchmark/                 ← A/B latency + quality benchmark
│   ├── README.md
│   ├── test_phrases.txt       ← 10 medical booking phrases
│   └── run_benchmark.py       ← runs every phrase on every model
└── documentation/
    ├── AZURE_SETUP.md         ← VM provisioning + SSH handoff guide
    └── TTS_MODELS_RESEARCH.md ← field survey of open-source TTS candidates
```

---

## Endpoints

| Method | Path                  | Purpose                                                  |
| ------ | --------------------- | -------------------------------------------------------- |
| GET    | `/health`             | Model status, GPU memory, active connections. Unauthed.  |
| POST   | `/v1/audio/speech`    | OpenAI-compatible REST TTS (mp3/wav/opus/flac response). |
| WS     | `/v1/audio/stream`    | Chunked streaming TTS (PCM16 24kHz mono by default).     |

All non-health routes require an `X-API-Key` header (or `?api_key=` query param on the WebSocket). Keys come from the `API_KEYS` env var (comma-separated).

### REST — drop-in OpenAI compat

```bash
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"fish-s1-mini","input":"Your appointment is confirmed","voice":"default","response_format":"mp3"}' \
  --output test.mp3
```

Equivalent Python using the OpenAI SDK:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="dev-local-key-change-me")
audio = client.audio.speech.create(model="qwen3-tts", voice="default", input="Hello")
audio.stream_to_file("test.mp3")
```

### WebSocket — streaming

Client sends one JSON frame, then receives binary audio frames, then one final JSON frame with TTFA/total metrics. Full protocol documented in [app/streaming.py](app/streaming.py).

---

## Running it

### On a laptop (mock mode — no GPU)

Your MacBook can't host the models, but you can still boot the server end-to-end to test the API shape. `USE_MOCK_MODELS=1` swaps both wrappers for a sine-wave generator so nothing is downloaded and no CUDA is needed.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set USE_MOCK_MODELS=1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then hit `http://localhost:8000/health` and try the `curl` above.

### On the Azure GPU VM (real models)

See [documentation/AZURE_SETUP.md](documentation/AZURE_SETUP.md) for provisioning, SSH setup, and handoff. The short version once the VM is up and this repo is cloned on it:

```bash
cp .env.example .env          # edit API_KEYS, leave USE_MOCK_MODELS=0
docker compose up -d --build
curl http://localhost:8000/health
```

---

## Build phases (in order — do not skip)

The plan PDF defines a strict build order. Each phase exists to de-risk the next:

1. **Phase 1 — Models run.** Verify both models install and generate a single audio file. Current status: wrappers scaffolded, real inference call is marked `TODO(phase-1)` and will be filled in on the GPU VM.
2. **Phase 2 — REST endpoint.** `POST /v1/audio/speech` — already wired, uses `model.synthesize()`.
3. **Phase 3 — WebSocket streaming.** Native chunked generation per model. Currently falls back to synth-then-chunk.
4. **Phase 4 — Concurrency.** Load test 5 simultaneous streams, tune thread pool, watch GPU memory.
5. **Phase 5 — Docker + deploy.** Already containerized; deploy to Azure GPU VM in `eastus`.
6. **Phase 6 — Hand off to friend** for real-traffic testing.

---

## Cost model (from the plan)

| Item                  | Cost          | Notes                             |
| --------------------- | ------------- | --------------------------------- |
| Azure A10 VM          | $550/mo       | `NC8as_A10_v4`, always-on         |
| Storage               | $20/mo        | 128GB managed disk                |
| Bandwidth             | $30–50/mo     | Audio egress                      |
| **Infra total**       | **~$620/mo**  |                                   |
| Charge to friend      | $2,000/mo     | Friend saves ~$1,500 vs ElevenLabs |
| Margin                | ~$1,380/mo    | ~$16,560/year                      |

---

## Where to look when something breaks

- **Server won't start:** check `app.state.models` got populated — look at the `startup` log line for enabled_models + mock flag.
- **`501 Not Implemented` from REST:** the real model inference call isn't filled in yet (Phase 1 TODO). Either run with `USE_MOCK_MODELS=1` or implement `_generate_waveform()` on the GPU VM.
- **`401` on streaming:** API key missing — pass `?api_key=…` on the WS URL.
- **High TTFA:** the default `stream()` in [app/models/base.py](app/models/base.py) falls back to synth-then-chunk, which doesn't stream-as-you-go. Real TTFA wins come from native streaming in Phase 3.

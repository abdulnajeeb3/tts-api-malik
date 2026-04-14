# Agent Handoff

> Current checkpoint for resuming work in a later session or handing the repo
> to another agent.

**Last updated:** April 14, 2026  
**Branch:** `main`  
**Latest pushed commit:** `204f238`  
**Repo state at handoff:** clean working tree after push

---

## What Is Implemented

- Fish has been removed from the active serving path.
- The repo now targets:
  - `qwen3-tts`
  - `chatterbox`
- Runtime architecture is one model per service, not one mixed environment.
- Real wrappers are implemented in:
  - [app/models/qwen_tts.py](../app/models/qwen_tts.py)
  - [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)
- Docker/runtime split is implemented through:
  - [Dockerfile](../Dockerfile)
  - [docker-compose.yml](../docker-compose.yml)
  - [requirements.qwen.txt](../requirements.qwen.txt)
  - [requirements.chatterbox.txt](../requirements.chatterbox.txt)
  - [requirements.runtime.txt](../requirements.runtime.txt)
- The API surface currently exposed by the app is:
  - `GET /health`
  - `POST /v1/audio/speech`
  - `WS /v1/audio/stream`
- Streaming is active through synthesize-then-chunk fallback over WebSocket.
- Friend-facing usage instructions exist in:
  - [documentation/FRIEND_TESTING_GUIDE.md](./FRIEND_TESTING_GUIDE.md)

---

## What Was Validated

### Fully validated

- Local compile/config checks passed:
  - `python3 -m compileall app benchmark`
  - `docker compose config --services`
- Direct-package GPU benchmark on Vast succeeded for both models.
- Benchmark artifacts are committed under:
  - [benchmark/vast_4090_2026-04-13](../benchmark/vast_4090_2026-04-13)

### Not yet fully validated

- The updated FastAPI serving path has **not** had a full end-to-end GPU smoke
  test yet.
- The last fully validated real-model run is still the direct benchmark, not
  the FastAPI app.

---

## Current Risks / Caveats

1. Qwen and Chatterbox do not cleanly share one dependency stack.
2. The current WebSocket streaming path is correct for integration, but not
   native low-TTFA streaming.
3. The API is not ElevenLabs-compatible yet.
4. Qwen still underperformed its researched latency story in the direct Vast
   bakeoff.
5. Chatterbox worked on Vast, but its runtime needed CUDA library path fixes in
   the isolated virtualenv setup there.

---

## Immediate Next Step

Do a real GPU smoke test through the FastAPI app, one service at a time.

Suggested order:

1. Build and boot `tts-api-qwen`
2. Hit `/health`
3. Test `POST /v1/audio/speech`
4. Test `WS /v1/audio/stream`
5. Repeat for `tts-api-chatterbox`
6. Hand the active base URL to the friend for listening feedback

---

## Exact Files To Read First

1. [documentation/PROJECT_STATUS.md](./PROJECT_STATUS.md)
2. [documentation/VAST_BENCHMARK_STATUS.md](./VAST_BENCHMARK_STATUS.md)
3. [documentation/FRIEND_TESTING_GUIDE.md](./FRIEND_TESTING_GUIDE.md)
4. [app/config.py](../app/config.py)
5. [docker-compose.yml](../docker-compose.yml)
6. [app/models/qwen_tts.py](../app/models/qwen_tts.py)
7. [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)

---

## Useful Commands To Resume

Check repo state:

```bash
git status
git log --oneline -n 5
```

Build and run one model service:

```bash
docker compose up -d --build tts-api-qwen
docker compose up -d --build tts-api-chatterbox
```

Quick health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

App-level benchmark once a service is live:

```bash
python -m benchmark.run_benchmark \
  --base-url http://localhost:8000 \
  --api-key dev-local-key-change-me \
  --models qwen3-tts
```

or:

```bash
python -m benchmark.run_benchmark \
  --base-url http://localhost:8001 \
  --api-key dev-local-key-change-me \
  --models chatterbox
```

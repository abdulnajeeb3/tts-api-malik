# Agent Handoff

> Current checkpoint for resuming work in a later session or handing the repo
> to another agent.

**Last updated:** April 14, 2026 (updated after Chatterbox endpoint repair on a new Vast instance)  
**Branch:** `main`  
**Latest pushed commit:** `236e914`  
**Repo state at handoff:** working tree has local, uncommitted updates from the Chatterbox endpoint repair pass

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

### Fully validated (new — April 14, 2026)

- **Chatterbox FastAPI smoke test complete** on Vast.ai RTX 4090:
  - `GET /health` → 200, model loaded
  - `POST /v1/audio/speech` → 200, 192 KB WAV, `X-TTFA-Ms=7335`
  - `WS /v1/audio/stream` → 17 chunks, 117120 bytes, TTFA 820 ms
- Current public URL confirmed reachable from local Mac on **April 14, 2026**:
  `http://57.132.208.22:23106`

### Not yet fully validated

- Qwen3-TTS FastAPI serving path has not had an end-to-end GPU smoke test.
  The direct-package benchmark ran fine, but the FastAPI wrapper has not been
  hit on GPU.

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
6. Chatterbox also needed a Perth repair path in
   [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py) because
   `perth.PerthImplicitWatermarker` was unset during startup on the Texas box.

---

## Immediate Next Step

Chatterbox is already smoke-tested and the friend has a live URL. Wait for
their voice quality feedback, then act on it.

While waiting:

1. Share the pre-generated Chatterbox WAVs with the friend:
   `benchmark/vast_4090_2026-04-13/chatterbox_full_output/*.wav`
2. OR point them at `http://57.132.208.22:23106` with key `dev-local-key-change-me`

After feedback:

1. If Chatterbox quality is good → lock it in, start Qwen3-TTS FastAPI smoke
   test, then productionize on Azure once T4 quota approved
2. If Chatterbox quality is bad → run Qwen3-TTS via FastAPI on Vast, benchmark
   it, let friend compare
3. If both are bad → revisit TTS_MODELS_RESEARCH_V2.md for the next candidate

Also remaining:

- Update the tracked docs with the current Texas instance details and push
- Stop Vast instance `34960563` to stop the ~$0.30/hr burn when done testing

---

## Exact Files To Read First

1. [documentation/PROJECT_STATUS.md](./PROJECT_STATUS.md)
2. [documentation/VAST_BENCHMARK_STATUS.md](./VAST_BENCHMARK_STATUS.md)
3. [documentation/CURRENT_ENDPOINT.md](./CURRENT_ENDPOINT.md)
4. [documentation/FRIEND_TESTING_GUIDE.md](./FRIEND_TESTING_GUIDE.md)
5. [app/config.py](../app/config.py)
6. [docker-compose.yml](../docker-compose.yml)
7. [app/models/qwen_tts.py](../app/models/qwen_tts.py)
8. [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)

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

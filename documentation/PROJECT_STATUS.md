# Project Status

> Snapshot updated on **April 14, 2026** (third update) after the Chatterbox
> endpoint was repaired and relaunched on the current Vast.ai RTX 4090
> instance.
> Read this first before resuming work.

Latest pushed checkpoint:

- branch: `main`
- commit: `236e914`
- quick handoff: [documentation/AGENT_HANDOFF.md](./AGENT_HANDOFF.md)
- live endpoint: [documentation/CURRENT_ENDPOINT.md](./CURRENT_ENDPOINT.md)

---

## TL;DR

- The API scaffold boots locally in mock mode (pydantic-settings bug fixed).
- The research phase is complete and the model recommendation changed.
- Fish has been removed from the scaffold.
- A real remote benchmark was completed on Vast.ai for:
  - **Qwen3-TTS**
  - **Chatterbox**
- **Chatterbox FastAPI smoke test is complete and passing on RTX 4090.**
- The codebase now names:
  - `qwen3-tts`
  - `chatterbox`
- The runtime strategy is:
  - **one model per service**
  - **separate dependency stacks**
- The real wrapper code is implemented for both models.
- Streaming is active through the WebSocket route.
- Chatterbox live endpoint: `http://57.132.208.22:23093` (Vast.ai, watch the credit).
- Waiting on: friend's voice quality feedback and Azure T4 GPU quota approval.

---

## What Is Done

### 1. Research is complete

Relevant docs:

- [documentation/TTS_MODELS_RESEARCH_V2.md](./TTS_MODELS_RESEARCH_V2.md)

Current conclusion:

- **Qwen3-TTS** is still a top candidate because of its latency story and
  Apache 2.0 licensing.
- **Chatterbox** is the strongest open-source quality candidate with a clean
  commercial license.
- Several previously considered models are blocked for self-hosted production
  use by non-commercial licensing.

Practical implication:

- The original plan to keep Fish as the second production model is obsolete.

### 2. Vast.ai setup is working

Relevant doc:

- [documentation/VAST_BENCHMARK_STATUS.md](./VAST_BENCHMARK_STATUS.md)

Completed:

- Vast CLI auth issue diagnosed and fixed
- Dedicated SSH key created and attached
- Vast RTX 4090 instance rented successfully
- Remote SSH access verified

Important:

- The original benchmark box was instance `34883373` in New Jersey.
- The current live Chatterbox endpoint is on a newer instance:
  - Vast instance ID `34958086`
  - Texas RTX 4090
  - about `$0.2967/hr`
- Always re-check [documentation/CURRENT_ENDPOINT.md](./CURRENT_ENDPOINT.md)
  before assuming the live URL has not changed.

### 3. First real bakeoff is complete

Benchmark artifacts pulled into the repo:

- [benchmark/vast_4090_2026-04-13/qwen_full_output/results.jsonl](../benchmark/vast_4090_2026-04-13/qwen_full_output/results.jsonl)
- [benchmark/vast_4090_2026-04-13/chatterbox_full_output/results.jsonl](../benchmark/vast_4090_2026-04-13/chatterbox_full_output/results.jsonl)

Supporting script added:

- [benchmark/direct_model_bakeoff.py](../benchmark/direct_model_bakeoff.py)

High-level result:

- **Qwen3-TTS**
  - mean total `6478 ms`
  - mean audio `4.95 s`
  - mean RTF `1.31`
- **Chatterbox**
  - mean total `2035 ms`
  - mean audio `4.37 s`
  - mean RTF `0.47`

Interpretation:

- Chatterbox is the better runtime result in the current direct-package test.
- Qwen worked, but it did **not** reproduce the expected fast path yet.
- Qwen still needs tuning before we trust its latency story on this stack.

---

## What The Codebase Says Now

The scaffold is now aligned at the naming level:

- [app/config.py](../app/config.py)
  - `ModelName = Literal["qwen3-tts", "chatterbox"]`
  - `enabled_models` defaults to `qwen3-tts`
- [app/models/__init__.py](../app/models/__init__.py)
  - registry now knows Qwen and Chatterbox
- [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)
  - now includes a Perth repair path for runtime startup

Current implementation status of the wrappers:

- [app/models/qwen_tts.py](../app/models/qwen_tts.py)
  - loads via `qwen-tts`
  - serves through `generate_custom_voice(...)`
- [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)
  - loads via `chatterbox-tts`
  - serves through `generate(...)`

Important architectural finding from the Vast run:

- `qwen-tts` and `chatterbox-tts` currently want incompatible
  `transformers` versions.
- That means a naive single-env "load both in one process" approach is not the
  working direction for this repo.
- The remote benchmark only worked by splitting them into separate virtualenvs.

This is the biggest engineering constraint discovered so far, and the repo now
adopts **separate per-model runtimes** as the default answer.

---

## Recommended Next Coding Work

### Priority 1. GPU smoke-test the real app path

Completed at the build/config level:

1. Separate service concept chosen
2. Separate Docker build paths added
3. Separate dependency stacks added
4. Real wrappers added for Qwen and Chatterbox

Still missing:

1. Build and boot each runtime on GPU
2. Hit `/v1/audio/speech` and `WS /v1/audio/stream` for each service
3. Confirm package/runtime quirks did not break inside the FastAPI process

Current status:

1. Chatterbox: done
2. Qwen3-TTS: still pending

### Priority 2. Expose testing endpoints cleanly

Likely near-term shape:

1. Qwen service on one base URL/port
2. Chatterbox service on another base URL/port
3. Friend tests whichever service is active without worrying about mixed-model
   dependency issues
4. ElevenLabs-compatible shim comes later if needed

### Priority 3. Improve streaming quality

Today:

1. `WS /v1/audio/stream` is active
2. it streams PCM chunks from a completed waveform
3. TTFA therefore reflects full synthesis time, not native incremental output

Later:

1. try Qwen native streaming
2. investigate Chatterbox-native options if stable
3. add HTTP streaming only if a client specifically needs it

---

## Recommended Next Session Order

1. Read [documentation/VAST_BENCHMARK_STATUS.md](./VAST_BENCHMARK_STATUS.md)
2. Listen to the pulled WAVs under
   [benchmark/vast_4090_2026-04-13](../benchmark/vast_4090_2026-04-13)
3. Review the separate runtime Docker/compose setup
4. If continuing Chatterbox work, collect friend feedback from the live Texas URL
5. Otherwise, start the Qwen FastAPI smoke test next
6. hand that base URL to the friend

---

## Working Tree Changes To Be Aware Of

This checkpoint is committed and pushed. The main repo state to remember is:

- [README.md](../README.md)
- [app/README.md](../app/README.md)
- [app/models/README.md](../app/models/README.md)
- [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)
- [benchmark/direct_model_bakeoff.py](../benchmark/direct_model_bakeoff.py)
- [benchmark/README.md](../benchmark/README.md)
- [benchmark/vast_4090_2026-04-13](../benchmark/vast_4090_2026-04-13)
- [documentation/AZURE_SETUP.md](./AZURE_SETUP.md)
- [documentation/AGENT_HANDOFF.md](./AGENT_HANDOFF.md)
- [documentation/PROJECT_STATUS.md](./PROJECT_STATUS.md)
- [documentation/VAST_BENCHMARK_STATUS.md](./VAST_BENCHMARK_STATUS.md)

At the time this status doc was updated, the working tree was clean after
push. If you resume later, still run `git status` first before changing
anything.

---

## Quick Resume Checklist

```bash
cd ~/Documents/Projects/TTS-API-Malik
git status
```

Then read, in this order:

1. [documentation/AGENT_HANDOFF.md](./AGENT_HANDOFF.md)
2. [documentation/PROJECT_STATUS.md](./PROJECT_STATUS.md)
3. [documentation/VAST_BENCHMARK_STATUS.md](./VAST_BENCHMARK_STATUS.md)
4. [documentation/TTS_MODELS_RESEARCH_V2.md](./TTS_MODELS_RESEARCH_V2.md)

Then inspect the code paths that still need alignment:

1. [app/config.py](../app/config.py)
2. [app/models/__init__.py](../app/models/__init__.py)
3. [app/models/qwen_tts.py](../app/models/qwen_tts.py)
4. [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)

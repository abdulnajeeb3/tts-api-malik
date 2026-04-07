# Project Status & Tomorrow's Plan

> Snapshot at end of session on **2026-04-06**. Read this first when you sit
> down tomorrow — it tells you what's done, what's running, and exactly which
> command to run next.

---

## TL;DR

- The API scaffold is **complete** and **boots end-to-end on the MacBook in mock mode**. All three endpoints have been smoke-tested.
- Azure is **half-done**: free-tier subscription is alive, resource group + networking + budget alerts are in place. **No GPU VM yet** — that's blocked behind upgrading from Free Trial to Pay-As-You-Go.
- The **single hard decision waiting for you tomorrow**: do you want to upgrade the Azure subscription to PAYG so we can request A10 GPU quota and provision the real inference VM? Until then we're stuck doing only no-GPU work.

---

## What's done (verified working)

### 1. Repo + scaffold
- GitHub repo: [abdulnajeeb3/tts-api-malik](https://github.com/abdulnajeeb3/tts-api-malik), cloned at `~/Documents/Projects/TTS-API-Malik`, SSH key `personal-macbook` registered.
- Full FastAPI app structure with per-folder READMEs:
  - [app/](../app/) — entrypoint, config, auth, audio utils, streaming handler
  - [app/models/](../app/models/) — `TTSModel` ABC + Qwen3-TTS / Fish Speech wrappers + registry builder
  - [benchmark/](../benchmark/) — A/B latency runner + 10 medical phrases
  - [documentation/](.) — cross-cutting docs (this file, Azure setup, model research)
- Dockerfile (CUDA 12.1.1 runtime, Ubuntu 22.04, Python 3.11) and `docker-compose.yml` (NVIDIA runtime, models cache volume) — ready to use on the GPU VM.
- `.env.example` documented; local `.env` created with `USE_MOCK_MODELS=1`.
- Two commits on `main`, both pushed:
  1. `5338493` — Initial scaffold
  2. `b3e8ae6` — `fix(config): unblock mock-mode boot by storing list-style env vars as strings`

### 2. Local mock-mode boot — VERIFIED
- Python 3.9 venv at [.venv/](../.venv/), all deps from [requirements.txt](../requirements.txt) installed.
- The pydantic-settings v2 list-field bug is fixed: `api_keys` and `enabled_models` are stored as plain strings and exposed via `api_key_list` / `enabled_model_list` properties on [app/config.py](../app/config.py). Reason: `pydantic_settings.NoDecode` (the cleaner fix) isn't exported from 2.6.0.
- All three endpoints smoke-tested **today** with `uvicorn app.main:app --host 127.0.0.1 --port 8000`:

  | Endpoint | Result |
  |---|---|
  | `GET /health` | 200, both mock models loaded |
  | `POST /v1/audio/speech` (valid key) | 200, valid 24kHz mono PCM WAV (147 KB) |
  | `POST /v1/audio/speech` (no key / wrong key) | 401 |
  | `WS /v1/audio/stream` | 21 binary chunks, 118 KB total, TTFA 1ms, final JSON frame received |

### 3. Azure free-tier scaffolding
- Subscription: **Azure subscription 1** (`9f381cde-3691-4ffe-9185-9397937ec847`)
  - Tenant: `c94a211e-7044-4508-8a2b-41d97eec6f49`
  - Mode: **Free Trial** (`FreeTrial_2014-09-01`), `spendingLimit: On` — this is the **real** safety net (auto-pauses everything if $200 credit runs out).
- Region: **eastus** (must match the friend's voice-agent infra).
- Resource group, virtual network, subnet, NSG, and NSG rules are all created (SSH from `47.184.121.141` on 22, TTS API on 8000).
- **Budget alerts** at $30/month with notifications at:
  - Actual ≥ 33% (~$10) — early-warning
  - Actual ≥ 83% (~$25) — danger
  - Actual ≥ 100% (~$30) — stop-the-line
  - Forecasted ≥ 100% — projection alarm
  - All sent to `abdulnajeeb3@gmail.com`. Budget body lives at `/tmp/tts-budget.json` (recreate from this file if needed; the actual budget is already deployed).
  - **Where to find them in the portal:** Cost Management + Billing → Cost Management → Budgets → `tts-api-monthly`. **Not** under Monitor → Alerts. The "Alerts and service issues" tile on the Azure home page only shows Monitor alerts (resource metrics), which is a completely separate system from budget alerts. To verify from CLI: `az consumption budget list -o table`.
- **No VM yet.** No GPU quota visible because Free Trial doesn't grant GPU SKUs.

### 4. Documentation
- [documentation/AZURE_SETUP.md](AZURE_SETUP.md) — full provisioning walkthrough for the GPU VM (quota check, NVIDIA driver extension with the A10/GRID 17.5 fix pinned to driver 535.161.08, NVIDIA Container Toolkit, SSH handoff).
- [documentation/TTS_MODELS_RESEARCH.md](TTS_MODELS_RESEARCH.md) — survey of open-source TTS models, recommends adding **CosyVoice2-0.5B** and **Chatterbox** to the benchmark shortlist alongside Qwen3-TTS and Fish Speech S1-mini. Includes scale math for 50M chars/month (one A10 is borderline insufficient).
- [README.md](../README.md) — repo entrypoint, cost model, "where to look when something breaks".

---

## What's not done yet

### Blocked
- **Real GPU inference.** `_generate_waveform()` in [app/models/qwen_tts.py](../app/models/qwen_tts.py) and [app/models/fish_tts.py](../app/models/fish_tts.py) is a `TODO(phase-1)` placeholder. We can't implement it on the MacBook (no CUDA, no VRAM headroom). It's the first thing to do on the GPU VM.
- **Azure GPU VM.** Blocked behind the PAYG upgrade decision. No quota → no `NC8as_A10_v4` → no real benchmarks.

### Optional / not started
- CosyVoice2-0.5B and Chatterbox model wrappers — recommended in the research doc but not yet scaffolded.
- Native streaming generation per model (Phase 3). The current `stream()` falls back to synth-then-chunk in [app/models/base.py](../app/models/base.py); real TTFA wins come from native chunk-by-chunk generation later.
- Concurrency tuning + load test (Phase 4).
- B1S free-tier VM for a deployment dry-run (cheap, useful but not on the critical path).

---

## Tomorrow's plan, in order

> Pick the path you want first. Path A unblocks the real work; Path B keeps you in free tier and is purely safe.

### Path A — Unblock the GPU VM (recommended)
1. **Decide on PAYG upgrade.** Open the Azure portal → Subscriptions → "Azure subscription 1" → **Upgrade**. Free credit ($200) carries over and gets consumed first; PAYG only kicks in after the credit is exhausted *and* the spending-limit-removal step is completed. The budget alerts are already in place as a tripwire.
2. **Request A10 quota** in `eastus`:
   ```bash
   az vm list-usage --location eastus -o table | grep -i a10
   az quota create ...   # OR use the portal "Request quota increase" UI
   ```
   Ask for `Standard NCASv3_T4 Family vCPUs` and `Standard NVadsA10 v5 Family vCPUs` — at least 8 vCPUs of each so we can pick whichever has stock. Quota requests usually approve in <30 min for tiny numbers.
3. **Provision** `NC8as_A10_v4` per [documentation/AZURE_SETUP.md](AZURE_SETUP.md). Use a **spot instance** (~$0.26/hr vs $1.43/hr PAYG) — the doc covers the eviction policy.
4. **Hand SSH access to me** so I can take over from inside the VM:
   - Create a fresh SSH keypair on the VM, paste the public key into your local `~/.ssh/authorized_keys` setup, and just run `az vm run-command invoke ...` (or open the VM in Cloud Shell) — you don't need to share any credentials. The Azure setup doc has the step-by-step.
5. From inside the VM I will:
   - Install NVIDIA driver extension (pinned 535.161.08, the A10/GRID 17.5 workaround).
   - Install NVIDIA Container Toolkit.
   - Clone the repo, set `USE_MOCK_MODELS=0`, `docker compose up -d --build`.
   - Fill in `_generate_waveform()` for both models (Phase 1).
   - Re-run the smoke tests against real GPU output.
   - Run [benchmark/run_benchmark.py](../benchmark/run_benchmark.py) for the first real TTFA numbers.

### Path B — Stay in free tier
1. Spin up a `Standard_B1s` (or `B1ls`) VM in `eastus` — included in the always-free tier. No GPU, no real inference, but lets us do a Docker deployment dry-run with mock mode.
2. Add CosyVoice2-0.5B and Chatterbox model wrappers locally (mock-only) so they're ready when we get GPU.
3. Polish the WebSocket protocol docs and add a small client SDK example.

---

## Quickstart commands for tomorrow

```bash
# 1. Re-enter the project
cd ~/Documents/Projects/TTS-API-Malik
source .venv/bin/activate

# 2. Confirm nothing is stale
git status
git pull --ff-only

# 3. Boot the API in mock mode (sanity check)
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. In another terminal, smoke-test
curl -s http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"fish-s1-mini","input":"hello","voice":"default","response_format":"wav"}' \
  --output /tmp/test.wav
file /tmp/test.wav   # should report: RIFF WAVE 16-bit mono 24000 Hz

# 5. (Optional) Re-confirm Azure state
az account show -o table
az group list -o table
az consumption budget list -o table
```

---

## Key facts to keep in your head

- **Region is locked to `eastus`** (friend's infra).
- **Both models load into VRAM at startup** (no lazy loading) — this is a deliberate plan-locked decision.
- **Auth is `X-API-Key` header** (or `?api_key=` on the WS URL). Keys come from the `API_KEYS` env var.
- **PCM16 24kHz mono** is the default streaming format.
- **Free Trial spending limit is the real safety net.** The $30 budget alerts are *informational*, not enforcement.
- **The plan PDF defines a strict 6-phase build order. Don't skip phases.** We're between Phase 0 (scaffold) and Phase 1 (models actually run).

---

## Things to double-check before any merge to `main`

1. `uvicorn app.main:app` boots without warnings on a clean venv.
2. Mock-mode `GET /health` returns both models.
3. Mock-mode REST returns valid audio (`file <output>` reports a real WAV/MP3 header).
4. WebSocket smoke test reports `done: True` with non-zero `bytes`.
5. `git status` is clean and `git push` succeeds.

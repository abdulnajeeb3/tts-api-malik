# Current Live Endpoint

> Written **April 14, 2026** after the FastAPI GPU smoke test on Vast.ai.
> This file is intentionally ephemeral — update it every time you spin up or
> tear down a GPU instance.

---

## Status

**Chatterbox service: LIVE** (as of April 14, 2026, ~19:00 UTC)  
**Qwen3-TTS service: NOT YET SERVED via FastAPI** (only via direct benchmark harness)

---

## Connection Details

| Field | Value |
|---|---|
| Provider | Vast.ai |
| GPU | RTX 4090 (24 GB VRAM) |
| Instance ID | `34883373` |
| Region | New Jersey, US |
| Public IP | `71.104.167.38` |
| REST port | `52328` (maps to container port 8000) |
| SSH port | `52292` |
| Rate | ~$0.39/hr |

**Base URL (REST):**

```
http://71.104.167.38:52328
```

**Base URL (WebSocket):**

```
ws://71.104.167.38:52328
```

---

## API Key

```
dev-local-key-change-me
```

Send as header: `X-API-Key: dev-local-key-change-me`

---

## Quick Smoke Test Commands

```bash
# Health check
curl http://71.104.167.38:52328/health

# Generate a WAV (saves to chatterbox_live.wav)
curl -X POST http://71.104.167.38:52328/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "chatterbox",
    "input": "Your appointment with Doctor Smith is confirmed for Tuesday at 2:30 PM.",
    "voice": "default",
    "response_format": "wav",
    "speed": 1.0
  }' \
  --output chatterbox_live.wav
```

---

## Validated Smoke Test Results (April 14, 2026)

All three endpoints were hit from a local Mac against the Vast RTX 4090.

| Test | Result | Notes |
|---|---|---|
| `GET /health` | 200 OK | model = chatterbox, status = loaded |
| `POST /v1/audio/speech` | 200 OK | 186 KB WAV, 2.2s wall time |
| `WS /v1/audio/stream` | 15 chunks, 101 KB | TTFA 1.1s |

VRAM at load time: **3.47 / 23.52 GB used** — plenty of headroom.

Round-trip from local Mac (including network): **2.7s** for a 4-second phrase.

---

## Watchdog

A local watchdog process keeps the instance from running indefinitely.

- Script: `scripts/vast_watchdog.sh`
- Heartbeat file: `/tmp/vast_keepalive`
- Stale threshold: 900s (15 min)
- Hard cap: 10800s (3 hr from watchdog start)
- Instance is destroyed automatically if heartbeat goes stale

To keep the instance alive while you work:

```bash
touch /tmp/vast_keepalive
```

To stop the watchdog WITHOUT destroying the instance:

```bash
pkill -f vast_watchdog.sh   # while leaving the heartbeat file in place
```

---

## SSH Access

```bash
ssh -A \
  -o StrictHostKeyChecking=no \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p 52292 root@71.104.167.38
```

---

## What Is Running Remotely

The Chatterbox service was started via `/workspace/launch_chatterbox.sh`:

```bash
#!/bin/bash
export LD_LIBRARY_PATH=\
/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cudnn/lib:\
/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cufft/lib:\
/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cublas/lib:\
$LD_LIBRARY_PATH

source /workspace/venvs/chatterbox/bin/activate
cd /workspace/TTS-API-Malik
uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
```

The `.env` file on the remote:

```
HOST=0.0.0.0
PORT=8000
API_KEYS=dev-local-key-change-me
ENABLED_MODELS=chatterbox
HF_HOME=/workspace/hf_cache
CHATTERBOX_DEVICE=cuda:0
USE_MOCK_MODELS=0
DEFAULT_REST_FORMAT=wav
```

---

## Spend Tracking

- Rate: $0.39/hr
- Running since: April 13, 2026
- At time of handoff (April 14, ~19:00 UTC): approximately $0.50–0.80 spent
- Remaining Vast credit at session start: $2.03

Shut down the instance when the friend has finished testing:

```bash
# Destroy via API (uses ~/.config/vastai/vast_api_key):
curl -s -X DELETE \
  -H "Authorization: Bearer $(cat ~/.config/vastai/vast_api_key)" \
  "https://console.vast.ai/api/v0/instances/34883373/"
```

Or from the Vast.ai web console.

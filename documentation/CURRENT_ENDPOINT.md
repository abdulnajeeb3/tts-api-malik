# Current Live Endpoint

> Updated **April 14, 2026** after repairing and relaunching the Chatterbox
> FastAPI service on the current Vast.ai instance.
> This file is intentionally ephemeral. Update it every time you rotate
> instances, change ports, or shut the endpoint down.

---

## Status

**Qwen3-TTS service: LIVE** (swapped in over the same instance on April 14, 2026)  
Verified from local Mac.

**Chatterbox service: STOPPED**  
The Chatterbox venv and launch script remain on the remote box; to switch back, run `/workspace/launch_chatterbox.sh` after killing Qwen's uvicorn.

---

## Connection Details

| Field | Value |
|---|---|
| Provider | Vast.ai |
| GPU | RTX 4090 (24 GB VRAM) |
| Instance ID | `34960563` |
| Label | `tts-v3` |
| Region | Texas, US |
| Public IP | `57.132.208.22` |
| REST port | `23106` (maps to container port 8000) |
| Proxy SSH host | `ssh6.vast.ai` |
| Proxy SSH port | `10562` |
| Hourly rate | ~$0.2967/hr |

**Base URL (REST):**

```text
http://57.132.208.22:23106
```

**Base URL (WebSocket):**

```text
ws://57.132.208.22:23106
```

---

## API Key

```text
dev-local-key-change-me
```

Use header: `X-API-Key: dev-local-key-change-me`

---

## Verified Smoke Tests

Validated on **April 14, 2026**.

| Test | Result | Notes |
|---|---|---|
| `GET /health` | 200 OK | `models_loaded = ["qwen3-tts"]` |
| `POST /v1/audio/speech` | 200 OK | 222764-byte WAV, `X-TTFA-Ms=3501`, `X-Total-Ms=3501` |
| `WS /v1/audio/stream` | pending | not exercised on this swap |

Current health response:

```json
{
  "status": "ok",
  "models_loaded": ["chatterbox"],
  "gpu_memory_used_gb": 3.48,
  "gpu_memory_total_gb": 23.52,
  "active_connections": 0,
  "version": "0.1.0"
}
```

---

## Quick Smoke Test Commands

```bash
curl http://57.132.208.22:23106/health
```

```bash
curl -X POST http://57.132.208.22:23106/v1/audio/speech \
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

## Streaming Smoke Test

Request payload:

```json
{
  "model": "chatterbox",
  "input": "Please hold for just a moment while I transfer you.",
  "voice": "default",
  "format": "pcm",
  "sample_rate": 24000,
  "speed": 1.0
}
```

Final frame received:

```json
{
  "done": true,
  "request_id": "552ae11a-baa7-446b-988c-47f51025eb42",
  "ttfa_ms": 820,
  "total_ms": 823,
  "bytes": 117120
}
```

---

## Remote Runtime Notes

The service is launched via `/workspace/launch_chatterbox.sh` and uses:

- `/workspace/venvs/chatterbox`
- `/workspace/TTS-API-Malik`
- a patched [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)

The critical repair was:

- ensure `perth.PerthImplicitWatermarker` is repaired via direct import before
  Chatterbox model load
- fall back to `DummyWatermarker` only if the direct Perth import still fails

Without that repair, startup failed with:

```text
TypeError: 'NoneType' object is not callable
```

---

## SSH Access

```bash
ssh -A \
  -o StrictHostKeyChecking=no \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p 38086 root@ssh7.vast.ai
```

---

## Shut It Down When Done

Destroy via Vast CLI or portal when the friend has finished testing.

Example via API key:

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer $(cat ~/.config/vastai/vast_api_key)" \
  "https://console.vast.ai/api/v0/instances/34960563/"
```

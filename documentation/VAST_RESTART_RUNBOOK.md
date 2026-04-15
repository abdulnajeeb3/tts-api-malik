# Vast Restart Runbook

> End-to-end procedure for bringing this repo back up on a fresh Vast.ai
> instance and exposing either `chatterbox` or `qwen3-tts`.
>
> This is the "do it again from scratch" document. It is based on the steps
> that actually worked during the live Vast rebuilds.

---

## Scope

This runbook covers:

1. renting a new Vast instance
2. getting the SSH details
3. syncing the repo
4. setting up a dedicated venv for one model
5. launching the FastAPI service
6. smoke-testing the public endpoint
7. updating the live-endpoint docs

Current recommendation:

- run **one model per instance / runtime**
- use **Chatterbox** when you need the currently validated FastAPI path
- use **Qwen** only after doing a fresh FastAPI smoke test on the new box

---

## Prerequisites

Expected local state:

- Vast API key saved at `~/.config/vastai/vast_api_key`
- SSH key at `~/.ssh/vast_benchmark_ed25519`
- repo checked out locally
- `vastai` CLI available at `/tmp/vastai-venv-312/bin/vastai`

Quick checks:

```bash
env -u VAST_API_KEY -u VAST_AI_API_KEY /tmp/vastai-venv-312/bin/vastai show user --raw
ssh-add -l
git status
```

If `ssh-add -l` does not show your Vast key:

```bash
ssh-add ~/.ssh/vast_benchmark_ed25519
```

---

## Step 1 — Find And Rent A Box

Search for a cheap US 4090-class box:

```bash
env -u VAST_API_KEY -u VAST_AI_API_KEY /tmp/vastai-venv-312/bin/vastai search offers --raw --limit 10 -o dph 'gpu_name in ["RTX 4090","RTX 3090","A10","RTX A5000","RTX A6000"] gpu_ram>=16 disk_space>=50 cuda_vers>=12.1 reliability>=0.97 num_gpus=1 direct_port_count>=2 dph<=0.40'
```

Rent one with port `8000` exposed:

```bash
env -u VAST_API_KEY -u VAST_AI_API_KEY /tmp/vastai-venv-312/bin/vastai create instance ASK_ID \
  --image pytorch/pytorch:2.4.1-cuda12.1-cudnn9-devel \
  --disk 60 \
  --ssh \
  --direct \
  --label tts-v3 \
  -e '-p 8000:8000'
```

Notes:

- `ASK_ID` is the offer id from the search output.
- `-e '-p 8000:8000'` matters. Without it, the API port is not exposed.

---

## Step 2 — Get SSH And Port Details

After the instance is running:

```bash
env -u VAST_API_KEY -u VAST_AI_API_KEY /tmp/vastai-venv-312/bin/vastai show instances --raw
```

Record:

- `id`
- `public_ipaddr`
- `ssh_host`
- `ssh_port`
- `ports["8000/tcp"][0]["HostPort"]`

Example values from the working Chatterbox rebuild:

- instance id: `34960563`
- public IP: `57.132.208.22`
- SSH host: `ssh6.vast.ai`
- SSH port: `10562`
- public API port: `23106`

Verify the box:

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST \
  'python --version && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
```

---

## Step 3 — Sync The Repo

Only sync what the remote runtime needs:

```bash
rsync -az \
  -e "ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes -o PreferredAuthentications=publickey -i ~/.ssh/vast_benchmark_ed25519 -p SSH_PORT" \
  --exclude .git \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude .claude \
  --exclude benchmark/vast_4090_2026-04-13 \
  app \
  documentation \
  requirements.runtime.txt \
  requirements.qwen.txt \
  requirements.chatterbox.txt \
  .env.example \
  root@SSH_HOST:/workspace/TTS-API-Malik/
```

---

## Step 4 — Chatterbox Setup

### 4.1 Create the venv and install

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST "bash -lc '
set -e
cd /workspace
python3 -m venv venvs/chatterbox
source venvs/chatterbox/bin/activate
pip install --upgrade pip wheel
pip install \"setuptools<81\"
pip install -r /workspace/TTS-API-Malik/requirements.chatterbox.txt
pip install torch==2.6.0 torchaudio==2.6.0 torchvision==0.21.0
'"
```

Why:

- `setuptools<81` keeps `pkg_resources` available for `perth`
- Chatterbox’s runtime stack is isolated from Qwen

### 4.2 Write `.env`

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST "cat > /workspace/TTS-API-Malik/.env <<'EOF'
HOST=0.0.0.0
PORT=8000
API_KEYS=dev-local-key-change-me
ENABLED_MODELS=chatterbox
HF_HOME=/workspace/hf_cache
CHATTERBOX_DEVICE=cuda:0
USE_MOCK_MODELS=0
DEFAULT_REST_FORMAT=wav
EOF"
```

### 4.3 Launch

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST "cat > /workspace/launch_chatterbox.sh <<'EOF'
#!/bin/bash
export LD_LIBRARY_PATH=/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cudnn/lib:/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cufft/lib:/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cublas/lib:\$LD_LIBRARY_PATH
source /workspace/venvs/chatterbox/bin/activate
cd /workspace/TTS-API-Malik
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
EOF
chmod +x /workspace/launch_chatterbox.sh
nohup /workspace/launch_chatterbox.sh >/workspace/chatterbox.log 2>&1 </dev/null &"
```

### 4.4 Verify

Remote:

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST 'pgrep -af "uvicorn app.main:app"; tail -n 80 /workspace/chatterbox.log; curl -fsS http://127.0.0.1:8000/health'
```

Public:

```bash
curl http://PUBLIC_IP:PUBLIC_PORT/health
curl -X POST http://PUBLIC_IP:PUBLIC_PORT/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"chatterbox","input":"Hello, this is a test.","voice":"default","response_format":"wav","speed":1.0}' \
  --output /tmp/chatterbox_smoke.wav
```

Important runtime note:

- the current repo contains a repair path in
  [app/models/chatterbox_tts.py](../app/models/chatterbox_tts.py)
  for `perth.PerthImplicitWatermarker`
- without that fix, startup can fail with:
  `TypeError: 'NoneType' object is not callable`

---

## Step 5 — Qwen Setup

### 5.1 Create the venv and install

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST "bash -lc '
set -e
cd /workspace
python3 -m venv venvs/qwen
source venvs/qwen/bin/activate
pip install --upgrade pip wheel
pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.4.1
pip install -r /workspace/TTS-API-Malik/requirements.qwen.txt
pip install flash-attn
'"
```

### 5.2 Write `.env`

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST "cat > /workspace/TTS-API-Malik/.env <<'EOF'
HOST=0.0.0.0
PORT=8000
API_KEYS=dev-local-key-change-me
ENABLED_MODELS=qwen3-tts
HF_HOME=/workspace/hf_cache
QWEN_MODEL_ID=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
QWEN_DEVICE=cuda:0
QWEN_SPEAKER=Aiden
QWEN_LANGUAGE=English
QWEN_INSTRUCT=Professional and friendly tone.
QWEN_DTYPE=bfloat16
QWEN_ATTN_IMPLEMENTATION=flash_attention_2
USE_MOCK_MODELS=0
DEFAULT_REST_FORMAT=wav
EOF"
```

### 5.3 Launch

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST "cat > /workspace/launch_qwen.sh <<'EOF'
#!/bin/bash
source /workspace/venvs/qwen/bin/activate
cd /workspace/TTS-API-Malik
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
EOF
chmod +x /workspace/launch_qwen.sh
nohup /workspace/launch_qwen.sh >/workspace/qwen.log 2>&1 </dev/null &"
```

### 5.4 Verify

```bash
ssh -A -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p SSH_PORT root@SSH_HOST 'pgrep -af "uvicorn app.main:app"; tail -n 80 /workspace/qwen.log; curl -fsS http://127.0.0.1:8000/health'
```

Then test publicly exactly like Chatterbox, but with:

```json
{
  "model": "qwen3-tts",
  "voice": "Aiden"
}
```

Important:

- Qwen has direct benchmark validation
- the FastAPI path should still be treated as pending until you smoke-test it
  on the current box

---

## Step 6 — Update The Docs

After the endpoint is live, update:

- [documentation/CURRENT_ENDPOINT.md](./CURRENT_ENDPOINT.md)
- [documentation/FRIEND_TESTING_GUIDE.md](./FRIEND_TESTING_GUIDE.md)
- [documentation/AGENT_HANDOFF.md](./AGENT_HANDOFF.md)
- [documentation/PROJECT_STATUS.md](./PROJECT_STATUS.md)

At minimum, change:

- instance id
- region
- public IP
- public port
- hourly rate
- smoke-test numbers

---

## Step 7 — Teardown

When done:

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer $(cat ~/.config/vastai/vast_api_key)" \
  "https://console.vast.ai/api/v0/instances/INSTANCE_ID/"
```

Or destroy it from the Vast web console.

---

## Watchdog

The repo includes [scripts/vast_watchdog.sh](../scripts/vast_watchdog.sh).

Use it only when you intentionally want the instance auto-destroyed after
inactivity.

Example:

```bash
INSTANCE_ID=INSTANCE_ID \
HEARTBEAT_TIMEOUT_SEC=1800 \
MAX_TOTAL_SEC=14400 \
nohup scripts/vast_watchdog.sh >/tmp/vast_watchdog.log 2>&1 &
```

While it is armed:

```bash
touch /tmp/vast_keepalive
```

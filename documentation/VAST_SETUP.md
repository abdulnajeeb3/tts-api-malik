# Vast.ai Chatterbox Setup Runbook

> End-to-end procedure to get the Chatterbox FastAPI service live on a fresh
> Vast.ai RTX 4090. Follow this top-to-bottom whenever the instance has been
> destroyed and you need to rebuild from scratch. All gotchas hit during
> real rebuilds are baked in — don't deviate without a reason.
>
> **Time budget:** ~8-10 minutes start-to-smoke-test.

---

## Prerequisites (already done, just verify)

- Vast API key at `~/.config/vastai/vast_api_key` (file-backed, not shell env)
- SSH keypair at `~/.ssh/vast_benchmark_ed25519` (public key attached to Vast account)
- Local repo at `~/Documents/Projects/TTS-API-Malik`
- Python 3 with curl

Quick sanity check:

```bash
curl -s -H "Authorization: Bearer $(cat ~/.config/vastai/vast_api_key)" \
  https://console.vast.ai/api/v0/users/current/ \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('credit: $',round(d['credit'],2))"
```

---

## Step 1 — Find and rent a cheap US RTX 4090

```bash
KEY=$(cat ~/.config/vastai/vast_api_key)

curl -s -H "Authorization: Bearer $KEY" \
  "https://console.vast.ai/api/v0/bundles/?q=%7B%22gpu_name%22%3A%22RTX+4090%22%2C%22num_gpus%22%3A%221%22%2C%22rentable%22%3A%7B%22eq%22%3Atrue%7D%2C%22order%22%3A%5B%5B%22dph_total%22%2C%22asc%22%5D%5D%2C%22disk_space%22%3A%7B%22gte%22%3A60%7D%2C%22reliability2%22%3A%7B%22gt%22%3A0.95%7D%7D&limit=10" \
  > /tmp/offers.json

python3 -c "
import json
with open('/tmp/offers.json') as f: d=json.load(f)
offers=[o for o in d.get('offers',[]) if o.get('geolocation') and 'US' in o.get('geolocation')]
for o in sorted(offers,key=lambda x:x.get('dph_total',999))[:5]:
    print(f\"id={o.get('id')} \${o.get('dph_total'):.3f}/hr {o.get('geolocation')} disk={o.get('disk_space')}GB inet={o.get('inet_down')}/{o.get('inet_up')}\")
"
```

Pick the cheapest one with inet > 500 Mbps. Then rent:

```bash
ASK_ID=XXXXXXXX   # paste from above
KEY=$(cat ~/.config/vastai/vast_api_key)

curl -s -X PUT -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  "https://console.vast.ai/api/v0/asks/$ASK_ID/" \
  -d '{"client_id":"me","image":"pytorch/pytorch:2.4.1-cuda12.1-cudnn9-devel","disk":60,"runtype":"ssh","label":"tts-chatterbox","env":{"-p 8000:8000":"1"}}'
```

**Critical:** the `env` block with `"-p 8000:8000"` is how Vast maps container
port 8000 to a host port. Without it, `ports` comes back `null` and you cannot
reach the FastAPI service from outside the SSH tunnel.
```

Save `new_contract` from the response — that's your instance id.

---

## Step 2 — Wait for boot and grab SSH info

```bash
INST=XXXXXXXX   # your instance id
KEY=$(cat ~/.config/vastai/vast_api_key)

# Poll until running (docker image pull + first boot = ~90s):
for i in 1 2 3 4 5 6 7 8; do
  sleep 15
  S=$(curl -s -H "Authorization: Bearer $KEY" "https://console.vast.ai/api/v0/instances/$INST/")
  echo "$S" | python3 -c "import sys,json;i=json.load(sys.stdin).get('instances') or {};print('status:',i.get('actual_status'),'|',(i.get('status_msg') or '')[:60])"
  if echo "$S" | grep -q '"actual_status": "running"'; then echo "$S" > /tmp/inst.json; break; fi
done

python3 -c "
import json
with open('/tmp/inst.json') as f: d=json.load(f)
i=d['instances']
print('SSH_HOST:',i.get('ssh_host'))
print('SSH_PORT:',i.get('ssh_port'))
print('IP:',i.get('public_ipaddr'))
print('8000->',i.get('ports',{}).get('8000/tcp'))
"
```

Export the connection values for the rest of the run:

```bash
export SSH_HOST=ssh7.vast.ai   # from output
export SSH_PORT=38086          # from output
export IP=57.132.208.22        # from output
export PORT_8000=23093         # from output (host port mapped to container 8000)
```

Verify SSH:

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p "$SSH_PORT" root@"$SSH_HOST" \
    "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
```

---

## Step 3 — Rsync the repo (only what's needed)

```bash
cd ~/Documents/Projects/TTS-API-Malik

rsync -az \
  -e "ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT" \
  --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
  --exclude='benchmark/vast_4090_2026-04-13' --exclude='.claude' \
  --exclude='*.wav' --exclude='*.mp3' \
  app requirements.runtime.txt requirements.chatterbox.txt \
  root@$SSH_HOST:/workspace/TTS-API-Malik/
```

---

## Step 4 — Create venv and install deps (with all known fixes)

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "bash -s" <<'REMOTE'
set -e
cd /workspace
python3 -m venv venvs/chatterbox
source venvs/chatterbox/bin/activate
pip install --upgrade pip wheel > /tmp/pip.log 2>&1
pip install 'setuptools<81' >> /tmp/pip.log 2>&1        # critical: perth needs pkg_resources
pip install -r /workspace/TTS-API-Malik/requirements.chatterbox.txt >> /tmp/pip.log 2>&1
pip install torch==2.6.0 torchaudio==2.6.0 torchvision==0.21.0 >> /tmp/pip.log 2>&1
echo "done"
REMOTE
```

**Why `setuptools<81`:** Chatterbox 0.1.7 uses `perth.PerthImplicitWatermarker`,
which imports `pkg_resources`. setuptools 81+ removed that module. Without this
pin the service boots and then dies with `TypeError: 'NoneType' object is not
callable` during model load.

Installation takes 3-5 minutes (chatterbox pulls torch, diffusers, etc).

---

## Step 5 — Write .env and launch script on remote

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "cat > /workspace/TTS-API-Malik/.env << 'EOF'
HOST=0.0.0.0
PORT=8000
API_KEYS=dev-local-key-change-me
ENABLED_MODELS=chatterbox
HF_HOME=/workspace/hf_cache
CHATTERBOX_DEVICE=cuda:0
USE_MOCK_MODELS=0
DEFAULT_REST_FORMAT=wav
EOF
cat > /workspace/launch_chatterbox.sh << 'EOF'
#!/bin/bash
export LD_LIBRARY_PATH=/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cudnn/lib:/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cufft/lib:/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cublas/lib:\$LD_LIBRARY_PATH
source /workspace/venvs/chatterbox/bin/activate
cd /workspace/TTS-API-Malik
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
EOF
chmod +x /workspace/launch_chatterbox.sh"
```

**Why the `LD_LIBRARY_PATH` export:** torch 2.6.0 inside the isolated venv
can't find `libcudnn.so.9` on its own — needs the pip-shipped nvidia .so files
visible to the loader.

---

## Step 6 — Boot the service

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST \
    "nohup /workspace/launch_chatterbox.sh > /workspace/chatterbox.log 2>&1 &"
```

Wait for model weights download + load (~60-90s first time):

```bash
for i in 1 2 3 4 5 6 7 8; do
  sleep 15
  LOG=$(ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
        -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST \
        "tail -2 /workspace/chatterbox.log")
  echo "[$i] $LOG"
  if echo "$LOG" | grep -q "Uvicorn running"; then break; fi
done
```

---

## Step 7 — Smoke test from local Mac

```bash
curl http://$IP:$PORT_8000/health

curl -X POST http://$IP:$PORT_8000/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"chatterbox","input":"Hello, this is a test.","voice":"default","response_format":"wav","speed":1.0}' \
  --output /tmp/chatterbox_smoke.wav && open /tmp/chatterbox_smoke.wav
```

---

## Step 8 — Update `documentation/CURRENT_ENDPOINT.md`

Replace the Instance ID, IP, port, rate, and region in that file. Commit and push.

---

## Teardown (when done)

```bash
KEY=$(cat ~/.config/vastai/vast_api_key)
INST=XXXXXXXX
curl -s -X DELETE -H "Authorization: Bearer $KEY" \
  "https://console.vast.ai/api/v0/instances/$INST/"
```

---

## About the watchdog

`scripts/vast_watchdog.sh` exists to prevent forgotten instances from burning
credit indefinitely. **Do not arm it if you're stress-testing, doing
long-running work, or planning to step away briefly without touching the
heartbeat** — it will destroy your instance.

Rules of thumb:

- **Arm it** only when you're explicitly stepping away and *expect* the
  instance to die if left unattended
- **Don't arm it** during smoke tests, stress tests, or while the friend is
  actively using the endpoint
- If armed, touch `/tmp/vast_keepalive` every time you run a command, or use
  `while true; do touch /tmp/vast_keepalive; sleep 60; done &` as a
  background refresher

To arm (only if you really want it):

```bash
INSTANCE_ID=XXXXXXXX \
  HEARTBEAT_TIMEOUT_SEC=1800 \
  MAX_TOTAL_SEC=14400 \
  nohup scripts/vast_watchdog.sh > /tmp/vast_watchdog.log 2>&1 &
disown
```

To disarm without destroying:

```bash
pkill -f vast_watchdog.sh
```

---

## Known gotchas (already handled above — do not re-discover)

1. **`pkg_resources` missing** → pin `setuptools<81` *before* installing
   chatterbox deps
2. **cuDNN not found at runtime** → `LD_LIBRARY_PATH` must include the
   venv's `nvidia/*/lib` dirs (see launch script)
3. **`transformers` version conflicts between Qwen and Chatterbox** → never
   install both in one venv; always use separate venvs
4. **HF_TOKEN not set** → downloads still work but are rate-limited. Set it
   in `.env` if you hit rate-limit errors
5. **Vast API calls fail with env var set** → `VAST_API_KEY` shell export
   overrides file-backed key. Always read from `~/.config/vastai/vast_api_key`
   directly in scripts
6. **Only one port exposed** → current setup maps only container :8000 →
   host port. If you add HF streaming direct ports later, request them at
   rent time via the image config
7. **`ports` field is `None` after boot** → you forgot the `env -p` block in
   the rent request. There is no way to add it after the fact; destroy and
   re-rent with the correct env

# Vast Setup — Fast Runbook

> Copy-paste top to bottom. Gets Chatterbox or Qwen live on a fresh RTX 4090 in
> **~8 minutes**. All known gotchas are pre-handled — don't improvise.
>
> Prereqs (verify once, then assume): `~/.config/vastai/vast_api_key` exists,
> `~/.ssh/vast_benchmark_ed25519` exists, public key is on your Vast account.

---

## 1. Find and rent the cheapest US RTX 4090

```bash
KEY=$(cat ~/.config/vastai/vast_api_key)

curl -s -H "Authorization: Bearer $KEY" \
  "https://console.vast.ai/api/v0/bundles/?q=%7B%22gpu_name%22%3A%22RTX+4090%22%2C%22num_gpus%22%3A%221%22%2C%22rentable%22%3A%7B%22eq%22%3Atrue%7D%2C%22order%22%3A%5B%5B%22dph_total%22%2C%22asc%22%5D%5D%2C%22disk_space%22%3A%7B%22gte%22%3A60%7D%2C%22reliability2%22%3A%7B%22gt%22%3A0.95%7D%7D&limit=10" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
for o in sorted([o for o in d.get('offers',[]) if o.get('geolocation') and 'US' in o.get('geolocation')],key=lambda x:x.get('dph_total',999))[:5]:
    print(f\"id={o.get('id')} \${o.get('dph_total'):.3f}/hr {o.get('geolocation')} inet={o.get('inet_down')}\")
"
```

Pick an `id`, then:

```bash
ASK_ID=XXXXXXXX   # paste from above
KEY=$(cat ~/.config/vastai/vast_api_key)

curl -s -X PUT -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  "https://console.vast.ai/api/v0/asks/$ASK_ID/" \
  -d '{"client_id":"me","image":"pytorch/pytorch:2.4.1-cuda12.1-cudnn9-devel","disk":60,"runtype":"ssh","label":"tts","env":{"-p 8000:8000":"1"}}'
```

Save `new_contract` from response. That's `$INST`.

---

## 2. Wait for boot, grab connection info

```bash
KEY=$(cat ~/.config/vastai/vast_api_key)
INST=XXXXXXXX   # paste new_contract

for i in 1 2 3 4 5 6 7 8; do
  sleep 15
  S=$(curl -s -H "Authorization: Bearer $KEY" "https://console.vast.ai/api/v0/instances/$INST/")
  echo "$S" | python3 -c "import sys,json;i=(json.load(sys.stdin).get('instances') or {});print(i.get('actual_status'),'|',(i.get('status_msg') or '')[:60],'|ports=',i.get('ports'))"
  if echo "$S" | grep -q "HostPort"; then echo "$S" > /tmp/inst.json; break; fi
done

python3 -c "
import json
i=json.load(open('/tmp/inst.json'))['instances']
print(f\"export SSH_HOST={i.get('ssh_host')}\")
print(f\"export SSH_PORT={i.get('ssh_port')}\")
print(f\"export IP={i.get('public_ipaddr')}\")
print(f\"export PORT_8000={i.get('ports',{}).get('8000/tcp',[{}])[0].get('HostPort')}\")
print(f\"export INST={i.get('id')}\")
"
```

Copy those `export` lines into your shell.

---

## 3. Rsync code to remote

```bash
cd ~/Documents/Projects/TTS-API-Malik

rsync -az \
  -e "ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT" \
  --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
  --exclude='benchmark/vast_4090_2026-04-13' --exclude='.claude' \
  --exclude='*.wav' --exclude='*.mp3' \
  app requirements.runtime.txt requirements.chatterbox.txt requirements.qwen.txt \
  root@$SSH_HOST:/workspace/TTS-API-Malik/
```

---

## 4. Install venv (pick one)

### 4a. Chatterbox

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "bash -s" <<'REMOTE'
set -e
cd /workspace
python3 -m venv venvs/chatterbox
source venvs/chatterbox/bin/activate
pip install --upgrade pip wheel 'setuptools<81' > /tmp/pip.log 2>&1
pip install -r /workspace/TTS-API-Malik/requirements.chatterbox.txt >> /tmp/pip.log 2>&1
pip install torch==2.6.0 torchaudio==2.6.0 torchvision==0.21.0 >> /tmp/pip.log 2>&1
echo DONE
REMOTE
```

### 4b. Qwen3-TTS

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "bash -s" <<'REMOTE'
set -e
cd /workspace
python3 -m venv venvs/qwen
source venvs/qwen/bin/activate
pip install --upgrade pip wheel 'setuptools<81' > /tmp/pip.log 2>&1
pip install -r /workspace/TTS-API-Malik/requirements.qwen.txt soundfile rich >> /tmp/pip.log 2>&1
echo DONE
REMOTE
```

Either takes ~3-5 min.

---

## 5. Write .env and launch script (pick one)

### 5a. Chatterbox

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "cat > /workspace/TTS-API-Malik/.env <<'EOF'
HOST=0.0.0.0
PORT=8000
API_KEYS=dev-local-key-change-me
ENABLED_MODELS=chatterbox
HF_HOME=/workspace/hf_cache
CHATTERBOX_DEVICE=cuda:0
USE_MOCK_MODELS=0
DEFAULT_REST_FORMAT=wav
EOF
cat > /workspace/launch.sh <<'EOF'
#!/bin/bash
export LD_LIBRARY_PATH=/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cudnn/lib:/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cufft/lib:/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/cublas/lib:\$LD_LIBRARY_PATH
source /workspace/venvs/chatterbox/bin/activate
cd /workspace/TTS-API-Malik
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
EOF
chmod +x /workspace/launch.sh"
```

### 5b. Qwen3-TTS

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "cat > /workspace/TTS-API-Malik/.env <<'EOF'
HOST=0.0.0.0
PORT=8000
API_KEYS=dev-local-key-change-me
ENABLED_MODELS=qwen3-tts
HF_HOME=/workspace/hf_cache
QWEN_DEVICE=cuda:0
QWEN_ATTN_IMPLEMENTATION=sdpa
USE_MOCK_MODELS=0
DEFAULT_REST_FORMAT=wav
EOF
cat > /workspace/launch.sh <<'EOF'
#!/bin/bash
export LD_LIBRARY_PATH=/workspace/venvs/qwen/lib/python3.11/site-packages/nvidia/cudnn/lib:/workspace/venvs/qwen/lib/python3.11/site-packages/nvidia/cufft/lib:/workspace/venvs/qwen/lib/python3.11/site-packages/nvidia/cublas/lib:\$LD_LIBRARY_PATH
source /workspace/venvs/qwen/bin/activate
cd /workspace/TTS-API-Malik
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
EOF
chmod +x /workspace/launch.sh"
```

---

## 6. Boot the service

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST \
    "pkill -9 -f uvicorn; nohup /workspace/launch.sh > /workspace/service.log 2>&1 &"

for i in 1 2 3 4 5 6 7 8; do
  sleep 15
  LOG=$(ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
        -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST "tail -2 /workspace/service.log")
  echo "[$i] $(echo "$LOG" | tail -1)"
  [[ "$LOG" == *"Uvicorn running"* ]] && break
done
```

---

## 7. Smoke test

Remote (isolates "is the service up?" from port mapping):

```bash
ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
    -i ~/.ssh/vast_benchmark_ed25519 -p $SSH_PORT root@$SSH_HOST \
    "curl -fsS http://127.0.0.1:8000/health"
```

Public:

```bash
curl http://$IP:$PORT_8000/health

# Chatterbox
curl -X POST http://$IP:$PORT_8000/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"chatterbox","input":"Hello test.","voice":"default","response_format":"wav","speed":1.0}' \
  --output /tmp/out.wav && open /tmp/out.wav

# Qwen
curl -X POST http://$IP:$PORT_8000/v1/audio/speech \
  -H "X-API-Key: dev-local-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-tts","input":"Hello test.","voice":"Aiden","response_format":"wav","speed":1.0}' \
  --output /tmp/out.wav && open /tmp/out.wav
```

---

## 8. Update `documentation/CURRENT_ENDPOINT.md`

Replace `Instance ID`, `Public IP`, `REST port`, `Proxy SSH host`, `Proxy SSH port`, `Hourly rate`. Commit and push.

---

## 9. Arm the 30-min kill timer

```bash
INSTANCE_ID=$INST DELAY_SEC=1800 \
  nohup scripts/vast_kill_in.sh > /tmp/vast_kill.log 2>&1 &
disown
```

Extend by killing the timer and re-arming. Cancel with `pkill -f vast_kill_in.sh`.

To manually destroy anytime:

```bash
curl -s -X DELETE -H "Authorization: Bearer $(cat ~/.config/vastai/vast_api_key)" \
  "https://console.vast.ai/api/v0/instances/$INST/"
```

---

## Switching models on a live instance

Both venvs can coexist; only one `uvicorn` runs at a time on port 8000.

```bash
# kill current service
ssh ... "pkill -9 -f uvicorn"

# rewrite .env + launch.sh with step 5a or 5b of the other model
# then step 6
```

---

## Gotchas (already handled above — don't re-discover)

1. **`setuptools<81`** must install before chatterbox or qwen — both indirectly need `pkg_resources` (removed in setuptools 81+)
2. **`env -p 8000:8000` in the rent request** — without it, `ports` comes back `null` and no public port exists. No way to patch after the fact; destroy and re-rent.
3. **`LD_LIBRARY_PATH`** — torch inside the venv can't find `libcudnn.so.9` without nvidia/*/lib on the path
4. **Qwen `attn_implementation=sdpa`** — avoids the 10+ min flash-attn build; set via `QWEN_ATTN_IMPLEMENTATION=sdpa` in `.env`
5. **Never mix Qwen + Chatterbox in one venv** — conflicting `transformers` pins; always use `/workspace/venvs/qwen` and `/workspace/venvs/chatterbox` separately
6. **`VAST_API_KEY` shell export** overrides file-backed key; scripts read `~/.config/vastai/vast_api_key` directly — don't `export VAST_API_KEY=`
7. **Watchdog vs kill timer** — use `scripts/vast_kill_in.sh` (unconditional 30-min timer) for fire-and-forget. The heartbeat-based `scripts/vast_watchdog.sh` killed a live friend-testing session once because the user and I stopped touching the heartbeat — don't arm it during interactive work

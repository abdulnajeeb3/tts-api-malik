# Vast.ai Benchmark Status

> Updated on **April 14, 2026** with the benchmark results plus the repo-side
> follow-up work that was pushed after the bakeoff.

---

## TL;DR

- Vast CLI auth is working.
- The original auth failure was caused by stale `VAST_API_KEY` shell exports,
  not by a bad saved key.
- A **New Jersey RTX 4090** instance was rented successfully and remote SSH is
  working.
- Qwen3-TTS and Chatterbox could **not** be installed into one Python env
  because their pinned `transformers` stacks conflict.
- Two isolated remote virtualenvs were created:
  - `/workspace/venvs/qwen`
  - `/workspace/venvs/chatterbox`
- Both models completed the full **10 medical booking phrases** benchmark.
- Pulled artifacts now live locally in:
  `benchmark/vast_4090_2026-04-13/`
- Initial latency result on this box:
  - **Qwen3-TTS:** mean total `6478 ms`, mean RTF `1.31`
  - **Chatterbox:** mean total `2035 ms`, mean RTF `0.47`
- Chatterbox was materially faster in this direct-package test. Qwen is still
  underperforming the research expectation and needs deeper runtime tuning
  before its latency numbers should be trusted here.
- Since this benchmark, the repo has been updated to run Qwen and Chatterbox
  as separate services with real wrapper implementations matching the package
  calls validated here.
- The benchmark remains the last fully validated real-model run; the new
  FastAPI serving path still needs a fresh GPU smoke test.
- The pushed repo checkpoint associated with this follow-up work is:
  - branch `main`
  - commit `204f238`

---

## Root Cause Of The Vast CLI Auth Failure

The file-backed key was valid the whole time:

- `~/.config/vastai/vast_api_key`

The real problem was shell precedence:

- `VAST_API_KEY` was exported in the shell with a different value.
- `VAST_AI_API_KEY` was also present, but this CLI path does not use it.

Verified behavior:

- Direct authenticated request to Vast's documented endpoint succeeded:
  `GET https://console.vast.ai/api/v0/users/current/`
- Vast CLI commands worked immediately when those stale env vars were unset per
  command.

Workaround used during setup:

```bash
env -u VAST_API_KEY -u VAST_AI_API_KEY /tmp/vastai-venv-312/bin/vastai ...
```

---

## SSH State

Dedicated keypair:

- Private key: `~/.ssh/vast_benchmark_ed25519`
- Public key: `~/.ssh/vast_benchmark_ed25519.pub`
- Fingerprint:
  `SHA256:DiRgOIlrBtW9XPFTfVy5Qv811y9F3NeeTmLIHD0hpC0`

Status:

- Public key attached to Vast account
- Public key explicitly attached to the rented instance
- Private key loaded into `ssh-agent`

Working direct SSH path:

```bash
ssh -A -o StrictHostKeyChecking=no \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -i ~/.ssh/vast_benchmark_ed25519 \
  -p 52292 root@71.104.167.38
```

Verified remote machine:

- Python: `3.11.9`
- GPU: `NVIDIA GeForce RTX 4090`
- VRAM: `24564 MiB`
- Driver: `580.126.09`

---

## Rented Instance

- Vast instance ID: `34883373`
- Label: `tts-benchmark`
- Region: **New Jersey, US**
- GPU: **RTX 4090**
- GPU VRAM: **24,564 MB**
- vCPUs: **16**
- RAM: **64.2 GB**
- Disk: **100 GB**
- Docker image:
  `pytorch/pytorch:2.4.1-cuda12.1-cudnn9-devel`
- Total hourly cost at rent time: about **`$0.3879/hr`**

Connection metadata:

- Proxy SSH URL: `ssh://root@ssh1.vast.ai:13372`
- Public IP: `71.104.167.38`
- Container SSH -> host port: `52292`
- Container API port `8000` -> host port: `52328`

Current state at last check:

- `actual_status`: `running`
- `status_msg`:
  `success, running pytorch/pytorch_2.4.1-cuda12.1-cudnn9-devel/ssh`

---

## Remote Setup Performed

### Repo staging

Only the benchmark folder was synced to the remote machine:

- Remote path: `/workspace/TTS-API-Malik/benchmark`

### Python env split

Qwen and Chatterbox currently conflict at the dependency layer.

Conflict observed:

- `qwen-tts` pins `transformers==4.57.3`
- `chatterbox-tts` pins `transformers==5.2.0`

That made a single shared env invalid, so the remote box now uses:

- `/workspace/venvs/qwen`
- `/workspace/venvs/chatterbox`

### Qwen env

Installed successfully:

- `qwen-tts`
- `flash-attn`
- `soundfile`
- `rich`

Notes:

- Qwen emits a non-fatal SoX warning because the container does not have the
  `sox` binary installed.
- Generation still works without that binary.

### Chatterbox env

Installed successfully:

- `chatterbox-tts`
- `torch==2.6.0`
- `torchaudio==2.6.0`
- `torchvision==0.21.0`
- `optree`
- `soundfile`
- `rich`

Runtime fixes required:

1. `torch 2.6.0` could not initially find `libcudnn.so.9`
2. The system `torchvision 0.19.1` from the base image conflicted with the
   Chatterbox env's `torch 2.6.0`

Working fix:

- Keep Chatterbox in its own env
- Shadow the base `torchvision` inside that env
- Export `LD_LIBRARY_PATH` to include:
  - `/workspace/venvs/chatterbox/lib/python3.11/site-packages/nvidia/*/lib`
  - `/opt/conda/lib/python3.11/site-packages/nvidia/cudnn/lib`

---

## Benchmark Results

All runs used the real 10-phrase medical booking set from:

- `benchmark/test_phrases.txt`

### Qwen3-TTS

Remote output:

- `/workspace/TTS-API-Malik/benchmark/qwen_full_output`

Pulled local output:

- `benchmark/vast_4090_2026-04-13/qwen_full_output`

Summary:

- Runs: `10`
- Errors: `0`
- Mean total: `6478.4 ms`
- Mean audio duration: `4.95 s`
- Mean RTF: `1.31`
- Min total: `2837 ms`
- Max total: `8886 ms`

Interpretation:

- Functional, but slower than real time on this setup.
- This does **not** match the expected low-latency Qwen story from the
  research, so the remote package/runtime path still needs investigation.

### Chatterbox

Remote output:

- `/workspace/TTS-API-Malik/benchmark/chatterbox_full_output`

Pulled local output:

- `benchmark/vast_4090_2026-04-13/chatterbox_full_output`

Summary:

- Runs: `10`
- Errors: `0`
- Mean total: `2034.9 ms`
- Mean audio duration: `4.37 s`
- Mean RTF: `0.47`
- Min total: `1225 ms`
- Max total: `2793 ms`

Interpretation:

- Faster than real time on this setup.
- Clean full-pass result after the CUDA library and `torchvision` fixes.

### High-level comparison

On this first direct-package bakeoff:

- **Chatterbox** is the better runtime result
- **Qwen3-TTS** is the model that still needs tuning

This is the opposite of the expected latency ordering from the research doc,
which is a strong signal that benchmarking the official package alone is not
enough to reproduce the advertised Qwen latency path yet.

---

## Pulled Artifacts

Local output directory:

- `benchmark/vast_4090_2026-04-13/`

Contents:

- `qwen_full_output/results.jsonl`
- `qwen_full_output/qwen3-tts/qwen3-tts__01.wav` through `__10.wav`
- `chatterbox_full_output/results.jsonl`
- `chatterbox_full_output/chatterbox/chatterbox__01.wav` through `__10.wav`

These files are ready for listening review and sharing with the friend.

---

## Important Caveats

1. Qwen is not yet hitting the researched latency profile on this machine.
2. The current comparison is a **direct package benchmark**, not the production
   FastAPI wrapper path.
3. Chatterbox required several env/runtime fixes before it became stable.
4. Hugging Face downloads were performed without an authenticated `HF_TOKEN`,
   so rate limits could be worse on repeated fresh machines.

---

## What This Means For The Repo

The remote benchmark advanced the decision-making more than the app code.

Current repo direction:

- Research + benchmark point to **Qwen3-TTS + Chatterbox**
- Fish has been removed from the scaffold
- Both model wrappers are now implemented in the repo
- The app-level serving path still needs a fresh GPU smoke test

Files that were aligned after this benchmark:

- `app/config.py`
- `app/models/__init__.py`
- `app/models/chatterbox_tts.py`
- `README.md`
- `app/models/README.md`

Most important technical finding:

- `qwen-tts` and `chatterbox-tts` currently conflict at the dependency level,
  especially around `transformers` and related torch stack expectations.
- The clean remote benchmark path used **two isolated virtualenvs**.
- The repo has now adopted **split per-model runtimes** as the implementation
  direction.

---

## Next Recommended Steps

1. Listen to the pulled WAVs in `benchmark/vast_4090_2026-04-13/`.
2. Build either `tts-api-qwen` or `tts-api-chatterbox` on GPU.
3. Smoke-test `/v1/audio/speech` and `WS /v1/audio/stream`.
4. Send the active base URL to the friend for subjective judgment.
3. Investigate Qwen's slow path on this box:
   - confirm official recommended runtime flags
   - compare package path vs repo path
   - check whether a streaming/community path reproduces the advertised numbers
4. Finish the real Chatterbox serving path in the FastAPI app.
5. Shut down instance `34883373` when done to stop the hourly charge.

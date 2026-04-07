# Azure GPU VM Setup — TTS API

**Goal:** Provision a single GPU VM in **Azure East US** (`eastus`) that hosts this TTS API, loads both models into VRAM, and exposes `:8000` to the friend's voice agent infrastructure — also in `eastus` — with minimal latency.

**Audience:** Najeeb (provisioning), and Claude Code (for SSH-based configuration once the VM exists).

**Last updated:** April 2026. Uses `az` CLI v2.60+, Ubuntu 22.04 LTS, CUDA 12.1.

---

## Quick reference — values you'll set once

```bash
# Names / region
export RG=tts-api-rg
export LOCATION=eastus
export VM_NAME=tts-api-vm
export NSG_NAME=tts-api-nsg
export VNET_NAME=tts-api-vnet
export SUBNET_NAME=tts-api-subnet

# VM size — see "Which VM SKU?" below
export VM_SIZE=Standard_NC8ads_A10_v4     # preferred: 1x A10 24GB
# Fallback if quota is unavailable in eastus:
# export VM_SIZE=Standard_NC4as_T4_v3      # 1x T4 16GB, cheaper, fits Fish but tight for both models

# Admin + SSH
export ADMIN_USER=azureuser
export SSH_PUB_KEY=~/.ssh/id_ed25519.pub   # the key you used for GitHub earlier
```

---

## Step 0 — Prerequisites on your MacBook

```bash
# Install Azure CLI if you don't have it
brew install azure-cli

# Log in to your Azure account (browser flow)
az login

# Confirm subscription. If you have multiple, pick the right one.
az account show
# az account set --subscription "<subscription-id-or-name>"
```

### Quota check — do this before everything else

The `NCads_A10_v4` family needs its own vCPU quota in `eastus`. Many new subscriptions start with 0. Check and request ahead of time:

```bash
# List your current GPU quotas in eastus
az vm list-usage --location eastus \
  --query "[?contains(name.value, 'NCAD') || contains(name.value, 'StandardNCadsA10v4')]" \
  --output table
```

If the current value is 0 or below what you need (NC8ads_A10_v4 needs **8 vCPUs**), file a quota request:

1. Azure Portal → **Quotas** → **Compute**
2. Filter: Provider = `Microsoft.Compute`, Location = `East US`, Family = `Standard NCADSA10v4 Family vCPUs`
3. Click **Request quota increase**, set new limit to at least 8 (or 16 if you're planning 2× A10s in the future).
4. Requests on a pay-as-you-go subscription typically approve within minutes to hours. Free/trial accounts may be blocked from GPU SKUs entirely.

> ⚠️ **Important:** Azure is currently prioritizing new capacity on the `NCads_H100_v5` series. If `NC8ads_A10_v4` isn't provisionable in `eastus` on your subscription, see the "VM SKU alternatives" section at the end.

---

## Step 1 — Pick the VM SKU

### Preferred: `Standard_NC8ads_A10_v4`

| Attribute | Value |
|---|---|
| GPU | 1× NVIDIA A10 (24 GB VRAM) |
| vCPUs | 8 |
| RAM | 110 GiB |
| Temp disk | ~350 GB NVMe |
| Price (pay-as-you-go) | ~$1.43 / hour ≈ $1,050 / mo always-on |
| Spot price | ~$0.26 / hour ≈ $190 / mo (subject to eviction) |

**Why A10:** Both Qwen3-TTS (~8 GB) and Fish Speech S1-mini (~4 GB) fit in 24 GB with plenty of headroom for KV cache, activations, and a third model later. Load both at startup — the plan bans lazy loading.

### Fallback: `Standard_NC4as_T4_v3`

| Attribute | Value |
|---|---|
| GPU | 1× NVIDIA T4 (16 GB VRAM) |
| vCPUs | 4 |
| RAM | 28 GiB |
| Price | ~$0.52 / hour ≈ $380 / mo |

Cheaper, but 16 GB is tight for both models loaded simultaneously. If we go this route, start with **Fish Speech only** (fits in 4 GB) and add Qwen once we confirm it fits.

### Cost-optimized later: 2× A10 behind a load balancer

Per `documentation/TTS_MODELS_RESEARCH.md`, one A10 handles ~20–30M chars/month. Once we cross 30M, provision a second A10 and put both behind an Azure Load Balancer with session affinity for WebSocket. Don't do this in Phase 1 — a single VM is simpler and the friend's current volume is well under 30M.

---

## Step 2 — Create the resource group + network

```bash
# Resource group
az group create --name "$RG" --location "$LOCATION"

# Virtual network + subnet
az network vnet create \
  --resource-group "$RG" \
  --name "$VNET_NAME" \
  --address-prefix 10.0.0.0/16 \
  --subnet-name "$SUBNET_NAME" \
  --subnet-prefix 10.0.0.0/24

# Network Security Group with two rules:
#   - SSH (22) from your current IP only
#   - HTTP (8000) from the friend's VNET address space (adjust CIDR below)
az network nsg create --resource-group "$RG" --name "$NSG_NAME"

# Allow SSH from your current public IP
MY_IP=$(curl -s ifconfig.me)
az network nsg rule create \
  --resource-group "$RG" --nsg-name "$NSG_NAME" \
  --name allow-ssh-from-me \
  --priority 1000 \
  --source-address-prefixes "${MY_IP}/32" \
  --destination-port-ranges 22 \
  --access Allow --protocol Tcp

# Allow the API port.
# TODO: replace 0.0.0.0/0 with the friend's Azure VNET CIDR once we know it.
# For development we start open, then tighten. Don't leave this open in prod.
az network nsg rule create \
  --resource-group "$RG" --nsg-name "$NSG_NAME" \
  --name allow-tts-api \
  --priority 1010 \
  --source-address-prefixes "0.0.0.0/0" \
  --destination-port-ranges 8000 \
  --access Allow --protocol Tcp
```

> **Security note:** The NSG rule for port 8000 starts open (`0.0.0.0/0`) so you can test from your MacBook. **Before the friend sends real traffic**, tighten it to their VNET CIDR. Auth is enforced by `X-API-Key`, but network-level scoping is still the right default.

---

## Step 3 — Create the VM

```bash
az vm create \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --location "$LOCATION" \
  --size "$VM_SIZE" \
  --image Canonical:ubuntu-24_04-lts:server:latest \
  --admin-username "$ADMIN_USER" \
  --ssh-key-values "$SSH_PUB_KEY" \
  --vnet-name "$VNET_NAME" \
  --subnet "$SUBNET_NAME" \
  --nsg "$NSG_NAME" \
  --public-ip-sku Standard \
  --os-disk-size-gb 128 \
  --storage-sku Premium_LRS
```

> **Image note:** If `ubuntu-24_04-lts` isn't available, fall back to `Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest` (Ubuntu 22.04 LTS). The plan PDF assumes 22.04; both work with CUDA 12.1 via the extension below.

Grab the public IP:

```bash
export VM_IP=$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)
echo "VM IP: $VM_IP"
```

---

## Step 4 — Install NVIDIA drivers (the hard part)

There are **two paths**; use path A first, fall back to B if the extension fails. The plan PDF's "Azure marketplace images with drivers pre-installed" path is path C and is also listed.

### Path A — NVIDIA GPU Driver Extension (recommended)

This installs and persists the right CUDA-compatible driver across kernel updates and reboots.

```bash
az vm extension set \
  --resource-group "$RG" \
  --vm-name "$VM_NAME" \
  --name NvidiaGpuDriverLinux \
  --publisher Microsoft.HpcCompute \
  --version 1.10 \
  --settings '{"updateOS": true}'
```

Wait ~5–10 minutes. Then SSH in and verify:

```bash
ssh -i ~/.ssh/id_ed25519 ${ADMIN_USER}@${VM_IP}
nvidia-smi
# Should show the A10 with the CUDA version in the top-right header.
```

> ⚠️ **Known issue (April 2026):** The extension has shipped the GRID 17.5 driver by default on A10, which breaks CUDA. If `nvidia-smi` shows no CUDA version or `import torch; torch.cuda.is_available()` returns False inside the container, force an older driver version:
> ```bash
> az vm extension set \
>   --resource-group "$RG" --vm-name "$VM_NAME" \
>   --name NvidiaGpuDriverLinux --publisher Microsoft.HpcCompute \
>   --version 1.10 \
>   --settings '{"updateOS": true, "driverVersion": "535.161.08"}'
> ```

### Path B — Manual install (fallback)

If Path A is giving you trouble:

```bash
ssh -i ~/.ssh/id_ed25519 ${ADMIN_USER}@${VM_IP}

sudo apt-get update
sudo apt-get install -y build-essential linux-headers-$(uname -r)

# Add NVIDIA's apt repo
distribution=$(. /etc/os-release; echo ${ID}${VERSION_ID})
wget https://developer.download.nvidia.com/compute/cuda/repos/${distribution//./}/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update

# Install the driver only (CUDA runtime comes from the Docker image)
sudo apt-get install -y cuda-drivers-535
sudo reboot
```

After reboot, re-SSH and run `nvidia-smi`.

### Path C — NVIDIA GPU-Optimized VMI from Azure Marketplace

Easiest path if available: pick the NVIDIA GPU-Optimized VMI image when creating the VM. It ships with Ubuntu 22.04, NVIDIA driver, Docker, and the NVIDIA Container Toolkit already installed, so you can skip Step 4 and Step 5 entirely. The downside is the image is maintained by NVIDIA, not you, so patching cadence is out of your hands.

```bash
# Replace the --image line in Step 3 with:
--image "nvidia:nvidia_gpu_optimized_vmi:a10:latest"
# (exact publisher/offer/sku changes over time — run `az vm image list --publisher nvidia --all` to confirm)
```

---

## Step 5 — Install Docker + NVIDIA Container Toolkit

Skip this step entirely if you used Path C (NVIDIA VMI).

```bash
ssh -i ~/.ssh/id_ed25519 ${ADMIN_USER}@${VM_IP}

# --- Docker CE via Docker's official convenience script ---
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Log out + back in (or `newgrp docker`) for the group change to take effect.

# --- NVIDIA Container Toolkit ---
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Smoke test: should print the GPU info.
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

If that last command prints the A10 details, you're done with the OS-level setup.

---

## Step 6 — Clone this repo + boot the API

```bash
# Still SSHed into the VM
sudo apt-get install -y git
git clone https://github.com/abdulnajeeb3/tts-api-malik.git
cd tts-api-malik

cp .env.example .env
# Edit .env:
#   - API_KEYS=<pick something real>
#   - USE_MOCK_MODELS=0
#   - confirm ENABLED_MODELS=qwen3-tts,fish-s1-mini
nano .env

# Build + run
docker compose up -d --build

# Tail the logs during first boot — models will download to /models_cache
docker compose logs -f tts-api
```

First boot is slow: the models download several GB into the persistent `models_cache` volume. After the first boot, restarts are fast because the cache is preserved.

Verify the API is up:

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","models_loaded":[...],"gpu_memory_used_gb":...}
```

From your laptop:

```bash
curl http://${VM_IP}:8000/health
```

---

## Step 7 — Let Claude Code SSH in

Once the VM is running, share **three things** with Claude Code in a new message:

1. **The VM IP:**
   ```
   VM_IP=<the public IP from Step 3>
   ```
2. **The SSH key paths** (they already exist on your MacBook from the GitHub setup — just confirm):
   ```
   Private key: ~/.ssh/id_ed25519
   Public key: ~/.ssh/id_ed25519.pub
   Username: azureuser
   ```
3. **The admin API key** you set in `.env` (so Claude Code can hit the endpoints to test).

With those three things, Claude Code can:
- SSH into the VM: `ssh -i ~/.ssh/id_ed25519 azureuser@$VM_IP`
- Iterate on the model wrappers in-place
- Run the benchmark script against the real models
- Tail logs, check GPU memory, debug failures
- Commit + push updates from the VM back to GitHub

Optional but helpful: add an SSH config entry on your MacBook so `ssh tts-vm` just works.

```bash
# ~/.ssh/config on your MacBook
Host tts-vm
  HostName <VM_IP>
  User azureuser
  IdentityFile ~/.ssh/id_ed25519
  ServerAliveInterval 60
```

---

## Step 8 — Ongoing operations

### Stop / start to save money while you're not testing

```bash
# Deallocate (stops billing for VM compute, keeps disk)
az vm deallocate --resource-group "$RG" --name "$VM_NAME"

# Start it again
az vm start --resource-group "$RG" --name "$VM_NAME"

# IMPORTANT: the public IP changes on deallocation unless you allocated a
# static public IP. If you want a stable IP, convert the public IP to Static
# during Step 3 with:  az network public-ip update --name ... --allocation-method Static
```

### Monitor GPU usage

```bash
ssh tts-vm 'watch -n 1 nvidia-smi'
```

### Restart the API after code changes

```bash
ssh tts-vm
cd tts-api-malik
git pull
docker compose up -d --build
docker compose logs -f tts-api
```

### Tear down completely

```bash
# Deletes the resource group and everything in it. Irreversible.
az group delete --name "$RG" --yes --no-wait
```

---

## VM SKU alternatives (if A10 isn't available)

If you hit "SKU not available in this region / subscription" on `NC8ads_A10_v4`:

1. **Try `NC4ads_A10_v4`** (quarter of an A10, 6 GB VRAM). Not enough for both models but works for benchmarking Fish Speech alone.
2. **Try `NC6s_v3`** (1× V100 16 GB, older but widely available). V100 is CUDA-compatible with everything in this project.
3. **Try `NC8ads_H100_v5`** (newer, Azure is prioritizing this family for new capacity). More expensive but more future-proof.
4. **Try a different region:** `eastus2`, `southcentralus`, or `westus3` often have A10 quota when `eastus` doesn't. **Only** do this if we've already confirmed with the friend that a cross-region hop adds acceptable latency. Most likely answer: no, stay in `eastus`, eat the quota request delay.

List what's actually available to your subscription in `eastus`:

```bash
az vm list-sizes --location eastus --output table | grep -i -E "NC.*A10|NC.*H100|NC.*v3"
```

---

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| `az vm create` errors "SKU not available" | No A10 capacity in `eastus` for your sub | Request quota / try alternative SKU (section above) |
| `nvidia-smi` shows no GPU | Driver extension hasn't finished or installed GRID instead of CUDA | Wait 5 more min; then pin `driverVersion` in the extension settings |
| `docker run --gpus all ...` fails | NVIDIA Container Toolkit not installed or Docker not restarted | Re-run Step 5 and `sudo systemctl restart docker` |
| `/health` returns `"status": "starting"` forever | Models still downloading on first boot | `docker compose logs -f tts-api` — watch progress; first pull is big |
| `/health` works locally but not from laptop | NSG rule for 8000 wrong or your public IP not in rule | Re-check `az network nsg rule list` |
| High TTFA from laptop but low inside VM | Network RTT; expected | Move client into `eastus` for real tests (the friend's infra is already there) |

---

## Sources

- [NC family VM size series — Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nc-family)
- [NVIDIA GPU Driver Extension for Linux — Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/hpccompute-gpu-linux)
- [Azure N-series GPU driver setup for Linux — Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/n-series-driver-setup)
- [Installing the NVIDIA Container Toolkit — NVIDIA docs](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [Create SSH keys with the Azure CLI — Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-machines/ssh-keys-azure-cli)
- [Increase regional vCPU quotas — Microsoft Learn](https://learn.microsoft.com/en-us/azure/quotas/regional-quota-requests)
- [NC8ads A10 v4 pricing and specs — Vantage](https://instances.vantage.sh/azure/vm/nc8ads-v4)
- [NGC on Azure Virtual Machines — NVIDIA docs](https://docs.nvidia.com/ngc/ngc-deploy-public-cloud/pdf/ngc-azure.pdf)

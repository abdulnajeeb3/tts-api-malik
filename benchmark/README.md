# `benchmark/` — model comparison harnesses

This folder now has **two** benchmark layers:

1. **App-level benchmark**
   Uses the FastAPI server's REST endpoint.
2. **Direct package bakeoff**
   Runs model packages directly on a GPU machine, bypassing the API scaffold.

The second one became necessary because the app wrappers were unfinished at the
time of the first real benchmark, while we still needed a real Qwen vs
Chatterbox comparison on GPU.

---

## Files

### `test_phrases.txt`

The 10 medical booking phrases used across all benchmark work.

These are deliberately not generic demo lines. They contain:

- dates
- times
- digits and confirmation numbers
- doctor names
- addresses
- medication names
- copay amounts

This is the real domain stress test.

### `run_benchmark.py`

Benchmarks the **running API server** through `POST /v1/audio/speech`.

Use this once:

- real inference is wired into the app
- the server is serving real audio instead of mock placeholders

Today, this harness is structurally useful for end-to-end validation of each
service after the wrapper implementation work.

### `direct_model_bakeoff.py`

Benchmarks model packages **directly** on a GPU box.

Current purpose:

- compare Qwen3-TTS vs Chatterbox independently of the FastAPI process
- save per-phrase WAVs
- log per-run JSONL results

This is the benchmark that produced the first real Vast.ai comparison.

### `vast_4090_2026-04-13/`

Pulled outputs from the first successful remote benchmark run on a Vast.ai
RTX 4090.

Contains:

- `qwen_full_output/`
- `chatterbox_full_output/`

Each contains:

- `results.jsonl`
- 10 per-phrase WAV files

---

## Current Benchmark Truth

The current real benchmark result is the Vast direct-package bakeoff, not the
API-level benchmark.

Summary from `benchmark/vast_4090_2026-04-13/`:

| Model | Runs | Mean total | Mean audio | Mean RTF |
|---|---:|---:|---:|---:|
| Qwen3-TTS | 10 | 6478 ms | 4.95 s | 1.31 |
| Chatterbox | 10 | 2035 ms | 4.37 s | 0.47 |

Interpretation:

- Chatterbox was faster on this first direct-package run.
- Qwen worked, but is still not hitting the expected fast path on this stack.

For the full setup and caveats, read:

- [documentation/VAST_BENCHMARK_STATUS.md](../documentation/VAST_BENCHMARK_STATUS.md)

---

## Running The App-Level Benchmark

Use this when the FastAPI server is running and real model inference is
implemented:

```bash
python -m benchmark.run_benchmark \
  --base-url http://localhost:8000 \
  --api-key dev-local-key-change-me \
  --output-dir benchmark/output
```

Only test one model:

```bash
python -m benchmark.run_benchmark --models qwen3-tts
```

Important:

- This benchmark reflects the app's configured model names.
- Each runtime should be tested against its own base URL.
- The direct bakeoff is still the most recently validated real benchmark.

---

## Running The Direct Package Bakeoff

Typical pattern:

```bash
python -m benchmark.direct_model_bakeoff \
  --phrases-file benchmark/test_phrases.txt \
  --output-dir benchmark/direct_output
```

The actual remote Vast run used isolated environments for Qwen and Chatterbox
because their Python dependency stacks conflicted.

That conflict is one of the most important findings from the benchmark work.

---

## Reading The Output

Look at:

- errors
- total time
- audio duration
- RTF
- the WAVs themselves

Rules of thumb:

- `RTF < 1.0` means faster than real time
- `RTF > 1.0` means too slow for clean real-time streaming
- the WAVs matter more than timing alone

If names, numbers, dates, or medical terms sound wrong, the model is not good
enough even if the latency is strong.

---

## What This Folder Is Missing

- ElevenLabs-style compatibility benchmarks
- true HTTP streaming benchmark
- concurrency/load benchmark
- automated listening-quality scoring

Those are still future work.

# `benchmark/` — A/B test both TTS models

Before anyone (including the friend) hears audio from this API, we run both models head-to-head on the same phrases, log the timings, and save the audio for a manual listening pass. This folder holds that harness.

---

## Files

### `test_phrases.txt` — the 10 medical booking phrases
Plain text, one phrase per line. These come from the plan PDF and represent the actual domain — appointment confirmations, availability offers, confirmation numbers with spelled-out digits, dollar amounts, medication names, addresses, time/date formats. Voice agents fail in weird ways on exactly these patterns (especially numbers and proper names), so this is a realistic stress test, not just Lorem Ipsum.

### `run_benchmark.py` — the runner
Hits the REST endpoint once per phrase per model, then prints a summary table. Key behaviors:

- **REST, not WebSocket.** Easier to script and the latency comparison is still meaningful. Streaming TTFA is validated separately in Phase 3/4.
- **Server-reported TTFA.** We prefer the `X-TTFA-Ms` header over the client-observed roundtrip so network RTT doesn't pollute the measurement.
- **Saves WAV to `output/`.** Every synthesis is written to `benchmark/output/<model>__NN.wav` so you can listen by ear. Voice quality is the number the plan says to obsess over.
- **Computes RTF.** Real-time factor = `total_time / audio_duration`. RTF < 1.0 means the model is faster than real time (required for streaming). RTF > 1.0 means it can't keep up and streaming will stutter.
- **Raw JSONL dump.** All per-run results are written to `output/results.jsonl` so you can re-analyze later without re-running the benchmark.

---

## Running it

From the repo root, with the server running and both models loaded:

```bash
python -m benchmark.run_benchmark \
  --base-url http://localhost:8000 \
  --api-key dev-local-key-change-me \
  --output-dir benchmark/output
```

On the Azure VM inside the container:

```bash
docker compose exec tts-api \
  python -m benchmark.run_benchmark --base-url http://localhost:8000
```

Only test one model:

```bash
python -m benchmark.run_benchmark --models qwen3-tts
```

---

## Reading the output

The summary table looks roughly like:

```
Model          Runs  Errors  Mean TTFA  Mean total  Mean audio  Mean RTF
qwen3-tts      10    0       95 ms      480 ms       3.8 s       0.13
fish-s1-mini   10    0       180 ms     620 ms       3.9 s       0.16
```

What to look for:
- **Mean TTFA** — plan target is <200ms. Anything over 250ms in this benchmark is a problem.
- **Mean RTF** — must be well under 1.0 for streaming to work. 0.1–0.3 is healthy on an A10.
- **Errors** — any non-zero means the server returned a non-200 for at least one request. Check the error column in the raw JSONL for the message.
- **Listen to the WAVs.** Numbers wrong? Proper names butchered? That's a model quality issue you can't catch from timings alone.

---

## What's _not_ in this benchmark (yet)

- **Streaming TTFA.** REST synth-then-return is not the same as WebSocket streaming. Phase 3 adds a dedicated streaming benchmark.
- **Concurrent load.** Phase 4 adds a 5-connection concurrency test to measure degradation under load.
- **Quality scoring.** We just save WAVs for manual review. Automated MOS scoring is out of scope for v1.

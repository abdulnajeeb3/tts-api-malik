# Open-Source TTS Model Research

**Last updated:** April 2026
**Scope:** Pick candidate models for a production TTS API replacing ElevenLabs for a medical booking voice agent, with a target scale of **~50M characters / month** and **sub-200ms TTFA** on streaming.

The build plan already commits to benchmarking **Qwen3-TTS** and **Fish Speech S1-mini**. This document is the wider field survey — what else exists in April 2026, how the candidates compare, and which ones we should add to the benchmark shortlist if the first two don't pan out.

---

## TL;DR — shortlist for our use case

| Model | License | Streaming TTFA | Quality (vs ElevenLabs) | Voice cloning | Our take |
|---|---|---|---|---|---|
| **Qwen3-TTS** | Apache 2.0 | ~97 ms (best OSS) | good, multilingual | yes | **Primary candidate (in plan).** Lowest latency in open source. |
| **Fish Speech S1 / 1.5** | Apache 2.0 | ~200 ms | best quality OSS in TTS Arena (ELO ~1339) | yes, zero-shot | **Primary candidate (in plan).** Best quality backup if Qwen latency doesn't materialize. |
| **CosyVoice2-0.5B** | Apache 2.0 | **150 ms (native streaming, 25 Hz)** | high, multilingual, emotion control | yes | **Strong add.** Native streaming + small model + explicit 150 ms target in the paper. Should be our third benchmark. |
| **Chatterbox (Resemble AI)** | **MIT** | faster-than-realtime | **~63.75% preferred over ElevenLabs** in blind tests | yes, zero-shot | **Strong add.** MIT license is the loosest in the field, and the quality number is the best OSS-vs-ElevenLabs result we found. |
| **Voxtral TTS (Mistral)** | open-weights | unclear streaming support | **~62–68% preferred over ElevenLabs Flash v2.5** | yes, 3-sec clone | Worth watching. Large model (4B); throughput per GPU may be worse. |
| **Kokoro-82M** | Apache 2.0 | ~300 ms (non-streaming) | 4.2 MOS, comparable to much bigger models | limited (embedding combo, not true clone) | **Cost play.** Tiny model, 96× realtime on a basic GPU — useful if we later want a cheap fallback tier. |
| **F5-TTS** | — | moderate | 4.1 MOS, zero-shot clone | yes | Skippable — slower than XTTS, no big quality edge over Fish. |
| **XTTS v2** | Coqui Public | moderate | 4.0 MOS | yes | Skippable for v1; losing ground to Fish/CosyVoice2. |

**Recommendation:** Add **CosyVoice2-0.5B** and **Chatterbox** to the benchmark as a third and fourth candidate alongside Qwen3-TTS and Fish S1-mini. They're cheap to add (one wrapper file each) and cover the two quality-risk scenarios: (a) Qwen latency isn't actually 97 ms on our hardware, (b) Fish quality isn't close enough to ElevenLabs.

---

## Ranking context: TTS Arena v2 (HuggingFace, April 2026)

The current TTS Arena v2 leaderboard is dominated by proprietary models. Top 10 (Elo):

1. Vocu V3.0 — 1583
2. Inworld TTS — 1577
3. Inworld TTS MAX — 1575
4. CastleFlow v1.0 — 1574
5. Hume Octave — 1565
6. Papla P1 — 1561
7. MiniMax Speech-02-HD — 1544
8. Eleven Turbo v2.5 — 1543
9. Eleven Flash v2.5 — 1541
10. MiniMax Speech-02-Turbo — 1538

Fish Speech V1.5 reports an ELO of ~1339 — ~200 points below Eleven Turbo. Open source has closed most but not all of the gap against ElevenLabs. **Blind preference studies** (Chatterbox ~64%, Voxtral ~63–68% over Eleven Flash v2.5) tell a more optimistic story than pure Elo rankings, likely because Elo aggregates over many users with different listening contexts.

**Takeaway:** Set the friend's expectation that open-source is 90–95% of ElevenLabs quality. Run a blind A/B with the friend on actual medical booking phrases before committing.

---

## Candidate deep dives

### 1. Qwen3-TTS (plan's #1 pick)
- **Source:** `QwenLM/Qwen3-TTS` on HuggingFace.
- **License:** Apache 2.0.
- **Latency:** 97 ms TTFA claimed — the lowest in open source we found.
- **Parameters:** Large (not officially disclosed, but "large" in the plan PDF; likely multi-billion).
- **VRAM:** ~8 GB.
- **Strengths:** Latency-first design from Alibaba; multilingual; voice cloning.
- **Risks:** New (April 2026), limited community tooling, 97 ms claim needs validation on our hardware.
- **Verdict:** Keep as primary streaming candidate.

### 2. Fish Speech S1-mini / v1.5 (plan's #2 pick)
- **Source:** `fishaudio/fish-speech` on GitHub; `fishaudio/fish-speech-1.5` on HuggingFace.
- **License:** Apache 2.0.
- **Latency:** ~200 ms.
- **Parameters:** 500M (distilled from the parent S1).
- **VRAM:** ~4 GB.
- **Strengths:** Best open-source quality in TTS Arena (ELO ~1339), WER 3.5% / CER 1.2% on English, zero-shot voice cloning, 13 languages, **mature Python package (`fish-speech`) with existing server code we can learn from**, native WebSocket streaming.
- **Risks:** Parent S1 is the quality leader — "mini" gives up some quality in the distillation.
- **Verdict:** Keep as primary quality candidate.

### 3. CosyVoice2-0.5B (Alibaba FunAudioLLM) — **recommend adding**
- **Source:** `FunAudioLLM/CosyVoice2-0.5B` on HuggingFace; `FunAudioLLM/CosyVoice` on GitHub.
- **License:** Apache 2.0.
- **Latency:** **150 ms in streaming mode at 25 Hz sampling.** Native text-in / audio-out streaming.
- **Parameters:** 0.5B.
- **Strengths:** 30–50% pronunciation error reduction over v1, MOS 5.53, fine-grained control over emotion / dialect / speed / volume. **4× speedup with TensorRT-LLM.** Explicit Chinese Pinyin + English CMU phoneme pronunciation inpainting.
- **Risks:** Alibaba-centric community; English-quality vs Fish 1.5 needs direct A/B.
- **Why add it:** If Qwen3-TTS's 97 ms claim doesn't survive our benchmark, CosyVoice2 is our backup with native low-latency streaming. Adding a wrapper is one file (~100 lines) and it shares Apache 2.0 + HuggingFace loading with the existing models.

### 4. Chatterbox (Resemble AI) — **recommend adding**
- **License:** **MIT** — most permissive in the field.
- **Parameters:** 350M (Chatterbox-Turbo variant).
- **Latency:** Faster than realtime; exact TTFA not documented but the devnen/Chatterbox-TTS-Server project exists with an OpenAI-compatible wrapper (reference implementation we can learn from).
- **Quality:** **63.75% preference over ElevenLabs** in blind tests (Podonos, 7–20s clips). This is the best open-source-vs-ElevenLabs preference number we found.
- **Features:** Zero-shot voice cloning, first OSS model with **emotion exaggeration control** (single parameter).
- **Risks:** Published benchmark methodology is sparse; we should reproduce the blind A/B before trusting the 63.75% figure.
- **Why add it:** MIT license + best-published ElevenLabs preference number + existing OSS server code to reference. Low cost to add, high upside if quality holds up on medical phrases.

### 5. Voxtral TTS (Mistral) — watch-list
- **Parameters:** 4B (big for a TTS model).
- **Quality:** 62.8% preferred over Eleven Flash v2.5 in blind human eval (one source reports up to 68.4%).
- **Voice cloning:** 3-second clone — fastest in the field.
- **License:** Open-weights (check exact terms before shipping commercially).
- **Risks:** 4B params → higher VRAM, lower throughput/GPU, slower streaming. Unclear whether Mistral has published a streaming-optimized inference path.
- **Verdict:** Watch-list. Revisit once we know our actual throughput numbers from Phase 4.

### 6. Kokoro-82M — cost/fallback tier
- **License:** Apache 2.0.
- **Parameters:** 82M. StyleTTS2 architecture.
- **Quality:** 4.2 MOS, outperforms models 14× its size. English, French, Korean, Japanese, Mandarin.
- **Throughput:** **96× realtime on a basic cloud GPU.** Market rate under $1 per 1M characters / $0.06 per hour of audio output (reference: April 2025 pricing).
- **Voice cloning:** Limited — combines existing voice embeddings rather than cloning a new speaker from a reference clip.
- **Verdict:** Not a primary candidate because it lacks true zero-shot cloning, but it's an obvious **fallback tier** if we ever need a cheap, high-throughput model (e.g. routing low-priority or high-volume non-interactive use cases through a Kokoro instance to save GPU hours).

### Also tested, not recommended
- **F5-TTS** — MOS 4.1, flow-matching, zero-shot cloning. But "around 50% slower than XTTS in the generation process using CUDA." Fish Speech dominates it on speed+quality.
- **XTTS v2 (Coqui)** — MOS 4.0, mature voice cloning. Losing ground to Fish/CosyVoice2. Coqui's corporate pivot left the license situation murky.
- **Parler-TTS** — MOS 3.8, most controllable via text prompts but quality isn't competitive at our target.
- **MeloTTS / Piper** — extremely fast, CPU-friendly, but quality gap vs ElevenLabs is too wide for a medical customer-facing use case.

---

## Scale math: does 50M characters/month fit on our plan?

Rough conversion (TTS is usually billed per character, not per token):

```
50M chars / month
÷ 30 days           = 1.67M chars/day
÷ 86,400 seconds    = ~19 chars/second (mean sustained load)
```

At ~15 chars/word and ~150 wpm natural speech, 50M chars/month ≈ **370 hours of audio output per month**.

### GPU throughput reality check

Field data we found:

> "A mid-range GPU instance (A10G or T4) can handle approximately **20–30 million characters per month at acceptable latency** for most production workloads." — Fish Audio high-volume blog, 2026.

**That means a single A10 is borderline / insufficient for our 50M target.** Options in increasing order of cost:

| Path | Monthly infra | Throughput headroom | Complexity |
|---|---|---|---|
| 1× A10 (plan's current default) | ~$620 | handles 20–30M chars safely | low — already in the plan |
| 2× A10 behind a load balancer | ~$1,170 | comfortable for 50M+ | medium — need LB + session affinity for WebSocket |
| 1× A100 (80GB, `NC24ads_A100_v4`) | ~$2,500+ | comfortable for 50M+; room to run bigger models like Voxtral | high — much bigger VM, more quota friction |
| 1× H100 (`NCads_H100_v5`) | ~$3,000+ | overkill for 50M; future-proof | higher — newest SKU, different region availability |

### Cost at 50M chars/month, three strategies

| Strategy | Monthly cost | Margin if charging friend $2K |
|---|---|---|
| ElevenLabs Scale (friend's current baseline, roughly $330/M chars) | ~$16,500 | — |
| Voxtral API (~$16/M chars) | ~$800 | — |
| Self-host on 1× A10 (our plan, may throttle at peak) | ~$620 | ~$1,380 |
| Self-host on 2× A10 (safe for 50M) | ~$1,170 | ~$830 |
| Self-host on 1× A100 | ~$2,500 | **negative** — revisit pricing to friend |

**Recommendation:**
- **Phase 1–5 stay as planned** on a single A10. The friend's current volume is ~10–15M chars/month (inferred from their $3.5–6K/month ElevenLabs bill), so one A10 is more than enough today.
- **Before hitting 30M chars/month**, provision a second A10 in the same region and put both behind an Azure Load Balancer. Plan the LB + health probe work during Phase 4 (Concurrency) so it's ready when we need it.
- **Revisit pricing with the friend** when we cross 40M chars/month — at 50M, the $2K/month charge still clears costs but margin drops. Be transparent about the cost curve, not secretive.

---

## Action items for this repo

1. **Phase 1 stays:** Validate Qwen3-TTS and Fish Speech S1-mini on the Azure VM per the plan. Listen to the WAVs, measure TTFA, confirm quality is defensible for medical booking.
2. **Add CosyVoice2 as a third wrapper** (`app/models/cosyvoice2_tts.py`) — same interface, Apache 2.0, native 150 ms streaming. This gives us a latency safety net if Qwen doesn't deliver 97 ms on our hardware.
3. **Add Chatterbox as a fourth wrapper** if we have time before Phase 6 handoff — it has the best published blind-preference-vs-ElevenLabs number and an MIT license. Reference implementation at `devnen/Chatterbox-TTS-Server` on GitHub.
4. **Plan for 2× A10** during Phase 4. Don't wait until 50M chars/month to discover we need a load balancer.
5. **Keep Kokoro in the back pocket** as a cheap fallback tier if we ever need to offload non-critical traffic.

---

## Sources

- [Best Open Source TTS Models 2026 — BentoML](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
- [Top Open-Source TTS Models — Modal Blog](https://modal.com/blog/open-source-tts)
- [Best TTS Models 2026: Open-Source vs ElevenLabs — OCDevel](https://ocdevel.com/blog/20250720-tts)
- [TTS Arena V2 Leaderboard — HuggingFace](https://tts-agi-tts-arena-v2.hf.space/leaderboard)
- [FunAudioLLM/CosyVoice2-0.5B on HuggingFace](https://huggingface.co/FunAudioLLM/CosyVoice2-0.5B)
- [FunAudioLLM/CosyVoice on GitHub](https://github.com/FunAudioLLM/CosyVoice)
- [CosyVoice2 project page](https://funaudiollm.github.io/cosyvoice2/)
- [hexgrad/Kokoro-82M on HuggingFace](https://huggingface.co/hexgrad/Kokoro-82M)
- [Kokoro-82M production deployment guide — UnfoldAI](https://medium.com/@simeon.emanuilov/kokoro-82m-building-production-ready-tts-with-82m-parameters-unfoldai-98e36ff286b9)
- [Chatterbox — Resemble AI](https://www.resemble.ai/chatterbox/)
- [Chatterbox TTS Server reference implementation — devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server)
- [Voxtral TTS vs ElevenLabs — HuggingFace Blog](https://huggingface.co/blog/azhan77168/voxtral-tts)
- [Fish Audio high-volume TTS blog (50M chars/month threshold)](https://fish.audio/blog/best-text-to-speech-api-high-volume-usage/)
- [Inferless 12-model TTS comparison](https://www.inferless.com/learn/comparing-different-text-to-speech---tts--models-part-2)
- [CodeSOTA TTS leaderboard](https://www.codesota.com/guides/tts-models)

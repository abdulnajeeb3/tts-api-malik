# Open-Source TTS Models Research (April 2026)

> Comprehensive field survey for replacing ElevenLabs with self-hosted TTS.
> Goal: match or beat ElevenLabs quality for a medical booking voice agent.

---

## TL;DR — The Top 5

| Rank | Model | Params | License | VRAM | Streaming TTFA | Beats ElevenLabs? |
|------|-------|--------|---------|------|---------------|-------------------|
| **1** | **Qwen3-TTS 1.7B** | 1.7B | Apache 2.0 | ~6 GB | **97ms** | Comparable; best latency |
| **2** | **Chatterbox** | 500M | MIT | 6-8 GB | ~472ms | **Yes** (63.75% preference) |
| **3** | **Orpheus TTS** | 150M–3B | Apache 2.0 | 2-11 GB | ~200ms | Comparable; best emotion |
| **4** | **CosyVoice 3** | 0.5B | Apache 2.0 | 8 GB | 150ms | Comparable for English |
| **5** | **Kokoro** | 82M | Apache 2.0 | 2-3 GB | <50ms | No, but 210x real-time |

**Bottom line:** Qwen3-TTS and Chatterbox are the two models most likely to satisfy the friend's quality bar. Qwen wins on latency (97ms), Chatterbox wins on proven ElevenLabs-beating quality. Both are commercially licensable. We should benchmark both.

---

## TTS Arena V2 Leaderboard (Current State)

The [TTS Arena V2](https://huggingface.co/spaces/tts-agi/tts-arena-v2) runs blind A/B tests. Current top ranks:

| Rank | Model | ELO | Type |
|------|-------|-----|------|
| 1 | Vocu V3.0 | 1581 | Proprietary |
| 2 | Inworld TTS | 1577 | Proprietary |
| 3 | CastleFlow v1.0 | 1574 | Proprietary |
| 5 | Hume Octave | 1564 | Proprietary |
| **8** | **ElevenLabs Turbo v2.5** | **1544** | **Proprietary** |
| 9 | ElevenLabs Flash v2.5 | 1540 | Proprietary |

**Open-source models on the Arena:**
- Kokoro v1.0: ~44% win rate (impressive for 82M params)
- Fish Audio S2 Pro: ELO 1128 on Artificial Analysis leaderboard

**Key insight:** Proprietary models still lead the blind Arena by ~100-200 ELO. BUT in targeted A/B tests (not the Arena), Chatterbox beats ElevenLabs 63.75% of the time, and Voxtral beats ElevenLabs Flash 62.8% of the time.

---

## Tier 1: Match or Beat ElevenLabs

### Qwen3-TTS (Alibaba) — RECOMMENDED #1

- **HuggingFace:** `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` (preset voices) or `Qwen/Qwen3-TTS-12Hz-1.7B-Base` (voice cloning)
- **Also available:** 0.6B variants for lower VRAM
- **Install:** `pip install -U qwen-tts`
- **License:** Apache 2.0
- **Languages:** 10 (EN, ZH, JA, KO, DE, FR, RU, PT, ES, IT)
- **Sample rate:** 24,000 Hz
- **VRAM:** ~6 GB (1.7B with FlashAttention), ~3 GB (0.6B)
- **Streaming:** Native, 97ms TTFA with FlashAttention
- **Voice cloning:** Yes, 3-10 sec reference audio
- **Concurrency:** 15-20 real-time sessions per RTX 4090

**Why #1 for us:**
- 97ms streaming latency is best-in-class for voice agents
- CustomVoice variant has 9 preset professional voices with instruction control ("calm, professional female voice")
- Apache 2.0 = no license risk
- Extremely low VRAM (0.6B variant at 3 GB = can pack many instances per GPU)
- `pip install` — clean dependency chain

**Code (CustomVoice):**
```python
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

wavs, sr = model.generate_custom_voice(
    text="Your appointment is confirmed for tomorrow at 3 PM.",
    language="English",
    speaker="Aiden",
    instruct="Professional and friendly tone.",
)
sf.write("output.wav", wavs[0], sr)
```

**Code (Voice Cloning):**
```python
model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base", ...
)
wavs, sr = model.generate_voice_clone(
    text="Your appointment is confirmed.",
    language="English",
    ref_audio="reference_speaker.wav",
    ref_text="Transcript of reference audio.",
)
```

**Streaming (community fork):**
```python
for chunk, chunk_sr in model.stream_generate_voice_clone(
    text="Hello, this is streaming!",
    language="English",
    voice_clone_prompt=prompt_items,
    emit_every_frames=4,        # ~0.33s per chunk
    decode_window_frames=80,
):
    # send chunk to WebSocket
    pass
```

**Risk:** Streaming not yet in official pip package ("coming soon"); available via community fork `dffdeeq/Qwen3-TTS-streaming`.

---

### Chatterbox (Resemble AI) — RECOMMENDED #2

- **HuggingFace:** `ResembleAI/chatterbox`
- **Install:** `pip install tts-chatterbox`
- **License:** MIT
- **Languages:** 23+
- **Sample rate:** 24,000 Hz
- **VRAM:** 6-8 GB (optimized ~1.5 GB)
- **Streaming:** Community fork exists (`davidbrowne17/chatterbox-streaming`)
- **Voice cloning:** Yes, 5-10 sec reference audio
- **Latency:** ~472ms first chunk on 4090; Turbo variant RTF 0.499

**Why #2:**
- **63.75% preferred over ElevenLabs in blind tests** — the strongest open-source quality claim
- MIT license — maximally permissive
- Emotion exaggeration control (unique feature)
- Neural watermarking built in
- 23 languages (widest of the top contenders)
- Variants: Original, Multilingual, Turbo

**Risk:** Real-world latency of ~472ms is above the 200ms threshold for natural conversation. Streaming via community fork, not native. Heavier GPU requirement for concurrent streams.

---

### Orpheus TTS (Canopy Labs) — RECOMMENDED #3

- **HuggingFace:** `canopylabs/orpheus-3b-0.1-ft`
- **Install:** `pip install orpheus-speech`
- **License:** Apache 2.0
- **Languages:** English primary
- **Sample rate:** 24,000 Hz
- **VRAM:** ~11 GB (3B), ~6 GB (1B), ~2 GB (150M)
- **Streaming:** Yes, ~200ms (100ms with input streaming)
- **Voice cloning:** Yes (best with 300+ samples, decent with ~50)
- **Notable:** Emotion tags: `<laugh>`, `<sigh>`, `<cough>`, etc.

**Why #3:**
- Multiple size variants (150M to 3B) — can pick quality/cost tradeoff
- Built on Llama architecture — tons of inference tooling (vLLM, etc.)
- Apache 2.0
- Emotion control via in-text tags is natural and unique

**Risk:** English-only. Voice cloning needs more reference data than Qwen/Chatterbox. 3B model is memory-hungry.

---

## Tier 2: Strong Alternatives

### CosyVoice 3 (Alibaba/FunAudioLLM)

- **HuggingFace:** `FunAudioLLM/CosyVoice2-0.5B`
- **License:** Apache 2.0
- **Languages:** Chinese + English + Japanese + Korean (+ 18 Chinese dialects in v3)
- **VRAM:** 8 GB (0.5B)
- **Streaming:** 150ms native
- **Voice cloning:** Yes, zero-shot
- **Quality:** MOS 5.53, CosyVoice 3 improves CER by 26% over v2

**Best for:** Chinese-English bilingual. Strong production track record in Chinese market. Less English-optimized than Qwen.

### Kokoro (hexgrad) — Best for High-Throughput

- **HuggingFace:** `hexgrad/Kokoro-82M`
- **Install:** `pip install kokoro>=0.9.4`
- **License:** Apache 2.0
- **VRAM:** 2-3 GB
- **Speed:** 210x real-time on GPU. RTF 0.03 on A100.
- **Concurrency:** 50+ concurrent streams per A100.

**Best for:** Bulk traffic where cost matters more than voice customization. 54 built-in voices, **no voice cloning**. Perfect for routing 85% of confirmations/greetings through a cheap fast path.

### Dia2 (Nari Labs) — Best for Dialogue

- **HuggingFace:** `nari-labs/Dia2-2B`
- **License:** Apache 2.0
- **VRAM:** ~10 GB
- **Streaming:** Native from first tokens
- **Voice cloning:** Yes, zero-shot

**Best for:** Dialogue-heavy scenarios. Non-verbal cues (laughter, sighs). English-only.

### Sesame CSM-1B — Best for Conversational AI

- **HuggingFace:** `sesame/csm-1b`
- **License:** Apache 2.0
- **VRAM:** ~4.5 GB
- **Notable:** Uses dialogue history for more natural responses. Powers viral Sesame Maya assistant.

### Pocket TTS (Kyutai) — Best for Edge/CPU

- **HuggingFace:** `kyutai/pocket-tts`
- **Params:** 100M
- **VRAM:** Zero — runs on CPU
- **Latency:** Sub-50ms, RTF 0.17 on MacBook Air M4
- **Voice cloning:** Yes

**Best for:** Edge deployment, testing without a GPU at all.

### Hume TADA

- **HuggingFace:** `HumeAI/tada-1b`
- **License:** Llama 3.2 Community License (some restrictions)
- **VRAM:** ~2.5 GB (1B)
- **Notable:** Zero hallucinations on 1000+ test samples. RTF 0.09. No voice cloning.

---

## License-Blocked Models (Non-Commercial)

These are high-quality but **cannot be self-hosted commercially**:

| Model | License | Quality | Can We Use? |
|-------|---------|---------|-------------|
| **Voxtral** (Mistral) | CC BY-NC 4.0 | 62.8% beats ElevenLabs Flash | **No** (self-hosted). API OK at $0.016/1K chars |
| **Fish Speech v1.5** | CC-BY-NC-SA (weights) | Excellent; WER 0.99% English | **No** |
| **Fish Audio S2** | Research License | Highest benchmarks overall | **No** without commercial license from Fish Audio |
| **F5-TTS** | CC-BY-NC (weights) | MOS 4.1, 7x real-time | **No** |
| **IndexTTS2** (Bilibili) | Non-commercial | Best emotion control (Chinese) | **No** |
| **MegaTTS3** (ByteDance) | Academic | Ultra-high clone quality | **Unclear** |

---

## Where ElevenLabs Still Wins

| Aspect | ElevenLabs Edge | Open-Source Gap |
|--------|----------------|----------------|
| Language breadth | 74 languages | Best open-source: 23 (Chatterbox) |
| Pre-built voices | 10,000+ | Best: 54 (Kokoro), 9 (Qwen) |
| Edge case handling | Numbers, abbreviations, medical terms | Open-source models struggle with unusual text |
| Pronunciation accuracy | 82% | ~77% typical for open-source |
| Voice consistency over long passages | Excellent | Some models degrade after 30+ seconds |
| Zero-setup ease of use | API key → done | Significant DevOps required |

## Where Open-Source Now Wins

| Aspect | Open-Source Edge |
|--------|-----------------|
| **Raw naturalness** | Chatterbox 63.75% preferred over EL in blind tests |
| **Latency** | Qwen3-TTS 97ms vs EL streaming ~200-300ms |
| **Cost at scale** | Self-hosted ~$0.002/1K chars vs EL ~$0.07/1K chars |
| **Emotion control** | Orpheus and Chatterbox Turbo have finer-grained control |
| **Voice cloning fidelity** | Fish S2 and MegaTTS3 match or exceed EL |
| **Privacy/HIPAA** | Data never leaves your infrastructure |

---

## Benchmark Plan

Models to test on the friend's voice agent use case, in priority order:

1. **Qwen3-TTS 1.7B CustomVoice** — test all 9 preset voices, measure TTFA
2. **Chatterbox** — voice-clone a professional voice, test quality vs Qwen
3. **Orpheus TTS 1B** — test emotion tags for conversational feel
4. **Kokoro 82M** — test as high-throughput fallback for simple utterances
5. **Qwen3-TTS 0.6B CustomVoice** — test if the smaller variant is "good enough" (half the VRAM)

Test phrases (medical booking context):
- "Your appointment with Doctor Smith is confirmed for Tuesday at 2:30 PM."
- "I have three available slots: Monday at 9 AM, Wednesday at 1 PM, or Friday at 4:30 PM."
- "Could you please spell your last name for me?"
- "Your insurance copay will be $35. Would you like to proceed?"
- "I'm transferring you to a specialist. Please hold for just a moment."

Record WAV files, play for the friend, get subjective feedback. Numbers don't matter — the friend's ear is the final judge.

---

## Sources

- [TTS Arena V2 Leaderboard](https://huggingface.co/spaces/tts-agi/tts-arena-v2)
- [Artificial Analysis TTS Leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard)
- [BentoML: Best Open-Source TTS Models 2026](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
- [Modal: Top Open-Source TTS Models](https://modal.com/blog/open-source-tts)
- [Inworld: Best TTS APIs for Real-Time Voice Agents 2026](https://inworld.ai/resources/best-voice-ai-tts-apis-for-real-time-voice-agents-2026-benchmarks)
- [Qwen3-TTS GitHub](https://github.com/QwenLM/Qwen3-TTS)
- [Chatterbox GitHub](https://github.com/resemble-ai/chatterbox)
- [Orpheus TTS GitHub](https://github.com/canopyai/Orpheus-TTS)
- [CosyVoice GitHub](https://github.com/FunAudioLLM/CosyVoice)
- [Kokoro HuggingFace](https://huggingface.co/hexgrad/Kokoro-82M)
- [Dia2 GitHub](https://github.com/nari-labs/dia2)
- [Sesame CSM GitHub](https://github.com/SesameAILabs/csm)
- [Pocket TTS GitHub](https://github.com/kyutai-labs/pocket-tts)
- [Hume TADA GitHub](https://github.com/HumeAI/tada)

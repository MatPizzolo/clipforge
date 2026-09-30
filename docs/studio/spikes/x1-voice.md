# X1: voice bake-off report

Date: 2026-09-30 · Spend: **$3.80 of $10** (from `modal billing`) · Status: **final**. The owner rated the samples blind, and the rules below decided.

**Question:** which TTS gives the best EN and ES narration per dollar?

## Setup
- **Scripts:** 10 original story scripts in the style of 07, about 170 words each, 55–72 s of audio. EN: molasses flood, Kodak, Antikythera, Blockbuster, 1904 marathon. ES: Lustig, Mary Celeste, Dagen H, Tunguska, Zeigarnik.
- **Voices:** Qwen3-TTS VoiceDesign designed 3 voices. Each has an EN and an ES reference clip (9.5–12 s) from the same instruct, and each clone uses the reference in its target language.
  - v1: deep male documentary narrator
  - v2: warm female storyteller
  - v3: bright young male host
- **Models:**
  - Qwen3-TTS 1.7B **Base** (clone), bf16, SDPA attention (no flash-attn).
  - Chatterbox **Multilingual** 0.1.7 (clone), default settings.
  - Kokoro-82M 0.9.4 with presets (it can't clone). Presets: v1 → `am_michael` / `em_alex`; v2 → `af_heart` / `ef_dora`; v3 → `am_puck` / `em_santa`.
- **Chunking:** scripts are split into paragraph chunks (5–7 per script), synthesized, and joined with 250 ms of silence.
- **Hardware:** Modal L4 (and Kokoro also on 4 CPU cores). L4 costs $0.000222/s, CPU $0.0000131/core-s, memory $0.00000222/GiB-s (modal.com/pricing, 2026-09-30).
- **WER:** faster-whisper large-v3-turbo on each output, compared with the script. Numbers are spelled out, and accents and punctuation are stripped.
- **Code:** a throwaway probe in `scratch/x1/` (Modal app `clipforge-x1`), deleted after the spike. The weights are on the `clipforge-models` Volume.

## Results (all 10 scripts × 3 voices per model)

| | Qwen3-TTS Base (clone) | Chatterbox Multilingual (clone) | Kokoro-82M (preset) |
|---|---|---|---|
| **Owner rating (1–5, blind): EN / ES / overall** | 4.0 / **5.0** / **4.5** | 4.5 / 3.5 / 4.0 | 4.5 / 4.0 / 4.25 |
| WER EN, mean / max | 1.0% / 2.4% | 1.2% / 2.9% | 1.0% / 2.2% |
| WER ES, mean / max | **0.6% / 3.0%** | 4.0% / **23.6%** | 0.6% / 1.8% |
| Files with a content error (dropped or invented text) | 0 / 30 unbatched; **2 / 10 batched** | **2 / 30** (both ES) | 0 / 30 |
| GPU-s per audio-s, unbatched (L4) | 2.50 | 1.05 | 0.015 (CPU, 4 cores: 0.34) |
| GPU-s per audio-s, batched | 0.68 with one script per batch (~6 chunks); 5 scripts per batch runs out of memory | no batch API | not needed |
| $ per 60 s of narration | **$0.033** unbatched (batched $0.009, not usable yet) | $0.014 | $0.0002 (CPU: $0.0013) |
| Cold start (container + imports + load, weights on Volume) | 35–40 s | 56–59 s | ~30 s (CPU: 27–35 s) |
| Peak VRAM | 4.6 GB unbatched; 8–13 GB batched | 4.7 GB | 1.0 GB |
| Voice per persona | yes (designed, then cloned) | yes (clones the same reference) | no: 3 ES voices in total, shared by every account |
| License | Apache-2.0 (code + weights) | MIT (code + weights; Perth watermark MIT; S3Tokenizer Apache-2.0) | Apache-2.0 (code, weights, misaki); **espeak-ng GPL-3.0** is a runtime dependency |

Notes:
- **Two cold-start rounds agreed** to within 5 s. The first call in a fresh container also pays for the first generation: Chatterbox took 26 s on its first sentence, against 5.6 s warm.
- **Speaking rate:** 2.6–2.9 words/s on average for all models, with every file between 2.0 and 3.3 words/s.
- **Batched Qwen** speeds up the 9 good scripts about 3.7×.

### The failures, in detail
- **Qwen batched, `en5_v2` (runaway):** one chunk never emitted its stop token. It produced 705 s of audio for a 58 s script and cost 1,930 GPU-s (about $0.43, more than the other 9 scripts together). Its first paragraph turned into noise.
- **Qwen batched, `en4_v2`:** dropped the last sentence ("In 2010, Blockbuster filed for bankruptcy. Today…").
- **Chatterbox, `es4_v2`:** invented about 40 words of Spanish-sounding babble in the second paragraph (WER 23.6%).
- **Chatterbox, `es2_v1`:** silently skipped a whole paragraph (WER 17%).
- **Qwen unbatched and Kokoro:** no content errors in 60 files.

## Recommendation (final, 2026-09-30)

**Result of the rating** (voice v2, 2 scripts per language, 30 s each):
- **Qwen** was rated best overall (4.5), and best in Spanish (5, 5).
- **Chatterbox** came in 0.5 points below Qwen. The rule needed it 0.5 points *above* to become the primary.
- **Kokoro** was second overall (4.25), and tied for best in English (4.5).

So the first rule applies: Qwen is the primary. English is the caveat: there Kokoro and Chatterbox beat Qwen by 0.5, with only 2 samples each. S6 should re-rate English on real story scripts before choosing an English-only persona voice.

**Primary: Qwen3-TTS 1.7B Base, cloning a VoiceDesign reference, run unbatched with the guard below.**
- It's the only candidate that combines a distinct designed voice per persona (07 and 06 need a voice per account), clean Spanish (0/30 content errors) and an Apache-2.0 license.
- **The runaway counts against it.** Batching is off until the guard exists and a re-test passes, so the cost is **$0.033 per 60 s** unbatched, not $0.009. At 20 accounts × 1–2 stories a day of about 75 s, that's about **$25–50 a month**. That's affordable, but it's the largest single media cost after talking heads, and it's 2.4× Chatterbox.
- The guard's WER check reuses the faster-whisper pass that makes caption word timings (03), so it adds no second transcription.
- In 03, a story video now costs about $0.09–0.13 (was $0.05–0.10), and scenario 2 comes to about $215–245 a month (was about $200).

**Fallback: Kokoro-82M**, for bulk or low-value narration and whenever Qwen fails twice on a whole item.
- It's 150× cheaper, has no content errors and fits on a CPU.
- The catch is that every account would share the same 3 Spanish and ~20 English preset voices. That runs into the sameness problem from ADR-35, so it isn't a persona voice.

**Not recommended: Chatterbox Multilingual** as the primary.
- It's half Qwen's cost and clones well. But in Spanish it made content errors in 2 of 15 files (a dropped paragraph and invented words), which a viewer would notice. It's also the slowest to cold-start.
- If the blind rating puts it clearly ahead (by 0.5 points or more), it becomes the primary with the same guard, since its failures are the same kind.

**How the rating changes this:**
- Qwen rated at least 3.5 and no more than 0.3 below the best → as above.
- Chatterbox ahead by 0.5 or more → Chatterbox primary with the guard, Qwen second.
- Kokoro rated best or tied → Kokoro for the cheap tier and Qwen for persona accounts.
- Everything under 3 → re-run with flash-attn and a different voice before S5.

## Risks
1. **Qwen runaway and truncation (seen 2 times in 10 batched scripts, 0 in 30 unbatched).** Batching or not, production needs this guard around every chunk:
   - **Output-token cap from text length:** `expected_s = words / 2.0` (slowest rate we measured, rounded down), then `max_new_tokens = ceil(1.5 × expected_s × codec_frames_per_s)`. The 12 Hz tokenizer runs at about 12.5 frames/s; read the exact value from the model config. A runaway then stops at 1.5× the expected length, instead of running to the model's limit and burning 30 minutes of GPU.
   - **Duration check:** reject a chunk whose audio falls outside 0.6–1.5 × `words / 2.7 s`. Every file we produced was within ±25% of that rate.
   - **Content check:** reject a chunk whose WER against its script text is above 15%. That catches dropped sentences and invented text that fit inside the duration window. **This must share the faster-whisper pass that already makes the caption word timings (03, "Word timing for captions")**, so production transcribes each narration once, not twice. S5/S6 build TTS guard + word timing as one step.
   - **One retry** of a rejected chunk with a new seed. If it fails again, the whole item fails and goes to review. Never splice in another model's voice mid-item.
   - Then re-test batching (one script per batch) under the guard before counting on the $0.009 rate.
2. **Qwen is slow unbatched** (RTF 2.5 with SDPA). flash-attn wasn't tested because it needs a matching wheel. It might halve the time, and S5 should try it with memory snapshots, which would also cut the 35–40 s cold start.
3. **Batch memory:** batches of about 35 chunks ran out of the L4's 22 GB. One script per batch peaked at 8–13 GB. Cap the batch by chunk count.
4. **Kokoro's espeak-ng is GPL-3.0.** Approved by the owner on 2026-09-30: GPL-3.0 tools that run only on our servers and are never distributed are allowed, and AGPL stays banned (03 allowlist, decision log #67).
5. **Chatterbox watermark:** its output always carries Resemble's Perth watermark. That's harmless for AI-disclosed accounts, but it's a vendor mark in our audio.
6. **Cross-language clones weren't tested:** each clone heard a reference in its own language. A persona speaking both EN and ES from one reference is untested.
7. **Measurement caveats:**
   - WER is only a content check. It says nothing about prosody; that's what the rating is for.
   - 10 scripts is a small sample. Chatterbox's 2 of 30 failure rate could really be anywhere from about 1% to 20%.

## Files
- **Kept, on the `clipforge-models` Volume:**
  - `refs/x1/v2_en.wav` and `refs/x1/v2_es.wav`: the v2 reference clips, the voice the blind rating used.
  - `hf/hub/`: the Qwen3-TTS Base and VoiceDesign weights, and Kokoro-82M. Chatterbox's weights were removed.
  - To clone v2, Qwen Base needs each clip **and its exact transcript** (`ref_text`):
    - VoiceDesign instruct: "Female narrator in her thirties, warm mid-range voice, clear and intimate storytelling tone, moderate pace, a slight smile in the voice." plus " Native American English speaker, neutral accent." (EN) or " Native Latin American Spanish speaker, neutral accent." (ES). Seed 7.
    - EN ref_text: "Some stories stay hidden for a hundred years. Then one small detail changes everything we thought we knew. Tonight, let's follow that detail and see where it leads."
    - ES ref_text: "Algunas historias pasan cien años escondidas. Hasta que un pequeño detalle cambia todo lo que creíamos saber. Hoy vamos a seguir ese detalle, a ver adónde nos lleva."
- **Deleted after the spike:** `scratch/x1/`, which held the probe (`probe.py`, Modal app `clipforge-x1`), the test scripts, every output, the blind samples and the answer key. All the numbers are in this report and in 03.

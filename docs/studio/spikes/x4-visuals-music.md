# X4: visuals and music spike report

Date: 2026-10-01 to 2026-10-02 · Spend: **about $5.4–5.5 of $15** (`modal billing summary`, ephemeral apps: $5.49 on one read, $5.38 after billing settled; plus ~$0.001 of Haiku) · Status: **final** (card 012, checkpoint B). The owner rated every category blind. The last sample (e2e3: captions and transitions) is waiting for its rating; it decides only the transition style, not a model.

**Question:** what do stills, 5 s b-roll and 60 s music beds cost on Modal, how fast are they, and are they good enough for the story accounts (untold.archive / historias.ocultas)?

**Answer in one line:** the models are good enough and cheap; the first end-to-end samples were poor because of **how the video was put together**, not the models. S6's producer must follow the rules in "What S6's producer must do" below, whichever model it uses.

## Setup
- **Test set:** 10 stills in the style of 07 (molasses flood, Antikythera, a ghost ship, a lost city, Tunguska, a workshop, a torn tent in the snow), the last 3 with text (an English headline, a museum label, a Spanish poster). 3 b-roll shots animated from 3 of the stills (image-to-video). 4 music moods (mystery, epic, melancholy, eerie) × 2 seeds, 60 s, instrumental. One shared style suffix; seed 42.
- **End-to-end samples:** e2e1 (a montage teaser: 3 b-roll frame rates), e2e2 (one story, the producer rules below, Qwen vs Z-Image), e2e3 (e2e2's winner with captions and transitions). All rendered locally with S4's `render.run`; narration is Kokoro `af_heart` as a placeholder for Qwen3-TTS.
- **Hardware and prices** (`modal billing rates`, 2026-10-01): L4 $0.80/h, L40S $1.95/h, H100 $3.95/h, memory $0.008/GiB-h. $ per unit = warm GPU seconds × the GPU's rate.
- **Weights:** on the `clipforge-models` Volume under `x4/` (about 264 GB, pinned revisions below). Code: a throwaway probe (Modal app `clipforge-x4`; diffusers 0.40.0, torch 2.10.0; ACE-Step 1.5 at tag `v0.1.6`).
- **Cold start** = container start (25–37 s where measured) + model load. Load times varied 2–4× between days (Volume read cache), so they are given as ranges.

## Licenses (none dropped)

| Candidate | Weights | Code | Bundled parts | Pinned revision |
|---|---|---|---|---|
| Z-Image-Turbo (`Tongyi-MAI/Z-Image-Turbo`) | Apache-2.0 | Apache-2.0 (`Tongyi-MAI/Z-Image`) | text encoder Qwen3-4B (Apache-2.0) | `f332072a` |
| Qwen-Image-2512 (`Qwen/Qwen-Image-2512`) | Apache-2.0 | Apache-2.0 (`QwenLM/Qwen-Image`) | text encoder Qwen2.5-VL-7B (Apache-2.0). **Not 2.1** (non-commercial, banned in 03) | `25468b98` |
| Qwen-Image-2512-Lightning 8-step LoRA (`lightx2v/…`) | Apache-2.0 | Apache-2.0 (`ModelTC/LightX2V`) | — | `a52649c9` |
| Wan2.2 TI2V-5B (`Wan-AI/Wan2.2-TI2V-5B-Diffusers`) | Apache-2.0 | Apache-2.0 (`Wan-Video/Wan2.2`) | umT5 text encoder, Wan VAE | `b8fff731` |
| Wan2.2 I2V-A14B (`Wan-AI/Wan2.2-I2V-A14B-Diffusers`) | Apache-2.0 | Apache-2.0 | same | `596658fd` |
| Wan2.2-Lightning I2V 4-step LoRAs (`lightx2v/Wan2.2-Lightning`, Seko-V1) | Apache-2.0 | Apache-2.0 | — | `18bccf88` |
| ACE-Step 1.5 (`ACE-Step/Ace-Step1.5`) | **MIT** | MIT (`ace-step/ACE-Step-1.5`, tag `v0.1.6`) | Qwen3-Embedding-0.6B (Apache-2.0), 5 Hz LM 1.7B. The card says it was trained on licensed, royalty-free and synthetic music, and output is for commercial use | `19671f40` |

ACE-Step **1.5** is MIT; ACE-Step v1 (3.5B) was Apache-2.0. Both are on 03's allowlist. Kijai's re-packed Wan LoRAs weren't used (unclear license); the lightx2v originals load in diffusers.

## Results by category

### Stills

| | Z-Image-Turbo, L4, FP8 storage | Z-Image-Turbo, L40S, bf16 | Qwen-Image-2512 + Lightning 8-step, L40S, FP8 storage |
|---|---|---|---|
| Size | 1088x1920 (2.1 MP), 9 steps | 1088x1920, 9 steps | 928x1664 (1.5 MP, its native 9:16), 8 steps |
| Warm s per image | 31.4 | 9.0–9.1 | **7.5–7.6** |
| **$ per image** | $0.0070 | $0.0049 | **$0.0041** |
| Model load / cold start | 58 s / ~85 s | 28–128 s / ~55–160 s | 132–317 s / ~160–350 s |
| Peak VRAM | 19.6 GB | 25.8 GB | 43.9 GB |
| Text (3 prompts) | label ✓, poster ✓, headline "MOLGAS", "FLOOD" twice | label ✓, poster ✓, headline "MOLGAS" | poster ✓, label "ANTIKYIHERA", headline "MOLOSS" |
| **Owner, blind** | **no visible difference from L40S bf16** (3 pairs) | see below | see below |

**Owner's still ratings, as given:** "A and B often came out in different styles (one more illustrated, one more photographic), so I couldn't compare them on equal terms. 03 and 04: B more realistic, A more digital. 07: the other way round." Against the key, the version the owner called more realistic was **Qwen** in all three pairs (03_B, 04_B, 07_A) and the more digital one Z-Image. **The shared style suffix did not give one consistent look across the two models.** In e2e2, where each variant used one model and one tuned photographic suffix, the owner preferred the **Qwen** variant ("B is better").

Notes:
- **L4 in FP8 loses:** 3.5× slower than L40S and 40% dearer per image, with no visible quality gain or loss. diffusers' FP8 *storage* casts each layer back to bf16, so the L4 does bf16 work on a slower card.
- **Prompt following:** Qwen drew the Tunguska radial blowdown and the flood itself; Z-Image drew a standing forest and a tanker wagon.
- **Text in images is unreliable** on uncommon words (both misspelled "MOLASSES"): headlines and labels need an OCR check against the script, or typeset text in the overlay.

### B-roll (5 s, image-to-video from a still)

| | Wan2.2 TI2V-5B, L40S | Wan2.2 I2V-A14B + lightx2v 4-step, H100 |
|---|---|---|
| Output | 704x1280, 121 frames, 24 fps | 720x1280, 81 frames, 16 fps |
| Steps | 50, CFG 5.0 | 4, no CFG |
| Warm s per clip | 436 | **82–94** |
| **$ per clip** | $0.24 | **$0.09–0.10** (+$0.02 memory while loading fp32 weights) |
| Model load / cold start | 34 s / ~70 s | 222–298 s (126 GB of fp32 weights) / ~250–330 s, about **$0.30 per batch** |
| Peak VRAM | 30.5 GB (needs VAE tiling; without it the decode ran out of 44 GB) | 69.9 GB |
| **Owner, blind** | preferred in 1 of 3 pairs | **preferred in 2 of 3 pairs** ("A looked better": A was A14B in pairs 1 and 3, 5B in pair 2) |

Notes:
- **The 4-step A14B is 2.5× cheaper per clip** than the 50-step 5B, which reverses 03's cost ordering. Its cold start only pays when a batch makes several clips.
- A14B added an unprompted person to one empty scene: producers must say "no people" for empty scenes, and the Judge (S6) should check the frames.
- **Frame rate:** the owner rated all three e2e1 variants (A14B interpolated to 30 fps, 5B at 24 fps, A14B at 16 fps) "very poor" for other reasons (below) and named no judder, so 16 fps b-roll in a 30 fps Timeline is acceptable for now. Practical-RIFE (MIT) stays the option if judder is ever flagged; ffmpeg `minterpolate` took 94 s of CPU per 5 s clip.
- An S5 server should store bf16 copies of the A14B experts (57 GB instead of 114 GB) and load them straight to the GPU, to roughly halve the load and drop the 96 GiB memory request.

### Music beds (60 s, ACE-Step 1.5 turbo on L4)

| | With "thinking" (the 5 Hz LM plans the codes) | Without thinking (DiT only) |
|---|---|---|
| Warm s per 60 s bed | 35.4 | **13.9** |
| **$ per bed** | $0.0079 | **$0.0031** |
| Model load / cold start | 88 s / ~120 s | 84 s / ~115 s |
| Peak VRAM | 13.1 GB | 13.1 GB |
| Loudness as generated | -15.0 to -21.8 LUFS | -12.5 to -18.2 LUFS |
| **Owner, blind** | "all OK as beds" | "all OK as beds" |

The owner rated all 8 beds (4 moods, both modes) acceptable, so the cheaper mode is enough. Every bed came out exactly 60.0 s, and loudness varies by up to 9 LU, so beds must be normalized before mixing (below).

### End-to-end samples

| Sample | What changed | Owner, blind |
|---|---|---|
| e2e1 (3 variants: b-roll at 16, 24 and interpolated 30 fps) | the spike's own stills, a montage narration, proportional cue timing, the bed at -4 dB | **"Very poor, all three; I wouldn't watch any of them."** The opening line ran over an unrelated image (a tent); the ship b-roll stopped at 0:17 and froze into its still until 0:22; the music was too loud and grew louder towards the middle |
| e2e2 (Qwen vs Z-Image, the same producer rules) | one story in 8 lines, one image per line, hook first, one model and one style per variant, per-line narration and exact cuts, b-roll only where the line fits the clip, the bed flattened and ~16 dB under the voice | Hook: "it is better". Images: "do not look like one video, they have the same style, but transition very poorly". B-roll cuts: "B is better than A" (B = **Qwen**). Music level: "yes" |
| e2e3 (Qwen; A = hard cuts with continued motion, B = 0.4 s crossfades) | e2e2's Qwen variant plus the clip producer's captions (key words in yellow, the hook title card) and smoother transitions | **pending** |

e2e2 cost $1.97 (8 stills on each model, 4 A14B clips, cold starts included); e2e3 cost about $0.001 (one Haiku call; everything else reused or on a CPU).

**e2e3 details.** Word timings came from faster-whisper large-v3-turbo on the narration (CPU, int8); key words from the captions stage's own `pick_keywords` (Haiku, `keywords_v2`: 18 of 84 words plus "MOLASSES" in the title "THE DAY BOSTON DROWNED IN MOLASSES"), burned in with `build_ass` through the Timeline overlay. Whisper wrote "waded **into their wastes**" for the script's "in to their waists" (corrected by hand for the sample) and split "fifteen-foot" into "15 -FOOT". That is why captions must be **snapped to the known script**, and why the script needs a display form with digits, since TTS scripts spell numbers out. The crossfade variant was composited outside the renderer (each shot rendered alone with S4, then `xfade`, then S4 again for audio and captions); b-roll shots got a 0.1–0.2 s held last frame inside the fade. Both variants render at -14.1 LUFS.

## Recommendation for S5 (models)

| Job | Primary | Fallback | GPU | $ per unit (warm) |
|---|---|---|---|---|
| Stills | **Qwen-Image-2512 + Lightning 8-step**, transformer stored in FP8, 928x1664 | Z-Image-Turbo (bf16) when its faster cold start matters or for an illustrated look; never mix the two in one video | L40S | $0.0041 per image |
| B-roll | **Wan2.2 I2V-A14B + lightx2v 4-step**, from the line's still, bf16 weights on the Volume | Wan2.2 TI2V-5B with VAE tiling | H100 (5B: L40S) | $0.09–0.10 per 5 s clip, plus ~$0.30 cold start per batch |
| Music | **ACE-Step 1.5, no thinking**, as a **bank of beds** (below) | a royalty-free library | L4 | $0.0031 per 60 s bed |
| Drop | Z-Image on L4 FP8 (slower and dearer); interpolation until judder is flagged | | | |

**Music: a bank of beds, not one per video** (owner's recommendation, 2026-10-02). S6 generates a bank of beds per mood per account once (for example 4 moods × 5 beds), the owner approves them, and items reuse them. The cost is about the same either way (cents), but a bank gives curation and a consistent sound per account. A royalty-free library stays the fallback.

**What S5 builds:** `modal.Cls` media servers for Qwen-Image (L40S), Wan2.2 A14B + Lightning (H100) and ACE-Step 1.5 (L4), registered in `media/registry.toml` with the revisions above. Each batches per account per day to spread the cold starts; A14B and Qwen loads are the slow ones (up to ~5 min), so memory snapshots matter most there.

## What S6's producer must do (independent of the model)

The first samples failed on these, not on image quality. They are producer rules, so they hold whichever model S5 serves.
1. **Shot planning:** the script is written in short lines (3–5 s each), and the shot list has **one image per line, drawn for that line**. No montage of unrelated images and no proportional timing.
2. **The hook frame:** frame 0 is a striking image for the first sentence, ideally something impossible to photograph, and it moves from the start (b-roll or a strong push-in). The first sentence and the first image are one beat.
3. **Style lock:** one model and one tuned style suffix per video, and per account (a blueprint field). Mixing models gives mixed looks.
4. **Shot continuity** (the owner's main complaint in e2e2: "they have the same style, but transition very poorly"): consecutive images should share composition cues (horizon, light direction, palette), and transitions should be smoother than hard cuts between unrelated framings. e2e3 tests hard cuts with continued Ken Burns motion vs 0.4 s crossfades; the owner's pick sets the default.
5. **B-roll timing:** a b-roll shot covers exactly its line, cut on a line boundary. A line longer than the clip doesn't get b-roll (or gets a longer clip); a b-roll never turns into its own still mid-sentence.
6. **Narration timing:** TTS per line (or word timings from the aligner), so every cut lands on a line boundary.
7. **Captions from the narration's timings:** the clip producer's style (Anton, white with a black border, ≤ 3 words per line, the pop, key words in yellow from `keywords_v2`, the hook title card), from faster-whisper word timings snapped to the known script. This is the same pass as X1's TTS guard and the aligner in 03, so production transcribes once.
8. **Bed level:** normalize each bed's loudness before mixing (no crescendo), fade it in and out, and sit it about 16 dB under the voice before ducking.
9. **Text in images:** check rendered text against the script (OCR) or put words in the overlay; never trust a generated headline.

## What the renderer needs (S5/S6 changes to `src/`)
- **Configurable duck depth.** S4's ducking is fixed (`sidechaincompress threshold=0.03 ratio=8`). The owner wants the bed much deeper under the voice (about -15 to -18 dB); the probe got there with a static `gain_db` on a pre-flattened bed. Add a duck-depth (or target bed level) field to the music track, and a bed-normalization step.
- **Timeline transitions.** The Timeline has only hard cuts between contiguous segments. Add an optional transition per cut (at least a crossfade of 0.3–0.5 s, `xfade`), with segments overlapping by the fade length; b-roll needs a held last frame or a slightly longer clip to cover the overlap. The probe composited crossfades outside the renderer (each shot rendered alone, then `xfade`), which costs a second encode.
- **Captions for produced Timelines:** a captions builder from narration word timings (not a `ClipSpec` over a source transcript), reusing `captions.chunk_words`, `pick_keywords` and `build_ass`. The probe called those functions directly; the stage's `run` needs a `ClipSpec`.
- S4's deferred minors on stills and b-roll (a `%` in a still's path, short b-roll padding) still apply.

## Risks
1. **Cold starts dominate small batches:** A14B costs ~$0.30 and Qwen ~$0.15 per cold start (more on a slow Volume day). Batch per account per day, and try memory snapshots in S5.
2. **Cost per story rises with b-roll:** 8 Qwen stills ≈ $0.033; each b-roll shot ≈ $0.10. A story with 1–2 b-roll shots costs about $0.18–0.30 in total (03's cost model is updated).
3. **Text in images** (above), and unprompted people in empty scenes.
4. **Small sample:** 10 stills, 3 b-roll pairs and one owner. S6 should re-rate on real story scripts before locking a blueprint's style.

## Files
- **Kept on the `clipforge-models` Volume:** `x4/` (about 264 GB): the owner deletes it after this card merges (`uv run modal volume rm -r clipforge-models x4`).
- **Probe, outputs and blind samples:** `~/clipforge-x4/` on the owner's machine (outside the repo; the card's `scratch/x4/` was blocked by the scope guard). Safe to delete once this card merges. All the numbers are in this report and in 03.

# X4: visuals and music spike report

Date: 2026-10-01 · Spend: **$3.50 of $15** (`modal billing summary`, ephemeral apps) · Status: **draft, waiting for the owner's blind ratings** (card 012, checkpoint A). The ratings, the recommendation and "what S5 builds" are final at checkpoint B.

**Question:** what do stills, 5 s b-roll and 60 s music beds cost on Modal, how fast are they, and are they good enough for the story accounts (untold.archive / historias.ocultas)?

## Setup
- **Test set:** 10 stills in the style of 07 (lost cities, forgotten inventors, "the day that…"; molasses flood, Antikythera, a ghost ship, Tunguska, a torn tent in the snow…), the last 3 with text (an English newspaper headline, a museum label, a Spanish poster). 3 b-roll shots animated from 3 of the stills (image-to-video). 4 music moods (mystery, epic, melancholy, eerie) × 2 seeds, 60 s, instrumental. One style suffix on every still prompt; seed 42.
- **Hardware and prices** (`modal billing rates`, 2026-10-01): L4 $0.80/h, L40S $1.95/h, H100 $3.95/h, memory $0.008/GiB-h. $ per unit = warm GPU seconds × the GPU's rate; memory adds under 5% except where noted.
- **Weights:** on the `clipforge-models` Volume under `x4/` (about 264 GB, pinned revisions below). Code: a throwaway probe (Modal app `clipforge-x4`, diffusers 0.40.0, torch 2.10.0; ACE-Step 1.5 at its `v0.1.6` tag).
- **Cold start** = container start (25–37 s, measured where a run was collected first) + model load (in the table). Warm = the mean of units 2–N.

## Licenses (action 1: none dropped)

| Candidate | Weights | Code | Bundled parts | Pinned revision |
|---|---|---|---|---|
| Z-Image-Turbo (`Tongyi-MAI/Z-Image-Turbo`) | Apache-2.0 | Apache-2.0 (`Tongyi-MAI/Z-Image`) | text encoder Qwen3-4B (Apache-2.0), in the repo | `f332072a` |
| Qwen-Image-2512 (`Qwen/Qwen-Image-2512`) | Apache-2.0 | Apache-2.0 (`QwenLM/Qwen-Image`) | text encoder Qwen2.5-VL-7B (Apache-2.0), in the repo. **Not 2.1** (non-commercial, banned in 03) | `25468b98` |
| Qwen-Image-2512-Lightning 8-step LoRA (`lightx2v/…`) | Apache-2.0 | Apache-2.0 (`ModelTC/LightX2V`) | — | `a52649c9` |
| Wan2.2 TI2V-5B (`Wan-AI/Wan2.2-TI2V-5B-Diffusers`) | Apache-2.0 | Apache-2.0 (`Wan-Video/Wan2.2`) | umT5 text encoder and Wan VAE, in the repo | `b8fff731` |
| Wan2.2 I2V-A14B (`Wan-AI/Wan2.2-I2V-A14B-Diffusers`) | Apache-2.0 | Apache-2.0 | same | `596658fd` |
| Wan2.2-Lightning I2V 4-step LoRAs (`lightx2v/Wan2.2-Lightning`, Seko-V1) | Apache-2.0 | Apache-2.0 | — | `18bccf88` |
| ACE-Step 1.5 (`ACE-Step/Ace-Step1.5`) | MIT | MIT (`ace-step/ACE-Step-1.5`, tag `v0.1.6`) | Qwen3-Embedding-0.6B (Apache-2.0), 5 Hz LM 1.7B (in the repo). The card says it was trained on licensed, royalty-free and synthetic music, and output is for commercial use | `19671f40` |

All are on 03's allowlist. Not used: Kijai's re-packed Wan LoRAs (unclear license); the lightx2v originals load in diffusers directly.

## Results

### Stills (10 prompts each)

| | Z-Image-Turbo, L4, FP8 storage | Z-Image-Turbo, L40S, bf16 | Qwen-Image-2512 + Lightning 8-step, L40S, FP8 storage |
|---|---|---|---|
| Size | 1088x1920 (2.1 MP), 9 steps | 1088x1920, 9 steps | 928x1664 (1.5 MP, its native 9:16), 8 steps |
| Warm s per image | 31.4 | **9.0** | **7.5** |
| **$ per image** | $0.0070 | **$0.0049** | **$0.0041** |
| Model load / cold start | 58 s / ~85 s | 28 s / ~55 s | 132 s / ~160 s |
| Peak VRAM | 19.6 GB | 25.8 GB | 43.9 GB |
| Text (3 prompts) | label ✓, poster ✓, headline "MOLGAS" and a repeated "FLOOD" | label ✓, poster ✓, headline "MOLGAS" | poster ✓, label "ANTIKYIHERA", headline "MOLOSS" |
| Owner rating (blind) | pending | pending | pending |

Notes:
- **L4 in FP8 loses on both counts:** 3.5× slower than the L40S and 40% more per image. diffusers' layerwise FP8 *storage* casts every layer back to bf16, so the L4 does bf16 work on a slower card. True FP8 matmuls (torchao) weren't tried; they would need an Ada-specific path and are unlikely to beat the L40S at $0.005.
- **Prompt following:** Qwen drew the Tunguska radial blowdown and the molasses flood; Z-Image drew a standing forest and a tanker wagon. Neither spelled "MOLASSES". An uncommon word in a headline needs a check (OCR) or a typeset overlay, never trust.
- FP8 storage on Qwen was needed to fit 48 GB (bf16 is 58 GB of weights); the blind set lets the owner judge it.

### B-roll (3 image-to-video shots, 5 s each)

| | Wan2.2 TI2V-5B, L40S | Wan2.2 I2V-A14B + lightx2v 4-step, H100 |
|---|---|---|
| Output | 704x1280, 121 frames, **24 fps** | 720x1280, 81 frames, **16 fps** |
| Steps | 50, CFG 5.0 | 4, no CFG |
| Warm s per clip | 436 | **94** |
| **$ per clip** | $0.24 | **$0.10** (+$0.02 memory: 96 GiB for loading fp32 weights) |
| Model load / cold start | 34 s / ~70 s | 222 s (126 GB of fp32 weights from the Volume, plus 16 s of prompt encoding) / ~250 s |
| Peak VRAM | 30.5 GB (with VAE tiling; without it the decode ran out of 44 GB) | 69.9 GB |
| Owner rating (blind) | pending | pending |

Notes:
- **The 4-step A14B is 2.3× cheaper per clip than the 50-step 5B,** reversing 03's ordering (03 had A14B as primary at $0.07–0.13 and 5B as the cheaper fallback). The A14B cold start costs about $0.27 per batch, so it pays only when a batch makes several clips.
- A14B added an unprompted person at the top of the temple stairs in one shot. Producers should keep "no people" in the negative/positive prompt for empty scenes and the Judge (S6) should look at the last frame.
- **Frame rate:** the Timeline renders at 30 fps. 24 fps b-roll gets every 4th frame repeated, and 16 fps gets most frames shown twice. The blind e2e set has the same Timeline three ways (A14B at 16 fps, A14B interpolated to 30 fps with ffmpeg `minterpolate`, 5B at 24 fps) so the owner can judge the judder. `minterpolate` took 94 s of CPU for 5 s of video on a laptop; Practical-RIFE (MIT, 03) is the production option if interpolation is wanted.
- A production server should store bf16 copies of the A14B experts (57 GB instead of 114 GB) and load them straight to the GPU; that should roughly halve the load and drop the 96 GiB memory request.

### Music beds (4 moods × 2 seeds, 60 s, ACE-Step 1.5 turbo on L4)

| | With "thinking" (5 Hz LM 1.7B plans the codes) | Without thinking (DiT only) |
|---|---|---|
| Warm s per 60 s bed | 35.4 | **13.9** |
| **$ per bed** | $0.0079 | **$0.0031** |
| Model load / cold start | 88 s / ~120 s | 84 s / ~115 s |
| Peak VRAM | 13.1 GB | 13.1 GB |
| Loudness (as generated) | -15.0 to -21.8 LUFS | -12.5 to -18.2 LUFS |
| Owner rating (blind) | pending | pending |

Notes: the LM ran on nano-vllm in eager mode (no flash-attn in the image), which is most of the thinking cost; flash-attn could narrow the gap. Every bed came out exactly 60.0 s. Loudness varies by 9 LU across beds, which the renderer's two-pass loudness and ducking absorb (ADR-47).

### End-to-end sample (action 5)
A 39.9 s Timeline rendered locally with S4's `render.run`: 7 stills with Ken Burns (Z-Image, L40S), the ghost-ship b-roll (then its still when the sentence outruns 5 s), a 37 s narration (Kokoro `af_heart`, a placeholder for Qwen3-TTS), and the mystery bed ducked under it at -4 dB. 1080x1920 at 30 fps, rendered in 19 s on a laptop CPU, -13.8 LUFS (two-pass, dynamic fallback). No captions or title card (not part of this spike).

## Spend
| Run | ≈ $ |
|---|---|
| Weight downloads (CPU, 7 repos in parallel, 264 GB in under 5 min) | small |
| Stills (3 runs) | ~0.45 |
| B-roll (first try: 5B ran out of memory at the decode and took the A14B run down with it; second try) | ~2.5 |
| Music (2 runs) + narration (CPU) | ~0.3 |
| **Total (billing summary)** | **$3.50** |

Volume storage for the `x4/` weights is about $0.75 a day while kept (264 GB at $0.09/GiB-month).

## Recommendation
Pending the owner's blind ratings (checkpoint B). The numbers alone point to: stills on **L40S** (drop L4 FP8); b-roll on **Wan2.2 I2V-A14B + lightx2v 4-step** (H100), batched per account per day; music on **ACE-Step 1.5**, without thinking if the ratings allow.

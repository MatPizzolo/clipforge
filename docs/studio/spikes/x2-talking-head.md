# X2: talking-head bake-off report

Date: 2026-10-06 (card 005; started 2026-09-30, paused at ~25%) · Spend: **about $19 of $30** (`modal billing report`, see §8) · Status: **final**. The owner rated the samples blind.

**Question (card X2 in 06):** which open model makes a convincing 9:16 presenter? Candidates: InfiniteTalk, LongCat-Video-Avatar 1.5, EchoMimicV3 Flash-Pro.

**Answer: none passes yet.** No candidate looks real enough to post as a presenter. InfiniteTalk was rated clearly best (3.25 of 5, against 1.75 for LongCat and 1.0 for EchoMimic), and its best clip was "much better lip sync, still not very real". It uses `chinese-wav2vec2-base`, so under O7 (log #153) using it needs the owner's explicit OK. LongCat 1.5, the O7-safe preference, came second: it over-gestures and opens the mouth too wide. EchoMimic is out. The owner also found that all four voices sound too obviously AI (an X1/S5 finding, §6).

## 1. License check: all three pass, each with a workaround

| Candidate | Licenses | InsightFace | Required workaround |
|---|---|---|---|
| **InfiniteTalk** | Code, weights, the Wan2.1-I2V-14B base and the official lightx2v I2V LoRA: Apache-2.0 | none, and no other face library | Exclude the **FusioniX LoRA** (CC BY-NC-SA, non-commercial). Stub its unconditional `kokoro` import, which pulls in GPL espeak-ng through `misaki[en]` |
| **LongCat-Video-Avatar 1.5** | MIT, plus Apache-2.0 UMT5, the Wan VAE and Whisper-large-v3 | none | Patch out its vocal separator: `Kim_Vocal_2.onnx` has **no license** and was never downloaded. Open bug #124 crashes single-GPU INT8, so run bf16 |
| **EchoMimicV3** (Flash-Pro only) | Apache-2.0, on a Wan2.1-Fun-1.3B base | its preview path downloads RetinaFace weights **converted from InsightFace** (banned) | Install without `retina-face` or `tensorflow`. Flash has no windowing, so 20 s needs chunking |

**O7, closed (owner, log #153):** InfiniteTalk and EchoMimic Flash use `chinese-wav2vec2-base` (MIT weights, pretrained on WenetSpeech, which OpenSLR licenses for non-commercial use only). Such models are "needs owner review": LongCat 1.5 (Whisper) is preferred, and a wav2vec model is chosen only if it is clearly better in the blind rating, then only with the owner's explicit OK.

**InsightFace check, measured:** in every run, the probe listed the installed packages, the imported modules and every file in the weight folders it used. It found no `insightface`, `retinaface`, `facexlib`, `antelopev2`, `buffalo_l`, `glintr100` or `scrfd` in any of the three models, and no `.onnx` file. EchoMimic's `src/face_detect.py` was deleted from its image.

## 2. Helper tools

| Tool | License | Verdict |
|---|---|---|
| Z-Image-Turbo (portraits) | Apache-2.0 | used: 768×1344, 9 steps, ~4 s per portrait on L40S |
| Real-ESRGAN x4plus (upscale) | BSD-3 | used, loaded with `spandrel` 0.4.1 (MIT) instead of the broken `basicsr` |
| GFPGAN (face restore) | has non-commercial parts | **out** |
| RIFE 4.26 (frame interpolation) | MIT | used: Practical-RIFE's 4.26 weights and arch via ComfyUI-Frame-Interpolation (MIT re-host) |
| SFace (identity check) | Apache-2.0 | used, with YuNet |
| SyncNet (lip-sync metric) | code MIT; `syncnet_v2.model` states no license | internal metric only, with YuNet in place of its unlicensed S3FD detector; never in the product |

## 3. Method

- **Personas:** 3 synthetic portraits from Z-Image-Turbo at 768×1344, chest-up and facing the camera: p1 a woman in her thirties (home studio), p2 a man in his forties (office), p3 a woman in her twenties (café). Seed 23 for each.
- **Voices:** Qwen3-TTS 1.7B Base clones, unbatched, under X1's duration guard. p1 is X1's v2 reference; p2 and p3 were designed with VoiceDesign (seed 7), then cloned.
- **Scripts:** one ~20 s presenter script per language about learning phrases in chunks (EN 19.7–21.5 s, ES 20.3–24.0 s across voices). Every persona uses the same text.
- **Runs:** 3 portraits × EN/ES × 3 models = 18 clips. Deployed spike app `clipforge-x2`: one `run_set` per model ran its 6 clips in sequence on one H100 container, so the first clip was cold and the rest warm. Upstream code was pinned: InfiniteTalk `50aa0a9`, LongCat-Video `6b3f4b8`, EchoMimicV3 `7e89489`.
- **Model settings:**
  - LongCat 1.5: bf16 DiT with the DMD distill LoRA, 8 steps, CFG 1, 480p (480×832), 93-frame segments plus video continuation (ref index 10, mask range 3), audio through Whisper-large-v3.
  - InfiniteTalk: Wan2.1-I2V-14B-480P plus the official lightx2v I2V step-distill LoRA (rank 64), 4 steps, text CFG 1, audio CFG 2, shift 2, streaming mode with 9 motion frames, 448×832.
  - EchoMimic Flash-Pro: Wan2.1-Fun-1.3B, 8 steps, TeaCache 0.1, CFG 6 / audio CFG 3, 576×1008. Clips were cut into ≤121-frame chunks, each started from the portrait.
- **Fair comparison:** every clip's audio track was replaced by the same original TTS file. The 12 blind clips (p1 and p2 × EN/ES × 3 models) all went through one delivery path: RIFE 4.26 25 → 50 fps, the frames nearest 30 fps kept, Real-ESRGAN ×4, then scaled and cropped to 1080×1920 at 30 fps. The A/B/C letters were shuffled per group.
- **Metrics:** warm GPU-seconds per output second, cold start (submit → model loaded), peak VRAM, the SyncNet offset and confidence on a YuNet face track, and SFace cosine similarity against the portrait every 5th frame.

## 4. Results

H100 $3.95/h, L40S $1.95/h (`modal billing rates`, 2026-10-05). Six clips per model, 127.6 s of output each.

| | LongCat-Video-Avatar 1.5 | InfiniteTalk (+ lightx2v 4-step) | EchoMimicV3 Flash-Pro |
|---|---|---|---|
| **Owner's blind rating (1–5, mapped from words, §5): mean** | 1.75 | **3.25** | 1.0 |
| Ratings per group: p1_en / p1_es / p2_en / p2_es | 1 / 3 / 2 / 1 | 4 / 3 / 3 / 3 | 1 / 1 / 1 / 1 |
| GPU-s per output s (H100, warm) | 19.3 (18.3–20.5) | 20.4 (18.8–22.4) | 9.9 (9.2–10.5) |
| $ per output s, generation | $0.021 | $0.022 | $0.011 |
| Delivery to 1080×1920@30 (L40S) | 14.7 GPU-s/s, $0.008/s | 13.7 GPU-s/s, $0.007/s | 23.8 GPU-s/s, $0.013/s |
| **$ per 20 s presenter clip, generated and delivered** | ~$0.58 | ~$0.59 | ~$0.48 |
| Cold start, submit → loaded | 122–140 s (load 74–114 s) | 295–302 s (load 251–293 s) | 50–101 s (load 46–86 s) |
| $ per cold start (H100) | ~$0.15 | ~$0.33 | ~$0.10 |
| Peak VRAM | 60.5 GB | 57.1 GB | 22.8 GB |
| SyncNet confidence, mean (min–max) | 5.01 (3.80–6.51) | 4.23 (3.62–5.23) | 2.67 (1.63–3.24) |
| SyncNet offset (frames) | −2 on all 6 | −2 (one −3) | −1 (one 0) |
| SFace vs the portrait, mean / min | 0.793 / 0.507 | 0.845 / 0.669 | 0.865 / 0.670 |
| SFace drift, last 2 s − first 2 s | −0.071 | −0.011 | −0.032 |
| Audio encoder (O7) | Whisper-large-v3: unaffected | chinese-wav2vec2-base: needs owner review | chinese-wav2vec2-base: needs owner review |
| Failures | none | none (one H100 preemption, re-run) | none |

**The measured lip-sync score disagreed with the owner.** SyncNet ranked LongCat first, but the owner heard LongCat's very wide mouth shapes as wrong, and rated InfiniteTalk first. SyncNet rewards large, audio-correlated mouth motion; it can't tell exaggerated from natural. It's useful for catching broken sync (EchoMimic's low scores matched the owner's "lip sync wrong"), but it is not a quality ranking. The constant −1 to −2 frame offset on every model is most likely the crop and AAC pipeline (about 1 frame of encoder delay), not the models.

## 5. The owner's blind rating

The owner rated in words. The coordinator relayed the ratings, and they were unblinded with the key afterwards. The owner's list named the second group "p2_es"; it was read as **p1_es**, since the groups were p1_en, p1_es, p2_en and p2_es.

**Word-to-score mapping** (overall, 1–5):
- 1 = "very bad", or broken: visible jumps, wrong lip sync, or a mouth that stays too closed.
- 2 = "bad but not too bad".
- 3 = lip sync bad at the beginning, then it corrects.
- 4 = "much better lip sync, still not very real".
- 5 = convincing; nothing reached it.

| Group | Clip | Model | Owner's words | Score |
|---|---|---|---|---|
| p1_en | A | EchoMimic | "very bad. The avatar cuts while moving to another position; lip sync very bad" | 1 |
| p1_en | B | LongCat | "very bad. Gesticulates a little too much and the mouth opens a lot, but no cuts" | 1 |
| p1_en | C | InfiniteTalk | "much better lip sync, still not very real" | 4 |
| p1_es | A | LongCat | "lip sync bad at the beginning, then it corrects" | 3 |
| p1_es | B | InfiniteTalk | "same as A" | 3 |
| p1_es | C | EchoMimic | "very bad. Mouth too closed, lip sync wrong, and it cuts while moving" | 1 |
| p2_en | A | EchoMimic | "very bad" | 1 |
| p2_en | B | LongCat | "lip sync bad but not too bad; gesticulates and opens the mouth a lot" | 2 |
| p2_en | C | InfiniteTalk | "lip sync bad at the beginning, then it corrects; movements still not real" | 3 |
| p2_es | A | InfiniteTalk | "lip sync bad at the beginning, then it corrects" | 3 |
| p2_es | B | LongCat | "very bad. Gesticulates a little too much and the mouth opens a lot, but no cuts" | 1 |
| p2_es | C | EchoMimic | "very bad. Mouth too closed, lip sync wrong, and it cuts while moving" | 1 |

What the words say, per model:
- **EchoMimic:** "cuts while moving" in 3 of 4 clips. Those are the chunk seams: every ~4.8 s chunk restarts from the portrait, so the head jumps back. The mouth also stays too closed. Its last place is partly our chunking, but Flash has no other way to make 20 s.
- **LongCat:** too much gesturing and mouth opening in 3 of 4 clips. It's consistent, and a calmer prompt and different guidance might fix it (§7). No cuts.
- **InfiniteTalk:** no clip below 3. Its recurring flaw is lip sync that starts wrong and then corrects (3 of 4 clips); the movements are "still not real".
- **"Bad at the beginning, then it corrects"** appears for both InfiniteTalk and LongCat. It points at the first second of each clip, where both models start from the still portrait with little audio context, rather than at either model alone.

## 6. Recommendation

1. **No talking head goes to production now.** None passes: the best model averages 3.25, and its best clip was "still not very real". The avatar producer (S8) and AI-model reels that need a speaking face wait for a passing follow-up. Stories, bands and clips don't depend on it.
2. **If a follow-up runs, its lead candidate is InfiniteTalk.** It was clearly better in the blind test: +1.5 over LongCat, and no clip below 3. Under O7 it may be used only with the owner's explicit OK. LongCat stays as the O7-safe alternative, with the follow-up settings in §7.
3. **EchoMimic is dropped.** It scored lowest, the chunk seams can't be fixed within Flash, and it has the same O7 issue.
4. **The voices are a blocker of their own.** The owner's overall note was that "all four voices are noticed to be AI too much". These are X1's Qwen3-TTS clones, the voice primary from log #69. A presenter can't pass with an AI-sounding voice, whatever the video model, so S5/S6 should re-rate voices on presenter-style scripts (X1 rated story narration) before relying on Qwen for personas.

## 7. What to try next (a follow-up spike, owner's call; about $5–8)

- **The first second:** pad the audio with 0.5–1 s of silence or a short neutral lead-in, generate, then trim. That gives both models motion context before the first word, which may fix the "bad at the beginning" pattern for InfiniteTalk and LongCat at almost no cost.
- **InfiniteTalk without step distillation:** 40 steps, text CFG 5, audio CFG 4 (the upstream defaults) on 2–4 clips, to see whether the 4-step LoRA costs realism. Expect ~10× the GPU time (~$4–5 per 20 s clip), so try it only as evidence.
- **LongCat, calmer:** a prompt without gesture cues ("hands out of frame, calm, minimal gestures"), the non-distilled 50-step path with audio CFG 3–4, and a tighter chest-up crop so the hands can't wander in.
- **Better voices first:** the same clips with a more natural voice (a different VoiceDesign brief or a different TTS), so the rating judges the face, not the voice.
- **Newer models:** re-scan for open talking-head releases with a Whisper-style audio encoder before the next spike, since this field moves monthly.

## 8. Cost and resources

- **Spend:** about **$19** of the $30 card, including ~$0.40 before the pause. `clipforge-x2` came to $18.66 through the 18:00 UTC hour of 2026-10-06: H100 $13.18, L40S $3.95, L4 $0.68, memory $0.38, CPU $0.46, T4 $0.01. The last evals after that cost cents. Avoidable spend was about $1.3 for a crash loop and about $1.5 for an H100 preemption plus the InfiniteTalk re-run. In the crash loop, InfiniteTalk's first image failed at import, and Modal restarted the container for 6 h. The probe now caps each clip at 45 min and runs an import check on a T4 before using an H100.
- **App:** `clipforge-x2` stopped by the owner on 2026-10-06. `clipforge-x2-dl` was already stopped.
- **Volume `clipforge-models`, folder `x2/`:** about 227 GB of weights plus ~1 GB of outputs in `x2/out/`, about **$20 a month** at $0.09/GiB-month.
  - **Delete now:** `x2/echomimicv3` (3.7 GB) and `x2/wan-fun-1.3b` (19.8 GB), because EchoMimic is out. Also `x2/z-image-turbo` (32.9 GB): portraits are made, and it can be re-downloaded at X4's pinned revision.
  - **Keep only if a follow-up runs within weeks:** `x2/wan-i2v` (82.3 GB), `x2/infinitetalk`, `x2/lightx2v` and `x2/wav2vec` for InfiniteTalk, and `x2/longcat` (76.5 GB) for LongCat. Otherwise remove all of `x2/`; everything is re-downloadable from Hugging Face.
  - The exact commands are in card 005's report.
- **Probe:** `scratch/x2/` (git-ignored): `probe.py`, the driver, all result JSONs, the 12 blind clips and the key. Safe to delete once the owner no longer needs the samples. The numbers are all in this file.

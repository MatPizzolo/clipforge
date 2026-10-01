# X2 talking-head spike: partial (stopped 2026-09-30)

**Status:** stopped at about 25%, at step 5 (making the test inputs), by the 2026-09-30 pause. **No talking-head clip was generated**, so there are no quality, lip-sync or cost numbers yet. The probe code lived in `scratch/x2/` and was deleted with `scratch/`. What remains: the weights on the Modal Volume (below) and the license findings in this file. Written by the coordinator from the X1/X2 session's hand-off report.

**Question (card X2 in 06; resumed by card 005):** which open model makes a convincing 9:16 presenter? Candidates: InfiniteTalk, LongCat-Video-Avatar 1.5, EchoMimicV3.

Spend so far: about $0.40 of the $30 limit (image builds, downloads, and the portrait and audio calls that were cut off).

## 1. License check (step 3): all three pass, each with a workaround

| Candidate | Licenses | InsightFace | Required workaround |
|---|---|---|---|
| **InfiniteTalk** | Code, weights, the Wan2.1-I2V-14B base and the official lightx2v I2V LoRA: Apache-2.0 | none, and no other face library | Exclude the **FusioniX LoRA** (CC BY-NC-SA, non-commercial). Stub its unconditional `kokoro` import, which pulls in GPL espeak-ng through `misaki[en]` |
| **LongCat-Video-Avatar 1.5** | MIT, plus Apache-2.0 UMT5, the Wan VAE and Whisper-large-v3 | none | Patch out its vocal separator: `Kim_Vocal_2.onnx` has **no license** and was never downloaded. Open bug #124 crashes single-GPU INT8, so try bf16 first |
| **EchoMimicV3** (Flash-Pro only) | Apache-2.0, on a Wan2.1-Fun-1.3B base | its preview path downloads RetinaFace weights **converted from InsightFace** (banned) | Install without `retina-face` or `tensorflow`. Flash has no windowing, so 20 s needs chunking |

**Open for the owner (decision-log Open O7):** InfiniteTalk and EchoMimic Flash use `chinese-wav2vec2-base`. Its weights are MIT, but it was pretrained on **WenetSpeech**, which OpenSLR licenses for non-commercial use only. This training-data gray area needs a ruling before either model is used in production. LongCat 1.5 (Whisper) isn't affected.

## 2. Helper tools

| Tool | License | Verdict |
|---|---|---|
| Z-Image-Turbo (portraits) | Apache-2.0 | use |
| Real-ESRGAN (upscale) | BSD-3 | use, loaded with `spandrel` (MIT) instead of the broken `basicsr` |
| GFPGAN (face restore) | has non-commercial parts | **out** |
| Practical-RIFE v4.26 (frame interpolation) | MIT | use |
| SFace (identity check) | Apache-2.0 | use |
| SyncNet (lip-sync metric) | code MIT; `syncnet_v2.model` states no license | internal metric only, with YuNet in place of its unlicensed S3FD detector; never in the product |

## 3. Method planned (to reuse when X2 resumes)

- **Voices:** p1 cloned from X1's v2 reference (`clipforge-models:refs/x1/`); p2 and p3 designed with Qwen3-TTS VoiceDesign.
- **Portraits:** 3 synthetic ones from Z-Image-Turbo at 768×1344.
- **Scripts:** 20 s presenter scripts about a language-learning tip, in EN and ES (deleted with `scratch/`; rewrite them).
- **Native resolutions:** InfiniteTalk 480 → 448×832; LongCat 480p → 480×832; EchoMimic 768 → 576×1024.
- **Delivery path:** RIFE 25 → 50 fps, then 30 fps, then Real-ESRGAN ×4, then a crop to 1080×1920.
- **Blind set:** 12 clips (2 portraits × EN/ES × 3 models).
- **Run style:** deployed spike apps (`clipforge-x2`, `clipforge-x2-dl`) rather than `modal run`, because the laptop's connection drops ("Deadline exceeded") killed ephemeral runs. Stop them when done. Run a smoke test on an H100 per model before the full run.

## 4. Resources left on Modal

- Apps `clipforge-x2` and `clipforge-x2-dl`: stopped.
- Volume `clipforge-models`, folder `x2/`: about 227 GB of weights: wan-i2v 82.27 GB, Avatar-1.5 53.2, z-image-turbo 32.85, LongCat-Video 23.25, wan-fun-1.3b 19.81, infinitetalk 9.95, echomimicv3 3.73, wav2vec 0.76, lightx2v 0.74. Keep them if X2 resumes soon. Otherwise the owner removes them with `uv run modal volume rm -r clipforge-models x2`. Check Volume storage pricing on modal.com/pricing before keeping them for long.

## 5. To resume

1. The owner rules on WenetSpeech (O7).
2. Rebuild the probe from §1–§3 (the weights are already on the Volume).
3. Continue X2 from step 5 (the test inputs). Steps 2 and 3 are [card 005](../../cards/005-x2-resume.md), with the remaining budget of about $29.60.

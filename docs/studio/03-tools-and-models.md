# 03: Tools and models

Research date: 2026-09-29. **Estimates** are marked (est.). Everything is to be measured by the spikes in 04 before it's adopted. **Licenses matter:** the accounts are monetized, so every model's code, weights and bundled dependencies must allow commercial use.

## License allowlist (to be enforced by a test on `media/registry.toml`)

- **Allowed:** Apache-2.0, MIT, BSD, CC0, CC-BY-4.0 (with attribution).
- **Allowed with a condition:** GPL-3.0 tools that run only on our own servers and are never distributed (e.g. espeak-ng, which Kokoro uses for Spanish). AGPL stays banned, because it also covers use over a network (owner decision, 2026-09-30).
- **Needs owner review:** OpenRAIL(++), Llama community licenses, "community licenses" with revenue caps (Stability < $1M, LTX < $10M), licenses with territorial exclusions (Tencent Hunyuan excludes the EU, UK and South Korea).
- **Banned (non-commercial or needs a paid license):**
  - InsightFace model packs (buffalo_l, antelopev2). These are pulled in by LivePortrait, LatentSync, Hallo, InstantID, PuLID-antelope and IP-Adapter-FaceID.
  - FLUX.1-dev, FLUX.2 klein 9B, Qwen-Image **2.1**.
  - Sonic, F5-TTS weights, XTTS-v2 (Coqui CPML), Fish Audio S2.
  - IndexTTS (commercial use needs written permission).
  - MusicGen weights, YuE2.
  - The MMS forced aligner (CC-BY-NC).
  - The FusioniX LoRA for Wan/InfiniteTalk (CC BY-NC-SA). GFPGAN's non-commercial parts. RetinaFace weights converted from InsightFace (pulled in by EchoMimicV3's preview path). `Kim_Vocal_2.onnx` (no license; LongCat's vocal separator). Found in X2, 2026-09-30.
- **Internal metrics only, never in the product:** SyncNet's `syncnet_v2.model` (no stated license), used with YuNet instead of its unlicensed S3FD detector (X2).
- **Open, owner ruling needed (log O7):** models pretrained on non-commercial data with permissively licensed weights, e.g. `chinese-wav2vec2-base` (MIT weights, pretrained on WenetSpeech, which is non-commercial). InfiniteTalk and EchoMimic Flash use it; LongCat 1.5 doesn't.
- **Libraries:** LGPL used unmodified as a dependency is allowed; the allowlist above is for models and vendored code.

## Media models (self-hosted on Modal)

| Job | Primary | Fallback | License | GPU | Cost (est.) |
|---|---|---|---|---|---|
| Transcription | faster-whisper large-v3-turbo (existing) | — | MIT | L4 | ~$0.05 per source hour |
| Voice (TTS), EN + ES | **Qwen3-TTS 1.7B** (VoiceDesign creates a persona's voice from text; Base clones that synthetic reference). Run **unbatched, behind a guard** (token cap from text length, duration check, WER check, one retry): batched, it ran away once in 10 scripts | **Kokoro-82M** (bulk narration; preset voices only, 3 in Spanish; uses espeak-ng, GPL-3.0). **Chatterbox Multilingual**: not recommended, 2 of 15 Spanish files dropped or invented text | Apache-2.0 / Apache-2.0 (+ GPL-3.0 espeak-ng) / MIT | L4 (Kokoro: CPU is enough) | Measured in X1, 2026-09-30, on L4: Qwen **$0.033 per 60 s** unbatched (RTF 2.5; batched $0.009, not usable until guarded), Chatterbox $0.014, Kokoro $0.0002 (CPU $0.0013). Cold start 35–40 s / 56–59 s / ~30 s. WER in Spanish 0.6% / 4.0% / 0.6%. Owner's blind rating EN/ES: Qwen 4.0/5.0, Kokoro 4.5/4.0, Chatterbox 4.5/3.5 |
| Word timing for captions | faster-whisper word timestamps on the TTS output, snapped to the known script. The same pass is the TTS guard's WER check, so production transcribes once (S5/S6 build it as one step) | WhisperX alignment (wav2vec2; check each language model's license) | MIT | L4 | ~$0.001 |
| Music beds | **ACE-Step 1.5** | DiffRhythm | MIT / Apache-2.0 | L4 | < $0.005 per bed |
| Persona face | **Z-Image-Turbo** + one **LoRA per persona** (20–40 curated synthetic shots) | Qwen-Image-Edit-**2509** for pose and outfit changes (pin the version; 2.1 is non-commercial); PuLID-FLUX **FaceNet variant** only | Apache-2.0 | L40S (LoRA training: H100) | one-off, ~$1–3 per persona (est.) |
| B-roll stills | **Z-Image-Turbo** (8 steps) | Qwen-Image-2512 + Lightning (images with text); FLUX.2 klein **4B** | Apache-2.0 | L40S (or L4 in FP8) | ~$0.002–0.006 per image |
| B-roll video (5 s) | **Wan2.2 A14B + lightx2v 4-step LoRA** | Wan2.2 TI2V-5B (L40S) | Apache-2.0 | H100 | ~$0.07–0.13 per clip |
| Talking head | **InfiniteTalk** (Wan2.1-I2V-14B + audio adapter; head, body and lips; 480p then upscale; audio encoder chinese-wav2vec2-base is MIT, no InsightFace in its requirements). InfiniteTalk and EchoMimic Flash use chinese-wav2vec2-base, pretrained on non-commercial WenetSpeech: open question O7 in 10, so prefer LongCat unless X2 shows a wav2vec model clearly better (log #121, spikes/x2-talking-head.md) | **LongCat-Video-Avatar 1.5** (MIT; no InsightFace; Whisper audio encoder) in a bake-off; **EchoMimicV3** Flash (1.3B, cheap) | Apache-2.0 / MIT / Apache-2.0 | H100 or A100-80 | ~$0.35–0.55 per 30 s at 480p; use it only for presenter segments |
| Face detection | YuNet (existing, MIT) or MediaPipe | — | MIT / Apache | CPU | — |

## LLM text (paid credits: the only paid AI)

| Quality level | Use | Provider |
|---|---|---|
| `quality` | Highlights, scripts, post copy, translation, policy claim check | Anthropic: `claude-haiku-4-5` by default; a larger Claude model for scripts if evals show it's needed. Pinned per stage and part of the cache key |
| `bulk` | Hashtag variants, title A/B ideas, research summaries | Router over free tiers (Gemini free, Groq, OpenRouter with a one-time $10 top-up), falling back to Haiku. Reads rate-limit headers and backs off. **Only public content goes to free tiers** (Google's free tier trains on prompts). Trial keys that forbid commercial use (Cohere) are out |

Before changing a model on any quality-level stage, run an eval (ADR-4, docs/EVALS.md).

## Platform and services

| Need | Primary | Fallback | Cost | Notes |
|---|---|---|---|---|
| Compute | **Modal** | — | Starter: $0 with $30/mo credit, 5 crons, 10 concurrent GPUs, 100 containers, 3 seats. Team: $250 with $100 credit, unlimited crons, 50 GPUs | GPU per hour: T4 $0.59, L4 $0.80, A10 $1.10, L40S $1.95, A100-80 $2.50, H100 $3.95. CPU $0.047/core-h, memory $0.008/GiB-h. No published web-endpoint count (rate limit 200 req/s). GPU memory snapshots are **alpha**. Volume v2 is beta with no data-loss guarantee, so only rebuildable caches. Dict entries expire after 7 days without reads or writes; whether `items()` counts is undocumented (checked 2026-09-29) |
| Posting | **Upload-Post** | Zernio (~$318/mo at 100 connections) | Basic $24/mo (5 profiles), Professional $50 (25), Advanced $147 (75); yearly billing −40%. Paid plans: unlimited uploads, FFmpeg-minute caps. **Free has no TikTok.** One profile = one account on every platform | Public TikTok posts through its own audited app (paid plans; the TikTok account must allow public posts, else `tiktok_privacy_unavailable`). AI-label fields: `is_aigc`/`tiktok_is_ai_generated`, `containsSyntheticMedia`, `is_ai_generated`, `facebook_is_ai_generated`. Media by URL or upload; photos and carousels. HMAC-SHA256 webhooks (`X-Upload-Post-Signature` over `<timestamp>.<body>`; deliveries before the secret exists are unsigned). Analytics (live lookup 100 req per 5 min). Python SDK `upload-post` (checked 2026-09-29). Avoid self-hosted Postiz (the TikTok audit falls on us) and Buffer (no video posting) |
| Official APIs (later) | YouTube Data v3 (upload quota: 100/day, its own bucket) plus YouTube Analytics | Instagram Graph (100 posts per 24 h, `is_ai_generated`) | free | TikTok's own API: unaudited apps can only post privately |
| Database | **Neon Postgres** | Supabase | Free: 0.5 GB and 100 CU-h/mo **per project**; scales to zero after 5 idle minutes (resume in a few hundred ms). Launch $0.106/CU-h, storage $0.35/GB-mo | Use the pooled endpoint from Modal, in Modal's AWS region. A query every 5 minutes keeps compute awake (~180 CU-h/mo at 0.25 CU), which is over the free tier |
| Media hosting | **Signed, expiring Volume links** (ADR-13's mechanism, ADR-28) | Cloudflare R2 (or S3), only if those prove unreliable | R2: $0.015/GB-month, **free egress**, 10 GB free | R2 would use a public bucket with unguessable keys, or presigned URLs |
| Dashboard hosting | **Vercel Pro** | Cloudflare Pages | $20/mo (includes $20 of usage) | Hobby is "non-commercial personal use only"; the fair-use page counts ads, and sites whose primary purpose is affiliate linking, as commercial. A monetized studio's dashboard needs Pro |
| Dashboard auth | **Auth.js** (one owner) | Clerk (free up to 50k MRU) | $0 | |
| API client | **@hey-api/openapi-ts** | openapi-typescript | $0 | Export the OpenAPI spec in CI; the docs routes stay off |
| LLM tracing | **Langfuse Cloud Hobby** | self-hosted | $0 (50k units/mo) | |
| Errors | **Sentry Developer** | — | $0 (5k errors/mo) | Initialize in `@enter` or at module level from a Modal secret |
| Stock media | **Pexels** (200 req/h), **Pixabay** | — | $0 | Credit Pexels in the app. Cache Pixabay results for 24 h and download files, don't hotlink |
| Band data | **MusicBrainz** (1 req/s, User-Agent with contact) + **Wikidata** (CC0) | — | $0 | Last.fm needs a separate agreement for commercial use. Spotify's Web API is effectively closed to new apps |
| Band photos | **Wikimedia Commons** (CC-BY or CC-BY-SA, with attribution) | Band-supplied press material with written permission | $0 | No photoreal generated images of real people |
| Downloads (local) | **yt-dlp** + Deno + bgutil PO-token plugin | yoinks (interactive only, no script mode) | $0 | Only from home internet. Only permitted content |

## Monthly cost model (recomputed 2026-09-29 with verified prices; voice measured in X1 on 2026-09-30; the rest are estimates until X2–X4 measure them)

**Per video, variable cost** (GPU, CPU and LLM; cold starts spread over a daily batch per account):

| Producer | Cost per video | Where it goes |
|---|---|---|
| Podcast clip | ~$0.02 | transcribe + highlights per source hour, split over its clips (measured) |
| Story or band (60–90 s, 6–8 stills, voice, music) | ~$0.09–0.13 | TTS ~190 L4-s for ~75 s of unbatched Qwen ($0.042, measured in X1), 7 stills ~20 L40S-s ($0.011), music ~$0.004, script and copy on Haiku ~$0.01, CPU render ~$0.002, plus cold starts |
| Avatar (presenter ~8 s plus b-roll) | ~$0.19–0.34 | ~8 s of talking head on H100 (~$0.10–0.15) plus the story costs |
| AI-model carousel / reel | ~$0.03 / ~$0.15 | stills only / plus one Wan2.2 motion clip |
| Dub | ~$0.08 (story), ~$0.33 (avatar) | new narration on unbatched Qwen (X1) |

Cold starts dominate at low volume. That's why GPU work is batched per account per day.

**Scenario 1: 5 accounts** (wave 1 clips ×3 at 4/day, wave 2 stories ×2 at 1.5/day ≈ 450 videos a month)

| Item | $/month |
|---|---|
| Modal: 360 clips ≈ $7, 90 stories ≈ $10, crons ≈ $1 | ~$18, **inside the $30 Starter credit → $0** |
| Upload-Post Basic (5 profiles) | $24 ($15 billed yearly) |
| Vercel Pro | $20 |
| Neon | $0 if it can scale to zero; ~$20 on Launch if a 5-minute cron keeps it awake |
| Claude API | ~$5–10 |
| R2 (only if Volume links prove unreliable) | $0 (under 10 GB) |
| **Total** | **~$50–75** |

**Scenario 2: 19 accounts** (the 07 portfolio: 3 clip accounts at 4/day; 6 story, 3 band, 4 avatar and 3 AI-model accounts at 1–1.5/day ≈ 1,000 videos a month)

| Item | $/month |
|---|---|
| Modal: clips 360 × $0.02 ≈ $7, stories 270 × $0.11 ≈ $30, bands 90 × $0.11 ≈ $10, avatars 120 × $0.29 ≈ $35, AI-model 90 × $0.15 ≈ $14, dubs ≈ $8, +30% cold starts ≈ $135 | **~$105** after the $30 credit |
| Upload-Post Professional (25 profiles) | $50 ($33 billed yearly) |
| Vercel Pro | $20 |
| Neon Launch | ~$20 |
| Claude API | ~$20–30 |
| R2 (only if Volume links prove unreliable) | ~$1–2 |
| xAI X Search trend job (optional, ~4K posts a month) | ~$20 |
| **Total** | **~$215–245** (~$195–225 without X Search) |

The $100+/month budget covers scenario 1 with room to spare. Scenario 2 needs about $215–245 (up from ~$200 once X1 measured the voice cost), so waves 3–6 should wait for revenue. Budgets per account are enforced in code.

## Structured judgments: TypeSafe Jev (early access, launched 2026-09-15)

**What it is:** a "System One" model. You send it a `state` plus typed questions, and it returns typed answers with **calibrated probabilities**. It never generates text. Three primitives:
- `Choice`: pick one of up to 255 options;
- `Score`: rank on ordered levels;
- `Noul`: probability that a statement is true.

All questions in one request run in parallel.

**Numbers:** 70–500 ms per call, **$0.042 per M input tokens, output free**. There are Python and JS SDKs, and it's also reachable through the Vercel AI Gateway.

**Caveats:**
- Early access, waitlist-gated. The launch price may be subsidized. Also listed on Vercel AI Gateway (`jev`) and OpenRouter (`jev-1.13`) (checked 2026-09-29).
- No weights, so no self-hosting.
- The benchmarks are vendor-run.
- "No hallucinations" means the output always matches the schema, not that it's correct.
- Spanish quality is unknown.

**Where it fits:** every *decision* point, as the `Judge` protocol (see 02 §5b).
- **Policy gate:** Noul checks for health claims, earnings claims, first-person testimonials and missing disclosure. Calibrated thresholds send the uncertain ones to `review`.
- **Review-tier routing:** confidence ≥ threshold posts automatically, and the middle band goes to a human. This is the tiered review from ADR-29.
- **Hook and title ranking:** Claude writes N variants and Jev scores them.
- **Classification:** reject-reason prediction, topic and pillar tagging, "same story as item X?" deduplication, and comment triage later.

**Not for:** scripts, copy, translation, or highlight spans. Those need text generation, so they stay with Claude.

**Adoption:** spike X5 compares Jev with Haiku on about 200 labeled items: the owner's past verdicts plus synthetic policy cases. It measures accuracy, calibration, Spanish and cost. If Jev loses, Haiku stays behind the same `Judge` protocol.

**Skill:** the TypeSafe Claude Code skill only gives guidance and makes no calls itself. Install it in the session that builds the Judge:

```
claude plugin marketplace add typesafe-ai/skills
claude plugin install typesafe@typesafe-ai
```

## xAI Grok

- **LLM:** grok-4.x costs $1.25–2 input / $2.50–6 output per M tokens, with schema-guaranteed JSON. It isn't cheaper than Haiku, so **it doesn't go into the router for general text.**
- **X Search tool** ($5 per 1K posts): a **weekly trend job** per niche ("what's trending on X about <niche>", structured output). This is compliant with X's terms and replaces scraping. The X API is now pay-per-use (~$0.005 per post read).
- **Grok Imagine Video 1.5:** ~$0.05–0.08/s at 480p (third parties quote ~$0.14/s at 720p), up to 15 s, native audio. It ranked #1 on the image-to-video arena in May 2026. Output is owned by the user, but there's **no IP indemnity outside enterprise**, and real people's likenesses are blocked.
  - **Use:** a premium "hero shot" option for story accounts, A/B tested against Wan2.2 on retention. **Not bulk.**
  - **Note:** it's a paid media API. That's an exception to the "self-hosted media" rule, so it's allowed only as an opt-in per account.
- There's little worth using among open-source "Grok bot" projects. Use xAI X Search directly.

## Open-source helpers (adopt or borrow)

| Tool | License | Use | Verdict |
|---|---|---|---|
| **modal-labs/modal-examples** | MIT | Patterns: `gpu_snapshot.py`, `text-to-audio/generate_music.py` (ACE-Step), `chatterbox_tts.py`, `batched_whisper.py`, `whisperx_transcribe.py`, `dreambooth/diffusers_lora_finetune.py`, `cls_with_options.py`, `ltx2_two_stage.py` | **Borrow patterns** for every media server |
| ComfyUI | GPL-3.0 | Graph image/avatar workflows | **Prototyping only.** Modal removed its ComfyUI examples on 2026-03-05, custom nodes drift away from `uv.lock`, and cold starts are slow. Port winning workflows to diffusers in a `modal.Cls` |
| **Practical-RIFE** | MIT | 16 fps (Wan/InfiniteTalk) → 30 fps | Adopt |
| **Real-ESRGAN** | BSD-3 | Upscale 360–480p sources and AI frames | Adopt, optional (avoid Upscayl: AGPL) |
| **BiRefNet** (rembg as a wrapper) | MIT | Cutouts for avatar and product composites | Adopt |
| **python-audio-separator** | MIT (check each checkpoint's license) | Vocal/music split for dubbing (Demucs is archived) | Adopt in S10 |
| ffmpeg-normalize / pyloudnorm | MIT | Two-pass loudnorm, LUFS checks in tests | Not needed: S4 built two-pass in-house (`stages/loudness.py`, ADR-47; measured single pass -14.5 to -14.2 LUFS vs two-pass -14.2 to -14.0 on real clips). `pyloudnorm` only if a test needs an independent LUFS check. Note from S4: the Modal image runs Debian bookworm's ffmpeg 5.1 while dev and CI run 6.1, so render changes are tested in a bookworm container before deploying |
| auto-editor | Unlicense | Silence and filler cutting | Borrow the idea: we already have word timestamps, so cut in ffmpeg |
| **pycaps** | MIT (alpha) | Animated caption effects | Borrow the presets and port them to ASS tags, plus **Noto Emoji** (Apache/OFL) overlays |
| Revideo / Motion Canvas | MIT | Code-driven motion graphics | Only if ASS limits us (Remotion needs a company license) |
| **Langfuse** | MIT core | LLM tracing, prompt versions, cost | Adopt |
| **promptfoo** | MIT | CI gate on prompt version bumps | Adopt, next to `clipforge eval` |
| DeepEval | Apache-2.0 | pytest-native LLM-judge metrics | Borrow |
| **Umami** | MIT | Analytics for a link-in-bio page | Adopt when the bio pages exist |
| Shlink | MIT | Self-hosted short links | Fallback to our own `/go` |
| YouTube Data API `mostPopular` + `commentThreads` | official | Trend and comment research | Adopt (compliant) |
| pytrends, TikTok-Api, Creative Center scrapers | — | Trends | **Skip.** pytrends is archived and broken, and the others break platform terms (never run them from posting IPs) |
| Postiz, Dub (self-host), Upscayl | AGPL | — | Skip |
| n8n | Sustainable Use | — | Skip (not OSI; the dispatcher cron covers it) |

## Open-source pipelines worth reading (ideas only; don't vendor)

- **openshorts** (MIT, 5.8k★, active): the closest open OpusClip clone. Compare its dubbing flow and virality prompts.
- **RedditVideoMakerBot** (GPL): story format ideas only.

- **MoneyPrinterTurbo** (MIT): how it matches stock footage to script lines.
- **ShortGPT** (MIT): an LLM-readable editing markup and a dubbing flow.
- **short-video-maker** (MIT): Kokoro, whisper.cpp captions and Pexels. It renders with Remotion, which needs a paid company license, so **keep ffmpeg + libass**.
- **VideoLingo** (Apache-2.0): a reference design for dubbing.

## Sources

**Models**
- TTS and alignment: https://github.com/QwenLM/Qwen3-TTS · https://huggingface.co/hexgrad/Kokoro-82M · https://huggingface.co/ResembleAI/chatterbox · https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner
- Music: https://huggingface.co/ACE-Step/Ace-Step1.5 · https://huggingface.co/facebook/musicgen-large (non-commercial) · https://huggingface.co/stabilityai/stable-audio-open-1.0/blob/main/LICENSE.md
- Avatar, image and video: https://github.com/MeiGen-AI/InfiniteTalk · https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5 · https://github.com/antgroup/echomimic_v3 · https://github.com/Wan-Video/Wan2.2 · https://huggingface.co/Qwen/Qwen-Image-Edit-2509 · https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md · https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence · https://github.com/KwaiVGI/LivePortrait/blob/main/LICENSE · https://www.insightface.ai/solutions/face-recognition-licensing · https://github.com/jixiaozhong/Sonic/blob/main/LICENSE · https://ltx.io/model/license

**Modal**
- https://modal.com/pricing · https://modal.com/docs/guide/memory-snapshots · https://modal.com/docs/guide/dicts · https://modal.com/docs/guide/volumes · https://modal.com/docs/guide/model-weights · https://modal.com/docs/guide/webhook-proxy-auth

**Posting and platform APIs**
- Upload-Post: https://docs.upload-post.com/api/upload-video/ · https://pypi.org/project/upload-post/
- Zernio: https://zernio.com/pricing
- Postiz: https://github.com/gitroomhq/postiz-app/issues/1854
- YouTube: https://developers.google.com/youtube/v3/determine_quota_cost
- Instagram: https://developers.facebook.com/docs/instagram-platform/content-publishing/
- TikTok: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post

**Infrastructure**
- https://neon.com/pricing · https://developers.cloudflare.com/r2/pricing/ · https://vercel.com/docs/limits/fair-use-guidelines · https://github.com/hey-api/hey-api · https://langfuse.com/pricing · https://sentry.io/pricing/

**Data sources**
- https://www.pexels.com/api/documentation/ · https://pixabay.com/api/docs/ · https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting · https://www.last.fm/api/tos · https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api · https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data

**Downloads**
- https://github.com/yt-dlp/yt-dlp/wiki/EJS · https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide · https://github.com/pablostanley/yoinks

**Monetization**
- https://www.skool.com/affiliate-program · https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards · https://support.google.com/youtube/answer/1311392 · https://creatorsagency.co/blog/tiktok-creator-rewards-program-2026 · https://creators.facebook.com/introducing-facebook-content-monetization · https://creatorblade.com/blog/youtube-inauthentic-content-policy-2026-stay-monetized

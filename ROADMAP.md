# Roadmap

Each phase ends with something usable. Tick items as they land; one item ≈ one PR.

## Phase 0 — Scaffolding
- [x] `uv` project, ruff, mypy, pytest with `gpu`/`slow` markers
- [x] `config.py` (pydantic-settings) + `.env.example`
- [x] Modal app skeleton with secrets, a Volume for job files, a Dict for job state
- [x] `models.py` with contracts: `Job`, `Transcript`, `Word`, `ClipCandidate`, `ClipSpec`, `RenderedClip`
- [x] Test fixtures: 10-second talking-head clip, sample transcript JSON
- [x] CI: lint + fast tests on push, deploy on main (ADR-16; the deploy job is off until the repository variable `DEPLOY_ENABLED` is set)

## Phase 1 — MVP: link in, clips out (fully serverless, ADR-9)
- [x] `ingest`: accept a direct media URL or a Telegram upload (≤ 20 MB); normalize to mp4 + 16 kHz mono wav (ADR-10)
- [x] `transcribe`: faster-whisper large-v3-turbo on GPU, word timestamps, language detection
- [x] `highlights`: chunk transcript, call LLM with `prompts/highlights_v1.md`, validate JSON, snap boundaries to sentence ends
- [x] `reframe` (simple): center crop 9:16 with blurred-background fallback
- [x] `captions`: word-level ASS file, one style preset
- [x] `render`: ffmpeg + libass, libx264 on CPU, 1080x1920, each clip under 50 MB
- [x] `package`: output folder layout, `metadata.json`, zip
- [x] Step chain on Modal: one function per step, spawn-next, atomic fan-in to package, retries, stall sweeper, resume (ADR-12)
- [x] Job API on Modal (FastAPI): `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/resume`, signed `GET /jobs/{id}/download` (ADR-2, ADR-13)
- [x] CLI: `clipforge run --input <url>` as a thin client of the deployed job API (in daily use with `clipforge clip`, `status` and `resume`)
- [ ] Telegram bot (webhook on Modal): `/clip <link>`, each clip sent as a video, then a signed zip link (the webhook and the posting assistant are live; the `/clip` path itself hasn't been verified end to end, and it retires when the dashboard's Produce page ships, ADR-44)
- **Exit criteria:** a 30-min podcast becomes 5 watchable clips in under 10 min, with cost logged.

## Phase 2 — Feels fast, collects feedback
- [ ] Job progress via `ctx.report`; bot edits one status message
- [ ] Send each clip as soon as it's rendered (per-clip fan-out lands in Phase 1 with the step chain; this item covers polish such as ordering and retries on send)
- [ ] 👍 / 👎 / ✂️ buttons; store ratings with clip features
- [ ] Command options: `n`, `len` and `lang` are built (bot options, plus `score`, `perm` and `credit`); `style` is open
- [x] Channel folders + `channels.toml` (credit, permission), batch submit, `--fetch` (ADR-22)
- [x] Posting queue on Modal: enqueue on package, derived per-platform status, `GET /posting`, `clipforge status` (ADR-23)
- [x] Telegram posting assistant: slot cron, clip + captions + ✅/⏭/🗑 buttons, pause rule, /status /next /pause /go (ADR-23)
- [x] Posting state kept alive against Modal Dict's 7-day expiry: daily per-key read + JSON snapshot on the Volume (ADR-24)
- [x] Cache by source hash: re-cuts reuse transcript + highlight scores
- [x] Cost summary in the final bot message

## Phase 3 — Clip quality
- [x] Scene detection (ffmpeg scene score, ADR-19)
- [x] Face-centered crop per shot (YuNet, ADR-19)
- [ ] Smoothed in-shot tracking (EMA/Kalman) for people who move a lot
- [x] Active speaker selection: cut to whoever is talking in multi-person shots, by mouth motion (ADR-21)
- [ ] Audio diarization (pyannote) for speaker choice, if mouth motion proves unreliable
- [ ] Silence and filler-word removal
- [ ] `post.md`: title, description, hashtags for TikTok / Reels / Shorts
- [ ] Thumbnail frame selection
- [x] Retention polish: -14 LUFS audio, hook title card, caption pop, bitrate by source (ADR-20)
- [ ] 2–3 caption style presets

## Phase 4 — Web app + storage
- [ ] Web app: submit link/file, live progress (SSE), preview + download clips
- [ ] Sync job folders to Google Drive or R2
- [ ] Google Drive link as input
- [ ] Volume retention policy (expire old jobs and their download links)
- [ ] Job history page

## Phase 5 — MLOps loop
- [ ] Eval set v1 (20–30 annotated videos) + `clipforge eval` (see docs/EVALS.md)
- [ ] Experiment tracking (MLflow or W&B): prompt version, model, eval scores
- [ ] Combine signals: LLM score + audio energy + laughter + heatmap peaks
- [ ] Ranker trained on 👍/👎 and, later, platform retention data

## Phase 6 — Studio (multi-account)
Full list with exit criteria, dependencies and action cards: [docs/studio/04-roadmap.md](docs/studio/04-roadmap.md) (cards in [06](docs/studio/06-session-prompts.md)). Accepted in the 2026-09-29 kickoff review: ADR-25, 26, 28–31, 34, 35, 38, 39; on 2026-09-30: ADR-41–46; on 2026-10-01: ADR-47 to ADR-50; on 2026-10-02: ADR-27 (the dispatcher) and ADR-33 (tracking links). **docs/studio/04 is the source of truth for Phase 6**; this list mirrors it.
- [ ] S0: plan C finished and plans A+B+C deployed (2026-09-29); only the 7-day background check is open. Assisted posting paused on 2026-10-05 (ADR-54)
- [ ] S1: Neon Postgres, accounts, content items, blueprints; queue and job records move off the Dict (code built, card 002; ticked at the rollout)
- [ ] S2: publishing through Upload-Post, the autopilot model (ADR-48; review dial, windows, ladder), the dispatcher, pure policy gate, tracking links; founder.tapes and hombre.en.construccion launch on it (designed in card 011; built in three cards: S2a rails, card 014; S2b Upload-Post, card 015; S2c autopilot and launches, card 016). Updated 2026-10-05 (ADR-54): Telegram is notifications only and assisted posting is paused; S2b starts after card 024 (the Review page) is deployed: 010 → 014 → 031 → 004 → 022 → 023 → 024 → 015 → 016
- [ ] S3a: dashboard shell (`web/`, login, Home over today's API): the shell is built; the Vercel deploy is card 004
- [ ] S3: Next.js dashboard v1 (separate `admin` Modal endpoint; after S1, alongside S2; planned in card 019; built in six cards, each after the previous one is deployed: S3-1 `admin` endpoint and Settings, card 022; S3-2 needs, Home and `/act`, card 023; S3-3 Review and Calendar, card 024; S3-4 Produce, Jobs and Sources, card 025; S3-5 Results, Compare and the account view, card 026; S3-5b Telegram retirements and the CLI cut-over, card 027). Updated 2026-10-05 (ADR-54): cards 004, 022, 023 and 024 now come before S2b, and `REVIEW_BATCH` no longer exists
- [ ] S3b: Notion one-way mirror (connector, no code)
- [ ] S3c: account workspaces: versioned categories, blueprints and accounts, experiments, notes (ADR-42; after S1 and S3's `admin` endpoint; planned in card 018; built in four cards: S3c-1a data and routes, card 035; S3c-1b pages, card 036; S3c-2 producer wiring, card 037; S3c-3 experiments, card 038)
- [x] S4: Timeline renderer (card 006, 2026-10-01; two-pass loudness ADR-47; deployed)
- [ ] HK: hook library and rotation (ADR-50; after S1's rollout, before S6; planned in card 020; built in three cards: HK-1 library, card 028; HK-2 variants, card 029; HK-3 interim page, card 030)
- [ ] S5: media servers and producer registry (planned in card 021; built in four cards: S5-1 the `modal_app/` split, card 031; S5-2 registry and engine, card 032; S5-3 media stages, card 033; S5-4 servers and hello, card 034)
- [ ] S6: story producer, plus the Judge, decision ledger and lanes (wave 2)
- [ ] S7: analytics, money, budgets, dispatcher cron
- [ ] S8: avatar producer and personas (wave 3)
- [ ] S9: band producer (wave 4)
- [ ] S10: dub winners EN ↔ ES
- [ ] S11: local fetch helper
- [ ] S12: the Desk (inbound triage)
- [ ] S13: AI model / influencer producer (wave 6)
- [ ] S14: funnel and own products
- [x] Spike X1: voice (2026-09-30: Qwen3-TTS primary, Kokoro fallback; see docs/studio/03)
- [ ] Spikes X2–X6: talking head (X2 resumes in card 005), persona, visuals and music (X4 is card 012), Judge, hero shots

## Later / ideas
- YouTube links (from the bot and the CLI): designed and spiked on 2026-09-28, then deferred because of proxy cost. See ADR-17 and `docs/superpowers/specs/2026-09-28-youtube-ingest-design.md` §9. The next attempt should download audio first plus per-clip 1080p ranges (about $0.50 per 30 minutes of video), or use a flat-price ISP proxy.
- Sub-projects from the 2026-09-28 brainstorm: split-screen layouts; silence/filler removal (pacing)
- Hook-first reordering (teaser line in first 2 s)
- Emphasis zoom-ins
- Translated caption variants
- Publishing APIs (YouTube Data API, Instagram Graph API, TikTok Content Posting API). Option looked at on 2026-09-29: Postiz cloud (from $29/mo, official APIs, public `POST /public/v1/upload` + `/posts`) as a publisher behind the same posting queue, once posting 6 clips a day by hand gets tedious. Self-hosted Postiz doesn't fit ADR-9 (needs Postgres, Redis and Temporal on a server).

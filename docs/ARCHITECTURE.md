# Architecture

ClipForge is a studio that runs many short-video channels: each account has a type, and every account runs the same loop, produce → review → publish → measure → scale (see the [README](../README.md)). **This document describes what is built today:** the `clips` producer (the step chain below), the posting assistant, and the S1 data layer (Postgres, accounts, sources). The full studio design, with the other producers, review tiers, publishing and measurement, is [studio/02-target-architecture.md](studio/02-target-architecture.md).

Everything runs serverless on Modal (ADR-9). Nothing runs on a local machine except development: tests, and deploys through `scripts/deploy.sh` (owner only).

## Overview

```
Telegram ──webhook──►┐
CLI / curl ──HTTPS──►├─ web (FastAPI, CPU)  POST /jobs · GET /jobs/{id} · POST /jobs/{id}/resume
                     │                        GET /jobs/{id}/download?exp=…&sig=… · POST /telegram/webhook
                     │                        GET /posting · POST /posting/rebuild · POST /posting/restore
                     │                        /accounts · /sources · /posting/import|verify · /jobs/backfill
                     └── creates Job in Dict (and its `jobs` row in Postgres), spawns ▼

 ingest_step ─spawn─► transcribe_step ─spawn─► highlights_step ─spawn×N─► clip_step(clip_01…N)
   (CPU)                (GPU L4)                  (CPU + Haiku)             (CPU: reframe→captions→render)
                                                                                   │ last one to finish
                                                                                   ▼ (atomic claim)
                                                                             package_step (CPU) ─► done
 sweeper (cron, every 10 min): stalled jobs → failed "stalled at <stage>"
 posting_tick (cron, every 5 min; plan C): the next clip to the owner's phone at each slot
 posting_daily (cron, daily 07:00 UTC; ADR-46): keep-alive + snapshots, verify, backfill, schedule sync, rebuild
```

- Interfaces (Telegram bot, CLI, and the dashboard in `web/`, Next.js) never touch the pipeline directly. They create jobs and read status through the job API (ADR-2).
- Each `*_step` is a Modal function that wraps a Modal-free stage module in `stages/` (ADR-9, ADR-12). The wrapper loads the job, reloads the Volume, runs the stage through `jobs.cached_stage`, commits the Volume, records the transition, and spawns the next step.
- Stages are cached by input (ADR-8), so step retries (`max_retries=2`), duplicated spawns and `resume` are safe.
- `app.py` is the only Modal module. `runtime.py` adapts the Modal Dict, Volume and functions to the chain's `KV`, `Volume` and `Spawner` interfaces. Images install the project from `uv.lock` (`Image.uv_sync`), so Modal runs the versions the tests ran.
- `GET /jobs/{id}` returns a `JobView` whose `download_url` (a fresh signed link) is filled in once the job is done. The CLI and the bot's `/status` print it. The webhook is registered with `uv run clipforge set-webhook`.

## Job lifecycle

1. `POST /jobs {input}` (or `/clip <link>` in Telegram) creates the job with status `queued` and spawns `ingest_step`.
2. Each step runs its stage, then spawns the next step. Stages call `ctx.report(stage, pct, message)` on their `jobs.JobContext`.
3. `highlights_step` selects the top `n` clips and spawns one `clip_step` per clip. Clips render in parallel.
4. When a clip is rendered, the bot sends it right away as a Telegram video (a `clip_ready` event).
5. The last clip to finish claims `package_step` (`Dict.put(..., skip_if_exists=True)`, so exactly one runs). It writes the output folder, `metadata.json` and the zip. The status becomes `done` and the bot sends a signed download link for the zip.
6. On an error, the job becomes `failed` with the stage and a sanitized message. A job not updated for longer than its current step's timeout plus 5 minutes is marked `failed` by the sweeper. `POST /jobs/{id}/resume` continues from the first incomplete step.

Status values: `queued | running | done | failed`.

Full design: [docs/superpowers/specs/2026-09-23-serverless-pipeline-design.md](superpowers/specs/2026-09-23-serverless-pipeline-design.md).

- **State (ADR-14):** every Dict key has exactly one writer. `job:<id>` is the core record and `job:<id>:clip:<clip_id>` holds per-clip state. Claims (`package`, `failed`, Telegram `update_id`) use set-if-absent. Steps pass only IDs. `metadata.json` on the Volume is the durable record.
- **Durable state in Postgres (ADR-26, ADR-41):** Neon, through `db/` (SQLAlchemy Core, psycopg 3, Alembic in `alembic/`). It holds accounts, sources, the posting queue and a `jobs` table (job summaries and per-stage `costs`), written best-effort by job create, `package_step`, the failure path and resume, and backfilled from `metadata.json`. `GET /jobs/{id}` and the overview read the `jobs` table first, then the Dict, then `metadata.json` (#207). Claims and in-flight step keys stay on the Dict. One engine per container (`app._database()`), connected lazily; every transaction has a 5 s statement timeout. Without `DATABASE_URL` everything runs Dict-only, as before S1. Migrations use `DATABASE_URL_UNPOOLED` only and run in the CI deploy job before `modal deploy`; `app.py::db_doctor` checks the revision, the pooled host and the schedule copies, read-only.
- **Errors (ADR-15):** transient errors are retried twice. `PermanentError` fails at once. Clips can partially succeed. LLM validation is judged per window. Sources over 3 h or 4 GB, or without audio, are rejected before GPU time.
- **Notifications:** a `Notifier` (`clip_ready`, `done`, `failed`) is attached by the step wrapper when the job came from Telegram. Notifier failures never fail a step. With `DASHBOARD_URL` set, bot messages carry URL buttons to the dashboard (ADR-44).
- **Ops alerts (ADR-45, `ops.py`):** failures that would otherwise be silent go to the owner chat (`POSTING_CHAT_ID`, else the first allowed user): failed jobs without a Telegram target, queueing errors, tick and daily-cron errors, posting off, missing schedule copies, mirror failures and verify differences. One per (kind, subject) per hour, at most 20 an hour, held during quiet hours (23:00–08:00 in `OWNER_TIMEZONE`) and folded into one message at the next tick. An alert never fails a step.

## Stages and contracts

All contracts are pydantic models in `src/clipforge/models.py`. Paths inside contracts are relative to `JOBS_ROOT` (the Volume mount, `/jobs`).

| Stage | Step | Input | Output | Compute |
|---|---|---|---|---|
| ingest | `ingest_step` | `JobInput` (direct URL or Telegram upload, `permission`) | `SourceMedia` (mp4 or mkv with the streams copied, 16 kHz wav, duration, fps, display size, rotation, source hash) | CPU |
| transcribe | `transcribe_step` | `SourceMedia` | `Transcript` (language, segments, `Word[]` with start/end/speaker) | GPU (L4) |
| highlights | `highlights_step` | `Transcript`, `ClipOptions` | `HighlightsResult` (ranked `ClipCandidate[]`, prompt version, model) → top-n `ClipSpec[]` | CPU + LLM API |
| reframe | `clip_step` | `ClipSpec` | `CropTrack` (per-shot crop boxes around the largest face, cuts between speakers in multi-person shots, or blur segments) | CPU |
| captions | `clip_step` | `ClipSpec`, `Transcript` | `CaptionFiles` (`.ass` + `.srt` paths, time offset) | CPU + LLM API (key words) |
| render | `clip_step` | `Timeline` (built from `ClipSpec`, `CropTrack`, `CaptionFiles` by `stages/timeline.py`) | `RenderedVideo` (path, encoder, ffprobe info, loudness), wrapped into `RenderedClip` | CPU (libx264) |
| package | `package_step` | `RenderedClip[]`, metadata | `PackageResult` (`PackagedClip[]`, `metadata.json` as `JobMetadata`, zip) | CPU |

### Timeline (ADR-31, S4)
- **The only render input.** `render` takes a `Timeline`:
  - contiguous visual segments: a `VideoSegment` (source, b-roll or talking head, framed by crop, cover or blur), or a `StillSegment` (optional Ken Burns);
  - audio tracks: source, narration, and music, which can be ducked under the voice;
  - one ASS overlay holding the captions and the hook title card (#340);
  - `assets`, for the policy gate.
- **One ffmpeg encode per Timeline.** `stages/render_graph.py` builds the inputs and filtergraphs. A clip Timeline (`timeline.for_clip`) gives exactly the v3 clip graph.
- **Two-pass loudness** (`stages/loudness.py`, #341). A measurement pass runs first, then the encode.
- **Cache key** (#342, #343): the Timeline without `assets`, without the paths of hashed media, and without the srt path.
- **Short video:** a Timeline with produced media whose picture ends early fails with `PermanentError`. Clip Timelines keep v3's behavior (#345).
- `render.STAGE_VERSION` 4.

### Key rules
- **Caching (ADR-8):** each stage output lives at `/jobs/cache/<stage>/<key>/`. The key is built from the narrowest inputs that determine the output, plus the stage version and the prompt/model version. If `result.json` exists and validates, the stage is skipped.
- **Boundaries:** clip start/end snap to word boundaries, preferably sentence ends or silences ≥ 300 ms.
- **Per-clip work only:** reframe and render operate on the clip's exact time range (`ClipSpec.start/end`). Render uses a single accurate-seek encode with no padding, and caption times are relative to `ClipSpec.start`.

## Highlight selection

1. Split the transcript into overlapping windows (~5 min, 30 s overlap).
2. For each window, the LLM proposes candidates using `prompts/highlights_v<N>.md` and returns JSON.
3. Merge and deduplicate overlaps (IoU > 0.5 → keep the higher score).
4. Filter by length options and rank by score. Keep the top `n` when `n` is given. Otherwise it's automatic: keep every candidate scoring at least `min_score` (default 0.80), at most 30 (`pipeline/selection.py`). If none qualifies, the job fails with the best score and a hint (`--min-score` / `--n`). The threshold is applied after the highlights cache, so trying another `n` or `min_score` reuses it.
5. Later (Phase 5): combine the LLM score with audio energy, laughter and heatmap signals, then a learned ranker.

## Reframing: what's left for Phase 3

Per-shot face framing (ADR-19) and cutting to the speaker in multi-person shots (ADR-21) are done (see Phase 1 stage details). Still open: audio diarization (pyannote) where the visual speaker choice is wrong, and a crop center smoothed with EMA/Kalman for people who move a lot within a shot, reset at cuts.

## Phase 1 stage details

- **Ingest:** streams are copied, never re-encoded (render re-encodes each clip anyway): mp4 for H.264/HEVC with AAC/MP3, mkv otherwise, and a transcode only if copying fails. Sources without a container duration (browser or screen recordings) are accepted, and the duration limit is applied to the normalized copy.
- **Reframe (ADR-19):** landscape sources in `auto` are cut at camera changes (ffmpeg scene score > 0.2, shots under 0.5 s merged). Each shot is cropped to 9:16 around its largest face: YuNet, the median of 3 samples, and faces at least 4% of the frame width. The crop is fixed per shot. Shots without a face, and any detection failure, use the blurred fit. Render cuts the video into segments, crops or blurs each, and rejoins them in one encode. Already-9:16 and near-square sources, and forced `center`/`blur`, keep the fixed crop or fit. In shots with two or more people (ADR-21), the crop follows whoever is talking: each word goes to the seat whose mouth moved most (mouth motion minus head motion, sampled at 10 fps), turns last at least 2 s, and switches are hard cuts mid-pause. People who fit in one crop are framed together.
- **Captions:** Anton (OFL, `assets/fonts/`), uppercase, white with a 7 px black border, ≤ 3 words per line, one caption per line (short pauses are bridged so captions don't flicker). Key words chosen by Haiku (`prompts/keywords_v2.md`, ADR-18) are yellow, with at most one per line and one per 4 words. If the reply is invalid twice, the clip keeps plain white captions. Bottom-center with MarginV 380 on 1920, just above the platform UI in the bottom 20%. ASS control characters in speech are stripped. A hook title card, the LLM's `title` (≤ 10 words, uppercase), is shown top-center for the first 3 s with a 0.3 s fade, and its key word, chosen in the same `keywords_v2` call, is yellow. Every caption line pops in, from 110% to 100% over 0.1 s (ADR-20).
- **Render:** one libx264 encode per clip (accurate `-ss`, crop or blur-fit, ASS burn-in), AAC 48 kHz 128 kb/s, video capped at `min(8 Mb/s, 45 MB·8/duration − audio)` so every clip fits Telegram's 50 MB. The video bitrate is also capped by the source's short side (so a vertical 720x1280 video counts as 720p): ≤ 480 p at 3 Mb/s, ≤ 720 p at 5 Mb/s. Audio is normalized to -14 LUFS (TP -1.5, LRA 11) in two passes: a measurement, then a linear `loudnorm` where the true peak allows (ADR-20 targets; ADR-47, log #341). Render's input is a `Timeline` (see above).
- **Package:** `<job_id>/output/clip_NN_scoreX.XX/{video.mp4,captions.srt,post.md}`, `metadata.json` (with per-clip costs merged in), and an uncompressed `job.zip`.

## Transcription (ADR-11)

faster-whisper `large-v3-turbo`, fp16 batched with word timestamps, on a Modal L4. The image (`nvidia/cuda:12.8.1-cudnn-runtime`, CTranslate2 4.8.2, faster-whisper 1.2.1, PyAV 17.0.0: 18+ breaks faster-whisper) has the weights baked in. Run `uv run modal run src/clipforge/app.py::doctor` after changing any of these versions.

## Inputs (ADR-10)

Direct HTTP(S) media links and Telegram uploads up to 20 MB. YouTube is not supported: it blocks Modal's egress IPs (spike, 2026-09-23). A residential-proxy design was spiked and deferred on cost (ADR-17). Links are checked on every redirect hop (at most 5): hosts that resolve to loopback, private, link-local or other non-public addresses are refused (SSRF). Download errors name only the host and status, never the URL (it can carry the bot token or signed query strings).

## Storage and delivery (ADR-13)

- Modal Volume `clipforge-jobs` mounted at `/jobs`:
  - `/jobs/cache/<stage>/<key>/` holds cached stage outputs, shared across jobs;
  - `/jobs/<job_id>/output/` holds the delivered clips, `post.md` and `metadata.json`;
  - `/jobs/<job_id>/job.zip` is the zip.
- Writers call `volume.commit()` after a stage. Readers in another container call `volume.reload()` first.
- Delivery: each clip is sent as a Telegram video (under 50 MB). The zip is sent as a signed, expiring link served by `GET /jobs/{id}/download`.
- Later (Phase 4): sync finished folders to Google Drive or R2.

## Local inbox (ADR-22)

`videos/<channel>/*.mp4` plus `videos/channels.toml` (credit, url and permission per channel; superseded by S1's database sources at the rollout, see below). `uv run clipforge clip` uploads and submits every new video with its channel, then exits. `--fetch` waits for the jobs in parallel and downloads each into `videos/out/<channel>/<episode>/`. `videos/.clipforge.json` keeps each video's job and whether it was fetched.

## Accounts, blueprints and sources (S1)

- **Blueprints** (`blueprints/<name>.toml`, ADR-35, mounted into the images) describe a channel concept; an **account** is a blueprint plus a language, handles, platforms and a posting schedule (`clipforge account create|edit|list`). ADR-42 moves blueprints into versioned database rows later (S3c).
- **Sources** are database records (option B): a permission record (type, platforms, monetization and translation yes/no/unknown, expiry, evidence), a `source_events` history, and hold rules (expired or narrowed permissions hold clips at enqueue and at the tick). `videos/<source-id>/` is the only local mapping. `clipforge source import-toml` imports `videos/channels.toml` once at the rollout; until then `clipforge clip` falls back to the file only when the API answers 503 "DATABASE_URL is not configured" (#98).

## Posting queue (ADR-23)

When a channel job finishes, `package_step` queues its clips (`post:<job>:<clip>` in the job Dict, skipping moments already queued). A clip's status (queued, sent, partly posted, posted, skipped, rejected, unavailable) is derived from one-writer keys: `sent:<n>`, `posted:<platform>`, `verdict`, `unavailable`. `GET /posting` (and `clipforge status`, `/status`) shows per-channel progress. `POST /posting/rebuild` re-queues finished channel jobs; it skips a job whose files are gone instead of stopping. Clips are queued before the job is saved as done, so a crash in between can't lose them. A re-cut can bring back a moment whose clip was rejected or whose video went missing. Code: `src/clipforge/posting/` (Modal-free).

- **Stores (ADR-41):** a `PostingRepo` with Dict, Sql and Dual implementations. `STATE_READS` (`dict`, the default and the rollback, or `postgres`) picks the primary; with a database wired, every write is repeated on the other store, best-effort, and `posting verify` compares them daily. Items are `ContentItem`s; their platforms are frozen at enqueue (the account's enabled platforms ∩ the source permission). Every tap and command writes through `posting/actions.py` with an actor (`telegram:<id>`, `web:<login>`, `cli:<user>`), kept as `post_events.data.actor`; a database error answers "Store unavailable, nothing changed".
- **Settings:** in `dict` mode, `POSTING_CHAT_ID` (off when unset), `POSTING_TIMEZONE`, `POSTING_SLOTS`, `POSTING_HASHTAGS` describe account #1 (`POSTING_ACCOUNT_ID`); in `postgres` mode each account holds its own schedule. `8:00` and `#tag` are normalized. Any other mistake turns posting off with the reason in `/status` (`Settings.posting_problem`), never the app, because every step loads the same settings.
- **Expiry (ADR-24):** Modal Dict entries expire after 7 days without reads or writes, and the queue lasts weeks. The daily cron `posting_daily` (07:00 UTC; it was `posting_keepalive`, ADR-46) reads every `post:*`, `job:*` and `posting:paused` key, then writes a JSON snapshot of the `post:*` keys (and the paused flag, for the record) to `/jobs/posting/snapshots/<date>.json`, keeping the last 14. `POST /posting/restore[?date=YYYY-MM-DD]` (bearer token), or `clipforge status --restore [DATE]`, puts back `post:*` keys missing from the Dict using that day's snapshot, or the newest readable one without a date. It only fills in missing keys from that snapshot, never overwrites, and never restores `posting:paused`, so it can bring back a ✅ that was undone after that snapshot: check `/status` afterwards. Runbook: after an outage of about 6 days or more, `/pause`, run `clipforge status --restore <last good date>`, check `/status`, then `/go`. Code: `posting/keepalive.py`. The Dict touch retires at the end of S1's migration (ADR-41, Task 23); the rest of `posting_daily` stays: with a database it also runs `posting verify`, backfills missing `jobs` rows, rewrites the schedule copies, runs `rebuild`, and snapshots the posting and source tables to `/jobs/posting/snapshots/db-<date>.json` (keep 14). Code: `posting/daily.py`. If it finds its newest snapshot more than 2 days old (an outage, so Dict keys may have expired), it sets `posting:outage`: rebuild is skipped (a manual `POST /posting/rebuild` or `clipforge status --rebuild` answers 409 with how to clear it, #220) and the tick sends nothing until `/go` or a restore clears it, and `/status` says so first (#217).

## Posting assistant (ADR-23)

`posting_tick` runs every 5 minutes. When a slot from `POSTING_SLOTS` (in `POSTING_TIMEZONE`) is at most 30 minutes old, it claims the slot (a set-if-absent claim, so overlapping ticks send once) and sends the best eligible clip to `POSTING_CHAT_ID`: the video (with its probed width, height and duration, so Telegram shows the 9:16 frame, #221), then an HTML text replying to it with one copy block per platform (TikTok, Instagram, YouTube) and the buttons. ✅ per platform toggles `posted:<platform>`, ⏭ Skip sends the next clip (the skipped one returns after 24 h), and 🗑 Reject asks for an optional reason. After 2 unanswered clips the slots pause and one reminder is sent. `/status`, `/next` (ignores the pause), `/pause` and `/go` work from the phone. If either part of a send fails, the delivered part is deleted, nothing is recorded, and the slot is released for the next tick. Code: `bot/posting.py`; the webhook registers `callback_query` updates (re-run `clipforge set-webhook` after deploying).

Per account (S1, ADR-41): the tick loops over accounts in id order, each with its own chat, time zone and slots. It computes the slot from the Dict copy `posting:schedule:<account>` (written only by the accounts service) and reads Postgres only when a slot is due. Before claiming a slot it checks whether a send is already recorded for it, so a lost or renamed claim can't send a slot twice (#202). `/next`, `/pause` and `/go` take an optional account. The Facebook button appears where an item is due on Facebook, campaign tags, links and `#ad` are added at send time, and expired or narrowed permissions hold clips. One account's failure never stops the others.

## Studio direction (accepted, not built yet)

The multi-account studio is planned in [docs/studio/](studio/README.md), and its build order is Phase 6 in ROADMAP.md. S1 built ADR-25 (`ContentItem`, accounts, sources as database rows), ADR-26 (Postgres for durable state) and ADR-35 (blueprints, mounted from `blueprints/`), and S4 built ADR-31 (the Timeline); they are described above. ADR-42 moves blueprints into versioned database rows later (S3c). The accepted decisions that will change this document when they're built:
- **ADR-27:** one `dispatcher` cron replaces `posting_tick` and runs every periodic task when it's due (the per-slot plan, review-card and hand-off phases, the 09:00 digest, publish reconcile, the alert fold); `sweeper` and `posting_daily` stay, so 3 crons (S2a).
- **ADR-28:** a `Publisher` protocol with Upload-Post as the primary and today's Telegram flow as the fallback. Media goes out by signed Volume links first, R2 only if needed. Webhooks are HMAC-checked (S2).
- **ADR-29:** review tiers per account (`review`, `sample`, `auto`) and a pure policy gate on every item (S2). The LLM claim check comes with the Judge in S6.
- **ADR-30:** open media models as `modal.Cls` servers, license-gated by `media/registry.toml` (S5).
- **ADR-33:** tracking links: `GET /go/<slug>` on the `web` endpoint logs a click (no IP or user agent) and redirects with a sub-id per account, item and platform; bio and affiliate links are wrapped when copy is frozen (S2c). Conversion import is draft ADR-51 (S7).
- **ADR-34:** `clipforge fetch` runs yt-dlp locally into `videos/<channel>/` for permitted sources (S11).
- **ADR-38:** the Next.js dashboard on Vercel is the operational UI. It calls a separate `admin` Modal endpoint with proxy auth and the bearer token, because the public `web` endpoint must stay reachable for webhooks, download links and `/go`. Notion is a one-way mirror (S3).
- **ADR-39:** AI-persona accounts keep provenance metadata and platform AI labels, and use synthetic-only training data (S13).

## Observability and cost

`metadata.json` per job records per-stage duration, GPU seconds, LLM input/output tokens, estimated USD, model names, prompt versions and git SHA. Prices live in `config.Prices`.

Estimated cost per source hour: transcription ~$0.05 (L4), highlights ~$0.07 (Haiku 4.5), plus CPU steps ~$0.03 per job.

## Security

- The bot only answers `TELEGRAM_ALLOWED_USER_IDS`. The webhook checks Telegram's secret-token header.
- The job API requires a bearer token. Download links carry an HMAC signature with an expiry. A missing secret makes its route answer 503, never run open.
- Job ids are validated (`jobs.is_job_id`) before any path is built, and served files must stay inside `/jobs`. The OpenAPI docs routes are disabled.
- Secrets come from the Modal secret `clipforge-secrets` (and `.env` for development), never from code or logs.

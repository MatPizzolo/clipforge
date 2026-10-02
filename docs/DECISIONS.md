# Architecture Decision Records

Short records of decisions. Add a new ADR instead of editing an accepted one; mark old ones "Superseded by ADR-N".

Template:
```
## ADR-N: Title
Date: YYYY-MM-DD · Status: Proposed | Accepted | Superseded
Context: ...
Decision: ...
Consequences: ...
```

---

## ADR-1: Modal for compute and hosting
Date: 2026-09-23 · Status: Accepted (reaffirmed by ADR-9)
Context: Bursty workload (a few jobs a day, spikes later) that needs GPUs for minutes at a time.
Decision: Run all stages and web endpoints on Modal; per-second GPU billing, `.map()` for fan-out.
Consequences: Near-zero idle cost and easy scaling. Lock-in is limited by keeping stage logic in plain Python modules that Modal only wraps.

## ADR-2: One job API, thin interfaces
Date: 2026-09-23 · Status: Accepted (reaffirmed by ADR-9)
Context: Both a Telegram bot and a web app are wanted.
Decision: A FastAPI job API is the only entry point; bot and web app are clients of it.
Consequences: New interfaces are cheap; the API must expose progress and events.

## ADR-3: Output folder instead of auto-publishing (for now)
Date: 2026-09-23 · Status: Accepted (updated by ADR-28: publishing through Upload-Post)
Context: Publishing APIs need account setup and app review; manual upload doubles as a quality check.
Decision: The pipeline ends at a packaged folder with per-platform copy in `post.md`.
Consequences: Revisit when manual upload becomes the bottleneck.

## ADR-4: LLM for highlight selection, learned ranker later
Date: 2026-09-23 · Status: Accepted
Context: No labeled data at the start.
Decision: A small, cheap LLM with a versioned prompt; collect 👍/👎 from day one to train a ranker later.
Consequences: Prompt quality drives early results, so an eval set is required before prompt changes.

## ADR-5: Job state in Modal Dict for the MVP
Date: 2026-09-23 · Status: Superseded by ADR-26 (2026-09-29)
Context: Need simple shared state for progress.
Decision: Modal Dict keyed by `job_id`; ratings and history in SQLite on the Volume.
Consequences: Move to Postgres if history queries or multi-user features grow.

## ADR-6: Local worker for the MVP
Date: 2026-09-23 · Status: Superseded by ADR-9
Context: Telegram bots can download user files only up to 20 MB and upload up to 50 MB, and a 5-clip zip is about 150–200 MB. YouTube often blocks downloads from datacenter IPs. The owner wants output on their own computer.
Decision: The Telegram bot (long polling) and the CPU stages (ingest, highlights, reframe, captions, render, package) run on the owner's machine, and output stays in a local `JOBS_ROOT`. Only transcription runs on Modal (L4 GPU), receiving the audio as bytes. Stage code never imports Modal; `app.py` is the only Modal module, and the orchestrator gets the transcriber through a `Backends` object.
Consequences: No public URL, webhook or file-size workarounds are needed. The bot answers only while the machine is on. Moving stages back to Modal (Phase 4 web app) only means changing `Backends`.

## ADR-7: In-process job service for the MVP
Date: 2026-09-23 · Status: Superseded by ADR-9
Context: ADR-2 makes a FastAPI job API the only entry point, but with ADR-6 the bot and CLI run in the same process as the pipeline.
Decision: `service.py` (create/get/run job) is the single entry point. The CLI and the bot call it directly. The FastAPI layer wraps the same service when the web app arrives.
Consequences: One fewer dependency and no local HTTP server. Interfaces stay thin because they still go through one service.

## ADR-8: Stage cache keys and storage layout
Date: 2026-09-23 · Status: Accepted
Context: Stages must skip work when their output already exists for the same input (CLAUDE.md rule 1), and Phase 2 wants re-cuts to reuse transcripts and highlight scores across jobs.
Decision:
- Key = `sha256(stage name + explicit STAGE_VERSION + canonical JSON of the inputs + prompt/model versions)`, truncated to 16 hex characters (`hashing.cache_key`). The git SHA is recorded in `metadata.json` but is not part of the key, so unrelated commits don't invalidate caches.
- Stages key on the narrowest input that determines their output, never on whole job-level models. Examples: ingest on the source URL or file hash; transcribe on `source_hash` + language + model; highlights on the transcript + min/max length + language (not `n`); per-clip stages on `source_hash` + start/end + the options they use (never rank or clip_id).
- Cached outputs live at `<JOBS_ROOT>/cache/<stage>/<key>/`, shared by all jobs. Job files live at `<JOBS_ROOT>/<job_id>/` (`job.json`, `output/`, `job.zip`). Paths inside contracts are relative to `JOBS_ROOT`.
- A cached output that no longer validates against its contract is treated as a cache miss, not an error.
Consequences: Re-running a job or re-cutting the same source reuses earlier work. Changing a stage's behavior requires bumping its STAGE_VERSION. A pinned-value test guards `cache_key`.

## ADR-9: Fully serverless runtime
Date: 2026-09-23 · Status: Accepted
Context: ADR-6 ran the bot and CPU stages on the owner's machine. The owner wants nothing running locally: everything on serverless cloud (Modal for compute, plus third-party APIs).
Decision: Every runtime component runs on Modal: the job API and Telegram webhook (web endpoint), each pipeline step (Modal functions), and scheduled maintenance (cron). The owner's machine is used only for development: editing code, running tests, and `modal deploy`. ADR-1 and ADR-2 apply as originally written. From ADR-6 we keep the rule that stage modules never import Modal; only `app.py` (and the step wrappers it defines) does.
Consequences: No machine needs to stay on, and nothing listens on a home network. Inputs and outputs have to be reachable from the cloud (ADR-10, ADR-13). The CLI becomes a thin client of the deployed job API. `FileJobStore` remains for tests.

## ADR-10: Direct media links only; no YouTube in the serverless MVP
Date: 2026-09-23 · Status: Accepted
Context: A spike on 2026-09-23 ran yt-dlp (latest) on 3 Modal containers with 3 different egress IPs (AWS and Azure ranges). All 3 were refused by YouTube with "Sign in to confirm you're not a bot", even for metadata only.
Decision: Ingest accepts direct HTTP(S) media links (downloaded with httpx) and Telegram file uploads up to 20 MB (the Bot API download limit). yt-dlp is not a dependency.
Consequences: Sources must be hosted somewhere that serves the file directly, such as your own storage or a public bucket. Google Drive links (a confirmation page for large files) remain a Phase 4 item. YouTube can return later through a residential proxy; account cookies were rejected because of the risk to the account.

## ADR-11: Own Whisper on Modal L4 instead of a transcription API
Date: 2026-09-23 · Status: Accepted
Context: Hosted transcription APIs would remove the GPU image. `doctor` showed our image working on L4: CUDA 12.8 + cuDNN 9, CTranslate2 4.8.2, faster-whisper 1.2.1, `large-v3-turbo` baked in, 2.2 s model load, 14 s round trip including cold start.
Decision: Keep faster-whisper `large-v3-turbo` (fp16, batched, word timestamps) on a Modal L4.
Consequences: About $0.05 per source hour versus roughly $0.25–0.45 for hosted APIs, and audio never leaves Modal. We maintain a pinned CUDA image, and `doctor` is the check to run after bumping any of its versions.

## ADR-12: Event-driven step chain with atomic fan-in and a stall sweeper
Date: 2026-09-23 · Status: Accepted
Context: A job runs ingest → transcribe → highlights → per-clip work → package, with minutes of GPU and CPU time. Options considered: one big function; a waiting orchestrator plus `.map()`; a chain where each step spawns the next. The owner chose the chain.
Decision:
- Each pipeline step is its own Modal function (`ingest_step`, `transcribe_step` on L4, `highlights_step`, `clip_step`, `package_step`). Each is a thin wrapper around a Modal-free stage module: load the job, reload the Volume, run the stage through `cached_stage`, commit the Volume, record the transition, then `.spawn()` the next step.
- `highlights_step` spawns one `clip_step` per selected clip (reframe → captions → render). Each clip marks itself done. The clip that sees all clips done claims package with `Dict.put(key, value, skip_if_exists=True)`, which returns `True` only for the first caller. Only that caller spawns `package_step`.
- Every step has `modal.Retries(max_retries=2)`. Stages are cached by input (ADR-8), so retries, duplicated spawns and resumes are safe.
- A `sweeper` cron (every 10 min) marks jobs with no progress for 15 min as `failed` with "stalled at <stage>". `POST /jobs/{id}/resume` works out the next step from the job's state and spawns it.
Consequences: No container sits idle waiting on another, clips render in parallel, and a crash loses at most one step. The cost is more moving parts than a single orchestrator, and a failure between commit and spawn is caught only by the sweeper.

## ADR-13: Delivery from the Modal Volume via Telegram videos and a signed link
Date: 2026-09-23 · Status: Accepted
Context: Output no longer lands on a local disk. Telegram bots can upload at most 50 MB per file, and a 5-clip zip is about 150–200 MB.
Decision: Output stays on the Modal Volume (`/jobs`). The bot sends each clip as a Telegram video, encoded to stay under 50 MB, as soon as it is rendered. When the job finishes, it sends a signed, expiring download link for the zip. The link is served by `GET /jobs/{id}/download` on our API and authorized by an HMAC signature with an expiry.
Consequences: No new storage vendor. Links stop working if the Volume is cleaned, so a retention policy is needed later. Syncing to R2 or Drive stays in Phase 4.

## ADR-14: Job state as single-writer Dict keys
Date: 2026-09-23 · Status: Accepted (refines ADR-5; replaces the `job.json` part of ADR-8)
Context: With the step chain (ADR-12), several containers update one job at the same time, for example parallel clip steps reporting progress and cost. A single read-modify-write record would lose updates.
Decision: Each Dict key has exactly one writer:
- `job:<id>` (core record) is written only by the step that currently owns the job, the failure path, resume and the sweeper;
- `job:<id>:clip:<clip_id>` is written only by that clip's step;
- attempt counters are written only by their step;
- claims (`package`, `failed`, `tg:update:<id>`) use `put(..., skip_if_exists=True)`.
Steps pass only IDs; inputs come from the Volume through `job.outputs[stage]` pointers. `service.get_job_view()` merges the records. `metadata.json` on the Volume is the durable record, and the view falls back to it.
Consequences: No locks and no lost updates. Reading a job means a few Dict reads. `FileJobStore` remains for tests. Note (2026-09-23): tests use DictJobStore over MemoryKV; FileJobStore was removed.

## ADR-15: Error classes, partial success and per-window LLM validation
Date: 2026-09-23 · Status: Accepted
Context: The chain needs deterministic failure: Modal doesn't tell a function that its current attempt is the last one. A single bad LLM window or clip shouldn't sink a whole job.
Decision:
- Transient errors raise and are retried by Modal (`max_retries=2`).
- `PermanentError(user_message)` fails the job or clip immediately, with no retry.
- The wrapper counts attempts itself and fails cleanly on the third.
- A failure is announced once (`claim:failed`), with a sanitized message.
- Clips can partially succeed: package ships what rendered, and the job fails only if every clip fails.
- LLM validation (CLAUDE.md rule 5) applies per window: a window failing twice is dropped, and the stage fails only if more than 25% of windows fail or no candidates remain.
- Ingest rejects sources over 3 hours or 4 GB, and sources without audio, before any GPU time is spent.
- Refines ADR-12's stall rule: the sweeper fails a job not updated for longer than its current step's timeout plus 5 minutes, instead of a flat 15 minutes, so a long but healthy transcription isn't failed.
Consequences: Worst-case cost per job is about $0.50. A user can get "4 of 5 clips" instead of nothing.

## ADR-16: CI checks on every push, auto-deploy on main
Date: 2026-09-23 · Status: Accepted (CI runs scripts/check.sh; the deploy job is off behind DEPLOY_ENABLED, log #109, #212)
Context: With serverless, deploying is releasing.
Decision: `.github/workflows/ci.yml` runs ruff, a format check, mypy and the fast tests on every push and PR. On `main`, after the checks pass, it runs `modal deploy` using the GitHub secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. GPU and smoke tests run only from a manual `workflow_dispatch` workflow.
Consequences: Merged to `main` means live. CI never spends Modal money automatically. A bad deploy is rolled back by reverting on `main` (or with `modal app rollback`).


## ADR-17: YouTube input through a residential proxy
Date: 2026-09-28 · Status: Deferred (2026-09-28); ADR-10 stays in force
Context: ADR-10 excluded YouTube because it refuses downloads from Modal's egress IPs. The owner wants YouTube links to work from the bot and CLI. Options considered: yt-dlp through a residential proxy, a managed download API (Apify/RapidAPI-style), and account cookies (already rejected in ADR-10 for account risk).
Decision: Ingest recognizes single-video YouTube URLs and downloads them with yt-dlp on Modal, routing only that traffic through a residential proxy (Decodo; `YOUTUBE_PROXY_URL` in `clipforge-secrets`). Best video up to 1080p, H.264 + m4a preferred. Metadata is checked (duration, size, live) before any media is downloaded. The cache key is `youtube:<video_id>`. Proxy bytes are logged as cost. Everything after ingest is unchanged. Adopted only if the spike in the design (3 of 3 downloads from Modal) passes.
Consequences: About $1–3 of proxy traffic per 30-minute video, logged per job. yt-dlp needs updates when YouTube changes. YouTube's terms forbid downloading outside its apps; the owner accepts that, and permission for the content remains the owner's guarantee (docs/SOURCING.md). Design: docs/superpowers/specs/2026-09-28-youtube-ingest-design.md.
Deferred, 2026-09-28: the spike showed the approach works, but it costs too much for the current use (about one video a day). Findings:
- Through Decodo's sticky residential port (`gate.decodo.com:10001`), metadata came back in 3.7 s. YouTube's bot check didn't trigger, and the exit IP stayed the same across requests.
- yt-dlp's default client got HTTP 403 on the media. The `web_safari` and `web_embedded` clients downloaded at 1080p. `tv_simply`, `mweb` and `android_vr` only offered 360p.
- Pay-per-GB residential traffic runs about $3.70/GB (Decodo: $11 per 3 GB). A full 1080p download is about $3 per 30 minutes of video, and the 100 MB trial ran out mid-spike.
- Free downloader sites have no stable API. The official cobalt server has dropped YouTube and requires a captcha token, and its community instance list no longer resolves.
Revisit with: an audio-first download plus per-clip 1080p time ranges (about 90% less traffic, about $0.50 per 30 minutes of video), and/or a flat-price static ISP proxy.

## ADR-18: Key caption words chosen by the LLM
Date: 2026-09-28 · Status: Accepted
Context: The owner reviewed the first clips. Captions should sit lower, and the important words should stand out in color. The word-by-word yellow karaoke highlight made lines busy and emphasized filler words as much as key ones.
Decision: The captions stage asks Haiku once per clip (`prompts/keywords_v1.md`) for the indices of the words to emphasize, and shows those in yellow. It keeps at most one per caption line and one per 4 words, in the LLM's order of importance. The reply is validated with the rule-5 single retry. If it's invalid twice, the clip keeps plain white captions and a warning is logged, so a caption nicety never fails a clip. The karaoke highlight is removed, and each caption line is one event. MarginV goes from 480 to 380, and the border stays at 7 px. The prompt version and model are part of the captions cache key, and `captions.STAGE_VERSION` is now 2.
Consequences: About $0.0005 and one short API call per clip, logged as captions cost. Word choice works in any language without stopword lists. Re-cutting an existing video regenerates only the captions and renders; the transcript and highlights come from cache.

## ADR-19: Face-centered reframing, fixed per shot
Date: 2026-09-28 · Status: Accepted
Context: The Phase 1 center crop cuts off people in multi-camera podcasts, where each shot shows one person in the left or right third. The Phase 3 roadmap planned PySceneDetect + MediaPipe with smoothed tracking.
Decision: Per clip, detect camera cuts with ffmpeg's scene score, then frame each shot on its largest face, found by OpenCV's YuNet detector (the median over 3 sampled frames). The crop is fixed for the shot and moves only at cuts. Shots with no reliable face, and any detection failure, fall back to the blurred-background fit. Render cuts the video into segments, crops or blurs each, and rejoins them in one encode. PySceneDetect and MediaPipe aren't used: ffmpeg and a 230 KB model do the job with one new dependency (opencv-python-headless).
Consequences: A few seconds of CPU per clip, and no API cost. Smoothed tracking and active-speaker choice stay open in the roadmap. Design: docs/superpowers/specs/2026-09-28-face-reframe-design.md.

## ADR-20: Retention polish (loudness, hook title, caption pop, bitrate by source)
Date: 2026-09-28 · Status: Accepted; "single-pass `loudnorm`" updated by ADR-47 (2026-10-01; the targets are unchanged)
Context: The owner posts clips to grow their own channels, so retention and a recognizable style matter most. Clips had uneven loudness, no on-screen hook, static captions, and 8 Mb/s video even for 360 p sources, which made 30 clips about 1.2 GB on a slow downlink.
Decision: The render encode normalizes audio to -14 LUFS (single-pass `loudnorm`). The video bitrate is capped by the source's short side (3/5/8 Mb/s at ≤480/≤720/above, so vertical phone videos count by their width). The captions `.ass` gains a hook title card: the highlights `title`, top-center, first 3 s, one yellow key word chosen by the same per-clip LLM call as the caption key words (`prompts/keywords_v2.md`). Every caption line pops in, from 110% to 100% over 100 ms.
Consequences: No new API calls, since the title word shares the keywords call. Clips from low-res sources are much smaller. The captions and render cache versions move to 3, so re-cuts re-render.

## ADR-21: Cut to the speaker in multi-person shots (visual mouth motion)
Date: 2026-09-28 · Status: Accepted
Context: Single-camera podcasts and the wide shots of multi-camera ones show two people in one shot. ADR-19 frames the largest face, so the crop stays on one person while the other talks. Options: visual mouth motion, audio diarization (pyannote on the GPU, needing torch, a gated-model token and a re-transcribe), or visual first with diarization later.
Decision: Visual first. In a shot with two or more seats (faces seen in at least 2 of reframe's 3 samples), the shot is decoded once at 10 fps in grayscale. Each seat is scored by the change in its mouth patch minus the change in its eye band, and each transcript word goes to the seat that moved most (at least 1.2x the runner-up, otherwise unknown). Runs of words become turns of at least 2 s, and each switch is a hard cut in the middle of the pause between words. Seats that fit together in one 9:16 crop are framed as a group. Any failure falls back to the largest face and isn't cached. The interface is "which seat said each word", so diarization can replace the visual step later.
Consequences: A few CPU seconds per clip and no new dependencies. A listener laughing hard can steal a turn shorter than the hold. Diarization stays open in the roadmap for footage where this is wrong. Design: docs/superpowers/specs/2026-09-28-speaker-framing-design.md.

## ADR-22: Channel folders and batch submit
Date: 2026-09-28 · Status: Accepted (database sources replace channels.toml at the S1 rollout, ADR-25, ADR-41)
Context: The owner clips whole podcast channels, starting with 11 episodes of Billy Garton Jr. (creator agreement), with more channels in the same niche later. Every clip needs the right credit, and the posting assistant (ADR-23) needs to know each job's channel. Waiting for each video in turn took hours.
Decision: Videos go in `videos/<channel>/`. `videos/channels.toml` gives each channel a credit name, an optional url and a permission. `clipforge clip` submits every new video with `JobInput.channel`, `source_credit`, `permission` and `source_label`, then exits. `--fetch` waits for all submitted jobs together and downloads each into `videos/out/<channel>/<episode>/`. The inbox ledger keeps `{job_id, status}` per video; the old format loads as fetched. Spec: docs/superpowers/specs/2026-09-28-posting-assistant-design.md §3.
Consequences: Credit and permission are set once per channel. A video moved into a channel folder counts as new and is submitted again; this is cheap because the transcript and highlights are cached by source hash, and posting skips overlapping moments.

## ADR-23: Phone-first posting assistant with the queue on Modal
Date: 2026-09-28 · Status: Accepted
Context: Clips go to one brand account on TikTok, Instagram Reels and YouTube Shorts, posted by hand from the phone apps (ADR-3), 5–7 a day. The owner wants a queue that scales to any number of videos and channels and always knows what was posted where. A local day-folder queue was designed first and dropped: it needed the laptop at posting time and couldn't know what was actually posted. We also chose not to test on TikTok first and promote winners: a new account's first-day views are mostly noise.
Decision: When a channel job (ADR-22) finishes, `package_step` queues its clips in the job Dict (`post:<job>:<clip>`), skipping moments that overlap a non-rejected clip of the same video (IoU > 0.5). State is split into one-writer keys: sends, per-platform confirmations, a verdict (skipped or rejected with a reason) and unavailable. The status is derived, never stored. A cron sends the next clip at each slot (plan C): the best score with a fresh-episode bonus, never the same video or channel twice in a row while another is eligible. The owner taps ✅ per platform, ⏭ Skip (back after 24 h) or 🗑 Reject. `GET /posting`, `/status` and `clipforge status` show per-channel progress. Enqueue never fails a job; `POST /posting/rebuild` re-queues finished channel jobs idempotently. Spec: docs/superpowers/specs/2026-09-28-posting-assistant-design.md.
Consequences: The laptop is needed only to add videos. Reads scan all `post:*` keys (`KV.items()`), which is fine for thousands of clips; move to an index or SQLite if it grows past that. Reject reasons feed the Phase 5 ranker. API publishing (step B) would replace the ✅ taps and gets its own ADR.

## ADR-24: Keep the posting state alive against Modal Dict expiry
Date: 2026-09-29 · Status: Accepted (implementation: plan C Task 6; refined by ADR-46)
Context: The Plan B review found that Modal Dict entries expire after 7 days without reads or writes (modal 1.5.5 `Dict` docs; our Dict was created in 2026, so the new rule applies). The posting queue (ADR-23) lives in the job Dict and lasts weeks (11 episodes at 6 clips a day is about 55 days). If a posted clip's `posted:*` keys expire, the clip reads as unposted and the bot sends it again. Expired verdicts would bring rejected clips back, and expired items and `job:*` records would silently shrink the queue and hide jobs from `rebuild`. Whether a streaming `items()` read resets the timer is undocumented. Options: a keep-alive read, a Volume snapshot, or making the Volume the record and the Dict a cache (a redesign).
Decision: A daily Modal cron, `posting_keepalive`, reads every `post:*` and `job:*` key (and `posting:paused`) one by one with `get`, which the docs count as activity. It then writes every `post:*` key and value to `/jobs/posting/snapshots/<date>.json` on the Volume, keeping the last 14. A restore, `POST /posting/restore` (bearer token), with `clipforge status --restore`, puts back keys from the newest snapshot only where they are missing (set-if-absent), so it never overwrites newer state. Short-lived claims (`posting:slot:*`, `posting:reminded:*`, `tg:update:*`) are left to expire.
Consequences: A few seconds to about a minute of CPU a day. A week-long cron outage is recoverable from the snapshot. The Volume-as-record redesign stays open if the Dict grows past tens of thousands of keys.

## ADR-25: Multi-account studio with one content-item seam
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S1)
Context: ClipForge serves one brand from one producer (podcast clips). The owner wants 20+ accounts across four kinds (clips, AI stories, bands, AI-avatar affiliate) in English and Spanish, all from one repo.
Decision:
- Every producer ends in a `ContentItem`: video, per-platform copy, AI-disclosure and sponsored flags, credits, asset licenses, cost, account.
- Distribution (queue, review, publish, analytics) consumes only `ContentItem`s.
- An `Account` holds its platforms and per-platform rules, review tier, persona, brand kit, budget and paired-language account.
- `channels.toml` sources become `sources` rows owned by accounts.
Consequences: New content types are new producers only. The clip producer gains a small wrapper step. The ADR-23 `PostItem` is replaced by `ContentItem` + `posts` rows.

## ADR-26: Postgres (Neon) for durable state; Dict only for hot step state
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S1; supersedes ADR-5; retires ADR-24 once migrated; refined by ADR-46)
Context: Modal Dict entries expire after 7 days of inactivity, and ADR-24 works around that with keep-alives. The dashboard needs queries across accounts, dates and platforms (calendar, stats, money) that a key-value scan can't serve. Modal Volumes aren't safe for a database with many writers.
Decision: Neon Postgres, reached through the pooled endpoint with SQLAlchemy 2 + psycopg 3, holds everything durable. Migrations use Alembic. The Dict keeps only in-flight job and step keys and claims (ADR-14); `job:*` summaries move to a `jobs` table too, so nothing durable depends on a Dict entry surviving 7 idle days. The dashboard reaches the data only through the FastAPI API (ADR-2).
Consequences: One new managed dependency, free until it's outgrown. Tests need a local Postgres, and CI a Postgres service. Alembic runs in the deploy job before `modal deploy`. During the switch a setting points reads back at the Dict for rollback. The ADR-24 keep-alive and snapshot are removed a week after the migration is verified.

## ADR-28: Publishing through Upload-Post behind a Publisher protocol
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S2; updates ADR-3 and ADR-23's "API publishing gets its own ADR")
Context: TikTok's own API allows only private posts until an app audit passes. Doing that audit and Meta's app review ourselves is slow. At ~25 accounts × 4 platforms, Upload-Post costs about $50–147/mo. Alternatives: Zernio (~$318/mo), Ayrshare (~$599/mo), self-hosted Postiz (we'd need our own audits).
Decision:
- A `Publisher` protocol with two implementations: `UploadPostPublisher` (primary) and `AssistedPublisher` (the Telegram manual flow from ADR-23).
- Media is served by URL: signed, expiring Volume links first (ADR-13's mechanism), Cloudflare R2 only if those prove unreliable.
- `ai_disclosure` maps to every platform's AI flag.
- Signed webhooks update the `posts` rows.
Consequences: A vendor dependency that can be swapped. Official YouTube and Instagram publishers can be added later behind the same protocol.

## ADR-29: Tiered review with an always-on policy gate
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S2); the tier becomes the Review dial of ADR-48's autopilot model, and ADR-49 sets the producer-version window (2026-10-01)
Context: At 20+ accounts, approving every post by hand is 100+ taps a day. Platforms punish undisclosed AI, mass-produced content and false claims.
Decision:
- Each account has a review tier: `review` (every item), `sample` (auto-post, ~10% spot checks, daily digest) or `auto`.
- A new account, a new format and a new producer version all start in `review`.
- A pure policy gate runs on every item. The LLM claim check joins it with the Judge (ADR-36) in S6, when AI content first appears; clips make no product claims. It checks disclosure, #ad, credits, license manifest, cross-account duplicates, and health and earnings claims.
- Any violation sends the item to `review`.
Consequences: Owner time scales with how new the content is, not with volume. Reject reasons feed the ranker.

## ADR-30: Self-hosted open media models on Modal, license-gated
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S5; models chosen by spikes X1–X4)
Context: The owner rules out paid voice and avatar SaaS, and the target is 20+ accounts. Open models now cover voice (Qwen3-TTS), images (Z-Image), talking heads (InfiniteTalk), music (ACE-Step) and b-roll (Wan2.2). Many popular models are non-commercial (InsightFace packs, FLUX.1-dev, Qwen-Image 2.1, F5-TTS, XTTS, MusicGen).
Decision:
- Each model runs as a `modal.Cls` media server, with weights on a `clipforge-models` Volume, memory snapshots, and GPU step methods inside the class so nothing waits idle (ADR-12).
- Stage logic uses Modal-free protocols in `media/`.
- `media/registry.toml` pins every model's revision and license. A test fails for licenses outside the allowlist.
- Personas are fully synthetic (a designed voice and a generated face with a LoRA).
Consequences: Cents per video instead of a subscription per seat. We maintain GPU images and pins. Spikes X1–X4 must confirm quality and cost before each producer is built.

## ADR-31: Timeline as the single render input
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S4)
Context: Clips crop a source video, while stories, bands and avatars assemble stills, generated clips, talking heads, narration and music. Separate renderers would drift apart in captions, loudness and size limits (ADR-18/20).
Decision: A `Timeline` contract (visual segments, audio tracks, captions, title card, asset sources) is the only input to `render`. The clip producer moves onto it first, keeping identical output properties.
Consequences: One ffmpeg + libass path, with the ADR-20 polish applying everywhere. `render.STAGE_VERSION` bumps once.

## ADR-34: Local download helper
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S11; keeps ADR-10 for the cloud; ADR-17 stays deferred)
Context: YouTube blocks Modal's egress IPs. The owner's home connection works, and permitted sources such as creator agreements still need downloading.
Decision: `clipforge fetch` runs yt-dlp locally, with Deno and the bgutil PO-token plugin, into `videos/<channel>/`. It only downloads for sources whose permission is recorded. yoinks is fine for manual use.
Consequences: The laptop is needed only to fetch sources. Everything else stays serverless.

## ADR-35: Channels as blueprint instances
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S1); "blueprints are files" superseded by ADR-42 (2026-09-30)
Context: The portfolio (07) has 15 concepts in 5 categories, about 19 accounts with Spanish pairs, and it has to grow further. Designing each channel by hand doesn't scale, and YouTube's inauthentic-content rule penalizes templated sameness.
Decision:
- Each channel concept is a versioned blueprint (`blueprints/<name>.toml`): niche, pillars, rotating series formats, voice and visual briefs, platform defaults, money sources, a compliance profile, and prompt names.
- An account is a blueprint plus a language, persona, handles, posting profile, budget and review tier.
- Producers rotate series and structure per item and log the variation.
- EN/ES pairs share a blueprint and link through `paired_account_id`. The Spanish side is a native adaptation.
Consequences: A new account is one command plus platform sign-ups. Blueprint changes are reviewable diffs. The policy gate reads the compliance profile.

## ADR-38: Next.js as the operational dashboard, Notion as a one-way mirror
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S3)
Context: The owner wants one place to run the studio and a readable, shareable planning space. Notion's API is rate-limited (about 3 req/s), can't play R2 video, and allows manual schema edits. A two-way sync would create two sources of truth.
Decision: All operations (accounts, queue, review, thresholds, stats, money, costs) live in the Next.js dashboard over the FastAPI API and Postgres. A `notion_mirror` task writes the planning pack, SOPs and weekly reports to Notion one way, and never reads edits back. The pages say so.
Consequences: Notion is for reading, sharing and thinking. Every change goes through the dashboard or repo.

## ADR-39: AI model / influencer category with provenance kept
Date: 2026-09-29 · Status: Accepted (2026-09-29, kickoff review; built in S13)
Context: Lifestyle AI personas earn from brand deals and affiliate storefronts. Common playbooks strip AI metadata to pass as human, scrape real people's photos for training, and swap faces onto real people's videos.
Decision:
- Category E uses fully synthetic personas, trained only on their own generated images.
- Provenance metadata (C2PA/IPTC) and platform AI labels are always kept.
- "AI creator" goes in the bio.
- No face or body swaps onto real people's footage.
- Sponsored posts are disclosed. No sexual content.
- `ContentItem` gains media kinds `carousel` and `image`.
Consequences: Platform-compliant accounts that can take brand deals openly. Some "indistinguishable from real" growth tactics are deliberately off the table.

## ADR-41: Moving to Postgres by writing to both stores, and posting per account
Date: 2026-09-29 · Status: Accepted (S1; written into this file by card 002, 2026-09-30; completes ADR-26's switch; the Dict writes retire at S1 Task 23)
Context: ADR-26 moves durable state to Neon and asks for a setting that points reads back at the Dict for rollback. The studio also needs several accounts posting on their own schedules (S1 kickoff, 2026-09-29).
Decision:
- A `PostingRepo` protocol with Dict, Sql and Dual implementations. `STATE_READS` (`dict` | `postgres`) picks the primary. Every successful write is repeated on the other store, best-effort, so a rollback flips reads onto a store that is still current. The Dict side serves account #1 only. A mirror failure is an ops alert (ADR-45).
- `posting_daily` (ADR-46, was `posting_keepalive`) compares the two stores daily (`posting verify`). The Dict writes, `STATE_READS`, the `POSTING_*` settings and the Dict keep-alive are removed after at least 7 days of clean verifies.
- Each account holds its posting schedule (chat, time zone, slots, hashtags). The `POSTING_*` settings are read only in `dict` mode and to seed account #1. Pausing is runtime state in `posting_state`, written only by `/pause` and `/go` (through `posting/actions.py`, ADR-44).
- The tick computes the slot from a Dict copy of each schedule (`posting:schedule:<account>`, written only by the accounts service) and reads Postgres only when a slot is due, so Neon can scale to zero between slots.
- "Posted everywhere" means every platform an item was queued on (its `posts` rows), so enabling a platform on an account never changes old clips.
- In Postgres, one writer per column group replaces one writer per key (ADR-14). Claims stay on the Dict.
- The `jobs` table is written best-effort by job create, `package_step` and the failure path, and backfilled from `metadata.json`. The job view and the overview read it first.
Consequences: Two writes per posting action until Task 23, with drift visible in the daily verify. The Telegram buttons keep their format, so messages sent before the switch keep working. Spec: docs/superpowers/specs/2026-09-29-studio-s1-design.md.

## ADR-42: Versioned categories, blueprints and accounts in the database
Date: 2026-09-30 · Status: Accepted (2026-09-30, the owner's review after card 003; built in S3c; supersedes ADR-35's "blueprints are files" part); refined by ADR-48 (the review tier and the budget leave the versioned setup) and ADR-50 (the hook library lives outside it), 2026-10-01
Context: Each account type is very different, and the owner wants to improve every category and every account from the dashboard: edit the setup, keep notes, run experiments and see results. ADR-35 keeps blueprints as files (`blueprints/<name>.toml`), and S1 copies blueprint values into each account row and updates accounts in place, so there is no history, no way to tie a video to the setup that made it, and no dashboard editing. Spec: docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md.
Decision:
- The database is the source of truth for three versioned levels: **category** (the 5 fixed codes: playbook, rules = compliance profile, production defaults), **blueprint** (pillars, series formats, briefs, money, prompts) and **account** (overrides plus identity fields). Effective setup = category, overridden by blueprint, overridden by account; the dashboard shows each value's origin.
- Every save writes a full, validated snapshot with an author and a note, in append-only `*_versions` tables. Restore saves an old version as a new one; history is never rewritten.
- **Accounts pin their parent versions:** an account version records the category and blueprint versions it builds on. Parent saves reach accounts through an explicit "Apply to accounts". `(account_id, version)` fully determines the setup; there is no separate setup id. The pair is stamped on every content item (`content_items.setup_version`) and on every send (`post_events.data.setup_version`).
- The setup is frozen per job at `create_job`, feeds only existing cache-key inputs (ADR-8) and is never part of a cache key. Prompts stay versioned files (CLAUDE.md rule 4); the setup only picks a released version.
- Every field has a change class (live, recut, format, rules, identity). Format changes send the first 10 items to `review` (ADR-29, enforced by S2); rules are never experimented on.
- One dry run, `POST /setup/preview`, returns the diff, the stages a new job re-runs, the affected accounts and items, and the estimated cost. A save, a restore, "Apply to accounts" and an experiment start all show it first and recompute it inside their write, so the preview and the write can't disagree.
- Experiments (change → metric over a window → keep or revert, one running per account) and notes (idea, learning, question) live in the same database. Keep and revert are decided only on the experiment's dashboard page.
- Every write records an actor (`telegram:<id>`, `web:<login>`, `session:<name>`, or S1's `cli:<os user>`): version authors, notes, and a new `post_events.actor` column written by `posting/actions.py`.
- S1's `blueprints/*.toml` and account rows are imported once as version 1 (`clipforge setup import`, `setup verify` at 0 differences), like `channels.toml` became sources. After that the files are no longer read; they stay in the repo until the move has been verified for 7 days.
Consequences: Every video can be traced to the exact setup that made it, and experiments can isolate their accounts. The accounts table becomes a projection of the current version with one writer (ADR-41). Blueprint changes are reviewed as version diffs in the dashboard instead of file diffs. A `SETUP_SOURCE=db|off` switch lets producers fall back to today's constants. Updates ADR-35: channels are still blueprint instances, but blueprints live in the database. `setup_version` (which setup) stays separate from `producer_version` (which code, derived per ADR-43); per ADR-44, setup edits and experiment decisions are dashboard tasks, and Telegram only deep-links to them (the 08 §2b formats, plus `/categories/<code>` and `/blueprints/<name>`); per ADR-45, "experiments need a decision" is a digest line, never an instant alert. ADR-46's daily reconcile is unchanged.

## ADR-43: Producer version is derived; the build SHA is separate
Date: 2026-09-30 · Status: Accepted (2026-09-30; refines ADR-29; replaces the rule in decision-log #85); a version change opens ADR-49's 5-item review window (2026-10-01)
Context: ADR-29 starts a new producer version in `review`. A git SHA changes on every deploy, docs-only ones included, and is "unknown" when deploying from a folder without git.
Decision: `producer_version = "<producer>:" + sha256(sorted STAGE_VERSIONs, prompt names, model ids)[:8]`, computed in code. The git SHA is recorded as `build` on jobs and in metadata only, and never compared. Items read back from the Dict keep `"plan-c"`.
Consequences: Review restarts only when the output logic changes. S1's current code stamps `settings.git_sha or "unknown"` (#85) and must be changed (a card after the 2026-09-30 pause).

## ADR-44: One home per task — Telegram pushes, the dashboard runs
Date: 2026-09-30 · Status: Accepted (2026-09-30; refines ADR-23, ADR-29, ADR-38)
Context: One owner, 20+ accounts, two surfaces. Tasks done in both drift apart and double-notify.
Decision:
- Every task has one home, listed in docs/studio/08 §2. Telegram: time-bound single decisions (assisted posting, review cards for items due soon), alerts that need action, `/pause` and `/go`, one daily digest. Everything that needs context, comparison, editing, bulk actions, history, experiments or money: the dashboard.
- A task in both surfaces needs a written reason in 08 §2 and one backend (`posting/actions.py`, `service.*`), with an actor recorded on every write (`telegram:<user id>` or `web:<login>`).
- A change on either surface shows on the other: dashboard actions redraw or delete every Telegram message of the item; Telegram taps show on the dashboard's next poll.
- Telegram messages deep-link to dashboard pages (`DASHBOARD_URL`); login keeps the target (`callbackUrl`, relative paths only).
- After S2, Telegram keeps review cards, alerts, the brake, the digest and the AssistedPublisher fallback. `/clip` retires when the dashboard's Produce page ships.
Consequences: Fewer messages as accounts grow; one writer per action.

## ADR-45: Notification budget and ops alerts
Date: 2026-09-30 · Status: Accepted (2026-09-30)
Decision:
- Every event is instant, digest or dashboard-only (the policy table in docs/studio/08). The digest goes out at 09:00 in the owner's time zone. Quiet hours are 23:00–08:00; only brake-worthy events (publishing broken across accounts, spend over 2× the daily budget) break through.
- At most one alert per (kind, subject) per hour, deduped by a Dict claim `notify:<kind>:<subject>:<hour>` (ADR-14); at most 20 instant messages an hour, the rest folded into "N more → dashboard".
- Silent failures go to the owner chat through `ops_alert()`: failed channel jobs (no Telegram notifier), enqueue errors, tick and keep-alive errors, Dual-write mirror failures, `posting verify` differences. An alert failure never fails a step.
Consequences: Failures become visible without new services, and the bot stays quiet as accounts grow.

## ADR-46: Daily reconcile instead of retiring the ADR-24 cron
Date: 2026-09-30 · Status: Accepted (2026-09-30; refines ADR-26's "the keep-alive and snapshot are removed")
Decision: `posting_keepalive` becomes `posting_daily`, in the same cron slot (07:00 UTC). While the Dict and Postgres are both written, it runs the Dict touch, the snapshot and `posting verify`. Always, it backfills missing `jobs` rows, runs `rebuild` (both idempotent), and writes a JSON snapshot of the posting and source tables to `/jobs/posting/snapshots/`, keeping 14. The Dict touch goes when ADR-24 retires.
Consequences: A self-healing queue and a cheap backup; the number of crons doesn't change.

## ADR-47: Two-pass loudness normalization for every render
Date: 2026-10-01 · Status: Accepted (2026-10-01, the owner's review of the S4 spec; built in S4, card 006; updates ADR-20's "single-pass `loudnorm`")
Context: ADR-20 normalizes every clip with a single-pass `loudnorm` (I=-14, TP=-1.5, LRA=11), which estimates loudness on the fly and applies dynamic gain. ADR-31 makes one Timeline renderer serve every producer, and from S6 on many Timelines mix narration over a ducked music bed, where a dynamic gain can work against the ducking. Measured on 2026-10-01 (S4 spec §6): single pass lands at -14.5 to -14.2 LUFS on five real clips and -14.1/-13.8 on two synthetic mixes; two passes land at -14.2 to -14.0. On the real clips, ffmpeg falls back to dynamic mode in pass 2 because the sources already peak near the true-peak limit; linear mode applies to the mixes.
Decision: Every render measures first (pass 1: the audio graph only, `loudnorm` with `print_format=json`) and normalizes in the encode with the measured values and `linear=true`; ffmpeg itself falls back to dynamic gain when linear gain would break the true-peak limit. Silence or an unparseable measurement falls back to the single-pass filter, and loudness never fails a render. The targets stay ADR-20's. The mode and the measured input values are recorded in `RenderedVideo.loudness`. One code path for clips and mixes; no per-producer switch.
Consequences: Mixed Timelines get one constant gain that keeps the ducking intact. Clips change by 0.1–0.3 LU (not audible) and cost about 2 s more CPU each. True peak after the AAC encode stays -0.9 to -1.3 dBTP, as today; if a platform ever flags clipping, TP=-2.0 is the knob.

## ADR-48: Autopilot per account
Date: 2026-10-01 · Status: Accepted (2026-10-01, the owner's review of card 009's spec, docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md; refines ADR-29; log #421, #422, #425, #428, #437)
Context: ADR-29 gives each account a review tier. The owner wants each account to run as automatically as it has earned, across production, review, publishing and scaling, within a daily attention budget of about 20 minutes and spend limits, with the owner stepping in only where judgment pays off.
Decision:
- Each account has three switches (Produce, Publish, Scale) and the Review dial (ADR-29's `review`, `sample`, `auto`), set together by presets Hands-on, Supervised and Autopilot; any one can be overridden. Controls never block each other; each shows what it waits on.
- Rails no control lifts: the policy gate; the batch line, account cap and fleet cap; new accounts start Hands-on; the review windows (format change: 10; producer version: 5, ADR-49; first dubs in a pair: 10).
- Always the owner's: spend over the line, sponsored and #ad items (first 30 days; brand deals always), new sources and new series formats.
- A graduation ladder: the system suggests promotions on 01's criteria (Hands-on → Supervised) and on ≥ 30 days, ≥ 12 spot checks with ≤ 1 rejected, no gate failure or strike in 30 days and runway ≥ 14 days (Supervised → Autopilot); the owner taps. Demotions are automatic: one step after 2 rejects in the last 5 spot checks, to Hands-on after a strike. On `sample`, spot checks are at least 1 in 10 and at least 3 a week per account.
- The settings are operating state in an `autopilot` table with one writer (`accounts/autopilot.py`) and an append-only change history (who, when, from → to, why), not part of ADR-42's versioned setup; every change records the person who tapped (`web:<login>` or `telegram:<id>`, promotions included, with the reason "promotion suggested by the ladder: <criteria>"), and `system:<component>` only for changes nobody tapped (`system:demotion`, `system:filler`). The Activity tab and "what ran without me" read the history.
- Hard spend caps are enforced in `service.create_job` for every caller from the first automatic job creator on (S6's queue filler, or an earlier card that creates jobs automatically). Until then only owner-started jobs exist, and the per-batch line still asks first. The dashboard only shows caps.
Consequences: owner time scales with how new each account is. ADR-29's tier becomes the Review dial and leaves S3c's "rules" class. Two new tables. Wave-2 clip accounts wait for S2 because assisted posting doesn't fit the attention budget.

## ADR-49: Producer-version review window
Date: 2026-10-01 · Status: Accepted (2026-10-01, the owner's review of card 009's spec, docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md; refines ADR-29 and ADR-43; log #423)
Context: ADR-29 says a new producer version starts in `review`. With ADR-43, a `producer_version` changes whenever stage versions, prompts or models change (for example S4's `render.STAGE_VERSION` 3 → 4: Timeline input and ADR-47's two-pass loudness), which would put every account back in full review.
Decision: after a `producer_version` change, the first 5 items per account made under the new version go to `review`; then the account's dial applies again. The account's rung doesn't change. A format change keeps S3c's 10.
Consequences: about 5 reviews per account per producer change (about 95 across 19 accounts), against a full return to Hands-on. S2 enforces it from `content_items.producer_version`.

## ADR-50: Hook library versioned outside the account setup
Date: 2026-10-01 · Status: Accepted (2026-10-01, the owner's review of card 009's spec, docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md; refines ADR-42; log #426)
Context: hooks are the lever the owner wants to improve most. Rotating hook patterns per item and ranking them by results is continuous, while ADR-42's setup experiments change one account version at a time and block other setup edits while they run.
Decision: each account has a hook library (patterns shareable to its blueprint) in its own tables, outside the versioned setup. Patterns are immutable versions; an edit writes v+1; every item stamps `hook_pattern_id@version` and the rotation weights in force. Producers write 2–3 variants per item from approved patterns and ship the best-ranked one. While the account runs a setup experiment, its rotation weights are frozen. Hook rotation is never an S3c experiment.
Consequences: an item's setup is `(account_id, account_version)` plus its hook stamp, so ADR-42's traceability holds. About $0.0025–0.0035 of Haiku per item. A separate hooks card builds it after S1's rollout and before S6.

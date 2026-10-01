# ClipForge

Turn long-form videos into ready-to-post vertical short clips (TikTok, Instagram Reels, YouTube Shorts).

Send a direct video link (or a file up to 20 MB) to a Telegram bot. ClipForge transcribes the video, finds the best moments, reframes them to 9:16, burns in animated captions, and delivers the clips back in the chat with a download link for the whole folder. Everything runs serverless on [Modal](https://modal.com); nothing runs on your machine.

> **Content policy:** only process videos you own or have permission to use (creator agreements, paid clipping programs, Creative Commons, public domain). See [docs/SOURCING.md](docs/SOURCING.md).

## How it works

```
link/file ─► ingest ─► transcribe ─► find highlights ─► reframe 9:16 ─► captions + render ─► output folder
                         (Whisper)        (LLM)          (face tracking)      (ffmpeg/ASS)
```

Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Output

Stored on the Modal Volume `clipforge-jobs`:

```
/jobs/<job_id>/
  output/
    clip_01_score0.91/
      video.mp4        # 9:16, captions burned in
      captions.srt
      post.md          # title, hook, source credit (full per-platform copy in Phase 3)
    metadata.json      # timestamps, scores, permission, model + prompt versions, cost
  job.zip              # delivered as a signed, expiring download link
```

Clean (caption-free) videos and thumbnails arrive in Phase 3.

## Quickstart

Requirements: a [Modal](https://modal.com) account, a Telegram bot token (from @BotFather) and an Anthropic API key. For development: Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg (tests only).

```bash
git clone <repo> && cd clipforge
uv sync
uv run modal setup                               # log in to Modal
cp .env.example .env                             # fill in the secrets (see the comments)

# The Modal secret every function reads. Generate random values with
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
uv run modal secret create clipforge-secrets \
  ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... \
  TELEGRAM_ALLOWED_USER_IDS=... API_TOKEN=... DOWNLOAD_SIGNING_KEY=...

uv run modal run src/clipforge/app.py::doctor    # check ffmpeg + the GPU image
uv run modal run src/clipforge/app.py::smoke     # one real job on the 10 s fixture (~$0.01)
uv run modal deploy src/clipforge/app.py         # deploy the API, webhook and pipeline
```

`modal deploy` prints the `web` URL. Put it in `API_URL` in `.env` and in the secret (re-run `modal secret create --force clipforge-secrets` with every value plus `API_URL=...`), then register the bot's webhook:

```bash
uv run clipforge set-webhook
```

## Everyday commands

### Clip videos from your computer

Put each channel's videos (`.mp4 .mov .mkv .webm .m4v .avi`) in its own folder, `videos/<channel>/`, and describe the channel once in `videos/channels.toml` (credit name, optional url, permission; ADR-22). Then:

```bash
uv run clipforge clip                                       # upload + submit every new video, then exit
uv run clipforge clip --fetch                               # ...and wait, then download the clips
uv run clipforge clip "videos/billy-garton/ep01.mp4" --again   # re-cut one video
```

`clip` submits and exits: the jobs run on Modal. Channel clips join the posting queue when they finish (ADR-23). With `--fetch`, each finished job is downloaded into `videos/out/<channel>/<episode>/` (a re-cut goes to `<episode>-2/`, so nothing is overwritten):

```
videos/out/billy-garton/ep01/
  clip_01_score0.89/  video.mp4  captions.srt  post.md
  clip_02_score0.88/  ...
  metadata.json       # scores, timings, cost
```

Videos directly in `videos/` still work, without a channel (they aren't queued for posting). Setup details: [videos/README.md](videos/README.md).

### How many clips

By default the number is **automatic**: every clip the AI scored **0.80 or higher**, up to 30.

```bash
uv run clipforge clip --min-score 0.85     # stricter: fewer, stronger clips
uv run clipforge clip --min-score 0.7      # looser: more clips
uv run clipforge clip --n 10               # exactly the top 10, whatever their score
```

Re-cutting with a different `--min-score` or `--n` (plus `--again`) is cheap: the transcript and highlight scores are reused, and clips already rendered aren't rendered again.

### Other options

```bash
uv run clipforge clip --len 20-45          # clip length range in seconds (default 30-60)
uv run clipforge clip --lang es            # force the language (default: detected)
uv run clipforge clip --perm own           # override the channel's permission
```

### From a link, and checking jobs

```bash
uv run clipforge run --input https://example.com/episode.mp4    # same options as clip
uv run clipforge status <job_id>           # progress, cost, and the zip link when done
uv run clipforge resume <job_id>           # continue a failed job from where it stopped
uv run clipforge status                    # posting overview: per channel, queue length, next slot
uv run clipforge status --rebuild          # re-queue every finished channel job for posting
```

The defaults live in `.env`: `DEFAULT_CLIP_COUNT=auto`, `DEFAULT_MIN_SCORE=0.80`, `DEFAULT_CLIP_LEN=30-60`. For the Telegram bot to use the same defaults, update the Modal secret too (`uv run modal secret create --force clipforge-secrets --from-dotenv .env`). More in [videos/README.md](videos/README.md).

Inputs must be direct media links (or Telegram uploads up to 20 MB). YouTube links are not supported, because YouTube blocks Modal's servers (see ADR-10).

## Telegram usage

```
/clip <link> [n=auto] [score=0.8] [len=30-60] [lang=auto] [perm=own] [credit="..."]
/status <job_id>
/resume <job_id>
```

A bare link uses the defaults (automatic count, score ≥ 0.80). A video file up to 20 MB works too; put options in its caption (`score=0.85 len=20-45`). Only users in `TELEGRAM_ALLOWED_USER_IDS` get an answer. The bot sends each clip as a video as soon as it is rendered, then a download link for the zip.

**Posting assistant (plan C, live since 2026-09-29; ADR-23, ADR-24).** Once `POSTING_CHAT_ID` is set, the bot sends the next queued clip at each slot (default 08:00, 10:30, 13:00, 16:00, 19:00, 21:30 New York time) with copy-ready captions for TikTok, Instagram and YouTube, and buttons: ✅ per platform (tap again to undo), ⏭ Skip (back after 24 h) and 🗑 Reject (with an optional reason). `/status` shows the posting overview; `/next`, `/pause` and `/go` run the queue. After 2 clips without a tap it waits and reminds you once. A daily keep-alive stops the queue expiring (the Modal Dict drops entries after 7 idle days) and snapshots it; `clipforge status --restore` puts back anything lost. Owner steps and commands: [docs/studio/11-owner-runbook.md](docs/studio/11-owner-runbook.md).

## Project docs

One question, one home:

| Question | Where |
|---|---|
| Where do things stand right now? | [STATUS.md](STATUS.md) |
| How does the system work today? | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Why was it built this way? | [docs/DECISIONS.md](docs/DECISIONS.md) (ADRs) and [docs/studio/10-decision-log.md](docs/studio/10-decision-log.md) (every owner decision) |
| What's next? | [docs/studio/04-roadmap.md](docs/studio/04-roadmap.md) (Phase 6 source of truth); [ROADMAP.md](ROADMAP.md) (all phases, mirrors 04) |
| What does the owner do, and how? | [docs/studio/11-owner-runbook.md](docs/studio/11-owner-runbook.md) |
| What is each session doing, and what did it do? | [docs/cards/](docs/cards/README.md) and [docs/reports/](docs/reports/README.md) |
| Which accounts exist? | [docs/studio/09-account-registry.md](docs/studio/09-account-registry.md) |
| Which secret lives where? | [docs/ops/secrets.md](docs/ops/secrets.md) (names only) · deploys: [docs/ops/deploys.md](docs/ops/deploys.md) |
| How should Claude Code work here? | [CLAUDE.md](CLAUDE.md) |
| What must pass, what may a branch touch, how do I deploy? | [scripts/check.sh](scripts/check.sh), [scripts/scopes.toml](scripts/scopes.toml), [scripts/worktree.sh](scripts/worktree.sh), [scripts/deploy.sh](scripts/deploy.sh) |
| Designs and task plans | [docs/superpowers/](docs/superpowers/README.md) (active vs historical) |
| Studio plan (vision, architecture target, tools, portfolio, dashboard) | [docs/studio/](docs/studio/README.md) |
| Clip quality, content permissions, prompts | [docs/EVALS.md](docs/EVALS.md), [docs/SOURCING.md](docs/SOURCING.md), [prompts/](prompts/) |

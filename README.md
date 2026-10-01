# ClipForge

ClipForge turns long videos, such as podcast episodes, into vertical short clips for TikTok, Instagram Reels and YouTube Shorts, then helps you post them.

You give it a video. It transcribes it, picks the strongest moments, frames each one to 9:16 around whoever is talking, adds captions and a hook title, and hands back ready-to-post clips. A Telegram bot then sends you one clip at a time, at set times of day, with the captions to paste for each platform.

Everything runs serverless on [Modal](https://modal.com). Nothing needs to run on your own computer except when you add videos.

> **Only process videos you own or have permission to use:** your own content, creator agreements, paid clipping programs, Creative Commons or public domain. See [docs/SOURCING.md](docs/SOURCING.md).

## What works today

- **Clipping:** a video file or a direct link becomes 1080x1920 clips with captions, a hook title, loudness at -14 LUFS, and face framing that follows the speaker.
- **Batch clipping by channel:** drop episodes into `videos/<channel>/`, run one command, and every new video is clipped.
- **The posting assistant:** a Telegram bot sends the next clip at each posting slot and tracks what you posted where.
- **A dashboard shell** (`web/`): built, not online yet.

Where it's going: a studio that runs many accounts and content types (AI stories, music, avatars) from one codebase ([docs/studio/](docs/studio/README.md), ROADMAP Phase 6). Current progress is in [STATUS.md](STATUS.md).

## How it works

```
video ─► ingest ─► transcribe ─► find highlights ─► frame to 9:16 ─► captions + render ─► clips
                   (Whisper, GPU)     (Claude)        (faces, speaker)     (ffmpeg)
```

Each step is a separate Modal function, and each step's result is cached, so a re-cut reuses the transcript and the highlight scores. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Clipping videos

### From your computer

1. Put each channel's episodes in their own folder: `videos/<channel>/` (`.mp4`, `.mov`, `.mkv`, `.webm`, `.m4v` or `.avi`).
2. Describe the channel once (credit name, link, permission) in `videos/channels.toml`. Setup details: [videos/README.md](videos/README.md).
3. Run:

```bash
uv run clipforge clip            # submit every new video, then exit; the jobs run on Modal
uv run clipforge clip --fetch    # ...and wait, then download the clips
```

With `--fetch`, each video's clips land in `videos/out/<channel>/<episode>/`:

```
videos/out/billy-garton/ep01/
  clip_01_score0.89/   video.mp4  captions.srt  post.md
  clip_02_score0.88/   ...
  metadata.json        # scores, timings, cost
```

Clips from a channel also join the posting queue (below). A video placed directly in `videos/`, outside a channel folder, is clipped but not queued.

> After the S1 rollout, channels move from `channels.toml` into the database: `uv run clipforge source add`, or `uv run clipforge source import-toml` once to copy the file.

### From a link

```bash
uv run clipforge run --input https://example.com/episode.mp4    # submit and wait
```

Links must point straight at a media file. YouTube links don't work, because YouTube blocks Modal's servers (ADR-10).

### Choosing how many clips

By default the count is **automatic**: every moment scored **0.80 or higher**, up to 30.

```bash
uv run clipforge clip --min-score 0.85     # stricter: fewer, stronger clips
uv run clipforge clip --n 10               # exactly the 10 best, whatever their score
uv run clipforge clip --len 20-45          # clip length in seconds (default 30-60)
uv run clipforge clip --lang es            # force the language (default: detected)
uv run clipforge clip "videos/billy-garton/ep01.mp4" --again --min-score 0.7   # re-cut one video
```

`run` takes the same options. Re-cutting is cheap: the transcript and scores are reused, and clips that were already rendered aren't rendered again. The defaults live in `.env` (`DEFAULT_CLIP_COUNT`, `DEFAULT_MIN_SCORE`, `DEFAULT_CLIP_LEN`).

### Checking on jobs

```bash
uv run clipforge status <job_id>     # progress, cost, and the download link when done
uv run clipforge resume <job_id>     # continue a failed job from where it stopped
```

## Posting with the Telegram bot

At each posting slot (by default 08:00, 10:30, 13:00, 16:00, 19:00 and 21:30, New York time), the bot sends you the next clip from the queue, with the captions to copy for TikTok, Instagram and YouTube. Under each clip:

- **✅ per platform:** mark it posted there (tap again to undo);
- **⏭ Skip:** the clip comes back after 24 hours;
- **🗑 Reject:** drop it, with an optional reason.

If two clips go unanswered, the bot stops sending and reminds you once.

| Command | What it does |
|---|---|
| `/status` | the posting overview: progress per channel, queue length, next slot |
| `/next` | send the next clip now |
| `/pause`, `/go` | stop and restart the slots |
| `/clip <link>` | clip a video from the chat (options: `n=`, `score=`, `len=`, `lang=`, `perm=`, `credit=`); a file up to 20 MB works too |
| `/status <job_id>`, `/resume <job_id>` | check or continue a job |

The bot only answers users listed in `TELEGRAM_ALLOWED_USER_IDS`.

The same overview is available from your computer:

```bash
uv run clipforge status              # the posting overview
uv run clipforge status --rebuild    # re-queue every finished channel job
uv run clipforge status --restore    # put back queue entries lost after an outage
```

A daily job at 07:00 UTC keeps the queue from expiring and saves a snapshot of it. What to do after an outage, and every other owner task: [docs/studio/11-owner-runbook.md](docs/studio/11-owner-runbook.md).

## First-time setup

You need a [Modal](https://modal.com) account, a Telegram bot token (from @BotFather) and an Anthropic API key. For development you also need Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg.

```bash
git clone <repo> && cd clipforge
uv sync
uv run modal setup                   # log in to Modal
cp .env.example .env                 # fill in the values (the comments explain each one)
```

Create the Modal secret that every function reads. Generate the random values with `python -c "import secrets; print(secrets.token_urlsafe(32))"`:

```bash
uv run modal secret create clipforge-secrets \
  ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... \
  TELEGRAM_ALLOWED_USER_IDS=... API_TOKEN=... DOWNLOAD_SIGNING_KEY=...
```

Check the setup, run one test job, then deploy:

```bash
uv run modal run src/clipforge/app.py::doctor     # ffmpeg and the GPU image
uv run modal run src/clipforge/app.py::smoke      # one real job on a 10-second clip (~$0.01)
scripts/deploy.sh --dry-run
scripts/deploy.sh --reason "first deploy"
```

The deploy prints the API's URL. Put it in `API_URL`, both in `.env` and in the Modal secret, then register the bot:

```bash
uv run clipforge set-webhook
```

To change the secret later, edit it in the Modal dashboard (Secrets → `clipforge-secrets` → **Edit**) and redeploy. Never run `modal secret create --force`: it replaces the whole secret. Which secret lives where: [docs/ops/secrets.md](docs/ops/secrets.md).

## Development

```bash
scripts/check.sh             # the one gate: lint, types, fast tests, the API contract, the dashboard, docs, scope
uv run pytest -q             # every test, including the slow and GPU ones
```

Work is organized as cards: each one is a brief for one Claude Code session, on its own branch and worktree, ending in a pull request. How that works: [CLAUDE.md](CLAUDE.md) and [docs/cards/](docs/cards/README.md). Deploys only go through `scripts/deploy.sh`, which refuses inside a posting slot's blackout.

## Where to find things

| Question | Where |
|---|---|
| Where do things stand right now? | [STATUS.md](STATUS.md) |
| How does the system work today? | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Why was it built this way? | [docs/DECISIONS.md](docs/DECISIONS.md) (ADRs) and [docs/studio/10-decision-log.md](docs/studio/10-decision-log.md) (every owner decision) |
| What's next? | [ROADMAP.md](ROADMAP.md), and [docs/studio/04-roadmap.md](docs/studio/04-roadmap.md) for the studio phase |
| What does the owner do, and how? | [docs/studio/11-owner-runbook.md](docs/studio/11-owner-runbook.md) |
| What is each session doing? | [docs/cards/](docs/cards/README.md) and [docs/reports/](docs/reports/README.md) |
| Which accounts exist? | [docs/studio/09-account-registry.md](docs/studio/09-account-registry.md) |
| Which secret lives where, and what was deployed? | [docs/ops/secrets.md](docs/ops/secrets.md) and [docs/ops/deploys.md](docs/ops/deploys.md) |
| Designs and implementation plans | [docs/superpowers/](docs/superpowers/README.md) |
| The studio plan | [docs/studio/](docs/studio/README.md) |
| Clip quality, content permissions, prompts | [docs/EVALS.md](docs/EVALS.md), [docs/SOURCING.md](docs/SOURCING.md), [prompts/](prompts/) |

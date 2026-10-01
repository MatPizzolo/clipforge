# CLAUDE.md

Guidance for Claude Code in this repository. Read this first, then the relevant doc below before changing code.

- Architecture and stage contracts: @docs/ARCHITECTURE.md
- Current plan and next tasks: @ROADMAP.md
- Past decisions (don't relitigate without a new ADR): @docs/DECISIONS.md

## Project summary

ClipForge is a pipeline that turns long videos into 9:16 short clips and writes them to an output folder. Interfaces (Telegram bot, web app) are thin clients over one job API. Everything runs serverless on Modal (ADR-9): the API, the Telegram webhook and each pipeline step. Nothing runs locally except development.

## Stack

- Python 3.12, managed with `uv` (never use pip directly)
- Modal for GPU functions, web endpoints, Volumes and Dicts
- faster-whisper / WhisperX for transcription
- Anthropic API (`claude-haiku-4-5` default) for highlight selection and post copy
- ffmpeg + libass for rendering; PySceneDetect + MediaPipe for reframing
- FastAPI for the job API (Modal `@asgi_app`), python-telegram-bot for the bot in webhook mode (no polling `Application`)
- pydantic v2 for every data contract

## Commands

```bash
scripts/check.sh                         # the single gate: python, contract, web, docs, scope (--python/--web/--docs/--scope, --e2e)
scripts/worktree.sh <branch>             # owner: a card's worktree in ../clipForge-<stream> (--remove <branch> after the merge)
scripts/deploy.sh --dry-run              # owner: the only deploy path (main, clean, CI green, outside the blackout)
uv sync                                  # install
uv run pytest -q                         # all tests
uv run pytest -q -m "not gpu and not slow"   # fast tests (run these before every commit)
uv run ruff check . && uv run ruff format .
uv run mypy src
uv run modal run src/clipforge/app.py::doctor   # local ffmpeg + Modal GPU environment check
uv run modal serve src/clipforge/app.py          # dev: hot-reload web endpoints on Modal
uv run modal run src/clipforge/app.py::smoke    # one real job on Modal (~$0.01)
scripts/deploy.sh --reason "<why>"               # deploy the app (owner only; never a bare `modal deploy`)
uv run clipforge run --input <url>               # submit a job to the deployed API
uv run clipforge clip [videos/<channel>/<file>] [--fetch]   # videos/ inbox → jobs (ADR-22); --fetch downloads the clips
uv run clipforge status [<id>] [--rebuild|--restore [DATE]] / resume <id>     # read or continue a job; no id: the posting overview
uv run clipforge set-webhook                     # point Telegram at the deployed API
# uv run clipforge eval --set evals/v1   # planned, not built (ROADMAP Phase 5, docs/EVALS.md)
uv run alembic upgrade head                      # migrate Neon (DATABASE_URL_UNPOOLED only; CI runs it before deploy)
uv run modal run src/clipforge/app.py::db_doctor # read-only: revision, pooled host, schedule copies (rollout only)
uv run clipforge account create|edit|list        # studio accounts (blueprints/)
uv run clipforge source add|edit|list|show|submissions   # sources live in the database (option B)
uv run clipforge source import-toml [--dry-run]  # one-off: videos/channels.toml -> sources
uv run clipforge posting import [--dry-run]|verify   # S1 migration (ADR-41)
uv run clipforge jobs backfill [--dry-run]       # jobs table from metadata.json and the Dict
```

## Layout

```
src/clipforge/
  app.py            # Modal app: step functions, web endpoints, cron (the only modal importer)
  doctor.py         # environment checks (local half of `doctor`)
  hashing.py        # file hashes and stage cache keys
  ffmpeg.py         # ffmpeg/ffprobe wrappers (media_info, probe_info, run)
  prompts.py        # versioned prompt loader (prompts/<name>_v<N>.md + metadata.json)
  llm.py            # LLMClient protocol + AnthropicClient
  links.py          # signed, expiring zip links (ADR-13)
  runtime.py        # Modal adapters (DictKV, ModalVolume, FunctionSpawner) + build_deps
  smoke.py          # checks for the Modal smoke job (app.py::smoke)
  cli.py            # `clipforge run|clip|status|resume|set-webhook|posting|jobs|account|source` (thin API client)
  inbox.py          # videos/ inbox for `clipforge clip`: channels.toml, channel folders, ledger, Volume paths
  api/main.py       # FastAPI job API + Telegram webhook route
  bot/              # Telegram: telegram.py (PTB sync bridge), messages, notifier, commands, webhook, context, posting (ADR-23), deeplinks (DASHBOARD_URL)
  stages/           # one module per stage + segmenting.py (sentences/windows) + shots.py/faces.py/speakers.py (reframe helpers) + runner.py (PipelineStages)
    ingest.py transcribe.py highlights.py reframe.py captions.py render.py package.py
  models.py         # pydantic contracts shared by stages
  jobs.py           # DictJobStore, JobContext, cached_stage (ADR-14)
  pipeline/         # step chain (Modal-free): deps.py interfaces, steps.py, selection.py, errors.py
  posting/          # posting queue (ADR-23/41): repo (PostingRepo: Dict/Sql/Dual), backend, actions (shared taps/commands, actors), queue rules, enqueue, slots, captions (per-platform copy), keepalive (ADR-24), daily (ADR-46), migrate (import/backfill/verify)
  service.py        # job service: create_job, get_job_view, resume_job (API, bot and CLI use it)
  config.py         # settings from env
  db/               # Postgres (ADR-26/41): engine (Database, 5 s statement timeout), tables, migrations, doctor, accounts/sources/jobs/posting repos
  accounts/         # blueprints loader + account service (create/edit, the posting:schedule:<account> Dict copies)
  schedule.py       # slot and hashtag normalization shared by config and accounts
  sources.py        # source permission hold rules
  sanitize.py       # clean (user-facing) and redact (logs, driver errors)
  ops.py            # ops alerts to the owner chat (ADR-45)
prompts/            # versioned prompts, loaded by filename
assets/             # fonts/ (Anton, OFL) and models/ (YuNet face model, MIT)
alembic/            # migrations (0001 is frozen; new tables and columns go in 0002+)
blueprints/         # account blueprints (ADR-35), mounted into the images
tests/              # mirrors src/ layout; fixtures in tests/fixtures/
web/                # Next.js dashboard (S3a): a client of the job API
scripts/            # check.sh (the gate), deploy.sh, worktree.sh, scopes.toml
docs/               # architecture, ADRs, studio plan, cards, reports, templates
```

`evals/` (eval sets and results) is planned, not built (ROADMAP Phase 5).

## Rules

1. **Stages are pure and resumable.** Each stage takes a pydantic input, writes its output to its cache directory (`/jobs/cache/<stage>/<key>/`, ADR-8), and returns a pydantic output. If the output already exists for the same input hash, skip the work. Never make a later stage re-run an earlier one. Stage modules never import Modal.
2. **Contracts live in `models.py`.** Change a contract there first, then update producer and consumer, then tests.
3. **Report progress.** Long-running stages call `ctx.report(stage, pct, message)` on the `jobs.JobContext` they receive. The bot and web app depend on this.
4. **Prompts are files, not strings.** Load them from `prompts/<name>_v<N>.md`. Never edit a released prompt version in place; create the next version and record it in `metadata.json`.
5. **LLM output is JSON-validated.** Parse with pydantic; on failure retry that call once with the validation error. For highlights, this applies per transcript window: a window that fails twice is dropped and recorded in the job metadata, and the stage fails clearly only if more than 25% of windows fail or no candidates remain.
6. **Process only selected segments on GPU.** Reframing and rendering run per clip, never on the full source video.
7. **Log cost.** Every stage records GPU seconds and LLM tokens in the job metadata.
8. **No secrets in code or logs.** Use `config.py` / Modal secrets. Never print tokens.
9. **Content policy.** Don't add features whose purpose is to evade copyright detection (e.g. mirroring, pitch-shifting, cropping to beat Content ID). See docs/SOURCING.md.

## Testing

- Unit-test stages with tiny fixtures in `tests/fixtures/` (a 10-second clip, a short transcript JSON).
- Mark GPU tests `@pytest.mark.gpu` and network/LLM tests `@pytest.mark.slow`; mock the Anthropic client in fast tests.
- For ffmpeg changes, assert on output properties (duration, resolution 1080x1920, stream count) with ffprobe, not on bytes.
- DB tests need Postgres: Docker Desktop (WSL integration) running, or `TEST_DATABASE_URL`. They fail, never skip, without it.

## Sessions

- Work only from a card: `Run card docs/cards/NNN-….md`. The card's branch, scope, log range and cost cap bind the session; `scripts/scopes.toml` lists every prefix's paths.
- Run `scripts/check.sh` before every checkpoint, until it's green. Paste its summary into the report.
- Write the report in `docs/reports/NNN-<stream>-<YYYY-MM-DD>.md` (`docs/templates/handoff-report.md`), then stop with a suggested commit message.
- Never commit, push, tag, deploy or stop the Modal app: the owner does, from the commands you give.
- Stay in scope. `docs/studio/10-decision-log.md` is append-only, in your range. Anything else is a question for the owner.
- Skills: `run-card` starts a card; `checkpoint` closes each checkpoint (it uses `write-report` and `log-append`). The coordinator uses `write-card` and `review-pr`.
- Agents: `pr-reviewer` before every merge; add `security-reviewer`, `migration-reviewer` or `pipeline-reviewer` for their areas; `docs-auditor` at each pause.
- Guardrails (`.claude/settings.json`) enforce this: hooks block git writes, deploys, app stops, secret changes and printing secrets; they deny out-of-scope edits and overwriting the decision log; they restore the card context at start, resume and after compaction; and they ask for `scripts/check.sh` before a session stops with unchecked changes. Per-user overrides go in the gitignored `.claude/settings.local.json`.

## Working style

- Before a non-trivial change, state a short plan and which files you'll touch.
- Keep PRs to one roadmap item. Tick the checkbox in ROADMAP.md when done (for Phase 6, in docs/studio/04-roadmap.md too).
- If you make an architectural choice, add an ADR to docs/DECISIONS.md.
- Prefer boring, explicit code over clever abstractions. Type hints everywhere.

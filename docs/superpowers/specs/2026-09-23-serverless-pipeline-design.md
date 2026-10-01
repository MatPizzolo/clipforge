> **Historical (Phase 1, ADR-9–16, deployed 2026-09-23):** built and deployed; docs/ARCHITECTURE.md and the code are current.

# Serverless pipeline design (Phase 1)

Date: 2026-09-23 · Status: Awaiting review · ADRs: 9–16 in `docs/DECISIONS.md`

## 1. Goal and constraints

**Outcome.** You send a direct video link (or a Telegram upload up to 20 MB) to the ClipForge Telegram bot. You get back up to 5 captioned 9:16 clips as Telegram videos, followed by a signed download link for a zip of the output folder. Cost is logged in `metadata.json`.

**Constraints**
- Everything runs serverless on Modal plus third-party APIs (Anthropic, Telegram). Nothing runs on the owner's machine except development: tests, `modal deploy`, and the CLI as an API client.
- Phase 1 limits: center crop with blurred-background fallback, one caption style, no diarization, no web app.
- Keep dependencies few. Stage modules never import Modal.

**Success criteria (Phase 1 exit)**
- A 30-minute source becomes 5 watchable clips in under 10 minutes; the estimate is about 5 minutes.
- Cost per source hour is logged (estimated ~$0.15).
- A failure is announced once, with the stage and reason, and can be resumed.

**Decided during brainstorming**

| Topic | Decision | ADR |
|---|---|---|
| Runtime | Fully serverless on Modal | 9 |
| Input | Direct links and Telegram uploads (≤ 20 MB). No YouTube: a spike showed yt-dlp blocked on 3 of 3 Modal IPs | 10 |
| Transcription | Own faster-whisper `large-v3-turbo` on L4 (proven by `doctor`) | 11 |
| Topology | Event-driven step chain, atomic fan-in, stall sweeper | 12 |
| Delivery | Output on the Volume; clips sent as Telegram videos; signed zip link | 13 |
| State | Single-writer Dict keys; metadata.json is the durable record | 14 |
| Errors | Transient vs permanent errors, partial clip success, per-window LLM validation | 15 |
| CI/CD | Checks on every push; auto-deploy on `main` | 16 |
| Bot library | python-telegram-bot in webhook mode (`Update.de_json`, `telegram.Bot`), no polling `Application` | 13 |

## 2. Components

```
Telegram ──webhook──►┐
CLI / curl ──HTTPS──►├─ web (FastAPI, CPU)  POST /jobs · GET /jobs/{id} · POST /jobs/{id}/resume
                     │                        GET /jobs/{id}/download?exp=…&sig=… · POST /telegram/webhook
                     └── creates Job in Dict, spawns ▼

 ingest_step ─spawn─► transcribe_step ─spawn─► highlights_step ─spawn×N─► clip_step(clip_01…N)
   (CPU)                (GPU L4)                  (CPU + Haiku)             (CPU: reframe→captions→render)
                                                                                   │ last clip to finish
                                                                                   ▼ (atomic claim)
                                                                             package_step (CPU) ─► done
 sweeper (cron, every 10 min): stalled jobs → failed "stalled at <stage>"
```

| Unit | Location | Purpose | Depends on |
|---|---|---|---|
| Stage modules | `stages/*.py` | The work itself: a pydantic input goes in, a pydantic output comes out. Modal-free. | `models`, `jobs.JobContext`, ffmpeg, LLM or transcriber interfaces |
| Step logic | `pipeline/steps.py` | One function per step: load the job, run the stage via `cached_stage`, record the transition, spawn the next step, handle errors and attempts. Modal-free. | `pipeline/deps.py` interfaces |
| Step deps | `pipeline/deps.py` | Interfaces `KV` (get, put with `skip_if_exists`, delete), `Volume` (commit, reload), `Spawner` and `Notifier`, plus in-memory versions for tests | none |
| Job store | `jobs.py` | `JobContext`, `DictJobStore` (on `KV`; tests use `MemoryKV`), `cached_stage` returning `Stored` | `KV` |
| Service | `service.py` | `create_job`, `get_job_view`, `resume_job`, `sweep`. Shared by the API and the bot. | `pipeline`, `jobs` |
| API | `api/main.py` | FastAPI routes (section 5) | `service` |
| Bot | `bot/` | Webhook handler, command parsing, Telegram notifier | python-telegram-bot, `service` |
| CLI | `cli.py` | Thin HTTP client of the API | httpx |
| Modal app | `app.py` | Images, functions, cron, secrets. Binds the real `KV`, `Volume`, `Spawner` and `Notifier`. The only module that imports Modal. | everything |
| Doctor | `doctor.py` + `app.py::doctor` | Environment checks (already built) | ffmpeg, GPU image |

### Modal functions

| Function | Image | Resources | Timeout | Retries |
|---|---|---|---|---|
| `web` (`@asgi_app`) | base | CPU 0.5, scales to zero | 10 min, for long zip downloads (the webhook itself returns in seconds) | none |
| `ingest_step` | base | CPU 2, 4 GB | 15 min | 2 |
| `transcribe_step` | whisper (existing) | L4 | 30 min | 2 |
| `highlights_step` | base | CPU 1 | 10 min | 2 |
| `clip_step` | base | CPU 4, 4 GB | 10 min | 2 |
| `package_step` | base | CPU 1 | 10 min | 2 |
| `sweeper` (`Cron("*/10 * * * *")`) | base | CPU 0.25 | 2 min | none |
| `set_webhook`, `smoke`, `doctor` | local entrypoints | none | none | none |

`base` image: `debian_slim(python="3.12")` with `ffmpeg` and `fontconfig` from apt, plus the project dependencies, with `clipforge`, `prompts/` and `assets/fonts/` added. All functions mount the Volume `clipforge-jobs` at `/jobs` and use the secret `clipforge-secrets`.

## 3. Data flow and state

**Spawn arguments are IDs only**: `job_id`, plus `clip_id` for clip steps. Each step reads the job from the Dict and its inputs from the Volume, via the `job.outputs[stage]` pointers to that stage's `result.json`.

**Per-step sequence**
1. `volume.reload()`, then load the job.
2. Mark the step `running` and report progress.
3. `cached_stage(...)` writes to `/jobs/cache/<stage>/<key>/`.
4. `volume.commit()`.
5. Record `outputs[stage]` and the cost.
6. Spawn the next step.

**Clip specs.** The highlights cache key excludes `n` (ADR-8). So `highlights_step` runs the cached stage to get the ranked `HighlightsResult`. It then selects the top `n` itself and writes `ClipSpec`s to `/jobs/<job_id>/clips/<clip_id>.json`, a job-scoped location. Changing `n` reuses the cached highlights. `clip_step` re-binds a cached `RenderedClip` to this job's spec and writes it to `/jobs/<job_id>/clips/<clip_id>.rendered.json`; `ClipState.result_ref` points there.

**Dict layout (ADR-14).** Every key has exactly one writer.

| Key | Value | Writer |
|---|---|---|
| `job:<id>` | `Job`: input, status, current stage, error, `outputs`, `clip_ids`, `notify`, cost of the steps before fan-out | the step owning the job (ingest, transcribe, highlights, package), the failure path, `resume`, `sweeper` |
| `job:<id>:clip:<clip_id>` | `ClipState`: status, result pointer, cost entries, progress, `telegram_sent`, error | that `clip_step` |
| `job:<id>:attempts:<step>[:<clip_id>]` | int | that step |
| `job:<id>:claim:package` | `True` | set-if-absent |
| `job:<id>:claim:failed` | `True` | set-if-absent |
| `job:<id>:claim:spawn:<step>` | `True` | set-if-absent, by the step handing over to `<step>` (released if the spawn raises, and by `resume`) |
| `tg:update:<update_id>` | `True` | set-if-absent, by the webhook |

- `service.get_job_view()` merges the core record and the clip records into a `JobView` with total cost.
- The Dict is working state. `/jobs/<id>/output/metadata.json` is the durable record, and the view falls back to it when Dict entries are gone.

**Fan-in.**
1. A `clip_step` finishes, either done or permanently failed, and writes its own clip key.
2. It reads all the clip keys.
3. If every clip has finished, it tries `put("job:<id>:claim:package", True, skip_if_exists=True)`.
4. Only the caller that gets `True` spawns `package_step`.

**Volume.** Writers commit after the stage and before spawning. Every step reloads first. Parallel clip steps write disjoint directories.

**At-least-once delivery.** A step whose output is already recorded does no work; it only makes sure its hand-over happened (the spawn claim makes that idempotent). So a late or duplicated delivery can't re-run a stage, re-spawn downstream steps or fail a healthy job. `fail_job` writes `failed` even when the claim is already held, so a crash between claiming and writing can't leave a job stuck in `running`.

**Notifier** (`Notifier` protocol: `clip_ready(job, clip)`, `done(job, link)`, `failed(job, error)`).
- The step wrapper attaches the Telegram notifier when `job.input.notify` is set.
- A failing notifier is logged and never fails the step.
- `clip_step` sends the clip, then sets `telegram_sent`. A retry that lands between those two sends the clip twice. That's rare and accepted.
- A retry of a clip that is `done` but not `telegram_sent` sends it, so a crash between the two writes never loses a clip. `package_step` notifies `done` before saving DONE, for the same reason.
- `Deps.notifier()` never raises: a failure to build the notifier logs and falls back to no notifications.

### Contract changes (models.py first, per rule 2)

- `JobInput`:
  - takes exactly one of `source_url`, `source_path` (a path on the Volume, for tests and dev) or `telegram_file_id` (new);
  - `requested_by` is replaced by `notify: TelegramTarget | None`, where `TelegramTarget` has `chat_id` and `reply_to_message_id`.
- `Job`: add `stage: StageName | None`, `outputs: dict[StageName, str]` and `clip_ids: list[str]`, and drop `output_dir`. `output_zip` stays.
- New `ClipStatus` (`pending | running | done | failed`), `ClipState` and `JobView` (a `Job` plus `clips: list[ClipState]` plus totals).
- New `PermanentError(Exception)` with a `user_message`, in `pipeline/errors.py`.
- `Settings`:
  - remove `transcribe_backend`, `local_whisper_model` and `send_clips_to_telegram`;
  - add `api_token`, `telegram_webhook_secret` and `download_signing_key` (all `SecretStr`), `api_url`, `download_link_ttl_s` (604800), `max_source_duration_s` (10800) and `max_source_bytes` (4 GB);
  - `jobs_root` defaults to `/jobs`.

## 4. Errors, retries and recovery (ADR-15)

**Transient errors** (network, Anthropic 5xx or 429 after the SDK's own retries, container loss) are raised, and Modal retries the step (`Retries(max_retries=2)`, backoff).

**Permanent errors** (`PermanentError`) are caught by the wrapper, which fails the job or clip immediately and without retrying. Examples:
- a URL that returns 404 or isn't media;
- no audio stream;
- a source over 3 hours or 4 GB, checked in ingest before any GPU time;
- no clip-worthy segments.

**Final failure.** The wrapper increments `attempts` before running the step. On the third failure it fails the job or clip and returns normally.

**Failing the job**
1. Claim `claim:failed`.
2. If the claim succeeds, set status `failed` with the stage and a sanitized message (URL query strings removed), and notify once.
3. The traceback goes only to the Modal logs.

**Partial success.** A clip that fails doesn't stop the others. Package ships the clips that rendered. The job fails only if every clip fails.

**Highlights (rule 5, per window).** A window whose JSON fails validation is retried once with the error. If it fails again, it's dropped and recorded. The stage fails only if more than 25% of windows fail or no candidates remain.

**Sweeper.** A running job whose `updated_at` is older than its current step's timeout plus 5 minutes is failed with "stalled at <stage>".

**`resume`**
1. Clear `claim:failed` and the attempt counters.
2. Set status `running`.
3. Spawn the first step without an `outputs` entry. For clips, spawn only the clips that aren't done, or package if they all are.

Cached stages are skipped.

## 5. API, bot and delivery (ADR-13)

| Route | Auth | Behaviour |
|---|---|---|
| `POST /jobs` | `Authorization: Bearer <API_TOKEN>` | Validate `JobInput`, create the job, spawn `ingest_step`, return `{job_id}` |
| `GET /jobs/{id}` | bearer | `JobView` |
| `POST /jobs/{id}/resume` | bearer | as in section 4 |
| `GET /jobs/{id}/download?exp=&sig=` | `sig = HMAC-SHA256(DOWNLOAD_SIGNING_KEY, f"{id}:{exp}")`, `exp` in the future | Stream `/jobs/<id>/job.zip` after a Volume reload |
| `POST /telegram/webhook` | header `X-Telegram-Bot-Api-Secret-Token` equals `TELEGRAM_WEBHOOK_SECRET` | Handle one update and return 200 quickly |

**Bot**
- **Library:** python-telegram-bot in webhook mode. The handler parses the update with `Update.de_json(body, bot)` and replies through `telegram.Bot` (async). There is no `Application` polling loop.
- **Access:** only users in `TELEGRAM_ALLOWED_USER_IDS`; others are silently ignored.
- **Duplicates:** each `update_id` is claimed once (`tg:update:<id>`).
- **Commands**
  - `/clip <url> [n= len= lang= perm= credit=]`. A message containing only a URL is treated as `/clip <url>`.
  - A video or document up to 20 MB becomes a job with `telegram_file_id`, and `ingest_step` downloads it via `getFile`. Larger files get a reply asking for a link.
  - `/status <job_id>` and `/resume <job_id>`.
- **Messages**
  - On receiving a job: "Got it, job `<id>`".
  - On `clip_ready`: the clip as a video, captioned `#1 · score 0.91 · <title>`.
  - On `done`: `<k> of <n> clips · $<cost> · <zip link>`.
  - On `failed`: `<stage>: <reason>`, then `/resume <id>`.
- **Webhook registration:** `uv run modal run src/clipforge/app.py::set_webhook` calls `setWebhook(url, secret_token, allowed_updates=["message"])`.

**Clip size.** `video_bitrate = min(8 Mbps, 45 MB × 8 / duration − audio_bitrate)`, so a clip of up to 180 s stays under Telegram's 50 MB limit.

**CLI**
- `clipforge run --input <url> [--n --len --lang --perm --credit]` posts the job, polls `GET /jobs/{id}` every 5 s printing the stage and percentage, and prints the download link at the end.
- `clipforge status <id>` and `clipforge resume <id>`.
- It needs only `API_URL` and `API_TOKEN` locally.

**Secrets.** The Modal secret `clipforge-secrets` holds `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_USER_IDS`, `API_TOKEN` and `DOWNLOAD_SIGNING_KEY`. Setup instructions generate the random values with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 6. Testing and CI/CD (ADR-16)

**Fast tests** (no network, no Modal; run before every checkpoint)
- **Stages:** real ffmpeg on synthetic media, with the fake LLM and fake transcriber. ffprobe checks on rendered clips:
  - 1080x1920, h264/yuv420p, 1 video and 1 audio (AAC) stream;
  - duration within 0.1 s, and audio/video durations within 50 ms of each other;
  - captions actually burned in (pixel difference in the caption band);
  - under 50 MB.
- **Chain:** the whole step chain runs in-process with an in-memory `KV`, a no-op `Volume` and a synchronous `Spawner`. Cases:
  - the happy path;
  - exactly one package when clips finish together (with real threads);
  - partial clip failure, giving "4 of 5 clips";
  - giving up after the third attempt;
  - a permanent error is not retried;
  - resume re-spawns only unfinished work and skips the cache;
  - the sweeper;
  - per-window LLM failure: under 25% of windows drops them, over 25% fails the stage.
- **API:** FastAPI `TestClient` with fake dependencies. Covers auth, signed links (valid, expired, tampered) and resume.
- **Bot:** recorded update JSON, with `telegram.Bot` mocked. Covers the allowed-user check, parsing, the upload-size refusal and duplicate `update_id`s.

**Tests marked `gpu`:** transcribe the talking-head fixture on the Modal L4.

**Tests marked `slow`**
- A real Haiku call on the long transcript.
- `modal run app.py::smoke`: a full real job on Modal with the 10 s fixture (n=1, len=5–9) that checks the delivered clip. About $0.01; run before closing a checkpoint that touches steps.

**`.github/workflows/ci.yml`**
- **`check` job** (every push and PR): apt ffmpeg, `uv sync`, `ruff check`, `ruff format --check`, `mypy src`, and `pytest -m "not gpu and not slow"`.
- **`deploy` job:** runs on `main` only, after `check`. It runs `uv run modal deploy src/clipforge/app.py` with the GitHub secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`.
- **`manual` workflow** (`workflow_dispatch`): runs the `gpu` and `smoke` tests. CI never spends money automatically.

## 7. Cost and timing (estimates)

| Step | 30-min source | Cost per source hour |
|---|---|---|
| ingest: download + remux + wav | ~1 min | ~$0.005 |
| transcribe: L4, cold start included | ~1.5 min | ~$0.05 |
| highlights: ~7 windows in parallel, Haiku | ~20 s | ~$0.07 |
| 5 × clip_step in parallel, 4 CPU each | ~1–1.5 min | ~$0.02 per job |
| package | ~20 s | <$0.005 |
| spawn and cold-start overhead | ~15 s | — |
| **Total** | **~4–5 min** | **~$0.15** |

## 8. Changes to existing code

- **Kept as is:** `hashing.py`, `doctor.py`, the GPU image in `app.py`, fixtures, `tests/builders.py`.
- **`models.py`, `config.py`, `.env.example`:** changed as listed in section 3.
- **`jobs.py`:**
  - `JobContext` gets its store through the `JobStore` protocol;
  - `DictJobStore` is new;
  - `FileJobStore` was removed; tests use `DictJobStore` over `MemoryKV`;
  - `cached_stage` is unchanged.
- **New:** `pipeline/` (`steps.py`, `deps.py`, `errors.py`), `service.py`, `api/main.py`, `bot/`, `cli.py`, `.github/workflows/ci.yml` and `manual.yml`.
- **New dependencies:** `anthropic`, `httpx`, `fastapi`, `python-telegram-bot`.

## 9. Out of scope (Phase 1)

- YouTube and other platform URLs; Google Drive links.
- Volume retention and cleanup; R2 or Drive sync.
- The live status message, rating buttons and the options UI (Phase 2).
- Face tracking, diarization, silence removal, thumbnails and full `post.md` copy (Phase 3).
- The web app (Phase 4).

## 10. Known risks

| Risk | Mitigation |
|---|---|
| A failure between commit and spawn stalls a job | The sweeper announces it; `resume` continues |
| A duplicate clip video on retry | Accepted; `telegram_sent` limits it to a narrow window |
| Dict entries expire or are lost | `metadata.json` on the Volume is the durable record; the view falls back to it |
| Cold start on the Telegram webhook | FastAPI on a slim image starts in ~2–5 s, well inside Telegram's timeout; duplicates are claimed by `update_id` |
| Direct-link hosts that require cookies or confirmation pages | A clear `PermanentError` ("not a direct media link"); Drive support in Phase 4 |

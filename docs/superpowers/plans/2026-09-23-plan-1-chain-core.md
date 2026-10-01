> **Historical (Phase 1, ADR-9–16, deployed 2026-09-23):** built and deployed; docs/ARCHITECTURE.md and the code are current.

# Plan 1 of 3: Step chain core + CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Modal-free step chain: new contracts and config, the KV/Volume/Spawner/Notifier interfaces, `DictJobStore`, all five steps with error handling, resume, the stall sweeper and the job service. Everything is tested in-process with fake stages. Also add the CI workflows.

**Architecture:** Each pipeline step is a plain function `xxx_step(deps, job_id[, clip_id])` in `pipeline/steps.py`. It reloads the Volume, loads the job from a `DictJobStore` (single-writer keys over a `KV`), runs its stage through a `StageRunner`, commits, records the output ref and spawns the next step. Tests bind in-memory versions (`MemoryKV`, `NullVolume`, `QueueSpawner`, `RecordingNotifier`) and fake stages. Plan 3 binds `modal.Dict`, `modal.Volume` and `Function.spawn`.

**Tech Stack:** Python 3.12, uv, pydantic v2, pytest, ruff, mypy (strict), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-23-serverless-pipeline-design.md` (ADR-8, ADR-12 to ADR-16 in `docs/DECISIONS.md`).

**The three plans:** Plan 1 (this one) covers the chain core and CI. Plan 2 covers the real stages. Plan 3 covers the Modal wiring, API, bot, CLI and smoke test. Plans 2 and 3 are written after Plan 1 lands.

**Git:** the owner runs every git command. "Checkpoint" steps list the files to commit and a suggested message; don't run git yourself.

## Global Constraints

- Python `>=3.12,<3.13`, managed with `uv` (never pip). Run commands as `uv run ...`.
- Stage modules and everything under `src/clipforge/pipeline/` must never import `modal`. Only `src/clipforge/app.py` imports it (ADR-9).
- Paths inside contracts are strings relative to `JOBS_ROOT`. `JobContext.path(rel)` and `load_ref(root, ref, Model)` resolve them.
- Dict keys each have exactly one writer (ADR-14):
  - `job:<id>`
  - `job:<id>:clip:<clip_id>`
  - `job:<id>:attempts:<step>[:<clip_id>]`
  - `job:<id>:claim:package`
  - `job:<id>:claim:failed`
- Values stored in the KV are JSON strings (`model_dump_json()`), not pickled objects.
- `MAX_ATTEMPTS = 3` (the first try plus Modal `Retries(max_retries=2)`). Step timeouts in seconds: ingest 900, transcribe 1800, highlights 600, clip 600, package 600. `STALL_MARGIN_S = 300`.
- User-facing error messages have URL query strings removed and are capped at 300 characters.
- New settings and limits: `jobs_root=/jobs`, `max_source_duration_s=10800`, `max_source_bytes=4_000_000_000`, `download_link_ttl_s=604800`.
- Before every checkpoint, `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"` must pass.

## Review Focus

1. **Duplicate spawns.** Modal can deliver a spawn twice. A duplicated step must not produce duplicate clip videos, a second package or a second "done" message. Test: `test_duplicate_spawns_do_not_duplicate_work` (Task 5).
2. **Stale steps.** A step can arrive after its job has already failed or finished, for example a clip still queued when the sweeper failed the job. It must do nothing. Test: `test_steps_for_a_failed_job_do_nothing` (Task 5).
3. **Unknown or expired job IDs.** A step for a job ID that isn't in the Dict must return quietly, not raise into three noisy Modal retries. Test: `test_step_for_unknown_job_is_ignored` (Task 5).
4. **Cache reuse across jobs.** A cached clip render reused by another job must be re-bound to *this* job's clip ID and rank; otherwise package and notifications label clips wrong. Test: `test_cached_clip_is_rebound_to_this_jobs_spec` (Task 5).
5. **Resume on a job that isn't failed.** Resuming a running job must be refused, since it would double-run steps. Resuming a finished job is a no-op. Test: `test_resume_rules` (Task 6).

---

## File Structure

| File | Responsibility |
|---|---|
| `.github/workflows/ci.yml` | Checks on every push/PR; deploy to Modal on `main` (Task 1) |
| `.github/workflows/manual.yml` | Manual GPU check (`doctor`); Plan 3 adds the smoke test (Task 1) |
| `src/clipforge/models.py` | + `TelegramTarget`, `ClipStatus`, `ClipState`, `JobView`; `JobInput` and `Job` changes (Task 2) |
| `src/clipforge/config.py`, `.env.example` | Serverless settings (Task 3) |
| `src/clipforge/pipeline/__init__.py` | Package marker (Task 4) |
| `src/clipforge/pipeline/errors.py` | `PermanentError` (Task 4) |
| `src/clipforge/pipeline/deps.py` | `KV`/`MemoryKV`, `Volume`/`NullVolume`, `Spawner`/`QueueSpawner`/`SpawnCall`, `Notifier`/`NullNotifier`/`RecordingNotifier`/`SafeNotifier` (Task 4); `StageRunner` (Task 5) |
| `src/clipforge/jobs.py` | `DictJobStore`, clip-aware `JobContext`, `Stored`, `load_ref`, `cached_stage` returning `Stored`. `FileJobStore` and `create_job` are removed (Task 4) |
| `src/clipforge/pipeline/selection.py` | `select_clips` (Task 5) |
| `src/clipforge/pipeline/steps.py` | `Step`, constants, `Deps`, all steps, `dispatch`, `fail_job`, `sanitize` (Task 5); `resume`, `sweep`, `JobNotResumable` (Task 6) |
| `src/clipforge/service.py` | `create_job`, `get_job_view`, `resume_job` (Task 7) |
| `tests/pipeline/__init__.py`, `tests/pipeline/fakes.py`, `tests/pipeline/harness.py` | Fake stages and the in-process chain runner (Task 5) |
| `tests/pipeline/test_chain.py`, `test_selection.py`, `test_recovery.py`, `tests/test_service.py`, `tests/test_deps.py` | Tests |
| Docs | `ROADMAP.md`, `CLAUDE.md`, spec and ADR note (Task 8) |

`FileJobStore` is dropped. The spec kept it "for tests", but `DictJobStore(MemoryKV())` gives tests the production store logic with no extra code. Task 8 records this change.

---

### Task 1: CI workflows

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/manual.yml`

**Interfaces:**
- Consumes: the existing commands (`ruff`, `mypy`, `pytest`, `modal deploy`, `modal run ...::doctor`).
- Produces: GitHub secrets the owner must add: `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` (from `~/.modal.toml`, or create new ones with `uv run modal token new`).

- [ ] **Step 1: Write `ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Install ffmpeg (with libass)
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends ffmpeg
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -q -m "not gpu and not slow"

  deploy:
    # ADR-16: merged to main means live. Never runs on pull requests.
    needs: check
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-24.04
    concurrency:
      group: deploy-production
      cancel-in-progress: false
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - run: uv sync --locked
      - run: uv run modal deploy src/clipforge/app.py
```

- [ ] **Step 2: Write `manual.yml`**

```yaml
name: Manual GPU checks

# Costs Modal money (about $0.01 per run), so it never runs automatically (ADR-16).
on:
  workflow_dispatch:

jobs:
  gpu:
    runs-on: ubuntu-24.04
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - name: Install ffmpeg (with libass)
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends ffmpeg
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - run: uv sync --locked
      - name: Local + GPU environment check
        run: uv run modal run src/clipforge/app.py::doctor
      # Plan 3 adds: uv run pytest -q -m "gpu or slow" and the smoke entrypoint.
```

- [ ] **Step 3: Check that both files parse as YAML**

Run: `uv run --with pyyaml python -c "import yaml; [yaml.safe_load(open(p)) for p in ('.github/workflows/ci.yml', '.github/workflows/manual.yml')]; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the CI commands locally, exactly as CI will**

Run: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass (63 tests at the time of writing).

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `.github/workflows/ci.yml`, `.github/workflows/manual.yml`. Suggested message: `ci: add checks, main deploy and manual GPU workflow`. After pushing, add the two GitHub secrets under Settings → Secrets and variables → Actions.

---

### Task 2: Contract changes in `models.py`

**Files:**
- Modify: `src/clipforge/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces (used by every later task):
  - `TelegramTarget(chat_id: int, reply_to_message_id: int | None = None)`, frozen.
  - `JobInput`: exactly one of `source_url: AnyHttpUrl | None`, `telegram_file_id: str | None` or `source_path: str | None`, plus `notify: TelegramTarget | None`. `requested_by` is removed.
  - `Job`: adds `stage: StageName | None = None`, `outputs: dict[StageName, str] = {}` and `clip_ids: list[str] = []`. `output_dir` is removed.
  - `ClipStatus` (a `StrEnum`: `pending | running | done | failed`).
  - `ClipState(clip_id, spec_ref, updated_at, status=PENDING, result_ref=None, progress=None, cost=[], error=None, telegram_sent=False)`, a mutable `BaseModel` with property `finished: bool`.
  - `JobView(job_id, status, stage, clips, cost, created_at, updated_at, progress=None, error=None, output_zip=None)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_models.py`; also add `ClipState, ClipStatus, JobView, TelegramTarget` to the import list at the top)

```python
def make_clip_state() -> ClipState:
    return ClipState(clip_id="clip_01", spec_ref="20260923-ffffffff-ab12/clips/clip_01.json", updated_at=NOW)


def test_job_input_sources() -> None:
    upload = JobInput(telegram_file_id="BQACAgIAAxk", permission=Permission.OWN)
    assert upload.source_url is None and upload.telegram_file_id == "BQACAgIAAxk"
    with pytest.raises(ValidationError, match="exactly one"):
        JobInput.model_validate(
            {"telegram_file_id": "x", "source_path": "a.mp4", "permission": "own"}
        )


def test_job_input_notify_round_trip() -> None:
    job_input = make_input(notify={"chat_id": 42, "reply_to_message_id": 7})
    assert job_input.notify == TelegramTarget(chat_id=42, reply_to_message_id=7)
    assert JobInput.model_validate_json(job_input.model_dump_json()) == job_input


def test_job_outputs_and_clip_ids_round_trip() -> None:
    job = Job(
        job_id="20260923-ffffffff-ab12",
        input=make_input(),
        created_at=NOW,
        updated_at=NOW,
        stage=StageName.RENDER,
        outputs={StageName.INGEST: "cache/ingest/k/result.json"},
        clip_ids=["clip_01", "clip_02"],
    )
    restored = Job.model_validate_json(job.model_dump_json())
    assert restored.outputs == {StageName.INGEST: "cache/ingest/k/result.json"}
    assert restored.clip_ids == ["clip_01", "clip_02"]


def test_clip_state_finished() -> None:
    state = make_clip_state()
    assert state.status is ClipStatus.PENDING and not state.finished
    assert state.model_copy(update={"status": ClipStatus.DONE}).finished
    assert state.model_copy(update={"status": ClipStatus.FAILED}).finished
    assert not state.model_copy(update={"status": ClipStatus.RUNNING}).finished
```

Then add these three samples to the `ALL_SAMPLES` list:

```python
    TelegramTarget(chat_id=42),
    make_clip_state(),
    JobView(
        job_id="20260923-ffffffff-ab12",
        status=JobStatus.RUNNING,
        stage=StageName.RENDER,
        clips=[make_clip_state()],
        cost=CostSummary(),
        created_at=NOW,
        updated_at=NOW,
    ),
```

and add `JobStatus` to the `clipforge.models` import.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_models.py -q`
Expected: collection fails with `ImportError: cannot import name 'ClipState'`.

- [ ] **Step 3: Implement the changes in `src/clipforge/models.py`**

Replace the `JobInput` class with:

```python
class TelegramTarget(Contract):
    """Where the Telegram notifier reports a job (the chat that sent it)."""

    chat_id: int
    reply_to_message_id: int | None = None


class JobInput(Contract):
    source_url: AnyHttpUrl | None = None  # direct media link (ADR-10)
    telegram_file_id: str | None = None  # Telegram upload, at most 20 MB
    source_path: str | None = None  # path relative to JOBS_ROOT on the Volume (tests, dev)
    permission: Permission
    source_credit: str | None = None  # creator + license link; required for cc_by
    source_label: str | None = None
    options: ClipOptions = Field(default_factory=ClipOptions)
    notify: TelegramTarget | None = None  # set for jobs that came from Telegram

    @model_validator(mode="after")
    def _check(self) -> JobInput:
        sources = (self.source_url, self.telegram_file_id, self.source_path)
        if sum(source is not None for source in sources) != 1:
            raise ValueError(
                "exactly one of source_url / telegram_file_id / source_path is required"
            )
        if self.permission is Permission.CC_BY and not self.source_credit:
            raise ValueError("cc_by sources need source_credit")
        return self
```

Replace the `Job` class with:

```python
class Job(BaseModel):
    """Core job record (`job:<id>` in the Dict), written only by the step owning the job."""

    job_id: str  # "<yyyymmdd>-<source_hash8>-<rand4>"
    status: JobStatus = JobStatus.QUEUED
    input: JobInput
    created_at: datetime
    updated_at: datetime
    stage: StageName | None = None  # stage of the step currently owning the job
    progress: Progress | None = None
    error: JobError | None = None
    cost: CostSummary = Field(default_factory=CostSummary)  # steps before the clip fan-out
    outputs: dict[StageName, str] = Field(default_factory=dict)  # stage -> result.json ref
    clip_ids: list[str] = Field(default_factory=list)
    output_zip: str | None = None


class ClipStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ClipState(BaseModel):
    """Working state of one clip (`job:<id>:clip:<clip_id>`), written only by its clip step."""

    clip_id: str
    spec_ref: str  # this job's ClipSpec JSON, relative to JOBS_ROOT
    updated_at: datetime
    status: ClipStatus = ClipStatus.PENDING
    result_ref: str | None = None  # this job's RenderedClip JSON once done
    progress: Progress | None = None
    cost: list[StageCost] = Field(default_factory=list)
    error: JobError | None = None
    telegram_sent: bool = False

    @property
    def finished(self) -> bool:
        return self.status in (ClipStatus.DONE, ClipStatus.FAILED)


class JobView(BaseModel):
    """What the API returns: the core record merged with its clips, and the total cost."""

    job_id: str
    status: JobStatus
    stage: StageName | None
    clips: list[ClipState]
    cost: CostSummary
    created_at: datetime
    updated_at: datetime
    progress: Progress | None = None
    error: JobError | None = None
    output_zip: str | None = None
```

Update the module docstring's exception sentence to: "The one exception is `JobInput.source_path`, which may name a file the user placed on the Volume."

- [ ] **Step 4: Run all fast tests**

Run: `uv run pytest -q -m "not gpu and not slow"`
Expected: all pass. `tests/test_jobs.py` still passes, because `JobInput(source_path=...)` is still valid.

- [ ] **Step 5: Run lint and types**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: no issues.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `src/clipforge/models.py`, `tests/test_models.py`. Message: `feat(models): clip state, job view, telegram target and job outputs`.

---

### Task 3: Serverless settings

**Files:**
- Modify: `src/clipforge/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Settings` gains `telegram_webhook_secret`, `api_token` and `download_signing_key` (`SecretStr | None`), `api_url: str | None`, `download_link_ttl_s: int = 604800`, `max_source_duration_s: float = 10800`, `max_source_bytes: int = 4_000_000_000`, and `jobs_root: Path = Path("/jobs")`.
  - Removed: `transcribe_backend`, `local_whisper_model` and `send_clips_to_telegram`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_config.py`:
  - Replace `test_env_example_parses_with_inline_comments` with the version below.
  - Add `test_serverless_defaults`.
  - Extend the `_clean_env` fixture's name tuple with `"API_TOKEN", "DOWNLOAD_SIGNING_KEY", "TELEGRAM_WEBHOOK_SECRET", "API_URL"`.

```python
def test_env_example_parses() -> None:
    s = Settings(_env_file=REPO_ROOT / ".env.example")
    assert s.telegram_allowed_user_ids == []
    assert s.jobs_root == Path("/jobs")
    assert s.api_token is None
    assert s.max_source_duration_s == 10800


def test_serverless_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_TOKEN", "tok-secret")
    monkeypatch.setenv("DOWNLOAD_SIGNING_KEY", "sign-secret")
    s = Settings(_env_file=None)
    assert s.jobs_root == Path("/jobs")
    assert s.download_link_ttl_s == 7 * 24 * 3600
    assert s.max_source_bytes == 4_000_000_000
    assert s.api_url is None
    assert s.api_token is not None and s.api_token.get_secret_value() == "tok-secret"
    assert "tok-secret" not in repr(s) and "sign-secret" not in repr(s)
    assert not hasattr(s, "transcribe_backend")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL (`jobs_root == Path("jobs")`; there's no `api_token` attribute).

- [ ] **Step 3: Update `Settings` in `src/clipforge/config.py`.** Replace the field block from `# Secrets` down to `prices:` with:

```python
    # Secrets (in production: the Modal secret `clipforge-secrets`, ADR-9)
    anthropic_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = []
    api_token: SecretStr | None = None  # bearer token for the job API
    download_signing_key: SecretStr | None = None  # HMAC key for zip links (ADR-13)

    # Deployed API (used by the CLI and in download links)
    api_url: str | None = None
    download_link_ttl_s: int = 7 * 24 * 3600

    # Models
    highlight_model: str = "claude-haiku-4-5"
    whisper_model: str = "large-v3-turbo"
    modal_app_name: str = "clipforge"

    # Job defaults
    default_clip_count: int = Field(5, ge=1, le=15)
    default_clip_len: Annotated[tuple[float, float], NoDecode] = (30.0, 60.0)
    default_permission: Permission = Permission.OWN

    # Limits checked in ingest, before any GPU time (ADR-15)
    max_source_duration_s: float = 3 * 3600
    max_source_bytes: int = 4_000_000_000

    # Storage: the Modal Volume mount (tests use a temp dir)
    jobs_root: Path = Path("/jobs")

    prices: Prices = Field(default_factory=Prices)
```

and remove the now-unused `Literal` from the `typing` import.

- [ ] **Step 4: Replace `.env.example`**

```
# Copy to .env and fill in. Never commit a filled-in .env.
# In production these values live in the Modal secret `clipforge-secrets` (ADR-9).
# Keep comments on their own lines: python-dotenv reads `KEY=  # note` as the value "# note".
# Generate random values with: python -c "import secrets; print(secrets.token_urlsafe(32))"

# --- Secrets
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
# Random string; Telegram sends it back in the X-Telegram-Bot-Api-Secret-Token header.
TELEGRAM_WEBHOOK_SECRET=
# Comma-separated Telegram user ids; the bot ignores everyone else.
TELEGRAM_ALLOWED_USER_IDS=
# Bearer token for the job API (CLI and curl).
API_TOKEN=
# Signs zip download links (HMAC-SHA256).
DOWNLOAD_SIGNING_KEY=

# --- Deployed API (printed by `modal deploy`; used by the CLI and in download links)
API_URL=
DOWNLOAD_LINK_TTL_S=604800

# --- Models
HIGHLIGHT_MODEL=claude-haiku-4-5
WHISPER_MODEL=large-v3-turbo
MODAL_APP_NAME=clipforge

# --- Job defaults
DEFAULT_CLIP_COUNT=5
DEFAULT_CLIP_LEN=30-60
# own | creator_agreement | clipping_program | cc_by | public_domain (see docs/SOURCING.md)
DEFAULT_PERMISSION=own

# --- Limits (checked before any GPU time)
MAX_SOURCE_DURATION_S=10800
MAX_SOURCE_BYTES=4000000000

# --- Storage: the Modal Volume mount
JOBS_ROOT=/jobs
```

- [ ] **Step 5: Run the checks**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass. A local `.env` that still has the removed keys is fine, because `extra="ignore"`.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `src/clipforge/config.py`, `.env.example`, `tests/test_config.py`. Message: `feat(config): serverless settings and limits`.

---

### Task 4: Chain interfaces and `DictJobStore`

**Files:**
- Create: `src/clipforge/pipeline/__init__.py` (empty)
- Create: `src/clipforge/pipeline/errors.py`
- Create: `src/clipforge/pipeline/deps.py`
- Modify (rewrite): `src/clipforge/jobs.py`
- Test: `tests/test_deps.py` (new), `tests/test_jobs.py` (rewrite)

**Interfaces:**
- Produces:
  - `PermanentError(user_message: str)` with a `.user_message` attribute.
  - `KV` protocol: `get(key) -> str | None`, `put(key, value, *, skip_if_exists=False) -> bool`, `delete(key) -> None`, `keys() -> Iterable[str]`. `MemoryKV` implements it and is thread-safe.
  - `Volume` protocol: `commit()`, `reload()`. `NullVolume` counts `commits` and `reloads`.
  - `Spawner` protocol: `spawn(step: str, job_id: str, clip_id: str | None = None) -> None`. `QueueSpawner` has `.queue: deque[SpawnCall]`, and `SpawnCall(step, job_id, clip_id=None)` is frozen.
  - `Notifier` protocol: `clip_ready(job, clip, rendered)`, `done(job)`, `failed(job)`. Implemented by `NullNotifier`, `RecordingNotifier(events: list[tuple[str, str, str | None]])` and `SafeNotifier(inner)`.
  - `jobs.utcnow()` and `jobs.new_job_id(seed, now=None)` are unchanged.
  - `DictJobStore(kv)` methods:
    - job records: `save(job)`, `get(job_id) -> Job` (raises `KeyError`), `list_job_ids() -> list[str]`;
    - clip records: `create_clip(job_id, state) -> bool` (set-if-absent), `save_clip(job_id, state)`, `get_clip(job_id, clip_id) -> ClipState` (raises `KeyError`), `clips(job_id, clip_ids) -> list[ClipState]`;
    - attempts: `incr_attempts(job_id, step, clip_id=None) -> int`, `reset_attempts(job_id)`;
    - claims: `claim(job_id, name) -> bool`, `release(job_id, name)`.
  - `JobContext(job_id, root, store, clip_id=None)` has `job_dir`, `path(rel)`, `rel(path)`, `job()`, `report(stage, pct, message="")` and `record_cost(cost)`. With `clip_id` set, `report` and `record_cost` write the clip's key instead of the job's.
  - `Stored[T]` is a frozen dataclass with `value: T` and `ref: str`.
  - `load_ref(root, ref, model) -> T`.
  - `cached_stage(ctx, stage, key, output_type, compute, clip_id=None) -> Stored[T]`, where `ref == f"cache/{stage}/{key}/result.json"`.
  - Removed: `FileJobStore`, `JobStore` and `create_job` (the service takes over job creation in Task 7).

- [ ] **Step 1: Write the failing `tests/test_deps.py`**

```python
import threading
from datetime import UTC, datetime

from clipforge.models import ClipState, Job, JobInput, Permission
from clipforge.pipeline.deps import (
    MemoryKV,
    NullVolume,
    QueueSpawner,
    RecordingNotifier,
    SafeNotifier,
    SpawnCall,
)

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def test_memory_kv_set_if_absent_is_atomic() -> None:
    kv = MemoryKV()
    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda: results.append(kv.put("claim", "1", skip_if_exists=True)))
        for _ in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    assert kv.put("claim", "2") is True and kv.get("claim") == "2"
    kv.delete("claim")
    kv.delete("claim")  # deleting a missing key is fine
    assert kv.get("claim") is None and list(kv.keys()) == []


def test_null_volume_and_queue_spawner() -> None:
    volume = NullVolume()
    volume.commit()
    volume.reload()
    assert (volume.commits, volume.reloads) == (1, 1)
    spawner = QueueSpawner()
    spawner.spawn("clip", "j1", "clip_01")
    assert list(spawner.queue) == [SpawnCall("clip", "j1", "clip_01")]


class Exploding:
    def clip_ready(self, job: Job, clip: ClipState, rendered: object) -> None:
        raise RuntimeError("telegram down")

    def done(self, job: Job) -> None:
        raise RuntimeError("telegram down")

    def failed(self, job: Job) -> None:
        raise RuntimeError("telegram down")


def test_safe_notifier_swallows_errors() -> None:
    job = Job(
        job_id="j1",
        input=JobInput(telegram_file_id="f", permission=Permission.OWN),
        created_at=NOW,
        updated_at=NOW,
    )
    clip = ClipState(clip_id="clip_01", spec_ref="j1/clips/clip_01.json", updated_at=NOW)
    safe = SafeNotifier(Exploding())  # type: ignore[arg-type]
    safe.clip_ready(job, clip, None)  # type: ignore[arg-type]
    safe.done(job)
    safe.failed(job)
    recorder = RecordingNotifier()
    SafeNotifier(recorder).done(job)
    assert recorder.events == [("done", "j1", None)]

```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deps.py -q`
Expected: `ModuleNotFoundError: No module named 'clipforge.pipeline'`.

- [ ] **Step 3: Create `src/clipforge/pipeline/__init__.py` (empty) and `src/clipforge/pipeline/errors.py`**

```python
"""Errors that the step chain treats specially (ADR-15)."""

from __future__ import annotations


class PermanentError(Exception):
    """A failure that retrying cannot fix: bad input, no audio, nothing worth clipping.

    `user_message` is shown to the user as is, so keep it short and free of secrets.
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message
```

- [ ] **Step 4: Create `src/clipforge/pipeline/deps.py`**

```python
"""Interfaces the step chain depends on, with in-memory versions for tests (ADR-12, ADR-14).

app.py binds the real ones (modal.Dict, modal.Volume, Function.spawn, the Telegram notifier).
Nothing in this package imports Modal.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from clipforge.models import ClipState, Job, RenderedClip

log = logging.getLogger(__name__)


class KV(Protocol):
    """String key-value store with an atomic set-if-absent (modal.Dict in production)."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str, *, skip_if_exists: bool = False) -> bool: ...

    def delete(self, key: str) -> None: ...

    def keys(self) -> Iterable[str]: ...


class MemoryKV:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: str, *, skip_if_exists: bool = False) -> bool:
        with self._lock:
            if skip_if_exists and key in self._data:
                return False
            self._data[key] = value
            return True

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._data)


class Volume(Protocol):
    def commit(self) -> None: ...

    def reload(self) -> None: ...


@dataclass
class NullVolume:
    commits: int = 0
    reloads: int = 0

    def commit(self) -> None:
        self.commits += 1

    def reload(self) -> None:
        self.reloads += 1


@dataclass(frozen=True)
class SpawnCall:
    step: str
    job_id: str
    clip_id: str | None = None


class Spawner(Protocol):
    def spawn(self, step: str, job_id: str, clip_id: str | None = None) -> None: ...


class QueueSpawner:
    """Records spawns instead of running them; tests drain `queue` (deque ops are thread-safe)."""

    def __init__(self) -> None:
        self.queue: deque[SpawnCall] = deque()

    def spawn(self, step: str, job_id: str, clip_id: str | None = None) -> None:
        self.queue.append(SpawnCall(step, job_id, clip_id))


class Notifier(Protocol):
    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None: ...

    def done(self, job: Job) -> None: ...

    def failed(self, job: Job) -> None: ...


class NullNotifier:
    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        return None

    def done(self, job: Job) -> None:
        return None

    def failed(self, job: Job) -> None:
        return None


@dataclass
class RecordingNotifier:
    events: list[tuple[str, str, str | None]] = field(default_factory=list)

    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        self.events.append(("clip_ready", job.job_id, clip.clip_id))

    def done(self, job: Job) -> None:
        self.events.append(("done", job.job_id, None))

    def failed(self, job: Job) -> None:
        self.events.append(("failed", job.job_id, None))


@dataclass
class SafeNotifier:
    """Logs notifier failures instead of failing the step (ADR-14)."""

    inner: Notifier

    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        try:
            self.inner.clip_ready(job, clip, rendered)
        except Exception:
            log.exception("notifier.clip_ready failed for %s/%s", job.job_id, clip.clip_id)

    def done(self, job: Job) -> None:
        try:
            self.inner.done(job)
        except Exception:
            log.exception("notifier.done failed for %s", job.job_id)

    def failed(self, job: Job) -> None:
        try:
            self.inner.failed(job)
        except Exception:
            log.exception("notifier.failed failed for %s", job.job_id)
```

- [ ] **Step 5: Run `tests/test_deps.py`**

Run: `uv run pytest tests/test_deps.py -q`
Expected: 3 passed.

- [ ] **Step 6: Rewrite `tests/test_jobs.py` for the new store (failing first)**

```python
import threading
from pathlib import Path

import pytest

from clipforge.jobs import (
    DictJobStore,
    JobContext,
    Stored,
    cached_stage,
    load_ref,
    new_job_id,
    utcnow,
)
from clipforge.models import (
    CaptionFiles,
    ClipState,
    Job,
    JobInput,
    Permission,
    StageCost,
    StageName,
)
from clipforge.pipeline.deps import MemoryKV

JOB_ID = "20260923-aaaaaaaa-0001"


@pytest.fixture
def store() -> DictJobStore:
    return DictJobStore(MemoryKV())


@pytest.fixture
def ctx(tmp_path: Path, store: DictJobStore) -> JobContext:
    now = utcnow()
    job_input = JobInput.model_validate(
        {"source_url": "https://media.example.com/a.mp4", "permission": Permission.OWN}
    )
    store.save(Job(job_id=JOB_ID, input=job_input, created_at=now, updated_at=now))
    return JobContext(job_id=JOB_ID, root=tmp_path, store=store)


def captions(out_dir: Path, ctx: JobContext) -> CaptionFiles:
    ass = out_dir / "clip.ass"
    ass.write_text("[Script Info]")
    return CaptionFiles(
        clip_id="clip_01",
        ass_path=ctx.rel(ass),
        srt_path=ctx.rel(out_dir / "clip.srt"),
        style="default",
        offset_s=10.0,
    )


def add_clip(store: DictJobStore, clip_id: str = "clip_01") -> ClipState:
    state = ClipState(clip_id=clip_id, spec_ref=f"{JOB_ID}/clips/{clip_id}.json", updated_at=utcnow())
    assert store.create_clip(JOB_ID, state)
    return state


def test_new_job_id_format() -> None:
    job_id = new_job_id("https://example.com/v.mp4")
    day, digest, rand = job_id.split("-")
    assert len(day) == 8 and len(digest) == 8 and len(rand) == 4
    assert new_job_id("x").split("-")[1] == new_job_id("x").split("-")[1]


def test_job_round_trip_and_listing(ctx: JobContext, store: DictJobStore) -> None:
    assert store.get(JOB_ID).job_id == JOB_ID
    with pytest.raises(KeyError):
        store.get("nope")
    add_clip(store)
    store.claim(JOB_ID, "package")
    store.incr_attempts(JOB_ID, "ingest")
    assert store.list_job_ids() == [JOB_ID]  # clip/claim/attempt keys are not jobs


def test_clip_create_is_set_if_absent(ctx: JobContext, store: DictJobStore) -> None:
    first = add_clip(store)
    again = first.model_copy(update={"spec_ref": "other"})
    assert store.create_clip(JOB_ID, again) is False
    assert store.get_clip(JOB_ID, "clip_01").spec_ref == first.spec_ref
    add_clip(store, "clip_02")
    assert [c.clip_id for c in store.clips(JOB_ID, ["clip_02", "clip_01"])] == [
        "clip_02",
        "clip_01",
    ]
    with pytest.raises(KeyError):
        store.get_clip(JOB_ID, "clip_09")


def test_attempts_and_claims(ctx: JobContext, store: DictJobStore) -> None:
    assert store.incr_attempts(JOB_ID, "ingest") == 1
    assert store.incr_attempts(JOB_ID, "ingest") == 2
    assert store.incr_attempts(JOB_ID, "clip", "clip_01") == 1
    assert store.incr_attempts("other-job", "ingest") == 1
    store.reset_attempts(JOB_ID)
    assert store.incr_attempts(JOB_ID, "ingest") == 1
    assert store.incr_attempts("other-job", "ingest") == 2  # other jobs untouched
    assert store.claim(JOB_ID, "failed") is True
    assert store.claim(JOB_ID, "failed") is False
    store.release(JOB_ID, "failed")
    assert store.claim(JOB_ID, "failed") is True


def test_report_updates_job_progress(ctx: JobContext) -> None:
    before = ctx.job().updated_at
    ctx.report(StageName.TRANSCRIBE, 150, "almost")
    job = ctx.job()
    assert job.progress is not None and job.progress.pct == 100  # clamped
    assert job.progress.stage is StageName.TRANSCRIBE
    assert job.updated_at >= before


def test_clip_context_writes_the_clip_key(ctx: JobContext, store: DictJobStore) -> None:
    add_clip(store)
    clip_ctx = JobContext(job_id=JOB_ID, root=ctx.root, store=store, clip_id="clip_01")
    clip_ctx.report(StageName.RENDER, 40, "encoding")
    clip_ctx.record_cost(StageCost(stage=StageName.RENDER, usd_estimate=0.001))
    state = store.get_clip(JOB_ID, "clip_01")
    assert state.progress is not None and state.progress.pct == 40
    assert [c.clip_id for c in state.cost] == ["clip_01"]
    assert ctx.job().progress is None and ctx.job().cost.stages == []


def test_record_cost_accumulates_across_threads(ctx: JobContext) -> None:
    def add() -> None:
        ctx.record_cost(StageCost(stage=StageName.HIGHLIGHTS, usd_estimate=0.01, llm_calls=1))

    threads = [threading.Thread(target=add) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    cost = ctx.job().cost
    assert len(cost.stages) == 20
    assert cost.total_usd == pytest.approx(0.20)


def test_cached_stage_computes_once_and_returns_ref(ctx: JobContext) -> None:
    calls = 0

    def compute(out_dir: Path) -> CaptionFiles:
        nonlocal calls
        calls += 1
        return captions(out_dir, ctx)

    first = cached_stage(ctx, StageName.CAPTIONS, "k1", CaptionFiles, compute)
    second = cached_stage(ctx, StageName.CAPTIONS, "k1", CaptionFiles, compute)
    assert isinstance(first, Stored)
    assert first == second and calls == 1
    assert first.ref == "cache/captions/k1/result.json"
    assert load_ref(ctx.root, first.ref, CaptionFiles) == first.value
    assert first.value.ass_path == "cache/captions/k1/clip.ass"
    assert [c.cached for c in ctx.job().cost.stages] == [True]


def test_cached_stage_recovers_from_partial_and_invalid_entries(ctx: JobContext) -> None:
    out_dir = ctx.root / "cache" / "captions" / "k2"
    out_dir.mkdir(parents=True)
    (out_dir / "leftover.tmp").write_text("partial")  # crash before result.json

    result = cached_stage(ctx, StageName.CAPTIONS, "k2", CaptionFiles, lambda d: captions(d, ctx))
    assert not (out_dir / "leftover.tmp").exists()

    (out_dir / "result.json").write_text('{"old_field": 1}')  # contract changed since
    again = cached_stage(ctx, StageName.CAPTIONS, "k2", CaptionFiles, lambda d: captions(d, ctx))
    assert again == result


def test_compute_failure_leaves_no_result(ctx: JobContext) -> None:
    def fail(out_dir: Path) -> CaptionFiles:
        raise RuntimeError("ffmpeg failed")

    with pytest.raises(RuntimeError):
        cached_stage(ctx, StageName.CAPTIONS, "k3", CaptionFiles, fail)
    assert not (ctx.root / "cache" / "captions" / "k3" / "result.json").exists()
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/test_jobs.py -q`
Expected: `ImportError: cannot import name 'DictJobStore'`.

- [ ] **Step 8: Rewrite `src/clipforge/jobs.py`**

```python
"""Job state, progress, cost and stage caching (ADR-8, ADR-14).

`DictJobStore` keeps each job in single-writer keys of a `KV` (a modal.Dict in production,
`MemoryKV` in tests). Stages get a `JobContext` and call `ctx.report(...)` and
`ctx.record_cost(...)`; in a clip step the context writes that clip's key, not the job's.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from clipforge.models import ClipState, CostSummary, Job, Progress, StageCost, StageName
from clipforge.pipeline.deps import KV

log = logging.getLogger(__name__)

CACHE_DIR = "cache"
RESULT_FILE = "result.json"


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_job_id(seed: str, now: datetime | None = None) -> str:
    """`<yyyymmdd>-<hash8 of seed>-<rand4>`; seed is the source URL, file id or path."""
    day = (now or utcnow()).strftime("%Y%m%d")
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8]
    return f"{day}-{digest}-{secrets.token_hex(2)}"


class DictJobStore:
    """Job state in single-writer KV keys (ADR-14). Values are JSON strings."""

    def __init__(self, kv: KV) -> None:
        self.kv = kv

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"job:{job_id}"

    @staticmethod
    def _clip_key(job_id: str, clip_id: str) -> str:
        return f"job:{job_id}:clip:{clip_id}"

    @staticmethod
    def _attempts_key(job_id: str, step: str, clip_id: str | None) -> str:
        suffix = f":{clip_id}" if clip_id else ""
        return f"job:{job_id}:attempts:{step}{suffix}"

    @staticmethod
    def _claim_key(job_id: str, name: str) -> str:
        return f"job:{job_id}:claim:{name}"

    # ---- core job record

    def save(self, job: Job) -> None:
        self.kv.put(self._job_key(job.job_id), job.model_dump_json())

    def get(self, job_id: str) -> Job:
        raw = self.kv.get(self._job_key(job_id))
        if raw is None:
            raise KeyError(f"unknown job {job_id!r}")
        return Job.model_validate_json(raw)

    def list_job_ids(self) -> list[str]:
        return [
            key.removeprefix("job:")
            for key in self.kv.keys()
            if key.startswith("job:") and key.count(":") == 1
        ]

    # ---- clip records

    def create_clip(self, job_id: str, state: ClipState) -> bool:
        """Set-if-absent, so a retried highlights step never resets a clip in progress."""
        key = self._clip_key(job_id, state.clip_id)
        return self.kv.put(key, state.model_dump_json(), skip_if_exists=True)

    def save_clip(self, job_id: str, state: ClipState) -> None:
        self.kv.put(self._clip_key(job_id, state.clip_id), state.model_dump_json())

    def get_clip(self, job_id: str, clip_id: str) -> ClipState:
        raw = self.kv.get(self._clip_key(job_id, clip_id))
        if raw is None:
            raise KeyError(f"unknown clip {job_id!r}/{clip_id!r}")
        return ClipState.model_validate_json(raw)

    def clips(self, job_id: str, clip_ids: list[str]) -> list[ClipState]:
        return [self.get_clip(job_id, clip_id) for clip_id in clip_ids]

    # ---- attempts and claims

    def incr_attempts(self, job_id: str, step: str, clip_id: str | None = None) -> int:
        key = self._attempts_key(job_id, step, clip_id)
        count = int(self.kv.get(key) or 0) + 1
        self.kv.put(key, str(count))
        return count

    def reset_attempts(self, job_id: str) -> None:
        prefix = f"job:{job_id}:attempts:"
        for key in list(self.kv.keys()):
            if key.startswith(prefix):
                self.kv.delete(key)

    def claim(self, job_id: str, name: str) -> bool:
        """Atomic: True for exactly one caller until released."""
        return self.kv.put(self._claim_key(job_id, name), "1", skip_if_exists=True)

    def release(self, job_id: str, name: str) -> None:
        self.kv.delete(self._claim_key(job_id, name))


@dataclass
class JobContext:
    """Everything a stage needs besides its input: where files go and where progress goes."""

    job_id: str
    root: Path  # JOBS_ROOT; contract paths are relative to it
    store: DictJobStore
    clip_id: str | None = None  # set in clip steps: progress and cost go to the clip's key
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def job_dir(self) -> Path:
        return self.root / self.job_id

    def path(self, rel: str) -> Path:
        """Resolve a contract path (relative to JOBS_ROOT)."""
        return self.root / rel

    def rel(self, path: Path) -> str:
        """Turn an absolute path under JOBS_ROOT into a contract path."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def job(self) -> Job:
        return self.store.get(self.job_id)

    def _update_job(self, change: Callable[[Job], Job]) -> None:
        with self._lock:
            job = change(self.store.get(self.job_id))
            self.store.save(job.model_copy(update={"updated_at": utcnow()}))

    def _update_clip(self, clip_id: str, change: Callable[[ClipState], ClipState]) -> None:
        with self._lock:
            state = change(self.store.get_clip(self.job_id, clip_id))
            self.store.save_clip(self.job_id, state.model_copy(update={"updated_at": utcnow()}))

    def report(self, stage: StageName, pct: float, message: str = "") -> None:
        """Record progress for a long-running stage (CLAUDE.md rule 3)."""
        progress = Progress(
            stage=stage, pct=max(0.0, min(100.0, pct)), message=message, at=utcnow()
        )
        if self.clip_id is None:
            self._update_job(lambda job: job.model_copy(update={"progress": progress}))
        else:
            self._update_clip(self.clip_id, lambda s: s.model_copy(update={"progress": progress}))

    def record_cost(self, cost: StageCost) -> None:
        """Append a cost entry (CLAUDE.md rule 7); clip contexts tag it with the clip id."""
        if self.clip_id is None:
            self._update_job(
                lambda job: job.model_copy(
                    update={"cost": CostSummary(stages=[*job.cost.stages, cost])}
                )
            )
        else:
            tagged = cost.model_copy(update={"clip_id": self.clip_id})
            self._update_clip(
                self.clip_id, lambda s: s.model_copy(update={"cost": [*s.cost, tagged]})
            )


@dataclass(frozen=True)
class Stored[T: BaseModel]:
    """A stage output and the ref of its result.json (relative to JOBS_ROOT)."""

    value: T
    ref: str


def load_ref[T: BaseModel](root: Path, ref: str, model: type[T]) -> T:
    return model.model_validate_json((root / ref).read_text())


def cached_stage[T: BaseModel](
    ctx: JobContext,
    stage: StageName,
    key: str,
    output_type: type[T],
    compute: Callable[[Path], T],
    clip_id: str | None = None,
) -> Stored[T]:
    """Return the cached output for `key`, or run `compute(out_dir)` and cache its result.

    `compute` writes its files into `out_dir` (`<JOBS_ROOT>/cache/<stage>/<key>/`) and returns
    the output contract; `result.json` is written last and marks the entry complete. A missing
    or invalid `result.json` (crash mid-stage, contract changed) is a cache miss.
    """
    ref = f"{CACHE_DIR}/{stage.value}/{key}/{RESULT_FILE}"
    result_file = ctx.root / ref
    out_dir = result_file.parent
    if result_file.exists():
        try:
            result = output_type.model_validate_json(result_file.read_text())
        except ValidationError:
            log.warning("cached %s output %s no longer validates; recomputing", stage, key)
        else:
            ctx.record_cost(StageCost(stage=stage, clip_id=clip_id, cached=True))
            return Stored(result, ref)

    if out_dir.exists():
        shutil.rmtree(out_dir)  # leftovers from an interrupted run
    out_dir.mkdir(parents=True)
    result = compute(out_dir)
    tmp = result_file.with_suffix(".tmp")
    tmp.write_text(result.model_dump_json(indent=2))
    tmp.replace(result_file)
    return Stored(result, ref)
```

- [ ] **Step 9: Run all fast tests, lint and types**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 10: Checkpoint (owner commits)**

Files: `src/clipforge/pipeline/__init__.py`, `src/clipforge/pipeline/errors.py`, `src/clipforge/pipeline/deps.py`, `src/clipforge/jobs.py`, `tests/test_deps.py`, `tests/test_jobs.py`. Message: `feat(pipeline): KV/volume/spawner/notifier interfaces and DictJobStore`.

---

### Task 5: The step chain (steps, fan-in, errors)

**Files:**
- Modify: `src/clipforge/pipeline/deps.py` (add `StageRunner`)
- Create: `src/clipforge/pipeline/selection.py`
- Create: `src/clipforge/pipeline/steps.py`
- Create: `tests/pipeline/__init__.py` (empty), `tests/pipeline/fakes.py`, `tests/pipeline/harness.py`
- Test: `tests/pipeline/test_selection.py`, `tests/pipeline/test_chain.py`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces:
  - A `StageRunner` protocol with five methods:
    - `ingest(ctx, job_input) -> Stored[SourceMedia]`
    - `transcribe(ctx, source) -> Stored[Transcript]`
    - `highlights(ctx, transcript, options) -> Stored[HighlightsResult]`
    - `clip(ctx, spec, transcript) -> Stored[RenderedClip]`
    - `package(ctx, job, source, transcript, rendered: list[RenderedClip]) -> Stored[PackageResult]`
  - `select_clips(result, source, options) -> list[ClipSpec]`.
  - `Step` (a `StrEnum`: `ingest | transcribe | highlights | clip | package`), `STEP_TIMEOUT_S`, `STALL_MARGIN_S`, `MAX_ATTEMPTS` and `STEP_STAGE`.
  - `Deps(store, volume, spawner, stages, root, notifier_for=..., max_attempts=3)` with methods `notifier(job)` and `context(job_id, clip_id=None)`.
  - The step functions `ingest_step(deps, job_id)`, `transcribe_step`, `highlights_step`, `clip_step(deps, job_id, clip_id)` and `package_step`.
  - `dispatch(deps, step, job_id, clip_id=None)`, `fail_job(deps, job_id, stage, error_type, message) -> bool`, `sanitize(message, limit=300) -> str`.
  - Job-scoped files: `<job_id>/clips/<clip_id>.json` (`ClipSpec`) and `<job_id>/clips/<clip_id>.rendered.json` (`RenderedClip` re-bound to this job's spec).

- [ ] **Step 1: Add `StageRunner` to `src/clipforge/pipeline/deps.py`.** Add these imports:

```python
from typing import TYPE_CHECKING, Protocol

from clipforge.models import (
    ClipOptions,
    ClipSpec,
    ClipState,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    RenderedClip,
    SourceMedia,
    Transcript,
)

if TYPE_CHECKING:  # jobs imports this module at runtime; avoid the cycle
    from clipforge.jobs import JobContext, Stored
```

Replace the existing `from typing import Protocol` and `from clipforge.models import ClipState, Job, RenderedClip` with the lines above. Then append:

```python
class StageRunner(Protocol):
    """The pipeline stages as the step chain calls them (real ones arrive in Plan 2).

    Each returns its output plus the ref of the cached result.json (via `cached_stage`).
    """

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]: ...

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]: ...

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]: ...

    def clip(
        self, ctx: JobContext, spec: ClipSpec, transcript: Transcript
    ) -> Stored[RenderedClip]: ...

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]: ...
```

- [ ] **Step 2: Write the failing `tests/pipeline/test_selection.py`**

```python
from clipforge.models import ClipCandidate, ClipOptions, HighlightsResult
from clipforge.pipeline.selection import select_clips
from tests.test_models import make_source  # 1800 s source


def candidate(start: float, end: float, score: float) -> ClipCandidate:
    return ClipCandidate(
        start=start, end=end, score=score, hook="h", title="t", reason="r",
        window_index=0, raw_start=start, raw_end=end,
    )  # fmt: skip


def test_select_top_n_in_rank_order() -> None:
    result = HighlightsResult(
        candidates=[candidate(10, 50, 0.9), candidate(100, 140, 0.8), candidate(200, 240, 0.7)],
        prompt_version="p",
        model="m",
    )
    specs = select_clips(result, make_source(), ClipOptions(n=2))
    assert [(s.clip_id, s.rank, s.start) for s in specs] == [("clip_01", 1, 10), ("clip_02", 2, 100)]


def test_skips_candidates_past_the_source_end() -> None:
    result = HighlightsResult(
        candidates=[candidate(1790, 1830, 0.95), candidate(10, 50, 0.9)],
        prompt_version="p",
        model="m",
    )
    specs = select_clips(result, make_source(), ClipOptions(n=5))
    assert [(s.clip_id, s.start) for s in specs] == [("clip_01", 10)]


def test_no_candidates() -> None:
    empty = HighlightsResult(candidates=[], prompt_version="p", model="m")
    assert select_clips(empty, make_source(), ClipOptions()) == []
```

- [ ] **Step 3: Create `src/clipforge/pipeline/selection.py`**

```python
"""Turn ranked highlight candidates into this job's clip specs."""

from __future__ import annotations

from clipforge.models import ClipOptions, ClipSpec, HighlightsResult, SourceMedia


def select_clips(
    result: HighlightsResult, source: SourceMedia, options: ClipOptions
) -> list[ClipSpec]:
    """The top `options.n` candidates as ClipSpecs; `clip_01` is the best.

    `result.candidates` is already ranked and length-filtered by the highlights stage, which
    is cached without `n` (ADR-8). This only skips candidates ending after the source and
    assigns ids.
    """
    specs: list[ClipSpec] = []
    for candidate in result.candidates:
        if len(specs) == options.n:
            break
        if candidate.end > source.duration_s:
            continue
        rank = len(specs) + 1
        specs.append(
            ClipSpec(
                clip_id=f"clip_{rank:02d}",
                rank=rank,
                source=source,
                start=candidate.start,
                end=candidate.end,
                candidate=candidate,
                options=options,
            )
        )
    return specs
```

- [ ] **Step 4: Run the selection tests**

Run: `uv run pytest tests/pipeline/test_selection.py -q` (create `tests/pipeline/__init__.py` first)
Expected: 3 passed.

- [ ] **Step 5: Create the fake stages in `tests/pipeline/fakes.py`**

```python
"""Fake stages for chain tests: real cached_stage and files, no ffmpeg, LLM or GPU."""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import (
    ClipCandidate,
    ClipOptions,
    ClipSpec,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    ProbeInfo,
    RenderedClip,
    SourceMedia,
    StageCost,
    StageName,
    Transcript,
)
from clipforge.pipeline.errors import PermanentError
from tests.builders import build_long_transcript

SOURCE_DURATION_S = 600.0


def _probe(duration: float) -> ProbeInfo:
    return ProbeInfo(
        width=1080, height=1920, duration_s=duration, video_duration_s=duration,
        audio_duration_s=duration, fps=30.0, video_codec="h264", pix_fmt="yuv420p",
        audio_codec="aac", n_video_streams=1, n_audio_streams=1, size_bytes=1000,
    )  # fmt: skip


@dataclass
class FakeStages:
    """Configurable failures, keyed by stage name ("ingest", ...) or clip id ("clip_03")."""

    n_candidates: int = 5
    reverse: bool = False  # reverse the ranking (same time ranges, different clip ids)
    transient: Counter[str] = field(default_factory=Counter)  # failures left per name
    permanent: dict[str, str] = field(default_factory=dict)  # name -> user message
    barrier: threading.Barrier | None = None  # clip computes wait here, to force a race
    calls: Counter[str] = field(default_factory=Counter)  # every call
    computes: Counter[str] = field(default_factory=Counter)  # cache misses
    packaged: list[str] = field(default_factory=list)  # clip ids given to the last package
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _enter(self, name: str) -> None:
        with self._lock:
            self.calls[name] += 1
            if self.transient[name] > 0:
                self.transient[name] -= 1
                raise RuntimeError(f"{name} blip")
        if name in self.permanent:
            raise PermanentError(self.permanent[name])

    def _computed(self, name: str) -> None:
        with self._lock:
            self.computes[name] += 1

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]:
        self._enter("ingest")
        key = cache_key("ingest", "fake", [], {"source": str(job_input.source_url)})

        def compute(out_dir: Path) -> SourceMedia:
            self._computed("ingest")
            (out_dir / "source.mp4").write_bytes(b"video")
            (out_dir / "audio.wav").write_bytes(b"audio")
            ctx.report(StageName.INGEST, 100, "downloaded")
            return SourceMedia(
                video_path=ctx.rel(out_dir / "source.mp4"),
                audio_path=ctx.rel(out_dir / "audio.wav"),
                source_hash="a" * 64,
                duration_s=SOURCE_DURATION_S,
                fps=30.0,
                width=1920,
                height=1080,
                video_codec="h264",
                size_bytes=5,
            )

        return cached_stage(ctx, StageName.INGEST, key, SourceMedia, compute)

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]:
        self._enter("transcribe")
        key = cache_key("transcribe", "fake", [], {"source_hash": source.source_hash})

        def compute(out_dir: Path) -> Transcript:
            self._computed("transcribe")
            ctx.record_cost(
                StageCost(stage=StageName.TRANSCRIBE, gpu_s=10.0, gpu_type="L4", usd_estimate=0.002)
            )
            return build_long_transcript(SOURCE_DURATION_S)

        return cached_stage(ctx, StageName.TRANSCRIBE, key, Transcript, compute)

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]:
        self._enter("highlights")
        key = cache_key(
            "highlights", "fake", [],
            {"n_candidates": str(self.n_candidates), "reverse": str(self.reverse),
             "min": str(options.min_len), "max": str(options.max_len)},
        )  # fmt: skip

        def compute(out_dir: Path) -> HighlightsResult:
            self._computed("highlights")
            ctx.record_cost(
                StageCost(
                    stage=StageName.HIGHLIGHTS, llm_model="fake", llm_input_tokens=1000,
                    llm_output_tokens=100, llm_calls=2, usd_estimate=0.0015,
                )  # fmt: skip
            )
            order = list(range(self.n_candidates))
            if self.reverse:
                order.reverse()
            candidates = [
                ClipCandidate(
                    start=10.0 + 60 * i, end=45.0 + 60 * i, score=round(0.9 - 0.1 * rank, 2),
                    hook=f"hook {i}", title=f"title {i}", reason="fake", window_index=i,
                    raw_start=10.0 + 60 * i, raw_end=45.0 + 60 * i,
                )  # fmt: skip
                for rank, i in enumerate(order)
            ]
            return HighlightsResult(candidates=candidates, prompt_version="fake_v1", model="fake")

        return cached_stage(ctx, StageName.HIGHLIGHTS, key, HighlightsResult, compute)

    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        self._enter(spec.clip_id)
        # Keyed on the time range, never on clip_id or rank (ADR-8).
        key = cache_key(
            "clip",
            "fake",
            [],
            {
                "source_hash": spec.source.source_hash,
                "start": str(spec.start),
                "end": str(spec.end),
            },
        )

        def compute(out_dir: Path) -> RenderedClip:
            self._computed("clip")
            ctx.report(StageName.RENDER, 50, "rendering")
            ctx.record_cost(StageCost(stage=StageName.RENDER, wall_s=1.0, usd_estimate=0.001))
            (out_dir / "clip.mp4").write_bytes(b"clip")
            (out_dir / "clip.srt").write_text("1\n")
            if self.barrier is not None:
                self.barrier.wait(timeout=5)
            return RenderedClip(
                clip_id=spec.clip_id,
                spec=spec,
                video_path=ctx.rel(out_dir / "clip.mp4"),
                srt_path=ctx.rel(out_dir / "clip.srt"),
                encoder="libx264",
                probe=_probe(spec.duration_s),
            )

        return cached_stage(ctx, StageName.RENDER, key, RenderedClip, compute, clip_id=spec.clip_id)

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]:
        self._enter("package")
        self.packaged = [r.clip_id for r in rendered]
        key = cache_key(
            "package", "fake", [], {"job": job.job_id, "clips": ",".join(self.packaged)}
        )

        def compute(out_dir: Path) -> PackageResult:
            self._computed("package")
            (out_dir / "job.zip").write_bytes(b"zip")
            return PackageResult(
                output_dir=ctx.rel(out_dir),
                zip_path=ctx.rel(out_dir / "job.zip"),
                metadata_path=ctx.rel(out_dir / "metadata.json"),
                clips=[],
            )

        return cached_stage(ctx, StageName.PACKAGE, key, PackageResult, compute)
```

- [ ] **Step 6: Create the chain runner in `tests/pipeline/harness.py`**

```python
"""Runs the step chain in-process: MemoryKV, NullVolume, QueueSpawner, fake stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from clipforge.jobs import DictJobStore, new_job_id, utcnow
from clipforge.models import Job, JobInput
from clipforge.pipeline.deps import MemoryKV, NullVolume, QueueSpawner, RecordingNotifier
from clipforge.pipeline.steps import Deps, Step, dispatch
from tests.pipeline.fakes import FakeStages

SOURCE_URL = "https://media.example.com/episode.mp4"


@dataclass
class Harness:
    root: Path
    store: DictJobStore
    spawner: QueueSpawner
    notifier: RecordingNotifier
    stages: FakeStages
    volume: NullVolume
    deps: Deps
    retries_seen: int = field(default=0)

    @classmethod
    def build(cls, root: Path, stages: FakeStages | None = None) -> Harness:
        store = DictJobStore(MemoryKV())
        spawner = QueueSpawner()
        notifier = RecordingNotifier()
        volume = NullVolume()
        fake = stages or FakeStages()
        deps = Deps(
            store=store, volume=volume, spawner=spawner, stages=fake, root=root,
            notifier_for=lambda job: notifier,
        )  # fmt: skip
        return cls(root, store, spawner, notifier, fake, volume, deps)

    def submit(self, **options: Any) -> str:
        """Create a job the way service.create_job will (Task 7) and queue its ingest step."""
        now = utcnow()
        job_input = JobInput.model_validate(
            {"source_url": SOURCE_URL, "permission": "own", "options": options}
        )
        job = Job(job_id=new_job_id(SOURCE_URL, now), input=job_input, created_at=now, updated_at=now)
        self.store.save(job)
        self.spawner.spawn(Step.INGEST, job.job_id)
        return job.job_id

    def run(self, max_calls: int = 300) -> None:
        """Run queued spawns until idle, re-running a raising step like Modal Retries would."""
        calls = 0
        while self.spawner.queue:
            call = self.spawner.queue.popleft()
            calls += 1
            if calls > max_calls:
                raise AssertionError("the chain did not settle")
            try:
                dispatch(self.deps, call.step, call.job_id, call.clip_id)
            except Exception:
                self.retries_seen += 1
                self.spawner.queue.appendleft(call)

    def run_until(self, step: Step) -> None:
        """Run queued spawns until the next one is `step` (or the queue is empty)."""
        while self.spawner.queue and self.spawner.queue[0].step != step:
            call = self.spawner.queue.popleft()
            dispatch(self.deps, call.step, call.job_id, call.clip_id)

    def event_kinds(self) -> list[str]:
        return [kind for kind, _, _ in self.notifier.events]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness.build(tmp_path)
```

Create `tests/pipeline/conftest.py` so the fixture is found:

```python
from tests.pipeline.harness import harness  # noqa: F401  (pytest fixture)
```

- [ ] **Step 7: Write the failing `tests/pipeline/test_chain.py`**

```python
import threading
from collections import Counter
from pathlib import Path

from clipforge.jobs import load_ref
from clipforge.models import ClipSpec, ClipStatus, JobStatus, RenderedClip, StageName
from clipforge.pipeline.steps import Step, dispatch, sanitize
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness


class ExplodingNotifier:
    def clip_ready(self, job: object, clip: object, rendered: object) -> None:
        raise RuntimeError("telegram down")

    def done(self, job: object) -> None:
        raise RuntimeError("telegram down")

    def failed(self, job: object) -> None:
        raise RuntimeError("telegram down")


# ---- happy path and caching


def test_happy_path(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run()
    job = harness.store.get(job_id)
    assert job.status is JobStatus.DONE
    assert job.output_zip is not None and (harness.root / job.output_zip).exists()
    assert job.clip_ids == [f"clip_{i:02d}" for i in range(1, 6)]
    assert set(job.outputs) == {
        StageName.INGEST, StageName.TRANSCRIBE, StageName.HIGHLIGHTS, StageName.PACKAGE
    }
    clips = harness.store.clips(job_id, job.clip_ids)
    assert all(c.status is ClipStatus.DONE and c.telegram_sent for c in clips)
    kinds = harness.event_kinds()
    assert kinds.count("clip_ready") == 5 and kinds.count("done") == 1 and kinds[-1] == "done"
    assert harness.stages.calls["package"] == 1 and harness.retries_seen == 0
    assert harness.volume.commits >= 5 and harness.volume.reloads >= 9


def test_clip_specs_are_job_scoped_and_ranked(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run()
    spec_file = harness.root / job_id / "clips" / "clip_01.json"
    spec = ClipSpec.model_validate_json(spec_file.read_text())
    assert spec.rank == 1 and spec.candidate.score == 0.9 and spec.start == 10.0


def test_second_job_reuses_cached_stages(harness: Harness) -> None:
    harness.submit()
    harness.run()
    second = harness.submit(n=3)
    harness.run()
    job = harness.store.get(second)
    assert job.status is JobStatus.DONE and len(job.clip_ids) == 3
    computes = harness.stages.computes
    assert (computes["ingest"], computes["transcribe"], computes["highlights"]) == (1, 1, 1)
    assert computes["clip"] == 5  # the second job's 3 clips all came from the cache
    cached = {c.stage for c in job.cost.stages if c.cached}
    assert {StageName.INGEST, StageName.TRANSCRIBE, StageName.HIGHLIGHTS} <= cached


def test_cached_clip_is_rebound_to_this_jobs_spec(harness: Harness) -> None:
    harness.submit()
    harness.run()
    harness.stages.reverse = True  # same five ranges, opposite ranking
    second = harness.submit()
    harness.run()
    assert harness.stages.computes["clip"] == 5  # every range reused from the cache
    state = harness.store.get_clip(second, "clip_01")
    assert state.result_ref is not None
    rendered = load_ref(harness.root, state.result_ref, RenderedClip)
    assert rendered.clip_id == "clip_01"
    assert rendered.spec.rank == 1 and rendered.spec.start == 250.0  # best range in job 2


# ---- review focus: duplicates, stale and unknown steps


def test_duplicate_spawns_do_not_duplicate_work(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.spawn(Step.INGEST, job_id)  # Modal delivers a spawn twice
    harness.run()
    kinds = harness.event_kinds()
    assert kinds.count("done") == 1 and kinds.count("clip_ready") == 5
    assert harness.stages.calls["package"] == 1
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_steps_for_a_failed_job_do_nothing(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(permanent={"ingest": "not a direct media link"}))
    job_id = h.submit()
    h.run()
    dispatch(h.deps, Step.TRANSCRIBE, job_id)
    dispatch(h.deps, Step.CLIP, job_id, "clip_01")
    assert h.stages.calls["transcribe"] == 0 and h.stages.calls["clip_01"] == 0
    assert not h.spawner.queue


def test_step_for_unknown_job_is_ignored(harness: Harness) -> None:
    dispatch(harness.deps, Step.TRANSCRIBE, "20260923-deadbeef-0000")
    assert not harness.spawner.queue and harness.stages.calls["transcribe"] == 0


# ---- errors (ADR-15)


def test_permanent_error_fails_at_once(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(permanent={"ingest": "not a direct media link"}))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert (job.error.stage, job.error.error_type) == (StageName.INGEST, "permanent")
    assert job.error.message == "not a direct media link"
    assert h.stages.calls["ingest"] == 1 and h.retries_seen == 0
    assert h.event_kinds() == ["failed"]


def test_transient_error_is_retried(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(transient=Counter({"transcribe": 2})))
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.DONE
    assert h.stages.calls["transcribe"] == 3 and h.retries_seen == 2


def test_gives_up_after_max_attempts(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(transient=Counter({"transcribe": 99})))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert (job.error.stage, job.error.error_type) == (StageName.TRANSCRIBE, "RuntimeError")
    assert job.error.message == "RuntimeError: transcribe blip"
    assert h.stages.calls["transcribe"] == 3 and h.retries_seen == 2
    assert h.event_kinds() == ["failed"]


def test_one_clip_failing_does_not_stop_the_others(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(permanent={"clip_03": "corrupt frame"}))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.DONE
    failed = h.store.get_clip(job_id, "clip_03")
    assert failed.status is ClipStatus.FAILED and failed.error is not None
    assert (failed.error.stage, failed.error.message) == (StageName.RENDER, "corrupt frame")
    assert h.stages.packaged == ["clip_01", "clip_02", "clip_04", "clip_05"]
    kinds = h.event_kinds()
    assert kinds.count("clip_ready") == 4 and kinds.count("done") == 1


def test_all_clips_failing_fails_the_job(tmp_path: Path) -> None:
    fail_all = {f"clip_{i:02d}": "boom" for i in range(1, 6)}
    h = Harness.build(tmp_path, FakeStages(permanent=fail_all))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert (job.error.stage, job.error.message) == (StageName.PACKAGE, "all 5 clips failed")
    assert h.event_kinds() == ["failed"]


def test_no_candidates_fails_highlights(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(n_candidates=0))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert job.error.stage is StageName.HIGHLIGHTS
    assert job.error.message == "no clip-worthy segments found in this video"


def test_notifier_failure_does_not_fail_the_job(harness: Harness) -> None:
    harness.deps.notifier_for = lambda job: ExplodingNotifier()
    job_id = harness.submit()
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_fan_in_spawns_package_exactly_once_under_concurrency(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(barrier=threading.Barrier(5)))
    job_id = h.submit()
    h.run_until(Step.CLIP)
    clip_calls = [h.spawner.queue.popleft() for _ in range(5)]
    assert not h.spawner.queue
    threads = [
        threading.Thread(target=dispatch, args=(h.deps, c.step, c.job_id, c.clip_id))
        for c in clip_calls
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [c.step for c in h.spawner.queue] == [Step.PACKAGE]
    h.run()
    assert h.store.get(job_id).status is JobStatus.DONE


def test_sanitize_strips_query_strings_and_caps_length() -> None:
    message = "404 for https://cdn.example.com/v.mp4?token=abc123 while downloading"
    assert sanitize(message) == "404 for https://cdn.example.com/v.mp4 while downloading"
    assert len(sanitize("x" * 1000)) == 300
```

- [ ] **Step 8: Run to verify it fails**

Run: `uv run pytest tests/pipeline -q`
Expected: `ModuleNotFoundError: No module named 'clipforge.pipeline.steps'`.

- [ ] **Step 9: Create `src/clipforge/pipeline/steps.py`**

```python
"""The step chain (ADR-12): one function per Modal step. Modal-free.

Each step reloads the Volume, loads the job, runs its stage (cached, ADR-8), commits the
Volume, records the output ref and spawns the next step. Errors follow ADR-15:
`PermanentError` fails at once; other exceptions are re-raised for Modal to retry until
`max_attempts`, then fail cleanly.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from clipforge.jobs import DictJobStore, JobContext, load_ref, utcnow
from clipforge.models import (
    ClipSpec,
    ClipState,
    ClipStatus,
    Job,
    JobError,
    JobStatus,
    RenderedClip,
    SourceMedia,
    StageName,
    Transcript,
)
from clipforge.pipeline.deps import (
    Notifier,
    NullNotifier,
    SafeNotifier,
    Spawner,
    StageRunner,
    Volume,
)
from clipforge.pipeline.errors import PermanentError
from clipforge.pipeline.selection import select_clips

log = logging.getLogger(__name__)


class Step(StrEnum):
    INGEST = "ingest"
    TRANSCRIBE = "transcribe"
    HIGHLIGHTS = "highlights"
    CLIP = "clip"
    PACKAGE = "package"


# Modal function timeouts (app.py uses these) and the sweeper's stall margin (ADR-15).
STEP_TIMEOUT_S: dict[Step, int] = {
    Step.INGEST: 15 * 60,
    Step.TRANSCRIBE: 30 * 60,
    Step.HIGHLIGHTS: 10 * 60,
    Step.CLIP: 10 * 60,
    Step.PACKAGE: 10 * 60,
}
STALL_MARGIN_S = 5 * 60
MAX_ATTEMPTS = 3  # first try + Modal Retries(max_retries=2)

# The stage a step's failures are reported under.
STEP_STAGE: dict[Step, StageName] = {
    Step.INGEST: StageName.INGEST,
    Step.TRANSCRIBE: StageName.TRANSCRIBE,
    Step.HIGHLIGHTS: StageName.HIGHLIGHTS,
    Step.CLIP: StageName.RENDER,
    Step.PACKAGE: StageName.PACKAGE,
}

_URL_QUERY = re.compile(r"(https?://[^\s?#]+)[?#]\S*")


def sanitize(message: str, limit: int = 300) -> str:
    """User-facing error text: URL query strings removed (they can carry tokens), capped."""
    cleaned = _URL_QUERY.sub(r"\1", message).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _no_notifier(job: Job) -> Notifier:
    return NullNotifier()


@dataclass
class Deps:
    store: DictJobStore
    volume: Volume
    spawner: Spawner
    stages: StageRunner
    root: Path  # JOBS_ROOT
    notifier_for: Callable[[Job], Notifier] = _no_notifier
    max_attempts: int = MAX_ATTEMPTS

    def notifier(self, job: Job) -> Notifier:
        return SafeNotifier(self.notifier_for(job))

    def context(self, job_id: str, clip_id: str | None = None) -> JobContext:
        return JobContext(job_id=job_id, root=self.root, store=self.store, clip_id=clip_id)


# ---- helpers


def _set(job: Job, **changes: object) -> Job:
    return job.model_copy(update={**changes, "updated_at": utcnow()})


def _set_clip(state: ClipState, **changes: object) -> ClipState:
    return state.model_copy(update={**changes, "updated_at": utcnow()})


def _start(deps: Deps, job_id: str, stage: StageName) -> None:
    deps.store.save(_set(deps.store.get(job_id), status=JobStatus.RUNNING, stage=stage))


def _advance(deps: Deps, job_id: str, stage: StageName, ref: str, next_step: Step) -> None:
    """Commit files, record the output ref, then hand over to the next step."""
    deps.volume.commit()
    job = deps.store.get(job_id)
    deps.store.save(_set(job, outputs={**job.outputs, stage: ref}))
    deps.spawner.spawn(next_step, job_id)


def _output[T: BaseModel](deps: Deps, job: Job, stage: StageName, model: type[T]) -> T:
    ref = job.outputs.get(stage)
    if ref is None:
        raise RuntimeError(f"job {job.job_id} has no {stage} output yet")
    return load_ref(deps.root, ref, model)


def _write_json(deps: Deps, rel: str, model: BaseModel) -> None:
    path = deps.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2))


# ---- failure handling (ADR-15)


def fail_job(deps: Deps, job_id: str, stage: StageName, error_type: str, message: str) -> bool:
    """Mark the job failed and notify, once. Returns False if it had already failed."""
    if not deps.store.claim(job_id, "failed"):
        return False
    error = JobError(stage=stage, error_type=error_type, message=sanitize(message))
    job = _set(deps.store.get(job_id), status=JobStatus.FAILED, error=error)
    deps.store.save(job)
    deps.notifier(job).failed(job)
    return True


def _fail_clip(deps: Deps, job_id: str, clip_id: str, error_type: str, message: str) -> None:
    state = deps.store.get_clip(job_id, clip_id)
    stage = state.progress.stage if state.progress else StageName.RENDER
    error = JobError(stage=stage, error_type=error_type, message=sanitize(message))
    deps.store.save_clip(job_id, _set_clip(state, status=ClipStatus.FAILED, error=error))
    _maybe_package(deps, job_id)


def _maybe_package(deps: Deps, job_id: str) -> None:
    """Fan-in: the first caller to see every clip finished spawns package (ADR-12)."""
    job = deps.store.get(job_id)
    clips = deps.store.clips(job_id, job.clip_ids)
    if clips and all(c.finished for c in clips) and deps.store.claim(job_id, "package"):
        deps.spawner.spawn(Step.PACKAGE, job_id)


def _guarded(
    deps: Deps,
    step: Step,
    job_id: str,
    body: Callable[[Job], None],
    clip_id: str | None = None,
) -> None:
    deps.volume.reload()
    try:
        job = deps.store.get(job_id)
    except KeyError:
        log.warning("%s step for unknown job %s; ignoring", step, job_id)
        return
    if job.status in (JobStatus.DONE, JobStatus.FAILED):
        log.info("%s step for %s job %s; ignoring", step, job.status, job_id)
        return
    attempt = deps.store.incr_attempts(job_id, step, clip_id)
    try:
        body(job)
    except PermanentError as exc:
        _handle_failure(deps, step, job_id, "permanent", exc.user_message, clip_id)
    except Exception as exc:
        if attempt < deps.max_attempts:
            log.warning(
                "%s step attempt %d/%d failed for %s",
                step, attempt, deps.max_attempts, job_id, exc_info=True,
            )  # fmt: skip
            raise
        log.exception("%s step failed for %s after %d attempts", step, job_id, attempt)
        name = type(exc).__name__
        _handle_failure(deps, step, job_id, name, f"{name}: {exc}", clip_id)


def _handle_failure(
    deps: Deps, step: Step, job_id: str, error_type: str, message: str, clip_id: str | None
) -> None:
    if clip_id is not None:
        _fail_clip(deps, job_id, clip_id, error_type, message)
    else:
        fail_job(deps, job_id, STEP_STAGE[step], error_type, message)


# ---- steps


def ingest_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        _start(deps, job_id, StageName.INGEST)
        stored = deps.stages.ingest(deps.context(job_id), job.input)
        _advance(deps, job_id, StageName.INGEST, stored.ref, Step.TRANSCRIBE)

    _guarded(deps, Step.INGEST, job_id, body)


def transcribe_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        source = _output(deps, job, StageName.INGEST, SourceMedia)
        _start(deps, job_id, StageName.TRANSCRIBE)
        stored = deps.stages.transcribe(deps.context(job_id), source)
        _advance(deps, job_id, StageName.TRANSCRIBE, stored.ref, Step.HIGHLIGHTS)

    _guarded(deps, Step.TRANSCRIBE, job_id, body)


def highlights_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        source = _output(deps, job, StageName.INGEST, SourceMedia)
        transcript = _output(deps, job, StageName.TRANSCRIBE, Transcript)
        _start(deps, job_id, StageName.HIGHLIGHTS)
        options = job.input.options
        stored = deps.stages.highlights(deps.context(job_id), transcript, options)
        specs = select_clips(stored.value, source, options)
        if not specs:
            raise PermanentError("no clip-worthy segments found in this video")

        spec_refs = {spec.clip_id: f"{job_id}/clips/{spec.clip_id}.json" for spec in specs}
        for spec in specs:
            _write_json(deps, spec_refs[spec.clip_id], spec)
        deps.volume.commit()

        now = utcnow()
        for clip_id, ref in spec_refs.items():
            deps.store.create_clip(job_id, ClipState(clip_id=clip_id, spec_ref=ref, updated_at=now))
        job = deps.store.get(job_id)
        deps.store.save(
            _set(
                job,
                stage=StageName.RENDER,
                outputs={**job.outputs, StageName.HIGHLIGHTS: stored.ref},
                clip_ids=list(spec_refs),
            )
        )
        for clip_id in spec_refs:
            deps.spawner.spawn(Step.CLIP, job_id, clip_id)

    _guarded(deps, Step.HIGHLIGHTS, job_id, body)


def clip_step(deps: Deps, job_id: str, clip_id: str) -> None:
    def body(job: Job) -> None:
        state = deps.store.get_clip(job_id, clip_id)
        if state.status is ClipStatus.DONE:  # duplicate spawn
            _maybe_package(deps, job_id)
            return
        spec = load_ref(deps.root, state.spec_ref, ClipSpec)
        transcript = _output(deps, job, StageName.TRANSCRIBE, Transcript)
        deps.store.save_clip(job_id, _set_clip(state, status=ClipStatus.RUNNING, error=None))

        stored = deps.stages.clip(deps.context(job_id, clip_id), spec, transcript)
        # The cached render may come from another job with a different rank for this range:
        # bind it to this job's spec before anyone reads it (ADR-8).
        rendered = stored.value.model_copy(update={"clip_id": spec.clip_id, "spec": spec})
        rendered_ref = f"{job_id}/clips/{clip_id}.rendered.json"
        _write_json(deps, rendered_ref, rendered)
        deps.volume.commit()

        state = _set_clip(
            deps.store.get_clip(job_id, clip_id), status=ClipStatus.DONE, result_ref=rendered_ref
        )
        deps.store.save_clip(job_id, state)
        if not state.telegram_sent:
            deps.notifier(job).clip_ready(job, state, rendered)
            deps.store.save_clip(job_id, _set_clip(state, telegram_sent=True))
        _maybe_package(deps, job_id)

    _guarded(deps, Step.CLIP, job_id, body, clip_id=clip_id)


def package_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        clips = deps.store.clips(job_id, job.clip_ids)
        rendered = [
            load_ref(deps.root, c.result_ref, RenderedClip)
            for c in clips
            if c.status is ClipStatus.DONE and c.result_ref is not None
        ]
        if not rendered:
            raise PermanentError(f"all {len(clips)} clips failed")
        source = _output(deps, job, StageName.INGEST, SourceMedia)
        transcript = _output(deps, job, StageName.TRANSCRIBE, Transcript)
        _start(deps, job_id, StageName.PACKAGE)
        stored = deps.stages.package(deps.context(job_id), job, source, transcript, rendered)
        deps.volume.commit()

        job = deps.store.get(job_id)
        job = _set(
            job,
            status=JobStatus.DONE,
            outputs={**job.outputs, StageName.PACKAGE: stored.ref},
            output_zip=stored.value.zip_path,
        )
        deps.store.save(job)
        deps.notifier(job).done(job)

    _guarded(deps, Step.PACKAGE, job_id, body)


def dispatch(deps: Deps, step: str, job_id: str, clip_id: str | None = None) -> None:
    """Run one step by name: what a spawned Modal function (or the test harness) calls."""
    match Step(step):
        case Step.INGEST:
            ingest_step(deps, job_id)
        case Step.TRANSCRIBE:
            transcribe_step(deps, job_id)
        case Step.HIGHLIGHTS:
            highlights_step(deps, job_id)
        case Step.CLIP:
            if clip_id is None:
                raise ValueError("the clip step needs a clip_id")
            clip_step(deps, job_id, clip_id)
        case Step.PACKAGE:
            package_step(deps, job_id)
```

- [ ] **Step 10: Run the chain tests**

Run: `uv run pytest tests/pipeline -q`
Expected: all pass. If `test_fan_in_spawns_package_exactly_once_under_concurrency` hangs, check that the barrier party count (5) matches `n` (default 5).

- [ ] **Step 11: Run the full fast suite, lint and types**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 12: Checkpoint (owner commits)**

Files: `src/clipforge/pipeline/{deps,selection,steps}.py`, `tests/pipeline/*`. Message: `feat(pipeline): event-driven step chain with atomic fan-in and error handling`.

---

### Task 6: Resume and the stall sweeper

**Files:**
- Modify: `src/clipforge/pipeline/steps.py` (append)
- Test: `tests/pipeline/test_recovery.py`

**Interfaces:**
- Consumes: `Deps`, `Step`, `fail_job`, `_set`, `_set_clip`, `STEP_TIMEOUT_S`, `STALL_MARGIN_S` (Task 5).
- Produces:
  - `JobNotResumable(Exception)`.
  - `resume(deps, job_id) -> Step | None`, which returns the step it spawned, `None` for a done job, and raises `JobNotResumable` for a queued or running job.
  - `sweep(deps, now: datetime | None = None) -> list[str]`, which returns the job IDs it failed.

- [ ] **Step 1: Write the failing `tests/pipeline/test_recovery.py`**

```python
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest

from clipforge.models import ClipStatus, JobStatus
from clipforge.pipeline.steps import JobNotResumable, Step, resume, sweep
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness


def test_resume_continues_from_first_incomplete_step(tmp_path: Path) -> None:
    stages = FakeStages(transient=Counter({"transcribe": 99}))
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.FAILED
    stages.transient.clear()
    assert resume(h.deps, job_id) is Step.TRANSCRIBE
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.DONE and job.error is None
    assert stages.computes["ingest"] == 1  # not redone
    kinds = h.event_kinds()
    assert kinds[0] == "failed" and kinds.count("clip_ready") == 5 and kinds[-1] == "done"


def test_resume_after_package_failure_skips_clips(tmp_path: Path) -> None:
    stages = FakeStages(transient=Counter({"package": 99}))
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.FAILED
    stages.transient.clear()
    assert resume(h.deps, job_id) is Step.PACKAGE
    h.run()
    assert h.store.get(job_id).status is JobStatus.DONE
    assert stages.calls["clip_01"] == 1 and stages.computes["clip"] == 5


def test_resume_reruns_failed_clips(tmp_path: Path) -> None:
    stages = FakeStages(permanent={f"clip_{i:02d}": "boom" for i in range(1, 6)})
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.FAILED
    stages.permanent.clear()
    assert resume(h.deps, job_id) is Step.CLIP
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.DONE
    assert all(c.status is ClipStatus.DONE for c in h.store.clips(job_id, job.clip_ids))
    assert stages.calls["clip_01"] == 2


def test_resume_rules(harness: Harness) -> None:
    job_id = harness.submit()
    with pytest.raises(JobNotResumable):
        resume(harness.deps, job_id)  # still queued
    harness.run()
    assert resume(harness.deps, job_id) is None  # done: nothing to do
    assert not harness.spawner.queue


def test_sweeper_fails_stalled_jobs(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.queue.clear()  # the ingest spawn was lost
    start = harness.store.get(job_id).updated_at
    assert sweep(harness.deps, now=start + timedelta(minutes=19)) == []  # 15 + 5 margin
    assert sweep(harness.deps, now=start + timedelta(minutes=21)) == [job_id]
    job = harness.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert job.error.error_type == "stalled"
    assert job.error.message.startswith("stalled at ingest")
    assert harness.event_kinds() == ["failed"]
    assert sweep(harness.deps, now=start + timedelta(hours=2)) == []  # already failed
    assert resume(harness.deps, job_id) is Step.INGEST
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_sweeper_counts_clip_activity(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run_until(Step.CLIP)
    harness.spawner.queue.clear()  # clip spawns lost
    job = harness.store.get(job_id)
    start = job.updated_at
    busy = harness.store.get_clip(job_id, "clip_01").model_copy(
        update={"updated_at": start + timedelta(minutes=14)}
    )
    harness.store.save_clip(job_id, busy)
    assert sweep(harness.deps, now=start + timedelta(minutes=16)) == []  # clip active 2 min ago
    assert sweep(harness.deps, now=start + timedelta(minutes=14 + 16)) == [job_id]
    job = harness.store.get(job_id)
    assert job.error is not None and job.error.message.startswith("stalled at render")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_recovery.py -q`
Expected: `ImportError: cannot import name 'JobNotResumable'`.

- [ ] **Step 3: Append to `src/clipforge/pipeline/steps.py`** (and add `from datetime import datetime` to the imports)

```python
# ---- recovery (ADR-12, ADR-15)


class JobNotResumable(Exception):
    """Resume was asked for a job that is still queued or running."""


def resume(deps: Deps, job_id: str) -> Step | None:
    """Continue a failed job from its first incomplete step; cached work is skipped.

    Returns the step spawned, or None for a job that is already done.
    """
    job = deps.store.get(job_id)
    if job.status is JobStatus.DONE:
        return None
    if job.status is not JobStatus.FAILED:
        raise JobNotResumable(
            f"job {job_id} is still {job.status}; only failed jobs can be resumed"
        )

    deps.store.release(job_id, "failed")
    deps.store.reset_attempts(job_id)
    job = _set(job, status=JobStatus.RUNNING, error=None)
    deps.store.save(job)

    for stage, step in (
        (StageName.INGEST, Step.INGEST),
        (StageName.TRANSCRIBE, Step.TRANSCRIBE),
        (StageName.HIGHLIGHTS, Step.HIGHLIGHTS),
    ):
        if stage not in job.outputs:
            deps.spawner.spawn(step, job_id)
            return step

    deps.store.release(job_id, "package")
    unfinished = [
        c for c in deps.store.clips(job_id, job.clip_ids) if c.status is not ClipStatus.DONE
    ]
    if not unfinished:
        deps.store.claim(job_id, "package")  # a late duplicate clip step must not spawn it again
        deps.spawner.spawn(Step.PACKAGE, job_id)
        return Step.PACKAGE
    for clip in unfinished:
        deps.store.save_clip(job_id, _set_clip(clip, status=ClipStatus.PENDING, error=None))
        deps.spawner.spawn(Step.CLIP, job_id, clip.clip_id)
    return Step.CLIP


_STAGE_STEP: dict[StageName | None, Step] = {
    None: Step.INGEST,
    StageName.INGEST: Step.INGEST,
    StageName.TRANSCRIBE: Step.TRANSCRIBE,
    StageName.HIGHLIGHTS: Step.HIGHLIGHTS,
    StageName.REFRAME: Step.CLIP,
    StageName.CAPTIONS: Step.CLIP,
    StageName.RENDER: Step.CLIP,
    StageName.PACKAGE: Step.PACKAGE,
}


def sweep(deps: Deps, now: datetime | None = None) -> list[str]:
    """Fail jobs not updated for longer than their current step's timeout + margin (ADR-15)."""
    now = now or utcnow()
    failed: list[str] = []
    for job_id in deps.store.list_job_ids():
        try:
            job = deps.store.get(job_id)
        except KeyError:
            continue
        if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            continue
        step = _STAGE_STEP[job.stage]
        last = job.updated_at
        if step is Step.CLIP:
            last = max([last, *(c.updated_at for c in deps.store.clips(job_id, job.clip_ids))])
        idle_s = (now - last).total_seconds()
        if idle_s <= STEP_TIMEOUT_S[step] + STALL_MARGIN_S:
            continue
        stage = job.stage or StageName.INGEST
        message = f"stalled at {stage} (no progress for {idle_s / 60:.0f} min)"
        if fail_job(deps, job_id, stage, "stalled", message):
            failed.append(job_id)
    return failed
```

- [ ] **Step 4: Run the recovery tests, then everything**

Run: `uv run pytest tests/pipeline -q && uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/pipeline/steps.py`, `tests/pipeline/test_recovery.py`. Message: `feat(pipeline): resume and stall sweeper`.

---

### Task 7: Job service

**Files:**
- Create: `src/clipforge/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `Deps`, `Step`, `resume`, `JobNotResumable` (Tasks 5–6) and `DictJobStore` (Task 4).
- Produces (Plan 3's API and bot call only these):
  - `create_job(deps, job_input) -> Job`
  - `get_job_view(store, root, job_id) -> JobView`, which raises `KeyError` for unknown jobs
  - `resume_job(deps, job_id) -> JobView`, which lets `JobNotResumable` propagate

- [ ] **Step 1: Write the failing `tests/test_service.py`**

```python
from collections import Counter
from pathlib import Path

import pytest

from clipforge.jobs import DictJobStore
from clipforge.models import JobInput, JobStatus, Permission, StageName
from clipforge.pipeline.deps import MemoryKV, SpawnCall
from clipforge.pipeline.steps import JobNotResumable
from clipforge.service import create_job, get_job_view, resume_job
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness
from tests.test_models import ALL_SAMPLES, JobMetadata


def test_create_job_saves_and_spawns_ingest(harness: Harness) -> None:
    job_input = JobInput(telegram_file_id="BQACAgIAAxk", permission=Permission.OWN)
    job = create_job(harness.deps, job_input)
    assert harness.store.get(job.job_id) == job
    assert job.status is JobStatus.QUEUED
    assert list(harness.spawner.queue) == [SpawnCall("ingest", job.job_id, None)]


def test_job_view_merges_clip_costs(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run()
    view = get_job_view(harness.store, harness.root, job_id)
    assert view.status is JobStatus.DONE and len(view.clips) == 5
    renders = [c for c in view.cost.stages if c.stage is StageName.RENDER and not c.cached]
    assert len(renders) == 5 and all(c.clip_id for c in renders)
    # fake costs: transcribe 0.002 + highlights 0.0015 + 5 clips x 0.001
    assert view.cost.total_usd == pytest.approx(0.0085)
    assert view.output_zip is not None


def test_job_view_falls_back_to_metadata(tmp_path: Path) -> None:
    meta = next(m for m in ALL_SAMPLES if isinstance(m, JobMetadata))
    path = tmp_path / meta.job_id / "output" / "metadata.json"
    path.parent.mkdir(parents=True)
    path.write_text(meta.model_dump_json())
    store = DictJobStore(MemoryKV())  # Dict entries are gone
    view = get_job_view(store, tmp_path, meta.job_id)
    assert view.status is JobStatus.DONE and view.cost == meta.cost
    assert view.output_zip == f"{meta.job_id}/job.zip"
    with pytest.raises(KeyError):
        get_job_view(store, tmp_path, "20260923-00000000-0000")


def test_resume_job_returns_the_view(tmp_path: Path) -> None:
    stages = FakeStages(transient=Counter({"highlights": 99}))
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    stages.transient.clear()
    view = resume_job(h.deps, job_id)
    assert view.status is JobStatus.RUNNING and view.error is None
    h.run()
    assert get_job_view(h.store, h.root, job_id).status is JobStatus.DONE
    with pytest.raises(JobNotResumable):
        resume_job(h.deps, h.submit())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_service.py -q`
Expected: `ModuleNotFoundError: No module named 'clipforge.service'`.

- [ ] **Step 3: Create `src/clipforge/service.py`**

```python
"""Job service: the one entry point shared by the API, the bot and the CLI (ADR-2)."""

from __future__ import annotations

from pathlib import Path

from clipforge.jobs import DictJobStore, new_job_id, utcnow
from clipforge.models import CostSummary, Job, JobInput, JobMetadata, JobStatus, JobView, StageName
from clipforge.pipeline.steps import Deps, Step, resume


def create_job(deps: Deps, job_input: JobInput) -> Job:
    """Save a queued job and spawn its first step."""
    seed = str(job_input.source_url or job_input.telegram_file_id or job_input.source_path)
    now = utcnow()
    job = Job(job_id=new_job_id(seed, now), input=job_input, created_at=now, updated_at=now)
    deps.store.save(job)
    deps.spawner.spawn(Step.INGEST, job.job_id)
    return job


def get_job_view(store: DictJobStore, root: Path, job_id: str) -> JobView:
    """The core record merged with its clips (ADR-14); falls back to metadata.json."""
    try:
        job = store.get(job_id)
    except KeyError:
        return _view_from_metadata(root, job_id)
    clips = store.clips(job_id, job.clip_ids)
    cost = CostSummary(stages=[*job.cost.stages, *(entry for c in clips for entry in c.cost)])
    return JobView(
        job_id=job.job_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error=job.error,
        clips=clips,
        cost=cost,
        output_zip=job.output_zip,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _view_from_metadata(root: Path, job_id: str) -> JobView:
    path = root / job_id / "output" / "metadata.json"
    if not path.exists():
        raise KeyError(f"unknown job {job_id!r}")
    meta = JobMetadata.model_validate_json(path.read_text())
    return JobView(
        job_id=job_id,
        status=JobStatus.DONE,
        stage=StageName.PACKAGE,
        clips=[],
        cost=meta.cost,
        output_zip=f"{job_id}/job.zip",
        created_at=meta.started_at,
        updated_at=meta.finished_at,
    )


def resume_job(deps: Deps, job_id: str) -> JobView:
    """Resume a failed job; raises steps.JobNotResumable while it is queued or running."""
    resume(deps, job_id)
    return get_job_view(deps.store, deps.root, job_id)
```

- [ ] **Step 4: Run the checks**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/service.py`, `tests/test_service.py`. Message: `feat: job service (create, view, resume)`.

---

### Task 8: Docs and roadmap

**Files:**
- Modify: `ROADMAP.md`, `CLAUDE.md`, `docs/DECISIONS.md`, `docs/superpowers/specs/2026-09-23-serverless-pipeline-design.md`

- [ ] **Step 1: Tick the CI box in `ROADMAP.md`**

Change `- [ ] CI: lint + fast tests on push` to `- [x] CI: lint + fast tests on push, deploy on main (ADR-16)`. Leave "Step chain on Modal" unticked: Plan 3 ticks it once the chain runs on Modal.

- [ ] **Step 2: Update the `CLAUDE.md` layout block.** Add these lines under `src/clipforge/`:

```
  pipeline/         # step chain (Modal-free): deps.py interfaces, steps.py, selection.py, errors.py
  service.py        # job service: create_job, get_job_view, resume_job (API, bot and CLI use it)
```

and change the `jobs.py` line to `jobs.py           # DictJobStore, JobContext, cached_stage (ADR-14)`.

- [ ] **Step 3: Add a dated note under ADR-14 in `docs/DECISIONS.md`** (a clarification rather than a new decision)

Append this line to the end of ADR-14's Consequences paragraph: ` Note (2026-09-23): tests use DictJobStore over MemoryKV; FileJobStore was removed.`

- [ ] **Step 4: Align the spec with what was built.** In the spec:
  - In section 2's unit table, change the Job store row's purpose to: "`JobContext`, `DictJobStore` (on `KV`; tests use `MemoryKV`), `cached_stage` returning `Stored`".
  - In section 5's CLI paragraph, change `CLIPFORGE_API_URL` to `API_URL`.
  - In section 3, add under "Clip specs": "`clip_step` re-binds a cached `RenderedClip` to this job's spec and writes it to `/jobs/<job_id>/clips/<clip_id>.rendered.json`; `ClipState.result_ref` points there."

- [ ] **Step 5: Final full check**

Run: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `ROADMAP.md`, `CLAUDE.md`, `docs/DECISIONS.md`, the spec. Message: `docs: plan 1 landed (chain core, CI)`.

---

## Self-review notes

- **Spec coverage (Plan 1 scope):**
  - Components and step functions: Task 5.
  - Single-writer Dict layout: Task 4.
  - Fan-in claim: Task 5.
  - Transient vs permanent errors, attempts, partial success and failure-once: Task 5.
  - Resume and sweeper: Task 6.
  - Service: Task 7.
  - Contract and config changes: Tasks 2–3.
  - CI/CD: Task 1.
  - Deferred to Plan 2: per-window LLM validation (it lives in the real highlights stage), the source limits in ingest, and the clip bitrate cap.
  - Deferred to Plan 3: API, bot, CLI, Modal bindings, cron and smoke test.
- **Type consistency:**
  - `Stored.ref` and `load_ref` are used identically in the store, steps, fakes and tests.
  - `SpawnCall(step: str, ...)` compares equal to `Step` values because `Step` is a `StrEnum`.
  - `ClipState.finished` is used in `_maybe_package`.
  - `JobNotResumable` is defined in steps and imported by the service tests.

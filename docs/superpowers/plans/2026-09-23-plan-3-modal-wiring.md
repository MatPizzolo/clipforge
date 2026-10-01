> **Historical (Phase 1, ADR-9–16, deployed 2026-09-23):** built and deployed; docs/ARCHITECTURE.md and the code are current.

# Plan 3: Modal wiring, job API, Telegram bot, CLI and smoke test

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the finished step chain (Plan 1) and real stages (Plan 2) on Modal behind a FastAPI job API, a Telegram webhook bot and a CLI, and prove it with a real smoke job, so a direct link sent to the bot comes back as captioned clips plus a signed zip link.

**Architecture:** Everything new except `app.py` is Modal-free and tested in-process. `runtime.py` adapts duck-typed Modal objects (Dict, Volume, Functions) to the `KV`, `Volume` and `Spawner` interfaces and builds `Deps`. `api/main.py` (FastAPI, sync routes) and `bot/` (python-telegram-bot, webhook mode, bridged to sync with `asyncio.run`) call `service.py`. `app.py` only declares images, functions, the cron, the ASGI endpoint and the `smoke` entrypoint, and each step function is one `dispatch(...)` call.

**Tech Stack:** Python 3.12, uv, Modal 1.5.5, FastAPI 0.141, python-telegram-bot 22.8, httpx 0.28, pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-23-serverless-pipeline-design.md` (sections 2, 3, 5 and 6 are the ones this plan implements). Architecture rules: `CLAUDE.md`, ADR-9 to ADR-16 in `docs/DECISIONS.md`.

## Global Constraints

- Only `src/clipforge/app.py` imports `modal`. `runtime.py`, `api/`, `bot/`, `cli.py`, `smoke.py`, `pipeline/` and `stages/` never do (ADR-9; Task 8 adds a test for this).
- No secrets in code or logs (CLAUDE.md rule 8). Secrets stay `SecretStr` until the line that uses them. Never print or log a token, a signing key or a signed URL's `sig`.
- New runtime dependencies: `fastapi` and `python-telegram-bot` only (spec §8). No other new packages.
- Fast tests (`uv run pytest -q -m "not gpu and not slow"`) need no network and no Modal. Telegram is faked with a `telegram.request.BaseRequest` subclass or a `FakeSender`; the API is exercised with FastAPI's `TestClient`.
- mypy strict on `src`, ruff (line length 100), `ruff format`. Run all three before every checkpoint.
- **The user does all git.** Every "Checkpoint" step lists files for them to commit; never run git.
- Modal resources come from spec §2: `web` CPU 0.5, 10 min; `ingest_step` CPU 2, 4 GB; `transcribe_step` L4; `highlights_step` CPU 1; `clip_step` CPU 4, 4 GB; `package_step` CPU 1; `sweeper` `Cron("*/10 * * * *")`, CPU 0.25, 2 min. Step timeouts come from `pipeline.steps.STEP_TIMEOUT_S` (ingest 900 s, transcribe 1800 s, others 600 s), retries `max_retries = MAX_ATTEMPTS - 1 = 2`.
- All functions mount the Volume `clipforge-jobs` at `/jobs` and use the secret `clipforge-secrets`.
- Bot messages (spec §5): `Got it, job <id>`; clip caption `#1 · score 0.91 · <title>`; done `<k> of <n> clips · $<cost> · <zip link>`; failed `<stage>: <reason>` then `/resume <id>`.
- Download signature: `sig = HMAC-SHA256(DOWNLOAD_SIGNING_KEY, f"{id}:{exp}")`, hex, `exp` a Unix time in the future.
- Telegram upload limit: 20 MB (`20 * 1024 * 1024` bytes).

### Deviations from the spec (decided while planning; the executor records them as rulings)

1. **`set_webhook` is a CLI subcommand** (`uv run clipforge set-webhook`), not `modal run app.py::set_webhook`. It only talks to Telegram with values from the local `.env`, so spinning up an ephemeral Modal app for it buys nothing.
2. **`JobView.download_url: str | None`** is new. The API fills it in (signed) when a job is done, so the CLI and `/status` can print the link without holding the signing key.
3. **The download route serves `JobView.output_zip`** (which is `<id>/job.zip` in production, and a fallback from `metadata.json`), with a check that the path stays inside `/jobs`, instead of hard-coding the path.
4. **The webhook route answers 200 even when handling the update fails**, after logging. The update is already claimed, so Telegram's redelivery would be dropped anyway, and a 5xx only makes Telegram back off the whole webhook.
5. **Images install the project from `uv.lock`** with `Image.uv_sync(...)`, so Modal runs exactly the versions tested locally. The GPU image adds the pinned faster-whisper and CTranslate2 on top.
6. **`build_job_input` is shared** by the bot and the CLI (`bot/commands.py`), so `/clip` options and `clipforge run` flags validate identically.

## Review Focus

1. **A setting missing from `clipforge-secrets`** (API_TOKEN, DOWNLOAD_SIGNING_KEY, API_URL, TELEGRAM_WEBHOOK_SECRET): the API answers 503 naming the setting and never runs unauthenticated. The "done" message still reaches Telegram, without a link. Tests: Task 1 `test_download_url_needs_config`, Task 2 `test_done_without_link_config`, Task 5 `test_api_token_unset_is_503` and `test_webhook_secret_unset_is_503`.
2. **Job ids that aren't ours** (`..`, `%2e%2e`, a valid signature reused for another job): never a file outside `/jobs`; 403 or 404. Tests: Task 5 `test_download_rejects_other_job_and_traversal`, Task 4 `test_status_rejects_non_job_ids`.
3. **Updates the bot doesn't handle** (edited messages, stickers, channel posts, a user not on the list): the webhook returns 200, strangers get no reply and leave no Dict key, and allowed users get the usage text. Tests: Task 4 `test_stranger_is_ignored_without_trace`, `test_edited_message_is_ignored` and `test_sticker_gets_usage`.
4. **`Volume.reload()` failing in the web container** (for example, open files during a download): status is still answered from the Dict. Test: Task 5 `test_volume_reload_failure_still_serves_status`.
5. **Telegram failing while a clip is sent** (network, 413, 429): the clip step still finishes and the job still packages. Test: Task 6 `test_failing_telegram_never_fails_the_job`.

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `src/clipforge/links.py` | new | sign, verify, `download_url`, `with_download_url` (Task 1) |
| `src/clipforge/models.py` | modify | `JobView.download_url` (Task 1) |
| `src/clipforge/bot/__init__.py` | new | empty package marker |
| `src/clipforge/bot/telegram.py` | new | `TelegramSender` protocol, `TelegramClient` sync wrapper over PTB (Task 2) |
| `src/clipforge/bot/messages.py` | new | every user-facing bot text (Task 2) |
| `src/clipforge/bot/notifier.py` | new | `TelegramNotifier` (the `Notifier` for Telegram jobs) (Task 2) |
| `src/clipforge/bot/commands.py` | new | parse messages into commands; `build_job_input` (Task 3) |
| `src/clipforge/bot/webhook.py` | new | `BotContext`, `handle_update` (Task 4) |
| `src/clipforge/jobs.py` | modify | `is_job_id`, `DictJobStore.claim_update` (Task 4) |
| `src/clipforge/api/__init__.py` | new | empty package marker |
| `src/clipforge/api/main.py` | new | `ApiContext`, `create_app` (Task 5) |
| `src/clipforge/runtime.py` | new | `DictKV`, `ModalVolume`, `FunctionSpawner`, `UnavailableStages`, `telegram_sender`, `notifier_factory`, `build_deps` (Task 6) |
| `src/clipforge/cli.py` | new | `clipforge run / status / resume / set-webhook`; `ApiClient`, `wait` (Task 7) |
| `src/clipforge/smoke.py` | new | `smoke_input`, `check_smoke` (Task 8) |
| `src/clipforge/app.py` | rewrite | images, step functions, sweeper, web, `doctor`, `smoke` (Task 8) |
| `pyproject.toml`, `uv.lock` | modify | add fastapi, python-telegram-bot (Tasks 2 and 5) |
| `.github/workflows/ci.yml`, `manual.yml` | modify | GIT_SHA on deploy; smoke on manual (Task 9) |
| `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `ROADMAP.md`, `.env.example` | modify | setup, commands, ticks (Task 9) |
| `tests/test_links.py`, `tests/bot/*`, `tests/api/*`, `tests/test_runtime.py`, `tests/test_cli.py`, `tests/test_smoke_check.py`, `tests/test_app.py` | new or modify | tests per task |

---

### Task 1: Signed download links and `JobView.download_url`

**Files:**
- Create: `src/clipforge/links.py`
- Modify: `src/clipforge/models.py` (class `JobView`)
- Test: `tests/test_links.py`

**Interfaces:**
- Consumes: `Settings.api_url`, `Settings.download_signing_key`, `Settings.download_link_ttl_s`; `JobView`, `JobStatus`.
- Produces:
  - `class LinksNotConfigured(RuntimeError)`
  - `sign(key: str, job_id: str, exp: int) -> str`
  - `verify(key: str, job_id: str, exp: int, sig: str, now: float | None = None) -> bool`
  - `download_url(settings: Settings, job_id: str, now: float | None = None) -> str`, which raises `LinksNotConfigured`
  - `with_download_url(view: JobView, settings: Settings, now: float | None = None) -> JobView`
  - `JobView.download_url: str | None = None`

- [ ] **Step 1: Write the failing tests**

`tests/test_links.py`:

```python
"""Signed, expiring zip links (ADR-13)."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from clipforge.config import Settings
from clipforge.links import LinksNotConfigured, download_url, sign, verify, with_download_url
from clipforge.models import CostSummary, JobStatus, JobView, StageName

JOB = "20260923-aaaaaaaa-0001"
NOW = 1_800_000_000.0


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "api_url": "https://api.example/",
        "download_signing_key": "k3y",
        "download_link_ttl_s": 3600,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _view(status: JobStatus, output_zip: str | None) -> JobView:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    return JobView(
        job_id=JOB,
        status=status,
        stage=StageName.PACKAGE,
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
        output_zip=output_zip,
    )


def test_sign_verify_round_trip() -> None:
    sig = sign("k3y", JOB, 1_800_000_100)
    assert len(sig) == 64 and "k3y" not in sig
    assert verify("k3y", JOB, 1_800_000_100, sig, now=NOW)


def test_verify_rejects_expired_tampered_and_other_job() -> None:
    exp = 1_800_000_100
    sig = sign("k3y", JOB, exp)
    assert not verify("k3y", JOB, exp, sig, now=exp)  # expiry is exclusive
    assert not verify("k3y", JOB, exp + 1, sig, now=NOW)  # exp changed
    assert not verify("k3y", JOB, exp, sig[:-1] + "0", now=NOW)
    assert not verify("k3y", "20260923-bbbbbbbb-0001", exp, sig, now=NOW)
    assert not verify("other", JOB, exp, sig, now=NOW)


def test_download_url_is_signed_and_expires_after_ttl() -> None:
    url = download_url(_settings(), JOB, now=NOW)
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == f"https://api.example/jobs/{JOB}/download"
    query = parse_qs(parts.query)
    exp = int(query["exp"][0])
    assert exp == int(NOW) + 3600
    assert verify("k3y", JOB, exp, query["sig"][0], now=NOW)


@pytest.mark.parametrize("missing", ["api_url", "download_signing_key"])
def test_download_url_needs_config(missing: str) -> None:
    with pytest.raises(LinksNotConfigured):
        download_url(_settings(**{missing: None}), JOB, now=NOW)


def test_with_download_url_only_for_done_jobs_with_a_zip() -> None:
    settings = _settings()
    done = with_download_url(_view(JobStatus.DONE, f"{JOB}/job.zip"), settings, now=NOW)
    assert done.download_url is not None and done.download_url.startswith("https://api.example/")
    running = with_download_url(_view(JobStatus.RUNNING, None), settings, now=NOW)
    assert running.download_url is None
    unconfigured = _settings(download_signing_key=None)
    assert with_download_url(_view(JobStatus.DONE, "x"), unconfigured).download_url is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_links.py`
Expected: FAIL, collection error `ModuleNotFoundError: No module named 'clipforge.links'`.

- [ ] **Step 3: Add the contract field**

In `src/clipforge/models.py`, class `JobView`, add as the last field:

```python
    download_url: str | None = None  # signed zip link, filled in by the API when done
```

- [ ] **Step 4: Write `src/clipforge/links.py`**

```python
"""Signed, expiring download links for job zips (ADR-13).

`sig = HMAC-SHA256(DOWNLOAD_SIGNING_KEY, f"{job_id}:{exp}")`. The link carries only the job id,
the expiry and the signature; the key never leaves the server.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from clipforge.config import Settings
from clipforge.models import JobStatus, JobView


class LinksNotConfigured(RuntimeError):
    """API_URL or DOWNLOAD_SIGNING_KEY is missing, so no link can be made."""


def sign(key: str, job_id: str, exp: int) -> str:
    return hmac.new(key.encode(), f"{job_id}:{exp}".encode(), hashlib.sha256).hexdigest()


def verify(key: str, job_id: str, exp: int, sig: str, now: float | None = None) -> bool:
    if exp <= (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sign(key, job_id, exp), sig)


def download_url(settings: Settings, job_id: str, now: float | None = None) -> str:
    if settings.api_url is None or settings.download_signing_key is None:
        raise LinksNotConfigured("set API_URL and DOWNLOAD_SIGNING_KEY to make download links")
    exp = int(time.time() if now is None else now) + settings.download_link_ttl_s
    sig = sign(settings.download_signing_key.get_secret_value(), job_id, exp)
    return f"{settings.api_url.rstrip('/')}/jobs/{job_id}/download?exp={exp}&sig={sig}"


def with_download_url(view: JobView, settings: Settings, now: float | None = None) -> JobView:
    """The view with a fresh signed link when the job is done and links are configured."""
    if view.status is not JobStatus.DONE or view.output_zip is None:
        return view
    try:
        url = download_url(settings, view.job_id, now)
    except LinksNotConfigured:
        return view
    return view.model_copy(update={"download_url": url})
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_links.py tests/test_models.py`
Expected: PASS (all). If `tests/test_models.py` round-trips a `JobView` sample, it still passes, because the field is optional.

- [ ] **Step 6: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass. If the `# type: ignore[arg-type]` in the test turns out to be unused, mypy doesn't check `tests/`, so leave it (it's harmless).

- [ ] **Step 7: Checkpoint (the user commits)**

Files: `src/clipforge/links.py`, `src/clipforge/models.py`, `tests/test_links.py`.

---

### Task 2: Telegram client, bot messages and the Telegram notifier

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Create: `src/clipforge/bot/__init__.py`, `src/clipforge/bot/telegram.py`, `src/clipforge/bot/messages.py`, `src/clipforge/bot/notifier.py`
- Create: `tests/bot/__init__.py`, `tests/bot/fakes.py`, `tests/bot/test_telegram.py`, `tests/bot/test_notifier.py`

**Interfaces:**
- Consumes:
  - `links.download_url`, `links.LinksNotConfigured` (Task 1);
  - `jobs.DictJobStore.clips(job_id, clip_ids)`, `jobs.merged_cost(store, job) -> CostSummary`;
  - `models.Job`, `ClipState`, `ClipStatus`, `RenderedClip` (`.video_path` is relative to JOBS_ROOT; `.spec.rank`; `.spec.candidate.score/.title`), `TelegramTarget`, `JobView`.
- Produces:
  - `bot.telegram`:
    - `class TelegramSender(Protocol)` with `send_message(chat_id: int, text: str, reply_to: int | None = None) -> None` and `send_video(chat_id: int, path: Path, caption: str, reply_to: int | None = None) -> None`;
    - `class TelegramClient(token: str, request_factory: Callable[[], BaseRequest] = default_request)`, which implements `TelegramSender` plus `set_webhook(url: str, secret: str) -> None`.
  - `bot.messages`: `USAGE`, `TOO_BIG`, `job_accepted(job_id) -> str`, `clip_caption(rendered) -> str`, `done_text(done, total, cost_usd, link) -> str`, `failed_text(job) -> str`, `status_text(view) -> str`.
  - `bot.notifier`: `TelegramNotifier(sender, target, store, settings, root)`, which implements `pipeline.deps.Notifier`.
  - `tests/bot/fakes.py`: `FakeSender`, `FakeRequest`, `make_settings(root, **overrides)`, `update(...)`, `video(...)`.

- [ ] **Step 1: Add the dependency**

Run: `uv add "python-telegram-bot>=22.8"`
Expected: `pyproject.toml` lists `python-telegram-bot>=22.8`; `uv.lock` updated; `uv run python -c "import telegram; print(telegram.__version__)"` prints `22.8` or later.

- [ ] **Step 2: Write the test fakes**

`tests/bot/__init__.py`: empty file.

`tests/bot/fakes.py`:

```python
"""Telegram fakes: a recording TelegramSender, a PTB BaseRequest that never hits the network,
and builders for update JSON and test settings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telegram.request import BaseRequest, RequestData

from clipforge.config import Settings

ALLOWED_USER = 42
CHAT = 7


@dataclass
class FakeSender:
    messages: list[tuple[int, str, int | None]] = field(default_factory=list)
    videos: list[tuple[int, Path, str, int | None]] = field(default_factory=list)
    fail: bool = False

    def send_message(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        if self.fail:
            raise RuntimeError("telegram is down")
        self.messages.append((chat_id, text, reply_to))

    def send_video(self, chat_id: int, path: Path, caption: str, reply_to: int | None = None) -> None:
        if self.fail:
            raise RuntimeError("telegram is down")
        self.videos.append((chat_id, path, caption, reply_to))


class FakeRequest(BaseRequest):
    """Records Bot API calls as (method, parameters, has_files) and answers `ok`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], bool]] = []
        self.shutdowns = 0

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        self.shutdowns += 1

    @property
    def read_timeout(self) -> float | None:
        return None

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: RequestData | None = None,
        read_timeout: Any = None,
        write_timeout: Any = None,
        connect_timeout: Any = None,
        pool_timeout: Any = None,
    ) -> tuple[int, bytes]:
        name = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        has_files = bool(request_data and request_data.multipart_data)
        self.calls.append((name, params, has_files))
        result: object = True
        if name.startswith("send"):
            result = {"message_id": 99, "date": 0, "chat": {"id": CHAT, "type": "private"}}
        return 200, json.dumps({"ok": True, "result": result}).encode()


def make_settings(root: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "api_token": "t0ken",
        "api_url": "https://api.example",
        "download_signing_key": "k3y",
        "telegram_bot_token": "123:abc",
        "telegram_webhook_secret": "hook-secret",
        "telegram_allowed_user_ids": [ALLOWED_USER],
        "jobs_root": root,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def update(
    update_id: int = 1,
    *,
    text: str | None = None,
    user_id: int = ALLOWED_USER,
    message_id: int = 3,
    kind: str = "message",
    **fields: Any,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": message_id,
        "date": 0,
        "chat": {"id": CHAT, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "M"},
        **fields,
    }
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, kind: message}


def video(file_size: int | None, file_id: str = "VID") -> dict[str, Any]:
    return {
        "file_id": file_id,
        "file_unique_id": f"U{file_id}",
        "width": 1920,
        "height": 1080,
        "duration": 30,
        "file_size": file_size,
    }
```

- [ ] **Step 3: Write the failing tests**

`tests/bot/test_telegram.py`:

```python
"""TelegramClient: the sync bridge over python-telegram-bot, without network."""

from __future__ import annotations

from pathlib import Path

from clipforge.bot.telegram import TelegramClient
from tests.bot.fakes import FakeRequest


def _client() -> tuple[TelegramClient, FakeRequest]:
    request = FakeRequest()
    return TelegramClient("123:abc", request_factory=lambda: request), request


def test_send_message_replies_and_disables_previews() -> None:
    client, request = _client()
    client.send_message(7, "hello", reply_to=3)
    name, params, _ = request.calls[-1]
    assert name == "sendMessage"
    assert params["chat_id"] == 7 and params["text"] == "hello"
    assert params["reply_parameters"] == {"message_id": 3, "allow_sending_without_reply": True}
    assert params["link_preview_options"] == {"is_disabled": True}
    assert request.shutdowns == 1  # every call closes its HTTP client


def test_send_message_without_reply() -> None:
    client, request = _client()
    client.send_message(7, "hi")
    assert "reply_parameters" not in request.calls[-1][1]


def test_send_video_uploads_the_file(tmp_path: Path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00" * 16)
    client, request = _client()
    client.send_video(7, path, "x" * 2000, reply_to=3)
    name, params, has_files = request.calls[-1]
    assert name == "sendVideo" and has_files
    assert params["supports_streaming"] is True
    assert len(params["caption"]) == 1024  # Telegram's caption limit


def test_set_webhook_sends_secret_and_message_updates_only() -> None:
    client, request = _client()
    client.set_webhook("https://api.example/telegram/webhook", "hook-secret")
    name, params, _ = request.calls[-1]
    assert name == "setWebhook"
    assert params == {
        "url": "https://api.example/telegram/webhook",
        "secret_token": "hook-secret",
        "allowed_updates": ["message"],
    }


def test_repr_hides_the_token() -> None:
    client, _ = _client()
    assert "123:abc" not in repr(client)
```

`tests/bot/test_notifier.py`:

```python
"""TelegramNotifier and the message texts, driven through the real step chain."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from clipforge.bot import messages
from clipforge.bot.notifier import TelegramNotifier
from clipforge.links import verify
from clipforge.models import (
    CostSummary,
    Job,
    JobError,
    JobStatus,
    JobView,
    Progress,
    StageName,
    TelegramTarget,
)
from tests.bot.fakes import CHAT, FakeSender, make_settings
from tests.pipeline.harness import Harness

TARGET = TelegramTarget(chat_id=CHAT, reply_to_message_id=3)


def _wire(harness: Harness, **settings: object) -> FakeSender:
    sender = FakeSender()
    config = make_settings(harness.root, **settings)
    harness.deps.notifier_for = lambda job: TelegramNotifier(
        sender, TARGET, harness.store, config, harness.root
    )
    return sender


def test_chain_sends_each_clip_then_the_zip_link(harness: Harness) -> None:
    sender = _wire(harness)
    job_id = harness.submit()
    harness.run()

    assert len(sender.videos) == 5
    chat, path, caption, reply_to = sender.videos[0]
    assert (chat, reply_to) == (CHAT, 3)
    assert path.is_relative_to(harness.root) and path.name == "clip.mp4"
    assert caption.startswith("#") and " · score " in caption

    chat, text, reply_to = sender.messages[-1]
    assert text.startswith("5 of 5 clips · $")
    url = text.rsplit(" · ", 1)[-1]
    query = parse_qs(urlsplit(url).query)
    assert f"/jobs/{job_id}/download" in url
    assert verify("k3y", job_id, int(query["exp"][0]), query["sig"][0])


def test_done_without_link_config(harness: Harness) -> None:
    sender = _wire(harness, api_url=None)
    harness.submit()
    harness.run()
    assert sender.messages[-1][1].startswith("5 of 5 clips")
    assert "not set" in sender.messages[-1][1]


def test_failed_message_names_stage_and_resume(harness: Harness) -> None:
    sender = _wire(harness)
    harness.stages.permanent["transcribe"] = "no speech found"
    job_id = harness.submit()
    harness.run()
    assert sender.messages == [(CHAT, f"transcribe: no speech found\n/resume {job_id}", 3)]


def test_status_text() -> None:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    view = JobView(
        job_id="J",
        status=JobStatus.RUNNING,
        stage=StageName.TRANSCRIBE,
        progress=Progress(stage=StageName.TRANSCRIBE, pct=40, message="transcribing", at=at),
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
    )
    assert messages.status_text(view) == (
        "job J: running\nstage: transcribe 40% transcribing\ncost: $0.000"
    )


def test_failed_text_without_error_record() -> None:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    job = Job.model_validate(
        {
            "job_id": "J",
            "input": {"source_url": "https://a.example/v.mp4", "permission": "own"},
            "created_at": at,
            "updated_at": at,
            "status": "failed",
            "error": JobError(stage=StageName.INGEST, error_type="x", message="bad").model_dump(),
        }
    )
    assert messages.failed_text(job) == "ingest: bad\n/resume J"

```

`FakeStages.permanent: dict[str, str]` (in `tests/pipeline/fakes.py`) makes the named stage raise `PermanentError(message)`. Tasks 4, 5 and 7 use the same hook.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest -q tests/bot`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.bot'`.

- [ ] **Step 5: Write `src/clipforge/bot/__init__.py` (empty) and `src/clipforge/bot/telegram.py`**

```python
"""A small synchronous wrapper over python-telegram-bot's async `Bot` (webhook mode, no
polling `Application`, spec §5).

Each call builds a fresh `Bot` and HTTP client inside `asyncio.run`, so it works from the sync
Modal step functions and from FastAPI's worker threads, and never shares a client across event
loops. The token is never logged or shown in `repr` (CLAUDE.md rule 8).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from telegram import Bot, LinkPreviewOptions, ReplyParameters
from telegram.request import BaseRequest, HTTPXRequest

CAPTION_LIMIT = 1024
UPLOAD_TIMEOUT_S = 300.0  # a 45 MB clip on a slow uplink


class TelegramSender(Protocol):
    def send_message(self, chat_id: int, text: str, reply_to: int | None = None) -> None: ...

    def send_video(
        self, chat_id: int, path: Path, caption: str, reply_to: int | None = None
    ) -> None: ...


def default_request() -> BaseRequest:
    return HTTPXRequest(
        connection_pool_size=1,
        read_timeout=60.0,
        write_timeout=60.0,
        connect_timeout=10.0,
        media_write_timeout=UPLOAD_TIMEOUT_S,
    )


def _reply(message_id: int | None) -> ReplyParameters | None:
    if message_id is None:
        return None
    return ReplyParameters(message_id=message_id, allow_sending_without_reply=True)


class TelegramClient:
    def __init__(
        self, token: str, request_factory: Callable[[], BaseRequest] = default_request
    ) -> None:
        self._token = token
        self._request_factory = request_factory

    def __repr__(self) -> str:
        return "TelegramClient(token=***)"

    def _run(self, call: Callable[[Bot], Awaitable[object]]) -> None:
        async def main() -> None:
            request = self._request_factory()
            bot = Bot(self._token, request=request, get_updates_request=request)
            try:
                await call(bot)
            finally:
                await request.shutdown()

        asyncio.run(main())

    def send_message(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        self._run(
            lambda bot: bot.send_message(
                chat_id,
                text,
                reply_parameters=_reply(reply_to),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        )

    def send_video(
        self, chat_id: int, path: Path, caption: str, reply_to: int | None = None
    ) -> None:
        async def call(bot: Bot) -> object:
            with path.open("rb") as video:
                return await bot.send_video(
                    chat_id,
                    video,
                    caption=caption[:CAPTION_LIMIT],
                    supports_streaming=True,
                    reply_parameters=_reply(reply_to),
                )

        self._run(call)

    def set_webhook(self, url: str, secret: str) -> None:
        self._run(
            lambda bot: bot.set_webhook(url, secret_token=secret, allowed_updates=["message"])
        )
```

- [ ] **Step 6: Write `src/clipforge/bot/messages.py`**

```python
"""Every text the bot sends (spec §5), in one place."""

from __future__ import annotations

from clipforge.models import ClipStatus, Job, JobView, RenderedClip

USAGE = (
    "Send a direct video link, or a video file up to 20 MB.\n"
    "/clip <link> [n=5] [len=30-60] [lang=en] [perm=own] [credit=\"...\"]\n"
    "/status <job_id> · /resume <job_id>"
)
TOO_BIG = (
    "That file is over 20 MB, the most a Telegram bot can download. "
    "Upload it somewhere that serves the file directly and send the link."
)
NO_LINK = "zip link unavailable (API_URL / DOWNLOAD_SIGNING_KEY not set)"


def job_accepted(job_id: str) -> str:
    return f"Got it, job {job_id}"


def clip_caption(rendered: RenderedClip) -> str:
    candidate = rendered.spec.candidate
    return f"#{rendered.spec.rank} · score {candidate.score:.2f} · {candidate.title}"


def done_text(done: int, total: int, cost_usd: float, link: str | None) -> str:
    return f"{done} of {total} clips · ${cost_usd:.3f} · {link or NO_LINK}"


def failed_text(job: Job) -> str:
    if job.error is not None:
        head = f"{job.error.stage}: {job.error.message}"
    else:
        head = f"{job.stage or 'job'}: failed"
    return f"{head}\n/resume {job.job_id}"


def status_text(view: JobView) -> str:
    lines = [f"job {view.job_id}: {view.status}"]
    if view.stage is not None:
        stage = f"stage: {view.stage}"
        if view.progress is not None:
            stage = f"{stage} {view.progress.pct:.0f}% {view.progress.message}".rstrip()
        lines.append(stage)
    if view.clips:
        done = sum(c.status is ClipStatus.DONE for c in view.clips)
        lines.append(f"clips: {done}/{len(view.clips)} done")
    lines.append(f"cost: ${view.cost.total_usd:.3f}")
    if view.error is not None:
        lines.append(f"error: {view.error.stage}: {view.error.message}")
    if view.download_url is not None:
        lines.append(view.download_url)
    return "\n".join(lines)
```

- [ ] **Step 7: Write `src/clipforge/bot/notifier.py`**

```python
"""The Notifier for jobs that came from Telegram (ADR-13). `Deps.notifier()` wraps it in
`SafeNotifier`, so a Telegram failure is logged and never fails a step."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clipforge.bot.messages import clip_caption, done_text, failed_text
from clipforge.bot.telegram import TelegramSender
from clipforge.config import Settings
from clipforge.jobs import DictJobStore, merged_cost
from clipforge.links import LinksNotConfigured, download_url
from clipforge.models import ClipState, ClipStatus, Job, RenderedClip, TelegramTarget


@dataclass
class TelegramNotifier:
    sender: TelegramSender
    target: TelegramTarget
    store: DictJobStore
    settings: Settings
    root: Path  # JOBS_ROOT: contract paths are relative to it

    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        self.sender.send_video(
            self.target.chat_id,
            self.root / rendered.video_path,
            clip_caption(rendered),
            self.target.reply_to_message_id,
        )

    def done(self, job: Job) -> None:
        clips = self.store.clips(job.job_id, job.clip_ids)
        done = sum(c.status is ClipStatus.DONE for c in clips)
        try:
            link: str | None = download_url(self.settings, job.job_id)
        except LinksNotConfigured:
            link = None
        cost = merged_cost(self.store, job).total_usd
        self.sender.send_message(
            self.target.chat_id,
            done_text(done, len(clips), cost, link),
            self.target.reply_to_message_id,
        )

    def failed(self, job: Job) -> None:
        self.sender.send_message(
            self.target.chat_id, failed_text(job), self.target.reply_to_message_id
        )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest -q tests/bot`
Expected: PASS (5 in `test_telegram.py`, 5 in `test_notifier.py`).

- [ ] **Step 9: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 10: Checkpoint (the user commits)**

Files: `pyproject.toml`, `uv.lock`, `src/clipforge/bot/__init__.py`, `src/clipforge/bot/telegram.py`, `src/clipforge/bot/messages.py`, `src/clipforge/bot/notifier.py`, `tests/bot/__init__.py`, `tests/bot/fakes.py`, `tests/bot/test_telegram.py`, `tests/bot/test_notifier.py`.

---

### Task 3: Bot command parsing and `build_job_input`

**Files:**
- Create: `src/clipforge/bot/commands.py`
- Test: `tests/bot/test_commands.py`

**Interfaces:**
- Consumes:
  - `Settings.default_clip_count`, `default_clip_len`, `default_permission`;
  - `models.JobInput`, `TelegramTarget`;
  - `bot.messages.USAGE` (Task 2).
- Produces:
  - `class CommandError(ValueError)`, where `str(exc)` is the reply;
  - `ClipCommand(url: str, options: dict[str, str])`, `JobCommand(name: Literal["status", "resume"], job_id: str)`, `HelpCommand()`, and `Command = ClipCommand | JobCommand | HelpCommand`;
  - `parse_text(text: str) -> Command`, `parse_options(tokens: list[str]) -> dict[str, str]`, `parse_caption(caption: str | None) -> dict[str, str]`;
  - `build_job_input(settings, options, target: TelegramTarget | None, *, url: str | None = None, telegram_file_id: str | None = None) -> JobInput`, which raises `CommandError`.

- [ ] **Step 1: Write the failing tests**

`tests/bot/test_commands.py`:

```python
"""Parsing /clip, /status, /resume and bare links (spec §5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipforge.bot.commands import (
    ClipCommand,
    CommandError,
    HelpCommand,
    JobCommand,
    build_job_input,
    parse_caption,
    parse_text,
)
from clipforge.models import Permission, TelegramTarget
from tests.bot.fakes import make_settings

URL = "https://media.example.com/ep.mp4"
TARGET = TelegramTarget(chat_id=7, reply_to_message_id=3)


def test_clip_with_options_and_quoted_credit() -> None:
    command = parse_text(f'/clip {URL} n=3 len=20-45 lang=es perm=cc_by credit="Jane Doe, CC BY"')
    assert command == ClipCommand(
        URL,
        {"n": "3", "len": "20-45", "lang": "es", "perm": "cc_by", "credit": "Jane Doe, CC BY"},
    )


def test_clip_addressed_to_the_bot() -> None:
    assert parse_text(f"/clip@ClipForgeBot {URL}") == ClipCommand(URL, {})


def test_bare_link_is_a_clip_command() -> None:
    assert parse_text(URL) == ClipCommand(URL, {})
    assert parse_text(f"{URL} n=2") == ClipCommand(URL, {"n": "2"})


def test_status_and_resume() -> None:
    assert parse_text("/status 20260923-aaaaaaaa-0001") == JobCommand(
        "status", "20260923-aaaaaaaa-0001"
    )
    assert parse_text("/resume J") == JobCommand("resume", "J")


@pytest.mark.parametrize("text", ["/start", "/help", "hello there", "", "   "])
def test_everything_else_is_help(text: str) -> None:
    assert parse_text(text) == HelpCommand()


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("/clip", "Usage: /clip"),
        ("/clip not-a-link", "Usage: /clip"),
        (f"/clip {URL} style=bold", "Unknown option"),
        (f"/clip {URL} n=", "Unknown option"),
        (f'/clip {URL} credit="open', "quotes"),
        ("/status", "Usage: /status"),
    ],
)
def test_errors_explain_themselves(text: str, fragment: str) -> None:
    with pytest.raises(CommandError, match=fragment):
        parse_text(text)


def test_caption_options() -> None:
    assert parse_caption(None) == {}
    assert parse_caption("n=2 len=10-20") == {"n": "2", "len": "10-20"}
    with pytest.raises(CommandError):
        parse_caption("just a caption")


def test_build_job_input_uses_settings_defaults(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, default_clip_count=4, default_clip_len="25-50")
    job_input = build_job_input(settings, {}, TARGET, url=URL)
    assert str(job_input.source_url) == URL
    assert job_input.permission is Permission.OWN
    assert (job_input.options.n, job_input.options.min_len, job_input.options.max_len) == (
        4,
        25.0,
        50.0,
    )
    assert job_input.notify == TARGET


def test_build_job_input_applies_options(tmp_path: Path) -> None:
    options = {"n": "2", "len": "10-20", "lang": "auto", "perm": "cc_by", "credit": "Jane"}
    job_input = build_job_input(make_settings(tmp_path), options, None, telegram_file_id="F")
    assert job_input.telegram_file_id == "F" and job_input.notify is None
    assert job_input.options.n == 2 and job_input.options.language is None
    assert job_input.permission is Permission.CC_BY and job_input.source_credit == "Jane"


@pytest.mark.parametrize(
    ("options", "fragment"),
    [
        ({"n": "99"}, "options.n"),
        ({"len": "abc"}, "len must look like"),
        ({"len": "60-30"}, "min_len"),
        ({"perm": "cc_by"}, "credit"),
        ({"perm": "stolen"}, "permission"),
    ],
)
def test_build_job_input_errors(tmp_path: Path, options: dict[str, str], fragment: str) -> None:
    with pytest.raises(CommandError, match=fragment):
        build_job_input(make_settings(tmp_path), options, TARGET, url=URL)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/bot/test_commands.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.bot.commands'`.

- [ ] **Step 3: Write `src/clipforge/bot/commands.py`**

```python
"""Parse bot messages into commands and build a JobInput from options (spec §5).

Pure functions: no Telegram, no Dict. The CLI reuses `build_job_input`, so `/clip` options and
`clipforge run` flags validate the same way.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from clipforge.config import Settings
from clipforge.models import JobInput, TelegramTarget

OPTION_KEYS = ("n", "len", "lang", "perm", "credit")
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_CLIP_USAGE = 'Usage: /clip <link> [n=5] [len=30-60] [lang=en] [perm=own] [credit="..."]'
_OPTIONS_HINT = 'Options: n=5 len=30-60 lang=en perm=own credit="..."'


class CommandError(ValueError):
    """A message the user can fix; `str(exc)` is the reply."""


@dataclass(frozen=True)
class ClipCommand:
    url: str
    options: dict[str, str]


@dataclass(frozen=True)
class JobCommand:
    name: Literal["status", "resume"]
    job_id: str


@dataclass(frozen=True)
class HelpCommand:
    pass


Command = ClipCommand | JobCommand | HelpCommand


def _split(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        raise CommandError("Unbalanced quotes in the command.") from None


def parse_text(text: str) -> Command:
    tokens = _split(text.strip())
    if not tokens:
        return HelpCommand()
    head = tokens[0]
    if head.startswith("/"):
        name = head.split("@", 1)[0].lower()  # "/clip@ClipForgeBot"
        if name == "/clip":
            if len(tokens) < 2 or not _URL.fullmatch(tokens[1]):
                raise CommandError(_CLIP_USAGE)
            return ClipCommand(tokens[1], parse_options(tokens[2:]))
        if name in ("/status", "/resume"):
            if len(tokens) != 2:
                raise CommandError(f"Usage: {name} <job_id>")
            return JobCommand("status" if name == "/status" else "resume", tokens[1])
        return HelpCommand()
    if _URL.fullmatch(head):
        return ClipCommand(head, parse_options(tokens[1:]))
    return HelpCommand()


def parse_options(tokens: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        key = key.lower()
        if not sep or not value or key not in OPTION_KEYS:
            raise CommandError(f"Unknown option {token!r}. {_OPTIONS_HINT}")
        options[key] = value
    return options


def parse_caption(caption: str | None) -> dict[str, str]:
    """Options written in an uploaded video's caption, e.g. `n=2 len=10-20`."""
    if not caption or not caption.strip():
        return {}
    return parse_options(_split(caption))


def build_job_input(
    settings: Settings,
    options: dict[str, str],
    target: TelegramTarget | None,
    *,
    url: str | None = None,
    telegram_file_id: str | None = None,
) -> JobInput:
    low, high = settings.default_clip_len
    clip: dict[str, object] = {"n": settings.default_clip_count, "min_len": low, "max_len": high}
    if "n" in options:
        clip["n"] = options["n"]
    if "len" in options:
        min_len, sep, max_len = options["len"].partition("-")
        if not sep:
            raise CommandError("len must look like 30-60 (seconds).")
        clip["min_len"], clip["max_len"] = min_len, max_len
    if "lang" in options:
        lang = options["lang"]
        clip["language"] = None if lang.lower() == "auto" else lang
    data: dict[str, object] = {
        "source_url": url,
        "telegram_file_id": telegram_file_id,
        "permission": options.get("perm", settings.default_permission),
        "source_credit": options.get("credit"),
        "options": clip,
        "notify": target.model_dump() if target is not None else None,
    }
    try:
        return JobInput.model_validate(data)
    except ValidationError as exc:
        raise CommandError(_first_error(exc)) from None


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    where = ".".join(str(part) for part in error["loc"])
    message = str(error["msg"]).removeprefix("Value error, ")
    return f"Invalid {where}: {message}" if where else message
```

If a `test_build_job_input_errors` case fails only because pydantic words its message differently (for example, the `len=60-30` error reads `min_len must be < max_len` without `options.` in front), fix the expected fragment and record a ruling. The contract is "the reply names the bad option", not the exact pydantic wording.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/bot/test_commands.py`
Expected: PASS (all 23 cases, parametrized ones included).

- [ ] **Step 5: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 6: Checkpoint (the user commits)**

Files: `src/clipforge/bot/commands.py`, `tests/bot/test_commands.py`.

---

### Task 4: The webhook handler

**Files:**
- Modify: `src/clipforge/jobs.py` (add `is_job_id` and `DictJobStore.claim_update`)
- Create: `src/clipforge/bot/webhook.py`
- Test: `tests/bot/test_webhook.py`, `tests/test_jobs.py` (append)

**Interfaces:**
- Consumes:
  - Tasks 2 and 3: `bot.commands.*`, `bot.messages.*`, `bot.telegram.TelegramSender`;
  - `links.with_download_url` (Task 1);
  - `service.create_job(deps, job_input) -> Job`, `service.get_job_view(store, root, job_id) -> JobView`, `service.resume_job(deps, job_id) -> JobView`;
  - `pipeline.steps.Deps`, `pipeline.steps.JobNotResumable`.
- Produces:
  - `jobs.is_job_id(value: str) -> bool`, `jobs.DictJobStore.claim_update(update_id: int) -> bool`;
  - `bot.webhook`: `MAX_UPLOAD_BYTES = 20 * 1024 * 1024`, `BotContext(settings: Settings, sender: TelegramSender, deps: Deps)`, and `handle_update(body: dict[str, Any], ctx: BotContext) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jobs.py`:

```python
def test_is_job_id() -> None:
    from clipforge.jobs import is_job_id, new_job_id

    assert is_job_id(new_job_id("https://a.example/v.mp4"))
    for bad in ["", "..", "../20260923-aaaaaaaa-0001", "20260923-aaaaaaaa-0001/x", "J"]:
        assert not is_job_id(bad)


def test_claim_update_once() -> None:
    from clipforge.jobs import DictJobStore
    from clipforge.pipeline.deps import MemoryKV

    kv = MemoryKV()
    store = DictJobStore(kv)
    assert store.claim_update(10) and not store.claim_update(10) and store.claim_update(11)
    assert "tg:update:10" in kv.keys()
    assert store.list_job_ids() == []  # update claims are not jobs
```

`tests/bot/test_webhook.py`:

```python
"""handle_update: one Telegram update in, at most one job and one reply out (spec §5)."""

from __future__ import annotations

import pytest

from clipforge.bot import messages
from clipforge.bot.webhook import MAX_UPLOAD_BYTES, BotContext, handle_update
from clipforge.models import TelegramTarget
from clipforge.pipeline.deps import SpawnCall
from tests.bot.fakes import CHAT, FakeSender, make_settings, update, video
from tests.pipeline.harness import Harness

URL = "https://media.example.com/ep.mp4"
Bot = tuple[BotContext, FakeSender]


@pytest.fixture
def bot(harness: Harness) -> Bot:
    sender = FakeSender()
    return BotContext(make_settings(harness.root), sender, harness.deps), sender


def _jobs(harness: Harness) -> list[str]:
    return harness.store.list_job_ids()


def test_clip_command_creates_a_job_and_replies(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=f"/clip {URL} n=2"), ctx)
    [job_id] = _jobs(harness)
    job = harness.store.get(job_id)
    assert str(job.input.source_url) == URL and job.input.options.n == 2
    assert job.input.notify == TelegramTarget(chat_id=CHAT, reply_to_message_id=3)
    assert list(harness.spawner.queue) == [SpawnCall("ingest", job_id, None)]
    assert sender.messages == [(CHAT, messages.job_accepted(job_id), 3)]


def test_bare_link_creates_a_job(harness: Harness, bot: Bot) -> None:
    ctx, _ = bot
    handle_update(update(text=URL), ctx)
    assert len(_jobs(harness)) == 1


def test_duplicate_update_is_handled_once(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(5, text=URL), ctx)
    handle_update(update(5, text=URL), ctx)
    assert len(_jobs(harness)) == 1 and len(sender.messages) == 1


def test_stranger_is_ignored_without_trace(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=URL, user_id=666), ctx)
    assert sender.messages == [] and _jobs(harness) == []
    assert not any(k.startswith("tg:") for k in harness.store.kv.keys())


def test_edited_message_is_ignored(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=URL, kind="edited_message"), ctx)
    handle_update(update(2, text=URL, kind="channel_post"), ctx)
    assert sender.messages == [] and _jobs(harness) == []


def test_sticker_gets_usage(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    sticker = {
        "file_id": "S",
        "file_unique_id": "US",
        "width": 1,
        "height": 1,
        "is_animated": False,
        "is_video": False,
        "type": "regular",
    }
    handle_update(update(sticker=sticker), ctx)
    assert sender.messages == [(CHAT, messages.USAGE, 3)]


def test_small_video_upload_creates_a_telegram_job(harness: Harness, bot: Bot) -> None:
    ctx, _ = bot
    handle_update(update(video=video(5_000_000), caption="n=1 len=10-20"), ctx)
    [job_id] = _jobs(harness)
    job = harness.store.get(job_id)
    assert job.input.telegram_file_id == "VID" and job.input.options.n == 1


def test_document_upload_is_accepted(harness: Harness, bot: Bot) -> None:
    ctx, _ = bot
    document = {"file_id": "DOC", "file_unique_id": "UDOC", "file_size": 1000}
    handle_update(update(document=document), ctx)
    assert harness.store.get(_jobs(harness)[0]).input.telegram_file_id == "DOC"


def test_upload_over_20_mb_is_refused(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(video=video(MAX_UPLOAD_BYTES + 1)), ctx)
    assert _jobs(harness) == [] and sender.messages == [(CHAT, messages.TOO_BIG, 3)]


def test_bad_option_replies_with_the_error(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=f"/clip {URL} style=bold"), ctx)
    assert _jobs(harness) == [] and "Unknown option" in sender.messages[0][1]


def test_status_of_a_finished_job_has_the_link(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    job_id = harness.submit()
    harness.run()
    handle_update(update(text=f"/status {job_id}"), ctx)
    text = sender.messages[-1][1]
    assert text.startswith(f"job {job_id}: done") and f"/jobs/{job_id}/download?" in text


def test_status_rejects_non_job_ids(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    (harness.root / "x" / "output").mkdir(parents=True)
    handle_update(update(text="/status ../x"), ctx)
    assert sender.messages[-1][1] == "No job ../x."


def test_resume_of_a_running_job_explains(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    job_id = harness.submit()
    handle_update(update(text=f"/resume {job_id}"), ctx)
    assert "only failed jobs can be resumed" in sender.messages[-1][1]


def test_resume_of_a_failed_job_respawns(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    harness.stages.permanent["transcribe"] = "no speech"
    job_id = harness.submit()
    harness.run()
    harness.stages.permanent.clear()
    handle_update(update(text=f"/resume {job_id}"), ctx)
    assert sender.messages[-1][1] == f"Resuming job {job_id}."
    assert harness.spawner.queue[-1] == SpawnCall("transcribe", job_id, None)
```

Lines over 100 characters here are the formatter's job: run `uv run ruff format tests/bot` after writing the file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/bot/test_webhook.py tests/test_jobs.py`
Expected: FAIL. `tests/bot/test_webhook.py` fails on `No module named 'clipforge.bot.webhook'`; the two new jobs tests fail on `ImportError: cannot import name 'is_job_id'` and `AttributeError: ... 'claim_update'`.

- [ ] **Step 3: Add `is_job_id` and `claim_update` to `src/clipforge/jobs.py`**

After `new_job_id` (the module already imports `hashlib` and `secrets`; add `import re` to the imports):

```python
_JOB_ID = re.compile(r"\d{8}-[0-9a-f]{8}-[0-9a-f]{4}")


def is_job_id(value: str) -> bool:
    """True for ids `new_job_id` makes; anything else (paths, `..`) is rejected at the edge."""
    return _JOB_ID.fullmatch(value) is not None
```

In `DictJobStore`, after `release_all`:

```python
    def claim_update(self, update_id: int) -> bool:
        """Telegram redelivers webhooks; each update is handled once (`tg:update:<id>`)."""
        return self.kv.put(f"tg:update:{update_id}", "1", skip_if_exists=True)
```

- [ ] **Step 4: Write `src/clipforge/bot/webhook.py`**

```python
"""Handle one Telegram update (webhook mode, spec §5). The API's webhook route calls this
after checking Telegram's secret-token header."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from telegram import Message, Update

from clipforge.bot.commands import (
    ClipCommand,
    CommandError,
    JobCommand,
    build_job_input,
    parse_caption,
    parse_text,
)
from clipforge.bot.messages import TOO_BIG, USAGE, job_accepted, status_text
from clipforge.bot.telegram import TelegramSender
from clipforge.config import Settings
from clipforge.jobs import is_job_id
from clipforge.links import with_download_url
from clipforge.models import JobInput, TelegramTarget
from clipforge.pipeline.steps import Deps, JobNotResumable
from clipforge.service import create_job, get_job_view, resume_job

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # the Bot API's getFile limit (ADR-10)


@dataclass
class BotContext:
    settings: Settings
    sender: TelegramSender
    deps: Deps  # create_job / resume_job need only the store and the spawner


def handle_update(body: dict[str, Any], ctx: BotContext) -> None:
    update = Update.de_json(body, None)
    message = update.message  # edited messages and channel posts are ignored
    if message is None or message.from_user is None:
        return
    if message.from_user.id not in ctx.settings.telegram_allowed_user_ids:
        log.info("ignoring update %s from a user not in the allow list", update.update_id)
        return
    if not ctx.deps.store.claim_update(update.update_id):
        return
    target = TelegramTarget(chat_id=message.chat.id, reply_to_message_id=message.message_id)
    try:
        reply = _reply_for(message, target, ctx)
    except CommandError as exc:
        reply = str(exc)
    ctx.sender.send_message(target.chat_id, reply, target.reply_to_message_id)


def _reply_for(message: Message, target: TelegramTarget, ctx: BotContext) -> str:
    upload = message.video or message.document
    if upload is not None:
        if upload.file_size is not None and upload.file_size > MAX_UPLOAD_BYTES:
            return TOO_BIG
        options = parse_caption(message.caption)
        job_input = build_job_input(
            ctx.settings, options, target, telegram_file_id=upload.file_id
        )
        return _submit(ctx, job_input)
    if not message.text:
        return USAGE
    command = parse_text(message.text)
    match command:
        case ClipCommand(url=url, options=options):
            return _submit(ctx, build_job_input(ctx.settings, options, target, url=url))
        case JobCommand(name="status", job_id=job_id):
            return _status(ctx, job_id)
        case JobCommand(name="resume", job_id=job_id):
            return _resume(ctx, job_id)
        case _:
            return USAGE


def _submit(ctx: BotContext, job_input: JobInput) -> str:
    return job_accepted(create_job(ctx.deps, job_input).job_id)


def _status(ctx: BotContext, job_id: str) -> str:
    if not is_job_id(job_id):
        return f"No job {job_id}."
    try:
        view = get_job_view(ctx.deps.store, ctx.deps.root, job_id)
    except KeyError:
        return f"No job {job_id}."
    return status_text(with_download_url(view, ctx.settings))


def _resume(ctx: BotContext, job_id: str) -> str:
    if not is_job_id(job_id):
        return f"No job {job_id}."
    try:
        resume_job(ctx.deps, job_id)
    except KeyError:
        return f"No job {job_id}."
    except JobNotResumable as exc:
        return str(exc)
    return f"Resuming job {job_id}."
```

Note on `test_resume_of_a_running_job_explains`: `harness.submit()` leaves the job `queued`, so `JobNotResumable`'s message reads "job <id> is still queued; only failed jobs can be resumed". The assertion only checks the second half.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/bot tests/test_jobs.py`
Expected: PASS.

- [ ] **Step 6: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 7: Checkpoint (the user commits)**

Files: `src/clipforge/jobs.py`, `src/clipforge/bot/webhook.py`, `tests/bot/test_webhook.py`, `tests/test_jobs.py`.

---

### Task 5: The job API (FastAPI)

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Create: `src/clipforge/api/__init__.py` (empty), `src/clipforge/api/main.py`
- Create: `tests/api/__init__.py` (empty), `tests/api/test_api.py`

**Interfaces:**
- Consumes:
  - Task 1: `links.verify`, `links.with_download_url`;
  - Task 4: `bot.webhook.BotContext`, `bot.webhook.handle_update`;
  - Task 2: `bot.telegram.TelegramSender`;
  - `jobs.is_job_id`; `service.create_job`, `service.get_job_view`, `service.resume_job`; `pipeline.steps.Deps`, `JobNotResumable`.
- Produces:
  - `api.main.ApiContext(settings: Settings, deps: Callable[[], Deps], sender: Callable[[], TelegramSender | None])`;
  - `api.main.create_app(ctx: ApiContext) -> FastAPI` with these routes:
    - `POST /jobs` → 201 `{"job_id": ...}`
    - `GET /jobs/{id}` → `JobView`
    - `POST /jobs/{id}/resume` → `JobView`
    - `GET /jobs/{id}/download?exp=&sig=` → zip
    - `POST /telegram/webhook` → `{"ok": true}`

- [ ] **Step 1: Add the dependency**

Run: `uv add "fastapi>=0.141"`
Expected: `pyproject.toml` lists `fastapi>=0.141`; `uv run python -c "import fastapi; print(fastapi.__version__)"` prints `0.141.1` or later.

- [ ] **Step 2: Write the failing tests**

`tests/api/__init__.py`: empty.

`tests/api/test_api.py`:

```python
"""The job API with the in-process chain behind it (spec §5, §6)."""

from __future__ import annotations

import dataclasses
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from clipforge.api.main import ApiContext, create_app
from clipforge.links import sign
from clipforge.pipeline.deps import SpawnCall
from tests.bot.fakes import FakeSender, make_settings, update
from tests.pipeline.harness import Harness

URL = "https://media.example.com/ep.mp4"
AUTH = {"Authorization": "Bearer t0ken"}
HOOK = {"X-Telegram-Bot-Api-Secret-Token": "hook-secret"}
BODY = {"source_url": URL, "permission": "own", "options": {"n": 2}}


def _client(harness: Harness, sender: FakeSender | None = None, **settings: object) -> TestClient:
    ctx = ApiContext(
        settings=make_settings(harness.root, **settings),
        deps=lambda: harness.deps,
        sender=lambda: sender,
    )
    return TestClient(create_app(ctx))


def _done_job(harness: Harness) -> str:
    job_id = harness.submit()
    harness.run()
    return job_id


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "t0ken"}])
def test_bad_or_missing_token_is_401(harness: Harness, headers: dict[str, str]) -> None:
    client = _client(harness)
    assert client.post("/jobs", json=BODY, headers=headers).status_code == 401
    assert client.get("/jobs/20260923-aaaaaaaa-0001", headers=headers).status_code == 401


def test_api_token_unset_is_503(harness: Harness) -> None:
    response = _client(harness, api_token=None).post("/jobs", json=BODY, headers=AUTH)
    assert response.status_code == 503 and "API_TOKEN" in response.json()["detail"]


def test_post_job_creates_and_spawns(harness: Harness) -> None:
    response = _client(harness).post("/jobs", json=BODY, headers=AUTH)
    assert response.status_code == 201
    job_id = response.json()["job_id"]
    assert harness.store.get(job_id).input.options.n == 2
    assert list(harness.spawner.queue) == [SpawnCall("ingest", job_id, None)]


def test_invalid_job_input_is_422(harness: Harness) -> None:
    body = {**BODY, "telegram_file_id": "F"}  # two sources
    assert _client(harness).post("/jobs", json=body, headers=AUTH).status_code == 422


def test_get_job_view_with_signed_link_then_download(harness: Harness) -> None:
    job_id = _done_job(harness)
    client = _client(harness)
    view = client.get(f"/jobs/{job_id}", headers=AUTH).json()
    assert view["status"] == "done" and len(view["clips"]) == 5
    link = urlsplit(view["download_url"])
    response = client.get(f"{link.path}?{link.query}")  # no bearer: the signature authorizes
    assert response.status_code == 200 and response.content == b"zip"
    assert response.headers["content-type"] == "application/zip"


def test_unknown_or_malformed_job_is_404(harness: Harness) -> None:
    client = _client(harness)
    assert client.get("/jobs/20260923-aaaaaaaa-0001", headers=AUTH).status_code == 404
    assert client.get("/jobs/not-a-job", headers=AUTH).status_code == 404


def test_download_rejects_expired_and_tampered(harness: Harness) -> None:
    job_id = _done_job(harness)
    client = _client(harness)
    expired = sign("k3y", job_id, 1_000)
    assert client.get(f"/jobs/{job_id}/download?exp=1000&sig={expired}").status_code == 403
    exp = 4_000_000_000
    good = sign("k3y", job_id, exp)
    tampered = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert client.get(f"/jobs/{job_id}/download?exp={exp}&sig={tampered}").status_code == 403
    assert client.get(f"/jobs/{job_id}/download?exp={exp}&sig={good}").status_code == 200


def test_download_rejects_other_job_and_traversal(harness: Harness) -> None:
    job_id = _done_job(harness)
    client = _client(harness)
    exp = 4_000_000_000
    other = "20260923-bbbbbbbb-0001"
    reused = sign("k3y", job_id, exp)
    assert client.get(f"/jobs/{other}/download?exp={exp}&sig={reused}").status_code == 403
    for bad in ["..", "%2e%2e", "..%2F..%2Fetc"]:
        sig = sign("k3y", bad, exp)
        assert client.get(f"/jobs/{bad}/download?exp={exp}&sig={sig}").status_code in (403, 404)


def test_download_before_done_is_404(harness: Harness) -> None:
    job_id = harness.submit()
    exp = 4_000_000_000
    sig = sign("k3y", job_id, exp)
    assert _client(harness).get(f"/jobs/{job_id}/download?exp={exp}&sig={sig}").status_code == 404


def test_download_key_unset_is_503(harness: Harness) -> None:
    client = _client(harness, download_signing_key=None)
    assert client.get("/jobs/20260923-aaaaaaaa-0001/download?exp=1&sig=x").status_code == 503


def test_resume(harness: Harness) -> None:
    client = _client(harness)
    running = harness.submit()
    assert client.post(f"/jobs/{running}/resume", headers=AUTH).status_code == 409
    assert client.post("/jobs/20260923-aaaaaaaa-0001/resume", headers=AUTH).status_code == 404

    harness.stages.permanent["transcribe"] = "no speech"
    failed = harness.submit()
    harness.run()
    harness.stages.permanent.clear()
    response = client.post(f"/jobs/{failed}/resume", headers=AUTH)
    assert response.status_code == 200 and response.json()["status"] == "running"
    assert harness.spawner.queue[-1] == SpawnCall("transcribe", failed, None)


class _BrokenVolume:
    def commit(self) -> None:
        return None

    def reload(self) -> None:
        raise RuntimeError("there are open files preventing the operation")


def test_volume_reload_failure_still_serves_status(harness: Harness) -> None:
    job_id = _done_job(harness)
    deps = dataclasses.replace(harness.deps, volume=_BrokenVolume())
    ctx = ApiContext(make_settings(harness.root), deps=lambda: deps, sender=lambda: None)
    response = TestClient(create_app(ctx)).get(f"/jobs/{job_id}", headers=AUTH)
    assert response.status_code == 200 and response.json()["status"] == "done"


def test_webhook_checks_the_secret(harness: Harness) -> None:
    sender = FakeSender()
    client = _client(harness, sender)
    bad = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    assert client.post("/telegram/webhook", json=update(text=URL), headers=bad).status_code == 403
    assert client.post("/telegram/webhook", json=update(text=URL)).status_code == 403
    assert harness.store.list_job_ids() == [] and sender.messages == []


def test_webhook_secret_unset_is_503(harness: Harness) -> None:
    client = _client(harness, FakeSender(), telegram_webhook_secret=None)
    assert client.post("/telegram/webhook", json=update(text=URL), headers=HOOK).status_code == 503


def test_webhook_handles_an_update(harness: Harness) -> None:
    sender = FakeSender()
    response = _client(harness, sender).post(
        "/telegram/webhook", json=update(text=URL), headers=HOOK
    )
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert len(harness.store.list_job_ids()) == 1 and len(sender.messages) == 1


def test_webhook_answers_200_when_handling_fails(harness: Harness) -> None:
    sender = FakeSender(fail=True)  # the reply raises
    response = _client(harness, sender).post(
        "/telegram/webhook", json=update(text=URL), headers=HOOK
    )
    assert response.status_code == 200


def test_openapi_docs_are_not_public(harness: Harness) -> None:
    client = _client(harness)
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_zip_path_must_stay_inside_root(harness: Harness) -> None:
    job_id = _done_job(harness)
    job = harness.store.get(job_id)
    harness.store.save(job.model_copy(update={"output_zip": "../outside.zip"}))
    (harness.root.parent / "outside.zip").write_bytes(b"secret")
    exp = 4_000_000_000
    sig = sign("k3y", job_id, exp)
    assert _client(harness).get(f"/jobs/{job_id}/download?exp={exp}&sig={sig}").status_code == 404
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest -q tests/api`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.api'`.

- [ ] **Step 4: Write `src/clipforge/api/main.py`**

```python
"""Job API (spec §5): the entry point for the CLI, curl and the Telegram webhook (ADR-2).

Routes are sync, so FastAPI runs them in worker threads: the Modal Dict/Function calls block,
and the Telegram bridge uses `asyncio.run`, which needs a thread without a running loop.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from clipforge.bot.telegram import TelegramSender
from clipforge.bot.webhook import BotContext, handle_update
from clipforge.config import Settings
from clipforge.jobs import is_job_id
from clipforge.links import verify, with_download_url
from clipforge.models import JobInput, JobView
from clipforge.pipeline.steps import Deps, JobNotResumable
from clipforge.service import create_job, get_job_view, resume_job

log = logging.getLogger(__name__)


@dataclass
class ApiContext:
    settings: Settings
    deps: Callable[[], Deps]  # built lazily, once per container
    sender: Callable[[], TelegramSender | None]


def _same(given: str | None, expected: str) -> bool:
    return hmac.compare_digest((given or "").encode(), expected.encode())


def create_app(ctx: ApiContext) -> FastAPI:
    settings = ctx.settings
    app = FastAPI(title="ClipForge", docs_url=None, redoc_url=None, openapi_url=None)

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.api_token is None:
            raise HTTPException(503, "API_TOKEN is not configured")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not _same(token, settings.api_token.get_secret_value()):
            raise HTTPException(
                401, "invalid or missing bearer token", headers={"WWW-Authenticate": "Bearer"}
            )

    authorized = [Depends(require_token)]

    def reload(deps: Deps) -> None:
        try:
            deps.volume.reload()
        except Exception:
            log.warning("volume reload failed; serving possibly stale files", exc_info=True)

    def view(job_id: str) -> JobView:
        if not is_job_id(job_id):
            raise HTTPException(404, "unknown job")
        deps = ctx.deps()
        reload(deps)
        try:
            found = get_job_view(deps.store, deps.root, job_id)
        except KeyError:
            raise HTTPException(404, "unknown job") from None
        return with_download_url(found, settings)

    @app.post("/jobs", status_code=201, dependencies=authorized)
    def post_job(job_input: JobInput) -> dict[str, str]:
        return {"job_id": create_job(ctx.deps(), job_input).job_id}

    @app.get("/jobs/{job_id}", dependencies=authorized)
    def get_job(job_id: str) -> JobView:
        return view(job_id)

    @app.post("/jobs/{job_id}/resume", dependencies=authorized)
    def post_resume(job_id: str) -> JobView:
        if not is_job_id(job_id):
            raise HTTPException(404, "unknown job")
        try:
            resume_job(ctx.deps(), job_id)
        except KeyError:
            raise HTTPException(404, "unknown job") from None
        except JobNotResumable as exc:
            raise HTTPException(409, str(exc)) from None
        return view(job_id)

    @app.get("/jobs/{job_id}/download")
    def download(job_id: str, exp: int, sig: str) -> FileResponse:
        if settings.download_signing_key is None:
            raise HTTPException(503, "DOWNLOAD_SIGNING_KEY is not configured")
        key = settings.download_signing_key.get_secret_value()
        if not is_job_id(job_id) or not verify(key, job_id, exp, sig):
            raise HTTPException(403, "invalid or expired link")
        found = view(job_id)
        deps = ctx.deps()
        root = deps.root.resolve()
        path = (root / found.output_zip).resolve() if found.output_zip else None
        if path is None or not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "zip not found")
        return FileResponse(path, media_type="application/zip", filename=f"clipforge-{job_id}.zip")

    @app.post("/telegram/webhook")
    def telegram_webhook(
        body: Annotated[dict[str, Any], Body()],
        x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        sender = ctx.sender()
        if settings.telegram_webhook_secret is None or sender is None:
            raise HTTPException(503, "TELEGRAM_WEBHOOK_SECRET / TELEGRAM_BOT_TOKEN not configured")
        if not _same(
            x_telegram_bot_api_secret_token, settings.telegram_webhook_secret.get_secret_value()
        ):
            raise HTTPException(403, "bad secret token")
        try:
            handle_update(body, BotContext(settings, sender, ctx.deps()))
        except Exception:
            # The update is already claimed, so Telegram's redelivery would be dropped anyway;
            # a 5xx would only make Telegram back off the whole webhook.
            log.exception("handling a Telegram update failed")
        return {"ok": True}

    return app
```

Two checks while making the tests pass:
- `test_download_rejects_expired_and_tampered` and `test_zip_path_must_stay_inside_root` depend on the download route calling `view()`, which reloads the Volume and 404s unknown jobs.
- `test_webhook_answers_200_when_handling_fails` depends on `handle_update`'s reply raising inside the `try`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/api`
Expected: PASS (all).

- [ ] **Step 6: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 7: Checkpoint (the user commits)**

Files: `pyproject.toml`, `uv.lock`, `src/clipforge/api/__init__.py`, `src/clipforge/api/main.py`, `tests/api/__init__.py`, `tests/api/test_api.py`.

---

### Task 6: Runtime adapters and `build_deps`

**Files:**
- Create: `src/clipforge/runtime.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Consumes:
  - `pipeline.deps`: `KV`, `Volume`, `Spawner`, `StageRunner`, `Notifier`, `NullNotifier`;
  - `pipeline.steps.Deps`, `Step`, `dispatch`;
  - `jobs.DictJobStore`;
  - Task 2: `bot.notifier.TelegramNotifier`, `bot.telegram.TelegramClient`, `TelegramSender`.
- Produces:
  - `DictKV(d: Any)`, which implements `KV` over a `modal.Dict`-like object;
  - `ModalVolume(v: Any)`, which implements `Volume`;
  - `FunctionSpawner(functions: Mapping[Step, Any])`, which implements `Spawner` and raises `ValueError` if a step is missing;
  - `UnavailableStages()`, which implements `StageRunner` and raises on use;
  - `telegram_sender(settings) -> TelegramClient | None`;
  - `notifier_factory(settings, store, root, sender) -> Callable[[Job], Notifier]`;
  - `build_deps(settings, *, kv, volume, spawner, stages, sender) -> Deps`.

- [ ] **Step 1: Write the failing tests**

`tests/test_runtime.py`:

```python
"""Runtime wiring with Modal-shaped fakes: the adapters, the notifier choice, a whole chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clipforge.bot.notifier import TelegramNotifier
from clipforge.jobs import DictJobStore
from clipforge.models import JobInput, JobStatus, Permission, TelegramTarget
from clipforge.pipeline.deps import NullNotifier, NullVolume, QueueSpawner
from clipforge.pipeline.steps import Step, dispatch
from clipforge.runtime import (
    DictKV,
    FunctionSpawner,
    ModalVolume,
    UnavailableStages,
    build_deps,
    notifier_factory,
    telegram_sender,
)
from clipforge.service import create_job
from tests.bot.fakes import FakeSender, make_settings
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import SOURCE_URL


class FakeModalDict:
    """modal.Dict semantics: get → default, pop raises KeyError, put returns a bool."""

    def __init__(self) -> None:
        self.data: dict[Any, Any] = {}

    def get(self, key: Any, default: Any = None) -> Any:
        return self.data.get(key, default)

    def put(self, key: Any, value: Any, *, skip_if_exists: bool = False) -> bool:
        if skip_if_exists and key in self.data:
            return False
        self.data[key] = value
        return True

    def pop(self, key: Any) -> Any:
        return self.data.pop(key)

    def keys(self) -> Any:
        return iter(list(self.data))


class FakeFunction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def spawn(self, *args: str) -> None:
        self.calls.append(args)


def test_dict_kv_matches_the_kv_contract() -> None:
    kv = DictKV(FakeModalDict())
    assert kv.get("a") is None
    assert kv.put("a", "1") and kv.get("a") == "1"
    assert kv.put("a", "2", skip_if_exists=True) is False and kv.get("a") == "1"
    kv.delete("a")
    kv.delete("missing")  # no KeyError
    kv.put("b", "x")
    assert kv.keys() == ["b"]
    store = DictJobStore(kv)
    assert store.claim("J", "package") and not store.claim("J", "package")


def test_modal_volume_forwards() -> None:
    inner = NullVolume()
    volume = ModalVolume(inner)
    volume.commit()
    volume.reload()
    assert (inner.commits, inner.reloads) == (1, 1)


def test_function_spawner_routes_by_step() -> None:
    functions = {step: FakeFunction() for step in Step}
    spawner = FunctionSpawner(functions)
    spawner.spawn("ingest", "J")
    spawner.spawn(Step.CLIP, "J", "clip_01")
    assert functions[Step.INGEST].calls == [("J",)]
    assert functions[Step.CLIP].calls == [("J", "clip_01")]


def test_function_spawner_needs_every_step() -> None:
    with pytest.raises(ValueError, match="package"):
        FunctionSpawner({step: FakeFunction() for step in Step if step is not Step.PACKAGE})


def test_unavailable_stages_raise() -> None:
    with pytest.raises(RuntimeError, match="not available"):
        UnavailableStages().ingest(None, None)  # type: ignore[arg-type]


def test_telegram_sender_needs_a_token(tmp_path: Path) -> None:
    assert telegram_sender(make_settings(tmp_path, telegram_bot_token=None)) is None
    assert telegram_sender(make_settings(tmp_path)) is not None


def test_notifier_factory_picks_telegram_only_for_telegram_jobs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = DictJobStore(DictKV(FakeModalDict()))
    deps = build_deps(
        settings,
        kv=store.kv,
        volume=NullVolume(),
        spawner=QueueSpawner(),
        stages=FakeStages(),
        sender=FakeSender(),
    )
    plain = create_job(deps, JobInput(source_url=SOURCE_URL, permission=Permission.OWN))
    telegram = create_job(
        deps,
        JobInput(
            source_url=SOURCE_URL, permission=Permission.OWN, notify=TelegramTarget(chat_id=7)
        ),
    )
    build = notifier_factory(settings, store, tmp_path, FakeSender())
    assert isinstance(build(plain), NullNotifier)
    assert isinstance(build(telegram), TelegramNotifier)
    assert isinstance(notifier_factory(settings, store, tmp_path, None)(telegram), NullNotifier)


def _run_chain(settings_root: Path, sender: FakeSender) -> tuple[str, DictJobStore]:
    spawner = QueueSpawner()
    deps = build_deps(
        make_settings(settings_root),
        kv=DictKV(FakeModalDict()),
        volume=ModalVolume(NullVolume()),
        spawner=spawner,
        stages=FakeStages(),
        sender=sender,
    )
    job_input = JobInput(
        source_url=SOURCE_URL, permission=Permission.OWN, notify=TelegramTarget(chat_id=7)
    )
    job = create_job(deps, job_input)
    for _ in range(100):
        if not spawner.queue:
            break
        call = spawner.queue.popleft()
        dispatch(deps, call.step, call.job_id, call.clip_id)
    return job.job_id, deps.store


def test_build_deps_runs_a_whole_telegram_job(tmp_path: Path) -> None:
    sender = FakeSender()
    job_id, store = _run_chain(tmp_path, sender)
    assert store.get(job_id).status is JobStatus.DONE
    assert len(sender.videos) == 5 and sender.messages[-1][1].startswith("5 of 5 clips")


def test_failing_telegram_never_fails_the_job(tmp_path: Path) -> None:
    job_id, store = _run_chain(tmp_path, FakeSender(fail=True))
    job = store.get(job_id)
    assert job.status is JobStatus.DONE and job.output_zip is not None
```

Run `uv run ruff format tests/test_runtime.py` after writing it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_runtime.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.runtime'`.

- [ ] **Step 3: Write `src/clipforge/runtime.py`**

```python
"""Binds the pipeline's interfaces to Modal objects and builds `Deps` (ADR-9, ADR-12).

The adapters are duck-typed (`Any`), so this module never imports modal and is tested with
fakes. app.py passes in the real `modal.Dict`, `modal.Volume` and step functions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from clipforge.bot.notifier import TelegramNotifier
from clipforge.bot.telegram import TelegramClient, TelegramSender
from clipforge.config import Settings
from clipforge.jobs import DictJobStore, JobContext, Stored
from clipforge.models import (
    ClipOptions,
    ClipSpec,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    RenderedClip,
    SourceMedia,
    Transcript,
)
from clipforge.pipeline.deps import KV, Notifier, NullNotifier, Spawner, StageRunner, Volume
from clipforge.pipeline.steps import Deps, Step


class DictKV:
    """`KV` over a `modal.Dict` (values are the JSON strings DictJobStore writes)."""

    def __init__(self, d: Any) -> None:
        self._d = d

    def get(self, key: str) -> str | None:
        value = self._d.get(key)
        return None if value is None else str(value)

    def put(self, key: str, value: str, *, skip_if_exists: bool = False) -> bool:
        return bool(self._d.put(key, value, skip_if_exists=skip_if_exists))

    def delete(self, key: str) -> None:
        try:
            self._d.pop(key)
        except KeyError:
            pass

    def keys(self) -> list[str]:
        return [str(key) for key in self._d.keys()]  # noqa: SIM118 (not a dict)


class ModalVolume:
    def __init__(self, volume: Any) -> None:
        self._volume = volume

    def commit(self) -> None:
        self._volume.commit()

    def reload(self) -> None:
        self._volume.reload()


class FunctionSpawner:
    """Spawns the Modal function for a step: `fn.spawn(job_id)` or `fn.spawn(job_id, clip_id)`."""

    def __init__(self, functions: Mapping[Step, Any]) -> None:
        missing = [str(step) for step in Step if step not in functions]
        if missing:
            raise ValueError(f"no function for steps: {', '.join(missing)}")
        self._functions = dict(functions)

    def spawn(self, step: str, job_id: str, clip_id: str | None = None) -> None:
        function = self._functions[Step(step)]
        if clip_id is None:
            function.spawn(job_id)
        else:
            function.spawn(job_id, clip_id)


class UnavailableStages:
    """For containers that only create, read and resume jobs (web, sweeper, smoke)."""

    def _fail(self) -> RuntimeError:
        return RuntimeError("pipeline stages are not available in this container")

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]:
        raise self._fail()

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]:
        raise self._fail()

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]:
        raise self._fail()

    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        raise self._fail()

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]:
        raise self._fail()


def telegram_sender(settings: Settings) -> TelegramClient | None:
    if settings.telegram_bot_token is None:
        return None
    return TelegramClient(settings.telegram_bot_token.get_secret_value())


def notifier_factory(
    settings: Settings, store: DictJobStore, root: Path, sender: TelegramSender | None
) -> Callable[[Job], Notifier]:
    def build(job: Job) -> Notifier:
        if job.input.notify is None or sender is None:
            return NullNotifier()
        return TelegramNotifier(sender, job.input.notify, store, settings, root)

    return build


def build_deps(
    settings: Settings,
    *,
    kv: KV,
    volume: Volume,
    spawner: Spawner,
    stages: StageRunner,
    sender: TelegramSender | None,
) -> Deps:
    store = DictJobStore(kv)
    root = settings.jobs_root
    return Deps(
        store=store,
        volume=volume,
        spawner=spawner,
        stages=stages,
        root=root,
        notifier_for=notifier_factory(settings, store, root, sender),
    )
```

Note: `make_settings(root)` sets `jobs_root=root`, so `build_deps` uses the tmp dir in tests and `/jobs` on Modal.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_runtime.py`
Expected: PASS (9).

- [ ] **Step 5: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 6: Checkpoint (the user commits)**

Files: `src/clipforge/runtime.py`, `tests/test_runtime.py`.

---

### Task 7: The CLI (a thin API client) and `set-webhook`

**Files:**
- Create: `src/clipforge/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - the API from Task 5 (over HTTP; tests use `TestClient`, which is an `httpx.Client`);
  - `bot.commands.build_job_input`, `CommandError` (Task 3);
  - `bot.messages.status_text` (Task 2);
  - `bot.telegram.TelegramClient` (Task 2);
  - `models.JobInput`, `JobView`, `JobStatus`, `ClipStatus`, `Permission`.
- Produces:
  - `class ApiError(RuntimeError)`;
  - `ApiClient(http: httpx.Client, token: str)` with `create_job(job_input) -> str`, `get_job(job_id) -> JobView` and `resume(job_id) -> JobView`;
  - `wait(get_view, *, interval_s=5.0, timeout_s=3600.0, sleep=time.sleep, clock=time.monotonic, echo=print) -> JobView`;
  - `progress_line(view) -> str`;
  - `set_webhook(settings, client_factory=TelegramClient) -> str`;
  - `main(argv=None, *, http=None, settings=None, sleep=time.sleep) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
"""The CLI against the real API app with the in-process chain behind it."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clipforge.api.main import ApiContext, create_app
from clipforge.bot.telegram import TelegramClient
from clipforge.cli import main, set_webhook, wait
from clipforge.models import CostSummary, JobStatus, JobView, StageName
from tests.bot.fakes import FakeRequest, make_settings
from tests.pipeline.harness import Harness

URL = "https://media.example.com/ep.mp4"


@pytest.fixture
def api(harness: Harness) -> Iterator[TestClient]:
    ctx = ApiContext(make_settings(harness.root), deps=lambda: harness.deps, sender=lambda: None)
    with TestClient(create_app(ctx)) as client:
        yield client


def _run(harness: Harness, api: TestClient, *argv: str, **kw: object) -> int:
    return main(list(argv), http=api, settings=make_settings(harness.root), **kw)  # type: ignore[arg-type]


def test_run_no_wait_prints_the_job_id(harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(harness, api, "run", "--input", URL, "--n", "2", "--no-wait") == 0
    [job_id] = harness.store.list_job_ids()
    assert capsys.readouterr().out.strip() == f"job {job_id}"
    assert harness.store.get(job_id).input.options.n == 2


def test_run_waits_and_prints_the_link(harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(harness, api, "run", "--input", URL, sleep=lambda _s: harness.run())
    out = capsys.readouterr().out
    assert code == 0
    assert "done · 5 of 5 clips · $" in out
    assert "/download?exp=" in out.strip().splitlines()[-1]


def test_run_reports_failure_and_resume_hint(harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    harness.stages.permanent["transcribe"] = "no speech"
    code = _run(harness, api, "run", "--input", URL, sleep=lambda _s: harness.run())
    out = capsys.readouterr().out
    assert code == 1 and "failed at transcribe: no speech" in out and "clipforge resume" in out


def test_status_and_resume(harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    job_id = harness.submit()
    assert _run(harness, api, "status", job_id) == 0
    assert capsys.readouterr().out.startswith(f"job {job_id}: queued")
    assert _run(harness, api, "resume", job_id) == 1  # 409: not failed
    assert "HTTP 409" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--input", "/home/me/video.mp4"],
        ["run", "--input", URL, "--len", "abc"],
    ],
)
def test_bad_input_exits_2(harness: Harness, api: TestClient, argv: list[str]) -> None:
    assert _run(harness, api, *argv) == 2
    assert harness.store.list_job_ids() == []


def test_missing_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = make_settings(tmp_path, api_url=None)
    assert main(["status", "20260923-aaaaaaaa-0001"], settings=settings) == 2
    assert "API_URL" in capsys.readouterr().err


def test_wrong_token_is_reported(harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    settings = make_settings(harness.root, api_token="wrong")
    assert main(["status", "20260923-aaaaaaaa-0001"], http=api, settings=settings) == 1
    assert "HTTP 401" in capsys.readouterr().err


def test_wait_times_out() -> None:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    view = JobView(
        job_id="J",
        status=JobStatus.RUNNING,
        stage=StageName.INGEST,
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
    )
    ticks = iter([0.0, 10.0, 20.0, 30.0])
    lines: list[str] = []
    with pytest.raises(TimeoutError, match="still running"):
        wait(
            lambda: view,
            interval_s=5,
            timeout_s=15,
            sleep=lambda _s: None,
            clock=lambda: next(ticks),
            echo=lines.append,
        )
    assert lines == ["running · ingest"]  # repeated lines are printed once


def test_set_webhook(tmp_path: Path) -> None:
    request = FakeRequest()
    url = set_webhook(
        make_settings(tmp_path, api_url="https://api.example/"),
        client_factory=lambda token: TelegramClient(token, request_factory=lambda: request),
    )
    assert url == "https://api.example/telegram/webhook"
    assert request.calls[-1][1]["secret_token"] == "hook-secret"


def test_set_webhook_names_missing_settings(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="TELEGRAM_WEBHOOK_SECRET"):
        set_webhook(make_settings(tmp_path, telegram_webhook_secret=None))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_cli.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.cli'`.

- [ ] **Step 3: Write `src/clipforge/cli.py`**

```python
"""`clipforge` CLI: a thin client of the deployed job API (spec §5). Needs API_URL and
API_TOKEN (from `.env`); `set-webhook` also needs the Telegram values.

    uv run clipforge run --input <url> [--n 5 --len 30-60 --lang en --perm own --credit "..."]
    uv run clipforge status <job_id>
    uv run clipforge resume <job_id>
    uv run clipforge set-webhook
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections.abc import Callable

import httpx

from clipforge.bot.commands import CommandError, build_job_input
from clipforge.bot.messages import status_text
from clipforge.bot.telegram import TelegramClient
from clipforge.config import Settings, get_settings
from clipforge.models import ClipStatus, JobInput, JobStatus, JobView, Permission

_HTTP_URL = re.compile(r"https?://\S+", re.IGNORECASE)


class ApiError(RuntimeError):
    """The API answered with an error; the message is safe to print."""


class ApiClient:
    def __init__(self, http: httpx.Client, token: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {token}"}

    def _request(self, method: str, path: str, json_body: str | None = None) -> httpx.Response:
        headers = dict(self._headers)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        response = self._http.request(method, path, headers=headers, content=json_body)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(f"HTTP {response.status_code}: {detail}")
        return response

    def create_job(self, job_input: JobInput) -> str:
        response = self._request("POST", "/jobs", json_body=job_input.model_dump_json())
        return str(response.json()["job_id"])

    def get_job(self, job_id: str) -> JobView:
        return JobView.model_validate(self._request("GET", f"/jobs/{job_id}").json())

    def resume(self, job_id: str) -> JobView:
        return JobView.model_validate(self._request("POST", f"/jobs/{job_id}/resume").json())


def progress_line(view: JobView) -> str:
    line = f"{view.status} · {view.stage or 'queued'}"
    if view.progress is not None and view.status is JobStatus.RUNNING:
        line = f"{line} {view.progress.pct:.0f}%"
    if view.clips:
        done = sum(c.status is ClipStatus.DONE for c in view.clips)
        line = f"{line} · clips {done}/{len(view.clips)}"
    return line


def wait(
    get_view: Callable[[], JobView],
    *,
    interval_s: float = 5.0,
    timeout_s: float = 3600.0,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    echo: Callable[[str], object] = print,
) -> JobView:
    """Poll until the job is done or failed, printing each new progress line once."""
    deadline = clock() + timeout_s
    last: str | None = None
    while True:
        view = get_view()
        line = progress_line(view)
        if line != last:
            echo(line)
            last = line
        if view.status in (JobStatus.DONE, JobStatus.FAILED):
            return view
        if clock() >= deadline:
            raise TimeoutError(f"job {view.job_id} still {view.status} after {timeout_s:.0f} s")
        sleep(interval_s)


def set_webhook(
    settings: Settings, client_factory: Callable[[str], TelegramClient] = TelegramClient
) -> str:
    """Point Telegram at `<API_URL>/telegram/webhook` with the secret-token header."""
    missing = [
        name
        for name, value in (
            ("API_URL", settings.api_url),
            ("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
            ("TELEGRAM_WEBHOOK_SECRET", settings.telegram_webhook_secret),
        )
        if value is None
    ]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} in .env first")
    assert settings.api_url and settings.telegram_bot_token and settings.telegram_webhook_secret
    url = f"{settings.api_url.rstrip('/')}/telegram/webhook"
    client = client_factory(settings.telegram_bot_token.get_secret_value())
    client.set_webhook(url, settings.telegram_webhook_secret.get_secret_value())
    return url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipforge", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="submit a job and wait for it")
    run.add_argument("--input", required=True, help="direct http(s) media link (ADR-10)")
    run.add_argument("--n", help="number of clips")
    run.add_argument("--len", help="clip length range in seconds, e.g. 30-60")
    run.add_argument("--lang", help="language code, or auto")
    run.add_argument("--perm", choices=[p.value for p in Permission], help="source permission")
    run.add_argument("--credit", help="creator + license link (required for cc_by)")
    run.add_argument("--no-wait", action="store_true", help="print the job id and exit")
    for name in ("status", "resume"):
        commands.add_parser(name).add_argument("job_id")
    commands.add_parser("set-webhook", help="register the Telegram webhook")
    return parser


def _finish(view: JobView) -> int:
    if view.status is JobStatus.DONE:
        done = sum(c.status is ClipStatus.DONE for c in view.clips)
        print(f"done · {done} of {len(view.clips)} clips · ${view.cost.total_usd:.3f}")
        print(view.download_url or "(no download link: API_URL / DOWNLOAD_SIGNING_KEY unset)")
        return 0
    error = view.error
    where = f"{error.stage}: {error.message}" if error else str(view.stage)
    print(f"failed at {where}\nclipforge resume {view.job_id}")
    return 1


def main(
    argv: list[str] | None = None,
    *,
    http: httpx.Client | None = None,
    settings: Settings | None = None,
    sleep: Callable[[float], object] = time.sleep,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    if args.command == "set-webhook":
        print(f"webhook set: {set_webhook(settings)}")
        return 0
    if settings.api_token is None or (http is None and settings.api_url is None):
        print("set API_URL and API_TOKEN in .env (see .env.example)", file=sys.stderr)
        return 2
    http = http or httpx.Client(base_url=str(settings.api_url), timeout=30.0)
    client = ApiClient(http, settings.api_token.get_secret_value())
    try:
        if args.command == "run":
            return _run(args, settings, client, sleep)
        if args.command == "status":
            print(status_text(client.get_job(args.job_id)))
            return 0
        print(status_text(client.resume(args.job_id)))
        return 0
    except ApiError as exc:
        print(exc, file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(exc, file=sys.stderr)
        return 1


def _run(
    args: argparse.Namespace,
    settings: Settings,
    client: ApiClient,
    sleep: Callable[[float], object],
) -> int:
    if not _HTTP_URL.fullmatch(args.input):
        print("--input must be a direct http(s) media link (ADR-10)", file=sys.stderr)
        return 2
    options = {
        key: value
        for key, value in (
            ("n", args.n),
            ("len", args.len),
            ("lang", args.lang),
            ("perm", args.perm),
            ("credit", args.credit),
        )
        if value is not None
    }
    try:
        job_input = build_job_input(settings, options, None, url=args.input)
    except CommandError as exc:
        print(exc, file=sys.stderr)
        return 2
    job_id = client.create_job(job_input)
    print(f"job {job_id}")
    if args.no_wait:
        return 0
    return _finish(wait(lambda: client.get_job(job_id), sleep=sleep))
```

In `test_missing_config_exits_2`, `http` is None and `api_url` is None, so the check exits 2 before building a client. `pyproject.toml` already declares `clipforge = "clipforge.cli:main"`; the generated script calls `sys.exit(main())`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_cli.py`
Expected: PASS (all). Then `uv run clipforge --help` lists `run`, `status`, `resume` and `set-webhook`.

- [ ] **Step 5: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 6: Checkpoint (the user commits)**

Files: `src/clipforge/cli.py`, `tests/test_cli.py`.

---

### Task 8: Modal app: images, step functions, sweeper, web endpoint and the smoke entrypoint

**Files:**
- Create: `src/clipforge/smoke.py`
- Rewrite: `src/clipforge/app.py`
- Test: `tests/test_smoke_check.py`, `tests/test_app.py` (extend)

**Interfaces:**
- Consumes:
  - Task 6: `runtime.DictKV`, `ModalVolume`, `FunctionSpawner`, `UnavailableStages`, `telegram_sender`, `build_deps`;
  - Task 5: `api.main.ApiContext`, `create_app`;
  - Task 7: `cli.wait`;
  - `stages.runner.PipelineStages.from_settings`;
  - `pipeline.steps`: `Step`, `STEP_TIMEOUT_S`, `MAX_ATTEMPTS`, `dispatch`, `sweep`;
  - `service.create_job`, `get_job_view`; `config.get_settings`.
- Produces:
  - Modal functions `ingest_step(job_id)`, `transcribe_step(job_id)`, `highlights_step(job_id)`, `clip_step(job_id, clip_id)`, `package_step(job_id)`, `sweeper()` and `web()`;
  - local entrypoints `doctor(audio="", skip_gpu=False)` (unchanged) and `smoke(timeout_s=900)`;
  - `smoke.smoke_input(source_path) -> JobInput`, `smoke.check_smoke(view, meta) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_smoke_check.py`:

```python
"""What the Modal smoke job must deliver, checked against metadata.json."""

from __future__ import annotations

from datetime import UTC, datetime

from clipforge.models import (
    CostSummary,
    JobError,
    JobMetadata,
    JobStatus,
    JobView,
    StageCost,
    StageName,
)
from clipforge.smoke import check_smoke, smoke_input
from tests.test_models import ALL_SAMPLES

AT = datetime(2026, 9, 23, tzinfo=UTC)


def _meta(**probe: object) -> JobMetadata:
    meta = next(m for m in ALL_SAMPLES if isinstance(m, JobMetadata))
    clip = meta.clips[0]
    good = {
        "width": 1080,
        "height": 1920,
        "duration_s": 7.0,
        "n_video_streams": 1,
        "n_audio_streams": 1,
        "size_bytes": 2_000_000,
    }
    clip = clip.model_copy(update={"probe": clip.probe.model_copy(update={**good, **probe})})
    cost = CostSummary(
        stages=[StageCost(stage=StageName.TRANSCRIBE, gpu_s=4.0, usd_estimate=0.001)]
    )
    return meta.model_copy(update={"clips": [clip], "cost": cost})


def _view(status: JobStatus, error: JobError | None = None) -> JobView:
    return JobView(
        job_id="J",
        status=status,
        stage=StageName.PACKAGE,
        clips=[],
        cost=CostSummary(),
        created_at=AT,
        updated_at=AT,
        error=error,
    )


def test_smoke_input_is_one_short_clip() -> None:
    job_input = smoke_input("smoke/abc/talking_head_10s.mp4")
    assert job_input.source_path == "smoke/abc/talking_head_10s.mp4"
    assert (job_input.options.n, job_input.options.min_len, job_input.options.max_len) == (
        1,
        5.0,
        9.0,
    )


def test_good_job_passes() -> None:
    assert check_smoke(_view(JobStatus.DONE), _meta()) == []


def test_failed_job_reports_stage_and_reason() -> None:
    error = JobError(stage=StageName.HIGHLIGHTS, error_type="permanent", message="no clips")
    assert check_smoke(_view(JobStatus.FAILED, error), None) == [
        "job failed at highlights: no clips"
    ]


def test_bad_clip_properties_are_listed() -> None:
    problems = check_smoke(_view(JobStatus.DONE), _meta(width=720, duration_s=12.0))
    assert any("1080x1920" in p for p in problems)
    assert any("duration" in p for p in problems)


def test_missing_gpu_cost_is_a_problem() -> None:
    meta = _meta().model_copy(update={"cost": CostSummary()})
    assert any("GPU" in p for p in check_smoke(_view(JobStatus.DONE), meta))
```

Append to `tests/test_app.py`:

```python
import re
from pathlib import Path

import clipforge


def test_step_functions_and_endpoints_exist() -> None:
    for name in (
        "ingest_step",
        "transcribe_step",
        "highlights_step",
        "clip_step",
        "package_step",
        "sweeper",
        "web",
        "smoke",
        "doctor",
    ):
        assert hasattr(app, name), name


def test_spawner_covers_every_step() -> None:
    # FunctionSpawner raises ValueError if a step has no function; building needs no Modal call.
    assert app._spawner() is not None


def test_container_env_points_at_the_image_dirs() -> None:
    assert app.CONTAINER_ENV["JOBS_ROOT"] == "/jobs"
    assert app.CONTAINER_ENV["PROMPTS_DIR"] == app.PROMPTS_MOUNT
    assert app.CONTAINER_ENV["FONTS_DIR"] == app.FONTS_MOUNT
    assert (app.REPO_ROOT / "prompts" / "metadata.json").is_file()
    assert (app.REPO_ROOT / "assets" / "fonts" / "Anton-Regular.ttf").is_file()


def test_only_app_imports_modal() -> None:
    src = Path(clipforge.__file__).parent
    pattern = re.compile(r"^\s*(import modal|from modal)", re.MULTILINE)
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if path.name != "app.py" and pattern.search(path.read_text())
    ]
    assert offenders == []
```

Move the new imports to the top of `tests/test_app.py` (ruff's isort rules).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_smoke_check.py tests/test_app.py`
Expected: FAIL. `test_smoke_check.py` fails on `No module named 'clipforge.smoke'`; in `test_app.py`, the new tests fail on the missing attributes (`ingest_step`, `_spawner`, `CONTAINER_ENV`), while `test_only_app_imports_modal` already passes.

- [ ] **Step 3: Write `src/clipforge/smoke.py`**

```python
"""The Modal smoke test (spec §6): one real job on the 10 s fixture, checked end to end.

`app.py::smoke` uploads the fixture, runs the job on Modal and calls `check_smoke`. The checks
live here, Modal-free, so they are unit-tested.
"""

from __future__ import annotations

from clipforge.models import ClipOptions, JobInput, JobMetadata, JobStatus, JobView, Permission

FIXTURE = "tests/fixtures/talking_head_10s.mp4"
MIN_LEN, MAX_LEN = 5.0, 9.0
TOLERANCE_S = 0.1
TELEGRAM_LIMIT_BYTES = 50_000_000


def smoke_input(source_path: str) -> JobInput:
    return JobInput(
        source_path=source_path,
        permission=Permission.OWN,
        source_label="smoke",
        options=ClipOptions(n=1, min_len=MIN_LEN, max_len=MAX_LEN),
    )


def check_smoke(view: JobView, meta: JobMetadata | None) -> list[str]:
    """Problems with a finished smoke job; an empty list means it passed."""
    if view.status is not JobStatus.DONE:
        if view.error is not None:
            return [f"job {view.status} at {view.error.stage}: {view.error.message}"]
        return [f"job ended {view.status} at {view.stage}"]
    if meta is None:
        return ["metadata.json is missing"]
    problems: list[str] = []
    if len(meta.clips) != 1:
        problems.append(f"expected 1 clip, got {len(meta.clips)}")
    for clip in meta.clips:
        probe = clip.probe
        if (probe.width, probe.height) != (1080, 1920):
            problems.append(f"{clip.clip_id}: {probe.width}x{probe.height}, expected 1080x1920")
        if not MIN_LEN - TOLERANCE_S <= probe.duration_s <= MAX_LEN + TOLERANCE_S:
            problems.append(f"{clip.clip_id}: duration {probe.duration_s:.2f} s outside 5-9 s")
        if (probe.n_video_streams, probe.n_audio_streams) != (1, 1):
            streams = f"{probe.n_video_streams}v/{probe.n_audio_streams}a"
            problems.append(f"{clip.clip_id}: streams {streams}, expected 1v/1a")
        if probe.size_bytes >= TELEGRAM_LIMIT_BYTES:
            problems.append(f"{clip.clip_id}: {probe.size_bytes} bytes, over Telegram's 50 MB")
    if not any(stage.gpu_s > 0 for stage in meta.cost.stages):
        problems.append("no GPU seconds recorded (transcribe cost missing)")
    return problems
```

- [ ] **Step 4: Rewrite `src/clipforge/app.py`**

```python
"""Modal app (ADR-9): images, the pipeline step functions, the web endpoint, the sweeper cron
and local entrypoints. The only module that imports modal; each function is one call into the
Modal-free code.

    uv run modal run src/clipforge/app.py::doctor    # local + GPU environment checks
    uv run modal run src/clipforge/app.py::smoke     # one real job on the 10 s fixture (~$0.01)
    uv run modal deploy src/clipforge/app.py         # deploy the API, webhook and pipeline
"""

from __future__ import annotations

import functools
import os
import time
import uuid
from pathlib import Path

import modal
from fastapi import FastAPI

from clipforge import runtime
from clipforge.api.main import ApiContext, create_app
from clipforge.config import get_settings
from clipforge.pipeline.steps import MAX_ATTEMPTS, STEP_TIMEOUT_S, Deps, Step, dispatch, sweep

APP_NAME = "clipforge"
# Baked into the GPU image at build time. Keep in sync with Settings.whisper_model.
WHISPER_MODEL = "large-v3-turbo"
MODEL_DIR = "/models"
GPU = "L4"
JOBS_ROOT = "/jobs"
REPO_ROOT = Path(__file__).resolve().parents[2]  # only meaningful locally (image build)
PROMPTS_MOUNT = "/app/prompts"
FONTS_MOUNT = "/app/assets/fonts"
CONTAINER_ENV = {
    "JOBS_ROOT": JOBS_ROOT,
    "PROMPTS_DIR": PROMPTS_MOUNT,
    "FONTS_DIR": FONTS_MOUNT,
    "GIT_SHA": os.environ.get("GIT_SHA", ""),  # set by the CI deploy; empty means unknown
}

app = modal.App(APP_NAME)


def _download_whisper_model() -> None:
    from faster_whisper import download_model

    download_model(WHISPER_MODEL, output_dir=f"{MODEL_DIR}/{WHISPER_MODEL}")


def _with_app_files(image: modal.Image) -> modal.Image:
    return (
        image.env(CONTAINER_ENV)
        .add_local_dir(REPO_ROOT / "prompts", PROMPTS_MOUNT)
        .add_local_dir(REPO_ROOT / "assets" / "fonts", FONTS_MOUNT)
        .add_local_python_source("clipforge")
    )


# CPU steps and the web endpoint: ffmpeg (with libass) + the locked project dependencies.
base_image = _with_app_files(
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "fontconfig")
    .uv_sync(str(REPO_ROOT))
)

# CUDA 12 + cuDNN 9, as required by CTranslate2 4.x (ADR-11).
whisper_image = _with_app_files(
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_sync(str(REPO_ROOT))
    .uv_pip_install("faster-whisper==1.2.1", "ctranslate2==4.8.2")
    .run_function(_download_whisper_model)
)

jobs_volume = modal.Volume.from_name("clipforge-jobs", create_if_missing=True)
job_state = modal.Dict.from_name("clipforge-job-state", create_if_missing=True)
secrets = modal.Secret.from_name("clipforge-secrets")

RETRIES = modal.Retries(max_retries=MAX_ATTEMPTS - 1, backoff_coefficient=2.0, initial_delay=5.0)


def _spawner() -> runtime.FunctionSpawner:
    return runtime.FunctionSpawner(
        {
            Step.INGEST: ingest_step,
            Step.TRANSCRIBE: transcribe_step,
            Step.HIGHLIGHTS: highlights_step,
            Step.CLIP: clip_step,
            Step.PACKAGE: package_step,
        }
    )


@functools.cache
def _step_deps() -> Deps:
    """One per container: the real stages (LLM client, prompt, transcriber) are built once."""
    from clipforge.stages.runner import PipelineStages

    settings = get_settings()
    return runtime.build_deps(
        settings,
        kv=runtime.DictKV(job_state),
        volume=runtime.ModalVolume(jobs_volume),
        spawner=_spawner(),
        stages=PipelineStages.from_settings(settings),
        sender=runtime.telegram_sender(settings),
    )


@functools.cache
def _service_deps() -> Deps:
    """For the web endpoint and the sweeper: jobs are created, read and resumed, never run."""
    settings = get_settings()
    return runtime.build_deps(
        settings,
        kv=runtime.DictKV(job_state),
        volume=runtime.ModalVolume(jobs_volume),
        spawner=_spawner(),
        stages=runtime.UnavailableStages(),
        sender=runtime.telegram_sender(settings),
    )


@app.function(
    image=base_image,
    cpu=2.0,
    memory=4096,
    timeout=STEP_TIMEOUT_S[Step.INGEST],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def ingest_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.INGEST, job_id)


@app.function(
    image=whisper_image,
    gpu=GPU,
    timeout=STEP_TIMEOUT_S[Step.TRANSCRIBE],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def transcribe_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.TRANSCRIBE, job_id)


@app.function(
    image=base_image,
    cpu=1.0,
    timeout=STEP_TIMEOUT_S[Step.HIGHLIGHTS],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def highlights_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.HIGHLIGHTS, job_id)


@app.function(
    image=base_image,
    cpu=4.0,
    memory=4096,
    timeout=STEP_TIMEOUT_S[Step.CLIP],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def clip_step(job_id: str, clip_id: str) -> None:
    dispatch(_step_deps(), Step.CLIP, job_id, clip_id)


@app.function(
    image=base_image,
    cpu=1.0,
    timeout=STEP_TIMEOUT_S[Step.PACKAGE],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def package_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.PACKAGE, job_id)


@app.function(
    image=base_image,
    cpu=0.25,
    timeout=120,
    schedule=modal.Cron("*/10 * * * *"),
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def sweeper() -> None:
    failed = sweep(_service_deps())
    if failed:
        print(f"sweeper: failed {len(failed)} stalled job(s): {', '.join(failed)}")


@app.function(
    image=base_image,
    cpu=0.5,
    timeout=600,  # long zip downloads; the webhook itself answers in seconds
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
@modal.asgi_app()
def web() -> FastAPI:
    settings = get_settings()
    sender = runtime.telegram_sender(settings)
    return create_app(ApiContext(settings=settings, deps=_service_deps, sender=lambda: sender))


@app.function(image=whisper_image, gpu=GPU, timeout=600)
def gpu_doctor(audio_wav: bytes) -> dict[str, object]:
    ...  # unchanged from the current app.py: copy the existing body verbatim


@app.local_entrypoint()
def doctor(audio: str = "", skip_gpu: bool = False) -> None:
    ...  # unchanged from the current app.py: copy the existing body verbatim


@app.local_entrypoint()
def smoke(timeout_s: int = 900) -> None:
    """One real job on the 10 s fixture (n=1, len 5-9) on Modal; exits non-zero on failure."""
    from clipforge.cli import wait
    from clipforge.jobs import DictJobStore
    from clipforge.models import JobMetadata
    from clipforge.pipeline.deps import NullVolume
    from clipforge.service import create_job, get_job_view
    from clipforge.smoke import FIXTURE, check_smoke, smoke_input

    fixture = REPO_ROOT / FIXTURE
    rel = f"smoke/{uuid.uuid4().hex[:8]}/{fixture.name}"
    with jobs_volume.batch_upload() as batch:
        batch.put_file(str(fixture), f"/{rel}")

    deps = Deps(
        store=DictJobStore(runtime.DictKV(job_state)),
        volume=NullVolume(),  # the job runs in Modal containers; nothing is read locally
        spawner=_spawner(),
        stages=runtime.UnavailableStages(),
        root=Path(JOBS_ROOT),
    )
    started = time.monotonic()
    job = create_job(deps, smoke_input(rel))
    print(f"smoke job {job.job_id}")
    view = wait(lambda: get_job_view(deps.store, deps.root, job.job_id), timeout_s=timeout_s)

    meta = None
    if view.status.value == "done":
        raw = b"".join(jobs_volume.read_file(f"{job.job_id}/output/metadata.json"))
        meta = JobMetadata.model_validate_json(raw)
    problems = check_smoke(view, meta)
    if problems:
        raise SystemExit("smoke FAILED:\n  " + "\n  ".join(problems))
    elapsed = time.monotonic() - started
    print(f"smoke OK · {elapsed:.0f} s · ${view.cost.total_usd:.4f} · {meta.clips[0].title!r}")
```

Copy the `gpu_doctor` and `doctor` bodies exactly as they are in the current `app.py`, including the `import time`/`Path` usage they need. The `...` above is not literal code to keep. `meta` is not None on the success path; if mypy disagrees, add `assert meta is not None` before the last print.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_smoke_check.py tests/test_app.py`
Expected: PASS. If importing `app` fails because `Image.uv_sync` checks the project path at definition time, `REPO_ROOT` (the repo root, locally) is correct. The failure would only appear inside a container, and that is exercised in Task 9.

- [ ] **Step 6: Lint, types, full fast suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 7: Check that Modal accepts the app definition without running anything**

Run: `uv run modal run src/clipforge/app.py::doctor --skip-gpu`
Expected: builds `base_image` (first time: a few minutes for `apt ffmpeg` + `uv sync`) and `whisper_image`, prints the local ffmpeg checks, and exits 0. This only runs the local half of `doctor`, but `modal run` builds every image the app declares. The run fails if `clipforge-secrets` does not exist; see Task 9 Step 1 for creating it.

- [ ] **Step 8: Checkpoint (the user commits)**

Files: `src/clipforge/smoke.py`, `src/clipforge/app.py`, `tests/test_smoke_check.py`, `tests/test_app.py`.

---

### Task 9: Smoke on Modal, CI, docs and the go-live steps

**Files:**
- Modify: `.github/workflows/ci.yml`, `.github/workflows/manual.yml`
- Modify: `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `ROADMAP.md`, `.env.example`

**Interfaces:**
- Consumes: everything above.
- Produces: a passing Modal smoke run, and docs that match the code.

- [ ] **Step 1: Check the secret exists (names only, never values)**

Run: `uv run modal secret list`
Expected: a row named `clipforge-secrets`. If it is missing, **stop and ask the user** to create it with their own values; never read or type their keys. Give them this command:

```bash
uv run modal secret create clipforge-secrets \
  ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... \
  TELEGRAM_ALLOWED_USER_IDS=... API_TOKEN=... DOWNLOAD_SIGNING_KEY=... API_URL=...
```

The smoke run needs only `ANTHROPIC_API_KEY`. `API_URL` is known only after the first deploy (Step 7), so it can be added then with `modal secret create --force`.

- [ ] **Step 2: Run the smoke job on Modal (about $0.01; authorized by spec §6)**

Run: `uv run modal run src/clipforge/app.py::smoke 2>&1 | tee <workspace>/smoke.log | tail -30`
Expected: progress lines (`queued`, `running · ingest`, `running · transcribe`, `running · highlights`, `running · render … clips 0/1`, `running · package`, `done · package · clips 1/1`), then `smoke OK · <s> s · $0.00xx · '<title>'`. Wall time is typically 2 to 4 minutes, most of it cold starts.

If it fails, read the Modal logs (`uv run modal app logs clipforge` for the ephemeral run's app id printed at the top, or the dashboard) and use superpowers:systematic-debugging. Likely failures and their fixes:
- `Image.uv_sync` path or `--no-dev` issues: pass `groups=[]` or adjust `uv_project_dir`; record a ruling.
- `debian_slim` ffmpeg (5.1) missing a filter the render uses: switch the apt source or install a static ffmpeg build; record a ruling.
- `PROMPTS_DIR`/`FONTS_DIR` not found: check `CONTAINER_ENV` against `Settings` field names.
- Haiku finding no 5 to 9 s clip in 10 s of speech (the job fails at highlights with "no candidates"): run once more. If it repeats, stop and report it to the user rather than weakening the check (`ClipOptions.min_len` can't go below 5 anyway).

- [ ] **Step 3: Update the CI workflows**

In `.github/workflows/ci.yml`, job `deploy`, extend `env:`:

```yaml
      GIT_SHA: ${{ github.sha }}
```

In `.github/workflows/manual.yml`, replace the trailing comment line with:

```yaml
      - name: Smoke job on Modal (10 s fixture, about $0.01)
        run: uv run modal run src/clipforge/app.py::smoke
```

- [ ] **Step 4: Update the docs**

- `README.md`:
  - "Telegram usage" becomes `/clip <link> [n=5] [len=30-60] [lang=auto] [perm=own] [credit="..."]`, plus: a bare link works; a video up to 20 MB works, with options in its caption; `/status <id>`; `/resume <id>`. Remove `style=`, which isn't supported until Phase 2.
  - "Quickstart" gains the go-live steps in order: `modal secret create clipforge-secrets …` (the Step 1 command), `modal deploy`, put the printed `web` URL into `API_URL` in both `.env` and the secret (`modal secret create --force`), `uv run clipforge set-webhook`, then send a link to the bot.
- `CLAUDE.md`, "Commands":
  - add `uv run modal run src/clipforge/app.py::smoke   # one real job on Modal (~$0.01)` and `uv run clipforge set-webhook   # point Telegram at the deployed API`;
  - add `status <id>` / `resume <id>` next to `clipforge run`.
  - In "Layout", add `runtime.py  # Modal adapters (DictKV, ModalVolume, FunctionSpawner) + build_deps`, `smoke.py`, `cli.py`, `links.py` (signed zip links), and `api/main.py`, `bot/` (telegram, messages, notifier, commands, webhook).
- `docs/ARCHITECTURE.md`:
  - under Security, note that API docs routes are disabled and that job ids are validated before any path is built;
  - under Overview, note that `JobView.download_url` is filled in by the API;
  - add one line to the Modal functions description saying images install from `uv.lock` (`uv_sync`).
- `.env.example`: after `API_URL=`, add a comment line: `# The web URL printed by modal deploy, e.g. https://<workspace>--clipforge-web.modal.run`.
- `ROADMAP.md`: tick `transcribe` (the smoke run transcribed on the L4), `Step chain on Modal`, `Job API on Modal`, `CLI` and `Telegram bot`. Leave the Phase 1 exit criteria unticked until the user has run a 30-minute source.

- [ ] **Step 5: Final local check**

Run: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 6: Checkpoint (the user commits)**

Files: `.github/workflows/ci.yml`, `.github/workflows/manual.yml`, `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `.env.example`, `ROADMAP.md`.

- [ ] **Step 7: Go live (the user's call: deploying publishes a public endpoint)**

**Stop and ask the user** before running any of these, because each one is outward-facing:
1. `uv run modal deploy src/clipforge/app.py` (prints the `web` URL). Once the user pushes to `main`, CI does this on every merge.
2. Add `API_URL=<web URL>` to `.env` and to `clipforge-secrets`.
3. `uv run clipforge set-webhook`
4. From the allowed Telegram account, send a direct link to the bot. Expected: "Got it, job …", then the clips as videos, then `k of n clips · $… · <link>`, and the link downloads the zip.
5. `uv run clipforge run --input <direct link to a 30-min source>`, timed against the Phase 1 exit criterion (under 10 minutes, cost logged).

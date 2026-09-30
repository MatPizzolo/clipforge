# Plan B: Posting queue core — Implementation Plan

> **Status (2026-09-29): done.** All 5 tasks plus the final-review fix pass (4 Important findings fixed; the Critical one, Dict expiry, became ADR-24 and plan C Task 6; 7 minors deferred). Ledger: `.superpowers/sdd/2026-09-28-b-posting-core/progress.md`. Not deployed yet.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a channel job finishes, its clips join a posting queue in the Modal Dict, with no duplicate moments across re-cuts. The queue knows every clip's state on every platform, picks the next clip to post, and reports a per-channel overview through `GET /posting` and `uv run clipforge status`.

**Architecture:** A new Modal-free package, `src/clipforge/posting/`:
- `store.py` maps the ADR-23 Dict keys to typed reads and writes, one writer per key.
- `queue.py` holds the pure rules: derived status, eligibility, pick order, overlap and the pause count.
- `enqueue.py` turns a finished job's rendered clips into `PostItem`s.
- `slots.py` turns the posting settings into slot times.

`package_step` calls enqueue with the same never-fail guard the notifier uses. `service.py` adds `posting_overview` and `rebuild_posting`, and the API and CLI render them. Plan C builds the Telegram assistant on top.

**Tech Stack:** Python 3.12 (`zoneinfo`), pydantic v2, pydantic-settings, FastAPI, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-posting-assistant-design.md` §4, §5, §9, §10 (ADR-23). **Runs after Plan A** (it needs `JobInput.channel` and `ChannelRef`).

**Git:** the owner runs every git command. "Checkpoint" steps list the changed files; don't run git.

**The code moves.** Another session edits this repo at the same time. Read each file before changing it, keep unrelated current code, and report what you adapted. Check that ADR-23 is still free in `docs/DECISIONS.md`, and take the next free number if it isn't.

## Global Constraints

- `posting/` never imports `modal`, `telegram` or `clipforge.stages` (ADR-9). Only `app.py` imports modal.
- Dict keys, exactly as in the spec: `post:<job_id>:<clip_id>`, `post:<ref>:sent:<n>`, `post:<ref>:posted:<tiktok|instagram|youtube>`, `post:<ref>:verdict`, `post:<ref>:unavailable`, `posting:slot:<iso>`, `posting:paused`, `posting:reminded:<iso>`. Here `<ref>` is `<job_id>:<clip_id>`. Values are JSON from `model_dump_json()`, or `"1"` for flags and claims.
- Rules: same moment = same `source_hash` and time IoU > 0.5 against a non-rejected item; skip return = 24 h; fresh bonus = +0.05 if the episode finished ≤ 7 days ago; pause after 2 unanswered sends; slot window = 30 min.
- Enqueue never fails or retries a pipeline step: catch, log with `log.exception`, continue.
- Settings defaults: `POSTING_CHAT_ID` unset (posting off), `POSTING_TIMEZONE=America/New_York`, `POSTING_SLOTS=08:00,10:30,13:00,16:00,19:00,21:30`, `POSTING_HASHTAGS=` (empty). `POSTING_CHAT_ID` must be one of `TELEGRAM_ALLOWED_USER_IDS`.
- All datetimes are timezone-aware. "Now" is passed in; only `app.py`, the API and the CLI call `utcnow()`.
- Before every checkpoint: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.

## Review Focus

1. **A re-cut of an episode that's already queued.** Its overlapping moments are not added again; a moment that was rejected can come back through a re-cut. Test: `test_enqueue_skips_overlapping_moments` (Task 3).
2. **Enqueue blowing up** (a bad record in the Dict, a bug). The job still ends `done` and its notifier still runs. Test: `test_enqueue_failure_never_fails_the_job` (Task 4).
3. **A skipped clip.** It isn't eligible for 24 h, then comes back; a clip that was re-sent after a skip counts as sent again. Test: `test_skip_returns_after_24h_and_resend_counts` (Task 2).
4. **Old records without the new keys** (jobs finished before this plan). `rebuild` queues them once and is safe to repeat. Test: `test_rebuild_queues_old_channel_jobs_once` (Task 4).
5. **A DST change day.** Slot times are wall-clock times in the posting zone, and the next slot is correct across the switch. Test: `test_slots_follow_wall_clock_across_dst` (Task 1).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/clipforge/models.py` | + `Platform`, `PostStatus`, `RejectReason`, `PostItem`, `PostSend`, `PostVerdict`, `PostRecord`, `ChannelProgress`, `PostingOverview` (Task 1) |
| `src/clipforge/config.py` | + posting settings and validators (Task 1) |
| `src/clipforge/posting/__init__.py`, `posting/slots.py` | Slot times (Task 1) |
| `src/clipforge/pipeline/deps.py`, `src/clipforge/runtime.py` | + `KV.items()` (Task 2) |
| `src/clipforge/posting/store.py` | `PostingStore` over KV (Task 2) |
| `src/clipforge/posting/queue.py` | `status`, `eligible`, `pick_next`, `unanswered`, `overlaps` (Task 2) |
| `src/clipforge/posting/enqueue.py` | `items_for`, `enqueue`, `enqueue_job` (Task 3) |
| `src/clipforge/pipeline/steps.py` | Enqueue after package (Task 4) |
| `src/clipforge/service.py` | `posting_overview`, `rebuild_posting` (Task 4) |
| `src/clipforge/bot/messages.py` | `posting_overview_text` (Task 5) |
| `src/clipforge/api/main.py`, `src/clipforge/cli.py` | `GET /posting`, `POST /posting/rebuild`; `clipforge status [--rebuild]` (Task 5) |
| `tests/posting/__init__.py`, `tests/posting/builders.py`, `tests/posting/test_*.py`, `tests/test_config.py`, `tests/test_runtime.py`, `tests/pipeline/test_posting_chain.py`, `tests/test_service.py`, `tests/api/test_api.py`, `tests/test_cli.py` | Tests |
| `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `.env.example` | ADR-23, docs (Task 5) |

---

### Task 1: Contracts, settings, slot times

**Files:**
- Modify: `src/clipforge/models.py`, `src/clipforge/config.py`, `.env.example`
- Create: `src/clipforge/posting/__init__.py`, `src/clipforge/posting/slots.py`
- Create: `tests/posting/__init__.py` (empty), `tests/posting/builders.py`, `tests/posting/test_slots.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: the models below; `Settings.posting_chat_id: int | None`, `.posting_timezone: str`, `.posting_slots: list[str]`, `.posting_hashtags: list[str]`; `slots.SLOT_WINDOW = timedelta(minutes=30)`; `slots.day_slots(settings, day: date) -> list[datetime]`; `slots.current_slot(settings, now) -> datetime | None`; `slots.next_slot(settings, now) -> datetime`; builders `item()`, `send()`, `record()`, `T0`.

- [ ] **Step 1: Write the failing tests**

`tests/posting/builders.py`:

```python
"""Builders for posting tests."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from clipforge.models import ChannelRef, Platform, PostItem, PostRecord, PostSend, PostVerdict

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
JOB = "20260928-aaaaaaaa-0001"


def item(
    clip_id: str = "clip_01",
    *,
    job_id: str = JOB,
    source_hash: str = "a" * 64,
    start: float = 0.0,
    end: float = 30.0,
    score: float = 0.85,
    channel: str = "billy-garton",
    name: str = "Billy Garton Jr.",
    finished_at: datetime = T0,
    title: str = "A title",
    hook: str = "A hook.",
    episode: str = "ep01",
) -> PostItem:
    return PostItem(
        job_id=job_id, clip_id=clip_id, channel=ChannelRef(slug=channel, name=name),
        source_hash=source_hash, start=start, end=end, score=score, title=title, hook=hook,
        video_path=f"cache/clip/{clip_id}/clip.mp4", episode=episode,
        episode_finished_at=finished_at, queued_at=finished_at,
    )  # fmt: skip


def send(n: int = 1, at: datetime = T0, message_id: int = 100) -> PostSend:
    return PostSend(n=n, at=at, slot=None, message_id=message_id, video_message_id=message_id - 1)


def record(
    it: PostItem,
    *,
    sends: Iterable[PostSend] = (),
    posted: Iterable[Platform] = (),
    verdict: PostVerdict | None = None,
    unavailable: bool = False,
) -> PostRecord:
    return PostRecord(
        item=it, sends=list(sends), posted={p: T0 for p in posted}, verdict=verdict,
        unavailable=unavailable,
    )  # fmt: skip
```

`tests/posting/test_slots.py`:

```python
"""Slot times: wall-clock times in the posting time zone."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from clipforge.posting.slots import current_slot, day_slots, next_slot
from tests.bot.fakes import make_settings

NY = ZoneInfo("America/New_York")


def _settings(tmp_path: Path, **kw: object):  # type: ignore[no-untyped-def]
    return make_settings(tmp_path, posting_slots=["08:00", "12:00", "18:00"], **kw)


def test_day_slots(tmp_path: Path) -> None:
    slots = day_slots(_settings(tmp_path), date(2026, 9, 29))
    assert [s.strftime("%H:%M") for s in slots] == ["08:00", "12:00", "18:00"]
    assert all(s.tzinfo == NY for s in slots)


def test_current_slot_only_inside_the_window(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert current_slot(s, datetime(2026, 9, 29, 12, 29, tzinfo=NY)) == datetime(
        2026, 9, 29, 12, 0, tzinfo=NY
    )
    assert current_slot(s, datetime(2026, 9, 29, 12, 31, tzinfo=NY)) is None  # missed: dropped
    assert current_slot(s, datetime(2026, 9, 29, 7, 59, tzinfo=NY)) is None


def test_next_slot_rolls_to_tomorrow(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert next_slot(s, datetime(2026, 9, 29, 18, 0, tzinfo=NY)) == datetime(
        2026, 9, 30, 8, 0, tzinfo=NY
    )


def test_slots_follow_wall_clock_across_dst(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    before, after = day_slots(s, date(2026, 10, 31)), day_slots(s, date(2026, 11, 1))
    assert before[0].utcoffset() != after[0].utcoffset()  # EDT -> EST
    assert after[0].strftime("%H:%M") == "08:00"
```

Append to `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from tests.bot.fakes import ALLOWED_USER, make_settings


def test_posting_settings_parse_env_strings(tmp_path: Path) -> None:
    s = make_settings(
        tmp_path, posting_chat_id=ALLOWED_USER, posting_slots="09:00, 18:30",
        posting_hashtags="mindset,growth", posting_timezone="Europe/Madrid",
    )  # fmt: skip
    assert s.posting_slots == ["09:00", "18:30"]
    assert s.posting_hashtags == ["mindset", "growth"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"posting_timezone": "Mars/Olympus"},
        {"posting_slots": "9am"},
        {"posting_slots": "18:00,09:00"},
        {"posting_slots": ""},
        {"posting_hashtags": "#mindset"},
        {"posting_chat_id": 999},  # not an allowed user
    ],
)
def test_bad_posting_settings(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, **overrides)
```

(`make_settings` sets `telegram_allowed_user_ids=[ALLOWED_USER]`. If `tests/test_config.py` already imports `Path`, don't import it twice.)

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_slots.py tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: clipforge.posting`, and unknown settings fields).

- [ ] **Step 3: Implement**

`models.py`, after the channel contracts from Plan A:

```python
# ---- posting queue (Modal Dict; ADR-23) ---------------------------------------------------


class Platform(StrEnum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"


class PostStatus(StrEnum):
    """Derived from a clip's keys, never stored (spec §4)."""

    QUEUED = "queued"
    SENT = "sent"  # sent to the phone, no tap yet
    PARTLY_POSTED = "partly_posted"
    POSTED = "posted"  # all three platforms
    SKIPPED = "skipped"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"  # video missing from the Volume


class RejectReason(StrEnum):
    BORING = "boring"
    BAD_CUT = "bad_cut"
    BAD_CROP = "bad_crop"
    CAPTIONS = "captions"
    OTHER = "other"


class PostItem(Contract):
    """`post:<job_id>:<clip_id>`: a clip waiting to be posted, written once at enqueue."""

    job_id: str
    clip_id: str
    channel: ChannelRef
    source_hash: str
    start: float  # source time
    end: float
    score: float
    title: str
    hook: str
    video_path: str  # rendered clip, relative to JOBS_ROOT
    episode: str  # JobInput.source_label, or the job id
    episode_finished_at: datetime
    queued_at: datetime

    @property
    def ref(self) -> str:
        return f"{self.job_id}:{self.clip_id}"


class PostSend(Contract):
    """`post:<ref>:sent:<n>`: one delivery to the phone (n = 1, then 2 after a skip...)."""

    n: int = Field(ge=1)
    at: datetime
    slot: datetime | None  # None for /next and skip
    message_id: int  # the text message with the buttons
    video_message_id: int


class PostVerdict(Contract):
    """`post:<ref>:verdict`."""

    kind: Literal["skipped", "rejected"]
    at: datetime
    reason: RejectReason | None = None


class PostRecord(Contract):
    """Everything the Dict holds for one clip (read model; not stored as one key)."""

    item: PostItem
    sends: list[PostSend] = Field(default_factory=list)  # ordered by n
    posted: dict[Platform, datetime] = Field(default_factory=dict)
    verdict: PostVerdict | None = None
    unavailable: bool = False


class ChannelProgress(Contract):
    slug: str
    name: str
    episodes_clipped: int = 0
    episodes_clipping: int = 0
    episodes_failed: int = 0
    counts: dict[PostStatus, int] = Field(default_factory=dict)


class PostingOverview(Contract):
    """What `/status`, `GET /posting` and `clipforge status` show (spec §9)."""

    enabled: bool  # POSTING_CHAT_ID is set
    paused: bool
    channels: list[ChannelProgress]
    waiting: int  # queued + skipped: clips that will still be sent
    days_left: int
    per_day: int
    next_slot: datetime | None
```

`config.py`: add `import re` and `from zoneinfo import ZoneInfo, ZoneInfoNotFoundError`, plus `model_validator` to the pydantic import. Add `from typing import Self` if the file doesn't import it. Fields, after the job defaults:

```python
    # Posting assistant (ADR-23): off until POSTING_CHAT_ID is set
    posting_chat_id: int | None = None
    posting_timezone: str = "America/New_York"  # the audience's time zone
    posting_slots: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]
    )
    posting_hashtags: Annotated[list[str], NoDecode] = []  # without "#"
```

Validators (next to the others):

```python
    @field_validator("posting_slots", "posting_hashtags", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("posting_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {value!r}") from exc
        return value

    @field_validator("posting_slots")
    @classmethod
    def _check_slots(cls, value: list[str]) -> list[str]:
        if not 1 <= len(value) <= 12:
            raise ValueError("between 1 and 12 posting slots")
        if any(not _SLOT.fullmatch(slot) for slot in value):
            raise ValueError("slots must be HH:MM, e.g. 08:00")
        if sorted(set(value)) != value:
            raise ValueError("slots must be unique and in order")
        return value

    @field_validator("posting_hashtags")
    @classmethod
    def _check_hashtags(cls, value: list[str]) -> list[str]:
        if any(not _HASHTAG.fullmatch(tag) for tag in value):
            raise ValueError("hashtags: letters, digits and _ only, without #")
        return value

    @model_validator(mode="after")
    def _check_posting_chat(self) -> Self:
        chat = self.posting_chat_id
        if chat is not None and chat not in self.telegram_allowed_user_ids:
            raise ValueError("POSTING_CHAT_ID must be one of TELEGRAM_ALLOWED_USER_IDS")
        return self
```

Module level in `config.py`: `_SLOT = re.compile(r"([01]\d|2[0-3]):[0-5]\d")` and `_HASHTAG = re.compile(r"\w+")`.

`.env.example`, add:

```
# Posting assistant (ADR-23): the bot sends clips here at each slot; unset = off
POSTING_CHAT_ID=
POSTING_TIMEZONE=America/New_York
POSTING_SLOTS=08:00,10:30,13:00,16:00,19:00,21:30
POSTING_HASHTAGS=
```

`src/clipforge/posting/__init__.py`:

```python
"""Posting queue (ADR-23): which clips go to the phone, when, and what happened to them.

Modal-free. State lives in the job Dict under `post:*` / `posting:*` keys (one writer each)."""
```

`src/clipforge/posting/slots.py`:

```python
"""Posting slots: wall-clock times in the audience's time zone (spec §6)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from clipforge.config import Settings

SLOT_WINDOW = timedelta(minutes=30)  # a slot missed by longer than this is dropped


def day_slots(settings: Settings, day: date) -> list[datetime]:
    zone = ZoneInfo(settings.posting_timezone)
    slots = []
    for text in settings.posting_slots:
        hour, minute = (int(part) for part in text.split(":"))
        slots.append(datetime.combine(day, time(hour, minute), tzinfo=zone))
    return slots


def current_slot(settings: Settings, now: datetime) -> datetime | None:
    """The latest slot at or before `now`, if it's at most SLOT_WINDOW old."""
    local = now.astimezone(ZoneInfo(settings.posting_timezone))
    for day in (local.date(), local.date() - timedelta(days=1)):
        past = [slot for slot in day_slots(settings, day) if slot <= now]
        if past:
            latest = past[-1]
            return latest if now - latest <= SLOT_WINDOW else None
    return None


def next_slot(settings: Settings, now: datetime) -> datetime:
    local = now.astimezone(ZoneInfo(settings.posting_timezone))
    for offset in range(2):
        for slot in day_slots(settings, local.date() + timedelta(days=offset)):
            if slot > now:
                return slot
    raise AssertionError("unreachable: there is at least one slot per day")
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting/test_slots.py tests/test_config.py tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/models.py`, `src/clipforge/config.py`, `.env.example`, `src/clipforge/posting/__init__.py`, `src/clipforge/posting/slots.py`, `tests/posting/__init__.py`, `tests/posting/builders.py`, `tests/posting/test_slots.py`, `tests/test_config.py`.

---

### Task 2: `KV.items()`, the store, the queue rules

**Files:**
- Modify: `src/clipforge/pipeline/deps.py` (`KV` protocol, `MemoryKV`), `src/clipforge/runtime.py` (`DictKV`)
- Create: `src/clipforge/posting/store.py`, `src/clipforge/posting/queue.py`
- Test: `tests/test_runtime.py`, `tests/posting/test_store.py`, `tests/posting/test_queue.py`

**Interfaces:**
- Consumes: the Task 1 models and builders.
- Produces:
  - `KV.items() -> Iterable[tuple[str, str]]`
  - `PostingStore(kv)` with:
    - `.add(item) -> bool` (set once)
    - `.get(ref) -> PostRecord | None`
    - `.records() -> list[PostRecord]`
    - `.add_send(ref, send) -> bool`
    - `.toggle_posted(ref, platform, at) -> bool` (returns the new state)
    - `.set_verdict(ref, verdict)`
    - `.set_reason(ref, reason) -> bool`
    - `.mark_unavailable(ref)`
    - `.claim_slot(slot: datetime) -> bool`, `.release_slot(slot)`
    - `.paused() -> bool`, `.set_paused(on: bool)`
    - `.claim_reminder(at: datetime) -> bool`
  - `queue.status(record) -> PostStatus`
  - `queue.eligible(record, now) -> bool`
  - `queue.pick_next(records, now) -> PostRecord | None`
  - `queue.unanswered(records) -> list[PostRecord]`
  - `queue.overlaps(item, records) -> bool`
  - Constants `SKIP_RETURN`, `FRESH_DAYS`, `FRESH_BONUS`, `PAUSE_AFTER`, `SAME_MOMENT_IOU`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_runtime.py`, and add `items()` to its `FakeModalDict` (`def items(self) -> Any: return iter(list(self.data.items()))`):

```python
def test_dict_kv_items() -> None:
    fake = FakeModalDict()
    kv = DictKV(fake)
    kv.put("a", "1")
    kv.put("b", "2")
    assert sorted(kv.items()) == [("a", "1"), ("b", "2")]
```

(Use the module's existing import of `DictKV`.) Also extend the existing MemoryKV test in `tests/pipeline/` if there is one; otherwise `test_store.py` below covers `MemoryKV.items()`.

`tests/posting/test_store.py`:

```python
"""PostingStore: the ADR-23 keys over the KV, one writer each."""

from __future__ import annotations

from datetime import timedelta

from clipforge.models import Platform, PostVerdict, RejectReason
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.store import PostingStore
from tests.posting.builders import T0, item, send


def test_add_is_set_once_and_records_roundtrip() -> None:
    kv = MemoryKV()
    store = PostingStore(kv)
    it = item()
    assert store.add(it) is True
    assert store.add(it.model_copy(update={"score": 0.1})) is False  # first write wins
    store.add_send(it.ref, send(1))
    store.toggle_posted(it.ref, Platform.TIKTOK, T0)
    kv.put("job:x", "{}")  # other keys in the Dict are ignored
    [rec] = store.records()
    assert rec.item == it and [s.n for s in rec.sends] == [1]
    assert set(rec.posted) == {Platform.TIKTOK}
    assert store.get(it.ref) == rec
    assert store.get("20260928-aaaaaaaa-0001:clip_99") is None


def test_toggle_posted_undoes() -> None:
    store = PostingStore(MemoryKV())
    it = item()
    store.add(it)
    assert store.toggle_posted(it.ref, Platform.YOUTUBE, T0) is True
    assert store.toggle_posted(it.ref, Platform.YOUTUBE, T0) is False
    assert store.get(it.ref).posted == {}  # type: ignore[union-attr]


def test_sends_are_ordered_and_set_once() -> None:
    store = PostingStore(MemoryKV())
    it = item()
    store.add(it)
    assert store.add_send(it.ref, send(2, T0 + timedelta(days=1))) is True
    assert store.add_send(it.ref, send(1)) is True
    assert store.add_send(it.ref, send(1)) is False
    assert [s.n for s in store.get(it.ref).sends] == [1, 2]  # type: ignore[union-attr]


def test_verdict_reason_and_flags() -> None:
    store = PostingStore(MemoryKV())
    it = item()
    store.add(it)
    assert store.set_reason(it.ref, RejectReason.BORING) is False  # not rejected yet
    store.set_verdict(it.ref, PostVerdict(kind="rejected", at=T0))
    assert store.set_reason(it.ref, RejectReason.BORING) is True
    store.mark_unavailable(it.ref)
    rec = store.get(it.ref)
    assert rec is not None and rec.verdict is not None
    assert rec.verdict.reason is RejectReason.BORING and rec.unavailable


def test_claims_and_pause() -> None:
    store = PostingStore(MemoryKV())
    assert store.claim_slot(T0) and not store.claim_slot(T0)
    store.release_slot(T0)
    assert store.claim_slot(T0)
    assert store.claim_reminder(T0) and not store.claim_reminder(T0)
    assert not store.paused()
    store.set_paused(True)
    assert store.paused()
    store.set_paused(False)
    assert not store.paused()
```

`tests/posting/test_queue.py`:

```python
"""Queue rules: derived status, eligibility, pick order, overlap, the pause count."""

from __future__ import annotations

from datetime import timedelta

from clipforge.models import Platform, PostStatus, PostVerdict
from clipforge.posting.queue import eligible, overlaps, pick_next, status, unanswered
from tests.posting.builders import T0, item, record, send

LATER = T0 + timedelta(hours=1)
OLD = T0 - timedelta(days=30)  # no fresh bonus


def test_status_branches() -> None:
    it = item()
    assert status(record(it)) is PostStatus.QUEUED
    assert status(record(it, sends=[send()])) is PostStatus.SENT
    assert status(record(it, sends=[send()], posted=[Platform.TIKTOK])) is PostStatus.PARTLY_POSTED
    assert status(record(it, posted=list(Platform))) is PostStatus.POSTED
    rejected = PostVerdict(kind="rejected", at=T0)
    assert status(record(it, posted=list(Platform), verdict=rejected)) is PostStatus.REJECTED
    assert status(record(it, unavailable=True)) is PostStatus.UNAVAILABLE


def test_skip_returns_after_24h_and_resend_counts() -> None:
    skipped = record(item(), sends=[send(1, T0)], verdict=PostVerdict(kind="skipped", at=LATER))
    assert status(skipped) is PostStatus.SKIPPED
    assert not eligible(skipped, LATER + timedelta(hours=23))
    assert eligible(skipped, LATER + timedelta(hours=24))
    resent = skipped.model_copy(update={"sends": [send(1, T0), send(2, LATER + timedelta(days=1))]})
    assert status(resent) is PostStatus.SENT
    assert unanswered([resent]) == [resent]


def test_unanswered_counts_only_untapped_sends() -> None:
    a = record(item("clip_01"), sends=[send()])
    b = record(item("clip_02"), sends=[send()], posted=[Platform.TIKTOK])
    c = record(item("clip_03"))
    assert unanswered([a, b, c]) == [a]


def _ids(rec: object) -> str:
    return rec.item.ref if rec is not None else "none"  # type: ignore[attr-defined]


def test_pick_prefers_other_video_then_other_channel() -> None:
    a1 = record(item("clip_01", score=0.9, finished_at=OLD), sends=[send(1, T0)])  # last sent
    a2 = record(item("clip_02", score=0.89, finished_at=OLD, start=100, end=130))
    b = record(item("clip_01", job_id="20260928-bbbbbbbb-0001", source_hash="b" * 64,
                    score=0.8, finished_at=OLD))  # fmt: skip
    assert _ids(pick_next([a1, a2, b], LATER)) == b.item.ref  # other video beats higher score
    c = record(item("clip_01", job_id="20260928-cccccccc-0001", source_hash="c" * 64,
                    channel="other", name="Other", score=0.7, finished_at=OLD))  # fmt: skip
    assert _ids(pick_next([a1, a2, b, c], LATER)) == c.item.ref  # other channel beats both


def test_pick_uses_fresh_bonus_and_skips_ineligible() -> None:
    old = record(item("clip_01", score=0.88, finished_at=OLD))
    new = record(item("clip_01", job_id="20260928-bbbbbbbb-0001", source_hash="b" * 64,
                      score=0.85, finished_at=T0))  # fmt: skip
    assert _ids(pick_next([old, new], LATER)) == new.item.ref
    rejected = record(item("clip_02", score=0.99), verdict=PostVerdict(kind="rejected", at=T0))
    assert _ids(pick_next([rejected], LATER)) == "none"


def test_overlaps_same_moment_unless_rejected() -> None:
    queued = record(item(start=100, end=130))
    assert overlaps(item("clip_05", job_id="20260929-aaaaaaaa-0002", start=101, end=131), [queued])
    assert not overlaps(item("clip_05", start=120, end=150), [queued])  # IoU 0.2
    assert not overlaps(item("clip_05", source_hash="b" * 64, start=100, end=130), [queued])
    rejected = queued.model_copy(update={"verdict": PostVerdict(kind="rejected", at=T0)})
    assert not overlaps(item("clip_05", start=100, end=130), [rejected])
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting tests/test_runtime.py -q`
Expected: FAIL (`ModuleNotFoundError: clipforge.posting.store`; `DictKV` has no `items`).

- [ ] **Step 3: Implement**

`pipeline/deps.py`: in `KV` add `def items(self) -> Iterable[tuple[str, str]]: ...`, and in `MemoryKV`:

```python
    def items(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._data.items())
```

`runtime.py`, in `DictKV`:

```python
    def items(self) -> list[tuple[str, str]]:
        """One streaming read of the whole Dict (posting reads all `post:*` keys per tick)."""
        return [(str(key), str(value)) for key, value in self._d.items()]
```

`src/clipforge/posting/store.py`:

```python
"""The ADR-23 posting keys over the job Dict. Each key has one writer (ADR-14): enqueue writes
`post:<ref>`, the sender writes `sent:<n>` / `unavailable` / slot and reminder claims, the
webhook writes `posted:*`, `verdict` and `posting:paused`."""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import ValidationError

from clipforge.models import (
    Platform,
    PostItem,
    PostMark,
    PostRecord,
    PostSend,
    PostVerdict,
    RejectReason,
)
from clipforge.pipeline.deps import KV

log = logging.getLogger(__name__)

PREFIX = "post:"
PAUSED_KEY = "posting:paused"


def _item_key(ref: str) -> str:
    return f"{PREFIX}{ref}"


class PostingStore:
    def __init__(self, kv: KV) -> None:
        self.kv = kv

    # ---- enqueue (writer: package step / rebuild)

    def add(self, item: PostItem) -> bool:
        return self.kv.put(_item_key(item.ref), item.model_dump_json(), skip_if_exists=True)

    # ---- reads

    def get(self, ref: str) -> PostRecord | None:
        raw = self.kv.get(_item_key(ref))
        if raw is None:
            return None
        values: dict[str, str] = {_item_key(ref): raw}
        n = 1
        while (sent := self.kv.get(f"{_item_key(ref)}:sent:{n}")) is not None:
            values[f"{_item_key(ref)}:sent:{n}"] = sent
            n += 1
        for suffix in [f"posted:{p}" for p in Platform] + ["verdict", "unavailable"]:
            key = f"{_item_key(ref)}:{suffix}"
            if (value := self.kv.get(key)) is not None:
                values[key] = value
        return _build(values).get(ref)

    def records(self) -> list[PostRecord]:
        values = {k: v for k, v in self.kv.items() if k.startswith(PREFIX)}
        return list(_build(values).values())

    # ---- sender

    def add_send(self, ref: str, send: PostSend) -> bool:
        key = f"{_item_key(ref)}:sent:{send.n}"
        return self.kv.put(key, send.model_dump_json(), skip_if_exists=True)

    def mark_unavailable(self, ref: str) -> None:
        self.kv.put(f"{_item_key(ref)}:unavailable", "1", skip_if_exists=True)

    def claim_slot(self, slot: datetime) -> bool:
        return self.kv.put(f"posting:slot:{slot.isoformat()}", "1", skip_if_exists=True)

    def release_slot(self, slot: datetime) -> None:
        self.kv.delete(f"posting:slot:{slot.isoformat()}")

    def claim_reminder(self, at: datetime) -> bool:
        return self.kv.put(f"posting:reminded:{at.isoformat()}", "1", skip_if_exists=True)

    # ---- webhook

    def toggle_posted(self, ref: str, platform: Platform, at: datetime) -> bool:
        key = f"{_item_key(ref)}:posted:{platform}"
        if self.kv.get(key) is not None:
            self.kv.delete(key)
            return False
        self.kv.put(key, PostMark(at=at).model_dump_json())
        return True

    def set_verdict(self, ref: str, verdict: PostVerdict) -> None:
        self.kv.put(f"{_item_key(ref)}:verdict", verdict.model_dump_json())

    def set_reason(self, ref: str, reason: RejectReason) -> bool:
        key = f"{_item_key(ref)}:verdict"
        raw = self.kv.get(key)
        if raw is None:
            return False
        verdict = PostVerdict.model_validate_json(raw)
        if verdict.kind != "rejected":
            return False
        self.kv.put(key, verdict.model_copy(update={"reason": reason}).model_dump_json())
        return True

    def paused(self) -> bool:
        return self.kv.get(PAUSED_KEY) is not None

    def set_paused(self, on: bool) -> None:
        if on:
            self.kv.put(PAUSED_KEY, "1")
        else:
            self.kv.delete(PAUSED_KEY)


def _build(values: dict[str, str]) -> dict[str, PostRecord]:
    """Group `post:*` key/values into records. A value that doesn't validate is logged and
    ignored (a clip with a bad item is left out; a bad side key is treated as missing)."""
    items: dict[str, PostItem] = {}
    extras: dict[str, dict[str, str]] = {}
    for key, raw in values.items():
        parts = key.split(":")  # post, job_id, clip_id[, kind[, arg]]
        if len(parts) < 3:
            continue
        ref = f"{parts[1]}:{parts[2]}"
        if len(parts) == 3:
            try:
                items[ref] = PostItem.model_validate_json(raw)
            except ValidationError:
                log.warning("ignoring an invalid posting item %s", ref)
        else:
            extras.setdefault(ref, {})[":".join(parts[3:])] = raw
    records: dict[str, PostRecord] = {}
    for ref, item in items.items():
        sends: list[PostSend] = []
        posted: dict[Platform, datetime] = {}
        verdict: PostVerdict | None = None
        unavailable = False
        for kind, raw in extras.get(ref, {}).items():
            try:
                if kind.startswith("sent:"):
                    sends.append(PostSend.model_validate_json(raw))
                elif kind.startswith("posted:"):
                    posted[Platform(kind.split(":", 1)[1])] = PostMark.model_validate_json(raw).at
                elif kind == "verdict":
                    verdict = PostVerdict.model_validate_json(raw)
                elif kind == "unavailable":
                    unavailable = True
            except (ValidationError, ValueError):
                log.warning("ignoring an invalid posting key %s:%s", ref, kind)
        sends.sort(key=lambda s: s.n)
        records[ref] = PostRecord(
            item=item, sends=sends, posted=posted, verdict=verdict, unavailable=unavailable
        )
    return records
```

Add `PostMark` to `models.py` next to `PostSend`:

```python
class PostMark(Contract):
    """`post:<ref>:posted:<platform>`: the owner confirmed this platform."""

    at: datetime
```

`src/clipforge/posting/queue.py`:

```python
"""Queue rules (spec §4–§6): pure functions over PostRecords."""

from __future__ import annotations

from datetime import datetime, timedelta

from clipforge.models import Platform, PostItem, PostRecord, PostStatus

SKIP_RETURN = timedelta(hours=24)
FRESH_DAYS = timedelta(days=7)
FRESH_BONUS = 0.05
PAUSE_AFTER = 2  # unanswered sends before the slots pause
SAME_MOMENT_IOU = 0.5


def status(record: PostRecord) -> PostStatus:
    verdict = record.verdict
    if verdict is not None and verdict.kind == "rejected":
        return PostStatus.REJECTED
    if record.unavailable:
        return PostStatus.UNAVAILABLE
    if len(record.posted) == len(Platform):
        return PostStatus.POSTED
    if record.posted:
        return PostStatus.PARTLY_POSTED
    last_send = record.sends[-1].at if record.sends else None
    if verdict is not None and verdict.kind == "skipped":
        if last_send is None or verdict.at >= last_send:
            return PostStatus.SKIPPED
    return PostStatus.SENT if last_send is not None else PostStatus.QUEUED


def eligible(record: PostRecord, now: datetime) -> bool:
    state = status(record)
    if state is PostStatus.QUEUED:
        return True
    if state is PostStatus.SKIPPED:
        assert record.verdict is not None
        return now - record.verdict.at >= SKIP_RETURN
    return False


def unanswered(records: list[PostRecord]) -> list[PostRecord]:
    return [r for r in records if status(r) is PostStatus.SENT]


def _priority(item: PostItem, now: datetime) -> float:
    fresh = now - item.episode_finished_at <= FRESH_DAYS
    return item.score + (FRESH_BONUS if fresh else 0.0)


def pick_next(records: list[PostRecord], now: datetime) -> PostRecord | None:
    """Highest priority first, never the same video or channel twice in a row while another is
    eligible (the channel rule gives way first)."""
    sent = [r for r in records if r.sends]
    last = max(sent, key=lambda r: r.sends[-1].at).item if sent else None
    pool = [r for r in records if eligible(r, now)]
    if last is not None:
        other_video = [r for r in pool if r.item.source_hash != last.source_hash]
        other_both = [r for r in other_video if r.item.channel.slug != last.channel.slug]
        pool = other_both or other_video or pool
    if not pool:
        return None
    return min(pool, key=lambda r: (-_priority(r.item, now), r.item.job_id, r.item.start))


def _iou(a: PostItem, b: PostItem) -> float:
    overlap = min(a.end, b.end) - max(a.start, b.start)
    if overlap <= 0:
        return 0.0
    return overlap / (max(a.end, b.end) - min(a.start, b.start))


def overlaps(item: PostItem, records: list[PostRecord]) -> bool:
    """True if a non-rejected clip of the same video covers the same moment."""
    return any(
        r.item.ref != item.ref
        and r.item.source_hash == item.source_hash
        and status(r) is not PostStatus.REJECTED
        and _iou(r.item, item) > SAME_MOMENT_IOU
        for r in records
    )
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting tests/test_runtime.py tests/pipeline -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/pipeline/deps.py`, `src/clipforge/runtime.py`, `src/clipforge/models.py`, `src/clipforge/posting/store.py`, `src/clipforge/posting/queue.py`, `tests/test_runtime.py`, `tests/posting/test_store.py`, `tests/posting/test_queue.py`.

---

### Task 3: Enqueue

**Files:**
- Create: `src/clipforge/posting/enqueue.py`
- Test: `tests/posting/test_enqueue.py`

**Interfaces:**
- Consumes: `PostingStore`, `overlaps`, `Job`, `RenderedClip`.
- Produces: `items_for(job: Job, rendered: list[RenderedClip], now: datetime) -> list[PostItem]` (empty without a channel); `enqueue(store: PostingStore, items: list[PostItem]) -> int` (the number added); `enqueue_job(store, job, rendered, now) -> int`.

- [ ] **Step 1: Write the failing test**

```python
"""Enqueue: a finished channel job's clips become PostItems, without duplicate moments."""

from __future__ import annotations

from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.enqueue import enqueue
from clipforge.posting.store import PostingStore
from tests.posting.builders import item


def test_enqueue_skips_overlapping_moments() -> None:
    store = PostingStore(MemoryKV())
    first = [item("clip_01", start=0, end=30), item("clip_02", start=100, end=130)]
    assert enqueue(store, first) == 2
    recut = [
        item("clip_01", job_id="20260929-aaaaaaaa-0002", start=1, end=31),  # same moment
        item("clip_02", job_id="20260929-aaaaaaaa-0002", start=200, end=230),  # new moment
    ]
    assert enqueue(store, recut) == 1
    assert enqueue(store, recut) == 0  # idempotent
    assert len(store.records()) == 3
```

Also add a unit test of `items_for` over a real `RenderedClip`. The clearest source is the harness's fake stages, so this is covered end to end in Task 4 (`test_channel_job_clips_are_queued`) instead of being faked here.

- [ ] **Step 2: Run the test and check it fails**

Run: `uv run pytest tests/posting/test_enqueue.py -q`
Expected: FAIL with `ModuleNotFoundError: clipforge.posting.enqueue`.

- [ ] **Step 3: Implement** `src/clipforge/posting/enqueue.py`

```python
"""Put a finished channel job's clips into the posting queue (spec §4)."""

from __future__ import annotations

from datetime import datetime

from clipforge.models import Job, PostItem, PostRecord, RenderedClip
from clipforge.posting.queue import overlaps
from clipforge.posting.store import PostingStore


def items_for(job: Job, rendered: list[RenderedClip], now: datetime) -> list[PostItem]:
    channel = job.input.channel
    if channel is None:
        return []
    return [
        PostItem(
            job_id=job.job_id,
            clip_id=clip.clip_id,
            channel=channel,
            source_hash=clip.spec.source.source_hash,
            start=clip.spec.start,
            end=clip.spec.end,
            score=clip.spec.candidate.score,
            title=clip.spec.candidate.title,
            hook=clip.spec.candidate.hook,
            video_path=clip.video_path,
            episode=job.input.source_label or job.job_id,
            episode_finished_at=job.updated_at,
            queued_at=now,
        )
        for clip in sorted(rendered, key=lambda r: r.spec.rank)
    ]


def enqueue(store: PostingStore, items: list[PostItem]) -> int:
    """Add each item unless a non-rejected clip already covers its moment. Idempotent."""
    records = store.records()
    added = 0
    for item in items:
        if overlaps(item, records):
            continue
        if store.add(item):
            added += 1
            records.append(PostRecord(item=item))
    return added


def enqueue_job(store: PostingStore, job: Job, rendered: list[RenderedClip], now: datetime) -> int:
    return enqueue(store, items_for(job, rendered, now))
```

- [ ] **Step 4: Run the test and check it passes**

Run: `uv run pytest tests/posting/test_enqueue.py -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/posting/enqueue.py`, `tests/posting/test_enqueue.py`.

---

### Task 4: Enqueue from `package_step`, rebuild, overview

**Files:**
- Modify: `src/clipforge/pipeline/steps.py` (`package_step`, new `_enqueue_posts`), `src/clipforge/service.py`
- Test: `tests/pipeline/test_posting_chain.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `enqueue_job`, `PostingStore`, `queue.status`, `slots.next_slot`, `Settings`.
- Produces: `service.posting_overview(deps: Deps, settings: Settings, now: datetime) -> PostingOverview`; `service.rebuild_posting(deps: Deps, now: datetime) -> int`; the test helper `tests.posting.builders.run_channel_job(harness, channel=BILLY) -> str`, used by Plan B's later tests and Plan C.

- [ ] **Step 1: Write the failing tests**

Append to `tests/posting/builders.py` (the shared helper for a finished channel job):

```python
from clipforge.models import JobInput
from clipforge.service import create_job
from tests.pipeline.harness import SOURCE_URL, Harness

BILLY = ChannelRef(slug="billy-garton", name="Billy Garton Jr.")


def run_channel_job(harness: Harness, channel: ChannelRef | None = BILLY) -> str:
    """Create a 3-clip channel job the way `clipforge clip` does and run the chain to done."""
    job_input = JobInput.model_validate(
        {"source_url": SOURCE_URL, "permission": "creator_agreement", "options": {"n": 3},
         "source_label": "ep01", "channel": channel.model_dump() if channel else None}
    )  # fmt: skip
    job_id = create_job(harness.deps, job_input).job_id
    harness.run()
    return job_id
```

`tests/pipeline/test_posting_chain.py`:

```python
"""The chain queues a channel job's clips for posting, and never fails because of it."""

from __future__ import annotations

import pytest

from clipforge.jobs import utcnow
from clipforge.models import JobStatus
from clipforge.posting.store import PostingStore
from clipforge.service import rebuild_posting
from tests.pipeline.harness import Harness
from tests.posting.builders import BILLY
from tests.posting.builders import run_channel_job as channel_job


def test_channel_job_clips_are_queued(harness: Harness) -> None:
    job_id = channel_job(harness)
    records = PostingStore(harness.store.kv).records()
    assert len(records) == 3
    assert {r.item.job_id for r in records} == {job_id}
    assert all(r.item.channel == BILLY and r.item.episode == "ep01" for r in records)
    assert all((harness.root / r.item.video_path).is_file() for r in records)


def test_job_without_channel_is_not_queued(harness: Harness) -> None:
    channel_job(harness, channel=None)
    assert PostingStore(harness.store.kv).records() == []


def test_enqueue_failure_never_fails_the_job(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> int:
        raise RuntimeError("dict exploded")

    monkeypatch.setattr("clipforge.pipeline.steps.enqueue_job", boom)
    job_id = channel_job(harness)
    assert harness.store.get(job_id).status is JobStatus.DONE
    assert "done" in harness.event_kinds()


def test_rebuild_queues_old_channel_jobs_once(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("clipforge.pipeline.steps.enqueue_job", lambda *a, **k: 0)  # "old" job
    channel_job(harness)
    monkeypatch.undo()
    assert PostingStore(harness.store.kv).records() == []
    assert rebuild_posting(harness.deps, utcnow()) == 3
    assert rebuild_posting(harness.deps, utcnow()) == 0
```


Append to `tests/test_service.py`:

```python
from datetime import UTC, datetime, timedelta

from clipforge.models import Platform, PostStatus, PostVerdict
from clipforge.posting.store import PostingStore
from clipforge.service import posting_overview
from tests.bot.fakes import ALLOWED_USER, make_settings
from tests.posting.builders import run_channel_job as channel_job


def test_posting_overview_counts(harness: Harness) -> None:
    channel_job(harness)
    store = PostingStore(harness.store.kv)
    first, second, _third = sorted(store.records(), key=lambda r: r.item.clip_id)
    at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    for platform in Platform:
        store.toggle_posted(first.item.ref, platform, at)
    store.set_verdict(second.item.ref, PostVerdict(kind="rejected", at=at))
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER)
    view = posting_overview(harness.deps, settings, at)
    [channel] = view.channels
    assert channel.slug == "billy-garton"
    assert (channel.episodes_clipped, channel.episodes_failed) == (1, 0)
    assert channel.counts[PostStatus.POSTED] == 1
    assert channel.counts[PostStatus.REJECTED] == 1
    assert channel.counts[PostStatus.QUEUED] == 1
    assert (view.enabled, view.paused, view.waiting, view.per_day, view.days_left) == (
        True, False, 1, 6, 1
    )  # fmt: skip
    assert view.next_slot is not None and view.next_slot > at
    off = posting_overview(harness.deps, make_settings(harness.root), at + timedelta(days=1))
    assert off.enabled is False
```

(Use the `harness` fixture the way the file's other tests do. If `tests/test_service.py` has no `Harness` import, add `from tests.pipeline.harness import Harness`.)

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/pipeline/test_posting_chain.py tests/test_service.py -q`
Expected: FAIL (`cannot import name 'rebuild_posting'`).

- [ ] **Step 3: Implement**

`pipeline/steps.py`: add the imports `from clipforge.posting.enqueue import enqueue_job` and `from clipforge.posting.store import PostingStore`. First check that `clipforge/posting/*` doesn't import `clipforge.pipeline.steps`, which would create a cycle. Only `posting/store.py` imports `clipforge.pipeline.deps`, and that's fine. At the end of `package_step`'s `body`, after `deps.store.save(job)`:

```python
        _enqueue_posts(deps, job, rendered)
```

and the helper next to `_deliver`:

```python
def _enqueue_posts(deps: Deps, job: Job, rendered: list[RenderedClip]) -> None:
    """Queue a channel job's clips for posting (ADR-23). Never fails the step: a bad queue
    is fixed with `POST /posting/rebuild`, a failed job is not."""
    if job.input.channel is None:
        return
    try:
        added = enqueue_job(PostingStore(deps.store.kv), job, rendered, utcnow())
        log.info("queued %d clip(s) of %s for posting", added, job.job_id)
    except Exception:
        log.exception("queueing %s for posting failed", job.job_id)
```

`service.py`: add these imports:

```python
from datetime import datetime
from math import ceil

from clipforge.config import Settings
from clipforge.jobs import load_ref
from clipforge.models import (
    ChannelProgress,
    ClipStatus,
    JobStatus,
    PostingOverview,
    PostStatus,
    RenderedClip,
)
from clipforge.posting import queue
from clipforge.posting.enqueue import enqueue_job
from clipforge.posting.slots import next_slot
from clipforge.posting.store import PostingStore
```

Merge them with the existing `models` import. Then add:

```python
def rebuild_posting(deps: Deps, now: datetime) -> int:
    """Queue every finished channel job's clips (idempotent; spec §4)."""
    store = PostingStore(deps.store.kv)
    added = 0
    for job_id in deps.store.list_job_ids():
        job = deps.store.get(job_id)
        if job.status is not JobStatus.DONE or job.input.channel is None:
            continue
        rendered = [
            load_ref(deps.root, c.result_ref, RenderedClip)
            for c in deps.store.clips(job_id, job.clip_ids)
            if c.status is ClipStatus.DONE and c.result_ref is not None
        ]
        added += enqueue_job(store, job, rendered, now)
    return added


_EPISODE_RANK = {JobStatus.DONE: 2, JobStatus.RUNNING: 1, JobStatus.QUEUED: 1, JobStatus.FAILED: 0}


def posting_overview(deps: Deps, settings: Settings, now: datetime) -> PostingOverview:
    """Per channel: episodes by job status (a re-cut counts once, by its best job) and clips by
    posting status; plus how long the queue lasts (spec §9)."""
    store = PostingStore(deps.store.kv)
    names: dict[str, str] = {}
    episodes: dict[str, dict[str, JobStatus]] = {}
    for job_id in deps.store.list_job_ids():
        job = deps.store.get(job_id)
        channel = job.input.channel
        if channel is None:
            continue
        names[channel.slug] = channel.name
        label = job.input.source_label or job.job_id
        seen = episodes.setdefault(channel.slug, {})
        if label not in seen or _EPISODE_RANK[job.status] > _EPISODE_RANK[seen[label]]:
            seen[label] = job.status
    counts: dict[str, dict[PostStatus, int]] = {}
    waiting = 0
    for record in store.records():
        slug = record.item.channel.slug
        names.setdefault(slug, record.item.channel.name)
        state = queue.status(record)
        by_status = counts.setdefault(slug, {})
        by_status[state] = by_status.get(state, 0) + 1
        if state in (PostStatus.QUEUED, PostStatus.SKIPPED):
            waiting += 1
    channels = []
    for slug in sorted(names):
        statuses = list(episodes.get(slug, {}).values())
        channels.append(
            ChannelProgress(
                slug=slug,
                name=names[slug],
                episodes_clipped=statuses.count(JobStatus.DONE),
                episodes_clipping=statuses.count(JobStatus.RUNNING)
                + statuses.count(JobStatus.QUEUED),
                episodes_failed=statuses.count(JobStatus.FAILED),
                counts=counts.get(slug, {}),
            )
        )
    per_day = len(settings.posting_slots)
    enabled = settings.posting_chat_id is not None
    return PostingOverview(
        enabled=enabled,
        paused=store.paused(),
        channels=channels,
        waiting=waiting,
        days_left=ceil(waiting / per_day),
        per_day=per_day,
        next_slot=next_slot(settings, now) if enabled else None,
    )
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/pipeline tests/test_service.py tests/posting -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/pipeline/steps.py`, `src/clipforge/service.py`, `tests/pipeline/test_posting_chain.py`, `tests/test_service.py`.

---

### Task 5: `GET /posting`, `POST /posting/rebuild`, `clipforge status`, docs

**Files:**
- Modify: `src/clipforge/bot/messages.py`, `src/clipforge/api/main.py`, `src/clipforge/cli.py`
- Modify: `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`
- Create: `tests/bot/test_messages.py`
- Test: `tests/api/test_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `posting_overview`, `rebuild_posting`, `utcnow`.
- Produces: `messages.posting_overview_text(view: PostingOverview, timezone: str) -> str`; `ApiClient.posting() -> PostingOverview`, `ApiClient.rebuild_posting() -> int`; routes `GET /posting` → `PostingOverview`, `POST /posting/rebuild` → `{"added": int}`. Plan C reuses `posting_overview_text` for `/status`.

- [ ] **Step 1: Write the failing tests**

Create `tests/bot/test_messages.py`:

```python
"""Bot texts."""

from __future__ import annotations

from datetime import UTC, datetime

from clipforge.bot.messages import posting_overview_text
from clipforge.models import ChannelProgress, PostingOverview, PostStatus


def test_posting_overview_text() -> None:
    view = PostingOverview(
        enabled=True, paused=False, waiting=175, days_left=30, per_day=6,
        next_slot=datetime(2026, 9, 30, 17, 0, tzinfo=UTC),
        channels=[ChannelProgress(
            slug="billy-garton", name="Billy Garton Jr.", episodes_clipped=9,
            episodes_clipping=1, episodes_failed=1,
            counts={PostStatus.POSTED: 38, PostStatus.PARTLY_POSTED: 2, PostStatus.SENT: 1,
                    PostStatus.QUEUED: 171, PostStatus.SKIPPED: 4, PostStatus.REJECTED: 7},
        )],
    )  # fmt: skip
    text = posting_overview_text(view, "America/New_York")
    assert text.splitlines() == [
        "Billy Garton Jr. — 11 episodes (9 clipped · 1 clipping · 1 failed)",
        "  posted 38 · partly 2 · waiting on you 1 · queued 171 · skipped 4 · rejected 7",
        "Queue: 175 clips ≈ 30 days at 6/day · next slot Wed 30 Sep 13:00",
    ]


def test_posting_overview_text_off_paused_and_empty() -> None:
    off = PostingOverview(enabled=False, paused=False, channels=[], waiting=0, days_left=0,
                          per_day=6, next_slot=None)  # fmt: skip
    assert posting_overview_text(off, "UTC").splitlines() == [
        "No channel clips yet. Add videos to videos/<channel>/ and run `clipforge clip`.",
        "Posting is off (set POSTING_CHAT_ID).",
    ]
    paused = off.model_copy(update={"enabled": True, "paused": True})
    assert posting_overview_text(paused, "UTC").splitlines()[-1] == "Paused. Send /go to restart."
```

Append to `tests/api/test_api.py`:

```python
from tests.posting.builders import run_channel_job as channel_job


def test_posting_overview_and_rebuild(harness: Harness) -> None:
    channel_job(harness)
    client = _client(harness)
    assert client.get("/posting").status_code == 401
    view = client.get("/posting", headers=AUTH).json()
    assert view["channels"][0]["slug"] == "billy-garton"
    assert client.post("/posting/rebuild", headers=AUTH).json() == {"added": 0}
```

Append to `tests/test_cli.py`:

```python
def test_status_without_id_prints_the_posting_overview(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.posting.builders import run_channel_job as channel_job

    channel_job(harness)
    assert _run(harness, api, "status") == 0
    out = capsys.readouterr().out
    assert out.startswith("Billy Garton Jr. — 1 episodes (1 clipped")
    assert _run(harness, api, "status", "--rebuild") == 0
    assert "added 0 clip(s) to the posting queue" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/bot/test_messages.py tests/api/test_api.py tests/test_cli.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`bot/messages.py` (add `from zoneinfo import ZoneInfo` and import `PostingOverview, PostStatus`):

```python
_COUNT_LABELS = [
    (PostStatus.POSTED, "posted"),
    (PostStatus.PARTLY_POSTED, "partly"),
    (PostStatus.SENT, "waiting on you"),
    (PostStatus.QUEUED, "queued"),
    (PostStatus.SKIPPED, "skipped"),
    (PostStatus.REJECTED, "rejected"),
    (PostStatus.UNAVAILABLE, "missing video"),
]


def posting_overview_text(view: PostingOverview, timezone: str) -> str:
    """`/status` and `clipforge status`: per channel, then the queue (spec §9)."""
    lines: list[str] = []
    for channel in view.channels:
        total = channel.episodes_clipped + channel.episodes_clipping + channel.episodes_failed
        lines.append(
            f"{channel.name} — {total} episodes ({channel.episodes_clipped} clipped · "
            f"{channel.episodes_clipping} clipping · {channel.episodes_failed} failed)"
        )
        counts = [f"{label} {channel.counts[s]}" for s, label in _COUNT_LABELS
                  if channel.counts.get(s)]  # fmt: skip
        if counts:
            lines.append("  " + " · ".join(counts))
    if not view.channels:
        lines.append(
            "No channel clips yet. Add videos to videos/<channel>/ and run `clipforge clip`."
        )
    if not view.enabled:
        lines.append("Posting is off (set POSTING_CHAT_ID).")
    elif view.paused:
        lines.append("Paused. Send /go to restart.")
    else:
        queue_line = f"Queue: {view.waiting} clips ≈ {view.days_left} days at {view.per_day}/day"
        if view.next_slot is not None:
            local = view.next_slot.astimezone(ZoneInfo(timezone))
            queue_line += f" · next slot {local:%a %d %b %H:%M}"
        lines.append(queue_line)
    return "\n".join(lines)
```

`api/main.py`: change the imports to `from clipforge.jobs import is_job_id, utcnow`, `from clipforge.models import JobInput, JobView, PostingOverview`, `from clipforge.service import create_job, get_job_view, posting_overview, rebuild_posting, resume_job`. Routes:

```python
    @app.get("/posting", dependencies=authorized)
    def get_posting() -> PostingOverview:
        return posting_overview(ctx.deps(), settings, utcnow())

    @app.post("/posting/rebuild", dependencies=authorized)
    def post_posting_rebuild() -> dict[str, int]:
        deps = ctx.deps()
        reload(deps)
        return {"added": rebuild_posting(deps, utcnow())}
```

`cli.py`:
- `ApiClient`:

  ```python
      def posting(self) -> PostingOverview:
          return PostingOverview.model_validate(self._request("GET", "/posting").json())

      def rebuild_posting(self) -> int:
          return int(self._request("POST", "/posting/rebuild").json()["added"])
  ```

- Parser: replace the `for name in ("status", "resume")` loop so that `status` takes an optional id and a `--rebuild` flag, and `resume` keeps a required id:

  ```python
      status = commands.add_parser("status", help="a job's status, or the posting overview")
      status.add_argument("job_id", nargs="?")
      status.add_argument("--rebuild", action="store_true",
                          help="re-queue every finished channel job for posting")  # fmt: skip
      commands.add_parser("resume").add_argument("job_id")
  ```

- `main`, status branch:

  ```python
          if args.command == "status":
              if args.rebuild:
                  print(f"added {client.rebuild_posting()} clip(s) to the posting queue")
              elif args.job_id is None:
                  print(posting_overview_text(client.posting(), settings.posting_timezone))
              else:
                  print(status_text(client.get_job(args.job_id)))
              return 0
  ```

  Import `posting_overview_text` from `clipforge.bot.messages` and `PostingOverview` from models. Docstring: `uv run clipforge status [<job_id>] [--rebuild]   # a job, or the posting overview`.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/bot/test_messages.py tests/api/test_api.py tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Docs**

`docs/DECISIONS.md`, append (renumber if ADR-23 was taken):

```markdown
## ADR-23: Phone-first posting assistant with the queue on Modal
Date: 2026-09-28 · Status: Accepted
Context: Clips go to one brand account on TikTok, Instagram Reels and YouTube Shorts, posted by hand from the phone apps (ADR-3), 5–7 a day. The owner wants a queue that scales to any number of videos and channels and always knows what was posted where. A local day-folder queue was designed first and dropped: it needed the laptop at posting time and couldn't know what was actually posted. We also chose not to test on TikTok first and promote winners: a new account's first-day views are mostly noise.
Decision: When a channel job (ADR-22) finishes, `package_step` queues its clips in the job Dict (`post:<job>:<clip>`), skipping moments that overlap a non-rejected clip of the same video (IoU > 0.5). State is split into one-writer keys: sends, per-platform confirmations, a verdict (skipped or rejected with a reason) and unavailable. The status is derived, never stored. A cron sends the next clip at each slot (plan C): the best score with a fresh-episode bonus, never the same video or channel twice in a row while another is eligible. The owner taps ✅ per platform, ⏭ Skip (back after 24 h) or 🗑 Reject. `GET /posting`, `/status` and `clipforge status` show per-channel progress. Enqueue never fails a job; `POST /posting/rebuild` re-queues finished channel jobs idempotently. Spec: docs/superpowers/specs/2026-09-28-posting-assistant-design.md.
Consequences: The laptop is needed only to add videos. Reads scan all `post:*` keys (`KV.items()`), which is fine for thousands of clips; move to an index or SQLite if it grows past that. Reject reasons feed the Phase 5 ranker. API publishing (step B) would replace the ✅ taps and gets its own ADR.
```

`docs/ARCHITECTURE.md`, add a section after "Local inbox":

```markdown
## Posting queue (ADR-23)

When a channel job finishes, `package_step` queues its clips (`post:<job>:<clip>` in the job Dict, skipping moments already queued). A clip's status (queued, sent, partly posted, posted, skipped, rejected, unavailable) is derived from one-writer keys: `sent:<n>`, `posted:<platform>`, `verdict`, `unavailable`. `GET /posting` (and `clipforge status`, `/status`) shows per-channel progress. `POST /posting/rebuild` re-queues finished channel jobs. Code: `src/clipforge/posting/` (Modal-free). Delivery to the phone: plan C, "Posting assistant".
```

`CLAUDE.md`: in Layout, add `  posting/          # posting queue (ADR-23): store (Dict keys), queue rules, enqueue, slots` after `pipeline/`. In Commands, change `uv run clipforge status <id> / resume <id>` to `uv run clipforge status [<id>] / resume <id>   # no id: the posting overview`.

`ROADMAP.md` Phase 2, add and tick after the ADR-22 line:
`- [x] Posting queue on Modal: enqueue on package, derived per-platform status, \`GET /posting\`, \`clipforge status\` (ADR-23)`

- [ ] **Step 6: Full check**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 7: Checkpoint.** Files: `src/clipforge/bot/messages.py`, `src/clipforge/api/main.py`, `src/clipforge/cli.py`, `tests/bot/test_messages.py`, `tests/api/test_api.py`, `tests/test_cli.py`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`.

> **Superseded (2026-09-28). Do not implement.** See `docs/superpowers/specs/2026-09-28-posting-assistant-design.md`; a new plan replaces this one.

# Posting queue — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uv run clipforge schedule` turns finished clips in `videos/out/` into daily posting slots for TikTok, Instagram and YouTube Shorts, with the order interleaved across videos and creators, per-platform captions, and upload-ready day folders.

**Architecture:** A new Modal-free package, `src/clipforge/posting/`, runs locally over the folders `clipforge clip` unzips (ADR-19). `library.py` scans and dedupes clips and keeps the ledger. `order.py` interleaves clips and assigns slots. `captions.py` builds the platform text. `export.py` writes the day folders. The contracts (`PostingConfig`, `QueuedClip`, `ScheduledPost`, `PostingLedgerEntry`) live in `models.py` (CLAUDE.md rule 2). `cli.py` adds the `schedule` subcommand, which needs no API token.

**Tech Stack:** Python 3.12 stdlib (`tomllib`, `zoneinfo`, `csv`, `math`), pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-posting-queue-design.md`

**Runs after:** `docs/superpowers/plans/2026-09-28-channels-batch.md` (ADR-20). Clips then live in `videos/out/<channel>/<episode>/`, and each `metadata.json` carries the creator credit (`input.source_credit`). If that plan created `tests/posting/helpers.py` without `queued()`, add `queued()` and its imports as shown in Task 1.

**Git:** the owner runs every git command. "Checkpoint" steps list the changed files; don't run git.

## Global Constraints

- `posting/` never imports `modal`, `httpx` or anything from `clipforge.stages`. It reads every `metadata.json` under `videos/out/` (flat `out/<episode>/` and channel `out/<channel>/<episode>/` folders; hidden folders such as `.x.downloading` are ignored) as `JobMetadata`.
- No new dependencies.
- Defaults: timezone `America/New_York`; slots `["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]`; `fresh_days = 7`; `fresh_bonus = 0.05`; minimum lead time 30 minutes; same-moment IoU > 0.5.
- Creator credit comes only from each clip's metadata (`input.source_credit`, then `input.source_label`). There is no credit setting in `posting.toml`.
- Paths: config `videos/posting.toml`, ledger `videos/out/.posting.json`, output `videos/schedule/<YYYY-MM-DD>/`.
- Text limits: TikTok and Instagram 2,200 characters; YouTube title 100 characters including ` #shorts`, with `<` and `>` removed; YouTube description 5,000; Instagram gets the first 5 hashtags.
- All datetimes are timezone-aware. Slots are built in the config time zone. "Now" is injected (never call `datetime.now()` outside `cli.main`).
- Before every checkpoint: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.

## Review Focus

1. **Two cuts of the same video** (`videos/out/` has this today). Only the newest cut is queued, and a moment scheduled from the old cut is not scheduled again from the new one. Tests: `test_scan_keeps_only_newest_cut` (Task 2), `test_ledger_treats_overlapping_moment_as_scheduled` (Task 2).
2. **Running `schedule` twice.** No slot is double-booked and no clip repeats. Test: `test_second_run_fills_next_open_slots` (Task 5).
3. **Running late in the day.** Past slots and slots within 30 minutes are skipped. Test: `test_open_slots_skip_past_and_too_soon` (Task 3).
4. **Stray or outdated folders in `videos/out/`**, such as a folder without `metadata.json`, an old contract, or a missing video. These are skipped with a warning and never crash the command. Test: `test_scan_skips_bad_folders_with_warnings` (Task 2).
5. **Titles YouTube rejects**, with `<`, `>` or more than 100 characters. Test: `test_youtube_title_limits` (Task 4).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/clipforge/models.py` | + posting contracts (Task 1) |
| `src/clipforge/posting/__init__.py` | Package docstring (Task 1) |
| `src/clipforge/posting/library.py` | `load_config`, `scan`, `iou`, `PostingLedger` (Tasks 1–2) |
| `src/clipforge/posting/order.py` | `interleave`, `open_slots`, `plan` (Task 3) |
| `src/clipforge/posting/captions.py` | `tiktok`, `instagram`, `youtube_title`, `youtube_description`, `post_text` (Task 4) |
| `src/clipforge/posting/export.py` | `write` day folders and CSV (Task 5) |
| `src/clipforge/cli.py` | `schedule` subcommand (Task 5) |
| `tests/posting/__init__.py`, `tests/posting/helpers.py` | `write_cut`, `queued` builders (Task 1) |
| `tests/posting/test_*.py`, `tests/test_models.py`, `tests/test_cli.py` | Tests |
| `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md` | ADR-19, docs, roadmap tick (Task 5) |
| `src/clipforge/status_report.py`, `tests/test_status_report.py` | "Posting" section in `videos/STATUS.md` (Task 6) |

---

### Task 1: Posting contracts and config loading

**Files:**
- Modify: `src/clipforge/models.py` (imports at the top; new section at the end)
- Create: `src/clipforge/posting/__init__.py`, `src/clipforge/posting/library.py`
- Create: `tests/posting/__init__.py` (empty), `tests/posting/helpers.py`, `tests/posting/test_library.py`

**Interfaces:**
- Produces: `PostingConfig`, `QueuedClip`, `ScheduledPost`, `PostingLedgerEntry` in `clipforge.models`; `library.CONFIG_NAME = "posting.toml"`; `library.load_config(path: Path) -> PostingConfig`; test builders `write_cut(...)` and `queued(...)`.

- [ ] **Step 1: Write the failing tests**

`tests/posting/helpers.py`:

```python
"""Builders for posting tests: finished job folders as `clipforge clip` unzips them."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from clipforge.models import (
    CostSummary,
    JobInput,
    JobMetadata,
    PackagedClip,
    Permission,
    ProbeInfo,
    QueuedClip,
    SourceMedia,
    Versions,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
T0 = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

_PROBE = ProbeInfo(
    width=1080, height=1920, duration_s=30.0, video_duration_s=30.0, audio_duration_s=30.0,
    fps=30.0, video_codec="h264", pix_fmt="yuv420p", audio_codec="aac",
    n_video_streams=1, n_audio_streams=1, size_bytes=1000,
)  # fmt: skip


def write_cut(
    out_dir: Path,
    folder: str,
    *,
    source_hash: str,
    clips: list[tuple[str, float, float, float, str]],  # (clip_id, start, end, score, title)
    finished_at: datetime = T0,
    credit: str | None = None,
) -> Path:
    job_dir = out_dir / folder
    packaged: list[PackagedClip] = []
    for rank, (clip_id, start, end, score, title) in enumerate(clips, start=1):
        name = f"{clip_id}_score{score:.2f}"
        (job_dir / name).mkdir(parents=True)
        (job_dir / name / "video.mp4").write_bytes(b"mp4")
        packaged.append(
            PackagedClip(
                clip_id=clip_id, rank=rank, dir=name, video=f"{name}/video.mp4",
                srt=f"{name}/captions.srt", post_md=f"{name}/post.md", start=start, end=end,
                score=score, title=title, hook=f"hook of {title}", probe=_PROBE,
            )  # fmt: skip
        )
    metadata = JobMetadata(
        job_id="20260928-aaaaaaaa-0001",
        input=JobInput(
            source_path="uploads/x.mp4", permission=Permission.OWN, source_credit=credit
        ),
        source=SourceMedia(
            video_path="cache/ingest/k/source.mp4", audio_path="cache/ingest/k/audio.wav",
            source_hash=source_hash, duration_s=3600.0, fps=30.0, width=1920, height=1080,
            video_codec="h264", size_bytes=1000,
        ),  # fmt: skip
        transcript_language="en",
        clips=packaged,
        cost=CostSummary(),
        versions=Versions(
            git_sha=None, clipforge="0.1.0", stages={}, highlight_prompt="highlights_v1",
            highlight_model="claude-haiku-4-5", whisper_model="large-v3-turbo",
        ),  # fmt: skip
        started_at=finished_at,
        finished_at=finished_at,
    )
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2))
    return job_dir


def queued(
    clip_id: str = "clip_01",
    *,
    source_hash: str = HASH_A,
    start: float = 0.0,
    end: float = 30.0,
    score: float = 0.85,
    creator: str | None = "Billy Garton Jr.",
    folder: str = "ep1",
    finished_at: datetime = T0,
    title: str = "A title",
    hook: str = "A hook.",
) -> QueuedClip:
    return QueuedClip(
        folder=folder, clip_id=clip_id, video=f"{folder}/{clip_id}/video.mp4",
        source_hash=source_hash, start=start, end=end, score=score, title=title, hook=hook,
        creator=creator, finished_at=finished_at,
    )  # fmt: skip
```

`tests/posting/test_library.py`:

```python
"""Posting library: config, scanning videos/out, the ledger."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from clipforge.models import PostingConfig
from clipforge.posting.library import load_config


def test_missing_config_gives_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "posting.toml")
    assert config.timezone == "America/New_York"
    assert config.slots == ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]
    assert config.hashtags == []


def test_config_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "posting.toml"
    path.write_text(
        'timezone = "Europe/Madrid"\nslots = ["09:00", "18:00"]\n'
        'hashtags = ["mindset"]\n'
    )
    config = load_config(path)
    assert config.timezone == "Europe/Madrid"
    assert config.slots == ["09:00", "18:00"]
    assert config.hashtags == ["mindset"]


@pytest.mark.parametrize(
    "fields",
    [
        {"timezone": "Mars/Olympus"},
        {"slots": []},
        {"slots": ["8:00"]},
        {"slots": ["25:00"]},
        {"slots": ["18:00", "09:00"]},
        {"slots": ["09:00", "09:00"]},
        {"hashtags": ["#mindset"]},
        {"hashtags": ["two words"]},
        {"surprise": 1},
    ],
)
def test_invalid_config_is_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PostingConfig.model_validate(fields)
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_library.py -q`
Expected: FAIL with `ImportError: cannot import name 'PostingConfig'`.

- [ ] **Step 3: Implement**

In `src/clipforge/models.py`, add to the imports:

```python
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
```

Append at the end of `models.py`:

```python
# ---- posting queue (local, over videos/out; ADR-19) ---------------------------------------

_SLOT = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
_HASHTAG = re.compile(r"\w+")


def _default_slots() -> list[str]:
    return ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]


class PostingConfig(Contract):
    """`videos/posting.toml`: when clips go out and what their captions carry."""

    timezone: str = "America/New_York"  # the audience's time zone
    slots: list[str] = Field(default_factory=_default_slots)  # one clip per slot, every platform
    hashtags: list[str] = Field(default_factory=list)  # without "#"
    fresh_days: int = Field(7, ge=0)
    fresh_bonus: float = Field(0.05, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check(self) -> PostingConfig:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {self.timezone!r}") from exc
        if not 1 <= len(self.slots) <= 12:
            raise ValueError("slots: between 1 and 12 per day")
        if any(not _SLOT.fullmatch(slot) for slot in self.slots):
            raise ValueError("slots must be HH:MM, e.g. 08:00")
        if sorted(set(self.slots)) != self.slots:
            raise ValueError("slots must be unique and in order")
        if any(not _HASHTAG.fullmatch(tag) for tag in self.hashtags):
            raise ValueError("hashtags: letters, digits and _ only, without #")
        return self


class QueuedClip(Contract):
    """A delivered clip that can be posted. `video` is relative to `videos/out/`."""

    folder: str  # relative to videos/out/, e.g. "billy-garton/ep01" or "billy_carton-Koa_smith-2"
    clip_id: str
    video: str  # "<folder>/clip_01_score0.89/video.mp4"
    source_hash: str
    start: float  # source time
    end: float
    score: float
    title: str
    hook: str
    creator: str | None
    finished_at: datetime


class ScheduledPost(Contract):
    slot: datetime  # timezone-aware
    clip: QueuedClip


class PostingLedgerEntry(Contract):
    """One line of `videos/out/.posting.json`."""

    source_hash: str
    start: float
    end: float
    slot: datetime
    folder: str
    clip_id: str
```

`src/clipforge/posting/__init__.py`:

```python
"""Posting queue (ADR-19): local, over the clips `clipforge clip` unzips into videos/out/.

Never imports modal: it runs on the owner's machine to plan manual uploads (step A)."""
```

`src/clipforge/posting/library.py`:

```python
"""Finished clips in `videos/out/` that can still be posted, and the ledger of scheduled posts."""

from __future__ import annotations

import tomllib
from pathlib import Path

from clipforge.models import PostingConfig

CONFIG_NAME = "posting.toml"


def load_config(path: Path) -> PostingConfig:
    """The config, or defaults if the file is missing. Raises TOMLDecodeError / ValidationError."""
    if not path.exists():
        return PostingConfig()
    return PostingConfig.model_validate(tomllib.loads(path.read_text()))
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting/test_library.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/models.py`, `src/clipforge/posting/__init__.py`, `src/clipforge/posting/library.py`, `tests/posting/__init__.py`, `tests/posting/helpers.py`, `tests/posting/test_library.py`. Run the full check from Global Constraints first.

---

### Task 2: Scan `videos/out/`, dedupe re-cuts, ledger

**Files:**
- Modify: `src/clipforge/posting/library.py`
- Test: `tests/posting/test_library.py`

**Interfaces:**
- Consumes: `PostingConfig`, `QueuedClip`, `ScheduledPost`, `PostingLedgerEntry`, `helpers.write_cut`, `helpers.queued`.
- Produces: `library.LEDGER_NAME = ".posting.json"`; `scan(out_dir: Path, config: PostingConfig) -> tuple[list[QueuedClip], list[str]]` (clips, warnings); `iou(a: tuple[float, float], b: tuple[float, float]) -> float`; `class PostingLedger(path: Path)` with `.is_scheduled(clip: QueuedClip) -> bool`, `.used_slots() -> set[datetime]` and `.record(posts: list[ScheduledPost]) -> None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/posting/test_library.py`, and merge the new imports into the import block at the top)

```python
from datetime import timedelta

from clipforge.models import ScheduledPost
from clipforge.posting.library import PostingLedger, iou, scan
from tests.posting.helpers import HASH_A, HASH_B, T0, queued, write_cut


def test_scan_reads_clips_with_paths_relative_to_out(tmp_path: Path) -> None:
    write_cut(tmp_path, "ep1", source_hash=HASH_A, clips=[("clip_01", 10.0, 40.0, 0.9, "One")])
    clips, warnings = scan(tmp_path, PostingConfig())
    assert warnings == ["ep1: no creator credit (put the video in a channel folder)"]
    [clip] = clips
    assert clip.video == "ep1/clip_01_score0.90/video.mp4"
    assert (tmp_path / clip.video).is_file()
    assert (clip.source_hash, clip.start, clip.end, clip.score) == (HASH_A, 10.0, 40.0, 0.9)
    assert clip.hook == "hook of One" and clip.creator is None


def test_scan_keeps_only_newest_cut(tmp_path: Path) -> None:
    write_cut(tmp_path, "ep", source_hash=HASH_A, clips=[("clip_01", 0.0, 30.0, 0.9, "Old")],
              finished_at=T0, credit="X")  # fmt: skip
    write_cut(tmp_path, "ep-2", source_hash=HASH_A, clips=[("clip_01", 0.0, 30.0, 0.9, "New")],
              finished_at=T0 + timedelta(hours=1), credit="X")  # fmt: skip
    clips, warnings = scan(tmp_path, PostingConfig())
    assert [c.title for c in clips] == ["New"]
    assert warnings == ["ep: older cut of the same video as ep-2, skipped"]


def test_scan_channel_folders_and_credit(tmp_path: Path) -> None:
    write_cut(tmp_path / "billy-garton", "ep01", source_hash=HASH_A,
              clips=[("clip_01", 0, 30, 0.9, "A")], credit="Billy Garton Jr.")  # fmt: skip
    write_cut(tmp_path, "loose", source_hash=HASH_B, clips=[("clip_01", 0, 30, 0.9, "B")],
              credit="From job")  # fmt: skip
    (tmp_path / "billy-garton" / ".ep02.downloading").mkdir()  # an unfinished download
    (tmp_path / "previews").mkdir()  # stray folder without metadata
    clips, warnings = scan(tmp_path, PostingConfig())
    assert {c.folder: c.creator for c in clips} == {
        "billy-garton/ep01": "Billy Garton Jr.",
        "loose": "From job",
    }
    by_folder = {c.folder: c for c in clips}
    assert by_folder["billy-garton/ep01"].video == "billy-garton/ep01/clip_01_score0.90/video.mp4"
    assert warnings == []


def test_scan_skips_bad_folders_with_warnings(tmp_path: Path) -> None:
    (tmp_path / "no_metadata").mkdir()
    (tmp_path / "old_contract").mkdir()
    (tmp_path / "old_contract" / "metadata.json").write_text('{"job_id": "x"}')
    two = [("clip_01", 0.0, 30.0, 0.9, "A"), ("clip_02", 40.0, 70.0, 0.8, "B")]
    job = write_cut(tmp_path, "ep1", source_hash=HASH_A, credit="C", clips=two)
    (job / "clip_02_score0.80" / "video.mp4").unlink()
    clips, warnings = scan(tmp_path, PostingConfig())
    assert [c.clip_id for c in clips] == ["clip_01"]
    assert warnings == [
        "old_contract: metadata.json doesn't match this version, skipped",
        "ep1/clip_02_score0.80/video.mp4: missing, skipped",
    ]
    assert scan(tmp_path / "nope", PostingConfig()) == ([], [])


def test_iou() -> None:
    assert iou((0, 10), (0, 10)) == 1.0
    assert iou((0, 10), (5, 15)) == pytest.approx(5 / 15)
    assert iou((0, 10), (10, 20)) == 0.0


def test_ledger_treats_overlapping_moment_as_scheduled(tmp_path: Path) -> None:
    ledger = PostingLedger(tmp_path / ".posting.json")
    post = ScheduledPost(slot=T0, clip=queued(start=100.0, end=130.0))
    ledger.record([post])
    reloaded = PostingLedger(tmp_path / ".posting.json")
    assert reloaded.is_scheduled(queued(start=101.0, end=131.0, folder="ep1-2"))  # re-cut
    assert not reloaded.is_scheduled(queued(start=120.0, end=150.0))  # IoU 0.25
    assert not reloaded.is_scheduled(queued(source_hash=HASH_B, start=100.0, end=130.0))
    assert reloaded.used_slots() == {T0}
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_library.py -q`
Expected: FAIL with `ImportError: cannot import name 'PostingLedger'`.

- [ ] **Step 3: Implement** (replace `library.py` with the full module)

```python
"""Finished clips in `videos/out/` that can still be posted, and the ledger of scheduled posts."""

from __future__ import annotations

import json
import tomllib
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from clipforge.models import (
    JobMetadata,
    PostingConfig,
    PostingLedgerEntry,
    QueuedClip,
    ScheduledPost,
)

CONFIG_NAME = "posting.toml"
LEDGER_NAME = ".posting.json"
SAME_MOMENT_IOU = 0.5  # the same threshold highlights uses to dedupe candidates


def load_config(path: Path) -> PostingConfig:
    """The config, or defaults if the file is missing. Raises TOMLDecodeError / ValidationError."""
    if not path.exists():
        return PostingConfig()
    return PostingConfig.model_validate(tomllib.loads(path.read_text()))


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    overlap = min(a[1], b[1]) - max(a[0], b[0])
    if overlap <= 0:
        return 0.0
    return overlap / (max(a[1], b[1]) - min(a[0], b[0]))


def _creator(metadata: JobMetadata) -> str | None:
    """The channel credit that `clipforge clip` put into the job (ADR-20)."""
    return metadata.input.source_credit or metadata.input.source_label


def scan(out_dir: Path, config: PostingConfig) -> tuple[list[QueuedClip], list[str]]:
    """Every clip of the newest cut of each source video, plus warnings about what was skipped."""
    if not out_dir.is_dir():
        return [], []
    warnings: list[str] = []
    newest: dict[str, tuple[str, JobMetadata]] = {}
    for meta_path in sorted(out_dir.rglob("metadata.json")):
        relative = meta_path.parent.relative_to(out_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue  # an unfinished download (".<name>.downloading")
        folder = relative.as_posix()
        try:
            metadata = JobMetadata.model_validate_json(meta_path.read_text())
        except ValidationError:
            warnings.append(f"{folder}: metadata.json doesn't match this version, skipped")
            continue
        kept = newest.get(metadata.source.source_hash)
        if kept is None or metadata.finished_at > kept[1].finished_at:
            if kept is not None:
                warnings.append(f"{kept[0]}: older cut of the same video as {folder}, skipped")
            newest[metadata.source.source_hash] = (folder, metadata)
        else:
            warnings.append(f"{folder}: older cut of the same video as {kept[0]}, skipped")

    clips: list[QueuedClip] = []
    for folder, metadata in newest.values():
        creator = _creator(metadata)
        if creator is None:
            warnings.append(f"{folder}: no creator credit (put the video in a channel folder)")
        for packaged in metadata.clips:
            video = f"{folder}/{packaged.video}"
            if not (out_dir / video).is_file():
                warnings.append(f"{video}: missing, skipped")
                continue
            clips.append(
                QueuedClip(
                    folder=folder,
                    clip_id=packaged.clip_id,
                    video=video,
                    source_hash=metadata.source.source_hash,
                    start=packaged.start,
                    end=packaged.end,
                    score=packaged.score,
                    title=packaged.title,
                    hook=packaged.hook,
                    creator=creator,
                    finished_at=metadata.finished_at,
                )
            )
    return clips, warnings


class PostingLedger:
    """`videos/out/.posting.json`: every post already given a slot, so no moment is scheduled
    twice (not even from a later re-cut of the same video) and no slot is double-booked."""

    def __init__(self, path: Path) -> None:
        self.path = path
        raw = json.loads(path.read_text()) if path.exists() else []
        self.entries = [PostingLedgerEntry.model_validate(entry) for entry in raw]

    def is_scheduled(self, clip: QueuedClip) -> bool:
        return any(
            entry.source_hash == clip.source_hash
            and iou((entry.start, entry.end), (clip.start, clip.end)) > SAME_MOMENT_IOU
            for entry in self.entries
        )

    def used_slots(self) -> set[datetime]:
        return {entry.slot for entry in self.entries}

    def record(self, posts: list[ScheduledPost]) -> None:
        self.entries.extend(
            PostingLedgerEntry(
                source_hash=post.clip.source_hash,
                start=post.clip.start,
                end=post.clip.end,
                slot=post.slot,
                folder=post.clip.folder,
                clip_id=post.clip.clip_id,
            )
            for post in posts
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [entry.model_dump(mode="json") for entry in self.entries]
        self.path.write_text(json.dumps(data, indent=2) + "\n")
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting/test_library.py -q`
Expected: PASS (17 tests). Then check against real data: `uv run python -c "from pathlib import Path; from clipforge.posting.library import scan; from clipforge.models import PostingConfig; c, w = scan(Path('videos/out'), PostingConfig()); print(len(c), w)"` should print `30` clips, a warning that `billy_carton-Koa_smith` is an older cut, and a no-credit warning.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/posting/library.py`, `tests/posting/test_library.py`.

---

### Task 3: Interleaved order and time slots

**Files:**
- Create: `src/clipforge/posting/order.py`
- Test: `tests/posting/test_order.py`

**Interfaces:**
- Consumes: `PostingConfig`, `QueuedClip`, `ScheduledPost`, `helpers.queued`.
- Produces: `MIN_LEAD = timedelta(minutes=30)`; `interleave(clips: list[QueuedClip], now: datetime, config: PostingConfig) -> list[QueuedClip]`; `open_slots(start: date, days: int, config: PostingConfig, now: datetime, used: set[datetime]) -> list[datetime]`; `plan(clips: list[QueuedClip], *, start: date, days: int, config: PostingConfig, now: datetime, used: set[datetime]) -> list[ScheduledPost]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Posting order: interleave videos and creators, best first; slots in the audience's zone."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from clipforge.models import PostingConfig, QueuedClip
from clipforge.posting.order import interleave, open_slots, plan
from tests.posting.helpers import HASH_A, HASH_B, T0, queued

HASH_C = "c" * 64
NY = ZoneInfo("America/New_York")
OLD = T0 - timedelta(days=30)  # past fresh_days, so no bonus unless a test wants one


def _ids(clips: list[QueuedClip]) -> list[str]:
    return [f"{c.folder}/{c.clip_id}" for c in clips]


def test_one_video_goes_by_score() -> None:
    clips = [queued("c1", score=0.82, finished_at=OLD), queued("c2", score=0.89, finished_at=OLD),
             queued("c3", score=0.85, finished_at=OLD)]  # fmt: skip
    assert _ids(interleave(clips, T0, PostingConfig())) == ["ep1/c2", "ep1/c3", "ep1/c1"]


def test_two_videos_alternate() -> None:
    a = [queued(f"a{i}", folder="A", score=0.9 - i / 100, finished_at=OLD) for i in range(3)]
    b = [queued(f"b{i}", folder="B", source_hash=HASH_B, score=0.8, finished_at=OLD)
         for i in range(2)]  # fmt: skip
    order = _ids(interleave(a + b, T0, PostingConfig()))
    assert order == ["A/a0", "B/b0", "A/a1", "B/b1", "A/a2"]


def test_creators_alternate_before_videos() -> None:
    a1 = [queued("x", folder="A1", creator="Ann", score=0.9, finished_at=OLD)]
    a2 = [queued("y", folder="A2", source_hash=HASH_B, creator="Ann", score=0.89, finished_at=OLD)]
    b = [queued("z", folder="B", source_hash=HASH_C, creator="Bob", score=0.8, finished_at=OLD)]
    order = _ids(interleave(a1 + a2 + b, T0, PostingConfig()))
    assert order == ["A1/x", "B/z", "A2/y"]  # Bob's weaker clip beats a second Ann in a row


def test_fresh_video_gets_bonus() -> None:
    old = queued("old", folder="Old", score=0.88, finished_at=OLD)
    new = queued("new", folder="New", source_hash=HASH_B, score=0.85, finished_at=T0)
    assert _ids(interleave([old, new], T0, PostingConfig()))[0] == "New/new"
    no_bonus = PostingConfig(fresh_bonus=0.0)
    assert _ids(interleave([old, new], T0, no_bonus))[0] == "Old/old"


def test_open_slots_skip_past_and_too_soon() -> None:
    config = PostingConfig(slots=["08:00", "12:00", "18:00"])
    now = datetime(2026, 9, 29, 11, 45, tzinfo=NY)  # 12:00 is only 15 min away
    slots = open_slots(date(2026, 9, 29), 2, config, now, used=set())
    assert [s.strftime("%d %H:%M") for s in slots] == [
        "29 18:00", "30 08:00", "30 12:00", "30 18:00"
    ]  # fmt: skip
    assert all(s.tzinfo == NY for s in slots)


def test_open_slots_skip_used_even_across_zones() -> None:
    config = PostingConfig(slots=["08:00", "18:00"])
    now = datetime(2026, 9, 29, 0, 0, tzinfo=NY)
    used = {datetime(2026, 9, 29, 12, 0, tzinfo=UTC)}  # = 08:00 in New York (EDT)
    slots = open_slots(date(2026, 9, 29), 1, config, now, used=used)
    assert [s.strftime("%H:%M") for s in slots] == ["18:00"]


def test_plan_stops_when_slots_or_clips_run_out() -> None:
    config = PostingConfig(slots=["08:00", "18:00"])
    now = datetime(2026, 9, 29, 0, 0, tzinfo=NY)
    clips = [
        queued(f"c{i}", start=i * 100.0, end=i * 100.0 + 30, finished_at=OLD) for i in range(3)
    ]
    posts = plan(clips, start=date(2026, 9, 29), days=1, config=config, now=now, used=set())
    assert len(posts) == 2
    posts = plan(clips, start=date(2026, 9, 29), days=5, config=config, now=now, used=set())
    assert len(posts) == 3
    assert posts[0].slot < posts[1].slot < posts[2].slot
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_order.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipforge.posting.order'`.

- [ ] **Step 3: Implement** `src/clipforge/posting/order.py`

```python
"""Posting order and slots: best clips first, but the feed never reads like one episode split up
(spec §4–5)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from clipforge.models import PostingConfig, QueuedClip, ScheduledPost

MIN_LEAD = timedelta(minutes=30)  # platform schedulers need a slot some time in the future


def _priority(clip: QueuedClip, now: datetime, config: PostingConfig) -> float:
    fresh = now - clip.finished_at <= timedelta(days=config.fresh_days)
    return clip.score + (config.fresh_bonus if fresh else 0.0)


def interleave(clips: list[QueuedClip], now: datetime, config: PostingConfig) -> list[QueuedClip]:
    """Highest priority first, never the same video or creator twice in a row while another is
    left (the creator rule gives way first). Within a video, highest score first."""
    groups: dict[str, list[QueuedClip]] = {}
    for clip in sorted(clips, key=lambda c: (-c.score, c.start)):
        groups.setdefault(clip.source_hash, []).append(clip)
    order: list[QueuedClip] = []
    last: QueuedClip | None = None
    while groups:
        heads = [group[0] for group in groups.values()]
        if last is None:
            pool = heads
        else:
            other_video = [c for c in heads if c.source_hash != last.source_hash]
            other_both = [c for c in other_video if c.creator != last.creator]
            pool = other_both or other_video or heads
        pick = min(pool, key=lambda c: (-_priority(c, now, config), c.folder, c.start))
        order.append(pick)
        groups[pick.source_hash].pop(0)
        if not groups[pick.source_hash]:
            del groups[pick.source_hash]
        last = pick
    return order


def open_slots(
    start: date, days: int, config: PostingConfig, now: datetime, used: set[datetime]
) -> list[datetime]:
    zone = ZoneInfo(config.timezone)
    slots: list[datetime] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for text in config.slots:
            hour, minute = (int(part) for part in text.split(":"))
            slot = datetime.combine(day, time(hour, minute), tzinfo=zone)
            if slot >= now + MIN_LEAD and slot not in used:
                slots.append(slot)
    return slots


def plan(
    clips: list[QueuedClip],
    *,
    start: date,
    days: int,
    config: PostingConfig,
    now: datetime,
    used: set[datetime],
) -> list[ScheduledPost]:
    slots = open_slots(start, days, config, now, used)
    ordered = interleave(clips, now, config)
    return [ScheduledPost(slot=slot, clip=clip) for slot, clip in zip(slots, ordered, strict=False)]
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting/test_order.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/posting/order.py`, `tests/posting/test_order.py`.

---

### Task 4: Per-platform captions

**Files:**
- Create: `src/clipforge/posting/captions.py`
- Test: `tests/posting/test_captions.py`

**Interfaces:**
- Consumes: `PostingConfig`, `QueuedClip`, `helpers.queued`.
- Produces: `tiktok(clip: QueuedClip, config: PostingConfig) -> str`, `instagram(...) -> str`, `youtube_title(clip: QueuedClip) -> str`, `youtube_description(clip, config) -> str`, `post_text(clip, config) -> str` (the `.txt` file).

- [ ] **Step 1: Write the failing tests**

```python
"""Per-platform caption text (template until the Phase 3 post.md copy)."""

from __future__ import annotations

from clipforge.models import PostingConfig
from clipforge.posting.captions import (
    instagram,
    post_text,
    tiktok,
    youtube_description,
    youtube_title,
)
from tests.posting.helpers import queued

CONFIG = PostingConfig(hashtags=["growth", "mindset", "men", "podcast", "honesty", "clips"])


def test_tiktok_has_hook_credit_and_tags() -> None:
    text = tiktok(queued(hook="I changed.", creator="Billy Garton Jr."), CONFIG)
    assert text == (
        "I changed.\n\n🎙️ Billy Garton Jr.\n\n#growth #mindset #men #podcast #honesty #clips"
    )


def test_no_credit_line_without_creator() -> None:
    assert "🎙️" not in tiktok(queued(creator=None), CONFIG)


def test_instagram_title_first_and_at_most_five_tags() -> None:
    text = instagram(queued(title="Be honest", hook="Hook."), CONFIG)
    assert text.startswith("Be honest\n\nHook.\n\n🎙️ ")
    assert text.endswith("#growth #mindset #men #podcast #honesty")


def test_youtube_title_limits() -> None:
    assert youtube_title(queued(title="Real <men> talk")) == "Real men talk #shorts"
    long = youtube_title(queued(title="word " * 40))
    assert len(long) == 100 and long.endswith("… #shorts")


def test_long_text_is_cut_to_the_platform_limit() -> None:
    clip = queued(hook="x" * 3000)
    assert len(tiktok(clip, CONFIG)) == 2200
    assert len(instagram(clip, CONFIG)) == 2200
    assert len(youtube_description(queued(hook="x" * 6000), CONFIG)) == 5000


def test_post_text_has_every_section() -> None:
    text = post_text(queued(), CONFIG)
    for header in ("TIKTOK", "INSTAGRAM", "YOUTUBE TITLE", "YOUTUBE DESCRIPTION"):
        assert f"== {header} ==" in text
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_captions.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipforge.posting.captions'`.

- [ ] **Step 3: Implement** `src/clipforge/posting/captions.py`

```python
"""Per-platform post text built from a clip's title, hook and creator credit.

A template on purpose: LLM-written copy is the Phase 3 `post.md` item and can replace these."""

from __future__ import annotations

from clipforge.models import PostingConfig, QueuedClip

TIKTOK_MAX = 2200
INSTAGRAM_MAX = 2200
INSTAGRAM_MAX_HASHTAGS = 5
YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESCRIPTION_MAX = 5000
SHORTS_TAG = " #shorts"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def _credit(clip: QueuedClip) -> str:
    return f"🎙️ {clip.creator}" if clip.creator else ""


def _tags(config: PostingConfig, limit: int | None = None) -> str:
    return " ".join(f"#{tag}" for tag in config.hashtags[:limit])


def tiktok(clip: QueuedClip, config: PostingConfig) -> str:
    return _cut(_join(clip.hook, _credit(clip), _tags(config)), TIKTOK_MAX)


def instagram(clip: QueuedClip, config: PostingConfig) -> str:
    text = _join(clip.title, clip.hook, _credit(clip), _tags(config, INSTAGRAM_MAX_HASHTAGS))
    return _cut(text, INSTAGRAM_MAX)


def youtube_title(clip: QueuedClip) -> str:
    """YouTube rejects `<` and `>` in titles."""
    title = " ".join(clip.title.replace("<", "").replace(">", "").split())
    return _cut(title, YOUTUBE_TITLE_MAX - len(SHORTS_TAG)) + SHORTS_TAG


def youtube_description(clip: QueuedClip, config: PostingConfig) -> str:
    return _cut(_join(clip.hook, _credit(clip), _tags(config)), YOUTUBE_DESCRIPTION_MAX)


def post_text(clip: QueuedClip, config: PostingConfig) -> str:
    """The `.txt` next to each scheduled video: every platform's text, ready to paste."""
    sections = [
        ("TIKTOK", tiktok(clip, config)),
        ("INSTAGRAM", instagram(clip, config)),
        ("YOUTUBE TITLE", youtube_title(clip)),
        ("YOUTUBE DESCRIPTION", youtube_description(clip, config)),
    ]
    return "\n\n".join(f"== {name} ==\n{text}" for name, text in sections) + "\n"
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting/test_captions.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/posting/captions.py`, `tests/posting/test_captions.py`.

---

### Task 5: Export, `clipforge schedule`, docs

**Files:**
- Create: `src/clipforge/posting/export.py`
- Modify: `src/clipforge/cli.py` (docstring, imports, `build_parser`, `main`, new `_schedule`)
- Modify: `docs/DECISIONS.md` (ADR-19), `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`
- Test: `tests/posting/test_export.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `export.SCHEDULE_DIR = "schedule"`; `export.write(posts: list[ScheduledPost], out_dir: Path, schedule_dir: Path, config: PostingConfig) -> list[Path]` (the day folders written); `cli.main(..., now: datetime | None = None)`.

- [ ] **Step 1: Write the failing tests**

`tests/posting/test_export.py`:

```python
"""Day folders: linked videos in posting order, caption files, an appended CSV."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from clipforge.models import PostingConfig, ScheduledPost
from clipforge.posting.export import write
from tests.posting.helpers import HASH_A, queued, write_cut

NY = ZoneInfo("America/New_York")


def test_write_day_folders(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_cut(out, "ep1", source_hash=HASH_A, clips=[("clip_01", 0, 30, 0.9, "Be Honest!")])
    clip = queued(folder="ep1", clip_id="clip_01", title="Be Honest!")
    clip = clip.model_copy(update={"video": "ep1/clip_01_score0.90/video.mp4"})
    slot = datetime(2026, 9, 29, 8, 0, tzinfo=NY)
    days = write([ScheduledPost(slot=slot, clip=clip)], out, tmp_path / "schedule", PostingConfig())
    day = tmp_path / "schedule" / "2026-09-29"
    assert days == [day]
    assert (day / "0800_be-honest.mp4").read_bytes() == b"mp4"
    assert "== TIKTOK ==" in (day / "0800_be-honest.txt").read_text()
    with (day / "schedule.csv").open() as f:
        [row] = list(csv.DictReader(f))
    assert row["time"] == "2026-09-29 08:00" and row["timezone"] == "America/New_York"
    assert row["video"] == "0800_be-honest.mp4" and row["clip_id"] == "clip_01"
    assert row["youtube_title"] == "Be Honest! #shorts"

    later = ScheduledPost(slot=datetime(2026, 9, 29, 18, 0, tzinfo=NY), clip=clip)
    write([later], out, tmp_path / "schedule", PostingConfig())
    with (day / "schedule.csv").open() as f:
        assert [r["time"] for r in csv.DictReader(f)] == ["2026-09-29 08:00", "2026-09-29 18:00"]
```

Append to `tests/test_cli.py` (merge the imports into its import block; `main` is already imported there, so check its import name first):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.posting.helpers import HASH_A, HASH_B, write_cut


def _videos(tmp_path: Path) -> Path:
    folder = tmp_path / "videos"
    two = [("clip_01", 0.0, 30.0, 0.9, "A one"), ("clip_02", 40.0, 70.0, 0.85, "A two")]
    one = [("clip_01", 0.0, 30.0, 0.8, "B one")]
    write_cut(folder / "out", "ep1", source_hash=HASH_A, clips=two, credit="Billy")
    write_cut(folder / "out", "ep2", source_hash=HASH_B, clips=one, credit="Billy")
    (folder / "posting.toml").write_text('slots = ["08:00", "18:00"]\n')
    return folder


NOW = datetime(2026, 9, 29, 0, 0, tzinfo=ZoneInfo("America/New_York"))


def test_schedule_needs_no_api(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _videos(tmp_path)
    code = main(["schedule", "--folder", str(folder), "--days", "1"],
                settings=Settings(_env_file=None), now=NOW)  # fmt: skip
    assert code == 0
    out = capsys.readouterr().out
    assert "ep1/clip_01" in out and "ep2/clip_01" in out and "1 clips still queued" in out
    day = folder / "schedule" / "2026-09-29"
    assert sorted(p.name for p in day.glob("*.mp4")) == ["0800_a-one.mp4", "1800_b-one.mp4"]


def test_second_run_fills_next_open_slots(tmp_path: Path) -> None:
    folder = _videos(tmp_path)
    for _ in range(2):
        main(["schedule", "--folder", str(folder), "--days", "2"],
             settings=Settings(_env_file=None), now=NOW)  # fmt: skip
    ledger = (folder / "out" / ".posting.json").read_text()
    assert ledger.count('"slot"') == 3  # 3 clips, 4 slots: nothing repeated or double-booked
    assert sorted(p.name for p in (folder / "schedule" / "2026-09-30").glob("*.mp4")) == [
        "0800_a-two.mp4"
    ]


def test_schedule_dry_run_writes_nothing(tmp_path: Path) -> None:
    folder = _videos(tmp_path)
    main(["schedule", "--folder", str(folder), "--dry-run"],
         settings=Settings(_env_file=None), now=NOW)  # fmt: skip
    assert not (folder / "schedule").exists()
    assert not (folder / "out" / ".posting.json").exists()


def test_schedule_bad_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _videos(tmp_path)
    (folder / "posting.toml").write_text('slots = ["9am"]\n')
    assert main(["schedule", "--folder", str(folder)], settings=Settings(_env_file=None),
                now=NOW) == 2  # fmt: skip
    assert "posting.toml" in capsys.readouterr().err
```

If `tests/test_cli.py` builds `Settings` differently (for example with a helper), use that helper instead of `Settings(_env_file=None)`. The point is that no `API_URL`/`API_TOKEN` is set.

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_export.py tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipforge.posting.export'`, and the CLI tests fail on the unknown `schedule` command.

- [ ] **Step 3: Implement `src/clipforge/posting/export.py`**

```python
"""Writes a schedule: per day (in the posting time zone), the videos to upload named in posting
order, a caption file next to each, and `schedule.csv` (appended by each run)."""

from __future__ import annotations

import csv
import os
import re
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

from clipforge.models import PostingConfig, ScheduledPost
from clipforge.posting import captions

SCHEDULE_DIR = "schedule"
CSV_NAME = "schedule.csv"
COLUMNS = [
    "time", "timezone", "video", "source", "clip_id", "score", "creator",
    "tiktok", "instagram", "youtube_title", "youtube_description",
]  # fmt: skip
_NOT_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _NOT_SLUG.sub("-", text.lower()).strip("-")[:40].rstrip("-") or "clip"


def _link_or_copy(src: Path, dest: Path) -> None:
    """A hard link saves disk; copy when the filesystem can't link (another drive, FAT)."""
    dest.unlink(missing_ok=True)
    try:
        os.link(src, dest)
    except OSError:
        shutil.copyfile(src, dest)


def write(
    posts: list[ScheduledPost], out_dir: Path, schedule_dir: Path, config: PostingConfig
) -> list[Path]:
    zone = ZoneInfo(config.timezone)
    rows: dict[Path, list[dict[str, str]]] = {}
    for post in posts:
        local = post.slot.astimezone(zone)
        day_dir = schedule_dir / local.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        clip = post.clip
        stem = f"{local:%H%M}_{_slug(clip.title)}"
        _link_or_copy(out_dir / clip.video, day_dir / f"{stem}.mp4")
        (day_dir / f"{stem}.txt").write_text(captions.post_text(clip, config))
        rows.setdefault(day_dir, []).append(
            {
                "time": f"{local:%Y-%m-%d %H:%M}",
                "timezone": config.timezone,
                "video": f"{stem}.mp4",
                "source": clip.folder,
                "clip_id": clip.clip_id,
                "score": f"{clip.score:.2f}",
                "creator": clip.creator or "",
                "tiktok": captions.tiktok(clip, config),
                "instagram": captions.instagram(clip, config),
                "youtube_title": captions.youtube_title(clip),
                "youtube_description": captions.youtube_description(clip, config),
            }
        )
    for day_dir, day_rows in rows.items():
        path = day_dir / CSV_NAME
        new = not path.exists()
        with path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if new:
                writer.writeheader()
            writer.writerows(day_rows)
    return list(rows)
```

- [ ] **Step 4: Implement the CLI command in `src/clipforge/cli.py`**

Docstring: add the line `    uv run clipforge schedule [--days 3 --start 2026-09-30 --dry-run]   # videos/out → posting slots`.

Imports (merge them in):

```python
import tomllib
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from clipforge.posting.export import SCHEDULE_DIR, write
from clipforge.posting.library import CONFIG_NAME, LEDGER_NAME as POSTING_LEDGER, PostingLedger, load_config, scan
from clipforge.posting.order import plan
```

(ruff's isort splits the long `library` import across lines. `LEDGER_NAME` is aliased because `inbox.LEDGER_NAME` is already imported.)

In `build_parser`, before the `status`/`resume` loop:

```python
    schedule = commands.add_parser(
        "schedule", help="plan posts from <folder>/out/ into daily slots (ADR-19)"
    )
    schedule.add_argument("--folder", default="videos", help="inbox folder (default: videos)")
    schedule.add_argument("--days", type=int, default=3, help="days to fill (default: 3)")
    schedule.add_argument("--start", help="first day, YYYY-MM-DD (default: today)")
    schedule.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
```

`main`: add the keyword parameter `now: datetime | None = None`. Right after the `set-webhook` branch (before the API_URL/API_TOKEN check), add:

```python
    if args.command == "schedule":
        return _schedule(args, now or datetime.now(UTC))
```

New function (after `_clip`):

```python
def _schedule(args: argparse.Namespace, now: datetime) -> int:
    """Fill open posting slots with clips from `<folder>/out/` that aren't scheduled yet."""
    folder = Path(args.folder)
    out_dir = folder / OUT_DIR
    config_path = folder / CONFIG_NAME
    try:
        config = load_config(config_path)
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        print(f"{config_path}: {exc}", file=sys.stderr)
        return 2
    if args.days < 1:
        print("--days must be at least 1", file=sys.stderr)
        return 2
    zone = ZoneInfo(config.timezone)
    try:
        start = date.fromisoformat(args.start) if args.start else now.astimezone(zone).date()
    except ValueError:
        print("--start must be YYYY-MM-DD", file=sys.stderr)
        return 2

    clips, warnings = scan(out_dir, config)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    ledger = PostingLedger(out_dir / POSTING_LEDGER)
    waiting = [clip for clip in clips if not ledger.is_scheduled(clip)]
    posts = plan(
        waiting, start=start, days=args.days, config=config, now=now, used=ledger.used_slots()
    )
    if not posts:
        reason = "no unscheduled clips" if not waiting else "no open slots in those days"
        print(f"nothing to schedule: {reason}")
        return 0
    for post in posts:
        local = post.slot.astimezone(zone)
        clip = post.clip
        where = f"{clip.folder}/{clip.clip_id}"
        print(f"{local:%a %d %b %H:%M}  {where}  {clip.score:.2f}  {clip.title}")
    left = len(waiting) - len(posts)
    if args.dry_run:
        print(f"dry run: {len(posts)} posts, {left} clips would stay queued")
        return 0
    days = write(posts, out_dir, folder / SCHEDULE_DIR, config)
    ledger.record(posts)
    print(f"{len(posts)} posts in {', '.join(str(d) for d in days)} · {left} clips still queued")
    return 0
```

- [ ] **Step 5: Run the tests and check they pass**

Run: `uv run pytest tests/posting tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Docs**

`docs/DECISIONS.md`, append:

```markdown
## ADR-19: Local posting queue over downloaded clips
Date: 2026-09-28 · Status: Accepted
Context: Clips go to one brand account on TikTok, Instagram Reels and YouTube Shorts (5–7 posts a day). Uploads are manual for now (ADR-3) through each platform's scheduler. The owner asked whether to test on TikTok first and promote winners.
Decision: `clipforge schedule` runs locally over `videos/out/` (what `clipforge clip` downloads). It assigns clips to daily slots in the audience's time zone, interleaving videos and creators with the best clips first. It writes day folders with the videos and per-platform captions, and keeps a ledger (`videos/out/.posting.json`) so no moment or slot is used twice, not even across re-cuts. Every clip goes to all three platforms in the same slot: no TikTok-first test, because a new account's first-day views are mostly noise and results on one platform predict the others poorly. Like the `clip` inbox, this is a client-side tool, not a pipeline stage, so ADR-9 is unaffected. Spec: docs/superpowers/specs/2026-09-28-posting-queue-design.md.
Consequences: No platform accounts or API audits are needed to start. Captions are a template until the Phase 3 `post.md` copy. Revisit TikTok-first ordering once each platform has about 30 posts and a performance import exists. API publishing (step B) needs its own ADR.
```

`docs/ARCHITECTURE.md`, add a section after "Storage and delivery":

```markdown
## Posting (local, ADR-19)

`uv run clipforge schedule` reads every `metadata.json` under `videos/out/` (the newest cut per `source_hash`; the credit comes from the job, ADR-20), skips moments already in `videos/out/.posting.json`, and fills the open slots from `videos/posting.toml` (default: 6 a day, America/New_York). The order is interleaved across videos and creators, best first, with a small bonus for fresh episodes. Output goes to `videos/schedule/<day>/`: `<HHMM>_<slug>.mp4` (a hard link), a `.txt` with the TikTok, Instagram and YouTube text, and `schedule.csv`. Upload by hand with each platform's scheduler. Code: `src/clipforge/posting/` (never imports Modal).
```

`CLAUDE.md`: in Commands, after the `clipforge clip` line, add `uv run clipforge schedule [--days 3]              # videos/out → posting slots + captions (ADR-19)`. In Layout, after the `inbox.py` line, add `  posting/          # local posting queue: library (scan, ledger), order, captions, export`.

`ROADMAP.md`: under Phase 2, after the "Command options" line, add and tick:
`- [x] Posting queue: \`clipforge schedule\` interleaves clips across videos into daily slots with per-platform captions (ADR-19)`

`videos/README.md`, append:

````markdown
## Scheduling posts

```bash
uv run clipforge schedule --dry-run   # preview the next 3 days
uv run clipforge schedule             # write them
uv run clipforge schedule --days 7    # a week at a time
```

Each run fills the next open slots with clips not posted yet, taking the newest cut of each video. For every day it writes `videos/schedule/<date>/`: the videos named `<time>_<title>.mp4` in posting order, a `.txt` next to each with the TikTok, Instagram and YouTube text, and `schedule.csv`. Upload each video to all three platforms at its time with their schedulers. `videos/out/.posting.json` remembers what's scheduled. Delete an entry there to free a moment again.

Settings go in `videos/posting.toml` (all optional):

```toml
timezone = "America/New_York"   # your audience's time zone
slots = ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]
hashtags = ["personalgrowth", "mindset", "masculinity", "podcast"]
```

The creator credit on each caption comes from the video's channel in `channels.toml`.
````

- [ ] **Step 7: Full check and a real run**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

Then run `uv run clipforge schedule --dry-run` against the real `videos/`. Expected: up to 18 posts over 3 days (today's past slots are skipped) from `billy_carton-Koa_smith-2`, highest scores first, a warning that `billy_carton-Koa_smith` is an older cut, and a no-credit warning until `videos/posting.toml` exists.

- [ ] **Step 8: Checkpoint.** Files: `src/clipforge/posting/export.py`, `src/clipforge/cli.py`, `tests/posting/test_export.py`, `tests/test_cli.py`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`.

---

### Task 6: Posting section in `videos/STATUS.md`

**Files:**
- Modify: `src/clipforge/status_report.py` (from the channels plan, ADR-20), `src/clipforge/cli.py` (`_schedule` rewrites the status)
- Test: `tests/test_status_report.py`

**Interfaces:**
- Consumes: `scan`, `PostingLedger`, `load_config`, `CONFIG_NAME`, `LEDGER_NAME` (posting library); `render` (status report).
- Produces: `render(...)` appends a `## Posting` section once `videos/out/.posting.json` exists.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_status_report.py`; merge the imports)

```python
from zoneinfo import ZoneInfo

from clipforge.models import PostingConfig, ScheduledPost
from clipforge.posting.library import PostingLedger, scan


def test_no_posting_section_before_first_schedule(tmp_path: Path) -> None:
    assert "## Posting" not in render(_inbox(tmp_path), BILLY, NOW)


def test_posting_section(tmp_path: Path) -> None:
    folder = _inbox(tmp_path)  # ep01: 2 clips in out/billy-garton/ep01
    clips, _ = scan(folder / "out", PostingConfig())
    slot = datetime(2026, 9, 30, 8, 0, tzinfo=ZoneInfo("America/New_York"))
    ledger = PostingLedger(folder / "out" / ".posting.json")
    ledger.record([ScheduledPost(slot=slot, clip=clips[0])])
    text = render(folder, BILLY, NOW)
    assert "## Posting\n\n| Channel | Scheduled | Queued |\n|---|---|---|\n" in text
    assert "| Billy Garton Jr. | 1 | 1 |" in text
    assert "1 clips queued: 1 days at 6 a day. Last scheduled post: Wed 30 Sep 08:00." in text
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_status_report.py -q`
Expected: `test_posting_section` FAILS (no "## Posting" in the output).

- [ ] **Step 3: Implement** in `status_report.py`

```python
from math import ceil
from zoneinfo import ZoneInfo

from clipforge.posting.library import CONFIG_NAME, PostingLedger, load_config, scan
from clipforge.posting.library import LEDGER_NAME as POSTING_LEDGER


def _channel_of(folder: str, channels: dict[str, Channel]) -> str | None:
    """`billy-garton/ep01` -> `billy-garton`; flat folders have no channel."""
    head, sep, _ = folder.partition("/")
    return head if sep and head in channels else None


def _posting_lines(folder: Path, channels: dict[str, Channel]) -> list[str]:
    out_dir = folder / OUT_DIR
    ledger_path = out_dir / POSTING_LEDGER
    if not ledger_path.exists():
        return []
    try:
        config = load_config(folder / CONFIG_NAME)
    except ValueError:
        return ["", "## Posting", "", f"`{CONFIG_NAME}` is invalid; `clipforge schedule` says why."]
    ledger = PostingLedger(ledger_path)
    clips, _ = scan(out_dir, config)
    queued = [clip for clip in clips if not ledger.is_scheduled(clip)]
    scheduled: dict[str | None, int] = {}
    for entry in ledger.entries:
        slug = _channel_of(entry.folder, channels)
        scheduled[slug] = scheduled.get(slug, 0) + 1
    waiting: dict[str | None, int] = {}
    for clip in queued:
        slug = _channel_of(clip.folder, channels)
        waiting[slug] = waiting.get(slug, 0) + 1
    seen = scheduled.keys() | waiting.keys()
    order: list[str | None] = [slug for slug in channels if slug in seen]
    if None in seen:
        order.append(None)
    lines = ["", "## Posting", "", "| Channel | Scheduled | Queued |", "|---|---|---|"]
    for slug in order:
        title = channels[slug].name if slug else "No channel"
        lines.append(f"| {_cell(title)} | {scheduled.get(slug, 0)} | {waiting.get(slug, 0)} |")
    per_day = len(config.slots)
    last = max(entry.slot for entry in ledger.entries).astimezone(ZoneInfo(config.timezone))
    lines += [
        "",
        f"{len(queued)} clips queued: {ceil(len(queued) / per_day)} days at {per_day} a day. "
        f"Last scheduled post: {last:%a %d %b %H:%M}.",
    ]
    return lines
```

In `render`, just before `return`, add `lines += _posting_lines(folder, channels)`.

In `cli._schedule`, after `ledger.record(posts)`, rewrite the status and ignore a broken `channels.toml` there (`clip` reports it). `load_channels`, `CHANNELS_NAME` and `status_report` are already imported in `cli.py` by the channels plan:

```python
    try:
        channels = load_channels(folder / CHANNELS_NAME)
    except ValueError:
        channels = {}
    status_report.write(folder, channels, datetime.now().astimezone())
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_status_report.py tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/status_report.py`, `src/clipforge/cli.py`, `tests/test_status_report.py`. Run the full check from Global Constraints first.

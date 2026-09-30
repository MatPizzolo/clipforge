# Plan A: Channels and batch submit — Implementation Plan

> **Status (2026-09-29): done.** All 3 tasks plus the final-review fix pass (5 Important findings fixed; 9 minors deferred). Ledger: `.superpowers/sdd/2026-09-28-a-channels-submit/progress.md`. Not deployed yet.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a channel's videos in `videos/<channel>/`, run `uv run clipforge clip`, and every new episode is uploaded and submitted with its channel, credit and permission, and the command exits. `--fetch` optionally waits and downloads the clips.

**Architecture:** `videos/channels.toml` maps slugs to a `Channel` contract. `JobInput` gains `channel: ChannelRef | None`, which plans B and C use to queue and label clips. `inbox.py` learns channel folders and a ledger with a status per video. `cli._clip` becomes submit-all-and-exit, and a new `_fetch` waits for every submitted job together and downloads each one when it's done.

**Tech Stack:** Python 3.12 stdlib (`tomllib`), pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-posting-assistant-design.md` §3 (ADR-22).

**Git:** the owner runs every git command. "Checkpoint" steps list the changed files; don't run git.

**The code moves.** Another session edits this repo at the same time (reframing, captions). Read `cli.py`, `inbox.py` and `models.py` before each task. Where the snippets here differ from the current code in unrelated details, keep the current code and apply only this plan's change. Report what you adapted. Before adding the ADR, check that ADR-22 is still free in `docs/DECISIONS.md`, and take the next free number if it isn't.

## Global Constraints

- `inbox.py` and `cli.py` never import `modal` (ADR-9). Uploads and downloads stay behind the existing `Uploader` and `Downloader` protocols.
- Channel slugs: `[a-z0-9][a-z0-9-]{0,39}`, never `out` or `schedule`. File: `videos/channels.toml`.
- Ledger keys are paths relative to the inbox folder, with `/` separators: `"ep.mp4"` for loose videos, `"billy-garton/ep.mp4"` for channel videos. Old string values load as `InboxEntry(job_id=value, status="fetched")`.
- Channel jobs get `channel = ChannelRef(slug, name)`, `source_credit = name`, `permission = channel.permission` (unless `--perm` is given) and `source_label = <video stem>`. Loose videos get no channel.
- `--fetch` output goes to `videos/out/<channel>/<stem>/`, or `videos/out/<stem>/` for loose videos, with `-2`, `-3`… for re-cuts. The poll interval is 15 s, with no overall timeout. A job that failed stays `submitted` in the ledger, so a later `clipforge resume` plus `--fetch` still downloads it.
- Before every checkpoint: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.

## Review Focus

1. **The owner's existing `.clipforge.json`** (old string format). It loads, and nothing is resubmitted or fetched again. Test: `test_ledger_reads_old_format` (Task 2).
2. **A channel folder name with a typo** (`videos/billy-gartn/`). It gets a warning and is not uploaded. Test: `test_unknown_channel_folder_is_skipped_with_warning` (Task 2).
3. **The same file name in two channels.** They get separate keys and separate output folders. Test: `test_same_name_in_two_channels` (Task 2).
4. **Ctrl-C during `--fetch`, or a failed job that is resumed later.** The next `--fetch` downloads it, and nothing is uploaded again. Tests: `test_fetch_downloads_later_and_keeps_failed_submitted` (Task 3), `test_clip_submits_and_exits` (Task 3).
5. **An old `metadata.json` or `JobInput` without `channel`.** It still validates (the field defaults to `None`). Test: `test_job_input_channel_is_optional` (Task 1).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/clipforge/models.py` | + `Channel`, `ChannelRef`, `InboxEntry`; `JobInput.channel` (Task 1) |
| `src/clipforge/inbox.py` | + `CHANNELS_NAME`, `RESERVED`, `load_channels`, `InboxVideo`, `inbox_videos`; `pending` and `Ledger` reworked (Tasks 1–2) |
| `src/clipforge/cli.py` | `_clip` submits and exits; `--fetch` / `_fetch`; `_job_input`, `_video_for`, `_out_dir` (Task 3) |
| `tests/test_models.py`, `tests/test_inbox.py`, `tests/test_cli.py` | Tests |
| `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md` | ADR-22, docs, roadmap (Task 3) |

---

### Task 1: Channel contracts and `channels.toml`

**Files:**
- Modify: `src/clipforge/models.py`, `src/clipforge/inbox.py`
- Test: `tests/test_models.py`, `tests/test_inbox.py`

**Interfaces:**
- Produces:
  - `models.Channel(name: str, url: AnyHttpUrl | None = None, permission: Permission)`
  - `models.ChannelRef(slug: str, name: str)`
  - `models.InboxEntry(job_id: str, status: Literal["submitted", "fetched"] = "submitted", out: str | None = None)`
  - `JobInput.channel: ChannelRef | None = None`
  - `inbox.CHANNELS_NAME = "channels.toml"`, `inbox.RESERVED = frozenset({"out", "schedule"})`
  - `inbox.load_channels(path: Path) -> dict[str, Channel]`. It raises `ValueError`, which covers `TOMLDecodeError` and pydantic's `ValidationError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
from clipforge.models import ChannelRef, JobInput


def test_job_input_channel_is_optional() -> None:
    plain = JobInput.model_validate({"source_path": "uploads/x.mp4", "permission": "own"})
    assert plain.channel is None
    tagged = JobInput.model_validate(
        {"source_path": "uploads/x.mp4", "permission": "creator_agreement",
         "channel": {"slug": "billy-garton", "name": "Billy Garton Jr."}}
    )  # fmt: skip
    assert tagged.channel == ChannelRef(slug="billy-garton", name="Billy Garton Jr.")
```

Append to `tests/test_inbox.py` (merge the imports):

```python
from clipforge.inbox import load_channels
from clipforge.models import Permission

CHANNELS = (
    '[billy-garton]\nname = "Billy Garton Jr."\n'
    'url = "https://www.youtube.com/@example"\npermission = "creator_agreement"\n'
)


def test_load_channels(tmp_path: Path) -> None:
    path = tmp_path / "channels.toml"
    assert load_channels(path) == {}
    path.write_text(CHANNELS)
    [(slug, channel)] = load_channels(path).items()
    assert slug == "billy-garton"
    assert channel.name == "Billy Garton Jr."
    assert channel.permission is Permission.CREATOR_AGREEMENT


@pytest.mark.parametrize(
    "text",
    [
        '[Billy]\nname = "B"\npermission = "own"\n',  # uppercase slug
        '[out]\nname = "B"\npermission = "own"\n',  # reserved
        '[b]\nname = "B"\n',  # permission missing
        '[b]\nname = "B"\npermission = "stolen"\n',
        '[b]\nname = ""\npermission = "own"\n',
        'name = "not a table"\n',
        "[b\n",  # not TOML
    ],
)
def test_bad_channels_file(tmp_path: Path, text: str) -> None:
    path = tmp_path / "channels.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_channels(path)
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_models.py tests/test_inbox.py -q`
Expected: FAIL with `ImportError: cannot import name 'ChannelRef'`.

- [ ] **Step 3: Implement**

`models.py`: define these before `JobInput`, since `JobInput` references `ChannelRef` (`Permission` and `AnyHttpUrl` are already imported):

```python
# ---- channels (videos/channels.toml; ADR-22) ----------------------------------------------


class Channel(Contract):
    """One `[slug]` table of `videos/channels.toml`; its videos live in `videos/<slug>/`."""

    name: str = Field(min_length=1)  # the creator credit shown in captions
    url: AnyHttpUrl | None = None  # for reference only
    permission: Permission


class ChannelRef(Contract):
    """The channel a job's video came from; jobs with one are queued for posting (ADR-23)."""

    slug: str
    name: str
```

In `JobInput`, after `notify`, add:

```python
    channel: ChannelRef | None = None  # set by `clipforge clip` for channel folders (ADR-22)
```

After `JobInput` (next to the other local contracts, or at the end of the file):

```python
class InboxEntry(Contract):
    """One video in `videos/.clipforge.json`."""

    job_id: str
    status: Literal["submitted", "fetched"] = "submitted"
    out: str | None = None  # where `--fetch` put the clips, relative to videos/out/
```

`inbox.py`: add `import tomllib` and `from clipforge.models import Channel, InboxEntry`. Then add:

```python
CHANNELS_NAME = "channels.toml"
RESERVED = frozenset({OUT_DIR, "schedule"})  # folders in videos/ that are never channels
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def load_channels(path: Path) -> dict[str, Channel]:
    """`videos/channels.toml`, or no channels if it's missing. Raises ValueError when invalid."""
    if not path.exists():
        return {}
    channels: dict[str, Channel] = {}
    for slug, fields in tomllib.loads(path.read_text()).items():
        if not _SLUG.fullmatch(slug) or slug in RESERVED:
            raise ValueError(
                f"channel {slug!r}: use lowercase letters, digits and -, and not out/schedule"
            )
        if not isinstance(fields, dict):
            raise ValueError(f"channel {slug!r}: expected a [{slug}] table")
        channels[slug] = Channel.model_validate(fields)
    return channels
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_models.py tests/test_inbox.py -q`
Expected: PASS. `InboxEntry` is imported but not used until Task 2; add a `# noqa: F401` only if ruff complains in between.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/models.py`, `src/clipforge/inbox.py`, `tests/test_models.py`, `tests/test_inbox.py`.

---

### Task 2: Channel folders and a ledger with status

**Files:**
- Modify: `src/clipforge/inbox.py` (`Ledger`, `pending`; new `InboxVideo`, `inbox_videos`), `src/clipforge/cli.py` (the minimal call-site update)
- Test: `tests/test_inbox.py`. Replace `test_pending_lists_new_videos_only` and `test_ledger_persists`.

**Interfaces:**
- Consumes: `Channel`, `InboxEntry`.
- Produces:
  - `@dataclass(frozen=True) class InboxVideo: path: Path; key: str; channel: str | None`
  - `inbox_videos(folder: Path, channels: dict[str, Channel]) -> tuple[list[InboxVideo], list[str]]`
  - `pending(folder: Path, ledger: Ledger, channels: dict[str, Channel]) -> tuple[list[InboxVideo], list[str]]`
  - `Ledger.get(key) -> InboxEntry | None`, `.job_id(key) -> str | None`, `.record(key, job_id)` (status `submitted`), `.update(key, entry)`, `.submitted() -> list[str]` (sorted keys with status `submitted`)

- [ ] **Step 1: Write the failing tests**

```python
from clipforge.inbox import InboxVideo, inbox_videos
from clipforge.models import Channel, InboxEntry

BILLY = {"billy-garton": Channel(name="Billy Garton Jr.", permission=Permission.CREATOR_AGREEMENT)}


def test_pending_lists_new_videos_only(tmp_path: Path) -> None:
    _video(tmp_path, "b.mp4")
    _video(tmp_path, "a.MOV")
    _video(tmp_path, "notes.txt")
    (tmp_path / "out").mkdir()
    _video(tmp_path / "out", "clip.mp4")  # results are never inputs
    ledger = Ledger(tmp_path / ".clipforge.json")
    assert [v.key for v in pending(tmp_path, ledger, {})[0]] == ["a.MOV", "b.mp4"]
    ledger.record("a.MOV", "20260928-aaaaaaaa-0001")
    assert [v.key for v in pending(tmp_path, ledger, {})[0]] == ["b.mp4"]


def test_channel_folder_videos(tmp_path: Path) -> None:
    (tmp_path / "billy-garton").mkdir()
    _video(tmp_path / "billy-garton", "ep02.mp4")
    _video(tmp_path / "billy-garton", "ep01.mp4")
    _video(tmp_path, "loose.mp4")
    videos, warnings = inbox_videos(tmp_path, BILLY)
    folder = tmp_path / "billy-garton"
    assert videos == [
        InboxVideo(folder / "ep01.mp4", "billy-garton/ep01.mp4", "billy-garton"),
        InboxVideo(folder / "ep02.mp4", "billy-garton/ep02.mp4", "billy-garton"),
        InboxVideo(tmp_path / "loose.mp4", "loose.mp4", None),
    ]
    assert warnings == []


def test_unknown_channel_folder_is_skipped_with_warning(tmp_path: Path) -> None:
    (tmp_path / "billy-gartn").mkdir()
    _video(tmp_path / "billy-gartn", "ep01.mp4")
    (tmp_path / "empty").mkdir()  # no videos: no warning
    (tmp_path / "schedule").mkdir()
    _video(tmp_path / "schedule", "0800_x.mp4")  # reserved, never an input
    videos, warnings = inbox_videos(tmp_path, BILLY)
    assert videos == []
    assert warnings == ["billy-gartn/: not in channels.toml, skipped"]


def test_same_name_in_two_channels(tmp_path: Path) -> None:
    channels = {**BILLY, "other": Channel(name="Other", permission=Permission.OWN)}
    for slug in channels:
        (tmp_path / slug).mkdir()
        _video(tmp_path / slug, "ep01.mp4")
    keys = [v.key for v in inbox_videos(tmp_path, channels)[0]]
    assert keys == ["billy-garton/ep01.mp4", "other/ep01.mp4"]


def test_ledger_persists_status(tmp_path: Path) -> None:
    path = tmp_path / ".clipforge.json"
    ledger = Ledger(path)
    ledger.record("billy-garton/ep.mp4", "J1")
    ledger.record("b.mp4", "J2")
    ledger.update("b.mp4", InboxEntry(job_id="J2", status="fetched", out="b"))
    reloaded = Ledger(path)
    assert reloaded.job_id("billy-garton/ep.mp4") == "J1"
    assert reloaded.get("b.mp4") == InboxEntry(job_id="J2", status="fetched", out="b")
    assert reloaded.get("other.mp4") is None
    assert reloaded.submitted() == ["billy-garton/ep.mp4"]


def test_ledger_reads_old_format(tmp_path: Path) -> None:
    path = tmp_path / ".clipforge.json"
    path.write_text('{"billy_carton-Koa_smith.mp4": "20260928-b8193698-ba91"}')
    ledger = Ledger(path)
    assert ledger.get("billy_carton-Koa_smith.mp4") == InboxEntry(
        job_id="20260928-b8193698-ba91", status="fetched"
    )
    assert ledger.submitted() == []
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_inbox.py -q`
Expected: FAIL with `ImportError: cannot import name 'InboxVideo'`.

- [ ] **Step 3: Implement** in `inbox.py` (add `from dataclasses import dataclass`)

```python
class Ledger:
    """`{video key: InboxEntry}` for videos already submitted, kept next to the videos. Keys are
    paths relative to the inbox folder ("ep.mp4", "billy-garton/ep.mp4"). The old format,
    `{name: job_id}`, loads as already fetched."""

    def __init__(self, path: Path) -> None:
        self.path = path
        raw: dict[str, object] = json.loads(path.read_text()) if path.exists() else {}
        self._data = {
            key: InboxEntry(job_id=value, status="fetched")
            if isinstance(value, str)
            else InboxEntry.model_validate(value)
            for key, value in raw.items()
        }

    def get(self, key: str) -> InboxEntry | None:
        return self._data.get(key)

    def job_id(self, key: str) -> str | None:
        entry = self._data.get(key)
        return entry.job_id if entry else None

    def submitted(self) -> list[str]:
        """Keys whose clips haven't been fetched (running, done or failed on Modal)."""
        return sorted(k for k, e in self._data.items() if e.status == "submitted")

    def record(self, key: str, job_id: str) -> None:
        self.update(key, InboxEntry(job_id=job_id))

    def update(self, key: str, entry: InboxEntry) -> None:
        self._data[key] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: e.model_dump(mode="json", exclude_none=True) for k, e in self._data.items()}
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


@dataclass(frozen=True)
class InboxVideo:
    path: Path
    key: str  # ledger key, relative to the inbox folder
    channel: str | None  # slug, or None for a loose video


def inbox_videos(
    folder: Path, channels: dict[str, Channel]
) -> tuple[list[InboxVideo], list[str]]:
    """Videos directly in `folder` and in its channel subfolders, sorted by key, plus warnings
    for subfolders with videos that aren't in channels.toml."""
    videos = [InboxVideo(p, p.name, None) for p in folder.iterdir() if is_video(p)]
    warnings: list[str] = []
    subfolders = (
        p for p in folder.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in RESERVED
    )  # fmt: skip
    for sub in sorted(subfolders):
        inside = [p for p in sub.iterdir() if is_video(p)]
        if sub.name not in channels:
            if inside:
                warnings.append(f"{sub.name}/: not in {CHANNELS_NAME}, skipped")
            continue
        videos += [InboxVideo(p, f"{sub.name}/{p.name}", sub.name) for p in inside]
    return sorted(videos, key=lambda v: v.key.lower()), warnings


def pending(
    folder: Path, ledger: Ledger, channels: dict[str, Channel]
) -> tuple[list[InboxVideo], list[str]]:
    """Videos not submitted yet (plus the warnings from `inbox_videos`)."""
    videos, warnings = inbox_videos(folder, channels)
    return [v for v in videos if ledger.get(v.key) is None], warnings
```

Minimal `cli._clip` update so the suite still runs: `videos, _ = pending(folder, ledger, {})`, and use `video.path` and `video.key` where it used the path and `video.name`. Task 3 rewrites `_clip`.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_inbox.py tests/test_cli.py -q`
Expected: inbox tests PASS. `test_clip_one_file_end_to_end` fails only on its ledger line; change that expectation to `{"My Talk.mp4": {"job_id": job_id, "status": "submitted"}}` for now (Task 3 changes it again).

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/inbox.py`, `src/clipforge/cli.py`, `tests/test_inbox.py`, `tests/test_cli.py`.

---

### Task 3: Submit-all-and-exit, `--fetch`, docs

**Files:**
- Modify: `src/clipforge/cli.py`
- Modify: `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_channels`, `CHANNELS_NAME`, `InboxVideo`, `pending`, `Ledger`, `InboxEntry`, `ChannelRef`, `progress_line`, `MAX_NETWORK_ERRORS`.
- Produces: `POLL_INTERVAL_S = 15.0`; `class JobReader(Protocol): def get_job(self, job_id: str) -> JobView: ...`; `_fetch(keys: list[str], ledger: Ledger, folder: Path, client: JobReader, sleep: Callable[[float], object], downloader: Downloader) -> int`; `_out_dir(folder: Path, key: str) -> Path`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`; merge the imports)

```python
from clipforge.cli import _fetch
from clipforge.inbox import Ledger
from clipforge.models import ChannelRef, InboxEntry, JobError, Permission

CHANNELS_TOML = '[billy-garton]\nname = "Billy Garton Jr."\npermission = "creator_agreement"\n'


def _channel_inbox(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "videos"
    (folder / "billy-garton").mkdir(parents=True)
    (folder / "channels.toml").write_text(CHANNELS_TOML)
    for name in names:
        (folder / "billy-garton" / name).write_bytes(name.encode())
    return folder


def test_clip_submits_and_exits(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4", "ep02.mp4")
    uploader, downloader = FakeUploader(), FakeDownloader()
    assert _clip(harness, api, uploader, "--folder", str(folder), downloader=downloader) == 0
    assert [local.name for local, _ in uploader.puts] == ["ep01.mp4", "ep02.mp4"]
    assert downloader.gets == []  # no waiting, no download without --fetch
    jobs = [harness.store.get(j) for j in harness.store.list_job_ids()]
    assert {j.input.source_label for j in jobs} == {"ep01", "ep02"}
    ref = ChannelRef(slug="billy-garton", name="Billy Garton Jr.")
    assert all(j.input.channel == ref for j in jobs)
    assert all(j.input.source_credit == "Billy Garton Jr." for j in jobs)
    assert all(j.input.permission is Permission.CREATOR_AGREEMENT for j in jobs)
    assert Ledger(folder / ".clipforge.json").submitted() == [
        "billy-garton/ep01.mp4", "billy-garton/ep02.mp4"
    ]  # fmt: skip
    # a second run finds nothing new and uploads nothing
    assert _clip(harness, api, uploader, "--folder", str(folder), downloader=downloader) == 0
    assert len(uploader.puts) == 2


def test_clip_fetch_downloads_into_channel_folders(
    harness: Harness, api: TestClient, tmp_path: Path
) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    downloader = FakeDownloader()
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder), "--fetch",
                 downloader=downloader) == 0  # fmt: skip
    out = folder / "out" / "billy-garton"
    assert [dest for _, dest in downloader.gets] == [out / "ep01"]
    entry = Ledger(folder / ".clipforge.json").get("billy-garton/ep01.mp4")
    assert entry is not None
    assert (entry.status, entry.out) == ("fetched", "billy-garton/ep01")


def test_clip_bad_channels_file_exits_2(
    harness: Harness, api: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    (folder / "channels.toml").write_text('[billy-garton]\nname = "B"\n')
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder)) == 2
    assert "channels.toml" in capsys.readouterr().err


class FakeReader:
    def __init__(self, views: dict[str, JobView]) -> None:
        self.views = views

    def get_job(self, job_id: str) -> JobView:
        return self.views[job_id]


def test_fetch_downloads_later_and_keeps_failed_submitted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "videos"
    ledger = Ledger(folder / ".clipforge.json")
    ledger.record("a.mp4", "JA")
    ledger.record("b.mp4", "JB")
    failed = _view(JobStatus.FAILED).model_copy(
        update={"error": JobError(stage=StageName.TRANSCRIBE, error_type="E", message="boom")}
    )
    reader = FakeReader({"JA": _view(JobStatus.DONE), "JB": failed})
    downloader = FakeDownloader()
    code = _fetch(["a.mp4", "b.mp4"], ledger, folder, reader, lambda _s: None, downloader)
    assert code == 1
    assert ledger.get("a.mp4") == InboxEntry(job_id="JA", status="fetched", out="a")
    assert ledger.get("b.mp4") == InboxEntry(job_id="JB")  # still submitted: resume + fetch
    assert "b.mp4: failed at transcribe: boom · clipforge resume JB" in capsys.readouterr().out
```

Change the last line of `test_clip_one_file_end_to_end` to the submitted shape, `{"My Talk.mp4": {"job_id": job_id, "status": "submitted"}}`, and add `"--fetch"` to that test's arguments if it asserts on downloads. With `--fetch` the expectation becomes `{"My Talk.mp4": {"job_id": job_id, "status": "fetched", "out": "My Talk"}}`. Keep whichever form matches what the test checks.

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL with `ImportError: cannot import name '_fetch'`.

- [ ] **Step 3: Implement** in `cli.py`

Imports: add `CHANNELS_NAME, InboxVideo, load_channels` to the `clipforge.inbox` import, and `Channel, ChannelRef, InboxEntry` to the `clipforge.models` import. Parser: add `clip.add_argument("--fetch", action="store_true", help="wait for the jobs and download the clips into <folder>/out/")`. Keep `--no-wait` accepted as a no-op for compatibility: `help="(default now) submit and exit"`.

```python
POLL_INTERVAL_S = 15.0  # one status check per waiting job per round


class JobReader(Protocol):
    def get_job(self, job_id: str) -> JobView: ...


def _video_for(folder: Path, path: Path, channels: dict[str, Channel]) -> InboxVideo:
    """A video named on the command line: a channel video when it sits in a channel folder."""
    parent = path.resolve().parent
    if parent.parent == folder.resolve() and parent.name in channels:
        return InboxVideo(path, f"{parent.name}/{path.name}", parent.name)
    return InboxVideo(path, path.name, None)


def _job_input(
    settings: Settings,
    options: dict[str, str],
    video: InboxVideo,
    channels: dict[str, Channel],
    remote: str,
) -> JobInput:
    """Channel videos carry their channel, credit and permission (ADR-22)."""
    options = dict(options)
    update: dict[str, object] = {"source_label": video.path.stem}
    if video.channel is not None:
        channel = channels[video.channel]
        options.setdefault("perm", channel.permission.value)
        options["credit"] = channel.name
        update["channel"] = ChannelRef(slug=video.channel, name=channel.name)
    return build_job_input(settings, options, None, source_path=remote).model_copy(update=update)


def _clip(
    args: argparse.Namespace,
    settings: Settings,
    client: ApiClient,
    sleep: Callable[[float], object],
    uploader: Uploader,
    downloader: Downloader,
) -> int:
    """Upload and submit every new video (channel folders included), then exit. With
    `--fetch`, also wait for every submitted job and download its clips."""
    folder = Path(args.folder)
    try:
        channels = load_channels(folder / CHANNELS_NAME)
    except ValueError as exc:
        print(f"{folder / CHANNELS_NAME}: {exc}", file=sys.stderr)
        return 2
    ledger = Ledger(folder / LEDGER_NAME)
    if args.file is not None:
        path = Path(args.file)
        if not is_video(path):
            print(f"{path}: not a video file (.mp4 .mov .mkv .webm .m4v .avi)", file=sys.stderr)
            return 2
        video = _video_for(folder, path, channels)
        previous = ledger.job_id(video.key)
        if previous is not None and not args.again:
            print(f"{video.key} was already submitted as job {previous}; use --again to re-cut",
                  file=sys.stderr)  # fmt: skip
            return 2
        videos = [video]
    else:
        folder.mkdir(parents=True, exist_ok=True)
        videos, warnings = pending(folder, ledger, channels)
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if not videos and not (args.fetch and ledger.submitted()):
            print(f"no new videos in {folder}/ (drop .mp4/.mov/... files there)")
            return 0

    options = {
        key: value
        for key, value in (
            ("n", args.n),
            ("score", args.min_score),
            ("len", args.len),
            ("lang", args.lang),
        )
        if value is not None
    }
    for video in videos:
        remote = volume_path(video.path)
        try:
            job_input = _job_input(settings, options, video, channels, remote)
        except CommandError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"uploading {video.key} ...", flush=True)
        uploader.put(video.path, remote)
        job_id = client.create_job(job_input)
        ledger.record(video.key, job_id)
        print(f"{video.key}: job {job_id}")
    if not args.fetch:
        if videos:
            print(f"{len(videos)} submitted; clips reach Telegram as they're ready "
                  "(or run `clipforge clip --fetch` to download them)")  # fmt: skip
        return 0
    return _fetch(ledger.submitted(), ledger, folder, client, sleep, downloader)


def _fetch(
    keys: list[str],
    ledger: Ledger,
    folder: Path,
    client: JobReader,
    sleep: Callable[[float], object],
    downloader: Downloader,
) -> int:
    """Check each job in turn until every one is done or failed, downloading each done job
    right away. Failed jobs stay `submitted`, so `clipforge resume` + `--fetch` still works.
    Safe to interrupt."""
    left = list(keys)
    last: dict[str, str] = {}
    errors = 0
    code = 0
    while left:
        for key in list(left):
            entry = ledger.get(key)
            assert entry is not None
            try:
                view = client.get_job(entry.job_id)
            except httpx.TransportError:
                errors += 1
                if errors >= MAX_NETWORK_ERRORS:
                    raise
                continue
            errors = 0
            line = progress_line(view)
            if last.get(key) != line:
                print(f"{key}: {line}", flush=True)
                last[key] = line
            if view.status is JobStatus.DONE:
                dest = _out_dir(folder, key)
                print(f"{key}: downloading the clips into {dest}/ ...", flush=True)
                downloader.get(f"{entry.job_id}/output", dest)
                out = dest.relative_to(folder / OUT_DIR).as_posix()
                ledger.update(key, InboxEntry(job_id=entry.job_id, status="fetched", out=out))
                left.remove(key)
            elif view.status is JobStatus.FAILED:
                error = view.error
                where = f"{error.stage}: {error.message}" if error else "unknown error"
                print(f"{key}: failed at {where} · clipforge resume {entry.job_id}")
                left.remove(key)
                code = 1
        if left:
            sleep(POLL_INTERVAL_S)
    return code


def _out_dir(folder: Path, key: str) -> Path:
    """`<folder>/out/[<channel>/]<video stem>/`, or `-2/`, `-3/`... so a re-cut never
    overwrites."""
    base = folder / OUT_DIR / Path(key).with_suffix("")
    candidate, n = base, 1
    while candidate.exists() and any(candidate.iterdir()):
        n += 1
        candidate = base.with_name(f"{base.name}-{n}")
    return candidate
```

Delete `_wait_for` if nothing uses it any more. `wait()` stays because `run` uses it. Update the module docstring's `clip` line to `uv run clipforge clip [videos/<channel>/ep.mp4] [--fetch]   # videos/ inbox → jobs`.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_cli.py tests/test_inbox.py tests/test_models.py -q`
Expected: PASS. If other existing `clip` tests relied on the old wait-and-download default, add `--fetch` to them.

- [ ] **Step 5: Docs**

`docs/DECISIONS.md`, append (renumber if ADR-22 was taken meanwhile):

```markdown
## ADR-22: Channel folders and batch submit
Date: 2026-09-28 · Status: Accepted
Context: The owner clips whole podcast channels, starting with 11 episodes of Billy Garton Jr. (creator agreement), with more channels in the same niche later. Every clip needs the right credit, and the posting assistant (ADR-23) needs to know each job's channel. Waiting for each video in turn took hours.
Decision: Videos go in `videos/<channel>/`. `videos/channels.toml` gives each channel a credit name, an optional url and a permission. `clipforge clip` submits every new video with `JobInput.channel`, `source_credit`, `permission` and `source_label`, then exits. `--fetch` waits for all submitted jobs together and downloads each into `videos/out/<channel>/<episode>/`. The inbox ledger keeps `{job_id, status}` per video; the old format loads as fetched. Spec: docs/superpowers/specs/2026-09-28-posting-assistant-design.md §3.
Consequences: Credit and permission are set once per channel. A video moved into a channel folder counts as new and is submitted again; this is cheap because the transcript and highlights are cached by source hash, and posting skips overlapping moments.
```

`docs/ARCHITECTURE.md`, add after "Storage and delivery":

```markdown
## Local inbox (ADR-22)

`videos/<channel>/*.mp4` plus `videos/channels.toml` (credit, url and permission per channel). `uv run clipforge clip` uploads and submits every new video with its channel, then exits. `--fetch` waits for the jobs in parallel and downloads each into `videos/out/<channel>/<episode>/`. `videos/.clipforge.json` keeps each video's job and whether it was fetched.
```

`CLAUDE.md` Commands: change the `clipforge clip` line to `uv run clipforge clip [videos/<channel>/<file>] [--fetch]   # videos/ inbox → jobs (ADR-22); --fetch downloads the clips`.

`ROADMAP.md` Phase 2, after "Command options", add and tick:
`- [x] Channel folders + \`channels.toml\` (credit, permission), batch submit, \`--fetch\` (ADR-22)`

`videos/README.md`: rewrite the top section:

````markdown
# videos/

One folder per channel, described in `channels.toml`:

```
videos/
  channels.toml
  billy-garton/ep01.mp4 ep02.mp4 ...
```

```toml
# channels.toml
[billy-garton]
name = "Billy Garton Jr."                # the credit on every clip
url = "https://www.youtube.com/@..."     # optional
permission = "creator_agreement"         # own | creator_agreement | clipping_program | cc_by
```

```bash
uv run clipforge clip                    # submit every new video in every channel, then exit
uv run clipforge clip --fetch            # ...and wait, then download the clips into out/
uv run clipforge clip "videos/billy-garton/ep01.mp4" --again   # re-cut one
```

Videos directly in `videos/` still work, without a channel (they aren't queued for posting).
````

Keep the rest of the README (options, output layout), updating paths to `out/<channel>/<episode>/`.

- [ ] **Step 6: Full check**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 7: Checkpoint.** Files: `src/clipforge/cli.py`, `tests/test_cli.py`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`.

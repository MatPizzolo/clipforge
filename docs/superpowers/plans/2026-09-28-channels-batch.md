> **Superseded (2026-09-28). Do not implement.** See §3 of `docs/superpowers/specs/2026-09-28-posting-assistant-design.md`; a new plan replaces this one.

# Channels, batch clipping and STATUS.md — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a channel's videos in `videos/<channel>/`, run `uv run clipforge clip` once, and get every episode clipped in parallel, credited to its creator, downloaded into `videos/out/<channel>/<episode>/`, and listed in an always-current `videos/STATUS.md`.

**Architecture:** `videos/channels.toml` maps channel slugs to a `Channel` contract (credit, url, permission). `inbox.py` learns channel folders and a status-carrying ledger (`InboxEntry`). `cli._clip` splits into submit-all, then `_collect` (poll every waiting job, download each when done). A new Modal-free module, `status_report.py`, renders `STATUS.md` from the ledger and the downloaded `metadata.json` files. `clipforge report` rewrites it without the API.

**Tech Stack:** Python 3.12 stdlib (`tomllib`), pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-channels-batch-design.md`

**Git:** the owner runs every git command. "Checkpoint" steps list the changed files; don't run git.

**The code moves.** Another session is changing `cli.py` and `inbox.py`, for example the Volume downloader that replaced the zip. Read both files before each task. Where this plan's snippets differ from the current code in unrelated details, keep the current code and apply only this plan's change. Report what you adapted.

## Global Constraints

- `inbox.py`, `status_report.py` and `cli.py` never import `modal` (ADR-9). Uploads and downloads stay behind the existing `Uploader`/`Downloader` protocols.
- Channel slugs: `[a-z0-9][a-z0-9-]{0,39}`, never `out` or `schedule`. File: `videos/channels.toml`.
- Ledger keys are paths relative to the inbox folder, with `/` separators: `"ep.mp4"` for loose videos, `"billy-garton/ep.mp4"` for channel videos. Old string values load as `InboxEntry(job_id=value, status="done")`.
- Channel jobs get `source_credit = channel.name`, `permission = channel.permission` (unless `--perm` is given) and `source_label = <video stem>`.
- Output: `videos/out/<channel>/<stem>/` (or `videos/out/<stem>/` for loose videos), with `-2`, `-3`… for re-cuts.
- Poll interval while waiting for a batch: 15 s. There is no overall timeout: the sweeper fails stalled jobs, and Ctrl-C is safe because the next run picks up `submitted` entries.
- `STATUS.md` is fully regenerated each time, never edited in place.
- Before every checkpoint: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.

## Review Focus

1. **Ctrl-C mid-batch, or `--no-wait`.** The next `clipforge clip` waits for those jobs and downloads them, without uploading or submitting again. Test: `test_clip_picks_up_earlier_submissions` (Task 3).
2. **The owner's existing `.clipforge.json`** (old string format). It loads, and nothing is resubmitted. Test: `test_ledger_reads_old_format` (Task 2).
3. **A channel folder name with a typo** (`videos/billy-gartn/`). It gets a warning, is not uploaded, and doesn't crash the run. Test: `test_unknown_channel_folder_is_skipped_with_warning` (Task 2).
4. **The same file name in two channels** (`ep01.mp4`). They get separate ledger keys and separate output folders. Test: `test_same_name_in_two_channels` (Task 2).
5. **A job that failed and was then resumed.** The next `clip` notices it's done and downloads it. A job still failed is reported, not dropped. Test: `test_collect_downloads_resumed_and_reports_failed` (Task 3).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/clipforge/models.py` | + `Channel`, `InboxEntry` (Task 1) |
| `src/clipforge/inbox.py` | + `CHANNELS_NAME`, `load_channels`, `InboxVideo`, `inbox_videos`; `pending` and `Ledger` reworked (Tasks 1–2) |
| `src/clipforge/cli.py` | `_clip` split into submit + `_collect`; `report` command (Tasks 3–4) |
| `src/clipforge/status_report.py` | `render`, `write` for `videos/STATUS.md` (Task 4) |
| `tests/test_inbox.py`, `tests/test_cli.py`, `tests/test_status_report.py` | Tests |
| `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md` | ADR-20, docs, roadmap (Task 4) |

---

### Task 1: Channel config

**Files:**
- Modify: `src/clipforge/models.py`, `src/clipforge/inbox.py`
- Test: `tests/test_inbox.py`

**Interfaces:**
- Produces: `models.Channel(name: str, url: AnyHttpUrl | None, permission: Permission)`; `models.InboxEntry(job_id: str, status: Literal["submitted", "done", "failed"], out: str | None, error: str | None)`; `inbox.CHANNELS_NAME = "channels.toml"`; `inbox.RESERVED = frozenset({"out", "schedule"})`; `inbox.load_channels(path: Path) -> dict[str, Channel]` (raises `ValueError`, which covers `TOMLDecodeError` and pydantic's `ValidationError`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_inbox.py`; merge the imports)

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

Run: `uv run pytest tests/test_inbox.py -q`
Expected: FAIL with `ImportError: cannot import name 'load_channels'`.

- [ ] **Step 3: Implement**

`models.py`, after `JobInput` (it uses `Permission` and `AnyHttpUrl`, both already imported):

```python
# ---- local inbox (videos/, `clipforge clip`; ADR-20) --------------------------------------


class Channel(Contract):
    """One `[slug]` table of `videos/channels.toml`; its videos live in `videos/<slug>/`."""

    name: str = Field(min_length=1)  # the creator credit shown in captions
    url: AnyHttpUrl | None = None  # for reference only
    permission: Permission


class InboxEntry(Contract):
    """One video in `videos/.clipforge.json`."""

    job_id: str
    status: Literal["submitted", "done", "failed"] = "submitted"
    out: str | None = None  # result folder, relative to videos/out/
    error: str | None = None  # "<stage>: <message>" when failed
```

`inbox.py`: add `import tomllib`, and `from clipforge.models import Channel, InboxEntry` (`InboxEntry` is used in Task 2). Then add:

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

Run: `uv run pytest tests/test_inbox.py -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/models.py`, `src/clipforge/inbox.py`, `tests/test_inbox.py`.

---

### Task 2: Channel folders and a ledger with status

**Files:**
- Modify: `src/clipforge/inbox.py` (`Ledger`, `pending`; new `InboxVideo`, `inbox_videos`)
- Test: `tests/test_inbox.py` (update `test_pending_lists_new_videos_only` and `test_ledger_persists` to the new API)

**Interfaces:**
- Consumes: `Channel`, `InboxEntry`, `load_channels`.
- Produces:
  - `@dataclass(frozen=True) class InboxVideo: path: Path; key: str; channel: str | None`
  - `inbox_videos(folder: Path, channels: dict[str, Channel]) -> tuple[list[InboxVideo], list[str]]`
  - `pending(folder: Path, ledger: Ledger, channels: dict[str, Channel]) -> tuple[list[InboxVideo], list[str]]`
  - `Ledger.get(key) -> InboxEntry | None`, `.job_id(key) -> str | None`, `.record(key, job_id)` (status `submitted`), `.update(key, entry)`, `.entries() -> dict[str, InboxEntry]`, `.unfinished() -> list[str]` (keys whose status is `submitted` or `failed`, sorted)

- [ ] **Step 1: Write the failing tests**

Replace `test_pending_lists_new_videos_only` and `test_ledger_persists` with these, and add the rest:

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
    assert videos == [
        InboxVideo(tmp_path / "billy-garton" / "ep01.mp4", "billy-garton/ep01.mp4", "billy-garton"),
        InboxVideo(tmp_path / "billy-garton" / "ep02.mp4", "billy-garton/ep02.mp4", "billy-garton"),
        InboxVideo(tmp_path / "loose.mp4", "loose.mp4", None),
    ]
    assert warnings == []


def test_unknown_channel_folder_is_skipped_with_warning(tmp_path: Path) -> None:
    (tmp_path / "billy-gartn").mkdir()
    _video(tmp_path / "billy-gartn", "ep01.mp4")
    (tmp_path / "empty").mkdir()  # no videos: no warning
    (tmp_path / "schedule").mkdir()
    _video(tmp_path / "schedule", "0800_x.mp4")  # posting output, never an input
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
    ledger.update("b.mp4", InboxEntry(job_id="J2", status="done", out="b"))
    reloaded = Ledger(path)
    assert reloaded.job_id("billy-garton/ep.mp4") == "J1"
    assert reloaded.get("b.mp4") == InboxEntry(job_id="J2", status="done", out="b")
    assert reloaded.get("other.mp4") is None
    assert reloaded.unfinished() == ["billy-garton/ep.mp4"]


def test_ledger_reads_old_format(tmp_path: Path) -> None:
    path = tmp_path / ".clipforge.json"
    path.write_text('{"billy_carton-Koa_smith.mp4": "20260928-b8193698-ba91"}')
    ledger = Ledger(path)
    assert ledger.get("billy_carton-Koa_smith.mp4") == InboxEntry(
        job_id="20260928-b8193698-ba91", status="done"
    )
    assert ledger.unfinished() == []
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_inbox.py -q`
Expected: FAIL with `ImportError: cannot import name 'InboxVideo'`.

- [ ] **Step 3: Implement** in `inbox.py` (add `from dataclasses import dataclass`)

```python
class Ledger:
    """`{video key: InboxEntry}` for videos already submitted, kept next to the videos. Keys are
    paths relative to the inbox folder ("ep.mp4", "billy-garton/ep.mp4"). The old format,
    `{name: job_id}`, loads as finished entries."""

    def __init__(self, path: Path) -> None:
        self.path = path
        raw: dict[str, object] = json.loads(path.read_text()) if path.exists() else {}
        self._data = {
            key: InboxEntry(job_id=value, status="done")
            if isinstance(value, str)
            else InboxEntry.model_validate(value)
            for key, value in raw.items()
        }

    def get(self, key: str) -> InboxEntry | None:
        return self._data.get(key)

    def job_id(self, key: str) -> str | None:
        entry = self._data.get(key)
        return entry.job_id if entry else None

    def entries(self) -> dict[str, InboxEntry]:
        return dict(self._data)

    def unfinished(self) -> list[str]:
        """Submitted jobs not downloaded yet, and failed ones (they may have been resumed)."""
        return sorted(k for k, e in self._data.items() if e.status in ("submitted", "failed"))

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

Update `cli._clip`'s call to `pending` minimally so the suite still runs: `videos, _ = pending(folder, ledger, {})` and use `video.path` where it used the path. Task 3 rewrites `_clip`.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_inbox.py tests/test_cli.py -q`
Expected: inbox PASS. `test_clip_one_file_end_to_end` fails only on its last line (the ledger JSON shape). Change that expectation to `{"My Talk.mp4": {"job_id": job_id, "status": "submitted"}}` for now; Task 3 changes it to `done`.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/inbox.py`, `src/clipforge/cli.py`, `tests/test_inbox.py`, `tests/test_cli.py`.

---

### Task 3: Submit everything, then collect in parallel

**Files:**
- Modify: `src/clipforge/cli.py` (`_clip`, `_out_dir`; new `_video_for`, `_job_input`, `_collect`, `JobReader`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_channels`, `CHANNELS_NAME`, `InboxVideo`, `pending`, `Ledger`, `InboxEntry`, `progress_line` (existing), `MAX_NETWORK_ERRORS` (existing).
- Produces: `POLL_INTERVAL_S = 15.0`; `class JobReader(Protocol): def get_job(self, job_id: str) -> JobView`; `_collect(keys: list[str], ledger: Ledger, folder: Path, client: JobReader, sleep: Callable[[float], object], downloader: Downloader) -> int`; `_out_dir(folder: Path, key: str) -> Path`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`; merge the imports)

```python
from clipforge.cli import _collect
from clipforge.inbox import Ledger
from clipforge.models import InboxEntry, JobError, Permission

CHANNELS_TOML = '[billy-garton]\nname = "Billy Garton Jr."\npermission = "creator_agreement"\n'


def _channel_inbox(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "videos"
    (folder / "billy-garton").mkdir(parents=True)
    (folder / "channels.toml").write_text(CHANNELS_TOML)
    for name in names:
        (folder / "billy-garton" / name).write_bytes(name.encode())
    return folder


def test_clip_channel_batch(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4", "ep02.mp4")
    uploader, downloader = FakeUploader(), FakeDownloader()
    assert _clip(harness, api, uploader, "--folder", str(folder), downloader=downloader) == 0

    assert [local.name for local, _ in uploader.puts] == ["ep01.mp4", "ep02.mp4"]
    jobs = [harness.store.get(j) for j in harness.store.list_job_ids()]
    assert {j.input.source_label for j in jobs} == {"ep01", "ep02"}
    assert all(j.input.source_credit == "Billy Garton Jr." for j in jobs)
    assert all(j.input.permission is Permission.CREATOR_AGREEMENT for j in jobs)
    out = folder / "out" / "billy-garton"
    assert sorted(dest for _, dest in downloader.gets) == [out / "ep01", out / "ep02"]
    ledger = Ledger(folder / ".clipforge.json")
    assert ledger.get("billy-garton/ep01.mp4") == InboxEntry(
        job_id=ledger.job_id("billy-garton/ep01.mp4") or "", status="done", out="billy-garton/ep01"
    )


def test_clip_picks_up_earlier_submissions(
    harness: Harness, api: TestClient, tmp_path: Path
) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    uploader, downloader = FakeUploader(), FakeDownloader()
    assert _clip(harness, api, uploader, "--folder", str(folder), "--no-wait",
                 downloader=downloader) == 0  # fmt: skip
    assert downloader.gets == []
    assert _clip(harness, api, uploader, "--folder", str(folder), downloader=downloader) == 0
    assert len(uploader.puts) == 1  # not uploaded or submitted again
    assert len(harness.store.list_job_ids()) == 1
    assert [dest.name for _, dest in downloader.gets] == ["ep01"]


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


def test_collect_downloads_resumed_and_reports_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "videos"
    ledger = Ledger(folder / ".clipforge.json")
    ledger.update("a.mp4", InboxEntry(job_id="JA", status="failed", error="x"))
    ledger.update("b.mp4", InboxEntry(job_id="JB", status="submitted"))
    failed = _view(JobStatus.FAILED).model_copy(
        update={"error": JobError(stage=StageName.TRANSCRIBE, error_type="E", message="boom")}
    )
    reader = FakeReader({"JA": _view(JobStatus.DONE), "JB": failed})
    downloader = FakeDownloader()
    code = _collect(["a.mp4", "b.mp4"], ledger, folder, reader, lambda _s: None, downloader)
    assert code == 1
    assert ledger.get("a.mp4") == InboxEntry(job_id="JA", status="done", out="a")
    assert ledger.get("b.mp4") == InboxEntry(
        job_id="JB", status="failed", error="transcribe: boom"
    )
    assert "clipforge resume JB" in capsys.readouterr().out
```

Also change the last line of `test_clip_one_file_end_to_end` to:

```python
    assert json.loads((folder / ".clipforge.json").read_text()) == {
        "My Talk.mp4": {"job_id": job_id, "status": "done", "out": "My Talk"}
    }
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL with `ImportError: cannot import name '_collect'`.

- [ ] **Step 3: Implement** in `cli.py`

Imports: add `CHANNELS_NAME, InboxVideo, load_channels` to the `clipforge.inbox` import. Add `Channel, InboxEntry` to the `clipforge.models` import.

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
    """Channel videos carry their creator credit and permission (ADR-20)."""
    options = dict(options)
    if video.channel is not None:
        channel = channels[video.channel]
        options.setdefault("perm", channel.permission.value)
        options["credit"] = channel.name
    job_input = build_job_input(settings, options, None, source_path=remote)
    return job_input.model_copy(update={"source_label": video.path.stem})


def _clip(
    args: argparse.Namespace,
    settings: Settings,
    client: ApiClient,
    sleep: Callable[[float], object],
    uploader: Uploader,
    downloader: Downloader,
) -> int:
    """Upload and submit every new video, then wait for all unfinished jobs together and fetch
    each one's clips into `<folder>/out/[<channel>/]<video name>/` as soon as it's done."""
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
        if not videos and not ledger.unfinished():
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
    if args.no_wait:
        print("submitted; run `clipforge clip` again later to download the clips")
        return 0
    return _collect(ledger.unfinished(), ledger, folder, client, sleep, downloader)


def _collect(
    keys: list[str],
    ledger: Ledger,
    folder: Path,
    client: JobReader,
    sleep: Callable[[float], object],
    downloader: Downloader,
) -> int:
    """Check each job in turn until every one is done or failed. Download each done job right
    away. Safe to interrupt: unfinished entries stay `submitted` for the next run."""
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
                ledger.update(key, InboxEntry(job_id=entry.job_id, status="done", out=out))
                left.remove(key)
            elif view.status is JobStatus.FAILED:
                error = view.error
                where = f"{error.stage}: {error.message}" if error else "failed"
                print(f"{key}: failed at {where} · clipforge resume {entry.job_id}")
                ledger.update(
                    key, InboxEntry(job_id=entry.job_id, status="failed", error=where)
                )
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

Delete `_wait_for`, which is now unused. `wait()` stays because `run` uses it. `error.stage` is a `StrEnum`, so it formats as `transcribe`.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_cli.py tests/test_inbox.py -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/cli.py`, `tests/test_cli.py`.

---

### Task 4: `videos/STATUS.md`, `clipforge report`, docs

**Files:**
- Create: `src/clipforge/status_report.py`
- Modify: `src/clipforge/cli.py` (write the status after `clip`; `report` command)
- Modify: `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`
- Test: `tests/test_status_report.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `inbox_videos`, `Ledger`, `load_channels`, `JobMetadata`.
- Produces: `status_report.STATUS_NAME = "STATUS.md"`; `render(folder: Path, channels: dict[str, Channel], now: datetime) -> str`; `write(folder: Path, channels: dict[str, Channel], now: datetime) -> Path`. The posting-queue plan extends `render` later.

- [ ] **Step 1: Write the failing tests** — `tests/test_status_report.py`

```python
"""videos/STATUS.md: rebuilt from the inbox ledger and the downloaded metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from clipforge.inbox import Ledger
from clipforge.models import Channel, InboxEntry, Permission
from clipforge.status_report import render, write
from tests.posting.helpers import HASH_A, write_cut

NOW = datetime(2026, 9, 29, 10, 12, tzinfo=UTC)
BILLY = {"billy-garton": Channel(name="Billy Garton Jr.", permission=Permission.CREATOR_AGREEMENT)}


def _inbox(tmp_path: Path) -> Path:
    folder = tmp_path / "videos"
    (folder / "billy-garton").mkdir(parents=True)
    for name in ("ep01.mp4", "ep02.mp4", "ep03.mp4", "ep04.mp4"):
        (folder / "billy-garton" / name).write_bytes(b"v")
    ledger = Ledger(folder / ".clipforge.json")
    ledger.update("billy-garton/ep01.mp4",
                  InboxEntry(job_id="J1", status="done", out="billy-garton/ep01"))  # fmt: skip
    ledger.update("billy-garton/ep02.mp4",
                  InboxEntry(job_id="J2", status="failed", error="transcribe: boom"))  # fmt: skip
    ledger.update("billy-garton/ep03.mp4", InboxEntry(job_id="J3"))
    clips = [("clip_01", 0.0, 30.0, 0.91, "A"), ("clip_02", 40.0, 70.0, 0.84, "B")]
    write_cut(folder / "out" / "billy-garton", "ep01", source_hash=HASH_A, clips=clips)
    return folder


def test_render(tmp_path: Path) -> None:
    text = render(_inbox(tmp_path), BILLY, NOW)
    assert text.startswith("# ClipForge status\n\nUpdated 2026-09-29 10:12\n")
    assert "| Billy Garton Jr. | 4 | 1 | 1 | 1 | 1 | 2 | $0.00 |" in text
    assert "## Billy Garton Jr. (`billy-garton`, creator_agreement)" in text
    assert "| ep01.mp4 | ✅ clipped | 2 | 0.91 | $0.00 | J1 |" in text
    assert "| ep02.mp4 | ❌ failed: transcribe: boom |  |  |  | J2 |" in text
    assert "| ep03.mp4 | ⏳ clipping |  |  |  | J3 |" in text
    assert "| ep04.mp4 | 🆕 new |  |  |  |  |" in text


def test_loose_videos_and_pipes_in_errors(tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "test.mp4").write_bytes(b"v")
    Ledger(folder / ".clipforge.json").update(
        "test.mp4", InboxEntry(job_id="J", status="failed", error="a | b")
    )
    text = render(folder, {}, NOW)
    assert "## No channel" in text
    assert "failed: a \\| b" in text  # a | would break the table


def test_write(tmp_path: Path) -> None:
    folder = _inbox(tmp_path)
    path = write(folder, BILLY, NOW)
    assert path == folder / "STATUS.md"
    assert path.read_text() == render(folder, BILLY, NOW)
```

The posting-queue plan creates `tests/posting/helpers.py` too. If this plan runs first, create that file here (its full contents are in the posting plan's Task 1, Step 1) together with an empty `tests/posting/__init__.py`. The posting plan then reuses it. `write_cut` also needs `PostingConfig`/`QueuedClip` only for `queued()`; if those contracts don't exist yet, leave `queued()` and its imports out and let the posting plan add them.

Append to `tests/test_cli.py`:

```python
def test_clip_writes_status(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    _clip(harness, api, FakeUploader(), "--folder", str(folder))
    assert "ep01.mp4" in (folder / "STATUS.md").read_text()


def test_report_needs_no_api(tmp_path: Path) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    settings = make_settings(tmp_path, api_token=None, api_url=None)
    assert main(["report", "--folder", str(folder)], settings=settings) == 0
    assert "🆕 new" in (folder / "STATUS.md").read_text()
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/test_status_report.py tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'clipforge.status_report'`.

- [ ] **Step 3: Implement** `src/clipforge/status_report.py`

```python
"""`videos/STATUS.md`: where every channel and episode stands (ADR-20).

Rebuilt from scratch from the inbox ledger, channels.toml and the downloaded metadata.json
files, so it's always true. Never edit it by hand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from clipforge.inbox import LEDGER_NAME, OUT_DIR, Ledger, inbox_videos
from clipforge.models import Channel, JobMetadata

STATUS_NAME = "STATUS.md"


@dataclass(frozen=True)
class _Row:
    name: str
    status: str  # "new" | "clipping" | "clipped" | "failed"
    job_id: str = ""
    clips: int | None = None
    best: float | None = None
    cost: float | None = None
    error: str = ""


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _metadata(folder: Path, out: str | None) -> JobMetadata | None:
    path = folder / OUT_DIR / out / "metadata.json" if out else None
    if path is None or not path.exists():
        return None
    try:
        return JobMetadata.model_validate_json(path.read_text())
    except ValidationError:
        return None


def _rows(folder: Path, channels: dict[str, Channel]) -> dict[str | None, list[_Row]]:
    videos, _ = inbox_videos(folder, channels)
    ledger = Ledger(folder / LEDGER_NAME)
    rows: dict[str | None, list[_Row]] = {}
    for video in videos:
        entry = ledger.get(video.key)
        name = video.path.name
        if entry is None:
            row = _Row(name, "new")
        elif entry.status == "submitted":
            row = _Row(name, "clipping", entry.job_id)
        elif entry.status == "failed":
            row = _Row(name, "failed", entry.job_id, error=entry.error or "")
        else:
            meta = _metadata(folder, entry.out)
            row = _Row(
                name, "clipped", entry.job_id,
                clips=len(meta.clips) if meta else None,
                best=max((c.score for c in meta.clips), default=None) if meta else None,
                cost=meta.cost.total_usd if meta else None,
            )  # fmt: skip
        rows.setdefault(video.channel, []).append(row)
    return rows


_ICON = {"new": "🆕 new", "clipping": "⏳ clipping", "clipped": "✅ clipped", "failed": "❌ failed"}


def render(folder: Path, channels: dict[str, Channel], now: datetime) -> str:
    rows = _rows(folder, channels)
    lines = [
        "# ClipForge status",
        "",
        f"Updated {now:%Y-%m-%d %H:%M}",
        "",
        "| Channel | Videos | Clipped | Clipping | Failed | New | Clips | Cost |",
        "|---|---|---|---|---|---|---|---|",
    ]
    order: list[str | None] = [slug for slug in channels if slug in rows]
    if None in rows:
        order.append(None)
    for slug in order:
        group = rows[slug]
        count = {s: sum(r.status == s for r in group) for s in _ICON}
        clips = sum(r.clips or 0 for r in group)
        cost = sum(r.cost or 0.0 for r in group)
        title = channels[slug].name if slug else "No channel"
        lines.append(
            f"| {_cell(title)} | {len(group)} | {count['clipped']} | {count['clipping']} | "
            f"{count['failed']} | {count['new']} | {clips} | ${cost:.2f} |"
        )
    for slug in order:
        if slug is None:
            heading = "No channel"
        else:
            channel = channels[slug]
            heading = f"{_cell(channel.name)} (`{slug}`, {channel.permission.value})"
        lines += ["", f"## {heading}", "", "| Video | Status | Clips | Best | Cost | Job |",
                  "|---|---|---|---|---|---|"]  # fmt: skip
        for row in rows[slug]:
            status = _ICON[row.status] + (f": {_cell(row.error)}" if row.error else "")
            clips = "" if row.clips is None else str(row.clips)
            best = "" if row.best is None else f"{row.best:.2f}"
            cost = "" if row.cost is None else f"${row.cost:.2f}"
            lines.append(
                f"| {_cell(row.name)} | {status} | {clips} | {best} | {cost} | {row.job_id} |"
            )
    return "\n".join(lines) + "\n"


def write(folder: Path, channels: dict[str, Channel], now: datetime) -> Path:
    path = folder / STATUS_NAME
    path.write_text(render(folder, channels, now))
    return path
```

`cli.py`:
- Import `from clipforge import status_report` and `from datetime import datetime`.
- In `_clip`, write the status on every exit after the ledger has changed. Wrap the submit loop and `_collect` in `try: ... finally: status_report.write(folder, channels, datetime.now().astimezone())`, so an interrupted run still leaves a current file. Keep the early `return 2`/`return 0` paths before the loop outside the `try`.
- Add the parser entry:

```python
    report = commands.add_parser("report", help="rewrite <folder>/STATUS.md")
    report.add_argument("--folder", default="videos", help="inbox folder (default: videos)")
```

- In `main`, before the API_URL/API_TOKEN check:

```python
    if args.command == "report":
        folder = Path(args.folder)
        try:
            channels = load_channels(folder / CHANNELS_NAME)
        except ValueError as exc:
            print(f"{folder / CHANNELS_NAME}: {exc}", file=sys.stderr)
            return 2
        print(status_report.write(folder, channels, datetime.now().astimezone()))
        return 0
```

- Docstring: add `    uv run clipforge report                  # rewrite videos/STATUS.md`.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_status_report.py tests/test_cli.py tests/test_inbox.py -q`
Expected: PASS.

- [ ] **Step 5: Docs**

`docs/DECISIONS.md`, append:

```markdown
## ADR-20: Channel folders, batch clipping and a generated STATUS.md
Date: 2026-09-28 · Status: Accepted
Context: The owner clips whole channels, starting with 11 episodes of Billy Garton Jr.'s podcast (permission: creator agreement), and more channels later. Every clip needs the right credit. Clipping one video at a time takes hours, and there was no single view of progress.
Decision: Videos go in `videos/<channel>/`. `videos/channels.toml` gives each channel a credit name, an optional url and a permission, and these go into every job's `JobInput`. `clipforge clip` submits every new video first, then polls all unfinished jobs together and downloads each when it's done. The inbox ledger keeps a status per video, so interrupted runs resume and failed jobs are re-checked. `videos/STATUS.md` is regenerated from the ledger and the downloaded metadata after every run (and by `clipforge report`), never edited by hand. Notion was considered and deferred until performance data exists. Spec: docs/superpowers/specs/2026-09-28-channels-batch-design.md.
Consequences: Credit and permission are set once per channel. A video moved into a channel folder counts as new and is submitted again; this is cheap because the transcript and highlights are cached by source hash, and the posting queue keeps only the newest cut.
```

`docs/ARCHITECTURE.md`, add after "Storage and delivery":

```markdown
## Local inbox (ADR-20)

`videos/<channel>/*.mp4` plus `videos/channels.toml` (credit, url, permission per channel). `uv run clipforge clip` uploads and submits every new video, then waits for all unfinished jobs in parallel and downloads each into `videos/out/<channel>/<episode>/`. `videos/.clipforge.json` keeps each video's job and status. `videos/STATUS.md` is regenerated after each run and by `clipforge report`.
```

`CLAUDE.md` Commands: change the `clipforge clip` line to `uv run clipforge clip [videos/<channel>/<file>]      # videos/ inbox (channel folders) → clips in videos/out/<channel>/<name>/`, and add `uv run clipforge report                           # rewrite videos/STATUS.md`. In Layout, after `inbox.py`, add `  status_report.py  # videos/STATUS.md from the ledger + downloaded metadata`.

`ROADMAP.md` Phase 2, after "Command options", add and tick:
`- [x] Channel folders + \`channels.toml\` (credit, permission), batch \`clipforge clip\`, generated \`videos/STATUS.md\` (ADR-20)`

`videos/README.md`: rewrite the top section for channel folders:

````markdown
# videos/

One folder per channel, described in `channels.toml`:

```
videos/
  channels.toml
  billy-garton/ep01.mp4 ep02.mp4 ...
  STATUS.md          # generated: where every channel and episode stands
```

```toml
# channels.toml
[billy-garton]
name = "Billy Garton Jr."                # the credit on every clip
url = "https://www.youtube.com/@..."     # optional
permission = "creator_agreement"         # own | creator_agreement | clipping_program | cc_by
```

```bash
uv run clipforge clip                    # every new video, all channels, clipped in parallel
uv run clipforge clip --no-wait          # just submit; run `clipforge clip` later to download
uv run clipforge clip "videos/billy-garton/ep01.mp4" --again   # re-cut one
uv run clipforge report                  # rewrite STATUS.md
```

Results land in `videos/out/<channel>/<episode>/`. It's safe to stop a run (Ctrl-C): the next `clipforge clip` picks up the jobs still running. Videos directly in `videos/` still work, without a credit.
````

Keep the rest of the README (options, output layout) and update the paths in it.

- [ ] **Step 6: Full check and a real look**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

Then run `uv run clipforge report` against the real `videos/`. Expected: `videos/STATUS.md` lists `billy_carton-Koa_smith.mp4` under "No channel" as clipped, read from the old-format ledger.

- [ ] **Step 7: Checkpoint.** Files: `src/clipforge/status_report.py`, `src/clipforge/cli.py`, `tests/test_status_report.py`, `tests/test_cli.py`, possibly `tests/posting/helpers.py` and `tests/posting/__init__.py`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`.

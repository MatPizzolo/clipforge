# Plan 2 of 3: Real stages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fake stages with the real ones and prove the whole chain end to end in-process. The stages are ingest, transcribe, highlights, reframe, captions, render and package, wired together in a `PipelineStages` that implements `StageRunner`. A synthetic video goes in and a zip of 1080x1920 captioned clips comes out.

**Architecture:** Each stage is a Modal-free module in `src/clipforge/stages/`. It exposes `run(ctx, ..., deps) -> Stored[T]` and caches through `jobs.cached_stage`, keyed on the narrowest inputs (ADR-8). External services sit behind small interfaces that tests replace: `httpx.Client` for downloads, `Transcriber` for faster-whisper, `LLMClient` for Anthropic. `stages/runner.py` wires the stages into the `StageRunner` protocol that Plan 1's step chain calls. Plan 3 binds this runner inside the Modal functions.

**Tech Stack:** Python 3.12, uv, ffmpeg 6.1 with libass and libx264, httpx 0.28, anthropic 1.8 (it uses `httpx2` internally), faster-whisper 1.2.1 (GPU image only), pydantic v2 and pytest.

**Spec:** `docs/superpowers/specs/2026-09-23-serverless-pipeline-design.md` (and ARCHITECTURE "Highlight selection", ADR-8, 10, 11, 15).

**Git:** the owner runs every git command. "Checkpoint" steps list the files to commit; don't run git.

## Global Constraints

- Stage modules never import `modal`. `faster_whisper` is imported only inside `WhisperTranscriber`, lazily.
- Every stage module defines `STAGE_VERSION = "1"`. Cache keys use `hashing.cache_key(stage, STAGE_VERSION, [], extra)` with narrow inputs, and never contain `clip_id` or `rank` (ADR-8).
- Clips are H.264 `yuv420p` at 1080x1920 with AAC audio at 48 kHz stereo, 128 kb/s. Each clip is under 50 MB (video bitrate is at most `45 MB × 8 / duration − 128 kb/s`, capped at 8 Mb/s), made in one encode with an accurate `-ss` seek.
- Captions use the Anton font (bundled in `assets/fonts/`, OFL): uppercase, at most 3 words per chunk, the current word in yellow, `MarginV 480` on a 1920 canvas. That's well clear of the platform UI in the bottom 15% (288 px).
- Highlights uses `prompts/highlights_v1.md` (registered in `prompts/metadata.json`) and model `settings.highlight_model` (`claude-haiku-4-5`, ADR-4). Windows are 300 s with 30 s overlap. A window whose JSON fails twice is dropped, and the stage fails if more than 25% of windows fail or no candidates remain (CLAUDE.md rule 5).
- Snapping: a clip start goes to the nearest sentence start or post-silence word within ±3 s, otherwise the nearest word start within ±3 s, otherwise the clip is dropped. Ends work the same way. Silence means a gap of at least 300 ms. After snapping, a clip must satisfy `min_len ≤ duration ≤ max_len`. Duplicates (IoU > 0.5) keep the higher score.
- Limits (ADR-15): at most 3 hours (`max_source_duration_s`) and 4 GB (`max_source_bytes`), and there must be an audio stream. Violations raise `PermanentError` with a short, secret-free message.
- HTTP: use `httpx` for downloads. Never pass an `httpx` object to the Anthropic SDK, which uses `httpx2`.
- Fast tests use real ffmpeg on synthetic media, with no network, GPU or API. Real Anthropic calls are marked `slow`; real faster-whisper is marked `gpu` (Plan 3 runs those on Modal).
- Before every checkpoint: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.

## Review Focus

1. **Rotated phone videos.** A portrait video stored as landscape with rotation metadata must come out upright, not squashed and not crashing the crop. Test: `test_rotated_source_renders_upright` (Task 10).
2. **ASS control characters in speech.** Text like `{\b1}` or backslashes in the transcript must not inject caption styling. Test: `test_ass_control_characters_are_stripped` (Task 9).
3. **Redirecting links.** Short links and CDNs that answer 302 must be followed. Test: `test_follows_redirects` (Task 3).
4. **Servers without Content-Length** (chunked responses). The size limit must still be enforced while streaming. Test: `test_size_limit_without_content_length` (Task 3).
5. **LLM replies with prose, code fences or extra keys.** They must parse on the first try instead of burning a retry. Test: `test_parse_clips_handles_prose_fences_and_extra_keys` (Task 7).

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | + `anthropic`, `httpx` (Task 1) |
| `assets/fonts/Anton-Regular.ttf`, `assets/fonts/OFL.txt` | Caption font and its license (Task 1) |
| `prompts/metadata.json` | Prompt registry (Task 1) |
| `src/clipforge/config.py` | + `prompts_dir`, `fonts_dir`, `whisper_model_path`, `gpu_type`, `llm_max_workers`, `git_sha` (Task 1) |
| `src/clipforge/jobs.py`, `src/clipforge/service.py` | + `merged_cost(store, job)`, used by the service and package (Task 1) |
| `src/clipforge/ffmpeg.py` | `run`, `probe`, `media_info`, `probe_info`, `filter_path`, `FfmpegError` (Task 2) |
| `src/clipforge/stages/ingest.py` | Fetch, limits, normalize, wav (Task 3) |
| `src/clipforge/stages/transcribe.py` | `Transcriber`, `WhisperTranscriber`, `to_transcript`, `run` (Task 4) |
| `src/clipforge/prompts.py`, `src/clipforge/llm.py` | Versioned prompt loading; `LLMClient`/`AnthropicClient` (Task 5) |
| `src/clipforge/stages/segmenting.py` | Sentences, windows, cut points, snapping (Task 6) |
| `src/clipforge/stages/highlights.py` | Per-window LLM calls, validation and retry, snap, filter, dedupe (Task 7) |
| `src/clipforge/stages/reframe.py` | `plan(spec) -> CropTrack` (Task 8) |
| `src/clipforge/stages/captions.py` | Word-level ASS and SRT (Task 9) |
| `src/clipforge/stages/render.py` | One ffmpeg encode per clip (Task 10) |
| `src/clipforge/stages/package.py` | Output folder, `post.md`, `metadata.json`, zip (Task 11) |
| `src/clipforge/stages/runner.py` | `PipelineStages` (the real `StageRunner`) and `STAGE_VERSIONS` (Task 12) |
| `tests/stages/helpers.py` | `make_ctx`, `upload`, fakes and media asserts, grown task by task |
| `tests/test_ffmpeg.py`, `tests/test_prompts.py`, `tests/test_llm.py`, `tests/stages/test_*.py` | Tests |

---

### Task 1: Dependencies, assets, settings and `merged_cost`

**Files:**
- Modify: `pyproject.toml` (via `uv add`), `src/clipforge/config.py`, `src/clipforge/jobs.py`, `src/clipforge/service.py`
- Create: `assets/fonts/Anton-Regular.ttf`, `assets/fonts/OFL.txt`, `prompts/metadata.json`
- Test: `tests/test_config.py`, `tests/test_jobs.py`

**Interfaces:**
- Produces:
  - `Settings.prompts_dir: Path` (repo `prompts/`), `Settings.fonts_dir: Path` (repo `assets/fonts/`), `Settings.whisper_model_path: str = "/models/large-v3-turbo"`, `Settings.gpu_type: str = "L4"`, `Settings.llm_max_workers: int = 4`, `Settings.git_sha: str | None = None`.
  - `jobs.merged_cost(store: DictJobStore, job: Job) -> CostSummary`, which combines the job's cost entries with every clip's.

- [ ] **Step 1: Add dependencies and assets**

```bash
uv add "anthropic>=1.8" "httpx>=0.28"
mkdir -p assets/fonts
curl -sL -o assets/fonts/Anton-Regular.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf
curl -sL -o assets/fonts/OFL.txt https://github.com/google/fonts/raw/main/ofl/anton/OFL.txt
ls -l assets/fonts   # Anton-Regular.ttf is ~170 KB
```

Create `prompts/metadata.json`:

```json
{
  "highlights_v1": {
    "released": "2026-09-23",
    "model_default": "claude-haiku-4-5",
    "notes": "Initial highlight-selection prompt."
  }
}
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_asset_paths_and_gpu_defaults() -> None:
    s = Settings(_env_file=None)
    assert (s.prompts_dir / "highlights_v1.md").is_file()
    assert (s.prompts_dir / "metadata.json").is_file()
    assert (s.fonts_dir / "Anton-Regular.ttf").is_file()
    assert s.whisper_model_path == "/models/large-v3-turbo"
    assert s.gpu_type == "L4" and s.llm_max_workers == 4 and s.git_sha is None
```

Append to `tests/test_jobs.py`, and add `merged_cost` to its `clipforge.jobs` import:

```python
def test_merged_cost_includes_clip_entries(ctx: JobContext, store: DictJobStore) -> None:
    add_clip(store)
    ctx.record_cost(StageCost(stage=StageName.TRANSCRIBE, usd_estimate=0.05))
    clip_ctx = JobContext(job_id=JOB_ID, root=ctx.root, store=store, clip_id="clip_01")
    clip_ctx.record_cost(StageCost(stage=StageName.RENDER, usd_estimate=0.01))
    job = store.get(JOB_ID).model_copy(update={"clip_ids": ["clip_01"]})
    cost = merged_cost(store, job)
    assert [c.stage for c in cost.stages] == [StageName.TRANSCRIBE, StageName.RENDER]
    assert cost.total_usd == pytest.approx(0.06)
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_config.py tests/test_jobs.py -q`
Expected: FAIL. There's no `prompts_dir` attribute, and `ImportError: cannot import name 'merged_cost'`.

- [ ] **Step 4: Implement.** In `src/clipforge/config.py`, add below the imports:

```python
_REPO_ROOT = Path(__file__).resolve().parents[2]
```

and add these fields to `Settings` just before `prices`:

```python
    # Files the stages read (Plan 3 adds these directories to the Modal image)
    prompts_dir: Path = _REPO_ROOT / "prompts"
    fonts_dir: Path = _REPO_ROOT / "assets" / "fonts"

    # Transcription (ADR-11): weights baked into the GPU image at this path
    whisper_model_path: str = "/models/large-v3-turbo"
    gpu_type: str = "L4"

    # Highlights: parallel LLM calls per job
    llm_max_workers: int = 4

    # Recorded in metadata.json (set by the deploy)
    git_sha: str | None = None
```

In `src/clipforge/jobs.py`, add after `cached_stage`:

```python
def merged_cost(store: DictJobStore, job: Job) -> CostSummary:
    """The job's cost entries plus every clip's (ADR-14 keeps them in separate keys)."""
    clips = store.clips(job.job_id, job.clip_ids)
    return CostSummary(stages=[*job.cost.stages, *(entry for c in clips for entry in c.cost)])
```

In `src/clipforge/service.py`, replace these two lines in `get_job_view`:

```python
    clips = store.clips(job_id, job.clip_ids)
    cost = CostSummary(stages=[*job.cost.stages, *(entry for c in clips for entry in c.cost)])
```

with:

```python
    clips = store.clips(job_id, job.clip_ids)
    cost = merged_cost(store, job)
```

and import `merged_cost` from `clipforge.jobs`. Remove `CostSummary` from the service's model imports if ruff reports it unused.

- [ ] **Step 5: Run the checks**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `pyproject.toml`, `uv.lock`, `assets/fonts/*`, `prompts/metadata.json`, `src/clipforge/{config,jobs,service}.py`, `tests/test_config.py`, `tests/test_jobs.py`. Message: `chore: stage dependencies, caption font, prompt registry, merged cost`.

---

### Task 2: ffmpeg wrappers

**Files:**
- Create: `src/clipforge/ffmpeg.py`
- Test: `tests/test_ffmpeg.py`

**Interfaces:**
- Produces:
  - `FfmpegError(RuntimeError)` with a `.stderr_tail` attribute.
  - `run(args: list[str], timeout: float = 900) -> str`, which prepends `ffmpeg -hide_banner -nostdin -y -loglevel warning` and returns stderr (the warnings).
  - `probe(path) -> dict[str, Any]` (ffprobe JSON).
  - `Rotation = Literal[0, 90, 180, 270]`.
  - `MediaInfo(duration_s, width, height, rotation, fps, video_codec, audio_codec, format_name)`, a frozen dataclass whose width and height are the display size after rotation.
  - `media_info(path) -> MediaInfo`.
  - `probe_info(path) -> ProbeInfo`.
  - `filter_path(path) -> str`, which raises `ValueError` for characters that would need filtergraph escaping.

- [ ] **Step 1: Write the failing `tests/test_ffmpeg.py`**

```python
from pathlib import Path

import pytest

from clipforge import ffmpeg
from clipforge.ffmpeg import FfmpegError, filter_path, media_info, probe_info
from tests.conftest import MediaFactory, requires_ffmpeg


@requires_ffmpeg
def test_media_info_landscape(media: MediaFactory) -> None:
    info = media_info(media(width=1920, height=1080, container="mkv"))
    assert (info.width, info.height, info.rotation) == (1920, 1080, 0)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")
    assert info.duration_s == pytest.approx(3.0, abs=0.1)
    assert info.fps == pytest.approx(30.0)


@requires_ffmpeg
def test_media_info_reports_display_size_for_rotated_video(
    tmp_path: Path, media: MediaFactory
) -> None:
    rotated = tmp_path / "rotated.mp4"
    ffmpeg.run(["-display_rotation:v:0", "90", "-i", str(media()), "-c", "copy", str(rotated)])
    info = media_info(rotated)
    assert info.rotation in (90, 270)
    assert (info.width, info.height) == (180, 320)


@requires_ffmpeg
def test_media_info_without_audio(media: MediaFactory) -> None:
    assert media_info(media(audio=False)).audio_codec is None


@requires_ffmpeg
def test_probe_info_counts_streams(media: MediaFactory) -> None:
    info = probe_info(media())
    assert (info.n_video_streams, info.n_audio_streams) == (1, 1)
    assert (info.width, info.height, info.pix_fmt) == (320, 180, "yuv420p")
    assert info.video_duration_s is not None and info.audio_duration_s is not None
    assert info.size_bytes > 0


@requires_ffmpeg
def test_errors_carry_stderr(tmp_path: Path) -> None:
    not_media = tmp_path / "notes.txt"
    not_media.write_text("hello")
    with pytest.raises(FfmpegError) as excinfo:
        media_info(not_media)
    assert excinfo.value.stderr_tail
    with pytest.raises(FfmpegError):
        ffmpeg.run(["-i", str(tmp_path / "missing.mp4"), str(tmp_path / "out.mp4")])


def test_filter_path_rejects_characters_that_need_escaping() -> None:
    assert filter_path(Path("/jobs/cache/captions/abc/clip.ass")) == "/jobs/cache/captions/abc/clip.ass"
    for bad in ("/tmp/a:b.ass", "/tmp/it's.ass", "/tmp/a,b.ass", "/tmp/[x].ass", "/tmp/a;b.ass"):
        with pytest.raises(ValueError):
            filter_path(Path(bad))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ffmpeg.py -q`
Expected: `ModuleNotFoundError: No module named 'clipforge.ffmpeg'`.

- [ ] **Step 3: Create `src/clipforge/ffmpeg.py`**

```python
"""Thin wrappers around the ffmpeg and ffprobe binaries."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from clipforge.models import ProbeInfo

Rotation = Literal[0, 90, 180, 270]
_ROTATIONS: dict[int, Rotation] = {0: 0, 90: 90, 180: 180, 270: 270}
_UNSAFE_IN_FILTERS = set(":',;[]\\")


class FfmpegError(RuntimeError):
    """ffmpeg or ffprobe exited non-zero; `stderr_tail` holds the last lines of its output."""

    def __init__(self, tool: str, stderr: str) -> None:
        self.stderr_tail = "\n".join(stderr.strip().splitlines()[-5:])
        super().__init__(f"{tool} failed: {self.stderr_tail}")


def run(args: list[str], timeout: float = 900) -> str:
    """Run ffmpeg with `args`; returns its stderr (warnings) on success."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise FfmpegError("ffmpeg", result.stderr)
    return result.stderr


def probe(path: Path) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise FfmpegError("ffprobe", result.stderr or "not a media file")
    data: dict[str, Any] = json.loads(result.stdout)
    return data


def _rate(value: str | None) -> float:
    if not value:
        return 0.0
    num, _, den = value.partition("/")
    denominator = float(den or 1)
    return float(num) / denominator if denominator else 0.0


def _duration(stream: dict[str, Any] | None) -> float | None:
    if stream is None or not stream.get("duration"):
        return None
    return float(stream["duration"])


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    width: int  # display width, after rotation
    height: int  # display height, after rotation
    rotation: Rotation
    fps: float
    video_codec: str | None
    audio_codec: str | None
    format_name: str


def media_info(path: Path) -> MediaInfo:
    data = probe(path)
    streams: list[dict[str, Any]] = data.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    width = height = 0
    fps = 0.0
    rotation: Rotation = 0
    if video is not None:
        raw = next(
            (sd["rotation"] for sd in video.get("side_data_list", []) if "rotation" in sd),
            video.get("tags", {}).get("rotate", 0),
        )
        rotation = _ROTATIONS[round(int(float(raw)) % 360 / 90) * 90 % 360]
        width, height = int(video["width"]), int(video["height"])
        if rotation in (90, 270):
            width, height = height, width
        fps = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    fmt: dict[str, Any] = data.get("format", {})
    return MediaInfo(
        duration_s=float(fmt.get("duration") or 0.0),
        width=width,
        height=height,
        rotation=rotation,
        fps=fps,
        video_codec=video.get("codec_name") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
        format_name=str(fmt.get("format_name", "")),
    )


def probe_info(path: Path) -> ProbeInfo:
    """Output properties the tests and the pipeline check (1080x1920, streams, durations)."""
    data = probe(path)
    streams: list[dict[str, Any]] = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    video = videos[0] if videos else {}
    audio = audios[0] if audios else None
    fmt: dict[str, Any] = data.get("format", {})
    return ProbeInfo(
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        duration_s=float(fmt.get("duration") or 0.0),
        video_duration_s=_duration(video) if videos else None,
        audio_duration_s=_duration(audio),
        fps=_rate(video.get("avg_frame_rate")),
        video_codec=str(video.get("codec_name", "")),
        pix_fmt=str(video.get("pix_fmt", "")),
        audio_codec=audio.get("codec_name") if audio else None,
        n_video_streams=len(videos),
        n_audio_streams=len(audios),
        size_bytes=int(fmt.get("size") or path.stat().st_size),
    )


def filter_path(path: Path) -> str:
    """A path for use inside a filtergraph. Our paths are generated (cache keys, fonts dir),
    so reject rather than escape the characters filtergraphs treat specially."""
    text = path.as_posix()
    if _UNSAFE_IN_FILTERS & set(text):
        raise ValueError(f"path not usable in an ffmpeg filter: {text!r}")
    return text
```

- [ ] **Step 4: Run the tests and checks**

Run: `uv run pytest tests/test_ffmpeg.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 6 passed and clean.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/ffmpeg.py`, `tests/test_ffmpeg.py`. Message: `feat: ffmpeg/ffprobe wrappers`.

---

### Task 3: Ingest

**Files:**
- Create: `src/clipforge/stages/ingest.py`, `tests/stages/helpers.py`
- Test: `tests/stages/test_ingest.py`

**Interfaces:**
- Consumes: `ffmpeg.run`, `ffmpeg.media_info`, `FfmpegError` (Task 2); `cached_stage`, `JobContext` (Plan 1); `Settings` (Task 1).
- Produces:
  - `ingest.IngestDeps(http: httpx.Client, settings: Settings)`.
  - `ingest.run(ctx, job_input, deps) -> Stored[SourceMedia]`.
  - `ingest.STAGE_VERSION`.
  - Files `cache/ingest/<key>/source.mp4` and `audio.wav`.
  - Test helpers `make_ctx(root, job_input=None, job_id=JOB_ID) -> JobContext` and `upload(root, src) -> str`.

- [ ] **Step 1: Create `tests/stages/helpers.py`**

```python
"""Shared helpers for stage tests; later tasks append fakes and media assertions."""

from __future__ import annotations

import shutil
from pathlib import Path

from clipforge.jobs import DictJobStore, JobContext, utcnow
from clipforge.models import Job, JobInput, Permission
from clipforge.pipeline.deps import MemoryKV

JOB_ID = "20260923-cccccccc-0001"


def make_ctx(root: Path, job_input: JobInput | None = None, job_id: str = JOB_ID) -> JobContext:
    store = DictJobStore(MemoryKV())
    now = utcnow()
    job_input = job_input or JobInput(source_path="uploads/none.mp4", permission=Permission.OWN)
    store.save(Job(job_id=job_id, input=job_input, created_at=now, updated_at=now))
    return JobContext(job_id=job_id, root=root, store=store)


def upload(root: Path, src: Path) -> str:
    """Copy `src` under JOBS_ROOT (as a user upload would be) and return its contract path."""
    dest = root / "uploads" / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return f"uploads/{src.name}"
```

- [ ] **Step 2: Write the failing `tests/stages/test_ingest.py`**

```python
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.hashing import sha256_file
from clipforge.models import JobInput, Permission
from clipforge.pipeline.errors import PermanentError
from clipforge.stages import ingest
from tests.conftest import MediaFactory, requires_ffmpeg
from tests.stages.helpers import make_ctx, upload

pytestmark = requires_ffmpeg

TOKEN = "123456:TESTTOKEN"
Handler = Callable[[httpx.Request], httpx.Response]


def deps(root: Path, handler: Handler | None = None, **overrides: Any) -> ingest.IngestDeps:
    transport = httpx.MockTransport(handler or (lambda request: httpx.Response(500)))
    settings = Settings(_env_file=None, jobs_root=root, telegram_bot_token=TOKEN, **overrides)
    return ingest.IngestDeps(http=httpx.Client(transport=transport), settings=settings)


def path_input(rel: str) -> JobInput:
    return JobInput(source_path=rel, permission=Permission.OWN)


def url_input(url: str) -> JobInput:
    return JobInput.model_validate({"source_url": url, "permission": "own"})


def serve(data: bytes) -> Handler:
    return lambda request: httpx.Response(200, content=data, headers={"content-type": "video/mp4"})


def test_remuxes_h264_aac_and_extracts_wav(tmp_path: Path, media: MediaFactory) -> None:
    src = media(width=1920, height=1080, container="mkv")
    job_input = path_input(upload(tmp_path, src))
    ctx = make_ctx(tmp_path, job_input)
    source = ingest.run(ctx, job_input, deps(tmp_path)).value
    assert (source.width, source.height, source.rotation) == (1920, 1080, 0)
    assert source.video_codec == "h264"
    assert source.duration_s == pytest.approx(3.0, abs=0.1)
    assert source.source_hash == sha256_file(src)
    assert ctx.path(source.video_path).suffix == ".mp4"
    with wave.open(str(ctx.path(source.audio_path))) as wav:
        assert (wav.getnchannels(), wav.getframerate()) == (1, 16000)
    assert ctx.job().progress is not None


def test_transcodes_other_codecs_to_h264(tmp_path: Path, media: MediaFactory) -> None:
    job_input = path_input(upload(tmp_path, media(vcodec="mpeg4", container="mkv")))
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path)).value
    assert source.video_codec == "h264"


def test_rotation_is_reported_with_display_size(tmp_path: Path, media: MediaFactory) -> None:
    rotated = tmp_path / "phone.mp4"
    ffmpeg.run(["-display_rotation:v:0", "90", "-i", str(media()), "-c", "copy", str(rotated)])
    job_input = path_input(upload(tmp_path, rotated))
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path)).value
    assert (source.width, source.height) == (180, 320)
    assert source.rotation in (90, 270)


def test_downloads_direct_links_once(tmp_path: Path, media: MediaFactory) -> None:
    requests: list[httpx.Request] = []
    data = media().read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return serve(data)(request)

    job_input = url_input("https://cdn.example.com/ep1.mp4")
    ctx = make_ctx(tmp_path, job_input)
    d = deps(tmp_path, handler)
    first = ingest.run(ctx, job_input, d)
    second = ingest.run(ctx, job_input, d)
    assert first == second and len(requests) == 1
    assert first.value.source_url == "https://cdn.example.com/ep1.mp4"
    assert not (ctx.root / first.ref).parent.joinpath("download").exists()  # raw download removed


def test_follows_redirects(tmp_path: Path, media: MediaFactory) -> None:
    data = media().read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/short":
            return httpx.Response(302, headers={"location": "https://cdn.example.com/real.mp4"})
        return serve(data)(request)

    job_input = url_input("https://link.example.com/short")
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler)).value
    assert source.duration_s == pytest.approx(3.0, abs=0.1)


def test_web_page_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>", headers={"content-type": "text/html"})

    job_input = url_input("https://example.com/watch")
    with pytest.raises(PermanentError, match="direct link"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


@pytest.mark.parametrize("status", [403, 404])
def test_client_errors_are_permanent(tmp_path: Path, status: int) -> None:
    job_input = url_input("https://cdn.example.com/gone.mp4")
    d = deps(tmp_path, lambda request: httpx.Response(status))
    with pytest.raises(PermanentError, match=f"HTTP {status}"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, d)


def test_server_errors_are_transient(tmp_path: Path) -> None:
    job_input = url_input("https://cdn.example.com/busy.mp4")
    d = deps(tmp_path, lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        ingest.run(make_ctx(tmp_path, job_input), job_input, d)


def test_size_limit_without_content_length(tmp_path: Path, media: MediaFactory) -> None:
    data = media().read_bytes()

    def chunks() -> Iterator[bytes]:
        for i in range(0, len(data), 4096):
            yield data[i : i + 4096]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks(), headers={"content-type": "video/mp4"})

    job_input = url_input("https://cdn.example.com/chunked.mp4")
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(
            make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler, max_source_bytes=10_000)
        )


def test_size_limit_from_content_length(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": "video/mp4", "content-length": str(10**10)}
        return httpx.Response(200, content=iter([b"x"]), headers=headers)

    job_input = url_input("https://cdn.example.com/huge.mp4")
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


def test_duration_limit(tmp_path: Path, media: MediaFactory) -> None:
    job_input = path_input(upload(tmp_path, media()))
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(
            make_ctx(tmp_path, job_input), job_input, deps(tmp_path, max_source_duration_s=1)
        )


def test_no_audio_is_permanent(tmp_path: Path, media: MediaFactory) -> None:
    job_input = path_input(upload(tmp_path, media(audio=False)))
    with pytest.raises(PermanentError, match="no audio"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path))


def test_not_a_video_is_permanent(tmp_path: Path) -> None:
    notes = tmp_path / "uploads" / "notes.mp4"
    notes.parent.mkdir()
    notes.write_text("definitely not a video")
    job_input = path_input("uploads/notes.mp4")
    with pytest.raises(PermanentError, match="not a video"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path))


def test_telegram_upload(tmp_path: Path, media: MediaFactory) -> None:
    data = media().read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/bot{TOKEN}/getFile":
            assert request.url.params["file_id"] == "FILE42"
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "videos/f_1.mp4"}})
        assert request.url.path == f"/file/bot{TOKEN}/videos/f_1.mp4"
        return serve(data)(request)

    job_input = JobInput(telegram_file_id="FILE42", permission=Permission.OWN)
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler)).value
    assert source.source_url is None and source.duration_s == pytest.approx(3.0, abs=0.1)


def test_telegram_refusal_is_permanent(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"ok": False, "description": "Bad Request: file is too big"}
        return httpx.Response(400, json=body)

    job_input = JobInput(telegram_file_id="FILE42", permission=Permission.OWN)
    with pytest.raises(PermanentError, match="too big"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


def test_paths_outside_jobs_root_are_rejected(tmp_path: Path) -> None:
    job_input = path_input("../../etc/passwd")
    with pytest.raises(PermanentError, match="no such file"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path))
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/stages/test_ingest.py -q`
Expected: `ImportError: cannot import name 'ingest' from 'clipforge.stages'`.

- [ ] **Step 4: Create `src/clipforge/stages/ingest.py`**

```python
"""Ingest: fetch the source, check the limits, normalize to mp4, extract 16 kHz mono wav.

Sources (ADR-10): a direct HTTP(S) media link, a Telegram upload (file_id, at most 20 MB)
or a path under JOBS_ROOT. The limits (ADR-15) are checked before any GPU time is spent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.ffmpeg import FfmpegError
from clipforge.hashing import cache_key, sha256_file
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import JobInput, SourceMedia, StageCost, StageName
from clipforge.pipeline.errors import PermanentError

STAGE_VERSION = "1"
TELEGRAM_API = "https://api.telegram.org"
REMUX_VIDEO = frozenset({"h264", "hevc"})
REMUX_AUDIO = frozenset({"aac", "mp3"})
_CHUNK = 1024 * 1024
_TIMEOUT = httpx.Timeout(30.0, read=120.0)


@dataclass
class IngestDeps:
    http: httpx.Client
    settings: Settings


def run(ctx: JobContext, job_input: JobInput, deps: IngestDeps) -> Stored[SourceMedia]:
    key = cache_key("ingest", STAGE_VERSION, [], {"source": _source_id(job_input)})

    def compute(out_dir: Path) -> SourceMedia:
        started = time.monotonic()
        raw = _fetch(ctx, job_input, out_dir, deps)
        ctx.report(StageName.INGEST, 40, "downloaded")
        source = _normalize(ctx, raw, out_dir, job_input, deps.settings)
        if raw.parent == out_dir:
            raw.unlink()  # keep only the normalized copy
        ctx.record_cost(StageCost(stage=StageName.INGEST, wall_s=time.monotonic() - started))
        return source

    return cached_stage(ctx, StageName.INGEST, key, SourceMedia, compute)


def _source_id(job_input: JobInput) -> str:
    if job_input.source_url is not None:
        return f"url:{job_input.source_url}"
    if job_input.telegram_file_id is not None:
        return f"telegram:{job_input.telegram_file_id}"
    return f"path:{job_input.source_path}"


def _fetch(ctx: JobContext, job_input: JobInput, out_dir: Path, deps: IngestDeps) -> Path:
    if job_input.source_path is not None:
        path = ctx.path(job_input.source_path).resolve()
        if not path.is_relative_to(ctx.root.resolve()) or not path.is_file():
            raise PermanentError(f"no such file on the volume: {job_input.source_path}")
        return path
    if job_input.source_url is not None:
        url = str(job_input.source_url)
    else:
        assert job_input.telegram_file_id is not None  # JobInput guarantees exactly one source
        url = _telegram_file_url(deps, job_input.telegram_file_id)
    raw = out_dir / "download"
    _download(ctx, deps, url, raw)
    return raw


def _telegram_file_url(deps: IngestDeps, file_id: str) -> str:
    token = deps.settings.telegram_bot_token
    if token is None:
        raise PermanentError("the bot is not configured to download uploaded files")
    secret = token.get_secret_value()
    response = deps.http.get(
        f"{TELEGRAM_API}/bot{secret}/getFile", params={"file_id": file_id}, timeout=_TIMEOUT
    )
    if response.status_code >= 500:
        response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        reason = data.get("description", "unknown error")
        raise PermanentError(f"Telegram could not provide the file: {reason}")
    return f"{TELEGRAM_API}/file/bot{secret}/{data['result']['file_path']}"


def _download(ctx: JobContext, deps: IngestDeps, url: str, dest: Path) -> None:
    limit = deps.settings.max_source_bytes
    too_big = f"the file is larger than the {limit / 1e9:.1f} GB limit"
    with deps.http.stream("GET", url, follow_redirects=True, timeout=_TIMEOUT) as response:
        status = response.status_code
        if 400 <= status < 500 and status not in (408, 429):
            raise PermanentError(f"could not download the video (HTTP {status})")
        response.raise_for_status()  # 5xx, 408 and 429 are retried by the step
        if response.headers.get("content-type", "").startswith("text/html"):
            raise PermanentError(
                "the link opens a web page, not a video file; send a direct link to the file"
            )
        declared = int(response.headers.get("content-length") or 0)
        if declared > limit:
            raise PermanentError(too_big)
        received = reported = 0
        with dest.open("wb") as f:
            for chunk in response.iter_bytes(_CHUNK):
                received += len(chunk)
                if received > limit:
                    raise PermanentError(too_big)
                f.write(chunk)
                if declared and received - reported >= declared / 10:
                    ctx.report(StageName.INGEST, 40 * received / declared, "downloading")
                    reported = received


def _normalize(
    ctx: JobContext, raw: Path, out_dir: Path, job_input: JobInput, settings: Settings
) -> SourceMedia:
    try:
        info = ffmpeg.media_info(raw)
    except FfmpegError as exc:
        raise PermanentError("the file is not a video ffmpeg can read") from exc
    if info.video_codec is None:
        raise PermanentError("the file is not a video (no video stream)")
    if info.audio_codec is None:
        raise PermanentError("the video has no audio track, so there is nothing to transcribe")
    if info.duration_s <= 0:
        raise PermanentError("could not read the video's duration")
    if info.duration_s > settings.max_source_duration_s:
        raise PermanentError(
            f"the video is {info.duration_s / 60:.0f} min long; "
            f"the limit is {settings.max_source_duration_s / 60:.0f} min"
        )

    video = out_dir / "source.mp4"
    if info.video_codec in REMUX_VIDEO and info.audio_codec in REMUX_AUDIO:
        codec_args = ["-c", "copy"]
    else:
        codec_args = [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
        ]  # fmt: skip
    ffmpeg.run(
        ["-i", str(raw), "-map", "0:v:0", "-map", "0:a:0", *codec_args,
         "-movflags", "+faststart", str(video)]
    )  # fmt: skip
    ctx.report(StageName.INGEST, 70, "normalized")

    audio = out_dir / "audio.wav"
    ffmpeg.run(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])
    ctx.report(StageName.INGEST, 90, "audio extracted")

    out = ffmpeg.media_info(video)
    return SourceMedia(
        video_path=ctx.rel(video),
        audio_path=ctx.rel(audio),
        source_hash=sha256_file(raw),
        source_url=str(job_input.source_url) if job_input.source_url is not None else None,
        title=job_input.source_label,
        duration_s=out.duration_s,
        fps=out.fps or info.fps,
        width=out.width,
        height=out.height,
        rotation=out.rotation,
        video_codec=out.video_codec or "",
        size_bytes=raw.stat().st_size,
    )
```

- [ ] **Step 5: Run the tests and checks**

Run: `uv run pytest tests/stages/test_ingest.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: 16 ingest tests pass; the suite is green.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `src/clipforge/stages/ingest.py`, `tests/stages/helpers.py`, `tests/stages/test_ingest.py`. Message: `feat(ingest): direct links, Telegram uploads, limits, normalize and wav`.

---

### Task 4: Transcribe

**Files:**
- Create: `src/clipforge/stages/transcribe.py`
- Modify: `tests/stages/helpers.py` (append `FakeTranscriber`)
- Test: `tests/stages/test_transcribe.py`

**Interfaces:**
- Consumes: `Settings.gpu_type`, `Settings.prices`, `Settings.whisper_model_path` (Task 1).
- Produces:
  - A `Transcriber` protocol with `model_name: str` and `transcribe(audio: Path, language: str | None) -> Transcript`.
  - `WhisperTranscriber(model_path, model_name, batch_size=16)`.
  - `to_transcript(segments, language, language_probability, duration_s, model_name) -> Transcript`.
  - `run(ctx, source, transcriber, settings, language) -> Stored[Transcript]`.
  - `STAGE_VERSION`.
  - The test helper `FakeTranscriber(transcript, model_name="fake-whisper")`, which records `calls` (the languages it was given).

- [ ] **Step 1: Append `FakeTranscriber` to `tests/stages/helpers.py`.** Add these imports at the top: `from dataclasses import dataclass, field` and `from clipforge.models import Transcript`.

```python
@dataclass
class FakeTranscriber:
    transcript: Transcript
    model_name: str = "fake-whisper"
    calls: list[str | None] = field(default_factory=list)

    def transcribe(self, audio: Path, language: str | None) -> Transcript:
        assert audio.exists()
        self.calls.append(language)
        return self.transcript
```

- [ ] **Step 2: Write the failing `tests/stages/test_transcribe.py`**

```python
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from clipforge.config import Settings
from clipforge.models import SourceMedia, StageName, Transcript
from clipforge.pipeline.errors import PermanentError
from clipforge.stages import transcribe
from clipforge.stages.transcribe import to_transcript
from tests.stages.helpers import FakeTranscriber, make_ctx


def seg(text: str, words: list[tuple[str, float, float]]) -> NS:
    return NS(text=text, words=[NS(word=w, start=s, end=e, probability=0.9) for w, s, e in words])


def test_to_transcript_cleans_words() -> None:
    segments = [
        seg(" Hello world.", [(" Hello", 0.0, 0.4), (" world.", 0.5, 0.9)]),
        seg(" Oops", [(" Oops", 2.0, 1.8), ("  ", 2.1, 2.2), (" early", -0.2, 0.1)]),
        seg(" ", []),
    ]
    t = to_transcript(segments, "en", 0.98, 10.0, "large-v3-turbo")
    assert [w.text for w in t.words] == ["Hello", "world.", "Oops", "early"]
    oops, early = t.words[2], t.words[3]
    assert (oops.start, oops.end) == (2.0, 2.0)  # inverted times clamped
    assert early.start == 0.0  # negative start clamped
    assert len(t.segments) == 2
    assert (t.segments[1].start, t.segments[1].end) == (0.0, 2.0)
    assert (t.language, t.model, t.duration_s) == ("en", "large-v3-turbo", 10.0)


def make_source(root: Path) -> SourceMedia:
    audio = root / "cache" / "ingest" / "k" / "audio.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"RIFF")
    return SourceMedia(
        video_path="cache/ingest/k/source.mp4", audio_path="cache/ingest/k/audio.wav",
        source_hash="b" * 64, duration_s=10.0, fps=30.0, width=1920, height=1080,
        video_codec="h264", size_bytes=4,
    )  # fmt: skip


def test_run_caches_and_records_gpu_cost(tmp_path: Path, short_transcript: Transcript) -> None:
    ctx = make_ctx(tmp_path)
    fake = FakeTranscriber(short_transcript)
    settings = Settings(_env_file=None, jobs_root=tmp_path)
    source = make_source(tmp_path)
    first = transcribe.run(ctx, source, fake, settings, "en")
    second = transcribe.run(ctx, source, fake, settings, "en")
    assert first == second and fake.calls == ["en"]
    [cost, cached] = ctx.job().cost.stages
    assert cost.stage is StageName.TRANSCRIBE and cost.gpu_type == "L4" and cost.gpu_s >= 0
    assert cost.usd_estimate == pytest.approx(settings.prices.gpu_usd("L4", cost.gpu_s))
    assert cached.cached
    transcribe.run(ctx, source, fake, settings, None)  # a different language hint is a new key
    assert fake.calls == ["en", None]


def test_no_speech_is_permanent(tmp_path: Path) -> None:
    empty = Transcript(language="en", duration_s=10.0, model="fake", segments=[])
    settings = Settings(_env_file=None, jobs_root=tmp_path)
    with pytest.raises(PermanentError, match="no speech"):
        transcribe.run(make_ctx(tmp_path), make_source(tmp_path), FakeTranscriber(empty), settings, None)


@pytest.mark.gpu
def test_whisper_on_gpu(tmp_path: Path, talking_head: Path) -> None:
    """Runs where faster-whisper and CUDA exist: the Modal GPU image (Plan 3)."""
    pytest.importorskip("faster_whisper")
    from clipforge.doctor import audio_wav_bytes

    audio = tmp_path / "audio.wav"
    audio.write_bytes(audio_wav_bytes(talking_head))
    settings = Settings(_env_file=None)
    whisper = transcribe.WhisperTranscriber(settings.whisper_model_path, settings.whisper_model)
    transcript = whisper.transcribe(audio, None)
    assert transcript.language == "en" and len(transcript.words) > 10
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/stages/test_transcribe.py -q -m "not gpu"`
Expected: `ImportError: cannot import name 'transcribe' from 'clipforge.stages'`.

- [ ] **Step 4: Create `src/clipforge/stages/transcribe.py`**

```python
"""Transcribe: faster-whisper word timestamps (ADR-11). Runs inside transcribe_step on the L4.

`WhisperTranscriber` imports faster-whisper lazily: it is installed only in the GPU image.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import Segment, SourceMedia, StageCost, StageName, Transcript, Word
from clipforge.pipeline.errors import PermanentError

STAGE_VERSION = "1"


class Transcriber(Protocol):
    model_name: str

    def transcribe(self, audio: Path, language: str | None) -> Transcript: ...


def to_transcript(
    segments: Iterable[Any],
    language: str,
    language_probability: float | None,
    duration_s: float,
    model_name: str,
) -> Transcript:
    """Convert faster-whisper segments, dropping empty words and clamping bad times."""
    out: list[Segment] = []
    for segment in segments:
        words: list[Word] = []
        for w in segment.words or []:
            text = str(w.word).strip()
            if not text:
                continue
            start = max(0.0, float(w.start))
            end = max(start, float(w.end))
            probability = float(w.probability) if w.probability is not None else None
            words.append(
                Word(text=text, start=round(start, 3), end=round(end, 3), probability=probability)
            )
        if words:
            out.append(
                Segment(
                    start=min(w.start for w in words),
                    end=max(w.end for w in words),
                    text=str(segment.text).strip(),
                    words=words,
                )
            )
    return Transcript(
        language=language,
        language_probability=language_probability,
        duration_s=duration_s,
        model=model_name,
        segments=out,
    )


class WhisperTranscriber:
    """faster-whisper on CUDA, fp16, batched, with word timestamps."""

    def __init__(self, model_path: str, model_name: str, batch_size: int = 16) -> None:
        self.model_path = model_path
        self.model_name = model_name
        self.batch_size = batch_size
        self._pipeline: Any = None

    def _load(self) -> Any:
        if self._pipeline is None:
            from faster_whisper import BatchedInferencePipeline, WhisperModel

            model = WhisperModel(self.model_path, device="cuda", compute_type="float16")
            self._pipeline = BatchedInferencePipeline(model)
        return self._pipeline

    def transcribe(self, audio: Path, language: str | None) -> Transcript:
        segments, info = self._load().transcribe(
            str(audio), batch_size=self.batch_size, word_timestamps=True, language=language
        )
        return to_transcript(
            segments, info.language, info.language_probability, info.duration, self.model_name
        )


def run(
    ctx: JobContext,
    source: SourceMedia,
    transcriber: Transcriber,
    settings: Settings,
    language: str | None,
) -> Stored[Transcript]:
    key = cache_key(
        "transcribe",
        STAGE_VERSION,
        [],
        {
            "source_hash": source.source_hash,
            "language": language or "auto",
            "model": transcriber.model_name,
        },
    )

    def compute(out_dir: Path) -> Transcript:
        ctx.report(StageName.TRANSCRIBE, 5, "transcribing")
        started = time.monotonic()
        transcript = transcriber.transcribe(ctx.path(source.audio_path), language)
        gpu_s = time.monotonic() - started
        ctx.record_cost(
            StageCost(
                stage=StageName.TRANSCRIBE,
                wall_s=gpu_s,
                gpu_s=gpu_s,
                gpu_type=settings.gpu_type,
                usd_estimate=settings.prices.gpu_usd(settings.gpu_type, gpu_s),
            )
        )
        if not transcript.words:
            raise PermanentError("no speech was found in the video")
        return transcript

    return cached_stage(ctx, StageName.TRANSCRIBE, key, Transcript, compute)
```

- [ ] **Step 5: Run the tests and checks**

Run: `uv run pytest tests/stages/test_transcribe.py -q -m "not gpu" && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 3 passed (the gpu test is deselected); clean.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `src/clipforge/stages/transcribe.py`, `tests/stages/helpers.py`, `tests/stages/test_transcribe.py`. Message: `feat(transcribe): faster-whisper transcriber, word cleanup, cached stage`.

---

### Task 5: Versioned prompts and the LLM client

**Files:**
- Create: `src/clipforge/prompts.py`, `src/clipforge/llm.py`
- Test: `tests/test_prompts.py`, `tests/test_llm.py`

**Interfaces:**
- Produces:
  - `Prompt(version, model_default, body)`, a frozen dataclass with a `placeholders: set[str]` property and `render(**values: str) -> str`, which raises `ValueError` for missing or extra values.
  - `load_prompt(version: str, prompts_dir: Path) -> Prompt`, which raises `ValueError` if the frontmatter version doesn't match the file or the version is missing from `metadata.json`.
  - `LLMReply(text, input_tokens, output_tokens, model)`.
  - An `LLMClient` protocol with `model: str` and `complete(messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply`.
  - `AnthropicClient(api_key, model, client=None)`. It maps auth, permission, not-found and bad-request errors to `PermanentError`; rate-limit, 5xx and connection errors propagate so the step retries.

- [ ] **Step 1: Write the failing `tests/test_prompts.py`**

```python
import json
from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.prompts import load_prompt

PROMPTS = Settings(_env_file=None).prompts_dir


def test_load_highlights_v1() -> None:
    prompt = load_prompt("highlights_v1", PROMPTS)
    assert prompt.version == "highlights_v1" and prompt.model_default == "claude-haiku-4-5"
    assert prompt.placeholders == {"min_len", "max_len", "language", "transcript"}
    assert '{"clips": []}' in prompt.body  # JSON braces are not placeholders


def test_render_fills_only_declared_placeholders() -> None:
    prompt = load_prompt("highlights_v1", PROMPTS)
    text = prompt.render(
        min_len="30", max_len="60", language="en", transcript="[0.0-3.1] S1: {curly} words"
    )
    assert "Target clip length: 30–60 seconds." in text  # noqa: RUF001 (the prompt's en dash)
    assert "{curly}" in text  # inserted values are never re-scanned
    assert "{min_len}" not in text and '"clips"' in text


def test_render_rejects_missing_or_extra_values() -> None:
    prompt = load_prompt("highlights_v1", PROMPTS)
    with pytest.raises(ValueError, match="missing"):
        prompt.render(min_len="30", max_len="60", language="en")
    with pytest.raises(ValueError, match="unexpected"):
        prompt.render(min_len="30", max_len="60", language="en", transcript="t", tone="fun")


def test_version_must_match_file_and_registry(tmp_path: Path) -> None:
    (tmp_path / "metadata.json").write_text(json.dumps({"a_v1": {}}))
    (tmp_path / "a_v1.md").write_text("---\nversion: a_v2\n---\nbody {x}\n")
    with pytest.raises(ValueError, match="declares version"):
        load_prompt("a_v1", tmp_path)
    (tmp_path / "b_v1.md").write_text("---\nversion: b_v1\n---\nbody\n")
    with pytest.raises(ValueError, match="metadata.json"):
        load_prompt("b_v1", tmp_path)
```

- [ ] **Step 2: Write the failing `tests/test_llm.py`**

```python
import os
from types import SimpleNamespace as NS
from typing import Any

import anthropic
import httpx2
import pytest

from clipforge.llm import AnthropicClient
from clipforge.pipeline.errors import PermanentError


class StubMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


def reply(text: str) -> NS:
    return NS(
        content=[NS(type="text", text=text)],
        usage=NS(input_tokens=1200, output_tokens=80),
        stop_reason="end_turn",
    )


def api_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


def client_with(messages: StubMessages) -> AnthropicClient:
    return AnthropicClient(api_key="x", model="claude-haiku-4-5", client=NS(messages=messages))


def test_complete_returns_text_and_usage() -> None:
    stub = StubMessages(response=reply('{"clips": []}'))
    out = client_with(stub).complete([{"role": "user", "content": "hi"}], max_tokens=100)
    assert (out.text, out.input_tokens, out.output_tokens) == ('{"clips": []}', 1200, 80)
    assert out.model == "claude-haiku-4-5"
    assert stub.kwargs["model"] == "claude-haiku-4-5" and stub.kwargs["max_tokens"] == 100


@pytest.mark.parametrize(
    ("cls", "status"),
    [
        (anthropic.AuthenticationError, 401),
        (anthropic.PermissionDeniedError, 403),
        (anthropic.NotFoundError, 404),
        (anthropic.BadRequestError, 400),
    ],
)
def test_configuration_errors_are_permanent(cls: type[anthropic.APIStatusError], status: int) -> None:
    with pytest.raises(PermanentError):
        client_with(StubMessages(error=api_error(cls, status))).complete([])


def test_rate_limits_propagate_for_the_step_to_retry() -> None:
    with pytest.raises(anthropic.RateLimitError):
        client_with(StubMessages(error=api_error(anthropic.RateLimitError, 429))).complete([])


@pytest.mark.slow
def test_real_haiku_call() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    out = AnthropicClient(api_key=key, model="claude-haiku-4-5").complete(
        [{"role": "user", "content": 'Reply with exactly this JSON and nothing else: {"ok": true}'}],
        max_tokens=50,
    )
    assert '"ok"' in out.text and out.input_tokens > 0 and out.output_tokens > 0
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_prompts.py tests/test_llm.py -q -m "not slow"`
Expected: `ModuleNotFoundError: No module named 'clipforge.prompts'` (and `'clipforge.llm'`).

- [ ] **Step 4: Create `src/clipforge/prompts.py`**

```python
"""Versioned prompts (CLAUDE.md rule 4): `prompts/<name>_v<N>.md` with a frontmatter header,
registered in `prompts/metadata.json`. Released versions are never edited in place."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Prompt:
    version: str
    model_default: str
    body: str

    @property
    def placeholders(self) -> set[str]:
        return set(PLACEHOLDER.findall(self.body))

    def render(self, **values: str) -> str:
        missing = self.placeholders - values.keys()
        unexpected = values.keys() - self.placeholders
        if missing:
            raise ValueError(f"{self.version}: missing values for {sorted(missing)}")
        if unexpected:
            raise ValueError(f"{self.version}: unexpected values {sorted(unexpected)}")
        return PLACEHOLDER.sub(lambda m: values[m.group(1)], self.body)


def load_prompt(version: str, prompts_dir: Path) -> Prompt:
    path = prompts_dir / f"{version}.md"
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path} has no frontmatter")
    header, _, body = text[4:].partition("\n---\n")
    meta: dict[str, str] = {}
    for line in header.splitlines():
        name, sep, value = line.partition(":")
        if sep:
            meta[name.strip()] = value.strip()
    if meta.get("version") != version:
        raise ValueError(f"{path} declares version {meta.get('version')!r}, expected {version!r}")
    registry = json.loads((prompts_dir / "metadata.json").read_text())
    if version not in registry:
        raise ValueError(f"{version} is not registered in {prompts_dir / 'metadata.json'}")
    return Prompt(version=version, model_default=meta.get("model_default", ""), body=body.lstrip("\n"))
```

- [ ] **Step 5: Create `src/clipforge/llm.py`**

```python
"""LLM client for highlight selection (ADR-4). Stages depend on the `LLMClient` protocol, so
tests use a fake and the Anthropic SDK stays at the edge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from clipforge.pipeline.errors import PermanentError


@dataclass(frozen=True)
class LLMReply:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(Protocol):
    model: str

    def complete(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply: ...


class AnthropicClient:
    """Messages API via the official SDK (which retries 429/5xx itself before raising)."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self.model = model
        self._client: Any = client or anthropic.Anthropic(
            api_key=api_key, max_retries=3, timeout=120.0
        )

    def complete(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply:
        try:
            response = self._client.messages.create(
                model=self.model, max_tokens=max_tokens, messages=messages
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise PermanentError("the Anthropic API key was rejected") from exc
        except anthropic.NotFoundError as exc:
            raise PermanentError(f"the LLM model {self.model!r} is not available") from exc
        except anthropic.BadRequestError as exc:
            raise PermanentError(f"the LLM rejected the request: {exc.message}") from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMReply(
            text=text,
            input_tokens=int(response.usage.input_tokens),
            output_tokens=int(response.usage.output_tokens),
            model=self.model,
        )
```

- [ ] **Step 6: Run the tests and checks**

Run: `uv run pytest tests/test_prompts.py tests/test_llm.py -q -m "not slow" && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 10 passed; clean. If mypy reports `anthropic` as untyped, it isn't (the SDK ships types), so fix the reported line instead of ignoring it.

- [ ] **Step 7: Checkpoint (owner commits)**

Files: `src/clipforge/{prompts,llm}.py`, `tests/test_{prompts,llm}.py`. Message: `feat: versioned prompt loader and Anthropic client`.

---

### Task 6: Sentences, windows and snapping

**Files:**
- Create: `src/clipforge/stages/segmenting.py`
- Test: `tests/stages/test_segmenting.py`

**Interfaces:**
- Produces:
  - `SENTENCE_END`, `TRAILING`, `SILENCE_S = 0.3`.
  - `Sentence(start, end, text)`, frozen.
  - `split_sentences(words) -> list[Sentence]`.
  - `Window(index, start, end, sentences: tuple[Sentence, ...])`.
  - `make_windows(sentences, window_s=300.0, overlap_s=30.0) -> list[Window]`.
  - `format_window(window, speaker="S1") -> str`.
  - `CutPoints(starts, ends, word_starts, word_ends)`.
  - `cut_points(words, sentences) -> CutPoints`.
  - `snap(t, preferred, fallback, tolerance=3.0) -> float | None`.

- [ ] **Step 1: Write the failing `tests/stages/test_segmenting.py`**

```python
from clipforge.models import Transcript, Word
from clipforge.stages.segmenting import (
    cut_points,
    format_window,
    make_windows,
    snap,
    split_sentences,
)


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_split_on_punctuation_and_long_pauses() -> None:
    words = [
        w("Hello", 0.0, 0.4), w("there.", 0.5, 0.9), w("Next", 1.0, 1.3), w("part", 1.4, 1.7),
        w("after", 3.0, 3.3), w("pause", 3.4, 3.7), w("«Quoted!»", 3.8, 4.2), w("end", 4.3, 4.5),
    ]  # fmt: skip
    assert [s.text for s in split_sentences(words)] == [
        "Hello there.", "Next part", "after pause «Quoted!»", "end",
    ]  # fmt: skip


def test_runaway_sentences_are_capped() -> None:
    words = [w("word", i * 0.4, i * 0.4 + 0.3) for i in range(100)]
    assert [len(s.text.split()) for s in split_sentences(words)] == [40, 40, 20]


def test_windows_overlap_and_cover_everything(long_transcript: Transcript) -> None:
    sentences = split_sentences(long_transcript.words)
    windows = make_windows(sentences)
    assert [(win.start, win.end) for win in windows] == [(0, 300), (270, 570), (540, 840)]
    covered = {s for win in windows for s in win.sentences}
    assert covered == set(sentences)
    in_overlap = [s for s in sentences if 270 <= s.start < 300]
    assert in_overlap and all(s in windows[0].sentences and s in windows[1].sentences for s in in_overlap)


def test_short_transcripts_get_one_window() -> None:
    sentences = split_sentences([w("Hi.", 0.0, 0.5)])
    assert len(make_windows(sentences)) == 1
    assert make_windows([]) == []


def test_format_window_lines(long_transcript: Transcript) -> None:
    window = make_windows(split_sentences(long_transcript.words))[0]
    first = format_window(window).splitlines()[0]
    assert first == "[0.0-3.1] S1: The ocean teaches you patience and respect every."


def test_cut_points_include_silences() -> None:
    words = [w("a", 0.0, 0.2), w("b", 0.3, 0.5), w("c", 1.0, 1.2), w("d.", 1.3, 1.5)]
    points = cut_points(words, split_sentences(words))
    assert 1.0 in points.starts and 0.5 in points.ends  # the 0.5 s gap between b and c
    assert 0.3 not in points.starts  # a 0.1 s gap is not a silence


def test_snap_prefers_boundaries_then_words_then_gives_up() -> None:
    preferred, fallback = [10.0, 20.0], [10.0, 12.4, 20.0]
    assert snap(11.0, preferred, fallback) == 10.0
    assert snap(14.0, preferred, fallback) == 12.4  # no boundary within 3 s, nearest word
    assert snap(50.0, preferred, fallback) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/stages/test_segmenting.py -q`
Expected: `ImportError: cannot import name 'segmenting'`.

- [ ] **Step 3: Create `src/clipforge/stages/segmenting.py`**

```python
"""Transcript text for highlight selection: sentences, overlapping LLM windows, and the
points a clip may be cut at (ARCHITECTURE "Highlight selection")."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from itertools import pairwise

from clipforge.models import Word

SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")  # noqa: RUF001 (CJK punctuation)
TRAILING = "\"'”’)]»"  # noqa: RUF001 (curly quotes)
LONG_PAUSE_S = 1.0  # a pause this long ends a sentence even without punctuation
MAX_SENTENCE_WORDS = 40
SILENCE_S = 0.3  # a gap this long is a good place to cut


def ends_sentence(text: str) -> bool:
    return text.rstrip(TRAILING).endswith(SENTENCE_END)


@dataclass(frozen=True)
class Sentence:
    start: float
    end: float
    text: str


def split_sentences(words: list[Word]) -> list[Sentence]:
    sentences: list[Sentence] = []
    current: list[Word] = []
    for i, word in enumerate(words):
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = nxt is not None and nxt.start - word.end >= LONG_PAUSE_S
        if nxt is None or pause or ends_sentence(word.text) or len(current) >= MAX_SENTENCE_WORDS:
            text = " ".join(w.text for w in current)
            sentences.append(Sentence(current[0].start, current[-1].end, text))
            current = []
    return sentences


@dataclass(frozen=True)
class Window:
    index: int
    start: float
    end: float
    sentences: tuple[Sentence, ...]


def make_windows(
    sentences: list[Sentence], window_s: float = 300.0, overlap_s: float = 30.0
) -> list[Window]:
    """Windows of `window_s` starting every `window_s - overlap_s`; a sentence belongs to
    every window its start falls in."""
    if not sentences:
        return []
    windows: list[Window] = []
    start = 0.0
    last_start = sentences[-1].start
    while True:
        end = start + window_s
        chunk = tuple(s for s in sentences if start <= s.start < end)
        if chunk:
            windows.append(Window(len(windows), start, end, chunk))
        if end > last_start:
            return windows
        start += window_s - overlap_s


def format_window(window: Window, speaker: str = "S1") -> str:
    """`[start-end] SPEAKER: text`, one sentence per line (the prompt's transcript format)."""
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {speaker}: {s.text}" for s in window.sentences)


@dataclass(frozen=True)
class CutPoints:
    starts: list[float]  # preferred clip starts: sentence starts and speech after a silence
    ends: list[float]  # preferred clip ends: sentence ends and speech before a silence
    word_starts: list[float]  # fallback: any word boundary
    word_ends: list[float]


def cut_points(words: list[Word], sentences: list[Sentence]) -> CutPoints:
    starts = {s.start for s in sentences}
    ends = {s.end for s in sentences}
    for a, b in pairwise(words):
        if b.start - a.end >= SILENCE_S:
            ends.add(a.end)
            starts.add(b.start)
    return CutPoints(
        starts=sorted(starts),
        ends=sorted(ends),
        word_starts=sorted(w.start for w in words),
        word_ends=sorted(w.end for w in words),
    )


def _nearest(t: float, points: list[float]) -> float | None:
    if not points:
        return None
    i = bisect.bisect_left(points, t)
    options = points[max(0, i - 1) : i + 1]
    return min(options, key=lambda p: abs(p - t))


def snap(
    t: float, preferred: list[float], fallback: list[float], tolerance: float = 3.0
) -> float | None:
    for points in (preferred, fallback):
        best = _nearest(t, points)
        if best is not None and abs(best - t) <= tolerance:
            return best
    return None
```

- [ ] **Step 4: Run the tests and checks**

Run: `uv run pytest tests/stages/test_segmenting.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 7 passed; clean.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/stages/segmenting.py`, `tests/stages/test_segmenting.py`. Message: `feat: sentence split, LLM windows and cut-point snapping`.

---

### Task 7: Highlights

**Files:**
- Create: `src/clipforge/stages/highlights.py`
- Modify: `tests/stages/helpers.py` (append `FakeLLM`, `clip_json`)
- Test: `tests/stages/test_highlights.py`

**Interfaces:**
- Consumes: `LLMClient`, `LLMReply` and `Prompt` (Task 5), and the Task 6 segmenting functions.
- Produces:
  - `PROMPT_VERSION = "highlights_v1"`.
  - `HighlightsDeps(llm, prompt, settings)`.
  - `parse_clips(text) -> LLMClipsResponse`, which raises `ValueError`.
  - `run(ctx, transcript, options, deps) -> Stored[HighlightsResult]`.
  - Test helpers `FakeLLM(respond)` and `clip_json(*clips)`.

- [ ] **Step 1: Append to `tests/stages/helpers.py`.** Add these imports: `import json`, `import threading`, `from collections.abc import Callable` and `from clipforge.llm import LLMReply`.

```python
@dataclass
class FakeLLM:
    """Answers each call with `respond(messages)`; thread-safe, records every call."""

    respond: Callable[[list[dict[str, str]]], str]
    model: str = "claude-haiku-4-5"
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def complete(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply:
        with self._lock:
            self.calls.append(list(messages))
        return LLMReply(self.respond(messages), input_tokens=1000, output_tokens=100, model=self.model)


def clip_json(*clips: tuple[float, float, float]) -> str:
    """An LLM reply with clips given as (start, end, score)."""
    return json.dumps(
        {
            "clips": [
                {"start": s, "end": e, "score": sc, "hook": "h", "title": "t", "reason": "r"}
                for s, e, sc in clips
            ]
        }
    )
```

- [ ] **Step 2: Write the failing `tests/stages/test_highlights.py`**

```python
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from clipforge.config import Settings
from clipforge.models import ClipOptions, StageName, Transcript
from clipforge.pipeline.errors import PermanentError
from clipforge.prompts import load_prompt
from clipforge.stages import highlights
from clipforge.stages.highlights import parse_clips
from tests.builders import build_long_transcript, sentence_bounds
from tests.conftest import llm_fixture
from tests.stages.helpers import FakeLLM, clip_json, make_ctx

SETTINGS = Settings(_env_file=None)
PROMPT = load_prompt("highlights_v1", SETTINGS.prompts_dir)


def window_start(messages: list[dict[str, str]]) -> float:
    match = re.search(r"\[(\d+\.\d)-\d+\.\d\] S1:", messages[0]["content"])
    assert match is not None
    return float(match.group(1))


def run(tmp_path: Path, transcript: Transcript, llm: FakeLLM, **options: float | str | int):
    deps = highlights.HighlightsDeps(llm=llm, prompt=PROMPT, settings=SETTINGS)
    ctx = make_ctx(tmp_path)
    return ctx, highlights.run(ctx, transcript, ClipOptions(**options), deps)  # type: ignore[arg-type]


def test_parse_clips_handles_prose_fences_and_extra_keys() -> None:
    assert len(parse_clips(llm_fixture("llm_fenced.txt")).clips) == 1
    assert parse_clips(llm_fixture("llm_empty.json")).clips == []
    with pytest.raises(ValueError):
        parse_clips(llm_fixture("llm_malformed.txt"))
    with pytest.raises(ValidationError):
        parse_clips(llm_fixture("llm_invalid_schema.json"))
    with pytest.raises(ValueError, match="no JSON"):
        parse_clips("I could not find anything good.")


def test_selects_snaps_and_ranks(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        if ws == 0.0:
            return clip_json((b[10][0] + 0.4, b[20][1] - 0.3, 0.7))
        if 270 <= ws < 300:
            return clip_json((b[80][0] - 0.5, b[92][1] + 0.2, 0.9))
        return '{"clips": []}'

    llm = FakeLLM(respond)
    ctx, stored = run(tmp_path, long_transcript, llm)
    got = [(c.start, c.end, c.score) for c in stored.value.candidates]
    assert got == [(b[80][0], b[92][1], 0.9), (b[10][0], b[20][1], 0.7)]
    assert stored.value.candidates[1].raw_start == pytest.approx(b[10][0] + 0.4)
    assert stored.value.prompt_version == "highlights_v1" and stored.value.model == llm.model
    assert len(llm.calls) == 3
    prompt = llm.calls[0][0]["content"]
    assert "Target clip length: 30–60 seconds." in prompt  # noqa: RUF001 (the prompt's en dash)
    assert "Language: en" in prompt
    llm_costs = [c for c in ctx.job().cost.stages if c.stage is StageName.HIGHLIGHTS and c.llm_calls]
    assert len(llm_costs) == 3 and all(c.usd_estimate > 0 for c in llm_costs)


def test_overlapping_windows_are_deduped(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    same = (b[70][0], b[80][1])

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        if ws < 270:
            return clip_json((*same, 0.6))
        if ws < 540:
            return clip_json((*same, 0.8))
        return '{"clips": []}'

    _, stored = run(tmp_path, long_transcript, FakeLLM(respond))
    assert [(c.start, c.end, c.score) for c in stored.value.candidates] == [(*same, 0.8)]


def test_invalid_json_is_retried_once_with_the_error(
    tmp_path: Path, long_transcript: Transcript
) -> None:
    b = sentence_bounds(long_transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        if window_start(messages) < 270 and len(messages) == 1:
            return 'Sure! {"clips": [{"start": 1'
        return clip_json((b[10][0], b[20][1], 0.7))

    llm = FakeLLM(respond)
    _, stored = run(tmp_path, long_transcript, llm)
    assert len(llm.calls) == 4
    retry = next(call for call in llm.calls if len(call) == 3)
    assert retry[1]["role"] == "assistant" and "not valid" in retry[2]["content"]
    assert stored.value.candidates


def _first_clip_after(ws: float, b: list[tuple[float, float]]) -> tuple[float, float, float]:
    i = next(k for k, (start, _) in enumerate(b) if start >= ws + 10)
    return (b[i][0], b[i + 11][1], 0.8)


def test_bad_windows_are_dropped_up_to_the_threshold(tmp_path: Path) -> None:
    transcript = build_long_transcript(1200.0)  # 5 windows
    b = sentence_bounds(transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        return "not json" if ws < 270 else clip_json(_first_clip_after(ws, b))

    _, stored = run(tmp_path, transcript, FakeLLM(respond))
    assert len(stored.value.candidates) == 4  # 1 of 5 windows (20%) dropped


def test_too_many_bad_windows_fail_the_stage(tmp_path: Path) -> None:
    transcript = build_long_transcript(1200.0)
    b = sentence_bounds(transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        return "not json" if ws < 540 else clip_json(_first_clip_after(ws, b))

    with pytest.raises(PermanentError, match="2 of 5"):
        run(tmp_path, transcript, FakeLLM(respond))


def test_length_filter(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    reply = clip_json((b[10][0], b[12][1], 0.9), (b[10][0], b[20][1], 0.5))  # ~10.6 s and ~39.8 s
    _, stored = run(tmp_path, long_transcript, FakeLLM(lambda m: reply))
    assert [(c.start, c.end) for c in stored.value.candidates] == [(b[10][0], b[20][1])]


def test_no_candidates_is_permanent(tmp_path: Path, long_transcript: Transcript) -> None:
    with pytest.raises(PermanentError, match="no clip-worthy"):
        run(tmp_path, long_transcript, FakeLLM(lambda m: '{"clips": []}'))


def test_uses_the_requested_language(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    llm = FakeLLM(lambda m: clip_json((b[10][0], b[20][1], 0.7)))
    run(tmp_path, long_transcript, llm, language="pt")
    assert "Language: pt" in llm.calls[0][0]["content"]


def test_results_are_cached(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    llm = FakeLLM(lambda m: clip_json((b[10][0], b[20][1], 0.7)))
    deps = highlights.HighlightsDeps(llm=llm, prompt=PROMPT, settings=SETTINGS)
    ctx = make_ctx(tmp_path)
    first = highlights.run(ctx, long_transcript, ClipOptions(), deps)
    second = highlights.run(ctx, long_transcript, ClipOptions(n=2), deps)  # n is not in the key
    assert first == second and len(llm.calls) == 3


def test_api_errors_propagate_for_the_step_to_retry(
    tmp_path: Path, long_transcript: Transcript
) -> None:
    def respond(messages: list[dict[str, str]]) -> str:
        raise RuntimeError("overloaded")

    with pytest.raises(RuntimeError, match="overloaded"):
        run(tmp_path, long_transcript, FakeLLM(respond))


def test_empty_transcript_is_permanent(tmp_path: Path) -> None:
    empty = Transcript(language="en", duration_s=10.0, model="fake", segments=[])
    with pytest.raises(PermanentError, match="empty"):
        run(tmp_path, empty, FakeLLM(lambda m: '{"clips": []}'))
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/stages/test_highlights.py -q`
Expected: `ImportError: cannot import name 'highlights'`.

- [ ] **Step 4: Create `src/clipforge/stages/highlights.py`**

```python
"""Highlights: ask the LLM for clip candidates per transcript window, validate the JSON
(retry once with the error), snap to cut points, filter by length, dedupe and rank
(ARCHITECTURE "Highlight selection"; CLAUDE.md rule 5, applied per window)."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from clipforge.config import Settings
from clipforge.hashing import cache_key, canonical_json
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.llm import LLMClient
from clipforge.models import (
    ClipCandidate,
    ClipOptions,
    HighlightsResult,
    LLMClip,
    LLMClipsResponse,
    StageCost,
    StageName,
    Transcript,
)
from clipforge.pipeline.errors import PermanentError
from clipforge.prompts import Prompt
from clipforge.stages.segmenting import (
    CutPoints,
    Window,
    cut_points,
    format_window,
    make_windows,
    snap,
    split_sentences,
)

log = logging.getLogger(__name__)

STAGE_VERSION = "1"
PROMPT_VERSION = "highlights_v1"
MAX_WINDOW_FAILURE_RATE = 0.25
IOU_DUPLICATE = 0.5
MAX_TOKENS = 2048


@dataclass
class HighlightsDeps:
    llm: LLMClient
    prompt: Prompt
    settings: Settings


@dataclass
class _WindowResult:
    index: int
    clips: list[LLMClip]
    error: str | None


def parse_clips(text: str) -> LLMClipsResponse:
    """The JSON object in an LLM reply, tolerating prose and code fences around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    return LLMClipsResponse.model_validate_json(text[start : end + 1])


def run(
    ctx: JobContext, transcript: Transcript, options: ClipOptions, deps: HighlightsDeps
) -> Stored[HighlightsResult]:
    language = options.language or transcript.language
    transcript_hash = hashlib.sha256(canonical_json(transcript).encode()).hexdigest()
    key = cache_key(
        "highlights",
        STAGE_VERSION,
        [],
        {
            "transcript": transcript_hash,
            "min_len": f"{options.min_len:g}",
            "max_len": f"{options.max_len:g}",
            "language": language,
            "prompt": deps.prompt.version,
            "model": deps.llm.model,
        },
    )

    def compute(out_dir: Path) -> HighlightsResult:
        words = transcript.words
        sentences = split_sentences(words)
        windows = make_windows(sentences)
        if not windows:
            raise PermanentError("the transcript is empty")
        workers = max(1, deps.settings.llm_max_workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(
                pool.map(lambda w: _ask_window(ctx, deps, w, options, language), windows)
            )
        _write_report(out_dir, windows, results)

        failed = [r for r in results if r.error is not None]
        if len(failed) / len(windows) > MAX_WINDOW_FAILURE_RATE:
            raise PermanentError(
                f"the LLM returned invalid JSON for {len(failed)} of {len(windows)} "
                "transcript windows"
            )
        for r in failed:
            log.warning("highlights window %d dropped: %s", r.index, r.error)

        points = cut_points(words, sentences)
        candidates = [
            c
            for r in results
            for clip in r.clips
            if (c := _snap(clip, r.index, points, options)) is not None
        ]
        ranked = _dedupe(sorted(candidates, key=lambda c: c.score, reverse=True))
        if not ranked:
            raise PermanentError("no clip-worthy segments found in this video")
        ctx.report(StageName.HIGHLIGHTS, 100, f"{len(ranked)} candidates")
        return HighlightsResult(
            candidates=ranked, prompt_version=deps.prompt.version, model=deps.llm.model
        )

    return cached_stage(ctx, StageName.HIGHLIGHTS, key, HighlightsResult, compute)


def _ask_window(
    ctx: JobContext, deps: HighlightsDeps, window: Window, options: ClipOptions, language: str
) -> _WindowResult:
    text = deps.prompt.render(
        min_len=f"{options.min_len:g}",
        max_len=f"{options.max_len:g}",
        language=language,
        transcript=format_window(window),
    )
    messages = [{"role": "user", "content": text}]
    error = "no reply"
    for _ in range(2):  # first try + one retry with the validation error (rule 5)
        reply = deps.llm.complete(messages, max_tokens=MAX_TOKENS)
        ctx.record_cost(
            StageCost(
                stage=StageName.HIGHLIGHTS,
                llm_model=reply.model,
                llm_input_tokens=reply.input_tokens,
                llm_output_tokens=reply.output_tokens,
                llm_calls=1,
                usd_estimate=deps.settings.prices.llm_usd(
                    reply.model, reply.input_tokens, reply.output_tokens
                ),
            )
        )
        try:
            return _WindowResult(window.index, parse_clips(reply.text).clips, None)
        except ValueError as exc:  # json and pydantic validation errors
            error = str(exc)
            messages = [
                *messages,
                {"role": "assistant", "content": reply.text},
                {
                    "role": "user",
                    "content": f"Your reply was not valid: {error[:500]}\n"
                    "Return only the corrected JSON object, with no prose.",
                },
            ]
    return _WindowResult(window.index, [], error)


def _snap(
    clip: LLMClip, window_index: int, points: CutPoints, options: ClipOptions
) -> ClipCandidate | None:
    start = snap(clip.start, points.starts, points.word_starts)
    end = snap(clip.end, points.ends, points.word_ends)
    if start is None or end is None or end <= start:
        return None
    if not options.min_len <= end - start <= options.max_len:
        return None
    return ClipCandidate(
        start=start,
        end=end,
        score=clip.score,
        hook=clip.hook,
        title=clip.title,
        reason=clip.reason,
        window_index=window_index,
        raw_start=clip.start,
        raw_end=clip.end,
    )


def _iou(a: ClipCandidate, b: ClipCandidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = max(a.end, b.end) - min(a.start, b.start)
    return inter / union if union > 0 else 0.0


def _dedupe(ranked: list[ClipCandidate]) -> list[ClipCandidate]:
    kept: list[ClipCandidate] = []
    for candidate in ranked:
        if all(_iou(candidate, k) <= IOU_DUPLICATE for k in kept):
            kept.append(candidate)
    return kept


def _write_report(out_dir: Path, windows: list[Window], results: list[_WindowResult]) -> None:
    """windows.json next to the cached result, for debugging prompt quality."""
    report = [
        {"index": w.index, "start": w.start, "end": w.end, "clips": len(r.clips), "error": r.error}
        for w, r in zip(windows, results, strict=True)
    ]
    (out_dir / "windows.json").write_text(json.dumps(report, indent=2))
```

- [ ] **Step 5: Run the tests and checks**

Run: `uv run pytest tests/stages/test_highlights.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 13 passed; clean.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `src/clipforge/stages/highlights.py`, `tests/stages/helpers.py`, `tests/stages/test_highlights.py`. Message: `feat(highlights): windowed LLM selection with validation, snapping and dedupe`.

---

### Task 8: Reframe (simple)

**Files:**
- Create: `src/clipforge/stages/reframe.py`
- Test: `tests/stages/test_reframe.py`

**Interfaces:**
- Produces:
  - `reframe.STAGE_VERSION`, `OUT_W = 1080`, `OUT_H = 1920`.
  - `plan(spec: ClipSpec) -> CropTrack`. It's pure and uncached, because nothing is written.

- [ ] **Step 1: Write the failing `tests/stages/test_reframe.py`**

```python
import pytest

from clipforge.models import ClipOptions, ClipSpec, CropBox
from clipforge.stages.reframe import plan
from tests.test_models import make_source, make_spec


def spec(width: int, height: int, mode: str = "auto") -> ClipSpec:
    source = make_source().model_copy(update={"width": width, "height": height})
    return make_spec().model_copy(update={"source": source, "options": ClipOptions(reframe=mode)})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("width", "height", "mode", "expected"),
    [
        (1920, 1080, "auto", CropBox(x=656, y=0, w=608, h=1080)),  # 16:9: center crop
        (1440, 1080, "auto", CropBox(x=416, y=0, w=608, h=1080)),  # 4:3 is still landscape
        (1280, 720, "center", CropBox(x=438, y=0, w=404, h=720)),
        (1921, 1081, "auto", CropBox(x=656, y=0, w=608, h=1080)),  # odd sizes give even crops
        (1080, 1080, "center", CropBox(x=236, y=0, w=608, h=1080)),  # forced center on square
        (720, 1600, "center", CropBox(x=0, y=160, w=720, h=1280)),  # taller than 9:16
        (1080, 1920, "auto", CropBox(x=0, y=0, w=1080, h=1920)),  # already 9:16: full frame
        (1080, 1920, "blur", CropBox(x=0, y=0, w=1080, h=1920)),  # nothing to blur
    ],
)
def test_center_crops(width: int, height: int, mode: str, expected: CropBox) -> None:
    track = plan(spec(width, height, mode))
    assert track.mode == "center" and track.box == expected
    assert (track.out_width, track.out_height) == (1080, 1920)


@pytest.mark.parametrize(
    ("width", "height", "mode"),
    [(1080, 1080, "auto"), (720, 1600, "auto"), (1920, 1080, "blur"), (1080, 1350, "auto")],
)
def test_blur_fallback(width: int, height: int, mode: str) -> None:
    track = plan(spec(width, height, mode))
    assert track.mode == "blur_fallback" and track.box is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/stages/test_reframe.py -q`
Expected: `ImportError: cannot import name 'reframe'`.

- [ ] **Step 3: Create `src/clipforge/stages/reframe.py`**

```python
"""Reframe (Phase 1, simple): center crop to 9:16, or blurred-background fit.

`auto` center-crops landscape sources and blur-fits near-square or tall ones, where a center
crop would cut too much. Face tracking replaces this in Phase 3."""

from __future__ import annotations

from clipforge.models import ClipSpec, CropBox, CropTrack

STAGE_VERSION = "1"
OUT_W, OUT_H = 1080, 1920
TARGET = OUT_W / OUT_H
LANDSCAPE_MIN = 1.2  # width/height above this counts as landscape for "auto"


def _even(value: float) -> int:
    n = int(round(value))
    return n - n % 2


def plan(spec: ClipSpec) -> CropTrack:
    w, h = spec.source.width, spec.source.height
    aspect = w / h
    mode = spec.options.reframe
    if abs(aspect - TARGET) < 0.01:  # already 9:16: use the whole frame
        box = CropBox(x=0, y=0, w=_even(w), h=_even(h))
        return CropTrack(clip_id=spec.clip_id, mode="center", box=box)
    if mode == "blur" or (mode == "auto" and aspect < LANDSCAPE_MIN):
        return CropTrack(clip_id=spec.clip_id, mode="blur_fallback", box=None)
    if aspect > TARGET:  # wider than 9:16: keep the full height, crop the width
        crop_h = h - h % 2
        crop_w = min(w - w % 2, _even(crop_h * TARGET))
    else:  # taller than 9:16: keep the full width, crop the height
        crop_w = w - w % 2
        crop_h = min(h - h % 2, _even(crop_w / TARGET))
    box = CropBox(x=(w - crop_w) // 2, y=(h - crop_h) // 2, w=crop_w, h=crop_h)
    return CropTrack(clip_id=spec.clip_id, mode="center", box=box)
```

- [ ] **Step 4: Run the tests and checks**

Run: `uv run pytest tests/stages/test_reframe.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 12 passed; clean.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/stages/reframe.py`, `tests/stages/test_reframe.py`. Message: `feat(reframe): center crop and blur fallback`.

---

### Task 9: Captions

**Files:**
- Create: `src/clipforge/stages/captions.py`
- Test: `tests/stages/test_captions.py`

**Interfaces:**
- Consumes: `SENTENCE_END`, `TRAILING` and `ends_sentence` (Task 6).
- Produces:
  - `captions.STAGE_VERSION`, `STYLE = "default"`, `FONT = "Anton"`, `MARGIN_V = 480`.
  - `clip_words(transcript, start, end) -> list[Word]`, with times relative to the clip.
  - `chunk_words(words) -> list[list[Word]]`.
  - `ass_time(t)` and `srt_time(t)`.
  - `build_ass(chunks) -> str` and `build_srt(chunks) -> str`.
  - `run(ctx, spec, transcript) -> Stored[CaptionFiles]`, writing `clip.ass` and `clip.srt` into its cache dir, with `offset_s == spec.start`.

- [ ] **Step 1: Write the failing `tests/stages/test_captions.py`**

```python
from pathlib import Path

from clipforge.models import Segment, Transcript, Word
from clipforge.stages import captions
from clipforge.stages.captions import (
    ass_time,
    build_ass,
    build_srt,
    chunk_words,
    clip_words,
    srt_time,
)
from tests.stages.helpers import make_ctx
from tests.test_models import make_spec


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def transcript_of(words: list[Word]) -> Transcript:
    segment = Segment(start=words[0].start, end=words[-1].end, text="", words=words)
    return Transcript(language="en", duration_s=1800.0, model="fake", segments=[segment])


def dialogues(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def test_time_formats() -> None:
    assert ass_time(0) == "0:00:00.00" and ass_time(3723.456) == "1:02:03.46"
    assert srt_time(0) == "00:00:00,000" and srt_time(3723.456) == "01:02:03,456"


def test_clip_words_are_shifted_clamped_and_filtered() -> None:
    t = transcript_of([w("before", 8.0, 9.5), w("edge", 9.8, 10.3), w("in", 11.0, 11.2), w("after", 21.0, 22.0)])
    got = clip_words(t, 10.0, 20.0)
    assert [(x.text, x.start, x.end) for x in got] == [("edge", 0.0, 0.3), ("in", 1.0, 1.2)]


def test_chunks_break_on_size_duration_punctuation_and_gaps() -> None:
    words = [
        w("one", 0.0, 0.2), w("two", 0.3, 0.5), w("three", 0.6, 0.8), w("four.", 0.9, 1.1),
        w("five", 1.2, 1.4), w("six", 2.5, 2.7), w("long", 2.8, 4.6),
    ]  # fmt: skip
    assert [[x.text for x in c] for c in chunk_words(words)] == [
        ["one", "two", "three"], ["four."], ["five"], ["six"], ["long"],
    ]  # fmt: skip


def test_build_ass_highlights_one_word_per_event() -> None:
    chunks = [[w("hello", 0.5, 0.9), w("world", 1.0, 1.4)]]
    ass = build_ass(chunks)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Default,Anton," in ass and ",2,60,60,480,1" in ass  # bottom-center, MarginV 480
    events = dialogues(ass)
    assert len(events) == 2
    assert events[0].startswith("Dialogue: 0,0:00:00.50,0:00:01.00,Default")
    assert "{\\c&H0000FFFF&}HELLO{\\c&H00FFFFFF&} WORLD" in events[0]
    assert "HELLO {\\c&H0000FFFF&}WORLD{\\c&H00FFFFFF&}" in events[1]
    assert events[1].split(",")[2] == "0:00:01.40"


def test_ass_control_characters_are_stripped() -> None:
    events = dialogues(build_ass([[w("{\\b1}hack\\N", 0.0, 0.5), w("ok", 0.6, 0.9)]]))
    text = events[0].split(",", 9)[9]
    assert "\\b1" not in text and "\\N" not in text
    assert text.count("{") == 2  # only our two color tags
    assert "HACK" in text


def test_build_srt() -> None:
    srt = build_srt([[w("Hello", 0.5, 0.9), w("there.", 1.0, 1.4)], [w("Bye", 2.0, 2.3)]])
    assert srt.split("\n\n")[0] == "1\n00:00:00,500 --> 00:00:01,400\nHello there."
    assert srt.strip().split("\n\n")[1] == "2\n00:00:02,000 --> 00:00:02,300\nBye"


def test_run_writes_cached_files(tmp_path: Path) -> None:
    spec = make_spec()  # 812.4 → 871.9
    t = transcript_of([w("inside", 812.6, 813.0), w("clip.", 813.1, 813.5)])
    ctx = make_ctx(tmp_path)
    first = captions.run(ctx, spec, t)
    second = captions.run(ctx, spec, t)
    assert first == second
    files = first.value
    assert files.offset_s == spec.start and files.style == "default"
    assert len(dialogues(ctx.path(files.ass_path).read_text())) == 2
    assert "inside clip." in ctx.path(files.srt_path).read_text()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/stages/test_captions.py -q`
Expected: `ImportError: cannot import name 'captions'`.

- [ ] **Step 3: Create `src/clipforge/stages/captions.py`**

```python
"""Captions: word-level ASS (one style preset) and SRT for a clip.

Up to 3 words per line; the word being spoken is yellow. Positioned bottom-center with
MarginV 480 on a 1920 canvas, clear of the platform UI in the bottom 15%."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import CaptionFiles, ClipSpec, StageName, Transcript, Word
from clipforge.stages.segmenting import ends_sentence

STAGE_VERSION = "1"
STYLE = "default"
FONT = "Anton"
FONT_SIZE = 110
MARGIN_V = 480
MAX_WORDS = 3
MAX_CHUNK_S = 1.5
CHUNK_GAP_S = 0.5
MIN_EVENT_S = 0.05
WHITE = "&H00FFFFFF&"
HIGHLIGHT = "&H0000FFFF&"  # yellow; ASS colors are &HAABBGGRR
_ASS_CONTROL = re.compile(r"\\[Nnh]|[{}\\\r\n]")

_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,0,2,60,60,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""  # noqa: E501


def clip_words(transcript: Transcript, start: float, end: float) -> list[Word]:
    """Words overlapping [start, end), with times relative to `start` and clamped to the clip."""
    duration = end - start
    out: list[Word] = []
    for word in transcript.words:
        if word.end <= start or word.start >= end:
            continue
        s = max(0.0, word.start - start)
        e = min(duration, word.end - start)
        out.append(Word(text=word.text, start=round(s, 3), end=round(max(s, e), 3)))
    return out


def chunk_words(words: list[Word]) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (
            len(current) >= MAX_WORDS
            or word.end - current[0].start > MAX_CHUNK_S
            or ends_sentence(current[-1].text)
            or word.start - current[-1].end >= CHUNK_GAP_S
        ):
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def ass_time(t: float) -> str:
    cs = round(t * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean(text: str) -> str:
    """Remove ASS override/control sequences so speech can't inject styling."""
    return _ASS_CONTROL.sub("", text).strip()


def build_ass(chunks: list[list[Word]]) -> str:
    lines = [_HEADER]
    for chunk in chunks:
        tokens = [_clean(word.text).upper() for word in chunk]
        for i, word in enumerate(chunk):
            end = chunk[i + 1].start if i + 1 < len(chunk) else chunk[-1].end
            end = max(end, word.start + MIN_EVENT_S)
            shown = [
                f"{{\\c{HIGHLIGHT}}}{tok}{{\\c{WHITE}}}" if j == i else tok
                for j, tok in enumerate(tokens)
            ]
            lines.append(
                f"Dialogue: 0,{ass_time(word.start)},{ass_time(end)},Default,,0,0,0,,"
                + " ".join(shown)
            )
    return "\n".join(lines) + "\n"


def build_srt(chunks: list[list[Word]]) -> str:
    cues = []
    for n, chunk in enumerate(chunks, start=1):
        text = " ".join(word.text for word in chunk)
        cues.append(f"{n}\n{srt_time(chunk[0].start)} --> {srt_time(chunk[-1].end)}\n{text}")
    return "\n\n".join(cues) + "\n"


def run(ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[CaptionFiles]:
    words = clip_words(transcript, spec.start, spec.end)
    words_hash = hashlib.sha256(
        json.dumps([w.model_dump(mode="json") for w in words], sort_keys=True).encode()
    ).hexdigest()
    key = cache_key(
        "captions",
        STAGE_VERSION,
        [],
        {
            "source_hash": spec.source.source_hash,
            "start": f"{spec.start:.3f}",
            "end": f"{spec.end:.3f}",
            "style": STYLE,
            "words": words_hash,
        },
    )

    def compute(out_dir: Path) -> CaptionFiles:
        chunks = chunk_words(words)
        ass, srt = out_dir / "clip.ass", out_dir / "clip.srt"
        ass.write_text(build_ass(chunks))
        srt.write_text(build_srt(chunks))
        return CaptionFiles(
            clip_id=spec.clip_id,
            ass_path=ctx.rel(ass),
            srt_path=ctx.rel(srt),
            style=STYLE,
            offset_s=spec.start,
        )

    return cached_stage(ctx, StageName.CAPTIONS, key, CaptionFiles, compute, clip_id=spec.clip_id)
```

- [ ] **Step 4: Run the tests and checks**

Run: `uv run pytest tests/stages/test_captions.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 8 passed; clean.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/stages/captions.py`, `tests/stages/test_captions.py`. Message: `feat(captions): word-level ASS with highlight, SRT`.

---

### Task 10: Render

**Files:**
- Create: `src/clipforge/stages/render.py`
- Modify: `tests/stages/helpers.py` (append the media asserts)
- Test: `tests/stages/test_render.py`

**Interfaces:**
- Consumes: `ffmpeg.run`, `ffmpeg.probe_info`, `filter_path` (Task 2); `CropTrack` (Task 8); `CaptionFiles` (Task 9); `Settings.fonts_dir` (Task 1).
- Produces:
  - `render.STAGE_VERSION`, `TELEGRAM_LIMIT_BYTES`.
  - `video_bitrate(duration_s) -> int`.
  - `filter_graph(track, ass, fonts_dir) -> str`.
  - `run(ctx, spec, track, captions, settings) -> Stored[RenderedClip]`, writing `cache/render/<key>/clip.mp4`.
  - Test helpers `assert_vertical_clip(probe, expected_s)`, `gray_frame(path, t) -> bytes` and `band_diff(a, b) -> float`.

- [ ] **Step 1: Append to `tests/stages/helpers.py`.** Add `import subprocess` and `from clipforge.models import ProbeInfo` to its imports.

```python
def assert_vertical_clip(probe: ProbeInfo, expected_s: float) -> None:
    """The output contract every rendered clip must meet (CLAUDE.md testing rules)."""
    assert (probe.width, probe.height) == (1080, 1920)
    assert (probe.video_codec, probe.pix_fmt) == ("h264", "yuv420p")
    assert (probe.n_video_streams, probe.n_audio_streams, probe.audio_codec) == (1, 1, "aac")
    assert abs(probe.duration_s - expected_s) < 0.1
    assert probe.video_duration_s is not None and probe.audio_duration_s is not None
    assert abs(probe.video_duration_s - probe.audio_duration_s) < 0.05  # A/V sync
    assert probe.size_bytes < 50 * 1024 * 1024


def gray_frame(path: Path, t: float) -> bytes:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]  # fmt: skip
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def band_diff(a: bytes, b: bytes, rows: tuple[int, int] = (1300, 1560), width: int = 1080) -> float:
    """Mean absolute pixel difference in the caption band of two 1080x1920 gray frames."""
    lo, hi = rows[0] * width, rows[1] * width
    return sum(abs(x - y) for x, y in zip(a[lo:hi], b[lo:hi], strict=True)) / (hi - lo)
```

- [ ] **Step 2: Write the failing `tests/stages/test_render.py`**

```python
from pathlib import Path

import pytest

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.ffmpeg import media_info
from clipforge.models import ClipOptions, ClipSpec, Segment, SourceMedia, Transcript, Word
from clipforge.stages import captions, reframe, render
from clipforge.stages.render import TELEGRAM_LIMIT_BYTES, video_bitrate
from tests.conftest import MediaFactory, requires_ffmpeg
from tests.stages.helpers import assert_vertical_clip, band_diff, gray_frame, make_ctx, upload
from tests.test_models import make_candidate

pytestmark = requires_ffmpeg

WORDS = [Word(text="HELLO", start=1.2, end=1.6), Word(text="WORLD", start=1.7, end=2.4)]


def source_from(root: Path, path: Path) -> SourceMedia:
    info = media_info(path)
    return SourceMedia(
        video_path=upload(root, path), audio_path="unused.wav", source_hash=path.name * 2,
        duration_s=info.duration_s, fps=info.fps, width=info.width, height=info.height,
        rotation=info.rotation, video_codec=info.video_codec or "", size_bytes=1,
    )  # fmt: skip


def spec_for(source: SourceMedia, mode: str, start: float = 1.0, end: float = 4.0) -> ClipSpec:
    candidate = make_candidate().model_copy(update={"start": start, "end": end})
    return ClipSpec(
        clip_id="clip_01", rank=1, source=source, start=start, end=end, candidate=candidate,
        options=ClipOptions(reframe=mode),  # type: ignore[arg-type]
    )  # fmt: skip


def transcript(words: list[Word]) -> Transcript:
    segs = [Segment(start=words[0].start, end=words[-1].end, text="", words=words)] if words else []
    return Transcript(language="en", duration_s=6.0, model="fake", segments=segs)


def render_clip(root: Path, spec: ClipSpec, words: list[Word] = WORDS) -> Path:
    ctx = make_ctx(root)
    caps = captions.run(ctx, spec, transcript(words)).value
    stored = render.run(ctx, spec, reframe.plan(spec), caps, Settings(_env_file=None, jobs_root=root))
    return ctx.path(stored.value.video_path)


@pytest.mark.parametrize("mode", ["center", "blur"])
def test_render_meets_the_output_contract(tmp_path: Path, media: MediaFactory, mode: str) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), mode)
    out = render_clip(tmp_path, spec)
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


def test_captions_are_burned_in(tmp_path: Path, media: MediaFactory) -> None:
    source = source_from(tmp_path, media(width=640, height=360, duration_s=6.0))
    with_words = render_clip(tmp_path, spec_for(source, "center"))
    without = render_clip(tmp_path, spec_for(source, "center"), words=[])
    t = 0.4  # "HELLO" is on screen from 0.2 s to 0.6 s of the clip
    assert band_diff(gray_frame(with_words, t), gray_frame(without, t)) > 10


def test_rotated_source_renders_upright(tmp_path: Path, media: MediaFactory) -> None:
    phone = tmp_path / "phone.mp4"
    ffmpeg.run(["-display_rotation:v:0", "90", "-i", str(media(duration_s=6.0)), "-c", "copy", str(phone)])
    source = source_from(tmp_path, phone)
    assert (source.width, source.height) == (180, 320)
    out = render_clip(tmp_path, spec_for(source, "auto"))  # 9:16 after rotation: full frame
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


def test_renders_are_cached(tmp_path: Path, media: MediaFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "center")
    render_clip(tmp_path, spec)
    calls: list[list[str]] = []
    monkeypatch.setattr(ffmpeg, "run", lambda args, timeout=900: calls.append(args) or "")
    ctx = make_ctx(tmp_path)
    caps = captions.run(ctx, spec, transcript(WORDS)).value
    render.run(ctx, spec, reframe.plan(spec), caps, Settings(_env_file=None, jobs_root=tmp_path))
    assert calls == []


def test_bitrate_keeps_every_clip_under_the_telegram_limit() -> None:
    assert video_bitrate(10) == 8_000_000
    for duration in (30, 60, 120, 180):
        size = (video_bitrate(duration) + render.AUDIO_BPS) * duration / 8
        assert size < TELEGRAM_LIMIT_BYTES
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/stages/test_render.py -q`
Expected: `ImportError: cannot import name 'render'`.

- [ ] **Step 4: Create `src/clipforge/stages/render.py`**

```python
"""Render: one ffmpeg encode per clip. Accurate seek, crop or blur-fit to 1080x1920, burn in
the ASS captions, then libx264 + AAC with a bitrate cap that keeps clips under Telegram's
50 MB limit (ADR-13). CPU only (ADR-10)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.ffmpeg import filter_path
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import CaptionFiles, ClipSpec, CropTrack, RenderedClip, StageCost, StageName
from clipforge.pipeline.errors import PermanentError

log = logging.getLogger(__name__)

STAGE_VERSION = "1"
MAX_VIDEO_BPS = 8_000_000
MIN_VIDEO_BPS = 500_000
AUDIO_BPS = 128_000
TARGET_BYTES = 45 * 1024 * 1024
TELEGRAM_LIMIT_BYTES = 50 * 1024 * 1024
MAX_FPS = 60


def video_bitrate(duration_s: float) -> int:
    budget = TARGET_BYTES * 8 / duration_s - AUDIO_BPS
    return int(max(MIN_VIDEO_BPS, min(MAX_VIDEO_BPS, budget)))


def filter_graph(track: CropTrack, ass: Path, fonts_dir: Path) -> str:
    subs = f"ass=filename={filter_path(ass)}:fontsdir={filter_path(fonts_dir)}"
    w, h = track.out_width, track.out_height
    if track.mode == "center":
        box = track.box
        if box is None:
            raise ValueError("center crop without a box")
        return (
            f"[0:v]crop={box.w}:{box.h}:{box.x}:{box.y},"
            f"scale={w}:{h}:flags=lanczos,setsar=1,{subs}[v]"
        )
    bw, bh = w // 4, h // 4  # blur a small copy: much cheaper than blurring at full size
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"boxblur=10:1,scale={w}:{h}[bgb];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,{subs}[v]"
    )


def run(
    ctx: JobContext,
    spec: ClipSpec,
    track: CropTrack,
    captions: CaptionFiles,
    settings: Settings,
) -> Stored[RenderedClip]:
    box = track.box.model_dump() if track.box is not None else None
    key = cache_key(
        "render",
        STAGE_VERSION,
        [],
        {
            "source_hash": spec.source.source_hash,
            "start": f"{spec.start:.3f}",
            "end": f"{spec.end:.3f}",
            "mode": track.mode,
            "box": json.dumps(box, sort_keys=True),
            "captions": captions.ass_path,  # a cache path: changes when the captions change
        },
    )

    def compute(out_dir: Path) -> RenderedClip:
        started = time.monotonic()
        out = out_dir / "clip.mp4"
        bitrate = video_bitrate(spec.duration_s)
        fps = min(MAX_FPS, round(spec.source.fps) or 30)
        graph = filter_graph(track, ctx.path(captions.ass_path), settings.fonts_dir)
        stderr = ffmpeg.run(
            [
                "-ss", f"{spec.start:.3f}", "-i", str(ctx.path(spec.source.video_path)),
                "-t", f"{spec.duration_s:.3f}",
                "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-maxrate", str(bitrate), "-bufsize", str(bitrate * 2),
                "-pix_fmt", "yuv420p", "-r", str(fps),
                "-c:a", "aac", "-b:a", str(AUDIO_BPS), "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(out),
            ]
        )  # fmt: skip
        if "fontselect" in stderr or "Glyph" in stderr:
            log.warning("caption font problem while rendering %s: %s", spec.clip_id, stderr[-300:])
        probe = ffmpeg.probe_info(out)
        if probe.size_bytes > TELEGRAM_LIMIT_BYTES:
            raise PermanentError(f"{spec.clip_id} rendered larger than Telegram's 50 MB limit")
        ctx.record_cost(StageCost(stage=StageName.RENDER, wall_s=time.monotonic() - started))
        return RenderedClip(
            clip_id=spec.clip_id,
            spec=spec,
            video_path=ctx.rel(out),
            srt_path=captions.srt_path,
            encoder="libx264",
            probe=probe,
        )

    return cached_stage(ctx, StageName.RENDER, key, RenderedClip, compute, clip_id=spec.clip_id)
```

- [ ] **Step 5: Run the tests and checks**

Run: `uv run pytest tests/stages/test_render.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 6 passed; clean. If `test_captions_are_burned_in` fails because `band_diff` is at most 10, render one frame of each file to PNG and look at it before changing the threshold.

- [ ] **Step 6: Checkpoint (owner commits)**

Files: `src/clipforge/stages/render.py`, `tests/stages/helpers.py`, `tests/stages/test_render.py`. Message: `feat(render): single-pass 1080x1920 encode with captions and size cap`.

---

### Task 11: Package

**Files:**
- Create: `src/clipforge/stages/package.py`
- Test: `tests/stages/test_package.py`

**Interfaces:**
- Consumes: `merged_cost` (Task 1); the `Versions`, `JobMetadata`, `PackagedClip` and `PackageResult` models.
- Produces:
  - `package.STAGE_VERSION`.
  - `post_markdown(job, rendered) -> str`.
  - `run(ctx, job, source, transcript, rendered, settings, stage_versions) -> Stored[PackageResult]`, which writes `<job_id>/output/clip_NN_scoreX.XX/{video.mp4, captions.srt, post.md}`, `<job_id>/output/metadata.json` and `<job_id>/job.zip` (stored uncompressed).

- [ ] **Step 1: Write the failing `tests/stages/test_package.py`**

```python
import zipfile
from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.jobs import utcnow
from clipforge.models import ClipState, JobInput, JobMetadata, RenderedClip, StageCost, StageName
from clipforge.stages import package
from tests.stages.helpers import JOB_ID, make_ctx
from tests.test_models import make_rendered, make_source, make_spec, make_transcript

VERSIONS = {"ingest": "1", "render": "1"}


def rendered(root: Path, clip_id: str, rank: int, score: float) -> RenderedClip:
    base = make_rendered()
    spec = make_spec().model_copy(
        update={"clip_id": clip_id, "rank": rank,
                "candidate": make_spec().candidate.model_copy(update={"score": score})}
    )  # fmt: skip
    video = root / "cache" / "render" / clip_id / "clip.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4 " + clip_id.encode())
    srt = video.with_suffix(".srt")
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    return base.model_copy(
        update={"clip_id": clip_id, "spec": spec, "video_path": f"cache/render/{clip_id}/clip.mp4",
                "srt_path": f"cache/render/{clip_id}/clip.srt"}
    )  # fmt: skip


def test_package_layout_metadata_and_zip(tmp_path: Path) -> None:
    job_input = JobInput.model_validate(
        {"source_url": "https://cdn.example.com/ep.mp4", "permission": "cc_by",
         "source_credit": "Jane Doe, CC BY 4.0, https://example.com/ep"}
    )  # fmt: skip
    ctx = make_ctx(tmp_path, job_input)
    now = utcnow()
    for clip_id in ("clip_01", "clip_02"):
        state = ClipState(clip_id=clip_id, spec_ref="x", updated_at=now,
                          cost=[StageCost(stage=StageName.RENDER, clip_id=clip_id, usd_estimate=0.01)])  # fmt: skip
        ctx.store.save_clip(JOB_ID, state)
    ctx.record_cost(StageCost(stage=StageName.TRANSCRIBE, usd_estimate=0.05))
    job = ctx.job().model_copy(update={"clip_ids": ["clip_01", "clip_02"]})
    ctx.store.save(job)
    clips = [rendered(tmp_path, "clip_02", 2, 0.72), rendered(tmp_path, "clip_01", 1, 0.91)]
    settings = Settings(_env_file=None, jobs_root=tmp_path, git_sha="abc1234")

    result = package.run(ctx, job, make_source(), make_transcript(), clips, settings, VERSIONS).value

    output = tmp_path / JOB_ID / "output"
    assert [c.dir for c in result.clips] == ["clip_01_score0.91", "clip_02_score0.72"]
    for name in ("clip_01_score0.91", "clip_02_score0.72"):
        assert {p.name for p in (output / name).iterdir()} == {"video.mp4", "captions.srt", "post.md"}
    assert (output / "clip_01_score0.91" / "video.mp4").read_bytes() == b"mp4 clip_01"

    meta = JobMetadata.model_validate_json((output / "metadata.json").read_text())
    assert meta.input.permission == "cc_by" and meta.versions.git_sha == "abc1234"
    assert meta.versions.stages == VERSIONS and meta.versions.highlight_prompt == "highlights_v1"
    assert meta.cost.total_usd == pytest.approx(0.07)  # transcribe + two clip renders
    assert [c.clip_id for c in meta.clips] == ["clip_01", "clip_02"]

    post = (output / "clip_01_score0.91" / "post.md").read_text()
    assert "Credit: Jane Doe, CC BY 4.0" in post and "Permission: cc_by" in post

    assert result.zip_path == f"{JOB_ID}/job.zip"
    with zipfile.ZipFile(tmp_path / result.zip_path) as zf:
        names = set(zf.namelist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in zf.infolist())
    assert names == {
        "metadata.json",
        *(f"{d}/{f}" for d in ("clip_01_score0.91", "clip_02_score0.72")
          for f in ("video.mp4", "captions.srt", "post.md")),
    }  # fmt: skip
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/stages/test_package.py -q`
Expected: `ImportError: cannot import name 'package'`.

- [ ] **Step 3: Create `src/clipforge/stages/package.py`**

```python
"""Package: the delivered folder (clips, post.md, metadata.json) and job.zip (ADR-3, ADR-13).

Output is job-scoped (`<job_id>/output/`), since it names this job's clips and ranks."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import clipforge
from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage, merged_cost, utcnow
from clipforge.models import (
    Job,
    JobMetadata,
    PackagedClip,
    PackageResult,
    RenderedClip,
    SourceMedia,
    StageName,
    Transcript,
    Versions,
)

STAGE_VERSION = "1"
HIGHLIGHT_PROMPT = "highlights_v1"


def post_markdown(job: Job, clip: RenderedClip) -> str:
    candidate = clip.spec.candidate
    source = job.input.source_label or (str(job.input.source_url) if job.input.source_url else "uploaded file")
    lines = [
        f"# {candidate.title}",
        "",
        f"**Hook:** {candidate.hook}",
        f"**Score:** {candidate.score:.2f} · rank {clip.spec.rank} · "
        f"{clip.spec.start:.1f}s to {clip.spec.end:.1f}s of the source",
        "",
        f"Source: {source}",
        f"Permission: {job.input.permission}",
    ]
    if job.input.source_credit:
        lines.append(f"Credit: {job.input.source_credit}")
    return "\n".join(lines) + "\n"


def run(
    ctx: JobContext,
    job: Job,
    source: SourceMedia,
    transcript: Transcript,
    rendered: list[RenderedClip],
    settings: Settings,
    stage_versions: dict[str, str],
) -> Stored[PackageResult]:
    ordered = sorted(rendered, key=lambda r: r.spec.rank)
    key = cache_key(
        "package",
        STAGE_VERSION,
        [],
        {"job": job.job_id, "clips": ",".join(f"{r.clip_id}@{r.video_path}" for r in ordered)},
    )

    def compute(out_dir: Path) -> PackageResult:
        output = ctx.job_dir / "output"
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
        packaged: list[PackagedClip] = []
        for clip in ordered:
            name = f"{clip.clip_id}_score{clip.spec.candidate.score:.2f}"
            folder = output / name
            folder.mkdir()
            shutil.copyfile(ctx.path(clip.video_path), folder / "video.mp4")
            shutil.copyfile(ctx.path(clip.srt_path), folder / "captions.srt")
            (folder / "post.md").write_text(post_markdown(job, clip))
            packaged.append(
                PackagedClip(
                    clip_id=clip.clip_id,
                    rank=clip.spec.rank,
                    dir=name,
                    video=f"{name}/video.mp4",
                    srt=f"{name}/captions.srt",
                    post_md=f"{name}/post.md",
                    start=clip.spec.start,
                    end=clip.spec.end,
                    score=clip.spec.candidate.score,
                    title=clip.spec.candidate.title,
                    hook=clip.spec.candidate.hook,
                    probe=clip.probe,
                )
            )
        metadata = JobMetadata(
            job_id=job.job_id,
            input=job.input,
            source=source,
            transcript_language=transcript.language,
            clips=packaged,
            cost=merged_cost(ctx.store, job),
            versions=Versions(
                git_sha=settings.git_sha,
                clipforge=clipforge.__version__,
                stages=stage_versions,
                highlight_prompt=HIGHLIGHT_PROMPT,
                highlight_model=settings.highlight_model,
                whisper_model=transcript.model,
            ),
            started_at=job.created_at,
            finished_at=utcnow(),
        )
        metadata_path = output / "metadata.json"
        metadata_path.write_text(metadata.model_dump_json(indent=2))

        zip_path = ctx.job_dir / "job.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(output).as_posix())
        ctx.report(StageName.PACKAGE, 100, f"{len(packaged)} clips packaged")
        return PackageResult(
            output_dir=ctx.rel(output),
            zip_path=ctx.rel(zip_path),
            metadata_path=ctx.rel(metadata_path),
            clips=packaged,
        )

    return cached_stage(ctx, StageName.PACKAGE, key, PackageResult, compute)
```

- [ ] **Step 4: Run the tests and checks**

Run: `uv run pytest tests/stages/test_package.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 1 passed; clean.

- [ ] **Step 5: Checkpoint (owner commits)**

Files: `src/clipforge/stages/package.py`, `tests/stages/test_package.py`. Message: `feat(package): output folder, post.md, metadata.json and zip`.

---

### Task 12: `PipelineStages`, the end-to-end run and docs

**Files:**
- Create: `src/clipforge/stages/runner.py`
- Test: `tests/stages/test_pipeline_e2e.py`
- Modify: `ROADMAP.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: every stage above; `Deps`, `dispatch` and `service.create_job` from Plan 1.
- Produces:
  - `PipelineStages(settings, http, transcriber, llm, prompt)`, which implements `StageRunner`.
  - `PipelineStages.from_settings(settings, transcriber=None, llm=None) -> PipelineStages`, which Plan 3 calls inside Modal.
  - `STAGE_VERSIONS: dict[str, str]`.

- [ ] **Step 1: Write the failing `tests/stages/test_pipeline_e2e.py`**

```python
"""The whole chain on real stages: ffmpeg for real; fake transcriber and LLM (no GPU, no API)."""

import zipfile
from pathlib import Path

import httpx

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.models import ClipOptions, JobInput, JobMetadata, JobStatus, Permission, StageName
from clipforge.prompts import load_prompt
from clipforge.service import create_job
from clipforge.stages.runner import STAGE_VERSIONS, PipelineStages
from tests.builders import build_long_transcript, sentence_bounds
from tests.conftest import MediaFactory, requires_ffmpeg
from tests.pipeline.harness import Harness
from tests.stages.helpers import FakeLLM, FakeTranscriber, assert_vertical_clip, clip_json, upload


@requires_ffmpeg
def test_real_stages_end_to_end(tmp_path: Path, media: MediaFactory) -> None:
    rel = upload(tmp_path, media(width=640, height=360, duration_s=12.0))
    transcript = build_long_transcript(12.0)  # three sentences
    b = sentence_bounds(transcript)
    llm = FakeLLM(lambda m: clip_json((b[0][0], b[1][1], 0.9), (b[1][0], b[2][1], 0.8)))
    settings = Settings(_env_file=None, jobs_root=tmp_path)
    stages = PipelineStages(
        settings=settings,
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        transcriber=FakeTranscriber(transcript),
        llm=llm,
        prompt=load_prompt("highlights_v1", settings.prompts_dir),
    )
    h = Harness.build(tmp_path, stages)  # type: ignore[arg-type]
    options = ClipOptions(n=2, min_len=5, max_len=9)
    job = create_job(h.deps, JobInput(source_path=rel, permission=Permission.OWN, options=options))
    h.run()

    done = h.store.get(job.job_id)
    assert done.status is JobStatus.DONE, done.error
    assert h.event_kinds().count("clip_ready") == 2 and h.event_kinds()[-1] == "done"
    assert done.output_zip is not None
    with zipfile.ZipFile(tmp_path / done.output_zip) as zf:
        videos = sorted(n for n in zf.namelist() if n.endswith("video.mp4"))
        assert videos == ["clip_01_score0.90/video.mp4", "clip_02_score0.80/video.mp4"]
        zf.extractall(tmp_path / "unzipped")
    for name in videos:
        assert_vertical_clip(ffmpeg.probe_info(tmp_path / "unzipped" / name), expected_s=6.7)

    meta = JobMetadata.model_validate_json((tmp_path / "unzipped" / "metadata.json").read_text())
    stages_costed = {c.stage for c in meta.cost.stages if not c.cached}
    assert {StageName.INGEST, StageName.TRANSCRIBE, StageName.HIGHLIGHTS, StageName.RENDER} <= stages_costed
    assert meta.versions.stages == STAGE_VERSIONS
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/stages/test_pipeline_e2e.py -q`
Expected: `ModuleNotFoundError: No module named 'clipforge.stages.runner'`.

- [ ] **Step 3: Create `src/clipforge/stages/runner.py`**

```python
"""The real StageRunner: wires the stage modules to their clients (Plan 1's chain calls this).

Plan 3 builds one per Modal container with `PipelineStages.from_settings(...)`."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from clipforge.config import Settings
from clipforge.jobs import JobContext, Stored
from clipforge.llm import AnthropicClient, LLMClient
from clipforge.models import (
    ClipOptions,
    ClipSpec,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    RenderedClip,
    SourceMedia,
    StageName,
    Transcript,
)
from clipforge.prompts import Prompt, load_prompt
from clipforge.stages import captions, highlights, ingest, package, reframe, render, transcribe

STAGE_VERSIONS: dict[str, str] = {
    "ingest": ingest.STAGE_VERSION,
    "transcribe": transcribe.STAGE_VERSION,
    "highlights": highlights.STAGE_VERSION,
    "reframe": reframe.STAGE_VERSION,
    "captions": captions.STAGE_VERSION,
    "render": render.STAGE_VERSION,
    "package": package.STAGE_VERSION,
}


@dataclass
class PipelineStages:
    settings: Settings
    http: httpx.Client
    transcriber: transcribe.Transcriber
    llm: LLMClient
    prompt: Prompt

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        transcriber: transcribe.Transcriber | None = None,
        llm: LLMClient | None = None,
    ) -> PipelineStages:
        if llm is None:
            if settings.anthropic_api_key is None:
                raise RuntimeError("ANTHROPIC_API_KEY is not configured")
            llm = AnthropicClient(
                api_key=settings.anthropic_api_key.get_secret_value(), model=settings.highlight_model
            )
        return cls(
            settings=settings,
            http=httpx.Client(),
            transcriber=transcriber
            or transcribe.WhisperTranscriber(settings.whisper_model_path, settings.whisper_model),
            llm=llm,
            prompt=load_prompt(highlights.PROMPT_VERSION, settings.prompts_dir),
        )

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]:
        return ingest.run(ctx, job_input, ingest.IngestDeps(http=self.http, settings=self.settings))

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]:
        language = ctx.job().input.options.language
        return transcribe.run(ctx, source, self.transcriber, self.settings, language)

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]:
        deps = highlights.HighlightsDeps(llm=self.llm, prompt=self.prompt, settings=self.settings)
        return highlights.run(ctx, transcript, options, deps)

    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        track = reframe.plan(spec)
        ctx.report(StageName.CAPTIONS, 10, "captions")
        caps = captions.run(ctx, spec, transcript)
        ctx.report(StageName.RENDER, 30, "rendering")
        return render.run(ctx, spec, track, caps.value, self.settings)

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]:
        return package.run(ctx, job, source, transcript, rendered, self.settings, STAGE_VERSIONS)
```

- [ ] **Step 4: Run the end-to-end test and the full suite**

Run: `uv run pytest tests/stages/test_pipeline_e2e.py -q && uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass. The e2e test takes a few seconds because it does two real 1080x1920 renders. If it takes more than 30 s on this machine, mark it `@pytest.mark.slow` and record that in the ledger.

- [ ] **Step 5: Update the docs**

In `ROADMAP.md`, tick these Phase 1 boxes: `ingest`, `highlights`, `reframe` (simple), `captions`, `render` and `package`. Leave `transcribe` unticked; Plan 3 ticks it after the GPU test passes on Modal.

In `CLAUDE.md`'s layout block, add under `src/clipforge/`:

```
  ffmpeg.py         # ffmpeg/ffprobe wrappers (media_info, probe_info, run)
  prompts.py        # versioned prompt loader (prompts/<name>_v<N>.md + metadata.json)
  llm.py            # LLMClient protocol + AnthropicClient
```

and change the `stages/` line to:

```
  stages/           # one module per stage + segmenting.py (sentences/windows) + runner.py (PipelineStages)
```

In `docs/ARCHITECTURE.md`, add this section after "Reframing (Phase 3)":

```markdown
## Phase 1 stage details

- **Reframe (simple):** already 9:16 → full frame; `auto` center-crops sources wider than 1.2:1 and blur-fits the rest; `center`/`blur` force a mode.
- **Captions:** Anton (OFL, `assets/fonts/`), uppercase, ≤ 3 words per line, the spoken word in yellow, bottom-center with MarginV 480 on 1920 (clear of the bottom 15%). ASS control characters in speech are stripped.
- **Render:** one libx264 encode per clip (accurate `-ss`, crop or blur-fit, ASS burn-in), AAC 48 kHz 128 kb/s, video capped at `min(8 Mb/s, 45 MB·8/duration − audio)` so every clip fits Telegram's 50 MB.
- **Package:** `<job_id>/output/clip_NN_scoreX.XX/{video.mp4,captions.srt,post.md}`, `metadata.json` (with per-clip costs merged in), and an uncompressed `job.zip`.
```

- [ ] **Step 6: Final check**

Run: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 7: Checkpoint (owner commits)**

Files: `src/clipforge/stages/runner.py`, `tests/stages/test_pipeline_e2e.py`, `ROADMAP.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`. Message: `feat: real StageRunner and end-to-end pipeline test`.

---

## Self-review notes

- **Spec coverage:**
  - Ingest (direct links, Telegram uploads, limits, remux/transcode, wav): Task 3.
  - Transcribe (word cleanup, GPU cost): Task 4. Whisper on the GPU itself is verified in Plan 3.
  - Highlights (windows, rule 5 per window, snapping, length filter, dedupe): Tasks 6–7.
  - Reframe: Task 8. Captions (safe area): Task 9. Render (1080x1920, one encode, 50 MB cap, A/V sync, burn-in proof): Task 10.
  - Package (layout, metadata including costs, zip): Task 11.
  - The `StageRunner` wiring and a real-stage end-to-end run: Task 12.
  - Deferred minor #10 from Plan 1 (package lacking clip costs) is fixed by `merged_cost` (Tasks 1 and 11).
- **Type consistency:**
  - `Stored`, `cached_stage` and `JobContext` come from Plan 1 unchanged.
  - Each stage's `run` returns `Stored[...]`, which is exactly what `StageRunner` declares.
  - `CaptionFiles.offset_s` is `spec.start`. Render's seek (`-ss spec.start`) makes caption times start at 0, which matches `clip_words`.
  - `render.run` takes `caps.value`, a `CaptionFiles` rather than a `Stored`.
- **Known limits (deliberate):**
  - CPU steps record wall time and $0: Modal CPU pricing isn't in `Prices`, and rule 7 asks for GPU seconds and tokens.
  - The Telegram file URL contains the bot token. `sanitize` redacts it in user messages (Plan 1 review fix #4).

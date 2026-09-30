# Plan 4: Face-centered reframing per shot

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each clip is cut at its camera changes, and each shot is cropped to 9:16 around its largest face, fixed for the shot. Shots without a reliable face use the blurred-background fit.

**Architecture:**
- `stages/shots.py` finds cuts with ffmpeg's scene score.
- `stages/faces.py` samples frames and runs OpenCV's YuNet detector behind a `FaceDetector` protocol.
- `stages/reframe.track()` builds a cached `CropTrack(mode="tracked", segments=[...])`.
- `stages/render.py` splits the video per segment, crops or blurs each one, and concatenates them in the same single encode.

**Tech Stack:** Python 3.12, ffmpeg (scene filter, trim, concat), opencv-python-headless 5.0 (`cv2.FaceDetectorYN`, YuNet 2023mar ONNX model), numpy, pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-face-reframe-design.md` (ADR-19). Project rules: `CLAUDE.md`.

## Global Constraints

- Reframing never loses a clip. Any detection failure gives one whole-clip `blur` segment plus `log.warning`.
- Per-clip work only (rule 6). Detection reads `[spec.start, spec.end]` at low resolution: 320 px wide for scene detection, 640 px for faces.
- One encode per clip. Audio is mapped straight from the input (`-map 0:a:0`) and never goes through the video filters.
- Stage modules stay Modal-free. `cv2` is imported lazily inside `faces.py`.
- The only new dependency is `opencv-python-headless>=5.0` (numpy comes with it).
- Contracts change in `models.py` first (rule 2).
- Cache keys never contain `clip_id` or rank (ADR-8). A cached `CropTrack` is rebound to this job's `clip_id`.
- Scene threshold is **0.2**. It was measured on 2026-09-28: the owner's podcast has cuts at 0.43–0.83 and noise at ≤0.04, and a synthetic test cut scored 0.29. This is a ruling against the spec's 0.3.
- Shots shorter than **0.5 s** are merged into the previous one. There are **3** face samples per shot (at 25%, 50% and 75%). The YuNet score threshold is **0.6**.
- A face counts only if its width is ≥ **4%** of the frame width, so background posters and tiny faces are ignored.
- 9:16 box: `h = H − H%2`, `w = min(W − W%2, even(h·9/16))`, `x = even(clamp(cx − w/2, 0, W − w))`, `y = 0`.
- **The user does all git.** "Checkpoint" steps list files; never run git.

## Review Focus

1. **Vertical, square and near-square sources, or forced `reframe=center/blur`:** these must not run detection at all, and should behave exactly as today. Test: Task 4 `test_track_delegates_to_plan_without_detecting`.
2. **A tiny face in the background** (a poster, a TV, a person far away): not framed. That shot blurs, or uses the real face. Test: Task 4 `test_tiny_faces_are_ignored`.
3. **Fast edits with many cuts in one clip** (10+ segments): the render still meets the output contract and stays in sync. Test: Task 5 `test_render_many_segments`.
4. **The same range cut again in another job, with a different clip id:** a cache hit, rebound to the new clip id, and no detection. Test: Task 4 `test_track_is_cached_and_rebound`.
5. **A face at the frame edge:** the box stays inside the frame. Test: Task 4 `test_crop_box_is_clamped`.

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `src/clipforge/models.py` | modify | `CropSegment`; `CropTrack.mode` gains `"tracked"`, plus `segments` (Task 1) |
| `src/clipforge/config.py` | modify | `models_dir`, `scene_threshold` (Task 1) |
| `assets/models/face_detection_yunet_2023mar.onnx`, `assets/models/LICENSE` | new | YuNet model (MIT) (Task 1) |
| `pyproject.toml`, `uv.lock` | modify | opencv-python-headless (Task 1) |
| `src/clipforge/stages/shots.py` | new | `detect_cuts`, `segments_from_cuts` (Task 2) |
| `src/clipforge/stages/faces.py` | new | `Face`, `FaceDetector`, `YuNetDetector`, `sample_size`, `sample_frame` (Task 3) |
| `src/clipforge/stages/reframe.py` | modify | `crop_box`, `track` (Task 4) |
| `src/clipforge/stages/render.py` | modify | the tracked filter graph, segments in the cache key (Task 5) |
| `src/clipforge/stages/runner.py`, `src/clipforge/app.py` | modify | wiring, image mount (Task 6) |
| `tests/conftest.py` | modify | `two_shot` fixture: the fixture's real face at left, then right, with a cut at 2 s (Task 2) |
| `tests/stages/helpers.py` | modify | `source_from`, `spec_for` moved here from `test_render.py` (Task 4) |
| Tests | new or modify | `tests/test_models.py`, `tests/test_config.py`, `tests/stages/test_shots.py`, `tests/stages/test_faces.py`, `tests/stages/test_reframe.py`, `tests/stages/test_render.py`, `tests/stages/test_pipeline_e2e.py`, `tests/test_app.py` |
| Docs | modify | `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (ADR-19 Accepted), `ROADMAP.md`, `CLAUDE.md` (Task 6) |

---

### Task 1: Contracts, config, model file and dependency

**Files:**
- Modify: `src/clipforge/models.py` (classes `CropBox` … `CropTrack`), `src/clipforge/config.py`, `pyproject.toml`
- Create: `assets/models/face_detection_yunet_2023mar.onnx`, `assets/models/LICENSE`
- Test: `tests/test_models.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `CropSegment(start: float, end: float, mode: Literal["crop", "blur"], box: CropBox | None = None)`;
  - `CropTrack.mode: Literal["center", "blur_fallback", "tracked"]` and `CropTrack.segments: list[CropSegment] = []`;
  - `Settings.models_dir: Path` and `Settings.scene_threshold: float = 0.2`.

- [ ] **Step 1: Add the dependency and the model**

```bash
uv add "opencv-python-headless>=5.0"
mkdir -p assets/models
curl -fsSL -o assets/models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -fsSL -o assets/models/LICENSE \
  https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/LICENSE
uv run python -c "import cv2; print(cv2.__version__)"
```

Expected: the model is 232589 bytes, `LICENSE` starts with "MIT License", and cv2 prints `5.0.0` or later.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_models.py` (`CropBox`, `CropSegment` and `CropTrack` imported from `clipforge.models`; add the missing names to the existing import):

```python
def test_crop_segment_needs_box_only_for_crop() -> None:
    box = CropBox(x=0, y=0, w=404, h=720)
    assert CropSegment(start=0, end=2, mode="crop", box=box).box == box
    assert CropSegment(start=0, end=2, mode="blur").box is None
    with pytest.raises(ValidationError):
        CropSegment(start=0, end=2, mode="crop")
    with pytest.raises(ValidationError):
        CropSegment(start=0, end=2, mode="blur", box=box)
    with pytest.raises(ValidationError):
        CropSegment(start=2, end=2, mode="blur")


def test_tracked_crop_track_needs_contiguous_segments() -> None:
    a = CropSegment(start=0, end=2, mode="blur")
    b = CropSegment(start=2, end=5, mode="blur")
    ok = CropTrack(clip_id="clip_01", mode="tracked", box=None, segments=[a, b])
    assert len(ok.segments) == 2
    gap = CropSegment(start=2.5, end=5, mode="blur")
    late = CropSegment(start=0.5, end=2, mode="blur")
    for segments in ([], [a, gap], [late, b]):
        with pytest.raises(ValidationError):
            CropTrack(clip_id="clip_01", mode="tracked", box=None, segments=segments)
    with pytest.raises(ValidationError):  # the fixed modes carry no segments
        CropTrack(clip_id="clip_01", mode="blur_fallback", box=None, segments=[a])
```

Append to `tests/test_config.py`:

```python
def test_reframe_settings() -> None:
    s = Settings(_env_file=None)
    assert s.scene_threshold == 0.2
    assert (s.models_dir / "face_detection_yunet_2023mar.onnx").is_file()
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest -q tests/test_models.py tests/test_config.py`
Expected: FAIL. `ImportError: cannot import name 'CropSegment'` in test_models; `AttributeError: 'Settings' object has no attribute 'scene_threshold'` in test_config.

- [ ] **Step 4: Implement the contracts**

In `src/clipforge/models.py`, replace `class CropTrack` (and add `CropSegment` above it):

```python
class CropSegment(Contract):
    """One shot of a tracked clip: [start, end) in seconds relative to the clip start."""

    start: float = Field(ge=0)
    end: float
    mode: Literal["crop", "blur"]
    box: CropBox | None = None  # set for "crop"

    @model_validator(mode="after")
    def _check(self) -> CropSegment:
        if self.end <= self.start:
            raise ValueError("segment end must be after its start")
        if (self.mode == "crop") != (self.box is not None):
            raise ValueError("box is required for 'crop' and must be None for 'blur'")
        return self


class CropTrack(Contract):
    clip_id: str
    mode: Literal["center", "blur_fallback", "tracked"]
    box: CropBox | None  # set for "center"; None otherwise
    segments: list[CropSegment] = Field(default_factory=list)  # "tracked" only (ADR-19)
    out_width: int = 1080
    out_height: int = 1920

    @model_validator(mode="after")
    def _box_matches_mode(self) -> CropTrack:
        if self.mode == "tracked":
            if self.box is not None or not self.segments:
                raise ValueError("'tracked' needs segments and no box")
            if abs(self.segments[0].start) > 1e-6:
                raise ValueError("segments must start at 0")
            for before, after in zip(self.segments, self.segments[1:], strict=False):
                if abs(after.start - before.end) > 1e-3:
                    raise ValueError("segments must be contiguous")
            return self
        if self.segments:
            raise ValueError("only 'tracked' carries segments")
        if (self.mode == "center") != (self.box is not None):
            raise ValueError("box is required for 'center' and must be None for 'blur_fallback'")
        return self
```

In `src/clipforge/config.py`, after `fonts_dir`:

```python
    models_dir: Path = _REPO_ROOT / "assets" / "models"  # YuNet face model (ADR-19)

    # Reframe (ADR-19): ffmpeg scene score above which a frame starts a new shot
    scene_threshold: float = Field(0.2, gt=0.0, lt=1.0)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_models.py tests/test_config.py tests/stages/test_reframe.py`
Expected: PASS (the existing reframe tests still pass: their modes are unchanged).

- [ ] **Step 6: Full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 7: Checkpoint (the user commits)**

Files: `pyproject.toml`, `uv.lock`, `assets/models/face_detection_yunet_2023mar.onnx`, `assets/models/LICENSE`, `src/clipforge/models.py`, `src/clipforge/config.py`, `tests/test_models.py`, `tests/test_config.py`.

---

### Task 2: Shot detection (`stages/shots.py`) and the `two_shot` fixture

**Files:**
- Create: `src/clipforge/stages/shots.py`, `tests/stages/test_shots.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `clipforge.ffmpeg.FfmpegError(tool, stderr)`.
- Produces:
  - `MIN_SHOT_S = 0.5`;
  - `detect_cuts(video: Path, start: float, end: float, threshold: float) -> list[float]`, which returns clip-relative seconds, ascending, strictly inside `(0, end - start)`, and raises `FfmpegError`;
  - `segments_from_cuts(cuts: list[float], duration: float, min_len: float = MIN_SHOT_S) -> list[tuple[float, float]]`;
  - fixture `two_shot: Path`, a 1280x720 4 s mp4 with audio. From 0 to 2 s, the talking-head fixture scaled to 600 px tall is at x=40, y=60 over a dark gray background. From 2 to 4 s it's at x=900 over dark blue. The cut is at 2.0 s.

- [ ] **Step 1: Add the fixture to `tests/conftest.py`**

After the `talking_head` fixture:

```python
TWO_SHOT_FACE_X = (40, 900)  # left edge of the pasted person in each shot; 338 px wide


@pytest.fixture(scope="session")
def two_shot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """1280x720, 4 s: the real talking-head face at the left (0-2 s), then at the right
    (2-4 s) over a different background, so there's one camera cut at 2.0 s."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("two_shot") / "two_shot.mp4"
    left, right = TWO_SHOT_FACE_X
    graph = (
        "[0:v][1:v]concat=n=2:v=1:a=0[bg];"
        "[2:v]trim=0:4,setpts=PTS-STARTPTS,scale=-2:600[f];"
        f"[bg][f]overlay=x='if(lt(t,2),{left},{right})':y=60:shortest=1[v]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x404040:s=1280x720:r=30:d=2",
        "-f", "lavfi", "-i", "color=c=0x203060:s=1280x720:r=30:d=2",
        "-i", str(TALKING_HEAD),
        "-f", "lavfi", "-i", "sine=f=440:d=4",
        "-filter_complex", graph, "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-t", "4", str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)
    return path
```

- [ ] **Step 2: Write the failing tests**

`tests/stages/test_shots.py`:

```python
"""Camera cuts inside a clip (ADR-19)."""

from pathlib import Path

import pytest

from clipforge.ffmpeg import FfmpegError
from clipforge.stages.shots import detect_cuts, segments_from_cuts
from tests.conftest import requires_ffmpeg


@requires_ffmpeg
def test_detects_the_cut(two_shot: Path) -> None:
    cuts = detect_cuts(two_shot, 0.0, 4.0, threshold=0.2)
    assert len(cuts) == 1 and abs(cuts[0] - 2.0) < 0.05


@requires_ffmpeg
def test_cut_times_are_relative_to_the_clip_start(two_shot: Path) -> None:
    cuts = detect_cuts(two_shot, 1.0, 4.0, threshold=0.2)
    assert len(cuts) == 1 and abs(cuts[0] - 1.0) < 0.05


@requires_ffmpeg
def test_no_cut_inside_one_shot(two_shot: Path) -> None:
    assert detect_cuts(two_shot, 0.2, 1.8, threshold=0.2) == []


@requires_ffmpeg
def test_unreadable_video_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(FfmpegError):
        detect_cuts(bad, 0.0, 4.0, threshold=0.2)


def test_segments_cover_the_clip() -> None:
    assert segments_from_cuts([2.0, 4.0], 6.0) == [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]
    assert segments_from_cuts([], 6.0) == [(0.0, 6.0)]


def test_short_shots_merge_into_the_previous_one() -> None:
    assert segments_from_cuts([2.0, 2.3], 6.0) == [(0.0, 2.3), (2.3, 6.0)]
    assert segments_from_cuts([0.2], 6.0) == [(0.0, 6.0)]  # a short first shot merges forward
    assert segments_from_cuts([5.8], 6.0) == [(0.0, 6.0)]  # and a short last one backward
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_shots.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.stages.shots'`.

- [ ] **Step 4: Write `src/clipforge/stages/shots.py`**

```python
"""Camera cuts inside a clip (ADR-19), from ffmpeg's scene score. Modal-free.

Only the clip's own range is read, scaled to 320 px wide, without audio (rule 6)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from clipforge.ffmpeg import FfmpegError

MIN_SHOT_S = 0.5
DETECT_WIDTH = 320
_PTS = re.compile(r"pts_time:(-?[0-9.]+)")


def detect_cuts(video: Path, start: float, end: float, threshold: float) -> list[float]:
    """Clip-relative times (s) where a new shot starts, ascending, inside (0, end - start)."""
    duration = end - start
    vf = f"scale={DETECT_WIDTH}:-2,select='gt(scene,{threshold})',metadata=print"
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(video),
        "-an", "-vf", vf, "-f", "null", "-",
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if result.returncode != 0:
        raise FfmpegError("ffmpeg", result.stderr)
    times = sorted({round(float(t), 3) for t in _PTS.findall(result.stderr)})
    return [t for t in times if 0.0 < t < duration]


def segments_from_cuts(
    cuts: list[float], duration: float, min_len: float = MIN_SHOT_S
) -> list[tuple[float, float]]:
    """Contiguous (start, end) shots covering [0, duration]. A shot shorter than `min_len`
    joins the one before it (the first joins the one after), so a false cut can't flash."""
    bounds = [0.0, *[c for c in cuts if 0.0 < c < duration], duration]
    segments: list[tuple[float, float]] = []
    for a, b in zip(bounds, bounds[1:], strict=False):
        if segments and b - a < min_len:
            segments[-1] = (segments[-1][0], b)
        else:
            segments.append((a, b))
    if len(segments) > 1 and segments[0][1] - segments[0][0] < min_len:
        segments[:2] = [(segments[0][0], segments[1][1])]
    return segments
```

`FfmpegError`'s signature is `FfmpegError(tool: str, stderr: str)`, as used by `ffmpeg.run`. Check it in `src/clipforge/ffmpeg.py` before running.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_shots.py`
Expected: PASS (7).

If `test_cut_times_are_relative_to_the_clip_start` reports the cut at 2.0 instead of 1.0, then ffmpeg kept source timestamps. Subtract the first frame's `pts_time`, which the same `metadata=print` output gives when the select expression is `'eq(n,0)+gt(scene,T)'`, and record a ruling.

- [ ] **Step 6: Full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 7: Checkpoint**

Files: `src/clipforge/stages/shots.py`, `tests/stages/test_shots.py`, `tests/conftest.py`.

---

### Task 3: Face detection (`stages/faces.py`)

**Files:**
- Create: `src/clipforge/stages/faces.py`, `tests/stages/test_faces.py`
- Modify: `pyproject.toml` (a mypy override only if cv2 lacks usable stubs; see Step 5)

**Interfaces:**
- Consumes: `Settings.models_dir` (Task 1); the `two_shot` fixture (Task 2).
- Produces:
  - `YUNET_MODEL = "face_detection_yunet_2023mar.onnx"` and `SAMPLE_WIDTH = 640`;
  - `@dataclass(frozen=True) Face(cx: float, cy: float, w: float, h: float, score: float)`, with an `area` property;
  - `class FaceDetector(Protocol)`, with `name: str` and `detect(frame: npt.NDArray[np.uint8]) -> list[Face]`;
  - `YuNetDetector(model_path: Path, score_threshold: float = 0.6)`, which loads lazily on the first `detect`;
  - `sample_size(width: int, height: int) -> tuple[int, int]`;
  - `sample_frame(video: Path, t: float, size: tuple[int, int]) -> npt.NDArray[np.uint8] | None`, a BGR frame of shape `(h, w, 3)`, or None if it can't be decoded.

- [ ] **Step 1: Write the failing tests**

`tests/stages/test_faces.py`:

```python
"""YuNet face detection on real faces (the talking-head fixture pasted into two_shot)."""

from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.stages.faces import YUNET_MODEL, YuNetDetector, sample_frame, sample_size
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg
MODEL = Settings(_env_file=None).models_dir / YUNET_MODEL


def test_sample_size_keeps_the_aspect_and_even_height() -> None:
    assert sample_size(1280, 720) == (640, 360)
    assert sample_size(1921, 1081) == (640, 360)
    assert sample_size(640, 360) == (640, 360)


def test_sample_frame_decodes_bgr(two_shot: Path) -> None:
    frame = sample_frame(two_shot, 0.5, (640, 360))
    assert frame is not None and frame.shape == (360, 640, 3)


def test_sample_frame_of_a_bad_file_is_none(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nope")
    assert sample_frame(bad, 0.5, (640, 360)) is None


@pytest.mark.parametrize(("t", "lo", "hi"), [(0.5, 20, 200), (2.5, 450, 620)])
def test_yunet_finds_the_face(two_shot: Path, t: float, lo: float, hi: float) -> None:
    frame = sample_frame(two_shot, t, (640, 360))
    assert frame is not None
    faces = YuNetDetector(MODEL).detect(frame)
    assert len(faces) == 1
    assert lo < faces[0].cx < hi and faces[0].score >= 0.6  # left shot, then right shot


def test_yunet_finds_nothing_in_a_test_pattern(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    frame = sample_frame(media(width=1280, height=720, duration_s=2.0), 1.0, (640, 360))
    assert frame is not None
    assert YuNetDetector(MODEL).detect(frame) == []


def test_missing_model_fails_on_first_use_not_at_construction(two_shot: Path) -> None:
    detector = YuNetDetector(Path("/nonexistent/model.onnx"))  # must not raise here
    frame = sample_frame(two_shot, 0.5, (640, 360))
    assert frame is not None
    with pytest.raises(Exception):  # noqa: B017 (cv2.error or FileNotFoundError)
        detector.detect(frame)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_faces.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'clipforge.stages.faces'`.

- [ ] **Step 3: Write `src/clipforge/stages/faces.py`**

```python
"""Face detection for reframing (ADR-19): OpenCV's YuNet on a few small frames per shot.

cv2 is imported on first use, so importing this module is cheap and a broken OpenCV install
surfaces as a detection failure (reframe falls back to blur) instead of an import error."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

YUNET_MODEL = "face_detection_yunet_2023mar.onnx"
SAMPLE_WIDTH = 640


@dataclass(frozen=True)
class Face:
    cx: float  # center, in pixels of the frame given to detect()
    cy: float
    w: float
    h: float
    score: float

    @property
    def area(self) -> float:
        return self.w * self.h


class FaceDetector(Protocol):
    name: str  # part of the reframe cache key

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]: ...


class YuNetDetector:
    def __init__(self, model_path: Path, score_threshold: float = 0.6) -> None:
        self.model_path = model_path
        self.score_threshold = score_threshold
        self.name = f"yunet:{model_path.name}:{score_threshold:g}"
        self._net: Any = None

    def _load(self) -> Any:
        if self._net is None:
            import cv2

            if not self.model_path.is_file():
                raise FileNotFoundError(f"face model not found: {self.model_path}")
            self._net = cv2.FaceDetectorYN.create(
                str(self.model_path), "", (SAMPLE_WIDTH, 360), self.score_threshold
            )
        return self._net

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]:
        net = self._load()
        height, width = frame.shape[:2]
        net.setInputSize((width, height))
        _, found = net.detect(frame)
        if found is None:
            return []
        return [
            Face(
                cx=float(f[0] + f[2] / 2),
                cy=float(f[1] + f[3] / 2),
                w=float(f[2]),
                h=float(f[3]),
                score=float(f[14]),
            )
            for f in found
        ]


def sample_size(width: int, height: int) -> tuple[int, int]:
    """640 px wide, even height, same aspect as the (display-oriented) source."""
    h = round(SAMPLE_WIDTH * height / width)
    return SAMPLE_WIDTH, h - h % 2


def sample_frame(
    video: Path, t: float, size: tuple[int, int]
) -> npt.NDArray[np.uint8] | None:
    """One BGR frame at `t` seconds of the source, scaled to `size`; None if undecodable."""
    w, h = size
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(t, 0.0):.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]  # fmt: skip
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0 or len(result.stdout) != w * h * 3:
        return None
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(h, w, 3)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_faces.py`
Expected: PASS (7). The detected centers on 640-wide frames are about 115 (left) and 538 (right), because the prototype measured 227 and 1076 at 1280 px.

- [ ] **Step 5: Full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass. If mypy reports `import-untyped` or missing stubs for `cv2`, add `"cv2"` to the `ignore_missing_imports` override list in `pyproject.toml` and record a ruling. The code already treats the net as `Any`.

- [ ] **Step 6: Checkpoint**

Files: `src/clipforge/stages/faces.py`, `tests/stages/test_faces.py` (and `pyproject.toml` if changed).

---

### Task 4: `reframe.track` (cached, per-shot boxes, never fails a clip)

**Files:**
- Modify: `src/clipforge/stages/reframe.py`, `tests/stages/helpers.py`, `tests/stages/test_render.py` (imports only), `tests/stages/test_reframe.py`

**Interfaces:**
- Consumes:
  - Task 2: `shots.detect_cuts`, `shots.segments_from_cuts`;
  - Task 3: `faces.FaceDetector`, `faces.Face`, `faces.sample_size`, `faces.sample_frame`;
  - Task 1: `CropSegment`, `CropTrack(mode="tracked")`, `Settings.scene_threshold`;
  - `jobs.cached_stage`, `hashing.cache_key`.
- Produces:
  - `reframe.STAGE_VERSION = "2"`, `SAMPLE_POINTS = (0.25, 0.5, 0.75)`, `MIN_FACE_WIDTH = 0.04`;
  - `crop_box(cx: float, width: int, height: int) -> CropBox`;
  - `uses_tracking(spec: ClipSpec) -> bool`;
  - `track(ctx: JobContext, spec: ClipSpec, detector: FaceDetector, settings: Settings) -> CropTrack`, which merges neighbouring segments with the same mode and box, and records a `StageCost(stage=REFRAME, wall_s=…)`;
  - helpers `source_from(root, path) -> SourceMedia` and `spec_for(source, mode, start=1.0, end=4.0) -> ClipSpec` in `tests/stages/helpers.py`.

- [ ] **Step 1: Move the render test helpers**

Move `source_from` and `spec_for` from `tests/stages/test_render.py` into `tests/stages/helpers.py`, unchanged. Add the imports they need there: `media_info` from `clipforge.ffmpeg`, `ClipOptions`, `ClipSpec` and `SourceMedia` from `clipforge.models`, and `make_candidate` from `tests.test_models`. In `test_render.py`, import them from `tests.stages.helpers`.

Run: `uv run pytest -q tests/stages/test_render.py`. Expected: PASS, unchanged.

- [ ] **Step 2: Write the failing tests**

Append to `tests/stages/test_reframe.py`:

```python
# ---- per-shot face tracking (ADR-19)

import logging  # noqa: E402  (moved to the top when the file is formatted)
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import numpy.typing as npt  # noqa: E402

from clipforge.config import Settings  # noqa: E402
from clipforge.stages.faces import YUNET_MODEL, Face, YuNetDetector  # noqa: E402
from clipforge.stages.reframe import crop_box, track  # noqa: E402
from tests.conftest import TWO_SHOT_FACE_X, requires_ffmpeg  # noqa: E402
from tests.stages.helpers import make_ctx, source_from, spec_for  # noqa: E402

SETTINGS = Settings(_env_file=None)


@dataclass
class FakeDetector:
    faces: list[Face] = field(default_factory=list)
    fail: bool = False
    calls: int = 0
    name: str = "fake"

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("cv2 exploded")
        return list(self.faces)


def test_crop_box_is_clamped() -> None:
    assert crop_box(640, 1280, 720) == CropBox(x=438, y=0, w=404, h=720)
    assert crop_box(0, 1280, 720).x == 0
    right = crop_box(1280, 1280, 720)
    assert right.x + right.w <= 1280 and right.x == 876
    odd = crop_box(700, 1921, 1081)
    assert odd.w % 2 == 0 and odd.h % 2 == 0 and odd.x % 2 == 0


@requires_ffmpeg
def test_two_shots_each_framed_on_its_face(tmp_path: Path, two_shot: Path) -> None:
    spec = spec_for(source_from(tmp_path, two_shot), "auto", start=0.0, end=4.0)
    detector = YuNetDetector(SETTINGS.models_dir / YUNET_MODEL)
    result = track(make_ctx(tmp_path), spec, detector, SETTINGS)
    assert result.mode == "tracked" and len(result.segments) == 2
    assert abs(result.segments[0].end - 2.0) < 0.05 and result.segments[-1].end == 4.0
    for segment, left in zip(result.segments, TWO_SHOT_FACE_X, strict=True):
        assert segment.mode == "crop" and segment.box is not None
        box = segment.box
        assert box.x <= left and left + 338 <= box.x + box.w  # the whole person is in frame
        assert 0 <= box.x and box.x + box.w <= 1280


@requires_ffmpeg
def test_shot_without_faces_blurs(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), FakeDetector(), SETTINGS)
    assert [s.mode for s in result.segments] == ["blur"]


@requires_ffmpeg
def test_largest_face_wins(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    small = Face(cx=100, cy=100, w=40, h=50, score=0.9)
    big = Face(cx=500, cy=180, w=120, h=150, score=0.8)
    detector = FakeDetector(faces=[small, big])
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), detector, SETTINGS)
    box = result.segments[0].box
    assert box is not None and box.x <= 1000 <= box.x + box.w  # 500 px at 640 = 1000 at 1280


@requires_ffmpeg
def test_tiny_faces_are_ignored(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    poster = Face(cx=600, cy=40, w=20, h=24, score=0.95)  # 20/640 = 3% of the width
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), FakeDetector([poster]), SETTINGS)
    assert [s.mode for s in result.segments] == ["blur"]


@requires_ffmpeg
def test_detector_failure_blurs_the_whole_clip(
    tmp_path: Path, two_shot: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = spec_for(source_from(tmp_path, two_shot), "auto", start=0.0, end=4.0)
    with caplog.at_level(logging.WARNING):
        result = track(make_ctx(tmp_path), spec, FakeDetector(fail=True), SETTINGS)
    assert [(s.start, s.end, s.mode) for s in result.segments] == [(0.0, 4.0, "blur")]
    assert "face reframing failed" in caplog.text


@pytest.mark.parametrize(
    ("width", "height", "mode", "expected"),
    [
        (1080, 1920, "auto", "center"),  # already 9:16
        (1080, 1080, "auto", "blur_fallback"),  # near-square: blur-fit, as before
        (1920, 1080, "center", "center"),
        (1920, 1080, "blur", "blur_fallback"),
    ],
)
def test_track_delegates_to_plan_without_detecting(
    tmp_path: Path, width: int, height: int, mode: str, expected: str
) -> None:
    detector = FakeDetector()
    result = track(make_ctx(tmp_path), spec(width, height, mode), detector, SETTINGS)
    assert result.mode == expected and detector.calls == 0


@requires_ffmpeg
def test_track_is_cached_and_rebound(tmp_path: Path, two_shot: Path) -> None:
    source = source_from(tmp_path, two_shot)
    first = spec_for(source, "auto", start=0.0, end=4.0)
    detector = FakeDetector(faces=[Face(cx=300, cy=150, w=100, h=120, score=0.9)])
    track(make_ctx(tmp_path), first, detector, SETTINGS)
    calls = detector.calls
    again = first.model_copy(update={"clip_id": "clip_07", "rank": 7})
    result = track(make_ctx(tmp_path), again, detector, SETTINGS)
    assert detector.calls == calls and result.clip_id == "clip_07"
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_reframe.py`
Expected: FAIL, `ImportError: cannot import name 'crop_box' from 'clipforge.stages.reframe'`.

- [ ] **Step 4: Implement in `src/clipforge/stages/reframe.py`**

Replace the module docstring and `STAGE_VERSION`, and add below `plan`:

```python
"""Reframe to 9:16 (ADR-19). For landscape sources in `auto` mode, each camera shot is
cropped around its largest face, fixed for the shot. Shots without a reliable face, and any
detection failure, use the blurred-background fit. Already-vertical and near-square sources
and forced `center`/`blur` keep the fixed Phase 1 `plan`."""
```

```python
STAGE_VERSION = "2"
SAMPLE_POINTS = (0.25, 0.5, 0.75)  # where in each shot to look for faces
MIN_FACE_WIDTH = 0.04  # of the sample width: smaller faces (posters, far away) don't count
```

Add these imports at the top: `logging`, `statistics`, `time`, `Path`; `Settings` from `clipforge.config`; `cache_key`; `JobContext` and `cached_stage` from `clipforge.jobs`; `CropSegment`, `StageCost` and `StageName` from `clipforge.models`; and `from clipforge.stages import faces, shots`. Also add `log = logging.getLogger(__name__)`.

```python
def crop_box(cx: float, width: int, height: int) -> CropBox:
    """Full-height 9:16 box horizontally centered on `cx`, kept inside the frame."""
    crop_h = height - height % 2
    crop_w = min(width - width % 2, _even(crop_h * TARGET))
    x = _even(min(max(cx - crop_w / 2, 0.0), width - crop_w))
    return CropBox(x=x, y=(height - crop_h) // 2, w=crop_w, h=crop_h)


def uses_tracking(spec: ClipSpec) -> bool:
    aspect = spec.source.width / spec.source.height
    return (
        spec.options.reframe == "auto"
        and abs(aspect - TARGET) >= 0.01
        and aspect >= LANDSCAPE_MIN
    )


def track(
    ctx: JobContext, spec: ClipSpec, detector: faces.FaceDetector, settings: Settings
) -> CropTrack:
    if not uses_tracking(spec):
        return plan(spec)
    key = cache_key(
        "reframe",
        STAGE_VERSION,
        [],
        {
            "source_hash": spec.source.source_hash,
            "start": f"{spec.start:.3f}",
            "end": f"{spec.end:.3f}",
            "detector": detector.name,
            "scene": f"{settings.scene_threshold:g}",
        },
    )

    def compute(out_dir: Path) -> CropTrack:
        started = time.monotonic()
        ctx.report(StageName.REFRAME, 5, "finding faces")
        segments = _merge_same(_segments(ctx, spec, detector, settings))
        ctx.record_cost(StageCost(stage=StageName.REFRAME, wall_s=time.monotonic() - started))
        return CropTrack(clip_id=spec.clip_id, mode="tracked", box=None, segments=segments)

    stored = cached_stage(ctx, StageName.REFRAME, key, CropTrack, compute, clip_id=spec.clip_id)
    # The cache is keyed on the time range, never the clip id (ADR-8): rebind to this clip.
    return stored.value.model_copy(update={"clip_id": spec.clip_id})


def _segments(
    ctx: JobContext, spec: ClipSpec, detector: faces.FaceDetector, settings: Settings
) -> list[CropSegment]:
    duration = spec.duration_s
    try:
        video = ctx.path(spec.source.video_path)
        try:
            cuts = shots.detect_cuts(video, spec.start, spec.end, settings.scene_threshold)
        except Exception:
            log.warning("scene detection failed for %s; one shot", spec.clip_id, exc_info=True)
            cuts = []
        size = faces.sample_size(spec.source.width, spec.source.height)
        scale = spec.source.width / size[0]
        segments: list[CropSegment] = []
        for start, end in shots.segments_from_cuts(cuts, duration):
            centers = [
                cx * scale
                for p in SAMPLE_POINTS
                if (cx := _face_center(video, spec.start + start + (end - start) * p, size,
                                       detector)) is not None
            ]  # fmt: skip
            if centers:
                box = crop_box(statistics.median(centers), spec.source.width, spec.source.height)
                segments.append(CropSegment(start=start, end=end, mode="crop", box=box))
            else:
                segments.append(CropSegment(start=start, end=end, mode="blur"))
        return segments
    except Exception:
        log.warning("face reframing failed for %s; using the blurred fit", spec.clip_id,
                    exc_info=True)  # fmt: skip
        return [CropSegment(start=0.0, end=duration, mode="blur")]


def _merge_same(segments: list[CropSegment]) -> list[CropSegment]:
    """Join neighbours with the same framing (e.g. two blurred shots): fewer filter branches."""
    merged: list[CropSegment] = []
    for segment in segments:
        last = merged[-1] if merged else None
        if last is not None and (last.mode, last.box) == (segment.mode, segment.box):
            merged[-1] = last.model_copy(update={"end": segment.end})
        else:
            merged.append(segment)
    return merged


def _face_center(
    video: Path, t: float, size: tuple[int, int], detector: faces.FaceDetector
) -> float | None:
    """Center x (sample pixels) of the largest big-enough face at `t`, or None."""
    frame = faces.sample_frame(video, t, size)
    if frame is None:
        return None
    found = [f for f in detector.detect(frame) if f.w >= MIN_FACE_WIDTH * size[0]]
    if not found:
        return None
    return max(found, key=lambda f: f.area).cx
```

Rewrite the list comprehension in `_segments` as a plain loop if it reads better after `ruff format`; the behavior must stay the same.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_reframe.py`
Expected: PASS: the existing plan tests plus the 12 new cases.

- [ ] **Step 6: Full check**

Run: `uv run ruff check . && uv run ruff format . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass. Move the `# noqa: E402` imports in the test file to the top.

- [ ] **Step 7: Checkpoint**

Files: `src/clipforge/stages/reframe.py`, `tests/stages/helpers.py`, `tests/stages/test_render.py`, `tests/stages/test_reframe.py`.

---

### Task 5: Render the segments

**Files:**
- Modify: `src/clipforge/stages/render.py`, `tests/stages/test_render.py`

**Interfaces:**
- Consumes: `CropTrack(mode="tracked", segments=[...])` (Task 1).
- Produces:
  - `render.STAGE_VERSION = "2"`;
  - `filter_graph(track, ass, fonts_dir)` handles `tracked`;
  - the render cache key includes the segments.

- [ ] **Step 1: Write the failing tests**

Append to `tests/stages/test_render.py`:

```python
def _tracked(segments: list[tuple[float, float, CropBox | None]]) -> CropTrack:
    return CropTrack(
        clip_id="clip_01",
        mode="tracked",
        box=None,
        segments=[
            CropSegment(start=a, end=b, mode="crop" if box else "blur", box=box)
            for a, b, box in segments
        ],
    )


LEFT = CropBox(x=0, y=0, w=202, h=360)
RIGHT = CropBox(x=438, y=0, w=202, h=360)


def render_tracked(root: Path, spec: ClipSpec, track: CropTrack) -> Path:
    ctx = make_ctx(root)
    caps = captions.run(ctx, spec, transcript(WORDS)).value
    stored = render.run(ctx, spec, track, caps, Settings(_env_file=None, jobs_root=root))
    return ctx.path(stored.value.video_path)


def test_render_tracked_segments(tmp_path: Path, media: MediaFactory) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "auto")
    track = _tracked([(0.0, 1.0, LEFT), (1.0, 2.0, None), (2.0, 3.0, RIGHT)])
    out = render_tracked(tmp_path, spec, track)
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


def test_render_many_segments(tmp_path: Path, media: MediaFactory) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "auto")
    cuts = [i * 0.25 for i in range(13)]  # 12 shots of 0.25 s
    boxes = [LEFT, RIGHT, None]
    track = _tracked([(a, b, boxes[i % 3]) for i, (a, b) in enumerate(zip(cuts, cuts[1:]))])
    out = render_tracked(tmp_path, spec, track)
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


def test_tracked_filter_graph_shape() -> None:
    graph = render.filter_graph(
        _tracked([(0.0, 1.5, LEFT), (1.5, 3.0, None)]), Path("/c.ass"), Path("/fonts")
    )
    assert graph.startswith("[0:v]split=2[s0][s1];")
    assert "[s0]trim=start=0.000:end=1.500,setpts=PTS-STARTPTS,crop=202:360:0:0," in graph
    assert "[s1]trim=start=1.500,setpts=PTS-STARTPTS" in graph  # the last shot runs to the end
    assert "boxblur" in graph and "[p0][p1]concat=n=2:v=1:a=0,ass=" in graph
    assert graph.endswith("[v]")


def test_render_key_includes_the_segments(
    tmp_path: Path, media: MediaFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "auto")
    first = render_tracked(tmp_path, spec, _tracked([(0.0, 3.0, LEFT)]))
    second = render_tracked(tmp_path, spec, _tracked([(0.0, 3.0, RIGHT)]))
    assert first != second
```

Add `CropBox`, `CropSegment` and `CropTrack` to the `clipforge.models` import.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_render.py`
Expected: the 4 new tests FAIL. `filter_graph` raises for `tracked`, because it falls into the blur branch and the shape test's asserts fail. The render tests error on the segments.

- [ ] **Step 3: Implement in `src/clipforge/stages/render.py`**

Set `STAGE_VERSION = "2"`. Replace `filter_graph`:

```python
def _crop(box: CropBox, w: int, h: int) -> str:
    return f"crop={box.w}:{box.h}:{box.x}:{box.y},scale={w}:{h}:flags=lanczos,setsar=1"


def _blur(src: str, dst: str, w: int, h: int, tag: str) -> str:
    """Fit `src` inside a blurred, zoomed copy of itself (blurred small: much cheaper)."""
    bw, bh = w // 4, h // 4
    return (
        f"[{src}]split=2[{tag}bg][{tag}fg];"
        f"[{tag}bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"boxblur=10:1,scale={w}:{h}[{tag}bgb];"
        f"[{tag}fg]scale={w}:{h}:force_original_aspect_ratio=decrease[{tag}fgs];"
        f"[{tag}bgb][{tag}fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[{dst}]"
    )


def filter_graph(track: CropTrack, ass: Path, fonts_dir: Path) -> str:
    subs = f"ass=filename={filter_path(ass)}:fontsdir={filter_path(fonts_dir)}"
    w, h = track.out_width, track.out_height
    if track.mode == "center":
        if track.box is None:
            raise ValueError("center crop without a box")
        return f"[0:v]{_crop(track.box, w, h)},{subs}[v]"
    if track.mode == "blur_fallback":
        return _blur("0:v", "fit", w, h, "b") + f";[fit]{subs}[v]"
    n = len(track.segments)
    parts = ["[0:v]split=" + str(n) + "".join(f"[s{i}]" for i in range(n))]
    for i, segment in enumerate(track.segments):
        end = f":end={segment.end:.3f}" if i < n - 1 else ""
        trim = f"trim=start={segment.start:.3f}{end},setpts=PTS-STARTPTS"
        if segment.box is not None:
            parts.append(f"[s{i}]{trim},{_crop(segment.box, w, h)}[p{i}]")
        else:
            parts.append(f"[s{i}]{trim}[t{i}];" + _blur(f"t{i}", f"p{i}", w, h, f"b{i}"))
    concat = "".join(f"[p{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,{subs}[v]"
    return ";".join([*parts, concat])
```

Import `CropBox` from `clipforge.models`. In `run`, add the segments to the key dict:

```python
            "segments": json.dumps(
                [s.model_dump(mode="json") for s in track.segments], sort_keys=True
            ),
```

`center` and `blur_fallback` produce the same pixels as before. The blur graph's labels change, but the filters are the same, so the existing render tests keep passing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_render.py`
Expected: PASS: all the existing tests plus the 4 new ones.

If the A/V check in `test_render_many_segments` fails by a frame or two, `trim` is dropping frames at float boundaries. Snap each boundary to the frame grid (`round(t * fps) / fps`, with fps from `spec.source.fps`) in `filter_graph`, and record a ruling.

- [ ] **Step 5: Full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 6: Checkpoint**

Files: `src/clipforge/stages/render.py`, `tests/stages/test_render.py`.

---

### Task 6: Wire it in, ship it, check the podcast

**Files:**
- Modify: `src/clipforge/stages/runner.py`, `src/clipforge/app.py`, `tests/stages/test_pipeline_e2e.py`, `tests/test_app.py`
- Modify: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `ROADMAP.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `reframe.track`, `faces.YuNetDetector`, `faces.YUNET_MODEL`, `Settings.models_dir`.
- Produces:
  - `PipelineStages.detector: FaceDetector`;
  - `app.MODELS_MOUNT = "/app/assets/models"` and `CONTAINER_ENV["MODELS_DIR"]`.

- [ ] **Step 1: Write the failing tests**

In `tests/stages/test_pipeline_e2e.py`:
- Build `PipelineStages(..., detector=YuNetDetector(settings.models_dir / YUNET_MODEL))`.
- After the existing assertions, add:

```python
    tracks = [c for c in meta.cost.stages if c.stage is StageName.REFRAME]
    assert tracks, "reframe ran as a cached stage for the landscape source"
```

`cached_stage` records a reframe cost entry. The synthetic source is 640x360 `testsrc2` with no faces, so the clips come out blurred and still pass `assert_vertical_clip`.

Append to `tests/test_app.py`:

```python
def test_face_model_is_mounted() -> None:
    assert app.CONTAINER_ENV["MODELS_DIR"] == app.MODELS_MOUNT
    assert (app.REPO_ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx").is_file()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_pipeline_e2e.py tests/test_app.py`
Expected: FAIL. `TypeError: ... unexpected keyword argument 'detector'` in e2e; `AttributeError: ... MODELS_MOUNT` in test_app.

- [ ] **Step 3: Implement**

In `src/clipforge/stages/runner.py`:
- Add `detector: faces.FaceDetector` to the dataclass fields.
- In `from_settings`, add the argument `detector: faces.FaceDetector | None = None` and pass `detector=detector or faces.YuNetDetector(settings.models_dir / faces.YUNET_MODEL)`.
- In `clip()`, replace `track = reframe.plan(spec)` with:

```python
        ctx.report(StageName.REFRAME, 0, "framing")
        track = reframe.track(ctx, spec, self.detector, self.settings)
```

Add `faces` to the `clipforge.stages` import.

In `src/clipforge/app.py`:
- Add `MODELS_MOUNT = "/app/assets/models"` next to `FONTS_MOUNT`, and `"MODELS_DIR": MODELS_MOUNT` to `CONTAINER_ENV`.
- In `_with_app_files`, add `.add_local_dir(REPO_ROOT / "assets" / "models", MODELS_MOUNT)`.

- [ ] **Step 4: Run the tests to verify they pass, then run the full check**

Run: `uv run pytest -q tests/stages/test_pipeline_e2e.py tests/test_app.py && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass, all clean.

- [ ] **Step 5: Docs**

- `docs/ARCHITECTURE.md`:
  - The reframe row of the stage table becomes: `reframe | clip_step | ClipSpec | CropTrack (per-shot crop boxes around the largest face, or blur segments) | CPU`.
  - Replace the "Reframe (simple)" bullet in "Phase 1 stage details" with: "**Reframe (ADR-19):** landscape sources in `auto` are cut at camera changes (ffmpeg scene score > 0.2, shots < 0.5 s merged). Each shot is cropped to 9:16 around its largest face: YuNet, the median of 3 samples, and faces ≥ 4% of the frame width. The crop is fixed per shot. Shots without a face, and any detection failure, use the blurred fit. Already-9:16 and near-square sources, and forced `center`/`blur`, keep the fixed crop or fit."
  - Replace the "Reframing (Phase 3)" section's first sentence with the remaining Phase 3 work: smoothed in-shot tracking and active-speaker choice.
- `docs/DECISIONS.md`: ADR-19 `Status: Proposed` becomes `Status: Accepted`.
- `ROADMAP.md`, Phase 3:
  - tick `Scene detection (PySceneDetect)` and change its text to `Scene detection (ffmpeg scene score, ADR-19)`;
  - replace `Face tracking with smoothed crop (MediaPipe + EMA/Kalman)` with two lines: `- [x] Face-centered crop per shot (YuNet, ADR-19)` and `- [ ] Smoothed in-shot tracking (EMA/Kalman) for people who move a lot`.
- `CLAUDE.md`, Layout: add `shots.py faces.py` to the `stages/` line, and add `assets/models/  # YuNet face model (MIT)`.

- [ ] **Step 6: Checkpoint**

Files: `src/clipforge/stages/runner.py`, `src/clipforge/app.py`, `tests/stages/test_pipeline_e2e.py`, `tests/test_app.py`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `ROADMAP.md`, `CLAUDE.md`.

- [ ] **Step 7: Deploy and re-cut the podcast (the owner approved testing this way)**

```bash
uv run modal deploy src/clipforge/app.py
uv run clipforge clip "videos/billy_carton-Koa_smith.mp4" --again
```

Expected: `done · 30 of 30 clips`, with transcript and highlights from cache. The new clips land in `videos/out/billy_carton-Koa_smith-3/`.

- [ ] **Step 8: Contact sheet for the owner**

Build one image: 6 clips × 3 frames, at 20%, 50% and 80% of each clip, taken from `-2/` (before) and `-3/` (after), side by side:

```bash
S=videos/out/previews && mkdir -p $S
for dir in "billy_carton-Koa_smith-2" "billy_carton-Koa_smith-3"; do
  i=0
  for clip in $(ls -d "videos/out/$dir"/clip_* | head -6); do
    d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$clip/video.mp4")
    for p in 0.2 0.5 0.8; do
      ffmpeg -v error -y -ss "$(echo "$d * $p" | bc -l)" -i "$clip/video.mp4" -frames:v 1 \
        -vf scale=180:320 "$S/${dir##*-}_${i}_${p}.png"
    done
    i=$((i+1))
  done
done
ffmpeg -v error -y -pattern_type glob -i "$S/2_*.png" -vf tile=9x2 "$S/before.png"
ffmpeg -v error -y -pattern_type glob -i "$S/3_*.png" -vf tile=9x2 "$S/after.png"
ffmpeg -v error -y -i "$S/before.png" -i "$S/after.png" -filter_complex vstack \
  "$S/reframe_before_after.png"
rm -f "$S"/2_*.png "$S"/3_*.png
```

Open `videos/out/previews/reframe_before_after.png` with the Read tool and check:
- the person is inside the frame in every "after" tile;
- tiles within one clip only change framing where the camera cut.

Report what you see to the owner, including any shot that blurred.

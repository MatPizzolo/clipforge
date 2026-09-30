# Speaker-Aware Framing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In shots with two or more people, frame whoever is talking and hard-cut to the other person when the turn changes.

**Architecture:** A new Modal-free module, `stages/speakers.py`:
- groups the faces from reframe's 3 samples into seats;
- measures each seat's mouth motion (minus head motion) from one 10 fps grayscale ffmpeg stream of the shot;
- gives each transcript word to the seat that moved most;
- groups the words into turns of at least 2 s, switching mid-pause.

`reframe._segments` turns those turns into several `crop` segments of the existing `CropTrack`, so render is unchanged. The runner passes the clip's words to `reframe.track`.

**Tech Stack:** Python 3.12, numpy, ffmpeg (rawvideo gray pipe), OpenCV YuNet (existing), pytest.

**Spec:** docs/superpowers/specs/2026-09-28-speaker-framing-design.md

## Global Constraints

- Stage modules never import Modal (CLAUDE.md rule 1). Per-clip work only, on the clip's time range (rule 6).
- No new dependencies, no API calls, no new tokens. CPU only, in `clip_step`.
- A failure never fails a clip. The fallback is today's framing (largest face per shot), and a fallback caused by a failure is never cached (`_Degraded`).
- Output contract unchanged: `CropTrack(mode="tracked", segments=[...])`, contiguous from 0 to the clip duration. `render.py` and `models.py` are untouched.
- Constants from the spec:
  - `MOTION_FPS = 10`, `MIN_TURN_S = 2.0`, `WIN_RATIO = 1.2`, `MIN_SEEN = 2`, `GROUP_PAD = 0.10`, `MIN_PATCH = 4`;
  - mouth patch: x from the left corner − 0.15·w to the right corner + 0.15·w, y from mouth y − 0.10·h to mouth y + 0.15·h;
  - eye band: the face box's top 45%.
- `reframe.STAGE_VERSION = "4"`.
- The user runs git. The "commit" steps are file-list checkpoints written to the ledger, never `git` commands.

## Review Focus

1. **Words overlapping a shot cut** (a word from 1.9 to 2.1 s with a cut at 2.0 s). Each shot must see the word clamped to its range, and the turn segments must still cover the shot exactly. Test: `test_turns_clamp_words_to_the_shot` (Task 3).
2. **The same seat on both sides of a merge.** A short run between two runs of seat A must leave one A turn, not two adjacent A segments. Test: `test_short_interruption_leaves_one_turn` (Task 3).
3. **Zero-length words** (whisper can give start == end). Such a word must still collect the frames around it instead of always being unknown. Test: `test_zero_length_word_uses_nearby_frames` (Task 2).
4. **Fake detectors without mouth landmarks** (the existing tests and any detector returning boxes only). The mouth patch must be estimated from the box, and nothing may crash. Test: `test_mouth_patch_estimated_without_landmarks` (Task 1).
5. **A two-seat shot with no words** (music, silence). It must frame the largest face, and the result must be cached, not degraded. Test: `test_two_seats_without_words_use_largest_face_and_cache` (Task 4).

---

### Task 1: Mouth landmarks and seats

**Files:**
- Modify: `src/clipforge/stages/faces.py` (the `Face` dataclass, `YuNetDetector.detect`)
- Create: `src/clipforge/stages/speakers.py`
- Test: `tests/stages/test_faces.py`, `tests/stages/test_speakers.py` (new)

**Interfaces:**
- Produces:
  - `Face(cx, cy, w, h, score, mouth_left: tuple[float, float] | None = None, mouth_right: tuple[float, float] | None = None)`;
  - `speakers.Seat(face: Face)` with the `cx` property;
  - `speakers.seats(samples: list[list[Face]], min_seen: int = MIN_SEEN) -> list[Seat]` (sorted by `cx`);
  - `speakers.fits_one_crop(seats: list[Seat], crop_w: float) -> bool`;
  - `speakers.group_center(seats: list[Seat]) -> float`;
  - `speakers.mouth_patch(face: Face) -> tuple[int, int, int, int]` and `speakers.eye_band(face: Face) -> tuple[int, int, int, int]`, both `(x0, y0, x1, y1)`, unclipped.
  - All values are in sample pixels.

- [ ] **Step 1: Write the failing tests**

Append to `tests/stages/test_faces.py`:

```python
def test_yunet_returns_mouth_corners_inside_the_face(two_shot: Path) -> None:
    frame = sample_frame(two_shot, 0.5, (640, 360))
    assert frame is not None
    (face,) = YuNetDetector(MODEL).detect(frame)
    assert face.mouth_left is not None and face.mouth_right is not None
    for x, y in (face.mouth_left, face.mouth_right):
        assert face.cx - face.w / 2 <= x <= face.cx + face.w / 2
        assert face.cy <= y <= face.cy + face.h / 2  # below the center, inside the box
```

Create `tests/stages/test_speakers.py`:

```python
"""Speaker-aware framing helpers (ADR-21)."""

from __future__ import annotations

import pytest

from clipforge.stages.faces import Face
from clipforge.stages.speakers import (
    Seat,
    eye_band,
    fits_one_crop,
    group_center,
    mouth_patch,
    seats,
)


def face(cx: float, w: float = 60, cy: float = 150, h: float = 80) -> Face:
    return Face(cx=cx, cy=cy, w=w, h=h, score=0.9)


def test_seats_group_by_position_and_sort_left_to_right() -> None:
    samples = [[face(480), face(150)], [face(152), face(478)], [face(149), face(481)]]
    found = seats(samples)
    assert [round(s.cx) for s in found] == [150, 480]


def test_a_face_seen_once_is_not_a_seat() -> None:
    samples = [[face(150), face(480)], [face(150)], [face(151)]]
    assert [round(s.cx) for s in seats(samples)] == [150]


def test_two_faces_in_one_sample_are_two_seats_even_if_close() -> None:
    samples = [[face(150, w=60), face(215, w=60)]] * 3  # 65 px apart, wider than 60
    assert len(seats(samples)) == 2


def test_seat_is_the_median_detection() -> None:
    samples = [[face(100)], [face(110)], [face(200 - 70)]]  # 100, 110, 130
    (seat,) = seats(samples)
    assert seat.cx == 110


def test_fits_one_crop() -> None:
    close = [Seat(face(150)), Seat(face(230))]  # span 120..260 = 140, padded 154
    far = [Seat(face(150)), Seat(face(480))]  # span 120..510 = 390
    assert fits_one_crop(close, crop_w=202)
    assert not fits_one_crop(far, crop_w=202)
    assert group_center(close) == 190


def test_mouth_patch_uses_the_landmarks() -> None:
    f = Face(cx=100, cy=100, w=60, h=80, score=0.9, mouth_left=(90, 120), mouth_right=(110, 122))
    assert mouth_patch(f) == (81, 113, 119, 133)  # 90-9, 121-8, 110+9, 121+12


def test_mouth_patch_estimated_without_landmarks() -> None:
    f = face(100, w=60, cy=100, h=80)  # corners estimated at (88, 120) and (112, 120)
    assert mouth_patch(f) == (79, 112, 121, 132)


def test_eye_band_is_the_top_45_percent() -> None:
    assert eye_band(face(100, w=60, cy=100, h=80)) == (70, 60, 130, 96)


@pytest.mark.parametrize("samples", [[], [[], [], []]])
def test_no_faces_no_seats(samples: list[list[Face]]) -> None:
    assert seats(samples) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/stages/test_speakers.py tests/stages/test_faces.py`
Expected: FAIL. `test_speakers.py` fails with `ModuleNotFoundError: clipforge.stages.speakers`. `test_yunet_returns_mouth_corners_inside_the_face` fails with `AttributeError: 'Face' object has no attribute 'mouth_left'`.

- [ ] **Step 3: Implement**

In `src/clipforge/stages/faces.py`, extend `Face` (new fields last, with defaults, so the existing `Face(cx=…, …, score=…)` calls keep working):

```python
@dataclass(frozen=True)
class Face:
    cx: float  # center, in pixels of the frame given to detect()
    cy: float
    w: float
    h: float
    score: float
    mouth_left: tuple[float, float] | None = None  # YuNet landmarks; None from box-only detectors
    mouth_right: tuple[float, float] | None = None

    @property
    def area(self) -> float:
        return self.w * self.h
```

And in `YuNetDetector.detect`, fill them in. YuNet rows are `x, y, w, h`, then 5 landmarks (right eye, left eye, nose, right mouth corner, left mouth corner), then the score:

```python
        return [
            Face(
                cx=float(f[0] + f[2] / 2),
                cy=float(f[1] + f[3] / 2),
                w=float(f[2]),
                h=float(f[3]),
                score=float(f[14]),
                mouth_left=_mouth(f)[0],
                mouth_right=_mouth(f)[1],
            )
            for f in found
        ]


def _mouth(row: Any) -> tuple[tuple[float, float], tuple[float, float]]:
    """YuNet's two mouth corners (columns 10-13), ordered left to right in the image."""
    a = (float(row[10]), float(row[11]))
    b = (float(row[12]), float(row[13]))
    return (a, b) if a[0] <= b[0] else (b, a)
```

Create `src/clipforge/stages/speakers.py`:

```python
"""Who is talking in a shot with several people (ADR-21): seats from reframe's face samples,
mouth motion minus head motion per seat, words given to the seat that moved most, and turns
of at least 2 s that switch in the middle of a pause.

All positions are in sample pixels (faces.sample_size); times are in seconds."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from clipforge.stages.faces import Face

MOTION_FPS = 10
MIN_TURN_S = 2.0
WIN_RATIO = 1.2  # the winning seat must move 1.2x as much as the runner-up
MIN_SEEN = 2  # a seat must appear in at least 2 of the 3 samples
GROUP_PAD = 0.10  # padding around a group that must fit in one crop
MIN_PATCH = 4  # patches under 4x4 px score 0


@dataclass(frozen=True)
class Seat:
    face: Face  # the median detection

    @property
    def cx(self) -> float:
        return self.face.cx


def seats(samples: list[list[Face]], min_seen: int = MIN_SEEN) -> list[Seat]:
    """Faces from different samples are one seat when their centers are closer than the wider
    face's width. Faces within one sample are always different seats."""
    groups: list[list[tuple[int, Face]]] = []
    for index, found in enumerate(samples):
        for f in found:
            for group in groups:
                ref = group[0][1]
                taken = any(i == index for i, _ in group)
                if not taken and abs(f.cx - ref.cx) < max(f.w, ref.w):
                    group.append((index, f))
                    break
            else:
                groups.append([(index, f)])
    kept = [[f for _, f in g] for g in groups if len({i for i, _ in g}) >= min_seen]
    return sorted((Seat(_median_face(g)) for g in kept), key=lambda s: s.cx)


def _median_face(found: list[Face]) -> Face:
    def med(values: list[float]) -> float:
        return float(statistics.median(values))

    def point(points: list[tuple[float, float] | None]) -> tuple[float, float] | None:
        if any(p is None for p in points):
            return None
        return med([p[0] for p in points if p]), med([p[1] for p in points if p])

    return Face(
        cx=med([f.cx for f in found]),
        cy=med([f.cy for f in found]),
        w=med([f.w for f in found]),
        h=med([f.h for f in found]),
        score=med([f.score for f in found]),
        mouth_left=point([f.mouth_left for f in found]),
        mouth_right=point([f.mouth_right for f in found]),
    )


def _span(seat_list: list[Seat]) -> tuple[float, float]:
    left = min(s.face.cx - s.face.w / 2 for s in seat_list)
    right = max(s.face.cx + s.face.w / 2 for s in seat_list)
    return left, right


def fits_one_crop(seat_list: list[Seat], crop_w: float) -> bool:
    left, right = _span(seat_list)
    return (right - left) * (1 + GROUP_PAD) <= crop_w


def group_center(seat_list: list[Seat]) -> float:
    left, right = _span(seat_list)
    return (left + right) / 2


def mouth_patch(face: Face) -> tuple[int, int, int, int]:
    """Around the mouth corners (estimated from the box when the detector gave none)."""
    left = face.mouth_left or (face.cx - 0.2 * face.w, face.cy + 0.25 * face.h)
    right = face.mouth_right or (face.cx + 0.2 * face.w, face.cy + 0.25 * face.h)
    mouth_y = (left[1] + right[1]) / 2
    return (
        round(min(left[0], right[0]) - 0.15 * face.w),
        round(mouth_y - 0.10 * face.h),
        round(max(left[0], right[0]) + 0.15 * face.w),
        round(mouth_y + 0.15 * face.h),
    )


def eye_band(face: Face) -> tuple[int, int, int, int]:
    """The top 45% of the face box: moves with the head, not with speech."""
    top = face.cy - face.h / 2
    return (
        round(face.cx - face.w / 2),
        round(top),
        round(face.cx + face.w / 2),
        round(top + 0.45 * face.h),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_speakers.py tests/stages/test_faces.py tests/stages/test_reframe.py`
Expected: PASS. The reframe tests are unchanged, so the defaulted `Face` fields break nothing.

- [ ] **Step 5: Checkpoint.** Ledger file list: `src/clipforge/stages/faces.py`, `src/clipforge/stages/speakers.py`, `tests/stages/test_faces.py`, `tests/stages/test_speakers.py`.

---

### Task 2: Mouth motion and words to seats

**Files:**
- Modify: `src/clipforge/stages/speakers.py`
- Test: `tests/stages/test_speakers.py`

**Interfaces:**
- Consumes: `Seat`, `mouth_patch`, `eye_band`, `MOTION_FPS`, `WIN_RATIO`, `MIN_PATCH` (Task 1); `models.Word`.
- Produces:
  - `speakers.Motion(times: npt.NDArray[np.float64], scores: npt.NDArray[np.float64])`, where `scores` has shape `(len(times), n_seats)`, and `Motion.shifted(dt: float) -> Motion`;
  - `speakers.mouth_motion(video: Path, start: float, end: float, seat_list: list[Seat], size: tuple[int, int], fps: int = MOTION_FPS) -> Motion`. `start` and `end` are source seconds. `times` are relative to `start` (the midpoint of each consecutive frame pair). It raises `RuntimeError` when ffmpeg fails or gives fewer than 2 frames.
  - `speakers.assign_words(words: list[Word], motion: Motion) -> list[int | None]`: each word's seat index, or None for unknown.

- [ ] **Step 1: Write the failing tests**

Add these imports to the top of `tests/stages/test_speakers.py` (merge them into the existing import block; ruff's E402 forbids imports mid-file):

```python
import subprocess
from pathlib import Path

import numpy as np

from clipforge.models import Word
from clipforge.stages.speakers import MOTION_FPS, Motion, assign_words, mouth_motion
from tests.conftest import requires_ffmpeg
```

Then append:

```python
LEFT, RIGHT = face(160, w=80, cy=150, h=100), face(480, w=80, cy=150, h=100)


def talking_pair(path: Path) -> Path:
    """640x360, 4 s, gray: noise flickers in LEFT's mouth patch for 0-2 s and in RIGHT's for
    2-4 s. Nothing moves in either eye band."""
    (lx0, ly0, lx1, ly1), (rx0, ry0, rx1, ry1) = mouth_patch(LEFT), mouth_patch(RIGHT)
    noise = "color=c=gray:s=640x360:r=25:d=4,noise=alls=100:allf=t"
    graph = (
        f"[1:v]crop={lx1 - lx0}:{ly1 - ly0}:0:0[n1];[2:v]crop={rx1 - rx0}:{ry1 - ry0}:0:0[n2];"
        f"[0:v][n1]overlay=x={lx0}:y={ly0}:enable='lt(t,2)'[a];"
        f"[a][n2]overlay=x={rx0}:y={ry0}:enable='gte(t,2)'[v]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x606060:s=640x360:r=25:d=4",
        "-f", "lavfi", "-i", noise, "-f", "lavfi", "-i", noise,
        "-filter_complex", graph, "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p",
        str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@requires_ffmpeg
def test_mouth_motion_follows_the_talking_seat(tmp_path: Path) -> None:
    video = talking_pair(tmp_path / "pair.mp4")
    motion = mouth_motion(video, 0.0, 4.0, [Seat(LEFT), Seat(RIGHT)], (640, 360))
    assert motion.scores.shape == (len(motion.times), 2)
    assert 35 <= len(motion.times) <= 40  # 10 fps over 4 s, minus one per pair
    first = motion.times < 1.9
    second = motion.times > 2.1
    assert motion.scores[first, 0].mean() > 3 * motion.scores[first, 1].mean()
    assert motion.scores[second, 1].mean() > 3 * motion.scores[second, 0].mean()


@requires_ffmpeg
def test_mouth_motion_times_are_relative_to_start(tmp_path: Path) -> None:
    video = talking_pair(tmp_path / "pair.mp4")
    motion = mouth_motion(video, 1.0, 3.0, [Seat(LEFT), Seat(RIGHT)], (640, 360))
    assert motion.times[0] == pytest.approx(0.5 / MOTION_FPS)
    assert motion.times[-1] < 2.0


@requires_ffmpeg
def test_mouth_motion_of_a_bad_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nope")
    with pytest.raises(RuntimeError):
        mouth_motion(bad, 0.0, 2.0, [Seat(LEFT)], (640, 360))


@requires_ffmpeg
def test_patch_off_the_frame_scores_zero(tmp_path: Path) -> None:
    video = talking_pair(tmp_path / "pair.mp4")
    off = Seat(face(-200, w=80))  # entirely left of the frame
    motion = mouth_motion(video, 0.0, 2.0, [off, Seat(LEFT)], (640, 360))
    assert (motion.scores[:, 0] == 0).all() and motion.scores[:, 1].mean() > 0


def motion(rows: list[tuple[float, float, float]]) -> Motion:
    """(time, left score, right score) rows."""
    arr = np.array(rows, dtype=np.float64)
    return Motion(times=arr[:, 0], scores=arr[:, 1:])


def word(start: float, end: float) -> Word:
    return Word(text="w", start=start, end=end)


def test_assign_words_picks_the_seat_that_moved_most() -> None:
    m = motion([(0.05, 5, 1), (0.15, 6, 1), (0.25, 1, 7), (0.35, 1, 8)])
    assert assign_words([word(0.0, 0.2), word(0.2, 0.4)], m) == [0, 1]


def test_near_tie_is_unknown() -> None:
    m = motion([(0.05, 5.0, 4.5), (0.15, 5.0, 4.5)])  # 5 < 1.2 * 4.5
    assert assign_words([word(0.0, 0.2)], m) == [None]


def test_no_motion_is_unknown() -> None:
    assert assign_words([word(0.0, 0.2)], motion([(0.05, 0, 0), (0.15, 0, 0)])) == [None]


def test_word_without_frames_is_unknown() -> None:
    assert assign_words([word(5.0, 5.2)], motion([(0.05, 5, 1)])) == [None]


def test_zero_length_word_uses_nearby_frames() -> None:
    m = motion([(0.97, 1, 9), (1.03, 1, 9)])
    assert assign_words([word(1.0, 1.0)], m) == [1]


def test_motion_shifted() -> None:
    m = motion([(0.05, 1, 2)]).shifted(2.0)
    assert m.times.tolist() == [2.05] and m.scores.tolist() == [[1, 2]]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/stages/test_speakers.py`
Expected: FAIL with `ImportError: cannot import name 'MOTION_FPS'`… or `'Motion'` from `clipforge.stages.speakers`. The Task 1 names exist, the new ones don't.

- [ ] **Step 3: Implement**

Add to `src/clipforge/stages/speakers.py`, with the new imports at the top (`subprocess`, `from pathlib import Path`, `numpy as np`, `numpy.typing as npt`, `from clipforge.models import Word`):

```python
WORD_SLACK_S = 0.5 / MOTION_FPS  # a word also counts the frames just around it


@dataclass(frozen=True)
class Motion:
    times: npt.NDArray[np.float64]  # seconds, one per consecutive frame pair
    scores: npt.NDArray[np.float64]  # (len(times), n_seats): mouth motion minus head motion

    def shifted(self, dt: float) -> Motion:
        return Motion(times=self.times + dt, scores=self.scores)


def mouth_motion(
    video: Path,
    start: float,
    end: float,
    seat_list: list[Seat],
    size: tuple[int, int],
    fps: int = MOTION_FPS,
) -> Motion:
    """One ffmpeg decode of [start, end) at `fps` as small grayscale frames; per seat, the mean
    frame-to-frame change in its mouth patch minus that of its eye band, floored at 0."""
    w, h = size
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(start, 0.0):.3f}",
        "-t", f"{max(end - start, 0.0):.3f}", "-i", str(video),
        "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, timeout=300, check=False)
    n = len(result.stdout) // (w * h)
    if result.returncode != 0 or n < 2:
        raise RuntimeError(f"mouth motion: ffmpeg gave {n} frames (exit {result.returncode})")
    frames = np.frombuffer(result.stdout[: n * w * h], dtype=np.uint8).reshape(n, h, w)
    times = (np.arange(n - 1, dtype=np.float64) + 0.5) / fps
    scores = np.zeros((n - 1, len(seat_list)), dtype=np.float64)
    for column, seat in enumerate(seat_list):
        mouth = _change(frames, mouth_patch(seat.face))
        if mouth is None:
            continue
        head = _change(frames, eye_band(seat.face))
        scores[:, column] = np.maximum(0.0, mouth - (head if head is not None else 0.0))
    return Motion(times=times, scores=scores)


def _change(
    frames: npt.NDArray[np.uint8], box: tuple[int, int, int, int]
) -> npt.NDArray[np.float64] | None:
    """Mean absolute change per consecutive frame pair inside `box` (clipped to the frame);
    None when the clipped box is under MIN_PATCH on a side."""
    _, h, w = frames.shape
    x0, y0 = max(box[0], 0), max(box[1], 0)
    x1, y1 = min(box[2], w), min(box[3], h)
    if x1 - x0 < MIN_PATCH or y1 - y0 < MIN_PATCH:
        return None
    patch = frames[:, y0:y1, x0:x1].astype(np.int16)
    return np.abs(np.diff(patch, axis=0)).mean(axis=(1, 2)).astype(np.float64)


def assign_words(words: list[Word], motion: Motion) -> list[int | None]:
    """Each word's seat: the one with the highest mean score over the word (plus half a frame
    either side). Unknown (None) with no frames, no motion, or a lead under WIN_RATIO."""
    out: list[int | None] = []
    for w in words:
        mask = (motion.times >= w.start - WORD_SLACK_S) & (motion.times <= w.end + WORD_SLACK_S)
        if not mask.any():
            out.append(None)
            continue
        means = motion.scores[mask].mean(axis=0)
        order = np.argsort(means)[::-1]
        best = float(means[order[0]])
        runner_up = float(means[order[1]]) if len(order) > 1 else 0.0
        if best <= 0 or best < WIN_RATIO * runner_up:
            out.append(None)
        else:
            out.append(int(order[0]))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_speakers.py`
Expected: PASS (all of Task 1 and Task 2).

If `test_mouth_motion_follows_the_talking_seat` fails on the 3x ratio, look at the scores before changing anything. H.264 at CRF 12 keeps the noise, and the eye band is static gray. A ratio under 3 means the patches are misaligned, not that the threshold is wrong.

- [ ] **Step 5: Checkpoint.** Ledger file list: `src/clipforge/stages/speakers.py`, `tests/stages/test_speakers.py`.

---

### Task 3: Turns

**Files:**
- Modify: `src/clipforge/stages/speakers.py`
- Test: `tests/stages/test_speakers.py`

**Interfaces:**
- Consumes: `Word`, `MIN_TURN_S`.
- Produces:
  - `speakers.Turn(start: float, end: float, seat: int)`, a frozen dataclass with times on the same clock as the words;
  - `speakers.turns(words: list[Word], seat_ids: list[int | None], shot_start: float, shot_end: float, min_turn: float = MIN_TURN_S) -> list[Turn] | None`.
  - Rules: contiguous turns covering `[shot_start, shot_end]` exactly, in order, no two neighbors on the same seat. Returns None when no word has a seat. Word times are clamped to the shot. Boundaries are rounded to milliseconds.

- [ ] **Step 1: Write the failing tests**

Add `Turn, turns` to the `from clipforge.stages.speakers import ...` line at the top of `tests/stages/test_speakers.py`, then append:

```python

def said(*spans: tuple[float, float, int | None]) -> tuple[list[Word], list[int | None]]:
    """Words given as (start, end, seat)."""
    return [word(s, e) for s, e, _ in spans], [seat for _, _, seat in spans]


def covers(result: list[Turn], start: float, end: float) -> None:
    assert result[0].start == start and result[-1].end == end
    for a, b in zip(result, result[1:], strict=False):
        assert a.end == b.start and a.seat != b.seat and a.end > a.start


def test_alternating_turns_switch_mid_pause() -> None:
    words, ids = said((0.5, 1.5, 0), (1.6, 3.2, 0), (3.6, 5.0, 1), (5.1, 6.8, 1), (7.2, 9.5, 0))
    result = turns(words, ids, 0.0, 10.0)
    assert result == [Turn(0.0, 3.4, 0), Turn(3.4, 7.0, 1), Turn(7.0, 10.0, 0)]
    covers(result, 0.0, 10.0)


def test_short_interjection_merges_into_the_longer_neighbor() -> None:
    words, ids = said((0.0, 3.0, 0), (3.2, 3.8, 1), (4.0, 9.0, 0))  # a 0.6 s "yeah"
    assert turns(words, ids, 0.0, 9.0) == [Turn(0.0, 9.0, 0)]


def test_short_interruption_leaves_one_turn() -> None:
    words, ids = said((0.0, 2.5, 0), (2.6, 3.0, 1), (3.1, 6.0, 0), (6.4, 9.0, 1))
    result = turns(words, ids, 0.0, 9.0)
    assert result == [Turn(0.0, 6.2, 0), Turn(6.2, 9.0, 1)]
    covers(result, 0.0, 9.0)


def test_initial_silence_goes_to_the_first_speaker() -> None:
    words, ids = said((3.0, 6.0, 1), (6.4, 9.0, 0))
    assert turns(words, ids, 0.0, 10.0) == [Turn(0.0, 6.2, 1), Turn(6.2, 10.0, 0)]


def test_unknown_words_join_the_turn_before_them() -> None:
    words, ids = said((0.0, 1.0, None), (1.1, 2.5, 0), (2.6, 3.0, None), (3.5, 6.0, 1))
    assert turns(words, ids, 0.0, 6.0) == [Turn(0.0, 3.25, 0), Turn(3.25, 6.0, 1)]


def test_all_unknown_is_none() -> None:
    words, ids = said((0.0, 1.0, None), (1.2, 2.0, None))
    assert turns(words, ids, 0.0, 3.0) is None
    assert turns([], [], 0.0, 3.0) is None


def test_one_speaker_is_one_turn() -> None:
    words, ids = said((0.2, 1.0, 1), (1.2, 1.8, 1))
    assert turns(words, ids, 0.0, 1.9) == [Turn(0.0, 1.9, 1)]


def test_turns_clamp_words_to_the_shot() -> None:
    words, ids = said((1.9, 2.1, 0), (2.2, 4.4, 0), (4.6, 7.0, 1), (7.8, 8.3, 1))
    result = turns(words, ids, 2.0, 8.0)  # the shot is [2, 8): first and last words overlap it
    assert result == [Turn(2.0, 4.5, 0), Turn(4.5, 8.0, 1)]
    covers(result, 2.0, 8.0)


def test_boundaries_are_milliseconds() -> None:
    words, ids = said((0.0, 2.5, 0), (2.6001, 5.0, 1))
    (_, second) = turns(words, ids, 0.0, 5.0) or []
    assert second.start == 2.55
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/stages/test_speakers.py`
Expected: FAIL with `ImportError: cannot import name 'Turn'`.

- [ ] **Step 3: Implement**

Add to `src/clipforge/stages/speakers.py`:

```python
@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    seat: int


@dataclass
class _Run:
    seat: int
    start: float  # first word start
    end: float  # last word end

    @property
    def length(self) -> float:
        return self.end - self.start


def turns(
    words: list[Word],
    seat_ids: list[int | None],
    shot_start: float,
    shot_end: float,
    min_turn: float = MIN_TURN_S,
) -> list[Turn] | None:
    """Words to turns: runs of one seat (unknown words join the run before them), runs under
    `min_turn` merged into their longer neighbor, switches halfway through the pause between
    two runs. The first turn starts at `shot_start`, the last ends at `shot_end`."""
    known = [s for s in seat_ids if s is not None]
    if not known:
        return None
    runs: list[_Run] = []
    current = known[0]  # leading unknown words go to the first speaker
    for w, seat in zip(words, seat_ids, strict=True):
        current = seat if seat is not None else current
        start = min(max(w.start, shot_start), shot_end)
        end = min(max(w.end, shot_start), shot_end)
        if runs and runs[-1].seat == current:
            runs[-1].end = max(runs[-1].end, end)
        else:
            runs.append(_Run(current, start, end))
    while len(runs) > 1:
        i = min(range(len(runs)), key=lambda k: runs[k].length)
        if runs[i].length >= min_turn:
            break
        if i == 0:
            j = 1
        elif i == len(runs) - 1:
            j = i - 1
        else:
            j = i - 1 if runs[i - 1].length >= runs[i + 1].length else i + 1
        keep, drop = runs[j], runs[i]
        keep.start, keep.end = min(keep.start, drop.start), max(keep.end, drop.end)
        del runs[i]
        runs = _coalesce(runs)
    bounds = [shot_start]
    bounds += [round((a.end + b.start) / 2, 3) for a, b in zip(runs, runs[1:], strict=False)]
    bounds.append(shot_end)
    return [
        Turn(start, end, run.seat)
        for start, end, run in zip(bounds, bounds[1:], runs, strict=False)
        if end > start
    ]


def _coalesce(runs: list[_Run]) -> list[_Run]:
    """Join neighboring runs of the same seat (left behind when a run between them merged)."""
    out: list[_Run] = []
    for run in runs:
        if out and out[-1].seat == run.seat:
            out[-1].end = max(out[-1].end, run.end)
        else:
            out.append(run)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_speakers.py`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Ledger file list: `src/clipforge/stages/speakers.py`, `tests/stages/test_speakers.py`.

---

### Task 4: Reframe integration and runner

**Files:**
- Modify: `src/clipforge/stages/reframe.py` (`STAGE_VERSION`, `track`, `_segments`, `_largest_face` becomes `_faces_at`)
- Modify: `src/clipforge/stages/runner.py:98-107` (`clip`)
- Test: `tests/stages/test_reframe.py` (every `track(ctx, spec, detector, SETTINGS)` call gains a `words` argument, plus the new tests)

**Interfaces:**
- Consumes: `speakers.seats`, `fits_one_crop`, `group_center`, `mouth_motion`, `Motion.shifted`, `assign_words`, `turns` (Tasks 1–3); `captions.clip_words(transcript, start, end) -> list[Word]` (existing, clip-relative times).
- Produces:
  - `reframe.track(ctx, spec, words: list[Word], detector, settings) -> CropTrack`, where `words` are clip-relative, as returned by `captions.clip_words`;
  - `reframe.STAGE_VERSION = "4"`.

- [ ] **Step 1: Update the existing call sites and write the failing tests**

In `tests/stages/test_reframe.py`, change every `track(ctx_expr, spec_expr, detector_expr, SETTINGS)` to `track(ctx_expr, spec_expr, [], detector_expr, SETTINGS)`. There are 12 calls, in the tests from `test_two_shots_each_framed_on_its_face` down to `test_two_samples_never_average_two_people`. Add these to the file's top import block:

```python
from collections.abc import Callable

from clipforge.models import Word
from clipforge.stages import reframe as reframe_module
from clipforge.stages import speakers
from clipforge.stages.speakers import Motion
```

Then append:

```python
NO_CUTS = Settings(_env_file=None, scene_threshold=1.0)  # one shot, whatever testsrc2 does

LEFT_FACE = Face(cx=100, cy=180, w=60, h=70, score=0.9)  # 1280x720 source, sample 640x360
RIGHT_FACE = Face(cx=540, cy=180, w=60, h=70, score=0.9)


def words_at(*spans: tuple[float, float]) -> list[Word]:
    return [Word(text="w", start=s, end=e) for s, e in spans]


def scripted_motion(switch: float) -> Callable[..., Motion]:
    """A mouth_motion stand-in: the left seat talks before `switch` (clip seconds), the right
    after. `start` is the shot start in source seconds; returned times are relative to it."""

    def fake(video: Path, start: float, end: float, seat_list: list, size: tuple, fps: int = 10):  # type: ignore[no-untyped-def]
        times = np.arange(0.05, end - start, 0.1)
        clip_t = times + (start - 1.0)  # spec_for's clip starts at 1.0 s of the source
        left = np.where(clip_t < switch, 5.0, 0.5)
        return Motion(times=times, scores=np.column_stack([left, 5.5 - left]))

    return fake


@requires_ffmpeg
def test_two_seats_cut_to_whoever_talks(
    tmp_path: Path, media, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=6.0))
    spec = spec_for(source, "auto", start=1.0, end=6.0)  # one 5 s shot
    monkeypatch.setattr(speakers, "mouth_motion", scripted_motion(switch=2.5))
    words = words_at((0.2, 1.0), (1.1, 2.3), (2.7, 3.5), (3.6, 4.8))
    detector = FakeDetector(faces=[LEFT_FACE, RIGHT_FACE])
    result = track(make_ctx(tmp_path), spec, words, detector, NO_CUTS)
    assert [(s.start, s.end) for s in result.segments] == [(0.0, 2.5), (2.5, 5.0)]
    left_box, right_box = (s.box for s in result.segments)
    assert left_box is not None and left_box.x <= 200 <= left_box.x + left_box.w
    assert right_box is not None and right_box.x <= 1080 <= right_box.x + right_box.w


@requires_ffmpeg
def test_close_seats_share_one_centered_crop(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    a = Face(cx=290, cy=180, w=50, h=60, score=0.9)
    b = Face(cx=350, cy=180, w=50, h=60, score=0.9)  # span 265..375 = 110 px, crop is 202
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), [], FakeDetector([a, b]), NO_CUTS)
    (segment,) = result.segments
    assert segment.box is not None
    assert abs(segment.box.x + segment.box.w / 2 - 640) <= 2  # centered on 320 at 640 = 640


@requires_ffmpeg
def test_two_seats_without_words_use_largest_face_and_cache(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    big = Face(cx=540, cy=180, w=90, h=100, score=0.9)
    detector = FakeDetector(faces=[LEFT_FACE, big])
    spec = spec_for(source, "auto")
    first = track(make_ctx(tmp_path), spec, [], detector, NO_CUTS)
    box = first.segments[0].box
    assert box is not None and box.x <= 1080 <= box.x + box.w  # the larger face
    calls = detector.calls
    track(make_ctx(tmp_path), spec, [], detector, NO_CUTS)
    assert detector.calls == calls  # cached: not a degraded result


@requires_ffmpeg
def test_motion_failure_falls_back_and_is_not_cached(
    tmp_path: Path, media, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=6.0))
    spec = spec_for(source, "auto", start=1.0, end=6.0)
    words = words_at((0.2, 2.3), (2.7, 4.8))
    detector = FakeDetector(faces=[LEFT_FACE, RIGHT_FACE])

    def broken(*args: object, **kwargs: object) -> Motion:
        raise RuntimeError("ffmpeg died")

    monkeypatch.setattr(speakers, "mouth_motion", broken)
    first = track(make_ctx(tmp_path), spec, words, detector, NO_CUTS)
    assert len(first.segments) == 1 and first.segments[0].mode == "crop"  # largest face
    monkeypatch.setattr(speakers, "mouth_motion", scripted_motion(switch=2.5))
    again = track(make_ctx(tmp_path), spec, words, detector, NO_CUTS)
    assert len(again.segments) == 2  # recomputed, not served from the cache


@requires_ffmpeg
def test_cache_key_changes_with_word_timings(
    tmp_path: Path, media, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=6.0))
    spec = spec_for(source, "auto", start=1.0, end=6.0)
    monkeypatch.setattr(speakers, "mouth_motion", scripted_motion(switch=2.5))
    detector = FakeDetector(faces=[LEFT_FACE, RIGHT_FACE])
    track(make_ctx(tmp_path), spec, words_at((0.2, 2.3), (2.7, 4.8)), detector, NO_CUTS)
    calls = detector.calls
    track(make_ctx(tmp_path), spec, words_at((0.2, 2.0), (2.7, 4.8)), detector, NO_CUTS)
    assert detector.calls > calls


def test_stage_version_is_4() -> None:
    assert reframe_module.STAGE_VERSION == "4"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/stages/test_reframe.py`
Expected: FAIL. Every `track(...)` call fails with `TypeError: track() takes 4 positional arguments but 5 were given`, and `test_stage_version_is_4` fails on `'3' == '4'`.

- [ ] **Step 3: Implement**

In `src/clipforge/stages/reframe.py`:
- update the module docstring's first sentence to add: "Shots with two or more people are cut to whoever is talking (ADR-21)";
- import `hashlib`, `Word` from `clipforge.models`, and `speakers` from `clipforge.stages`;
- set `STAGE_VERSION = "4"  # 4: speaker-aware framing in multi-person shots (ADR-21)`.

`track` becomes:

```python
def track(
    ctx: JobContext,
    spec: ClipSpec,
    words: list[Word],
    detector: faces.FaceDetector,
    settings: Settings,
) -> CropTrack:
    """`words` are the clip's words with clip-relative times (captions.clip_words)."""
    if not uses_tracking(spec):
        return plan(spec)
    timings = ";".join(f"{w.start:.3f}-{w.end:.3f}" for w in words)
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
            "words": hashlib.sha256(timings.encode()).hexdigest()[:16],
        },
    )

    def compute(out_dir: Path) -> CropTrack:
        started = time.monotonic()
        ctx.report(StageName.REFRAME, 5, "finding faces")
        segments, degraded = _segments(ctx, spec, words, detector, settings)
        ...  # the rest of compute and track unchanged
```

In `_segments`, replace the per-shot loop body and add the speaker helper:

```python
def _segments(
    ctx: JobContext,
    spec: ClipSpec,
    words: list[Word],
    detector: faces.FaceDetector,
    settings: Settings,
) -> tuple[list[CropSegment], bool]:
    ...  # unchanged down to `segments: list[CropSegment] = []`
        width, height = spec.source.width, spec.source.height
        crop_w = crop_box(0.0, width, height).w / scale  # in sample pixels
        for start, end in shots.segments_from_cuts(cuts, duration):
            samples: list[list[faces.Face]] = []
            for point in SAMPLE_POINTS:
                t = spec.start + start + (end - start) * point
                decoded, found = _faces_at(video, t, size, detector)
                degraded = degraded or not decoded
                samples.append(found)
            largest = [max(found, key=lambda f: f.area) for found in samples if found]
            if not largest:
                segments.append(CropSegment(start=start, end=end, mode="blur"))
                continue
            seat_list = speakers.seats(samples)
            if len(seat_list) >= 2:
                if speakers.fits_one_crop(seat_list, crop_w):
                    box = crop_box(speakers.group_center(seat_list) * scale, width, height)
                    segments.append(CropSegment(start=start, end=end, mode="crop", box=box))
                    continue
                try:
                    framed = _speaker_segments(spec, video, start, end, seat_list, words, size)
                except Exception:
                    log.warning("speaker framing failed for %s; largest face", where, exc_info=True)
                    framed, degraded = None, True
                if framed:
                    segments.extend(framed)
                    continue
            box = crop_box(_center(largest) * scale, width, height)
            segments.append(CropSegment(start=start, end=end, mode="crop", box=box))
        return segments, degraded
    ...  # the except block unchanged


def _speaker_segments(
    spec: ClipSpec,
    video: Path,
    start: float,
    end: float,
    seat_list: list[speakers.Seat],
    words: list[Word],
    size: tuple[int, int],
) -> list[CropSegment] | None:
    """One crop segment per speaker turn in the shot [start, end) (clip seconds); None when
    no word in the shot has a clear speaker. Raises when the motion can't be measured."""
    shot_words = [w for w in words if w.start < end and w.end > start]
    if not shot_words:
        return None
    motion = speakers.mouth_motion(video, spec.start + start, spec.start + end, seat_list, size)
    ids = speakers.assign_words(shot_words, motion.shifted(start))
    found = speakers.turns(shot_words, ids, start, end)
    if found is None:
        return None
    scale = spec.source.width / size[0]
    return [
        CropSegment(
            start=turn.start,
            end=turn.end,
            mode="crop",
            box=crop_box(seat_list[turn.seat].cx * scale, spec.source.width, spec.source.height),
        )
        for turn in found
    ]


def _faces_at(
    video: Path, t: float, size: tuple[int, int], detector: faces.FaceDetector
) -> tuple[bool, list[faces.Face]]:
    """(frame decoded?, the big-enough faces at `t`), in sample pixels."""
    frame = faces.sample_frame(video, t, size)
    if frame is None:
        return False, []
    return True, [f for f in detector.detect(frame) if f.w >= MIN_FACE_WIDTH * size[0]]
```

Delete `_largest_face`, since `_faces_at` and the `largest` list replace it. `_merge_same` still runs on the result in `compute`.

In `src/clipforge/stages/runner.py`, change `clip()`:

```python
    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        ctx.report(StageName.REFRAME, 0, "framing")
        words = captions.clip_words(transcript, spec.start, spec.end)
        track = reframe.track(ctx, spec, words, self.detector, self.settings)
        ...  # unchanged from here
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_reframe.py tests/stages/test_speakers.py tests/stages/test_pipeline_e2e.py`
Expected: PASS.

Then run the whole fast suite and the linters:
`uv run pytest -q -m "not gpu and not slow" > .superpowers/sdd/2026-09-28-plan-6-speaker-framing/pytest.log 2>&1; tail -3 .superpowers/sdd/2026-09-28-plan-6-speaker-framing/pytest.log && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all passed (409 before this plan plus the new tests), ruff clean, mypy clean.

- [ ] **Step 5: Checkpoint.** Ledger file list: `src/clipforge/stages/reframe.py`, `src/clipforge/stages/runner.py`, `tests/stages/test_reframe.py`.

---

### Task 5: Docs, deploy, and real check

**Files:**
- Modify: `docs/ARCHITECTURE.md` (the "Reframe (ADR-19)" bullet and "Reframing: what's left for Phase 3"), `docs/DECISIONS.md` (append ADR-21), `ROADMAP.md` (Phase 3)
- Modify: `CLAUDE.md` (the Layout line for `stages/`: add `speakers.py`)

**Interfaces:**
- Consumes: everything above. Produces: nothing new in code.

- [ ] **Step 1: Docs**

Append to `docs/DECISIONS.md`:

```markdown
## ADR-21: Cut to the speaker in multi-person shots (visual mouth motion)
Date: 2026-09-28 · Status: Accepted
Context: Single-camera podcasts and the wide shots of multi-camera ones show two people in one shot. ADR-19 frames the largest face, so the crop stays on one person while the other talks. Options: visual mouth motion, audio diarization (pyannote on the GPU, needing torch, a gated-model token and a re-transcribe), or visual first with diarization later.
Decision: Visual first. In a shot with two or more seats (faces seen in at least 2 of reframe's 3 samples), the shot is decoded once at 10 fps in grayscale. Each seat is scored by the change in its mouth patch minus the change in its eye band, and each transcript word goes to the seat that moved most (at least 1.2x the runner-up, otherwise unknown). Runs of words become turns of at least 2 s, and each switch is a hard cut in the middle of the pause between words. Seats that fit together in one 9:16 crop are framed as a group. Any failure falls back to the largest face and isn't cached. The interface is "which seat said each word", so diarization can replace the visual step later.
Consequences: A few CPU seconds per clip and no new dependencies. A listener laughing hard can steal a turn shorter than the hold. Diarization stays open in the roadmap for footage where this is wrong. Design: docs/superpowers/specs/2026-09-28-speaker-framing-design.md.
```

In `docs/ARCHITECTURE.md`, at the end of the **Reframe (ADR-19)** bullet in "Phase 1 stage details", add:

> In shots with two or more people (ADR-21), the crop follows whoever is talking. Each word goes to the seat whose mouth moved most (mouth motion minus head motion, sampled at 10 fps), turns last at least 2 s, and switches are hard cuts mid-pause. People who fit in one crop are framed together.

Replace the "Reframing: what's left for Phase 3" paragraph with:

> Per-shot face framing (ADR-19) and cutting to the speaker in multi-person shots (ADR-21) are done. Still open: audio diarization (pyannote) where the visual speaker choice is wrong, and a crop center smoothed with EMA/Kalman for people who move a lot within a shot, reset at cuts.

Also fix the stale reframe row of the stage table so the Output reads: `CropTrack` (per-shot crop boxes around the largest face, or cut between speakers in multi-person shots, or blur segments).

In `ROADMAP.md` Phase 3, replace `- [ ] Active speaker selection using diarization (WhisperX / pyannote)` with:

```markdown
- [x] Active speaker selection: cut to whoever is talking in multi-person shots, by mouth motion (ADR-21)
- [ ] Audio diarization (pyannote) for speaker choice, if mouth motion proves unreliable
```

In the "Later / ideas" sub-project line, replace `speaker-aware framing + split screen for single-camera podcasts;` with `split-screen layouts;`.

In `CLAUDE.md`'s Layout, change `shots.py/faces.py (reframe helpers)` to `shots.py/faces.py/speakers.py (reframe helpers)`.

- [ ] **Step 2: Full checks**

Run: `uv run pytest -q -m "not gpu and not slow" > .superpowers/sdd/2026-09-28-plan-6-speaker-framing/pytest.log 2>&1; tail -3 .superpowers/sdd/2026-09-28-plan-6-speaker-framing/pytest.log && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all passed; ruff and mypy clean.

- [ ] **Step 3: Deploy**

Run: `uv run modal deploy src/clipforge/app.py`
Expected: `✓ App deployed`.

- [ ] **Step 4: Real check**

Run: `uv run clipforge clip videos/billy_carton-Koa_smith.mp4 --again`
Expected: the job finishes and the clips land in a new `videos/out/billy_carton-Koa_smith-<N>/`. It costs about $0.01: the transcript and highlights come from cache, and only the captions call hits Haiku.

Then find a clip with a speaker switch. Each clip's `metadata.json` doesn't carry segments, so read the reframe results from the Volume:

```bash
uv run python -m modal volume ls clipforge-jobs /cache/reframe | head
```

Alternatively, save a frame every 2 s from each clip and look for wide-shot clips:

```bash
for f in videos/out/billy_carton-Koa_smith-<N>/clip_*/video.mp4; do
  ffmpeg -v error -i "$f" -vf "fps=0.5,scale=270:-2,tile=8x1" -frames:v 1 "${f%.mp4}_strip.png"
done
```

Open the strips. In a clip that includes a wide shot of both people, the crop should switch between them. Check the frames either side of a switch against `captions.srt`: the person shown should be the one saying those lines. Record in the ledger what you saw, including any wrong switches with their times.

- [ ] **Step 5: Checkpoint.** Ledger file list: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `ROADMAP.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-09-28-speaker-framing-design.md`, `docs/superpowers/plans/2026-09-28-plan-6-speaker-framing.md`.

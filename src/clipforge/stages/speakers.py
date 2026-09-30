"""Who is talking in a shot with several people (ADR-21): seats from reframe's face samples,
mouth motion minus head motion per seat, words given to the seat that moved most, and turns
of at least 2 s that switch in the middle of a pause.

All positions are in sample pixels (faces.sample_size); times are in seconds."""

from __future__ import annotations

import itertools
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from clipforge.models import Word
from clipforge.stages.faces import Face

MOTION_FPS = 10
MIN_TURN_S = 2.0
WIN_RATIO = 1.2  # the winning seat must move 1.2x as much as the runner-up
MIN_SEEN = 2  # a seat must appear in at least 2 of the 3 samples
GROUP_PAD = 0.10  # padding around a group that must fit in one crop
MIN_PATCH = 4  # patches under 4x4 px score 0
WORD_SLACK_S = 0.5 / MOTION_FPS  # a word also counts the frames just around it


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
        present = [p for p in points if p is not None]
        if len(present) != len(points):
            return None
        return med([p[0] for p in present]), med([p[1] for p in present])

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
    for a, b in itertools.pairwise(runs):  # never backwards, even if words overlap (review)
        bounds.append(min(max(round((a.end + b.start) / 2, 3), bounds[-1]), shot_end))
    bounds.append(shot_end)
    out: list[Turn] = []
    for start, end, run in zip(bounds, bounds[1:], runs, strict=False):
        if end <= start:
            continue
        if out and out[-1].seat == run.seat:
            out[-1] = Turn(out[-1].start, end, run.seat)
        else:
            out.append(Turn(start, end, run.seat))
    return out


def _coalesce(runs: list[_Run]) -> list[_Run]:
    """Join neighboring runs of the same seat (left behind when a run between them merged)."""
    out: list[_Run] = []
    for run in runs:
        if out and out[-1].seat == run.seat:
            out[-1].end = max(out[-1].end, run.end)
        else:
            out.append(run)
    return out

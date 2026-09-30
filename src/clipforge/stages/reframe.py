"""Reframe to 9:16 (ADR-19). For landscape sources in `auto` mode, each camera shot is
cropped around its largest face, fixed for the shot. Shots with two or more people are cut to
whoever is talking (ADR-21). Shots without a reliable face, and any
detection failure, use the blurred-background fit. Already-vertical and near-square sources
and forced `center`/`blur` keep the fixed Phase 1 `plan`."""

from __future__ import annotations

import hashlib
import logging
import statistics
import time
from pathlib import Path

from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, cached_stage
from clipforge.models import (
    ClipSpec,
    CropBox,
    CropSegment,
    CropTrack,
    StageCost,
    StageName,
    Word,
)
from clipforge.stages import faces, shots, speakers

log = logging.getLogger(__name__)

STAGE_VERSION = "4"  # 4: speaker-aware framing in multi-person shots (ADR-21)
SAMPLE_POINTS = (0.25, 0.5, 0.75)  # where in each shot to look for faces
MIN_FACE_WIDTH = 0.04  # of the sample width: smaller faces (posters, far away) don't count

OUT_W, OUT_H = 1080, 1920
TARGET = OUT_W / OUT_H
LANDSCAPE_MIN = 1.2  # width/height above this counts as landscape for "auto"


def _even(value: float) -> int:
    n = round(value)
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


def crop_box(cx: float, width: int, height: int) -> CropBox:
    """Full-height 9:16 box horizontally centered on `cx`, kept inside the frame."""
    crop_h = height - height % 2
    crop_w = min(width - width % 2, _even(crop_h * TARGET))
    x = _even(min(max(cx - crop_w / 2, 0.0), width - crop_w))
    return CropBox(x=x, y=(height - crop_h) // 2, w=crop_w, h=crop_h)


def uses_tracking(spec: ClipSpec) -> bool:
    aspect = spec.source.width / spec.source.height
    return (
        spec.options.reframe == "auto" and abs(aspect - TARGET) >= 0.01 and aspect >= LANDSCAPE_MIN
    )


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
        ctx.record_cost(StageCost(stage=StageName.REFRAME, wall_s=time.monotonic() - started))
        result = CropTrack(
            clip_id=spec.clip_id, mode="tracked", box=None, segments=_merge_same(segments)
        )
        if degraded:
            raise _Degraded(result)  # use it for this clip, but never cache a fallback
        return result

    try:
        stored = cached_stage(ctx, StageName.REFRAME, key, CropTrack, compute, clip_id=spec.clip_id)
    except _Degraded as fallback:
        return fallback.track
    # The cache is keyed on the time range, never the clip id (ADR-8): rebind to this clip.
    return stored.value.model_copy(update={"clip_id": spec.clip_id})


class _Degraded(Exception):
    """A fallback track: used for this clip, never cached (a retry or re-cut tries again)."""

    def __init__(self, track: CropTrack) -> None:
        super().__init__("degraded reframe")
        self.track = track


def _segments(
    ctx: JobContext,
    spec: ClipSpec,
    words: list[Word],
    detector: faces.FaceDetector,
    settings: Settings,
) -> tuple[list[CropSegment], bool]:
    """The shots and their framing, plus whether anything failed along the way (then the
    result is a fallback that must not be cached)."""
    duration = spec.duration_s
    where = f"{spec.clip_id} of job {ctx.job_id} (source {spec.source.source_hash[:12]})"
    degraded = False
    try:
        video = ctx.path(spec.source.video_path)
        try:
            cuts = shots.detect_cuts(video, spec.start, spec.end, settings.scene_threshold)
        except Exception:
            log.warning("scene detection failed for %s; one shot", where, exc_info=True)
            cuts, degraded = [], True
        size = faces.sample_size(spec.source.width, spec.source.height)
        scale = spec.source.width / size[0]
        segments: list[CropSegment] = []
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
    except Exception:
        log.warning("face reframing failed for %s; using the blurred fit", where, exc_info=True)
        return [CropSegment(start=0.0, end=duration, mode="blur")], True


def _center(found: list[faces.Face]) -> float:
    """With a face in every sample, the median center (robust to one odd frame). With fewer,
    the largest face's center: a median of two is their mean, which can land between two
    people."""
    if len(found) == len(SAMPLE_POINTS):
        return statistics.median(f.cx for f in found)
    return max(found, key=lambda f: f.area).cx


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

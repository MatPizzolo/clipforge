"""Clips as Timelines (spec §5)."""

import pytest

from clipforge.models import (
    CaptionFiles,
    ClipSpec,
    CropBox,
    CropSegment,
    CropTrack,
    Permission,
    VideoSegment,
)
from clipforge.stages import timeline
from tests.test_models import make_spec

BOX = CropBox(x=420, y=0, w=606, h=1080)
CAPS = CaptionFiles(
    clip_id="clip_01",
    ass_path="cache/captions/k/clip.ass",
    srt_path="cache/captions/k/clip.srt",
    style="default",
    offset_s=100.0,
)


def spec(start: float = 100.0, end: float = 103.0) -> ClipSpec:
    return make_spec().model_copy(update={"start": start, "end": end})


def test_center_is_one_crop_segment_over_the_clip() -> None:
    track = CropTrack(clip_id="clip_01", mode="center", box=BOX)
    tl = timeline.for_clip(spec(), track, CAPS, Permission.OWN)
    (seg,) = tl.visual
    assert isinstance(seg, VideoSegment)
    assert (seg.kind, seg.fit, seg.box, seg.in_s, seg.start, seg.end) == (
        "source",
        "crop",
        BOX,
        100.0,
        0.0,
        3.0,
    )
    assert (seg.path, seg.media_hash, seg.width, seg.height) == (
        "work/ingest/abc/source.mp4",
        "f" * 64,
        1920,
        1080,
    )
    assert tl.duration_s == 3.0 and tl.fps == 30 and (tl.width, tl.height) == (1080, 1920)


def test_blur_fallback_is_one_blur_segment() -> None:
    tl = timeline.for_clip(
        spec(), CropTrack(clip_id="clip_01", mode="blur_fallback", box=None), CAPS, Permission.OWN
    )
    (seg,) = tl.visual
    assert isinstance(seg, VideoSegment) and seg.fit == "blur" and seg.box is None


def test_tracked_maps_each_shot_with_its_media_time() -> None:
    track = CropTrack(
        clip_id="clip_01",
        mode="tracked",
        box=None,
        segments=[
            CropSegment(start=0.0, end=1.0, mode="crop", box=BOX),
            CropSegment(start=1.0, end=3.0, mode="blur"),
        ],
    )
    tl = timeline.for_clip(spec(), track, CAPS, Permission.OWN)
    a, b = tl.visual
    assert isinstance(a, VideoSegment) and isinstance(b, VideoSegment)
    assert (a.fit, a.in_s, a.start, a.end) == ("crop", 100.0, 0.0, 1.0)
    assert (b.fit, b.in_s, b.start, b.end) == ("blur", 101.0, 1.0, 3.0)


def test_last_shot_is_clamped_to_the_clip_duration() -> None:
    # A cached reframe track can end a hair short of the duration (float rounding).
    track = CropTrack(
        clip_id="clip_01",
        mode="tracked",
        box=None,
        segments=[CropSegment(start=0.0, end=2.9995, mode="blur")],
    )
    tl = timeline.for_clip(spec(), track, CAPS, Permission.OWN)
    assert tl.visual[-1].end == 3.0


def test_audio_overlay_and_assets() -> None:
    track = CropTrack(clip_id="clip_01", mode="center", box=BOX)
    tl = timeline.for_clip(spec(), track, CAPS, Permission.CC_BY, credit="Jane, CC BY 4.0")
    (audio,) = tl.audio
    assert (audio.kind, audio.path, audio.in_s, audio.start, audio.end, audio.gain_db) == (
        "source",
        "work/ingest/abc/source.mp4",
        100.0,
        0.0,
        3.0,
        0.0,
    )
    assert tl.overlay is not None
    assert (tl.overlay.ass_path, tl.overlay.srt_path) == (CAPS.ass_path, CAPS.srt_path)
    (asset,) = tl.assets
    assert (asset.kind, asset.license, asset.attribution) == (
        "source_video",
        "cc_by",
        "Jane, CC BY 4.0",
    )


@pytest.mark.parametrize(("fps", "expected"), [(29.97, 30), (59.94, 60), (120.0, 60), (0.0, 30)])
def test_clip_fps_matches_todays_rule(fps: float, expected: int) -> None:
    source = make_spec().source.model_copy(update={"fps": fps})
    assert timeline.clip_fps(make_spec().model_copy(update={"source": source})) == expected

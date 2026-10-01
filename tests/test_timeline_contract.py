"""Timeline contracts (ADR-31, spec §3)."""

import pytest
from pydantic import TypeAdapter, ValidationError

from clipforge.models import (
    AssetSource,
    AudioTrack,
    CropBox,
    KenBurns,
    StillSegment,
    Subtitles,
    Timeline,
    VideoSegment,
    VisualSegment,
)

BOX = CropBox(x=0, y=0, w=202, h=360)


def video(start: float, end: float, **kw: object) -> VideoSegment:
    fields: dict[str, object] = {
        "kind": "source",
        "path": "uploads/a.mp4",
        "width": 640,
        "height": 360,
        "in_s": 10.0 + start,
        "start": start,
        "end": end,
        "fit": "crop",
        "box": BOX,
    }
    fields.update(kw)
    return VideoSegment(**fields)  # type: ignore[arg-type]


def still(start: float, end: float, **kw: object) -> StillSegment:
    fields: dict[str, object] = {
        "path": "assets/a.png",
        "width": 1080,
        "height": 1920,
        "start": start,
        "end": end,
    }
    fields.update(kw)
    return StillSegment(**fields)  # type: ignore[arg-type]


def timeline(**kw: object) -> Timeline:
    fields: dict[str, object] = {
        "fps": 30,
        "duration_s": 3.0,
        "visual": [video(0.0, 1.0), still(1.0, 3.0)],
        "audio": [AudioTrack(kind="source", path="uploads/a.mp4", in_s=10.0, start=0.0, end=3.0)],
    }
    fields.update(kw)
    return Timeline(**fields)  # type: ignore[arg-type]


def test_a_valid_timeline_round_trips_through_json() -> None:
    tl = timeline(
        overlay=Subtitles(ass_path="cache/captions/k/clip.ass"),
        assets=[AssetSource(kind="source_video", license="own")],
    )
    again = Timeline.model_validate_json(tl.model_dump_json())
    assert again == tl
    assert isinstance(again.visual[1], StillSegment)


def test_the_union_is_discriminated_by_type() -> None:
    parsed = TypeAdapter(VisualSegment).validate_python(still(0.0, 1.0).model_dump())
    assert isinstance(parsed, StillSegment)


@pytest.mark.parametrize(
    "visual",
    [
        [video(0.0, 1.0), still(1.5, 3.0)],  # gap
        [video(0.5, 1.0), still(1.0, 3.0)],  # doesn't start at 0
        [video(0.0, 1.0), still(1.0, 2.5)],  # ends before duration_s
        [],
    ],
)
def test_visual_segments_cover_the_timeline_contiguously(visual: list[object]) -> None:
    with pytest.raises(ValidationError):
        timeline(visual=visual)


def test_box_iff_crop() -> None:
    with pytest.raises(ValidationError):
        video(0.0, 1.0, fit="crop", box=None)
    with pytest.raises(ValidationError):
        video(0.0, 1.0, fit="blur", box=BOX)
    assert video(0.0, 1.0, fit="cover", box=None).box is None


def test_ken_burns_only_on_cover_stills() -> None:
    with pytest.raises(ValidationError):
        still(0.0, 1.0, fit="blur", ken_burns=KenBurns())
    assert still(0.0, 1.0, ken_burns=KenBurns()).ken_burns is not None


def test_duck_only_on_music() -> None:
    with pytest.raises(ValidationError):
        AudioTrack(kind="narration", path="a.wav", start=0.0, end=1.0, duck=True)
    assert AudioTrack(kind="music", path="m.wav", start=0.0, end=1.0, duck=True).duck


def test_audio_tracks_stay_inside_the_timeline() -> None:
    late = AudioTrack(kind="music", path="m.wav", start=2.0, end=3.5)
    with pytest.raises(ValidationError):
        timeline(audio=[late])


@pytest.mark.parametrize("path", ["/etc/passwd", "../x.mp4", "a/../../x.mp4", ""])
def test_paths_are_relative_to_the_jobs_root(path: str) -> None:
    with pytest.raises(ValidationError):
        video(0.0, 1.0, path=path)
    with pytest.raises(ValidationError):
        AudioTrack(kind="music", path=path, start=0.0, end=1.0)
    with pytest.raises(ValidationError):
        Subtitles(ass_path=path)


@pytest.mark.parametrize("focus", [(-0.1, 0.5), (0.5, 1.2)])
def test_ken_burns_focus_is_a_fraction(focus: tuple[float, float]) -> None:
    with pytest.raises(ValidationError):
        KenBurns(focus_from=focus)
    with pytest.raises(ValidationError):
        KenBurns(focus_to=focus)


@pytest.mark.parametrize(("width", "height"), [(1081, 1920), (1080, 0), (0, 1920)])
def test_output_size_is_positive_and_even(width: int, height: int) -> None:
    with pytest.raises(ValidationError):
        timeline(width=width, height=height)

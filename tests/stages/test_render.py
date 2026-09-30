import itertools
import re
import subprocess
from pathlib import Path

import pytest

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.models import ClipSpec, CropBox, CropSegment, CropTrack, Segment, Transcript, Word
from clipforge.stages import captions, reframe, render
from clipforge.stages.render import TELEGRAM_LIMIT_BYTES, video_bitrate
from tests.conftest import MediaFactory, requires_ffmpeg
from tests.stages.helpers import (
    assert_vertical_clip,
    band_diff,
    gray_frame,
    make_ctx,
    source_from,
    spec_for,
)
from tests.test_models import make_source, make_spec

pytestmark = requires_ffmpeg

WORDS = [Word(text="HELLO", start=1.2, end=1.6), Word(text="WORLD", start=1.7, end=2.4)]


def transcript(words: list[Word]) -> Transcript:
    segs = [Segment(start=words[0].start, end=words[-1].end, text="", words=words)] if words else []
    return Transcript(language="en", duration_s=6.0, model="fake", segments=segs)


def render_clip(root: Path, spec: ClipSpec, words: list[Word] = WORDS) -> Path:
    ctx = make_ctx(root)
    caps = captions.run(ctx, spec, transcript(words)).value
    stored = render.run(
        ctx, spec, reframe.plan(spec), caps, Settings(_env_file=None, jobs_root=root)
    )
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
    # Text over testsrc2's bright yellow/blue bars has little luma contrast; ~9.7 measured.
    assert band_diff(gray_frame(with_words, t), gray_frame(without, t)) > 5


def test_rotated_source_renders_upright(tmp_path: Path, media: MediaFactory) -> None:
    phone = tmp_path / "phone.mp4"
    ffmpeg.run(
        ["-display_rotation:v:0", "90", "-i", str(media(duration_s=6.0)), "-c", "copy", str(phone)]
    )
    source = source_from(tmp_path, phone)
    assert (source.width, source.height) == (180, 320)
    out = render_clip(tmp_path, spec_for(source, "auto"))  # 9:16 after rotation: full frame
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


def test_renders_are_cached(
    tmp_path: Path, media: MediaFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    track = _tracked([(a, b, boxes[i % 3]) for i, (a, b) in enumerate(itertools.pairwise(cuts))])
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


def _integrated_lufs(path: Path) -> float:
    out = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null",
         "-"], capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    return float(re.findall(r"^\s+I:\s+(-?[0-9.]+) LUFS", out, re.M)[-1])


def test_audio_is_normalized_to_minus_14_lufs(tmp_path: Path) -> None:
    quiet = tmp_path / "quiet.mp4"
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=f=440:d=6:sample_rate=48000,volume=-12dB",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(quiet),
    ])  # fmt: skip
    assert _integrated_lufs(quiet) < -30  # the source really is quiet
    out = render_clip(tmp_path, spec_for(source_from(tmp_path, quiet), "center"))
    assert abs(_integrated_lufs(out) - (-14.0)) <= 1.5
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


@pytest.mark.parametrize(
    ("height", "cap"), [(360, 3_000_000), (480, 3_000_000), (720, 5_000_000), (1080, 8_000_000)]
)
def test_bitrate_is_capped_by_source_height(height: int, cap: int) -> None:
    assert video_bitrate(10, height) == cap
    assert video_bitrate(170, height) <= cap  # long clips still get the Telegram budget


@pytest.mark.parametrize(
    ("width", "height", "cap"),
    [(720, 1280, 5_000_000), (480, 854, 3_000_000), (1920, 1080, 8_000_000), (640, 360, 3_000_000)],
)
def test_bitrate_cap_uses_the_short_side(width: int, height: int, cap: int) -> None:
    # "720p" means the short side: a vertical 720x1280 phone video is 720p, not 1280p.
    source = make_source().model_copy(update={"width": width, "height": height})
    spec = make_spec().model_copy(update={"source": source})
    assert render.bitrate_for(spec) == min(cap, video_bitrate(spec.duration_s))

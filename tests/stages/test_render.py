import itertools
import re
import subprocess
from pathlib import Path

import pytest

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.models import (
    AssetSource,
    CaptionFiles,
    ClipSpec,
    CropBox,
    CropSegment,
    CropTrack,
    Permission,
    RenderedVideo,
    Segment,
    Timeline,
    Transcript,
    VideoSegment,
    Word,
)
from clipforge.pipeline.errors import PermanentError
from clipforge.stages import captions, reframe, render, timeline
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


CAPS = CaptionFiles(
    clip_id="clip_01",
    ass_path="cache/captions/k/clip.ass",
    srt_path="cache/captions/k/clip.srt",
    style="default",
    offset_s=100.0,
)


def clip_timeline(
    root: Path, spec: ClipSpec, track: CropTrack, words: list[Word] = WORDS
) -> Timeline:
    caps = captions.run(make_ctx(root), spec, transcript(words)).value
    return timeline.for_clip(spec, track, caps, Permission.OWN)


def render_timeline(root: Path, tl: Timeline) -> RenderedVideo:
    ctx = make_ctx(root)
    return render.run(ctx, tl, Settings(_env_file=None, jobs_root=root), clip_id="clip_01").value


def render_clip(root: Path, spec: ClipSpec, words: list[Word] = WORDS) -> Path:
    tl = clip_timeline(root, spec, reframe.plan(spec), words)
    return root / render_timeline(root, tl).video_path


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
    tl = clip_timeline(tmp_path, spec, reframe.plan(spec))
    monkeypatch.setattr(
        ffmpeg, "run", lambda args, timeout=900, loglevel="warning": calls.append(args) or ""
    )
    render.run(make_ctx(tmp_path), tl, Settings(_env_file=None, jobs_root=tmp_path))
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
    return root / render_timeline(root, clip_timeline(root, spec, track)).video_path


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
    blur = CropTrack(clip_id="c", mode="blur_fallback", box=None)
    tl = timeline.for_clip(spec, blur, CAPS, Permission.OWN)
    assert render.bitrate_for(tl) == min(cap, video_bitrate(spec.duration_s))


def test_render_key_ignores_assets() -> None:
    # A permission edit (`clipforge source edit`) must not re-render every clip (log #342).
    spec = make_spec().model_copy(update={"start": 100.0, "end": 103.0})
    track = CropTrack(clip_id="c", mode="blur_fallback", box=None)
    own = timeline.for_clip(spec, track, CAPS, Permission.OWN)
    licensed = own.model_copy(
        update={"assets": [AssetSource(kind="source_video", license="cc_by", attribution="Jane")]}
    )
    assert render.key(own) == render.key(licensed)
    other = own.model_copy(
        update={"visual": [own.visual[0].model_copy(update={"media_hash": "x"})]}
    )
    assert render.key(other) != render.key(own)


def test_render_key_ignores_paths_of_hashed_media_and_the_srt() -> None:
    # The same bytes ingested from two URLs live under two ingest keys (review CP2 #3).
    spec = make_spec().model_copy(update={"start": 100.0, "end": 103.0})
    track = CropTrack(clip_id="c", mode="blur_fallback", box=None)
    own = timeline.for_clip(spec, track, CAPS, Permission.OWN)
    moved = timeline.for_clip(
        spec.model_copy(update={"source": spec.source.model_copy(
            update={"video_path": "work/ingest/other/source.mp4"})}),
        track,
        CAPS.model_copy(update={"srt_path": "cache/captions/other/clip.srt"}),
        Permission.OWN,
    )  # fmt: skip
    assert render.key(moved) == render.key(own)
    unhashed = own.model_copy(
        update={"visual": [own.visual[0].model_copy(update={"media_hash": None})]}
    )
    re_pathed = unhashed.model_copy(
        update={"visual": [unhashed.visual[0].model_copy(update={"path": "x/y.mp4"})]}
    )
    assert render.key(re_pathed) != render.key(unhashed)  # without a hash, the path is the identity


def test_two_pass_loudness_is_recorded(tmp_path: Path, media: MediaFactory) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "center")
    rendered = render_timeline(tmp_path, clip_timeline(tmp_path, spec, reframe.plan(spec)))
    assert rendered.loudness.mode in ("linear", "dynamic")
    assert rendered.loudness.input_i is not None


def test_silent_source_falls_back_to_single_pass(tmp_path: Path) -> None:
    hush = tmp_path / "hush.mp4"
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(hush),
    ])  # fmt: skip
    spec = spec_for(source_from(tmp_path, hush), "center")
    rendered = render_timeline(tmp_path, clip_timeline(tmp_path, spec, reframe.plan(spec)))
    assert rendered.loudness.mode == "single_pass"
    assert_vertical_clip(rendered.probe, expected_s=3.0)


def test_unparseable_measurement_falls_back(
    tmp_path: Path, media: MediaFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "center")
    tl = clip_timeline(tmp_path, spec, reframe.plan(spec))
    real = ffmpeg.run

    def no_report(args: list[str], timeout: float = 900, loglevel: str = "warning") -> str:
        out = real(args, timeout, loglevel)
        return "garbled" if loglevel == "info" else out

    monkeypatch.setattr(ffmpeg, "run", no_report)
    rendered = render_timeline(tmp_path, tl)
    assert rendered.loudness.mode == "single_pass"


# v3's output for this clip, measured on 2026-10-01 before the switch (local ffmpeg 6.1.1):
# 1080x1920, 30 fps, 3.000 s (video 3.000, audio 3.000), h264/yuv420p/aac, 1 video + 1 audio.
V3_ONE_SHOT = {"size": (1080, 1920), "fps": 30.0, "duration_s": 3.0, "streams": (1, 1)}


def test_one_shot_tracked_clip_matches_v3(tmp_path: Path, media: MediaFactory) -> None:
    # The single-segment form replaces v3's split=1/trim/concat graph (owner, CP3).
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "auto")
    one = CropTrack(
        clip_id="clip_01",
        mode="tracked",
        box=None,
        segments=[CropSegment(start=0.0, end=3.0, mode="crop", box=LEFT)],
    )
    probe = ffmpeg.probe_info(render_tracked(tmp_path, spec, one))
    assert (probe.width, probe.height) == V3_ONE_SHOT["size"]
    assert abs(probe.fps - V3_ONE_SHOT["fps"]) < 0.01
    frame = 1 / V3_ONE_SHOT["fps"]
    for duration in (probe.duration_s, probe.video_duration_s, probe.audio_duration_s):
        assert duration is not None and abs(duration - V3_ONE_SHOT["duration_s"]) <= frame
    assert (probe.n_video_streams, probe.n_audio_streams) == V3_ONE_SHOT["streams"]


def test_video_shorter_than_the_timeline_is_refused(tmp_path: Path) -> None:
    # Review CP3 #1: media shorter than its segment gave 2 s of picture under 4 s of sound.
    a = tmp_path / "a"
    a.mkdir()
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(a / "short.mp4"),
    ])  # fmt: skip
    tl = Timeline(
        fps=30,
        duration_s=4.0,
        visual=[
            VideoSegment(kind="broll", path="a/short.mp4", width=640, height=360, in_s=0.0,
                         start=0.0, end=4.0, fit="cover"),
        ],
    )  # fmt: skip
    with pytest.raises(PermanentError, match="video ends"):
        render_timeline(tmp_path, tl)


def test_a_failed_measurement_run_is_retried_not_skipped(
    tmp_path: Path, media: MediaFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An ffmpeg error in pass 1 raises (transient: Modal retries the step, ADR-15); only an
    # unreadable report falls back to single pass.
    spec = spec_for(source_from(tmp_path, media(width=640, height=360, duration_s=6.0)), "center")
    tl = clip_timeline(tmp_path, spec, reframe.plan(spec))

    def broken(args: list[str], timeout: float = 900, loglevel: str = "warning") -> str:
        raise ffmpeg.FfmpegError("ffmpeg", "boom")

    monkeypatch.setattr(ffmpeg, "run", broken)
    with pytest.raises(ffmpeg.FfmpegError):
        render_timeline(tmp_path, tl)


def test_measurement_run_skips_video_and_silence_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    hush = tmp_path / "hush.mp4"
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(hush),
    ])  # fmt: skip
    spec = spec_for(source_from(tmp_path, hush), "center")
    tl = clip_timeline(tmp_path, spec, reframe.plan(spec))
    seen: list[list[str]] = []
    real = ffmpeg.run

    def spy(args: list[str], timeout: float = 900, loglevel: str = "warning") -> str:
        seen.append(args)
        return real(args, timeout, loglevel)

    monkeypatch.setattr(ffmpeg, "run", spy)
    with caplog.at_level("WARNING"):
        render_timeline(tmp_path, tl)
    measure = next(args for args in seen if "null" in args)
    assert "-vn" in measure
    assert "silent" in caplog.text


def test_clip_at_the_tail_of_a_short_video_stream_still_renders(tmp_path: Path) -> None:
    # Final review I-2: browser and screen recordings can stop the picture before the sound.
    # A clip ending there shipped in v3 with a short picture; it must not fail permanently.
    early = tmp_path / "early.mp4"
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=5.5",
        "-f", "lavfi", "-i", "sine=f=440:d=6:sample_rate=48000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(early),
    ])  # fmt: skip
    spec = spec_for(source_from(tmp_path, early), "center", start=3.0, end=5.95)
    rendered = render_timeline(tmp_path, clip_timeline(tmp_path, spec, reframe.plan(spec)))
    assert rendered.probe.audio_duration_s is not None
    assert abs(rendered.probe.audio_duration_s - 2.95) < 0.05

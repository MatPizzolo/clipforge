"""Filtergraph builders (spec §4). The clip goldens are v3's exact strings."""

import re
import subprocess
from pathlib import Path

from clipforge import ffmpeg
from clipforge.models import (
    AudioTrack,
    CaptionFiles,
    CropBox,
    CropSegment,
    CropTrack,
    KenBurns,
    Permission,
    StillSegment,
    Timeline,
    VideoSegment,
)
from clipforge.stages import render_graph, timeline
from tests.conftest import requires_ffmpeg
from tests.test_models import make_spec

ROOT = Path("/jobs")
FONTS = Path("/fonts")
CAPS = CaptionFiles(
    clip_id="clip_01",
    ass_path="cache/captions/k/clip.ass",
    srt_path="cache/captions/k/clip.srt",
    style="default",
    offset_s=100.0,
)
LEFT = CropBox(x=0, y=0, w=202, h=360)
RIGHT = CropBox(x=438, y=0, w=202, h=360)
SUBS = "ass=filename=/jobs/cache/captions/k/clip.ass:fontsdir=/fonts"

GOLDEN_CENTER = f"[0:v]crop=202:360:219:0,scale=1080:1920:flags=lanczos,setsar=1,{SUBS}[v]"
GOLDEN_BLUR = (
    "[0:v]split=2[bbg][bfg];[bbg]scale=270:480:force_original_aspect_ratio=increase,"
    "crop=270:480,boxblur=10:1,scale=1080:1920[bbgb];[bfg]scale=1080:1920:"
    "force_original_aspect_ratio=decrease[bfgs];[bbgb][bfgs]overlay=(W-w)/2:(H-h)/2,"
    f"setsar=1[fit];[fit]{SUBS}[v]"
)
GOLDEN_TRACKED = (
    "[0:v]split=3[s0][s1][s2];[s0]trim=start=0.000:end=1.000,setpts=PTS-STARTPTS,"
    "crop=202:360:0:0,scale=1080:1920:flags=lanczos,setsar=1[p0];[s1]trim=start=1.000:"
    "end=2.000,setpts=PTS-STARTPTS[t1];[t1]split=2[b1bg][b1fg];[b1bg]scale=270:480:"
    "force_original_aspect_ratio=increase,crop=270:480,boxblur=10:1,scale=1080:1920[b1bgb];"
    "[b1fg]scale=1080:1920:force_original_aspect_ratio=decrease[b1fgs];[b1bgb][b1fgs]"
    "overlay=(W-w)/2:(H-h)/2,setsar=1[p1];[s2]trim=start=2.000,setpts=PTS-STARTPTS,"
    "crop=202:360:438:0,scale=1080:1920:flags=lanczos,setsar=1[p2];[p0][p1][p2]concat=n=3:"
    f"v=1:a=0,{SUBS}[v]"
)


def clip_timeline(track: CropTrack) -> Timeline:
    spec = make_spec().model_copy(update={"start": 100.0, "end": 103.0})
    return timeline.for_clip(spec, track, CAPS, Permission.OWN)


def graphs(tl: Timeline) -> tuple[str, render_graph.AudioGraph, render_graph.Inputs]:
    inputs = render_graph.plan_inputs(tl, ROOT)
    subs = render_graph.subtitles(tl, ROOT, FONTS)
    return render_graph.video_graph(tl, inputs, subs), render_graph.audio_graph(tl, inputs), inputs


def test_center_clip_graph_is_unchanged() -> None:
    video, audio, inputs = graphs(
        clip_timeline(CropTrack(clip_id="c", mode="center", box=CropBox(x=219, y=0, w=202, h=360)))
    )
    assert video == GOLDEN_CENTER
    assert (audio.parts, audio.pre, audio.silent) == ([], "[0:a:0]", False)  # today's -af chain
    assert inputs.args == [
        "-ss",
        "100.000",
        "-t",
        "3.000",
        "-i",
        "/jobs/work/ingest/abc/source.mp4",
    ]


def test_blur_clip_graph_is_unchanged() -> None:
    video, _, _ = graphs(clip_timeline(CropTrack(clip_id="c", mode="blur_fallback", box=None)))
    assert video == GOLDEN_BLUR


def test_tracked_clip_graph_is_unchanged() -> None:
    track = CropTrack(
        clip_id="c",
        mode="tracked",
        box=None,
        segments=[
            CropSegment(start=0.0, end=1.0, mode="crop", box=LEFT),
            CropSegment(start=1.0, end=2.0, mode="blur"),
            CropSegment(start=2.0, end=3.0, mode="crop", box=RIGHT),
        ],
    )
    video, _, _ = graphs(clip_timeline(track))
    assert video == GOLDEN_TRACKED


def test_single_shot_tracked_uses_the_whole_range_form() -> None:
    track = CropTrack(
        clip_id="c",
        mode="tracked",
        box=None,
        segments=[CropSegment(start=0.0, end=3.0, mode="crop", box=LEFT)],
    )
    video, _, _ = graphs(clip_timeline(track))
    assert video == f"[0:v]crop=202:360:0:0,scale=1080:1920:flags=lanczos,setsar=1,{SUBS}[v]"


def mixed() -> Timeline:
    return Timeline(
        fps=30,
        duration_s=10.0,
        visual=[
            StillSegment(
                path="a/s1.png",
                width=1080,
                height=1920,
                start=0.0,
                end=4.0,
                ken_burns=KenBurns(zoom_to=1.2),
            ),
            VideoSegment(
                kind="broll",
                path="a/b.mp4",
                width=1280,
                height=720,
                in_s=2.0,
                start=4.0,
                end=7.0,
                fit="cover",
            ),
            StillSegment(path="a/s2.png", width=640, height=480, start=7.0, end=10.0, fit="blur"),
        ],
        audio=[
            AudioTrack(kind="narration", path="a/n.wav", start=1.0, end=10.0),
            AudioTrack(kind="music", path="a/m.wav", start=0.0, end=10.0, gain_db=-2.0, duck=True),
        ],
    )


def test_mixed_inputs_are_files_then_stills() -> None:
    inputs = render_graph.plan_inputs(mixed(), ROOT)
    assert [m.index for m in inputs.files.values()] == [0, 1, 2]  # b.mp4, n.wav, m.wav
    assert inputs.files["a/b.mp4"].seek == 2.0 and inputs.files["a/b.mp4"].span == 3.0
    assert inputs.stills == {0: 3, 2: 4}
    assert inputs.silence is None
    assert "-loop" in inputs.args  # the blur still loops; the Ken Burns one is a single frame


def test_mixed_video_graph_shape() -> None:
    video, _, _ = graphs(mixed())
    assert video.startswith("[3:v]scale=2160:3840:force_original_aspect_ratio=increase,")
    assert "zoompan=z='1+(0.2)*on/119'" in video and ":d=120:s=1080x1920:fps=30" in video
    assert (
        "[0:v]trim=start=0.000,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect" in video
    )
    assert video.endswith("[p0][p1][p2]concat=n=3:v=1:a=0[v]")  # no overlay: no ass filter


def test_mixed_audio_graph_ducks_music_under_the_voice() -> None:
    _, audio, _ = graphs(mixed())
    joined = ";".join(audio.parts)
    assert "[1:a:0]atrim=start=0.000:duration=9.000,asetpts=PTS-STARTPTS," in joined
    assert "adelay=1000:all=1[a0]" in joined
    assert "volume=-2dB" in joined
    assert f"[bed][vsc]{render_graph.DUCK}[ducked]" in joined
    assert "amix=inputs=2:normalize=0:duration=longest[mixed]" in joined
    assert joined.endswith("[mixed]apad,atrim=duration=10.000[pre]")
    assert audio.pre == "[pre]" and not audio.silent


def test_no_audio_adds_silence() -> None:
    tl = Timeline(
        fps=30,
        duration_s=2.0,
        visual=[StillSegment(path="a/s.png", width=1080, height=1920, start=0.0, end=2.0)],
    )
    inputs = render_graph.plan_inputs(tl, ROOT)
    audio = render_graph.audio_graph(tl, inputs)
    assert inputs.silence == 1 and "anullsrc=r=48000:cl=stereo" in inputs.args
    assert (audio.pre, audio.silent) == ("[1:a]", True)


def test_short_side_is_the_largest_over_visual_media() -> None:
    assert render_graph.short_side(mixed()) == 1080


def _run_graph(
    tmp_path: Path, tl: Timeline, label: str, out: list[str], tail: str = "anull"
) -> str:
    inputs = render_graph.plan_inputs(tl, tmp_path)
    if label == "a":
        audio = render_graph.audio_graph(tl, inputs)
        graph = ";".join([*audio.parts, f"{audio.pre}{tail}[a]"])
    else:
        graph = render_graph.video_graph(tl, inputs, None)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-nostats", *inputs.args,
           "-filter_complex", graph, "-map", f"[{label}]", *out]  # fmt: skip
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stderr


@requires_ffmpeg
def test_ducked_music_keeps_playing_after_the_voice_ends(tmp_path: Path) -> None:
    # Review CP2 #1: sidechaincompress stops at its shorter input; the bed must not go silent.
    a = tmp_path / "a"
    a.mkdir()
    ffmpeg.run(["-f", "lavfi", "-i", "sine=f=1000:d=3:sample_rate=48000", str(a / "v.wav")])
    ffmpeg.run(["-f", "lavfi", "-i", "sine=f=110:d=10:sample_rate=48000", str(a / "m.wav")])
    ffmpeg.run(["-f", "lavfi", "-i", "color=size=64x64", "-frames:v", "1", str(a / "s.png")])
    tl = Timeline(
        fps=30,
        duration_s=10.0,
        visual=[StillSegment(path="a/s.png", width=1080, height=1920, start=0.0, end=10.0)],
        audio=[
            AudioTrack(kind="narration", path="a/v.wav", start=0.0, end=3.0),
            AudioTrack(kind="music", path="a/m.wav", start=0.0, end=10.0, duck=True),
        ],
    )
    tail = "atrim=start=5:end=8,volumedetect"
    log = _run_graph(tmp_path, tl, "a", ["-f", "null", "-"], tail=tail)
    mean = float(re.findall(r"mean_volume: (-?[0-9.]+) dB", log)[-1])
    assert mean > -40  # the undamped 110 Hz bed is about -21 dB; silence is about -91


@requires_ffmpeg
def test_ken_burns_segment_has_all_its_frames(tmp_path: Path) -> None:
    # Review CP2 #2: an fps filter after zoompan dropped the last frame (59 of 60).
    a = tmp_path / "a"
    a.mkdir()
    ffmpeg.run(["-f", "lavfi", "-i", "testsrc2=size=320x568", "-frames:v", "1", str(a / "s.png")])
    tl = Timeline(
        fps=30,
        duration_s=2.0,
        visual=[StillSegment(path="a/s.png", width=320, height=568, start=0.0, end=2.0,
                             ken_burns=KenBurns(zoom_to=1.1))],
    )  # fmt: skip
    log = _run_graph(tmp_path, tl, "v", ["-f", "null", "-"])  # the last frame= line counts
    frames = int(re.findall(r"frame=\s*(\d+)", log)[-1])
    assert frames == 60

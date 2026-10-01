"""A synthetic Timeline through the one renderer (06 §S4 action 5, spec §10, items 5 and 6): stills
(Ken Burns and blur fit), 25 fps b-roll, narration starting at 1 s, music ducked under it,
captions with the title card. 1080x1920, under 50 MB, -14 LUFS ±1."""

from pathlib import Path

import numpy as np
import pytest

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.models import (
    AssetSource,
    AudioTrack,
    KenBurns,
    RenderedVideo,
    StillSegment,
    Subtitles,
    Timeline,
    VideoSegment,
    Word,
)
from clipforge.stages import captions, render
from tests.conftest import requires_ffmpeg
from tests.stages.helpers import assert_vertical_clip, band_diff, gray_frame, make_ctx
from tests.stages.test_render import _integrated_lufs

pytestmark = requires_ffmpeg
RATE = 48_000


def make_assets(root: Path) -> None:
    a = root / "assets"
    a.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        ["-f", "lavfi", "-i", "testsrc2=size=1080x1920", "-frames:v", "1", str(a / "kb.png")]
    )
    ffmpeg.run(
        ["-f", "lavfi", "-i", "smptebars=size=640x480", "-frames:v", "1", str(a / "bars.png")]
    )
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=4",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(a / "broll.mp4"),
    ])  # fmt: skip
    # Narration: a 1 kHz tone, 1 s on / 1 s off, peaks near -8 dBFS (sine's default is -18).
    ffmpeg.run([
        "-f", "lavfi", "-i",
        "sine=f=1000:d=11:sample_rate=48000,volume='if(lt(mod(t,2),1),1,0)':eval=frame,volume=10dB",
        str(a / "narration.wav"),
    ])  # fmt: skip
    ffmpeg.run(["-f", "lavfi", "-i", "sine=f=110:d=12:sample_rate=48000,volume=-14dB",
                str(a / "music.wav")])  # fmt: skip
    words = [Word(text="SYNTHETIC", start=0.5, end=1.0), Word(text="TIMELINE", start=1.1, end=1.6)]
    ass = captions.build_ass(
        captions.chunk_words(words), title=captions.TitleCard(("ONE", "RENDERER"), 1, 3.0)
    )
    (a / "overlay.ass").write_text(ass)


KB = KenBurns(zoom_to=1.2, focus_from=(0.4, 0.5), focus_to=(0.6, 0.5))


def synthetic() -> Timeline:
    return Timeline(
        fps=30,
        duration_s=12.0,
        visual=[
            StillSegment(path="assets/kb.png", width=1080, height=1920, start=0.0, end=4.0,
                         ken_burns=KB),
            VideoSegment(kind="broll", path="assets/broll.mp4", width=1280, height=720,
                         in_s=0.5, start=4.0, end=7.0, fit="cover"),
            StillSegment(path="assets/bars.png", width=640, height=480, start=7.0, end=12.0,
                         fit="blur"),
        ],
        audio=[
            AudioTrack(kind="narration", path="assets/narration.wav", start=1.0, end=12.0),
            AudioTrack(kind="music", path="assets/music.wav", start=0.0, end=12.0,
                       gain_db=-2.0, duck=True),
        ],
        overlay=Subtitles(ass_path="assets/overlay.ass"),
        assets=[AssetSource(kind="generated", license="test-fixture", model="ffmpeg lavfi")],
    )  # fmt: skip


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, RenderedVideo]:
    root = tmp_path_factory.mktemp("timeline")
    make_assets(root)
    stored = render.run(make_ctx(root), synthetic(), Settings(_env_file=None, jobs_root=root))
    return root, stored.value


def test_meets_the_output_contract(rendered: tuple[Path, RenderedVideo]) -> None:
    _, video = rendered
    assert_vertical_clip(video.probe, expected_s=12.0)  # 1080x1920, h264+aac, A/V in sync
    assert abs(video.probe.fps - 30) < 0.01
    # No frame lost per segment (a dropped frame per still pulled later segments early).
    assert video.probe.video_duration_s is not None
    assert abs(video.probe.video_duration_s - 12.0) < 0.5 / 30


def test_is_normalized_to_minus_14_lufs_in_linear_mode(
    rendered: tuple[Path, RenderedVideo],
) -> None:
    root, video = rendered
    assert video.loudness.mode == "linear"
    assert abs(_integrated_lufs(root / video.video_path) - (-14.0)) <= 1.0


def test_music_ducks_under_the_narration(rendered: tuple[Path, RenderedVideo]) -> None:
    root, video = rendered
    raw = ffmpeg_pcm(root / video.video_path, "lowpass=f=300,lowpass=f=300")  # music band

    def rms(a: float, b: float) -> float:
        part = raw[int(a * RATE) : int(b * RATE)]
        return float(np.sqrt(np.mean(part**2)))

    # Narration is on at [1,2), [3,4), ...; ducking releases over 400 ms after each stop.
    on = np.mean([rms(t + 0.3, t + 0.9) for t in (1.0, 3.0, 5.0, 7.0, 9.0)])
    off = np.mean([rms(t + 0.5, t + 0.95) for t in (2.0, 4.0, 6.0, 8.0, 10.0)])
    assert 20 * np.log10(off / on) >= 6.0


def test_ken_burns_moves(rendered: tuple[Path, RenderedVideo]) -> None:
    root, video = rendered
    path = root / video.video_path
    assert band_diff(gray_frame(path, 0.2), gray_frame(path, 3.8), rows=(200, 1200)) > 1


def test_silent_timeline_still_has_an_audio_stream(tmp_path: Path) -> None:
    make_assets(tmp_path)
    tl = Timeline(
        fps=30,
        duration_s=2.0,
        visual=[StillSegment(path="assets/kb.png", width=1080, height=1920, start=0.0, end=2.0)],
    )
    video = render.run(make_ctx(tmp_path), tl, Settings(_env_file=None, jobs_root=tmp_path)).value
    assert video.loudness.mode == "silent"
    assert_vertical_clip(video.probe, expected_s=2.0)


def ffmpeg_pcm(path: Path, filters: str) -> np.ndarray:
    import subprocess

    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-af", filters, "-ac", "1", "-ar", str(RATE),
         "-f", "f32le", "-"], capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(out, dtype=np.float32)

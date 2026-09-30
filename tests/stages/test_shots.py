"""Camera cuts inside a clip (ADR-19)."""

import subprocess
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


@requires_ffmpeg
def test_cut_is_never_rounded_after_the_first_frame_of_the_new_shot(tmp_path: Path) -> None:
    # 29.97 fps, cut at frame 37 (1.2345667 s): rounding to 1.235 would leave that frame in the
    # previous shot, and render would show it with the previous crop for one frame.
    video = tmp_path / "ntsc.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30000/1001:d=1.2345667",
         "-f", "lavfi", "-i", "smptebars=s=320x180:r=30000/1001:d=1",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True,
    )  # fmt: skip
    [cut] = detect_cuts(video, 0.0, 2.2, threshold=0.2)
    assert cut <= 37 * 1001 / 30000 + 1e-9

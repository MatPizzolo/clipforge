from pathlib import Path

import pytest

from clipforge import ffmpeg
from clipforge.ffmpeg import FfmpegError, filter_path, media_info, probe_info
from tests.conftest import MediaFactory, requires_ffmpeg


@requires_ffmpeg
def test_media_info_landscape(media: MediaFactory) -> None:
    info = media_info(media(width=1920, height=1080, container="mkv"))
    assert (info.width, info.height, info.rotation) == (1920, 1080, 0)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")
    assert info.duration_s == pytest.approx(3.0, abs=0.1)
    assert info.fps == pytest.approx(30.0)


@requires_ffmpeg
def test_media_info_reports_display_size_for_rotated_video(
    tmp_path: Path, media: MediaFactory
) -> None:
    rotated = tmp_path / "rotated.mp4"
    ffmpeg.run(["-display_rotation:v:0", "90", "-i", str(media()), "-c", "copy", str(rotated)])
    info = media_info(rotated)
    assert info.rotation in (90, 270)
    assert (info.width, info.height) == (180, 320)


@requires_ffmpeg
def test_media_info_without_audio(media: MediaFactory) -> None:
    assert media_info(media(audio=False)).audio_codec is None


@requires_ffmpeg
def test_probe_info_counts_streams(media: MediaFactory) -> None:
    info = probe_info(media())
    assert (info.n_video_streams, info.n_audio_streams) == (1, 1)
    assert (info.width, info.height, info.pix_fmt) == (320, 180, "yuv420p")
    assert info.video_duration_s is not None and info.audio_duration_s is not None
    assert info.size_bytes > 0


@requires_ffmpeg
def test_errors_carry_stderr(tmp_path: Path) -> None:
    not_media = tmp_path / "notes.txt"
    not_media.write_text("hello")
    with pytest.raises(FfmpegError) as excinfo:
        media_info(not_media)
    assert excinfo.value.stderr_tail
    with pytest.raises(FfmpegError):
        ffmpeg.run(["-i", str(tmp_path / "missing.mp4"), str(tmp_path / "out.mp4")])


def test_filter_path_rejects_characters_that_need_escaping() -> None:
    assert (
        filter_path(Path("/jobs/cache/captions/abc/clip.ass"))
        == "/jobs/cache/captions/abc/clip.ass"
    )
    for bad in ("/tmp/a:b.ass", "/tmp/it's.ass", "/tmp/a,b.ass", "/tmp/[x].ass", "/tmp/a;b.ass"):
        with pytest.raises(ValueError):
            filter_path(Path(bad))

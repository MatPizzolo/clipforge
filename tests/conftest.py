"""Shared fixtures: synthetic media (generated with ffmpeg at test time) and fixture files."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from clipforge.models import Transcript
from tests.builders import build_long_transcript
from tests.dbfixture import db, pg_url  # noqa: F401  (pytest fixtures)
from tests.pipeline.harness import harness  # noqa: F401  (pytest fixture, used across tests/)

FIXTURES = Path(__file__).parent / "fixtures"
TALKING_HEAD = FIXTURES / "talking_head_10s.mp4"

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


@dataclass(frozen=True)
class MediaSpec:
    """Synthetic test video: testsrc2 picture + 440 Hz sine audio."""

    width: int = 320
    height: int = 180
    duration_s: float = 3.0
    fps: int = 30
    audio: bool = True
    container: str = "mp4"  # "mp4" | "mkv"
    vcodec: str = "libx264"  # "libx264" | "mpeg4" (forces a transcode in ingest)
    vfr: bool = False  # drop 2 of every 3 frames with variable timestamps

    @property
    def filename(self) -> str:
        parts = [
            f"{self.width}x{self.height}",
            f"{self.duration_s:g}s",
            f"{self.fps}fps",
            self.vcodec,
            "audio" if self.audio else "noaudio",
            "vfr" if self.vfr else "cfr",
        ]
        return "_".join(parts) + f".{self.container}"


def make_media(path: Path, spec: MediaSpec) -> Path:
    size = f"{spec.width}x{spec.height}"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={spec.fps}:duration={spec.duration_s}",
    ]  # fmt: skip
    if spec.audio:
        cmd += [
            "-f", "lavfi", "-i",
            f"sine=frequency=440:sample_rate=48000:duration={spec.duration_s}",
        ]  # fmt: skip
    if spec.vfr:
        cmd += ["-vf", r"select=not(mod(n\,3))", "-fps_mode", "vfr"]
    cmd += ["-c:v", spec.vcodec, "-pix_fmt", "yuv420p"]
    if spec.vcodec == "libx264":
        cmd += ["-preset", "ultrafast"]
    if spec.audio:
        cmd += ["-c:a", "aac", "-b:a", "64k"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)
    return path


MediaFactory = Callable[..., Path]


@pytest.fixture(scope="session")
def media(tmp_path_factory: pytest.TempPathFactory) -> MediaFactory:
    """`media(width=1920, height=1080, container="mkv")` -> path to a cached synthetic video."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    root = tmp_path_factory.mktemp("media")

    def factory(**kwargs: object) -> Path:
        spec = MediaSpec(**kwargs)  # type: ignore[arg-type]
        path = root / spec.filename
        if not path.exists():
            make_media(path, spec)
        return path

    return factory


@pytest.fixture
def talking_head() -> Path:
    """Real 10 s speech clip, 480x854 portrait (see tests/fixtures/README.md)."""
    return TALKING_HEAD


TWO_SHOT_FACE_X = (40, 900)  # left edge of the pasted person in each shot; 338 px wide


@pytest.fixture(scope="session")
def two_shot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """1280x720, 4 s: the real talking-head face at the left (0-2 s), then at the right
    (2-4 s) over a different background, so there's one camera cut at 2.0 s."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("two_shot") / "two_shot.mp4"
    left, right = TWO_SHOT_FACE_X
    graph = (
        "[0:v][1:v]concat=n=2:v=1:a=0[bg];"
        "[2:v]trim=0:4,setpts=PTS-STARTPTS,scale=-2:600[f];"
        f"[bg][f]overlay=x='if(lt(t,2),{left},{right})':y=60:shortest=1[v]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x404040:s=1280x720:r=30:d=2",
        "-f", "lavfi", "-i", "color=c=0x203060:s=1280x720:r=30:d=2",
        "-i", str(TALKING_HEAD),
        "-f", "lavfi", "-i", "sine=f=440:d=4",
        "-filter_complex", graph, "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-t", "4", str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.fixture
def short_transcript() -> Transcript:
    return Transcript.model_validate_json((FIXTURES / "transcript_short.json").read_text())


@pytest.fixture(scope="session")
def long_transcript() -> Transcript:
    return build_long_transcript()


def llm_fixture(name: str) -> str:
    """Raw text of a canned LLM response in tests/fixtures/."""
    return (FIXTURES / name).read_text()

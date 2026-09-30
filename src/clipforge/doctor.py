"""Environment checks for the local machine (ffmpeg, libass, encoders). Modal-free.

The GPU side of `doctor` lives in app.py; `uv run modal run src/clipforge/app.py::doctor`
runs both.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_AUDIO_SOURCE = Path("tests/fixtures/talking_head_10s.mp4")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _nvenc_works() -> tuple[bool, str]:
    """A 1-frame h264_nvenc encode; listing the encoder doesn't mean a GPU is usable."""
    result = _run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=black:size=256x256:duration=0.1",
            "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
        ]
    )  # fmt: skip
    if result.returncode == 0:
        return True, "test encode OK"
    first_line = (result.stderr.strip().splitlines() or ["failed"])[0]
    return False, f"not usable ({first_line[:80]}); render uses libx264"


def local_checks() -> list[Check]:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return [Check("ffmpeg", False, "ffmpeg/ffprobe not on PATH (sudo apt install ffmpeg)")]

    version = _run(["ffmpeg", "-hide_banner", "-version"]).stdout.splitlines()[0]
    filters = _run(["ffmpeg", "-hide_banner", "-filters"]).stdout
    encoders = _run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    has_ass = any(line.split()[1:2] == ["ass"] for line in filters.splitlines() if line.strip())
    nvenc_ok, nvenc_detail = _nvenc_works() if "h264_nvenc" in encoders else (False, "absent")

    return [
        Check("ffmpeg", True, version),
        Check("libass (ass filter)", has_ass, "present" if has_ass else "missing: no captions"),
        Check("libx264", "libx264" in encoders, "present" if "libx264" in encoders else "missing"),
        Check("h264_nvenc", nvenc_ok, nvenc_detail, required=False),
    ]


def audio_wav_bytes(source: Path = DEFAULT_AUDIO_SOURCE) -> bytes:
    """16 kHz mono WAV of `source`, as sent to the GPU transcriber.

    Written to a temp file, not a pipe: over a pipe ffmpeg can't seek back to fill in the
    WAV size header, and some decoders reject the placeholder.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(source),
             "-vn", "-ac", "1", "-ar", "16000", str(out)],
            capture_output=True,
            check=True,
        )  # fmt: skip
        return out.read_bytes()


def format_checks(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        mark = "OK  " if check.ok else ("FAIL" if check.required else "--  ")
        lines.append(f"[{mark}] {check.name}: {check.detail}")
    return "\n".join(lines)

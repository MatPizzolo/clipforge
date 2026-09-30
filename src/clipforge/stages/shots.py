"""Camera cuts inside a clip (ADR-19), from ffmpeg's scene score. Modal-free.

Only the clip's own range is read, scaled to 320 px wide, without audio (rule 6)."""

from __future__ import annotations

import itertools
import math
import re
import subprocess
from pathlib import Path

from clipforge.ffmpeg import FfmpegError

MIN_SHOT_S = 0.5
DETECT_WIDTH = 320
_PTS = re.compile(r"pts_time:(-?[0-9.]+)")


def detect_cuts(video: Path, start: float, end: float, threshold: float) -> list[float]:
    """Clip-relative times (s) where a new shot starts, ascending, inside (0, end - start)."""
    duration = end - start
    vf = f"scale={DETECT_WIDTH}:-2,select='gt(scene,{threshold})',metadata=print"
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(video),
        "-an", "-vf", vf, "-f", "null", "-",
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if result.returncode != 0:
        raise FfmpegError("ffmpeg", result.stderr)
    # Floor, never round: a cut rounded up past the new shot's first frame would leave that
    # frame in the previous segment (one frame with the previous crop).
    times = sorted({math.floor(float(t) * 1000) / 1000 for t in _PTS.findall(result.stderr)})
    return [t for t in times if 0.0 < t < duration]


def segments_from_cuts(
    cuts: list[float], duration: float, min_len: float = MIN_SHOT_S
) -> list[tuple[float, float]]:
    """Contiguous (start, end) shots covering [0, duration]. A shot shorter than `min_len`
    joins the one before it (the first joins the one after), so a false cut can't flash."""
    bounds = [0.0, *[c for c in cuts if 0.0 < c < duration], duration]
    segments: list[tuple[float, float]] = []
    for a, b in itertools.pairwise(bounds):
        if segments and b - a < min_len:
            segments[-1] = (segments[-1][0], b)
        else:
            segments.append((a, b))
    if len(segments) > 1 and segments[0][1] - segments[0][0] < min_len:
        segments[:2] = [(segments[0][0], segments[1][1])]
    return segments

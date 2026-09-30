"""Thin wrappers around the ffmpeg and ffprobe binaries."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from clipforge.models import ProbeInfo

Rotation = Literal[0, 90, 180, 270]
_ROTATIONS: dict[int, Rotation] = {0: 0, 90: 90, 180: 180, 270: 270}
_UNSAFE_IN_FILTERS = set(":',;[]\\")


class FfmpegError(RuntimeError):
    """ffmpeg or ffprobe exited non-zero; `stderr_tail` holds the last lines of its output."""

    def __init__(self, tool: str, stderr: str) -> None:
        self.stderr_tail = "\n".join(stderr.strip().splitlines()[-5:])
        super().__init__(f"{tool} failed: {self.stderr_tail}")


def run(args: list[str], timeout: float = 900) -> str:
    """Run ffmpeg with `args`; returns its stderr (warnings) on success."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise FfmpegError("ffmpeg", result.stderr)
    return result.stderr


def probe(path: Path) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise FfmpegError("ffprobe", result.stderr or "not a media file")
    data: dict[str, Any] = json.loads(result.stdout)
    return data


def _rate(value: str | None) -> float:
    if not value:
        return 0.0
    num, _, den = value.partition("/")
    denominator = float(den or 1)
    return float(num) / denominator if denominator else 0.0


def _duration(stream: dict[str, Any] | None) -> float | None:
    if stream is None or not stream.get("duration"):
        return None
    return float(stream["duration"])


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    width: int  # display width, after rotation
    height: int  # display height, after rotation
    rotation: Rotation
    fps: float
    video_codec: str | None
    audio_codec: str | None
    format_name: str


def media_info(path: Path) -> MediaInfo:
    data = probe(path)
    streams: list[dict[str, Any]] = data.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    width = height = 0
    fps = 0.0
    rotation: Rotation = 0
    if video is not None:
        raw = next(
            (sd["rotation"] for sd in video.get("side_data_list", []) if "rotation" in sd),
            video.get("tags", {}).get("rotate", 0),
        )
        rotation = _ROTATIONS[round(int(float(raw)) % 360 / 90) * 90 % 360]
        width, height = int(video["width"]), int(video["height"])
        if rotation in (90, 270):
            width, height = height, width
        fps = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    fmt: dict[str, Any] = data.get("format", {})
    return MediaInfo(
        duration_s=float(fmt.get("duration") or 0.0),
        width=width,
        height=height,
        rotation=rotation,
        fps=fps,
        video_codec=video.get("codec_name") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
        format_name=str(fmt.get("format_name", "")),
    )


def probe_info(path: Path) -> ProbeInfo:
    """Output properties the tests and the pipeline check (1080x1920, streams, durations)."""
    data = probe(path)
    streams: list[dict[str, Any]] = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    video = videos[0] if videos else {}
    audio = audios[0] if audios else None
    fmt: dict[str, Any] = data.get("format", {})
    return ProbeInfo(
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        duration_s=float(fmt.get("duration") or 0.0),
        video_duration_s=_duration(video) if videos else None,
        audio_duration_s=_duration(audio),
        fps=_rate(video.get("avg_frame_rate")),
        video_codec=str(video.get("codec_name", "")),
        pix_fmt=str(video.get("pix_fmt", "")),
        audio_codec=audio.get("codec_name") if audio else None,
        n_video_streams=len(videos),
        n_audio_streams=len(audios),
        size_bytes=int(fmt.get("size") or path.stat().st_size),
    )


def filter_path(path: Path) -> str:
    """A path for use inside a filtergraph. Our paths are generated (cache keys, fonts dir),
    so reject rather than escape the characters filtergraphs treat specially."""
    text = path.as_posix()
    if _UNSAFE_IN_FILTERS & set(text):
        raise ValueError(f"path not usable in an ffmpeg filter: {text!r}")
    return text

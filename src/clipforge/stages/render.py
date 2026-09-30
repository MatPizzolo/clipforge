"""Render: one ffmpeg encode per clip. Accurate seek, crop or blur-fit to 1080x1920, burn in
the ASS captions, then libx264 + AAC with a bitrate cap that keeps clips under Telegram's
50 MB limit (ADR-13). CPU only (ADR-10)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.ffmpeg import filter_path
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import (
    CaptionFiles,
    ClipSpec,
    CropBox,
    CropTrack,
    RenderedClip,
    StageCost,
    StageName,
)
from clipforge.pipeline.errors import PermanentError

log = logging.getLogger(__name__)

STAGE_VERSION = "3"  # 3: loudnorm -14 LUFS, bitrate capped by source height (ADR-20)
MAX_VIDEO_BPS = 8_000_000
MIN_VIDEO_BPS = 500_000
AUDIO_BPS = 128_000
TARGET_BYTES = 45 * 1024 * 1024
TELEGRAM_LIMIT_BYTES = 50 * 1024 * 1024
MAX_FPS = 60


LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"  # EBU R128, the social-platform norm (ADR-20)
HEIGHT_CAPS = ((480, 3_000_000), (720, 5_000_000))  # source height -> max video b/s


def video_bitrate(duration_s: float, source_height: int = 1080) -> int:
    budget = TARGET_BYTES * 8 / duration_s - AUDIO_BPS
    cap = next((bps for h, bps in HEIGHT_CAPS if source_height <= h), MAX_VIDEO_BPS)
    return int(max(MIN_VIDEO_BPS, min(cap, budget)))


def bitrate_for(spec: ClipSpec) -> int:
    """The clip's video bitrate. The resolution cap uses the source's short side, which is
    what "480p/720p" means: a vertical 720x1280 phone video is 720p (review, ADR-20)."""
    short_side = min(spec.source.width, spec.source.height)
    return video_bitrate(spec.duration_s, short_side)


def _crop(box: CropBox, w: int, h: int) -> str:
    return f"crop={box.w}:{box.h}:{box.x}:{box.y},scale={w}:{h}:flags=lanczos,setsar=1"


def _blur(src: str, dst: str, w: int, h: int, tag: str) -> str:
    """Fit `src` inside a blurred, zoomed copy of itself (blurred small: much cheaper)."""
    bw, bh = w // 4, h // 4
    return (
        f"[{src}]split=2[{tag}bg][{tag}fg];"
        f"[{tag}bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"boxblur=10:1,scale={w}:{h}[{tag}bgb];"
        f"[{tag}fg]scale={w}:{h}:force_original_aspect_ratio=decrease[{tag}fgs];"
        f"[{tag}bgb][{tag}fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[{dst}]"
    )


def filter_graph(track: CropTrack, ass: Path, fonts_dir: Path) -> str:
    subs = f"ass=filename={filter_path(ass)}:fontsdir={filter_path(fonts_dir)}"
    w, h = track.out_width, track.out_height
    if track.mode == "center":
        if track.box is None:
            raise ValueError("center crop without a box")
        return f"[0:v]{_crop(track.box, w, h)},{subs}[v]"
    if track.mode == "blur_fallback":
        return _blur("0:v", "fit", w, h, "b") + f";[fit]{subs}[v]"
    n = len(track.segments)
    parts = ["[0:v]split=" + str(n) + "".join(f"[s{i}]" for i in range(n))]
    for i, segment in enumerate(track.segments):
        end = f":end={segment.end:.3f}" if i < n - 1 else ""
        trim = f"trim=start={segment.start:.3f}{end},setpts=PTS-STARTPTS"
        if segment.box is not None:
            parts.append(f"[s{i}]{trim},{_crop(segment.box, w, h)}[p{i}]")
        else:
            parts.append(f"[s{i}]{trim}[t{i}];" + _blur(f"t{i}", f"p{i}", w, h, f"b{i}"))
    concat = "".join(f"[p{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,{subs}[v]"
    return ";".join([*parts, concat])


def run(
    ctx: JobContext,
    spec: ClipSpec,
    track: CropTrack,
    captions: CaptionFiles,
    settings: Settings,
) -> Stored[RenderedClip]:
    box = track.box.model_dump() if track.box is not None else None
    key = cache_key(
        "render",
        STAGE_VERSION,
        [],
        {
            "source_hash": spec.source.source_hash,
            "start": f"{spec.start:.3f}",
            "end": f"{spec.end:.3f}",
            "mode": track.mode,
            "box": json.dumps(box, sort_keys=True),
            "captions": captions.ass_path,  # a cache path: changes when the captions change
            "segments": json.dumps(
                [s.model_dump(mode="json") for s in track.segments], sort_keys=True
            ),
        },
    )

    def compute(out_dir: Path) -> RenderedClip:
        started = time.monotonic()
        out = out_dir / "clip.mp4"
        bitrate = bitrate_for(spec)
        fps = min(MAX_FPS, round(spec.source.fps) or 30)
        graph = filter_graph(track, ctx.path(captions.ass_path), settings.fonts_dir)
        stderr = ffmpeg.run(
            [
                "-ss", f"{spec.start:.3f}", "-i", str(ctx.path(spec.source.video_path)),
                "-t", f"{spec.duration_s:.3f}",
                "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-maxrate", str(bitrate), "-bufsize", str(bitrate * 2),
                "-pix_fmt", "yuv420p", "-r", str(fps),
                "-af", LOUDNORM,
                "-c:a", "aac", "-b:a", str(AUDIO_BPS), "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(out),
            ]
        )  # fmt: skip
        if "fontselect" in stderr or "Glyph" in stderr:
            log.warning("caption font problem while rendering %s: %s", spec.clip_id, stderr[-300:])
        probe = ffmpeg.probe_info(out)
        if probe.size_bytes > TELEGRAM_LIMIT_BYTES:
            raise PermanentError(f"{spec.clip_id} rendered larger than Telegram's 50 MB limit")
        ctx.record_cost(StageCost(stage=StageName.RENDER, wall_s=time.monotonic() - started))
        return RenderedClip(
            clip_id=spec.clip_id,
            spec=spec,
            video_path=ctx.rel(out),
            srt_path=captions.srt_path,
            encoder="libx264",
            probe=probe,
        )

    return cached_stage(ctx, StageName.RENDER, key, RenderedClip, compute, clip_id=spec.clip_id)

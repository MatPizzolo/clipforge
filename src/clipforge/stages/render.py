"""Render (ADR-31): one ffmpeg encode per Timeline. Inputs seeked accurately, visual
segments framed to 1080x1920 and joined, the ASS overlay burned in, audio tracks mixed
(music ducked under the voice) and normalized in two passes (proposed ADR-47), then
libx264 + AAC with a bitrate cap that keeps every video under Telegram's 50 MB (ADR-13).
CPU only (ADR-10)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import (
    Loudness,
    RenderedVideo,
    StageCost,
    StageName,
    Timeline,
    VideoSegment,
)
from clipforge.pipeline.errors import PermanentError
from clipforge.stages import loudness, render_graph

log = logging.getLogger(__name__)

STAGE_VERSION = "4"  # 4: Timeline input, two-pass loudness (ADR-31, log #341)
MAX_VIDEO_BPS = 8_000_000
MIN_VIDEO_BPS = 500_000
AUDIO_BPS = 128_000
TARGET_BYTES = 45 * 1024 * 1024
TELEGRAM_LIMIT_BYTES = 50 * 1024 * 1024
HEIGHT_CAPS = ((480, 3_000_000), (720, 5_000_000))  # source short side -> max video b/s
SHORT_VIDEO_S = 0.1  # tolerated video shortfall beyond one frame (stream rounding)


def video_bitrate(duration_s: float, source_height: int = 1080) -> int:
    budget = TARGET_BYTES * 8 / duration_s - AUDIO_BPS
    cap = next((bps for h, bps in HEIGHT_CAPS if source_height <= h), MAX_VIDEO_BPS)
    return int(max(MIN_VIDEO_BPS, min(cap, budget)))


def bitrate_for(tl: Timeline) -> int:
    """By the largest short side among the visual media: "720p" means the short side, so a
    vertical 720x1280 phone video is 720p (ADR-20)."""
    return video_bitrate(tl.duration_s, render_graph.short_side(tl))


def key(tl: Timeline) -> str:
    """The Timeline without what doesn't change the output (ADR-8): `assets` (licensing,
    #342), the media `path` where a `media_hash` identifies the content (a clip's path holds
    the ingest key, which follows the URL, not the bytes), and the overlay's `srt_path`."""
    data = tl.model_dump(mode="json", exclude={"assets"})
    for media in [*data["visual"], *data["audio"]]:
        if media.get("media_hash"):
            del media["path"]
    if data["overlay"] is not None:
        del data["overlay"]["srt_path"]
    return cache_key("render", STAGE_VERSION, [], {"timeline": json.dumps(data, sort_keys=True)})


def _loudness(
    inputs: render_graph.Inputs, audio: render_graph.AudioGraph, target: float, name: str
) -> tuple[str, Loudness]:
    """The loudness filter for the encode, and what it is based on."""
    if audio.silent:
        return "anull", Loudness(mode="silent")
    graph = ";".join([*audio.parts, f"{audio.pre}{loudness.measure_filter(target)}[m]"])
    stderr = ffmpeg.run(
        [*inputs.args, "-filter_complex", graph, "-map", "[m]", "-vn", "-f", "null", "-"],
        loglevel="info",
    )  # an ffmpeg failure here is transient, like the encode's
    try:
        measured = loudness.parse(stderr)
    except ValueError as exc:
        log.warning("loudness not measured for %s (%s); single pass", name, exc)
        return loudness.single_pass(target), Loudness(mode="single_pass")
    if measured is None:
        log.warning("audio is silent for %s; single-pass loudness", name)
        return loudness.single_pass(target), Loudness(mode="single_pass")
    return loudness.second_pass(measured, target), Loudness(
        input_i=measured.i,
        input_tp=measured.tp,
        input_lra=measured.lra,
        mode=loudness.mode(measured, target),
    )


def run(
    ctx: JobContext, tl: Timeline, settings: Settings, clip_id: str | None = None
) -> Stored[RenderedVideo]:
    name = clip_id or "video"

    def compute(out_dir: Path) -> RenderedVideo:
        started = time.monotonic()
        out = out_dir / "clip.mp4"
        (out_dir / "timeline.json").write_text(tl.model_dump_json(indent=2))
        inputs = render_graph.plan_inputs(tl, ctx.root)
        subs = render_graph.subtitles(tl, ctx.root, settings.fonts_dir)
        video = render_graph.video_graph(tl, inputs, subs)
        audio = render_graph.audio_graph(tl, inputs)
        norm, measured = _loudness(inputs, audio, tl.loudness_lufs, name)
        graph = ";".join([video, *audio.parts, f"{audio.pre}{norm}[a]"])
        bitrate = bitrate_for(tl)
        stderr = ffmpeg.run(
            [
                *inputs.args,
                "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                "-t", f"{tl.duration_s:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-maxrate", str(bitrate), "-bufsize", str(bitrate * 2),
                "-pix_fmt", "yuv420p", "-r", str(tl.fps),
                "-c:a", "aac", "-b:a", str(AUDIO_BPS), "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(out),
            ]
        )  # fmt: skip
        if "fontselect" in stderr or "Glyph" in stderr:
            log.warning("caption font problem while rendering %s: %s", name, stderr[-300:])
        probe = ffmpeg.probe_info(out)
        shown = probe.video_duration_s or probe.duration_s
        produced = any(
            not (isinstance(seg, VideoSegment) and seg.kind == "source") for seg in tl.visual
        )
        if produced and tl.duration_s - shown > SHORT_VIDEO_S + 1 / tl.fps:
            # Audio is padded to duration_s, video isn't: produced media shorter than its
            # segments would ship sound under no picture (review CP3 #1, log #345). A
            # producer bug, never retried. Source-only (clip) Timelines keep v3's behavior:
            # a recording whose picture stops before its sound still ships (review I-2).
            raise PermanentError(
                f"{name}: video ends at {shown:.2f} s of a {tl.duration_s:.2f} s timeline"
            )
        if probe.size_bytes > TELEGRAM_LIMIT_BYTES:
            raise PermanentError(f"{name} rendered larger than Telegram's 50 MB limit")
        ctx.record_cost(StageCost(stage=StageName.RENDER, wall_s=time.monotonic() - started))
        return RenderedVideo(
            video_path=ctx.rel(out), encoder="libx264", probe=probe, loudness=measured
        )

    return cached_stage(ctx, StageName.RENDER, key(tl), RenderedVideo, compute, clip_id=clip_id)

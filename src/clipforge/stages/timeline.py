"""Timelines for producers (ADR-31). Clips: one source video cut into the reframe shots,
the source audio, and the captions overlay (which carries the hook title card, #340).
Pure: no ffmpeg, no files."""

from __future__ import annotations

from clipforge.models import (
    AssetSource,
    AudioTrack,
    CaptionFiles,
    ClipSpec,
    CropBox,
    CropTrack,
    Permission,
    Subtitles,
    Timeline,
    VideoSegment,
)

MAX_FPS = 60


def clip_fps(spec: ClipSpec) -> int:
    """The source's frame rate, rounded, at most 60; 30 when the source has none."""
    return min(MAX_FPS, round(spec.source.fps) or 30)


def for_clip(
    spec: ClipSpec,
    track: CropTrack,
    captions: CaptionFiles,
    permission: Permission,
    credit: str | None = None,
) -> Timeline:
    source = spec.source
    duration = spec.duration_s

    def shot(start: float, end: float, box: CropBox | None) -> VideoSegment:
        return VideoSegment(
            kind="source",
            path=source.video_path,
            media_hash=source.source_hash,
            width=source.width,
            height=source.height,
            in_s=spec.start + start,
            start=start,
            end=end,
            fit="crop" if box is not None else "blur",
            box=box,
        )

    if track.mode == "tracked":
        last = len(track.segments) - 1
        visual = [
            shot(seg.start, duration if i == last else seg.end, seg.box)
            for i, seg in enumerate(track.segments)
        ]
    else:  # "center" carries a box; "blur_fallback" doesn't
        visual = [shot(0.0, duration, track.box)]
    return Timeline(
        width=track.out_width,
        height=track.out_height,
        fps=clip_fps(spec),
        duration_s=duration,
        visual=visual,
        audio=[
            AudioTrack(
                kind="source",
                path=source.video_path,
                media_hash=source.source_hash,
                in_s=spec.start,
                start=0.0,
                end=duration,
            )
        ],
        overlay=Subtitles(ass_path=captions.ass_path, srt_path=captions.srt_path),
        assets=[AssetSource(kind="source_video", license=permission.value, attribution=credit)],
    )

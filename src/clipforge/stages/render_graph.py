"""ffmpeg inputs and filtergraphs for a Timeline (ADR-31, spec §4). Pure: builds strings,
runs nothing. A clip Timeline produces exactly v3's video graph (tests pin the strings)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clipforge.ffmpeg import filter_path
from clipforge.models import CropBox, KenBurns, StillSegment, Timeline, VideoSegment

SAMPLE_RATE = 48_000
EPS = 1e-3
DUCK = "sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400"


@dataclass(frozen=True)
class MediaInput:
    index: int  # ffmpeg input number
    path: str  # contract path
    seek: float  # media time the input starts at (-ss)
    span: float  # seconds read from it (-t)


@dataclass(frozen=True)
class Inputs:
    """Input order: one per media file (video or audio, first use first), then one per
    still, then the silence source when the Timeline has no audio."""

    args: list[str]
    files: dict[str, MediaInput]
    stills: dict[int, int]  # visual segment index -> input index
    silence: int | None


@dataclass(frozen=True)
class AudioGraph:
    parts: list[str]  # filter chains, all ending before loudness
    pre: str  # the label loudness reads, e.g. "[0:a:0]" or "[pre]"
    silent: bool


def plan_inputs(tl: Timeline, root: Path) -> Inputs:
    uses: dict[str, list[tuple[float, float]]] = {}
    for seg in tl.visual:
        if isinstance(seg, VideoSegment):
            uses.setdefault(seg.path, []).append((seg.in_s, seg.in_s + seg.end - seg.start))
    for track in tl.audio:
        uses.setdefault(track.path, []).append((track.in_s, track.in_s + track.end - track.start))
    args: list[str] = []
    files: dict[str, MediaInput] = {}
    for path, ranges in uses.items():
        seek = min(a for a, _ in ranges)
        span = max(b for _, b in ranges) - seek
        files[path] = MediaInput(len(files), path, seek, span)
        args += ["-ss", f"{seek:.3f}", "-t", f"{span:.3f}", "-i", str(root / path)]
    stills: dict[int, int] = {}
    count = len(files)
    for i, seg in enumerate(tl.visual):
        if isinstance(seg, StillSegment):
            stills[i] = count
            count += 1
            if seg.ken_burns is None:
                held = f"{seg.end - seg.start:.3f}"
                args += ["-loop", "1", "-framerate", str(tl.fps), "-t", held]
                args += ["-i", str(root / seg.path)]
            else:  # one frame; zoompan makes the segment's frames from it
                args += ["-i", str(root / seg.path)]
    silence = None
    if not tl.audio:
        silence = count
        args += ["-f", "lavfi", "-t", f"{tl.duration_s:.3f}",
                 "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo"]  # fmt: skip
    return Inputs(args, files, stills, silence)


def subtitles(tl: Timeline, root: Path, fonts_dir: Path) -> str | None:
    if tl.overlay is None:
        return None
    ass = filter_path(root / tl.overlay.ass_path)
    return f"ass=filename={ass}:fontsdir={filter_path(fonts_dir)}"


def short_side(tl: Timeline) -> int:
    """The bitrate cap's "p": the largest short side over the visual media (ADR-20)."""
    return max(min(seg.width, seg.height) for seg in tl.visual)


def _crop(box: CropBox, w: int, h: int) -> str:
    return f"crop={box.w}:{box.h}:{box.x}:{box.y},scale={w}:{h}:flags=lanczos,setsar=1"


def _cover(w: int, h: int) -> str:
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


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


def _frame(seg: VideoSegment, w: int, h: int) -> str:
    """crop or cover; blur is a graph of its own (_blur)."""
    if seg.fit == "crop":
        assert seg.box is not None  # the contract guarantees it
        return _crop(seg.box, w, h)
    return _cover(w, h)


def _whole(seg: VideoSegment, media: MediaInput) -> bool:
    return abs(seg.in_s - media.seek) < EPS and seg.end - seg.start >= media.span - EPS


def _ken_burns(kb: KenBurns, frames: int, w: int, h: int, fps: int) -> str:
    d1 = max(1, frames - 1)

    def lerp(a: float, b: float) -> str:
        return f"{a:g}+({b - a:g})*on/{d1}"

    fx = f"({lerp(kb.focus_from[0], kb.focus_to[0])})"
    fy = f"({lerp(kb.focus_from[1], kb.focus_to[1])})"
    x = f"max(0,min(iw-iw/zoom,iw*{fx}-iw/zoom/2))"
    y = f"max(0,min(ih-ih/zoom,ih*{fy}-ih/zoom/2))"
    return (
        f"scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,crop={2 * w}:{2 * h},"
        f"zoompan=z='{lerp(kb.zoom_from, kb.zoom_to)}':x='{x}':y='{y}'"
        f":d={frames}:s={w}x{h}:fps={fps},setsar=1"
    )


def _still(seg: StillSegment, k: int, i: int, tl: Timeline) -> str:
    w, h = tl.width, tl.height
    # The input (-framerate) or zoompan already sets the rate; an fps filter here would drop
    # each still's last frame (found at review CP2 and Task 6).
    tail = "format=yuv420p"
    if seg.ken_burns is not None:
        frames = max(1, round((seg.end - seg.start) * tl.fps))
        return f"[{k}:v]{_ken_burns(seg.ken_burns, frames, w, h, tl.fps)},{tail}[p{i}]"
    if seg.fit == "blur":
        return _blur(f"{k}:v", f"q{i}", w, h, f"b{i}") + f";[q{i}]{tail}[p{i}]"
    return f"[{k}:v]{_cover(w, h)},{tail}[p{i}]"


def _video(seg: VideoSegment, src: str, media: MediaInput, i: int, w: int, h: int) -> str:
    rel = seg.in_s - media.seek
    rel_end = rel + seg.end - seg.start
    end = f":end={rel_end:.3f}" if rel_end < media.span - EPS else ""  # to the end: open
    trim = f"trim=start={rel:.3f}{end},setpts=PTS-STARTPTS"
    if seg.fit == "blur":
        return f"[{src}]{trim}[t{i}];" + _blur(f"t{i}", f"p{i}", w, h, f"b{i}")
    return f"[{src}]{trim},{_frame(seg, w, h)}[p{i}]"


def video_graph(tl: Timeline, inputs: Inputs, subs: str | None) -> str:
    w, h = tl.width, tl.height
    tail = f",{subs}" if subs else ""
    only = tl.visual[0] if len(tl.visual) == 1 else None
    if isinstance(only, VideoSegment) and _whole(only, inputs.files[only.path]):
        src = f"{inputs.files[only.path].index}:v"  # v3's "center" and "blur_fallback" forms
        if only.fit == "blur":
            if subs is None:
                return _blur(src, "v", w, h, "b")
            return _blur(src, "fit", w, h, "b") + f";[fit]{subs}[v]"
        return f"[{src}]{_frame(only, w, h)}{tail}[v]"
    users: dict[str, list[int]] = {}
    for i, seg in enumerate(tl.visual):
        if isinstance(seg, VideoSegment):
            users.setdefault(seg.path, []).append(i)
    parts: list[str] = []
    label: dict[int, str] = {}
    for path, indices in users.items():
        src = f"{inputs.files[path].index}:v"
        if len(indices) == 1:
            label[indices[0]] = src
            continue
        parts.append(f"[{src}]split={len(indices)}" + "".join(f"[s{i}]" for i in indices))
        label.update({i: f"s{i}" for i in indices})
    for i, seg in enumerate(tl.visual):
        if isinstance(seg, VideoSegment):
            parts.append(_video(seg, label[i], inputs.files[seg.path], i, w, h))
        else:
            parts.append(_still(seg, inputs.stills[i], i, tl))
    n = len(tl.visual)
    parts.append("".join(f"[p{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0{tail}[v]")
    return ";".join(parts)


def _join(labels: list[str], out: str) -> str:
    if len(labels) == 1:
        return f"{labels[0]}anull[{out}]"
    return "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest[{out}]"


def audio_graph(tl: Timeline, inputs: Inputs) -> AudioGraph:
    if inputs.silence is not None:
        return AudioGraph([], f"[{inputs.silence}:a]", True)
    if len(tl.audio) == 1:  # v3's chain: the source audio straight into loudness
        track = tl.audio[0]
        media = inputs.files[track.path]
        whole = (
            track.start < EPS
            and track.end > tl.duration_s - EPS
            and track.gain_db == 0
            and abs(track.in_s - media.seek) < EPS
            and track.end - track.start >= media.span - EPS
        )
        if whole:
            return AudioGraph([], f"[{media.index}:a:0]", False)
    parts: list[str] = []
    voices: list[str] = []
    ducked: list[str] = []
    plain: list[str] = []
    for j, track in enumerate(tl.audio):
        media = inputs.files[track.path]
        chain = [
            f"atrim=start={track.in_s - media.seek:.3f}:duration={track.end - track.start:.3f}",
            "asetpts=PTS-STARTPTS",
            f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo",
        ]
        if track.gain_db:
            chain.append(f"volume={track.gain_db:g}dB")
        if track.start > EPS:
            chain.append(f"adelay={round(track.start * 1000)}:all=1")
        parts.append(f"[{media.index}:a:0]" + ",".join(chain) + f"[a{j}]")
        if track.kind != "music":
            voices.append(f"[a{j}]")
        elif track.duck:
            ducked.append(f"[a{j}]")
        else:
            plain.append(f"[a{j}]")
    if ducked and voices:
        parts.append(_join(voices, "voice"))
        # Pad the voice to the full length: sidechaincompress stops at its shorter input,
        # which would cut the bed off where the voice ends (review CP2 #1).
        parts.append(f"[voice]apad,atrim=duration={tl.duration_s:.3f},asplit=2[vo][vsc]")
        parts.append(_join(ducked, "bed"))
        parts.append(f"[bed][vsc]{DUCK}[ducked]")
        final = ["[vo]", "[ducked]", *plain]
    else:
        final = [*voices, *ducked, *plain]
    parts.append(_join(final, "mixed"))
    parts.append(f"[mixed]apad,atrim=duration={tl.duration_s:.3f}[pre]")
    return AudioGraph(parts, "[pre]", False)

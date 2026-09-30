"""Ingest: fetch the source, check the limits, normalize to mp4, extract 16 kHz mono wav.

Sources (ADR-10): a direct HTTP(S) media link, a Telegram upload (file_id, at most 20 MB)
or a path under JOBS_ROOT. The limits (ADR-15) are checked before any GPU time is spent.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.ffmpeg import FfmpegError
from clipforge.hashing import cache_key, sha256_file
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import JobInput, SourceMedia, StageCost, StageName
from clipforge.pipeline.errors import PermanentError

STAGE_VERSION = "1"
TELEGRAM_API = "https://api.telegram.org"
REMUX_VIDEO = frozenset({"h264", "hevc"})
REMUX_AUDIO = frozenset({"aac", "mp3"})
_CHUNK = 1024 * 1024
MAX_REDIRECTS = 5
_TIMEOUT = httpx.Timeout(30.0, read=120.0)


def _default_resolve(host: str) -> list[str]:
    """All addresses `host` resolves to (IPv4 and IPv6)."""
    return sorted({str(info[4][0]).split("%")[0] for info in socket.getaddrinfo(host, None)})


@dataclass
class IngestDeps:
    http: httpx.Client
    settings: Settings
    resolve: Callable[[str], list[str]] = _default_resolve  # injectable: tests use no real DNS


def run(ctx: JobContext, job_input: JobInput, deps: IngestDeps) -> Stored[SourceMedia]:
    key = cache_key("ingest", STAGE_VERSION, [], {"source": _source_id(job_input)})

    def compute(out_dir: Path) -> SourceMedia:
        started = time.monotonic()
        raw = _fetch(ctx, job_input, out_dir, deps)
        ctx.report(StageName.INGEST, 40, "downloaded")
        source = _normalize(ctx, raw, out_dir, job_input, deps.settings)
        if raw.parent == out_dir:
            raw.unlink()  # keep only the normalized copy
        ctx.record_cost(StageCost(stage=StageName.INGEST, wall_s=time.monotonic() - started))
        return source

    return cached_stage(ctx, StageName.INGEST, key, SourceMedia, compute)


def _source_id(job_input: JobInput) -> str:
    if job_input.source_url is not None:
        return f"url:{job_input.source_url}"
    if job_input.telegram_file_id is not None:
        return f"telegram:{job_input.telegram_file_id}"
    return f"path:{job_input.source_path}"


def _fetch(ctx: JobContext, job_input: JobInput, out_dir: Path, deps: IngestDeps) -> Path:
    if job_input.source_path is not None:
        path = ctx.path(job_input.source_path).resolve()
        if not path.is_relative_to(ctx.root.resolve()) or not path.is_file():
            raise PermanentError(f"no such file on the volume: {job_input.source_path}")
        return path
    if job_input.source_url is not None:
        url = str(job_input.source_url)
    else:
        assert job_input.telegram_file_id is not None  # JobInput guarantees exactly one source
        url = _telegram_file_url(deps, job_input.telegram_file_id)
    raw = out_dir / "download"
    _download(ctx, deps, url, raw)
    return raw


class DownloadError(RuntimeError):
    """A transient download failure. The message names only the host and status: download
    URLs can carry secrets (the bot token in Telegram file paths, signed query strings)."""


def _host(url: httpx.URL | str) -> str:
    return httpx.URL(str(url)).host or "the source"


def _telegram_file_url(deps: IngestDeps, file_id: str) -> str:
    token = deps.settings.telegram_bot_token
    if token is None:
        raise PermanentError("the bot is not configured to download uploaded files")
    secret = token.get_secret_value()
    try:
        response = deps.http.get(
            f"{TELEGRAM_API}/bot{secret}/getFile", params={"file_id": file_id}, timeout=_TIMEOUT
        )
        if response.status_code >= 500:
            raise DownloadError(f"HTTP {response.status_code} from Telegram getFile")
        data = response.json()
    except httpx.HTTPError as exc:
        raise DownloadError(f"{type(exc).__name__} from Telegram getFile") from None
    if not data.get("ok"):
        reason = data.get("description", "unknown error")
        raise PermanentError(f"Telegram could not provide the file: {reason}")
    return f"{TELEGRAM_API}/file/bot{secret}/{data['result']['file_path']}"


def _check_public(deps: IngestDeps, url: httpx.URL) -> None:
    """Refuse links to loopback, private, link-local and other non-public addresses (SSRF),
    checked on every redirect hop. DNS rebinding between this check and the connection
    is not covered (Phase 1 inputs come from allow-listed users)."""
    if url.scheme not in ("http", "https"):
        raise PermanentError("only http(s) links are supported")
    host = url.host
    try:
        addresses = deps.resolve(host)
    except OSError:
        raise PermanentError(f"could not resolve {host}") from None
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise PermanentError("links to private or internal addresses are not allowed")


def _download(ctx: JobContext, deps: IngestDeps, url: str, dest: Path) -> None:
    current = httpx.URL(url)
    try:
        for _ in range(MAX_REDIRECTS + 1):
            _check_public(deps, current)
            with deps.http.stream("GET", current, follow_redirects=False, timeout=_TIMEOUT) as r:
                if r.is_redirect:
                    location = r.headers.get("location")
                    if not location:
                        raise PermanentError("the link redirected without a destination")
                    current = current.join(location)
                    continue
                _save(ctx, deps, r, dest)
                return
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        what = f"HTTP {status}" if status else type(exc).__name__
        raise DownloadError(f"{what} while downloading from {_host(current)}") from None
    raise PermanentError("the link redirected too many times")


def _save(ctx: JobContext, deps: IngestDeps, response: httpx.Response, dest: Path) -> None:
    limit = deps.settings.max_source_bytes
    too_big = f"the file is larger than the {limit / 1e9:.1f} GB limit"
    status = response.status_code
    if 400 <= status < 500 and status not in (408, 429):
        raise PermanentError(f"could not download the video (HTTP {status})")
    response.raise_for_status()  # 5xx, 408 and 429 are retried by the step
    if response.headers.get("content-type", "").startswith("text/html"):
        raise PermanentError(
            "the link opens a web page, not a video file; send a direct link to the file"
        )
    declared = int(response.headers.get("content-length") or 0)
    if declared > limit:
        raise PermanentError(too_big)
    received = reported = 0
    with dest.open("wb") as f:
        for chunk in response.iter_bytes(_CHUNK):
            received += len(chunk)
            if received > limit:
                raise PermanentError(too_big)
            f.write(chunk)
            if declared and received - reported >= declared / 10:
                ctx.report(StageName.INGEST, 40 * received / declared, "downloading")
                reported = received


def _normalize(
    ctx: JobContext, raw: Path, out_dir: Path, job_input: JobInput, settings: Settings
) -> SourceMedia:
    try:
        info = ffmpeg.media_info(raw)
    except FfmpegError as exc:
        raise PermanentError("the file is not a video ffmpeg can read") from exc
    if info.video_codec is None:
        raise PermanentError("the file is not a video (no video stream)")
    if info.audio_codec is None:
        raise PermanentError("the video has no audio track, so there is nothing to transcribe")
    limit_s = settings.max_source_duration_s
    if info.duration_s > limit_s:
        raise _too_long(info.duration_s, limit_s)

    # Render re-encodes every clip, so ingest only needs a seekable file: copy the streams
    # (mp4 when the codecs allow, mkv otherwise) and transcode only if copying fails.
    # `-t` caps sources whose container has no duration (browser/screen recordings).
    cap = ["-t", f"{limit_s + 1:.0f}"]
    maps = ["-map", "0:v:0", "-map", "0:a:0"]
    if info.video_codec in REMUX_VIDEO and info.audio_codec in REMUX_AUDIO:
        video = out_dir / "source.mp4"
        ffmpeg.run(
            ["-i", str(raw), *maps, *cap, "-c", "copy", "-movflags", "+faststart", str(video)]
        )
    else:
        video = out_dir / "source.mkv"
        try:
            ffmpeg.run(["-i", str(raw), *maps, *cap, "-c", "copy", str(video)])
        except FfmpegError:
            video = out_dir / "source.mp4"
            ffmpeg.run(
                ["-i", str(raw), *maps, *cap, "-c:v", "libx264", "-preset", "ultrafast",
                 "-crf", "20", "-vf", "scale=-2:'min(1920,ih)'", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(video)]
            )  # fmt: skip
    ctx.report(StageName.INGEST, 70, "normalized")

    out = ffmpeg.media_info(video)
    if out.duration_s <= 0:
        raise PermanentError("could not read the video's duration")
    if out.duration_s > limit_s:
        raise _too_long(out.duration_s, limit_s)

    audio = out_dir / "audio.wav"
    ffmpeg.run(
        ["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)]
    )
    ctx.report(StageName.INGEST, 90, "audio extracted")

    return SourceMedia(
        video_path=ctx.rel(video),
        audio_path=ctx.rel(audio),
        source_hash=sha256_file(raw),
        source_url=str(job_input.source_url) if job_input.source_url is not None else None,
        title=job_input.source_label,
        duration_s=out.duration_s,
        fps=out.fps or info.fps,
        width=out.width,
        height=out.height,
        rotation=out.rotation,
        video_codec=out.video_codec or "",
        size_bytes=raw.stat().st_size,
    )


def _too_long(duration_s: float, limit_s: float) -> PermanentError:
    return PermanentError(
        f"the video is {duration_s / 60:.0f} min long; the limit is {limit_s / 60:.0f} min"
    )

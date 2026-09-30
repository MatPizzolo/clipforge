import ipaddress
import subprocess
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.hashing import sha256_file
from clipforge.models import JobInput, Permission
from clipforge.pipeline.errors import PermanentError
from clipforge.stages import ingest
from tests.conftest import MediaFactory, requires_ffmpeg
from tests.stages.helpers import make_ctx, upload

pytestmark = requires_ffmpeg

TOKEN = "123456:TESTTOKEN"
Handler = Callable[[httpx.Request], httpx.Response]


PUBLIC_IP = "93.184.216.34"
PRIVATE_HOSTS = {"internal.example.com": ["10.0.0.5"]}


def fake_resolve(host: str) -> list[str]:
    """No real DNS in tests: IP literals resolve to themselves, other hosts to a public IP."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return PRIVATE_HOSTS.get(host, [PUBLIC_IP])
    return [host]


def deps(root: Path, handler: Handler | None = None, **overrides: Any) -> ingest.IngestDeps:
    transport = httpx.MockTransport(handler or (lambda request: httpx.Response(500)))
    settings = Settings(_env_file=None, jobs_root=root, telegram_bot_token=TOKEN, **overrides)
    return ingest.IngestDeps(
        http=httpx.Client(transport=transport), settings=settings, resolve=fake_resolve
    )


def path_input(rel: str) -> JobInput:
    return JobInput(source_path=rel, permission=Permission.OWN)


def url_input(url: str) -> JobInput:
    return JobInput.model_validate({"source_url": url, "permission": "own"})


def serve(data: bytes) -> Handler:
    return lambda request: httpx.Response(200, content=data, headers={"content-type": "video/mp4"})


def test_remuxes_h264_aac_and_extracts_wav(tmp_path: Path, media: MediaFactory) -> None:
    src = media(width=1920, height=1080, container="mkv")
    job_input = path_input(upload(tmp_path, src))
    ctx = make_ctx(tmp_path, job_input)
    source = ingest.run(ctx, job_input, deps(tmp_path)).value
    assert (source.width, source.height, source.rotation) == (1920, 1080, 0)
    assert source.video_codec == "h264"
    assert source.duration_s == pytest.approx(3.0, abs=0.1)
    assert source.source_hash == sha256_file(src)
    assert ctx.path(source.video_path).suffix == ".mp4"
    with wave.open(str(ctx.path(source.audio_path))) as wav:
        assert (wav.getnchannels(), wav.getframerate()) == (1, 16000)
    assert ctx.job().progress is not None


def test_keeps_other_codecs_without_reencoding(tmp_path: Path, media: MediaFactory) -> None:
    # Render re-encodes every clip anyway; ingest only needs a seekable file (review fix #2).
    job_input = path_input(upload(tmp_path, media(vcodec="mpeg4", container="mkv")))
    ctx = make_ctx(tmp_path, job_input)
    source = ingest.run(ctx, job_input, deps(tmp_path)).value
    assert source.video_codec == "mpeg4" and source.video_path.endswith(".mkv")
    assert source.duration_s == pytest.approx(3.0, abs=0.1)


def test_falls_back_to_transcoding_when_copy_fails(
    tmp_path: Path, media: MediaFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run = ffmpeg.run

    def picky_run(args: list[str], timeout: float = 900) -> str:
        if "copy" in args and args[-1].endswith(".mkv"):
            raise ffmpeg.FfmpegError(
                "ffmpeg", "Could not write header (incorrect codec parameters)"
            )
        return real_run(args, timeout)

    monkeypatch.setattr(ffmpeg, "run", picky_run)
    job_input = path_input(upload(tmp_path, media(vcodec="mpeg4", container="mkv")))
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path)).value
    assert source.video_codec == "h264"


def piped_webm(path: Path, seconds: float = 3.0) -> Path:
    """A WebM written to a pipe, like a browser MediaRecorder file: no container duration."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=320x180:rate=30:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=duration={seconds}",
        "-c:v",
        "libvpx-vp9",
        "-deadline",
        "realtime",
        "-cpu-used",
        "8",
        "-c:a",
        "libopus",
        "-f",
        "webm",
        "-",
    ]
    path.write_bytes(subprocess.run(cmd, capture_output=True, check=True).stdout)
    return path


def test_accepts_webm_without_a_container_duration(tmp_path: Path) -> None:
    job_input = path_input(upload(tmp_path, piped_webm(tmp_path / "recording.webm")))
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path)).value
    assert source.duration_s == pytest.approx(3.0, abs=0.1)
    assert source.video_codec == "vp9"


def test_duration_limit_applies_when_the_duration_is_unknown(tmp_path: Path) -> None:
    job_input = path_input(upload(tmp_path, piped_webm(tmp_path / "recording.webm")))
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(
            make_ctx(tmp_path, job_input), job_input, deps(tmp_path, max_source_duration_s=1)
        )


def test_rotation_is_reported_with_display_size(tmp_path: Path, media: MediaFactory) -> None:
    rotated = tmp_path / "phone.mp4"
    ffmpeg.run(["-display_rotation:v:0", "90", "-i", str(media()), "-c", "copy", str(rotated)])
    job_input = path_input(upload(tmp_path, rotated))
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path)).value
    assert (source.width, source.height) == (180, 320)
    assert source.rotation in (90, 270)


def test_downloads_direct_links_once(tmp_path: Path, media: MediaFactory) -> None:
    requests: list[httpx.Request] = []
    data = media().read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return serve(data)(request)

    job_input = url_input("https://cdn.example.com/ep1.mp4")
    ctx = make_ctx(tmp_path, job_input)
    d = deps(tmp_path, handler)
    first = ingest.run(ctx, job_input, d)
    second = ingest.run(ctx, job_input, d)
    assert first == second and len(requests) == 1
    assert first.value.source_url == "https://cdn.example.com/ep1.mp4"
    assert not (ctx.root / first.ref).parent.joinpath("download").exists()  # raw download removed


def test_follows_redirects(tmp_path: Path, media: MediaFactory) -> None:
    data = media().read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/short":
            return httpx.Response(302, headers={"location": "https://cdn.example.com/real.mp4"})
        return serve(data)(request)

    job_input = url_input("https://link.example.com/short")
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler)).value
    assert source.duration_s == pytest.approx(3.0, abs=0.1)


def test_web_page_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>", headers={"content-type": "text/html"})

    job_input = url_input("https://example.com/watch")
    with pytest.raises(PermanentError, match="direct link"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


@pytest.mark.parametrize("status", [403, 404])
def test_client_errors_are_permanent(tmp_path: Path, status: int) -> None:
    job_input = url_input("https://cdn.example.com/gone.mp4")
    d = deps(tmp_path, lambda request: httpx.Response(status))
    with pytest.raises(PermanentError, match=f"HTTP {status}"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, d)


def test_server_errors_are_transient(tmp_path: Path) -> None:
    job_input = url_input("https://cdn.example.com/busy.mp4?sig=secret")
    d = deps(tmp_path, lambda request: httpx.Response(503))
    with pytest.raises(ingest.DownloadError) as excinfo:
        ingest.run(make_ctx(tmp_path, job_input), job_input, d)
    assert "503" in str(excinfo.value) and "secret" not in str(excinfo.value)


@pytest.mark.parametrize("failing_path", [f"/bot{TOKEN}/getFile", f"/file/bot{TOKEN}/videos/f.mp4"])
def test_telegram_errors_never_carry_the_bot_token(tmp_path: Path, failing_path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == failing_path:
            return httpx.Response(502)
        return httpx.Response(200, json={"ok": True, "result": {"file_path": "videos/f.mp4"}})

    job_input = JobInput(telegram_file_id="FILE42", permission=Permission.OWN)
    with pytest.raises(ingest.DownloadError) as excinfo:
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))
    assert TOKEN not in str(excinfo.value)
    error = excinfo.value
    # No chained exception (which would carry the URL) is printed with the traceback.
    assert error.__cause__ is None and (error.__context__ is None or error.__suppress_context__)


def test_connection_errors_never_carry_the_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    job_input = url_input("https://cdn.example.com/v.mp4?token=abc")
    with pytest.raises(ingest.DownloadError) as excinfo:
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))
    assert "abc" not in str(excinfo.value) and "cdn.example.com" in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/v.mp4",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/v.mp4",
        "https://internal.example.com/v.mp4",
    ],
)
def test_private_addresses_are_refused(tmp_path: Path, url: str) -> None:
    requests: list[httpx.Request] = []
    job_input = url_input(url)
    d = deps(tmp_path, lambda request: requests.append(request) or httpx.Response(200))
    with pytest.raises(PermanentError, match="not allowed"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, d)
    assert requests == []  # refused before any request was sent


def test_redirects_to_private_addresses_are_refused(tmp_path: Path) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://10.0.0.5/admin"})

    job_input = url_input("https://link.example.com/short")
    with pytest.raises(PermanentError, match="not allowed"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))
    assert requests == ["https://link.example.com/short"]


def test_redirect_loops_are_refused(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://link.example.com/again"})

    job_input = url_input("https://link.example.com/short")
    with pytest.raises(PermanentError, match="too many"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


def test_size_limit_without_content_length(tmp_path: Path, media: MediaFactory) -> None:
    data = media().read_bytes()

    def chunks() -> Iterator[bytes]:
        for i in range(0, len(data), 4096):
            yield data[i : i + 4096]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks(), headers={"content-type": "video/mp4"})

    job_input = url_input("https://cdn.example.com/chunked.mp4")
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(
            make_ctx(tmp_path, job_input),
            job_input,
            deps(tmp_path, handler, max_source_bytes=10_000),
        )


def test_size_limit_from_content_length(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": "video/mp4", "content-length": str(10**10)}
        return httpx.Response(200, content=iter([b"x"]), headers=headers)

    job_input = url_input("https://cdn.example.com/huge.mp4")
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


def test_duration_limit(tmp_path: Path, media: MediaFactory) -> None:
    job_input = path_input(upload(tmp_path, media()))
    with pytest.raises(PermanentError, match="limit"):
        ingest.run(
            make_ctx(tmp_path, job_input), job_input, deps(tmp_path, max_source_duration_s=1)
        )


def test_no_audio_is_permanent(tmp_path: Path, media: MediaFactory) -> None:
    job_input = path_input(upload(tmp_path, media(audio=False)))
    with pytest.raises(PermanentError, match="no audio"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path))


def test_not_a_video_is_permanent(tmp_path: Path) -> None:
    notes = tmp_path / "uploads" / "notes.mp4"
    notes.parent.mkdir()
    notes.write_text("definitely not a video")
    job_input = path_input("uploads/notes.mp4")
    with pytest.raises(PermanentError, match="not a video"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path))


def test_telegram_upload(tmp_path: Path, media: MediaFactory) -> None:
    data = media().read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/bot{TOKEN}/getFile":
            assert request.url.params["file_id"] == "FILE42"
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "videos/f_1.mp4"}})
        assert request.url.path == f"/file/bot{TOKEN}/videos/f_1.mp4"
        return serve(data)(request)

    job_input = JobInput(telegram_file_id="FILE42", permission=Permission.OWN)
    source = ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler)).value
    assert source.source_url is None and source.duration_s == pytest.approx(3.0, abs=0.1)


def test_telegram_refusal_is_permanent(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"ok": False, "description": "Bad Request: file is too big"}
        return httpx.Response(400, json=body)

    job_input = JobInput(telegram_file_id="FILE42", permission=Permission.OWN)
    with pytest.raises(PermanentError, match="too big"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path, handler))


def test_paths_outside_jobs_root_are_rejected(tmp_path: Path) -> None:
    job_input = path_input("../../etc/passwd")
    with pytest.raises(PermanentError, match="no such file"):
        ingest.run(make_ctx(tmp_path, job_input), job_input, deps(tmp_path))

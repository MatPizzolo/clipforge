"""The CLI against the real API app with the in-process chain behind it."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from clipforge.api.main import ApiContext, create_app
from clipforge.bot.telegram import TelegramClient
from clipforge.cli import _fetch, main, set_webhook, wait
from clipforge.inbox import Ledger
from clipforge.models import (
    ChannelRef,
    CostSummary,
    InboxEntry,
    JobError,
    JobStatus,
    JobView,
    Permission,
    StageName,
)
from clipforge.posting import keepalive
from tests.bot.fakes import FakeRequest, make_settings
from tests.dbhelpers import BILLY_SOURCE, make_account
from tests.pipeline.harness import Harness
from tests.posting.builders import run_channel_job as channel_job

URL = "https://media.example.com/ep.mp4"


@pytest.fixture
def api(harness: Harness) -> Iterator[TestClient]:
    ctx = ApiContext(make_settings(harness.root), deps=lambda: harness.deps, sender=lambda: None)
    with TestClient(create_app(ctx)) as client:
        yield client


def _run(harness: Harness, api: TestClient, *argv: str, **kw: object) -> int:
    return main(list(argv), http=api, settings=make_settings(harness.root), **kw)  # type: ignore[arg-type]


def test_run_no_wait_prints_the_job_id(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(harness, api, "run", "--input", URL, "--n", "2", "--no-wait") == 0
    [job_id] = harness.store.list_job_ids()
    assert capsys.readouterr().out.strip() == f"job {job_id}"
    assert harness.store.get(job_id).input.options.n == 2


def test_run_waits_and_prints_the_link(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(harness, api, "run", "--input", URL, sleep=lambda _s: harness.run())
    out = capsys.readouterr().out
    assert code == 0
    assert "done · 2 of 2 clips · $" in out  # automatic: fake scores 0.9 and 0.8 pass 0.80
    assert "/download?exp=" in out.strip().splitlines()[-1]


def test_run_reports_failure_and_resume_hint(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    harness.stages.permanent["transcribe"] = "no speech"
    code = _run(harness, api, "run", "--input", URL, sleep=lambda _s: harness.run())
    out = capsys.readouterr().out
    assert code == 1 and "failed at transcribe: no speech" in out and "clipforge resume" in out


def test_status_and_resume(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = harness.submit()
    assert _run(harness, api, "status", job_id) == 0
    assert capsys.readouterr().out.startswith(f"job {job_id}: queued")
    assert _run(harness, api, "resume", job_id) == 1  # 409: not failed
    assert "HTTP 409" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--input", "/home/me/video.mp4"],
        ["run", "--input", URL, "--len", "abc"],
    ],
)
def test_bad_input_exits_2(harness: Harness, api: TestClient, argv: list[str]) -> None:
    assert _run(harness, api, *argv) == 2
    assert harness.store.list_job_ids() == []


def test_missing_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = make_settings(tmp_path, api_url=None)
    assert main(["status", "20260923-aaaaaaaa-0001"], settings=settings) == 2
    assert "API_URL" in capsys.readouterr().err


def test_wrong_token_is_reported(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = make_settings(harness.root, api_token="wrong")
    assert main(["status", "20260923-aaaaaaaa-0001"], http=api, settings=settings) == 1
    assert "HTTP 401" in capsys.readouterr().err


def test_wait_times_out() -> None:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    view = JobView(
        job_id="J",
        status=JobStatus.RUNNING,
        stage=StageName.INGEST,
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
    )
    ticks = iter([0.0, 10.0, 20.0, 30.0])
    lines: list[str] = []
    with pytest.raises(TimeoutError, match="still running"):
        wait(
            lambda: view,
            interval_s=5,
            timeout_s=15,
            sleep=lambda _s: None,
            clock=lambda: next(ticks),
            echo=lines.append,
        )
    assert lines == ["running · ingest"]  # repeated lines are printed once


def test_set_webhook(tmp_path: Path) -> None:
    request = FakeRequest()
    url = set_webhook(
        make_settings(tmp_path, api_url="https://api.example/"),
        client_factory=lambda token: TelegramClient(token, request_factory=lambda: request),
    )
    assert url == "https://api.example/telegram/webhook"
    assert request.calls[-1][1]["secret_token"] == "hook-secret"


def test_set_webhook_names_missing_settings(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="TELEGRAM_WEBHOOK_SECRET"):
        set_webhook(make_settings(tmp_path, telegram_webhook_secret=None))


def _view(status: JobStatus) -> JobView:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    return JobView(
        job_id="J",
        status=status,
        stage=StageName.PACKAGE,
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
    )


def test_wait_rides_out_network_blips() -> None:
    answers: list[object] = [
        httpx.ConnectError("dns"),
        httpx.ReadTimeout("slow"),
        _view(JobStatus.DONE),
    ]

    def get_view() -> JobView:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        assert isinstance(answer, JobView)
        return answer

    view = wait(get_view, sleep=lambda _s: None, echo=lambda _l: None)
    assert view.status is JobStatus.DONE


def test_wait_gives_up_after_repeated_network_errors() -> None:
    def get_view() -> JobView:
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        wait(get_view, sleep=lambda _s: None, echo=lambda _l: None)


def test_unreachable_api_exits_1_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(refuse))
    assert (
        main(["status", "20260923-aaaaaaaa-0001"], http=http, settings=make_settings(tmp_path)) == 1
    )
    assert "network error talking to the API: ConnectError" in capsys.readouterr().err


class FakeUploader:
    def __init__(self) -> None:
        self.puts: list[tuple[Path, str]] = []

    def put(self, local: Path, remote: str) -> None:
        self.puts.append((local, remote))


class FakeDownloader:
    """Stands in for `modal volume get <job>/output`: writes one clip into dest."""

    def __init__(self) -> None:
        self.gets: list[tuple[str, Path]] = []

    def get(self, remote: str, dest: Path) -> None:
        self.gets.append((remote, dest))
        (dest / "clip_01_score0.90").mkdir(parents=True)
        (dest / "clip_01_score0.90" / "video.mp4").write_bytes(b"v")


def _clip(
    harness: Harness,
    api: TestClient,
    uploader: FakeUploader,
    *argv: str,
    downloader: FakeDownloader | None = None,
) -> int:
    return main(
        ["clip", *argv],
        http=api,
        settings=make_settings(harness.root),
        sleep=lambda _s: harness.run(),
        uploader=uploader,
        downloader=downloader or FakeDownloader(),
    )


def test_clip_one_file_end_to_end(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    video = folder / "My Talk.mp4"
    video.write_bytes(b"video")
    uploader = FakeUploader()

    downloader = FakeDownloader()
    code = _clip(
        harness, api, uploader, str(video), "--n", "2", "--folder", str(folder), "--fetch",
        downloader=downloader,
    )  # fmt: skip
    assert code == 0

    [(local, remote)] = uploader.puts
    assert local == video and remote.startswith("uploads/") and remote.endswith("-My_Talk.mp4")
    [job_id] = harness.store.list_job_ids()
    job = harness.store.get(job_id)
    assert job.input.source_path == remote and job.input.options.n == 2
    assert (folder / "out" / "My Talk" / "clip_01_score0.90" / "video.mp4").read_bytes() == b"v"
    assert downloader.gets == [(f"{job_id}/output", folder / "out" / "My Talk")]
    assert json.loads((folder / ".clipforge.json").read_text()) == {
        "My Talk.mp4": {"job_id": job_id, "status": "fetched", "out": "My Talk"}
    }


def test_clip_folder_submits_only_new_videos(
    harness: Harness, api: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "old.mp4").write_bytes(b"old")
    (folder / "new.mp4").write_bytes(b"new")
    (folder / ".clipforge.json").write_text('{"old.mp4": "20260928-aaaaaaaa-0001"}')
    uploader = FakeUploader()

    assert _clip(harness, api, uploader, "--folder", str(folder), "--no-wait") == 0
    assert [local.name for local, _ in uploader.puts] == ["new.mp4"]
    assert len(harness.store.list_job_ids()) == 1


def test_clip_folder_with_nothing_new(
    harness: Harness, api: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder)) == 0
    assert "no new videos" in capsys.readouterr().out


def test_clip_again_resubmits(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    video = folder / "ep.mp4"
    video.write_bytes(b"ep")
    (folder / ".clipforge.json").write_text('{"ep.mp4": "20260928-aaaaaaaa-0001"}')
    uploader = FakeUploader()
    assert _clip(harness, api, uploader, str(video), "--folder", str(folder), "--no-wait") == 2
    assert _clip(harness, api, uploader, str(video), "--folder", str(folder), "--again",
                 "--no-wait") == 0  # fmt: skip
    assert len(uploader.puts) == 1


@pytest.mark.parametrize("name", ["missing.mp4", "notes.txt"])
def test_clip_bad_file_exits_2(
    harness: Harness, api: TestClient, tmp_path: Path, name: str
) -> None:
    if name.endswith(".txt"):
        (tmp_path / name).write_text("hi")
    assert _clip(harness, api, FakeUploader(), str(tmp_path / name), "--folder", str(tmp_path)) == 2
    assert harness.store.list_job_ids() == []


def test_run_is_automatic_unless_n_is_given(harness: Harness, api: TestClient) -> None:
    assert _run(harness, api, "run", "--input", URL, "--no-wait") == 0
    assert _run(harness, api, "run", "--input", URL, "--n", "3", "--min-score", "0.9",
                "--no-wait") == 0  # fmt: skip
    jobs = sorted((harness.store.get(j) for j in harness.store.list_job_ids()),
                  key=lambda j: j.created_at)  # fmt: skip
    assert jobs[0].input.options.n is None
    assert (jobs[1].input.options.n, jobs[1].input.options.min_score) == (3, 0.9)


CHANNELS_TOML = '[billy-garton]\nname = "Billy Garton Jr."\npermission = "creator_agreement"\n'


# NOTE: tests using _channel_inbox run through the R25 channels.toml fallback (the TestClient
# API has no database); update them when the fallback is removed after the S1 rollout.
def _channel_inbox(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "videos"
    (folder / "billy-garton").mkdir(parents=True)
    (folder / "channels.toml").write_text(CHANNELS_TOML)
    for name in names:
        (folder / "billy-garton" / name).write_bytes(name.encode())
    return folder


def test_clip_submits_and_exits(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4", "ep02.mp4")
    uploader, downloader = FakeUploader(), FakeDownloader()
    assert _clip(harness, api, uploader, "--folder", str(folder), downloader=downloader) == 0
    assert [local.name for local, _ in uploader.puts] == ["ep01.mp4", "ep02.mp4"]
    assert downloader.gets == []  # no waiting, no download without --fetch
    jobs = [harness.store.get(j) for j in harness.store.list_job_ids()]
    assert {j.input.source_label for j in jobs} == {"ep01", "ep02"}
    ref = ChannelRef(slug="billy-garton", name="Billy Garton Jr.")
    assert all(j.input.channel == ref for j in jobs)
    assert all(j.input.source_credit == "Billy Garton Jr." for j in jobs)
    assert all(j.input.permission is Permission.CREATOR_AGREEMENT for j in jobs)
    assert Ledger(folder / ".clipforge.json").submitted() == [
        "billy-garton/ep01.mp4", "billy-garton/ep02.mp4"
    ]  # fmt: skip
    # a second run finds nothing new and uploads nothing
    assert _clip(harness, api, uploader, "--folder", str(folder), downloader=downloader) == 0
    assert len(uploader.puts) == 2


def test_clip_fetch_downloads_into_channel_folders(
    harness: Harness, api: TestClient, tmp_path: Path
) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    downloader = FakeDownloader()
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder), "--fetch",
                 downloader=downloader) == 0  # fmt: skip
    out = folder / "out" / "billy-garton"
    assert [dest for _, dest in downloader.gets] == [out / "ep01"]
    entry = Ledger(folder / ".clipforge.json").get("billy-garton/ep01.mp4")
    assert entry is not None
    assert (entry.status, entry.out) == ("fetched", "billy-garton/ep01")


def test_clip_bad_channels_file_exits_2(
    harness: Harness, api: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    (folder / "channels.toml").write_text('[billy-garton]\nname = "B"\n')
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder)) == 2
    assert "channels.toml" in capsys.readouterr().err


def test_clip_perm_overrides_the_channel(harness: Harness, api: TestClient, tmp_path: Path) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder), "--perm", "own") == 0
    [job_id] = harness.store.list_job_ids()
    job = harness.store.get(job_id)
    assert job.input.permission is Permission.OWN and job.input.channel is not None


class FakeReader:
    def __init__(self, views: dict[str, JobView]) -> None:
        self.views = views

    def get_job(self, job_id: str) -> JobView:
        return self.views[job_id]


def test_fetch_downloads_later_and_keeps_failed_submitted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "videos"
    ledger = Ledger(folder / ".clipforge.json")
    ledger.record("a.mp4", "JA")
    ledger.record("b.mp4", "JB")
    failed = _view(JobStatus.FAILED).model_copy(
        update={"error": JobError(stage=StageName.TRANSCRIBE, error_type="E", message="boom")}
    )
    reader = FakeReader({"JA": _view(JobStatus.DONE), "JB": failed})
    downloader = FakeDownloader()
    code = _fetch(["a.mp4", "b.mp4"], ledger, folder, reader, lambda _s: None, downloader)
    assert code == 1
    assert ledger.get("a.mp4") == InboxEntry(job_id="JA", status="fetched", out="a")
    assert ledger.get("b.mp4") == InboxEntry(job_id="JB")  # still submitted: resume + fetch
    assert "b.mp4: failed at transcribe: boom · clipforge resume JB" in capsys.readouterr().out


# ---- Plan A review fixes


def test_clip_file_in_unknown_folder_exits_2(
    harness: Harness, api: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _channel_inbox(tmp_path)
    (folder / "billy-gartn").mkdir()
    typo = folder / "billy-gartn" / "ep02.mp4"
    typo.write_bytes(b"x")
    uploader = FakeUploader()
    assert _clip(harness, api, uploader, str(typo), "--folder", str(folder)) == 2
    assert uploader.puts == []
    assert "billy-gartn/: not in channels.toml" in capsys.readouterr().err  # fallback text


def test_clip_symlinked_file_in_channel_folder_keeps_channel(
    harness: Harness, api: TestClient, tmp_path: Path
) -> None:
    folder = _channel_inbox(tmp_path)
    real = tmp_path / "downloads" / "ep.mp4"
    real.parent.mkdir()
    real.write_bytes(b"x")
    link = folder / "billy-garton" / "ep.mp4"
    link.symlink_to(real)
    assert _clip(harness, api, FakeUploader(), str(link), "--folder", str(folder)) == 0
    assert Ledger(folder / ".clipforge.json").submitted() == ["billy-garton/ep.mp4"]
    [job_id] = harness.store.list_job_ids()
    assert harness.store.get(job_id).input.channel is not None


class ScriptedReader:
    """get_job answers from a per-job script: a JobView, or an exception to raise."""

    def __init__(self, scripts: dict[str, list[object]]) -> None:
        self.scripts = scripts

    def get_job(self, job_id: str) -> JobView:
        script = self.scripts[job_id]
        answer = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(answer, Exception):
            raise answer
        assert isinstance(answer, JobView)
        return answer


def test_fetch_skips_an_unknown_job_and_retries_server_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from clipforge.cli import ApiError

    folder = tmp_path / "videos"
    ledger = Ledger(folder / ".clipforge.json")
    for key, job in (("a.mp4", "JA"), ("b.mp4", "JB")):
        ledger.record(key, job)
    reader = ScriptedReader({
        "JA": [ApiError("HTTP 404: unknown job", status=404)],
        "JB": [ApiError("HTTP 503: busy", status=503), _view(JobStatus.DONE)],
    })  # fmt: skip
    code = _fetch(["a.mp4", "b.mp4"], ledger, folder, reader, lambda _s: None, FakeDownloader())
    assert code == 1
    assert ledger.get("b.mp4") == InboxEntry(job_id="JB", status="fetched", out="b")
    assert "a.mp4: job JA not found on the API" in capsys.readouterr().out


def test_fetch_rides_out_a_blip_across_many_jobs(tmp_path: Path) -> None:
    folder = tmp_path / "videos"
    ledger = Ledger(folder / ".clipforge.json")
    keys = [f"ep{i:02d}.mp4" for i in range(8)]
    for key in keys:
        ledger.record(key, f"J{key}")
    blip = httpx.ConnectError("wifi")
    reader = ScriptedReader({f"J{k}": [blip, _view(JobStatus.DONE)] for k in keys})
    code = _fetch(keys, ledger, folder, reader, lambda _s: None, FakeDownloader())
    assert code == 0 and ledger.submitted() == []


def test_ledger_survives_an_interrupted_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".clipforge.json"
    ledger = Ledger(path)
    ledger.record("a.mp4", "JA")
    real_write = Path.write_text

    def half_write(self: Path, data: str, *args: object, **kwargs: object) -> int:
        real_write(self, data[: len(data) // 2])
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", half_write)
    with pytest.raises(KeyboardInterrupt):
        ledger.record("b.mp4", "JB")
    monkeypatch.undo()
    assert Ledger(path).get("a.mp4") == InboxEntry(job_id="JA")  # still valid JSON


def test_clip_bad_ledger_exits_2_naming_the_file(
    harness: Harness, api: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _channel_inbox(tmp_path, "ep01.mp4")
    (folder / ".clipforge.json").write_text('{"a.mp4": ')
    assert _clip(harness, api, FakeUploader(), "--folder", str(folder)) == 2
    assert ".clipforge.json" in capsys.readouterr().err


def test_status_without_id_prints_the_posting_overview(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    channel_job(harness)
    assert _run(harness, api, "status") == 0
    out = capsys.readouterr().out
    assert out.startswith("Billy Garton Jr. — 1 episodes (1 clipped")
    assert _run(harness, api, "status", "--rebuild") == 0
    assert "added 0 clip(s) to the posting queue" in capsys.readouterr().out
    assert _run(harness, api, "status", "--restore") == 0
    assert "restored 0 posting key(s) from the newest snapshot" in capsys.readouterr().out


def test_status_rebuild_during_an_outage_exits_1(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """The API's 409 reaches the owner as the outage line, with how to clear it (#220)."""
    channel_job(harness)
    keepalive.set_outage(harness.store.kv, "2026-09-20")
    assert _run(harness, api, "status", "--rebuild") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "HTTP 409: Outage: posting_daily didn't run since 2026-09-20" in captured.err
    assert "clipforge status --restore 2026-09-20" in captured.err


def test_status_restore_takes_an_optional_date(
    harness: Harness, api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    kv = harness.store.kv
    kv.put("post:job_a:clip_01", "{}")
    keepalive.snapshot(kv, harness.root, datetime(2026, 9, 20, tzinfo=UTC))
    kv.delete("post:job_a:clip_01")
    keepalive.snapshot(kv, harness.root, datetime(2026, 9, 29, tzinfo=UTC))
    assert _run(harness, api, "status", "--restore") == 0
    assert "restored 0 posting key(s) from the newest snapshot" in capsys.readouterr().out
    assert _run(harness, api, "status", "--restore", "2026-09-20") == 0
    assert "restored 1 posting key(s) from the 2026-09-20 snapshot" in capsys.readouterr().out
    assert kv.get("post:job_a:clip_01") == "{}"
    assert _run(harness, api, "status", "--restore", "someday") == 1
    assert "400" in capsys.readouterr().err


ACCOUNT_JSON = make_account().model_dump(mode="json")
BILLY_JSON = BILLY_SOURCE.model_dump(mode="json")


def _api(
    routes: dict[tuple[str, str], object], seen: list[httpx.Request] | None = None
) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        key = (request.method, request.url.path)
        if key not in routes:
            return httpx.Response(404, json={"detail": "no route"})
        body = routes[key]
        status = 201 if request.method == "POST" else 200
        return httpx.Response(status, json=body(request) if callable(body) else body)  # type: ignore[operator]

    return httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handle))


def _echo(request: httpx.Request) -> object:
    return json.loads(request.content)


def _inbox(tmp_path: Path, slug: str = "billy-garton") -> Path:
    folder = tmp_path / "videos"
    (folder / slug).mkdir(parents=True)
    (folder / slug / "ep01.mp4").write_bytes(b"x")
    return folder


def test_clip_stops_before_upload_when_sources_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _inbox(tmp_path)
    uploader = FakeUploader()
    code = main(["clip", "--folder", str(folder)], http=_api({("GET", "/sources"): []}),
                settings=make_settings(tmp_path), uploader=uploader)  # fmt: skip
    err = capsys.readouterr().err
    assert code == 2 and not uploader.puts and not (folder / ".clipforge.json").exists()
    assert 'no source "billy-garton"' in err
    assert "clipforge source add billy-garton --account" in err and "source import-toml" in err


def test_clip_stops_before_upload_when_api_unreachable(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    folder, uploader = _inbox(tmp_path), FakeUploader()
    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(refuse))
    assert main(["clip", "--folder", str(folder)], http=http, settings=make_settings(tmp_path),
                uploader=uploader) == 1 and not uploader.puts  # fmt: skip


def test_clip_takes_credit_and_permission_from_the_source(tmp_path: Path) -> None:
    folder, seen = _inbox(tmp_path), []
    http = _api({("GET", "/sources"): [BILLY_JSON],
                 ("POST", "/jobs"): {"job_id": "20260929-aaaaaaaa-0001"}}, seen)  # fmt: skip
    assert main(["clip", "--folder", str(folder)], http=http, settings=make_settings(tmp_path),
                uploader=FakeUploader()) == 0  # fmt: skip
    [job] = [json.loads(r.content) for r in seen if r.url.path == "/jobs"]
    assert job["permission"] == "creator_agreement" and job["source_credit"] == "Billy Garton Jr."
    assert job["channel"] == {"slug": "billy-garton", "name": "Billy Garton Jr."}


def test_clip_skips_held_sources_and_warns_about_channels_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, uploader = _inbox(tmp_path), FakeUploader()
    (folder / "channels.toml").write_text('[billy-garton]\nname = "B"\npermission = "own"\n')
    paused = {**BILLY_JSON, "status": "paused"}
    assert main(["clip", "--folder", str(folder)], http=_api({("GET", "/sources"): [paused]}),
                settings=make_settings(tmp_path), uploader=uploader) == 0  # fmt: skip
    err = capsys.readouterr().err
    assert not uploader.puts and "billy-garton: source paused" in err
    assert "channels.toml is no longer read" in err


def _toml_inbox(tmp_path: Path) -> Path:
    folder = _inbox(tmp_path)
    (folder / "channels.toml").write_text(CHANNELS_TOML)
    return folder


def test_clip_falls_back_to_channels_toml_when_the_api_has_no_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R25: a 503 on GET /sources means the deployed API has no database yet."""
    folder, seen, uploader = _toml_inbox(tmp_path), [], FakeUploader()

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/sources":
            return httpx.Response(503, json={"detail": "DATABASE_URL is not configured"})
        return httpx.Response(201, json={"job_id": "20260929-aaaaaaaa-0001"})

    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handle))
    assert main(["clip", "--folder", str(folder)], http=http, settings=make_settings(tmp_path),
                uploader=uploader) == 0  # fmt: skip
    [job] = [json.loads(r.content) for r in seen if r.url.path == "/jobs"]
    assert job["permission"] == "creator_agreement" and job["source_credit"] == "Billy Garton Jr."
    assert job["channel"] == {"slug": "billy-garton", "name": "Billy Garton Jr."}
    assert len(uploader.puts) == 1
    err = capsys.readouterr().err
    assert (f"warning: the API has no database yet; using {folder}/channels.toml until the S1 "
            "rollout (then run: clipforge source import-toml)") in err  # fmt: skip
    assert "no longer read" not in err


def test_clip_does_not_fall_back_on_other_errors(tmp_path: Path) -> None:
    folder, uploader = _toml_inbox(tmp_path), FakeUploader()
    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(
        lambda r: httpx.Response(500, json={"detail": "boom"})))  # fmt: skip
    assert main(["clip", "--folder", str(folder)], http=http, settings=make_settings(tmp_path),
                uploader=uploader) == 1 and not uploader.puts  # fmt: skip


def test_source_add_sends_the_full_record(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    http = _api({("POST", "/sources"): _echo}, seen)
    assert main(["source", "add", "billy-garton", "--account", "realtalk-clips-en",
                 "--credit", "Billy Garton Jr.", "--permission", "creator_agreement",
                 "--granted-at", "2026-09-01", "--evidence-url", "https://drive.example/a",
                 "--monetization", "yes", "--platforms", "tiktok,youtube",
                 "--handle", "tiktok=@billy"], http=http,
                settings=make_settings(tmp_path)) == 0  # fmt: skip
    body = json.loads(seen[0].content)
    assert body["permission"]["granted_at"] == "2026-09-01"
    assert body["permission"]["platforms"] == ["tiktok", "youtube"]
    assert body["permission"]["monetization_allowed"] is True
    assert body["permission"]["translation_allowed"] is None  # not given: not recorded
    assert body["creator_handles"] == {"tiktok": "@billy"}
    assert seen[0].headers["X-Clipforge-Actor"].startswith("cli:")


def test_source_edit_changes_only_given_fields(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    http = _api({("GET", "/sources/billy-garton"): BILLY_JSON,
                 ("PUT", "/sources/billy-garton"): _echo}, seen)  # fmt: skip
    assert main(["source", "edit", "billy-garton", "--status", "paused", "--expires", "2027-01-01"],
                http=http, settings=make_settings(tmp_path)) == 0  # fmt: skip
    put = json.loads(seen[-1].content)
    assert put["status"] == "paused" and put["permission"]["expires_at"].startswith("2027-01-01")
    assert put["credit_name"] == "Billy Garton Jr."


def test_source_show_lists_missing_permission_fields_and_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    event = {"source_id": "billy-garton", "at": "2026-09-29T12:00:00Z", "actor": "import-toml",
             "action": "imported", "before": None, "after": BILLY_JSON}  # fmt: skip
    http = _api({("GET", "/sources/billy-garton"): BILLY_JSON,
                 ("GET", "/sources/billy-garton/events"): [event]})  # fmt: skip
    assert (
        main(["source", "show", "billy-garton"], http=http, settings=make_settings(tmp_path)) == 0
    )
    out = capsys.readouterr().out
    assert (
        "not recorded: granted_at, granted_by, evidence_url" in out
        and "imported by import-toml" in out
    )


def test_import_toml_dry_run_real_and_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "channels.toml").write_text(
        '[billy-garton]\nname = "Billy Garton Jr."\npermission = "creator_agreement"\n'
    )
    seen: list[httpx.Request] = []
    routes: dict[tuple[str, str], object] = {("GET", "/sources"): [],
                                             ("POST", "/sources"): _echo}  # fmt: skip
    args = ["source", "import-toml", "--folder", str(folder), "--account", "realtalk-clips-en"]
    assert (
        main([*args, "--dry-run"], http=_api(routes, seen), settings=make_settings(tmp_path)) == 0
    )
    assert not [r for r in seen if r.method == "POST"]
    assert main(args, http=_api(routes, seen), settings=make_settings(tmp_path)) == 0
    [post] = [r for r in seen if r.method == "POST"]
    assert post.url.params["action"] == "imported"
    assert json.loads(post.content)["credit_name"] == "Billy Garton Jr."
    assert post.headers["X-Clipforge-Actor"] == "import-toml"
    routes[("GET", "/sources")] = [BILLY_JSON]  # the re-run finds it
    seen.clear()
    assert main(args, http=_api(routes, seen), settings=make_settings(tmp_path)) == 0
    assert (
        not [r for r in seen if r.method == "POST"]
        and "skipped billy-garton" in capsys.readouterr().out
    )


def test_account_create_and_list_print(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    http = _api({("POST", "/accounts"): ACCOUNT_JSON, ("GET", "/accounts"): [ACCOUNT_JSON]})
    assert main(["account", "create", "--blueprint", "realtalk-clips", "--lang", "en",
                 "--handle", "realtalk.clipsdaily", "--posting-from-env"],
                http=http, settings=make_settings(tmp_path)) == 0  # fmt: skip
    assert main(["account", "list"], http=http, settings=make_settings(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "realtalk-clips-en" in out and "tiktok=h.test" in out


def test_clip_does_not_fall_back_on_database_unavailable(tmp_path: Path) -> None:
    folder, uploader = _toml_inbox(tmp_path), FakeUploader()
    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(
        lambda r: httpx.Response(503, json={"detail": "database unavailable"})))  # fmt: skip
    assert main(["clip", "--folder", str(folder)], http=http, settings=make_settings(tmp_path),
                uploader=uploader) == 1 and not uploader.puts  # fmt: skip


def test_fallback_warns_about_stray_folders_and_still_submits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, uploader = _toml_inbox(tmp_path), FakeUploader()
    (folder / "misc").mkdir()
    (folder / "misc" / "x.mp4").write_bytes(b"x")

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sources":
            return httpx.Response(503, json={"detail": "DATABASE_URL is not configured"})
        return httpx.Response(201, json={"job_id": "20260929-aaaaaaaa-0001"})

    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handle))
    assert main(["clip", "--folder", str(folder)], http=http, settings=make_settings(tmp_path),
                uploader=uploader) == 0  # fmt: skip
    assert [p.name for p, _ in uploader.puts] == ["ep01.mp4"]
    assert "warning: misc/: not in channels.toml, skipped" in capsys.readouterr().err


def test_import_toml_409_counts_as_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "channels.toml").write_text(CHANNELS_TOML)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(409, json={"detail": "source exists"})

    http = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handle))
    args = ["source", "import-toml", "--folder", str(folder), "--account", "realtalk-clips-en"]
    assert main(args, http=http, settings=make_settings(tmp_path)) == 0
    assert "skipped billy-garton" in capsys.readouterr().out


def test_source_edit_no_expiry_clears_expires_at(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    dated = {**BILLY_JSON, "permission": {**BILLY_JSON["permission"],
                                          "expires_at": "2027-01-01T23:59:59Z"}}  # fmt: skip
    http = _api({("GET", "/sources/billy-garton"): dated,
                 ("PUT", "/sources/billy-garton"): _echo}, seen)  # fmt: skip
    assert main(["source", "edit", "billy-garton", "--no-expiry"], http=http,
                settings=make_settings(tmp_path)) == 0  # fmt: skip
    assert json.loads(seen[-1].content)["permission"]["expires_at"] is None


def test_posting_verify_exits_1_on_differences(tmp_path: Path) -> None:
    body = {"account_id": "a", "dict_items": 3, "postgres_items": 2, "differences": 1,
            "first": ["x:clip_01: only in the Dict"]}  # fmt: skip
    api = _api({("GET", "/posting/verify"): body})
    assert main(["posting", "verify"], http=api, settings=make_settings(tmp_path)) == 1
    clean = {**body, "postgres_items": 3, "differences": 0, "first": []}
    api = _api({("GET", "/posting/verify"): clean})
    assert main(["posting", "verify"], http=api, settings=make_settings(tmp_path)) == 0


def test_posting_import_dry_run_sends_the_flag(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    api = _api({("POST", "/posting/import"): {"dry_run": True, "failed": ["x"]}}, seen)
    code = main(["posting", "import", "--dry-run"], http=api, settings=make_settings(tmp_path))
    assert code == 1 and seen[0].url.params["dry_run"] == "true"

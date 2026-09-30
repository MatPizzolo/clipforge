"""The local videos/ inbox: picking videos, Volume paths, the ledger, upload and unzip."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from clipforge.inbox import (
    InboxVideo,
    Ledger,
    ModalCliDownloader,
    ModalCliUploader,
    inbox_videos,
    load_channels,
    pending,
    volume_path,
)
from clipforge.models import Channel, InboxEntry, Permission


def _video(folder: Path, name: str, data: bytes = b"video") -> Path:
    path = folder / name
    path.write_bytes(data)
    return path


BILLY = {"billy-garton": Channel(name="Billy Garton Jr.", permission=Permission.CREATOR_AGREEMENT)}


def test_pending_lists_new_videos_only(tmp_path: Path) -> None:
    _video(tmp_path, "b.mp4")
    _video(tmp_path, "a.MOV")
    _video(tmp_path, "notes.txt")
    (tmp_path / "out").mkdir()
    _video(tmp_path / "out", "clip.mp4")  # results are never inputs
    ledger = Ledger(tmp_path / ".clipforge.json")
    assert [v.key for v in pending(tmp_path, ledger, set())[0]] == ["a.MOV", "b.mp4"]
    ledger.record("a.MOV", "20260928-aaaaaaaa-0001")
    assert [v.key for v in pending(tmp_path, ledger, set())[0]] == ["b.mp4"]


def test_channel_folder_videos(tmp_path: Path) -> None:
    (tmp_path / "billy-garton").mkdir()
    _video(tmp_path / "billy-garton", "ep02.mp4")
    _video(tmp_path / "billy-garton", "ep01.mp4")
    _video(tmp_path, "loose.mp4")
    videos, warnings = inbox_videos(tmp_path, set(BILLY))
    folder = tmp_path / "billy-garton"
    assert videos == [
        InboxVideo(folder / "ep01.mp4", "billy-garton/ep01.mp4", "billy-garton"),
        InboxVideo(folder / "ep02.mp4", "billy-garton/ep02.mp4", "billy-garton"),
        InboxVideo(tmp_path / "loose.mp4", "loose.mp4", None),
    ]
    assert warnings == []


def test_unknown_source_folder_is_reported(tmp_path: Path) -> None:
    (tmp_path / "billy-gartn").mkdir()
    _video(tmp_path / "billy-gartn", "ep01.mp4")
    (tmp_path / "empty").mkdir()  # no videos: no warning
    (tmp_path / "schedule").mkdir()
    _video(tmp_path / "schedule", "0800_x.mp4")  # reserved, never an input
    videos, unknown = inbox_videos(tmp_path, set(BILLY))
    assert videos == []
    assert unknown == ["billy-gartn"]


def test_same_name_in_two_channels(tmp_path: Path) -> None:
    channels = {**BILLY, "other": Channel(name="Other", permission=Permission.OWN)}
    for slug in channels:
        (tmp_path / slug).mkdir()
        _video(tmp_path / slug, "ep01.mp4")
    keys = [v.key for v in inbox_videos(tmp_path, set(channels))[0]]
    assert keys == ["billy-garton/ep01.mp4", "other/ep01.mp4"]


def test_ledger_persists_status(tmp_path: Path) -> None:
    path = tmp_path / ".clipforge.json"
    ledger = Ledger(path)
    ledger.record("billy-garton/ep.mp4", "J1")
    ledger.record("b.mp4", "J2")
    ledger.update("b.mp4", InboxEntry(job_id="J2", status="fetched", out="b"))
    reloaded = Ledger(path)
    assert reloaded.job_id("billy-garton/ep.mp4") == "J1"
    assert reloaded.get("b.mp4") == InboxEntry(job_id="J2", status="fetched", out="b")
    assert reloaded.get("other.mp4") is None
    assert reloaded.submitted() == ["billy-garton/ep.mp4"]


def test_ledger_reads_old_format(tmp_path: Path) -> None:
    path = tmp_path / ".clipforge.json"
    path.write_text('{"billy_carton-Koa_smith.mp4": "20260928-b8193698-ba91"}')
    ledger = Ledger(path)
    assert ledger.get("billy_carton-Koa_smith.mp4") == InboxEntry(
        job_id="20260928-b8193698-ba91", status="fetched"
    )
    assert ledger.submitted() == []


def test_volume_path_is_content_addressed_and_safe(tmp_path: Path) -> None:
    one = _video(tmp_path, "My Talk (final)!.mp4", b"one")
    other_dir = tmp_path / "x"
    other_dir.mkdir()
    two = _video(other_dir, "My Talk (final)!.mp4", b"two")
    path_one, path_two = volume_path(one), volume_path(two)
    assert path_one.startswith("uploads/") and path_one.endswith("-My_Talk_final.mp4")
    assert path_one != path_two  # same name, different bytes: no overwrite
    assert volume_path(one) == path_one  # stable


def test_modal_cli_uploader_runs_volume_put(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    uploader = ModalCliUploader(volume="clipforge-jobs", run=calls.append)
    local = _video(tmp_path, "ep.mp4")
    uploader.put(local, "uploads/abcd1234-ep.mp4")
    assert calls == [
        [
            sys.executable,
            "-m",
            "modal",
            "volume",
            "put",
            "--force",
            "clipforge-jobs",
            str(local),
            "/uploads/abcd1234-ep.mp4",
        ]
    ]


def test_modal_cli_downloader_puts_the_output_folder_in_dest(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_volume_get(argv: list[str]) -> None:
        calls.append(argv)
        local = Path(argv[-1])  # `modal volume get VOL /job/output LOCAL` makes LOCAL/output/
        (local / "output" / "clip_01_score0.90").mkdir(parents=True)
        (local / "output" / "clip_01_score0.90" / "video.mp4").write_bytes(b"v")

    dest = tmp_path / "out" / "ep"
    ModalCliDownloader(volume="clipforge-jobs", run=fake_volume_get).get("J/output", dest)
    assert calls[0][:7] == [sys.executable, "-m", "modal", "volume", "get", "--force",
                            "clipforge-jobs"]  # fmt: skip
    assert calls[0][7] == "/J/output"
    assert (dest / "clip_01_score0.90" / "video.mp4").read_bytes() == b"v"
    assert [p.name for p in dest.parent.iterdir()] == ["ep"]  # no temp folder left behind


CHANNELS = (
    '[billy-garton]\nname = "Billy Garton Jr."\n'
    'url = "https://www.youtube.com/@example"\npermission = "creator_agreement"\n'
)


def test_load_channels(tmp_path: Path) -> None:
    path = tmp_path / "channels.toml"
    assert load_channels(path) == {}
    path.write_text(CHANNELS)
    [(slug, channel)] = load_channels(path).items()
    assert slug == "billy-garton"
    assert channel.name == "Billy Garton Jr."
    assert channel.permission is Permission.CREATOR_AGREEMENT


@pytest.mark.parametrize(
    "text",
    [
        '[Billy]\nname = "B"\npermission = "own"\n',  # uppercase slug
        '[out]\nname = "B"\npermission = "own"\n',  # reserved
        '[b]\nname = "B"\n',  # permission missing
        '[b]\nname = "B"\npermission = "stolen"\n',
        '[b]\nname = ""\npermission = "own"\n',
        'name = "not a table"\n',
        "[b\n",  # not TOML
    ],
)
def test_bad_channels_file(tmp_path: Path, text: str) -> None:
    path = tmp_path / "channels.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_channels(path)

import json
from datetime import UTC, date, datetime
from pathlib import Path

from clipforge.pipeline.deps import MemoryKV
from clipforge.posting import keepalive
from clipforge.posting.repo import PAUSED_KEY

NOW = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)


class RecordingKV(MemoryKV):
    def __init__(self) -> None:
        super().__init__()
        self.gets: list[str] = []

    def get(self, key: str) -> str | None:
        self.gets.append(key)
        return super().get(key)


def _seed(kv: MemoryKV) -> None:
    kv.put("post:job_a:clip_01", "{}")
    kv.put("post:job_a:clip_01:posted:tiktok", '{"at": "x"}')
    kv.put("job:job_a", "{}")
    kv.put("job:job_a:clip:clip_01", "{}")
    kv.put(PAUSED_KEY, "1")
    kv.put("tg:update:5", "1")
    kv.put("posting:slot:2026-09-29T08:00", "1")
    kv.put("posting:reminded:2026-09-29T08:00", "1")


def test_touch_reads_only_post_job_and_paused_keys() -> None:
    kv = RecordingKV()
    _seed(kv)
    assert keepalive.touch(kv) == 5
    assert sorted(kv.gets) == sorted(
        [
            "post:job_a:clip_01",
            "post:job_a:clip_01:posted:tiktok",
            "job:job_a",
            "job:job_a:clip:clip_01",
            PAUSED_KEY,
        ]
    )


def test_snapshot_writes_post_keys_and_paused(tmp_path: Path) -> None:
    kv = MemoryKV()
    _seed(kv)
    path, count = keepalive.snapshot(kv, tmp_path, NOW)
    assert count == 3
    assert path == tmp_path / "posting" / "snapshots" / "2026-09-29.json"
    data = json.loads(path.read_text())
    assert set(data) == {
        "post:job_a:clip_01",
        "post:job_a:clip_01:posted:tiktok",
        PAUSED_KEY,
    }
    assert [p.name for p in path.parent.iterdir()] == ["2026-09-29.json"]  # no temp left


def test_snapshot_same_day_overwrites_and_prunes(tmp_path: Path) -> None:
    kv = MemoryKV()
    kv.put("post:job_a:clip_01", "{}")
    folder = tmp_path / "posting" / "snapshots"
    folder.mkdir(parents=True)
    for day in range(1, 21):
        (folder / f"2026-09-{day:02d}.json").write_text("{}")
    (folder / "notes.txt").write_text("keep me")
    keepalive.snapshot(kv, tmp_path, NOW)
    keepalive.snapshot(kv, tmp_path, NOW)
    names = sorted(p.name for p in folder.glob("*.json"))
    assert len(names) == 14
    assert names[-1] == "2026-09-29.json"
    assert names[0] == "2026-09-08.json"
    assert (folder / "notes.txt").exists()
    assert json.loads((folder / "2026-09-29.json").read_text()) == {"post:job_a:clip_01": "{}"}


def test_restore_puts_back_missing_keys_only(tmp_path: Path) -> None:
    kv = MemoryKV()
    _seed(kv)
    keepalive.snapshot(kv, tmp_path, NOW)
    kv.delete("post:job_a:clip_01:posted:tiktok")
    kv.put("post:job_a:clip_01", "changed")
    assert keepalive.restore(kv, tmp_path) == 1
    assert kv.get("post:job_a:clip_01:posted:tiktok") == '{"at": "x"}'
    assert kv.get("post:job_a:clip_01") == "changed"


def test_restore_never_restores_paused(tmp_path: Path) -> None:
    kv = MemoryKV()
    _seed(kv)
    keepalive.snapshot(kv, tmp_path, NOW)
    kv.delete(PAUSED_KEY)  # /go
    kv.delete("post:job_a:clip_01")
    assert keepalive.restore(kv, tmp_path) == 1
    assert kv.get(PAUSED_KEY) is None


def test_restore_without_snapshot_returns_zero(tmp_path: Path) -> None:
    assert keepalive.restore(MemoryKV(), tmp_path) == 0


def test_restore_falls_back_past_a_corrupt_newest_file(tmp_path: Path) -> None:
    kv = MemoryKV()
    kv.put("post:job_a:clip_01", "{}")
    keepalive.snapshot(kv, tmp_path, datetime(2026, 9, 28, tzinfo=UTC))
    (tmp_path / "posting" / "snapshots" / "2026-09-29.json").write_text("{not json")
    kv.delete("post:job_a:clip_01")
    assert keepalive.restore(kv, tmp_path) == 1
    assert kv.get("post:job_a:clip_01") == "{}"


def test_restore_a_given_day_ignores_newer_snapshots(tmp_path: Path) -> None:
    """After a long outage the newest snapshot already lacks the expired keys (ADR-24)."""
    kv = MemoryKV()
    kv.put("post:job_a:clip_01", "{}")
    kv.put("post:job_a:clip_01:posted:tiktok", '{"at": "x"}')
    keepalive.snapshot(kv, tmp_path, datetime(2026, 9, 20, tzinfo=UTC))
    kv.delete("post:job_a:clip_01:posted:tiktok")  # expired during the outage
    keepalive.snapshot(kv, tmp_path, NOW)  # the first run after it
    assert keepalive.restore(kv, tmp_path) == 0
    assert keepalive.restore(kv, tmp_path, date(2026, 9, 20)) == 1
    assert kv.get("post:job_a:clip_01:posted:tiktok") == '{"at": "x"}'


def test_restore_a_missing_or_corrupt_day_returns_zero(tmp_path: Path) -> None:
    kv = MemoryKV()
    kv.put("post:job_a:clip_01", "{}")
    keepalive.snapshot(kv, tmp_path, NOW)
    kv.delete("post:job_a:clip_01")
    assert keepalive.restore(kv, tmp_path, date(2026, 9, 1)) == 0
    (tmp_path / "posting" / "snapshots" / "2026-09-28.json").write_text("{not json")
    assert keepalive.restore(kv, tmp_path, date(2026, 9, 28)) == 0  # no fallback to another day
    assert kv.get("post:job_a:clip_01") is None

"""posting_daily (ADR-46, card 002 A6): every part runs, guarded, and alerts on trouble."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clipforge.accounts.service import read_schedules
from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.ops import OpsAlerts
from clipforge.posting.daily import run_daily, snapshot_tables
from tests.bot.fakes import ALLOWED_USER, FakeSender
from tests.bot.helpers import two_account_ctx
from tests.pipeline.harness import Harness
from tests.posting.builders import JOB, run_channel_job

NOON = datetime(2026, 9, 30, 16, 0, tzinfo=UTC)  # 12:00 New York, outside quiet hours


def test_dict_mode_touches_snapshots_and_rebuilds(tmp_path: Path) -> None:
    harness = Harness.build(tmp_path)
    run_channel_job(harness)
    lines = run_daily(harness.deps, None, "realtalk-clips-en", NOON)
    assert [line.split(":")[0] for line in lines] == ["touch", "dict snapshot", "rebuild"]
    assert lines[-1] == "rebuild: 0 clips queued"  # already queued by package
    assert (tmp_path / "posting" / "snapshots" / "2026-09-30.json").is_file()


def test_with_a_database_it_verifies_backfills_syncs_and_snapshots(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    deps = ctx.deps
    alerts = FakeSender()
    deps.ops = OpsAlerts(deps.store.kv, alerts, ALLOWED_USER, "America/New_York")
    kv = deps.store.kv
    kv.delete("posting:schedule:founder-tapes-en")
    kv.delete(f"post:{JOB}:clip_01")  # drift: realtalk's clip is now only in Postgres
    lines = run_daily(deps, db, "realtalk-clips-en", NOON)
    names = [line.split(":")[0] for line in lines]
    assert names == ["touch", "dict snapshot", "verify", "jobs backfill", "schedules", "rebuild",
                     "db snapshot"]  # fmt: skip
    assert "founder-tapes-en" in read_schedules(kv)  # the lost copy is back
    assert any("posting verify: 1 differences" in t for _, t, _ in alerts.messages)
    path = tmp_path / "posting" / "snapshots" / "db-2026-09-30.json"
    data = json.loads(path.read_text())
    assert len(data["content_items"]) == 2 and len(data["accounts"]) == 2


def test_a_failing_part_alerts_and_the_rest_still_run(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    alerts = FakeSender()
    harness.deps.ops = OpsAlerts(harness.store.kv, alerts, ALLOWED_USER, "America/New_York")
    (tmp_path / "20260930-deadbeef-0001" / "output").mkdir(parents=True)
    (tmp_path / "20260930-deadbeef-0001" / "output" / "metadata.json").write_text("{broken")
    lines = run_daily(harness.deps, db, "realtalk-clips-en", NOON)
    assert "jobs backfill: failed" in lines and lines[-1].startswith("db snapshot: ")
    assert any("posting_daily: jobs backfill failed" in t for _, t, _ in alerts.messages)


def test_db_snapshots_keep_fourteen_and_never_match_the_restore_glob(
    tmp_path: Path, db: Database
) -> None:
    for day in range(16):
        snapshot_tables(db, tmp_path, NOON + timedelta(days=day))
    folder = tmp_path / "posting" / "snapshots"
    assert len(list(folder.glob("db-*.json"))) == 14
    assert list(folder.glob("????-??-??.json")) == []  # keepalive.restore reads only those

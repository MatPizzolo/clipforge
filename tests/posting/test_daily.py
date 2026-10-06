"""posting_daily (ADR-46, card 002 A6): every part runs, guarded, and alerts on trouble."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clipforge.accounts.service import read_schedules
from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.ops import OpsAlerts
from clipforge.posting.daily import run_daily, snapshot_tables
from clipforge.posting.outage import clear_outage, outage_since
from tests.bot.fakes import ALLOWED_USER, FakeSender
from tests.bot.helpers import two_account_ctx
from tests.pipeline.harness import Harness
from tests.posting.builders import run_channel_job

NOON = datetime(2026, 9, 30, 16, 0, tzinfo=UTC)  # 12:00 New York, outside quiet hours


def test_without_a_database_it_only_rebuilds(tmp_path: Path) -> None:
    harness = Harness.build(tmp_path)
    run_channel_job(harness)
    lines = run_daily(harness.deps, None, NOON)
    assert lines == ["rebuild: 0 clips queued"]  # already queued by package
    assert not (tmp_path / "posting" / "snapshots").exists()  # no Dict snapshot (card 040)


def test_with_a_database_it_backfills_syncs_and_snapshots(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    deps = ctx.deps
    alerts = FakeSender()
    deps.ops = OpsAlerts(deps.store.kv, alerts, ALLOWED_USER, "America/New_York")
    kv = deps.store.kv
    kv.delete("posting:schedule:founder-tapes-en")
    lines = run_daily(deps, db, NOON)
    names = [line.split(":")[0] for line in lines]
    # card 040: no touch, Dict snapshot or verify any more (ADR-24 retired)
    assert names == ["brakes", "jobs backfill", "schedules", "deliveries", "rebuild",
                     "db snapshot"]  # fmt: skip
    assert "founder-tapes-en" in read_schedules(kv)  # the lost copy is back
    assert alerts.messages == []
    assert not [k for k in kv.keys() if k.startswith("post:")]  # noqa: SIM118
    folder = tmp_path / "posting" / "snapshots"
    assert [p.name for p in folder.iterdir()] == ["db-2026-09-30.json"]
    data = json.loads((folder / "db-2026-09-30.json").read_text())
    assert len(data["content_items"]) == 2 and len(data["accounts"]) == 2


def test_a_failing_part_alerts_and_the_rest_still_run(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    alerts = FakeSender()
    harness.deps.ops = OpsAlerts(harness.store.kv, alerts, ALLOWED_USER, "America/New_York")
    (tmp_path / "20260930-deadbeef-0001" / "output").mkdir(parents=True)
    (tmp_path / "20260930-deadbeef-0001" / "output" / "metadata.json").write_text("{broken")
    lines = run_daily(harness.deps, db, NOON)
    assert "jobs backfill: failed" in lines and lines[-1].startswith("db snapshot: ")
    assert any("posting_daily: jobs backfill failed" in t for _, t, _ in alerts.messages)


def test_db_snapshots_keep_fourteen(tmp_path: Path, db: Database) -> None:
    for day in range(16):
        snapshot_tables(db, tmp_path, NOON + timedelta(days=day))
    folder = tmp_path / "posting" / "snapshots"
    assert len(list(folder.glob("db-*.json"))) == 14
    assert list(folder.glob("????-??-??.json")) == []


def test_the_daily_run_gets_a_longer_statement_timeout_and_one_snapshot_view(
    tmp_path: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    # migration review I1: whole-table reads must not hit the 5 s cap meant for taps and ticks
    from sqlalchemy import text

    import clipforge.posting.daily as daily

    seen: list[tuple[str, str]] = []
    real = daily.snapshot_tables

    def spy(database: Database, root: Path, now: datetime, keep: int = 14) -> tuple[Path, int]:
        with database.begin() as conn:
            seen.append((conn.execute(text("SHOW statement_timeout")).scalar_one(), ""))
        return real(database, root, now, keep)

    monkeypatch.setattr(daily, "snapshot_tables", spy)
    harness = Harness.build(tmp_path)
    run_daily(harness.deps, db, NOON)
    assert seen == [(daily.BATCH_TIMEOUT, "")]
    with db.begin() as conn:  # the shared Database keeps its 5 s
        assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "5s"


def test_rebuild_waits_for_go_after_a_long_outage(tmp_path: Path, db: Database) -> None:
    # PR review 3, made sticky by the coordinator's G review, measured from the table
    # snapshots since card 040: after days without posting_daily the flag holds rebuild (and
    # the tick) until the owner looks and sends /go
    harness = Harness.build(tmp_path)
    run_channel_job(harness)
    alerts = FakeSender()
    harness.deps.ops = OpsAlerts(harness.store.kv, alerts, ALLOWED_USER, "America/New_York")
    folder = tmp_path / "posting" / "snapshots"
    folder.mkdir(parents=True)
    (folder / "db-2026-09-25.json").write_text("{}")  # the last run was 5 days ago
    (folder / "2026-09-29.json").write_text("{}")  # an old Dict snapshot doesn't count
    lines = run_daily(harness.deps, db, NOON)
    assert "rebuild: skipped (outage: no table snapshot since 2026-09-25)" in lines
    assert outage_since(harness.store.kv) == "2026-09-25"
    [text] = [t for _, t, _ in alerts.messages if "No posting table snapshot" in t]
    assert "/go" in text and "restore" not in text
    # today's snapshot closes the gap, but the flag still holds tomorrow's rebuild
    lines = run_daily(harness.deps, db, NOON + timedelta(days=1))
    assert "rebuild: skipped (outage: no table snapshot since 2026-09-25)" in lines
    clear_outage(harness.store.kv)  # what /go does
    lines = run_daily(harness.deps, db, NOON + timedelta(days=2))
    assert "rebuild: 0 clips queued" in lines


def test_a_recent_table_snapshot_is_no_outage(tmp_path: Path) -> None:
    harness = Harness.build(tmp_path)
    folder = tmp_path / "posting" / "snapshots"
    folder.mkdir(parents=True)
    (folder / "db-2026-09-28.json").write_text("{}")  # 2 days: within MAX_GAP_DAYS
    (folder / "2026-09-01.json").write_text("{}")  # an old Dict snapshot is ignored
    assert run_daily(harness.deps, None, NOON) == ["rebuild: 0 clips queued"]
    assert outage_since(harness.store.kv) is None


def test_old_webhook_deliveries_are_pruned(db: Database) -> None:
    from sqlalchemy import func, select

    from clipforge.db.tables import webhook_deliveries
    from clipforge.posting.daily import DELIVERIES_KEPT, prune_deliveries

    with db.begin() as conn:
        conn.execute(webhook_deliveries.insert(), [
            {"delivery_id": "old", "event": "upload_completed", "payload": {},
             "received_at": NOON - DELIVERIES_KEPT - timedelta(minutes=1)},
            {"delivery_id": "new", "event": "upload_completed", "payload": {},
             "received_at": NOON - timedelta(days=1)},
        ])  # fmt: skip
    assert prune_deliveries(db, NOON - DELIVERIES_KEPT) == 1
    with db.begin() as conn:
        assert conn.execute(select(func.count()).select_from(webhook_deliveries)).scalar() == 1


def test_the_brake_repair_is_skipped_without_posting(tmp_path: Path, db: Database) -> None:
    # it writes rows only through the Posting repo, never a bare SQL repo (PR #52 review)
    from clipforge.posting.daily import _brakes

    harness = Harness.build(tmp_path)
    harness.deps.posting = None
    assert _brakes(harness.deps, db, NOON).startswith("skipped")

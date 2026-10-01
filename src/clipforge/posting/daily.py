"""The daily reconcile (ADR-46): `posting_keepalive` became `posting_daily`, same cron slot.

Until ADR-24 retires (Task 23), the Dict still holds the queue, so it is touched and
snapshotted every day. With a database wired it also runs `posting verify`, backfills missing
`jobs` rows, rewrites the schedule copies (A3), and snapshots the posting and source tables.
Rebuild always runs. Every part is idempotent and guarded: one failing part is reported (and
alerted, ADR-45) and the rest still run. Modal-free.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from clipforge.accounts.service import sync_schedules
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database, redact
from clipforge.db.tables import (
    accounts,
    assets,
    content_items,
    post_events,
    posting_state,
    posts,
    sends,
    source_events,
    sources,
)
from clipforge.pipeline.steps import Deps
from clipforge.posting import keepalive
from clipforge.posting.migrate import backfill_jobs

log = logging.getLogger(__name__)

# The durable posting and source tables (spec §3); `jobs` is rebuilt from metadata.json.
SNAPSHOT_TABLES = (accounts, posting_state, sources, source_events, content_items, assets, posts,
                   sends, post_events)  # fmt: skip
DB_SNAPSHOT_PREFIX = "db-"  # never matches keepalive's "????-??-??.json" restore glob


def snapshot_tables(db: Database, root: Path, now: datetime, keep: int = 14) -> tuple[Path, int]:
    """Every row of the posting and source tables as JSON in
    `<root>/posting/snapshots/db-<UTC date>.json`; keeps the newest `keep`. Returns the path
    and the row count."""
    data: dict[str, list[dict[str, object]]] = {}
    with db.begin() as conn:
        for table in SNAPSHOT_TABLES:
            data[table.name] = [dict(row._mapping) for row in conn.execute(select(table))]
    folder = root / "posting" / "snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{DB_SNAPSHOT_PREFIX}{now.astimezone(UTC):%Y-%m-%d}.json"
    tmp = folder / f".{path.name}.tmp"
    tmp.write_text(json.dumps(data, default=str))
    os.replace(tmp, path)
    for old in sorted(folder.glob(f"{DB_SNAPSHOT_PREFIX}????-??-??.json"))[:-keep]:
        old.unlink(missing_ok=True)
    return path, sum(len(rows) for rows in data.values())


def run_daily(deps: Deps, db: Database | None, account_id: str, now: datetime) -> list[str]:
    """Run every part; returns one summary line per part (for the cron log)."""
    from clipforge.service import rebuild_posting  # service imports posting code

    kv = deps.store.kv
    lines: list[str] = []

    def part(name: str, run: Callable[[], str]) -> None:
        try:
            lines.append(f"{name}: {run()}")
        except Exception as exc:
            log.warning("posting_daily: %s failed: %s", name, redact(exc))
            lines.append(f"{name}: failed")
            if deps.ops is not None:
                deps.ops.alert(f"posting_daily: {name} failed: {redact(exc)}", "daily", name,
                               now=now)  # fmt: skip

    part("touch", lambda: f"{keepalive.touch(kv)} keys")
    part("dict snapshot", lambda: _saved(keepalive.snapshot(kv, deps.root, now), "keys"))
    if db is not None:
        part("verify", lambda: _verify(deps, db, account_id, now))
        part("jobs backfill", lambda: _backfill(deps, db))
        part("schedules", lambda: f"{sync_schedules(AccountsRepo(db), kv)} accounts")
    part("rebuild", lambda: f"{rebuild_posting(deps, now)} clips queued")
    if db is not None:
        part("db snapshot", lambda: _saved(snapshot_tables(db, deps.root, now), "rows"))
    return lines


def _saved(result: tuple[Path, int], unit: str) -> str:
    path, count = result
    return f"{count} {unit} -> {path.name}"


def _verify(deps: Deps, db: Database, account_id: str, now: datetime) -> str:
    report = keepalive.verify_daily(deps.store.kv, db, account_id)
    if report is None:
        raise RuntimeError("posting verify could not run (see the log)")
    if report.differences and deps.ops is not None:
        first = "\n".join(report.first[:3])
        deps.ops.alert(f"posting verify: {report.differences} differences between the Dict and "
                       f"Postgres for {account_id}.\n{first}", "verify", account_id,
                       now=now)  # fmt: skip
    return f"{report.differences} differences"


def _backfill(deps: Deps, db: Database) -> str:
    report = backfill_jobs(deps.store.kv, deps.root, db, dry_run=False)
    if report.failed:
        raise RuntimeError(f"{len(report.failed)} jobs failed: {', '.join(report.failed[:5])}")
    return f"{report.written} rows written"

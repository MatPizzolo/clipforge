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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text

from clipforge.accounts.service import sync_schedules
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database, redact
from clipforge.db.tables import (
    accounts,
    assets,
    autopilot,
    autopilot_events,
    content_items,
    links,
    post_events,
    posting_state,
    posts,
    sends,
    slot_plans,
    source_events,
    sources,
    webhook_deliveries,
)
from clipforge.ops import OpsAlerts
from clipforge.pipeline.deps import KV
from clipforge.pipeline.steps import Deps
from clipforge.posting import brake, keepalive
from clipforge.posting.migrate import backfill_jobs
from clipforge.posting.repo import PostingRepo

log = logging.getLogger(__name__)

# The durable posting and source tables (spec §3); `jobs` is rebuilt from metadata.json.
SNAPSHOT_TABLES = (accounts, posting_state, sources, source_events, content_items, assets, posts,
                   sends, post_events, autopilot, autopilot_events, slot_plans,
                   links)  # fmt: skip
DELIVERIES_KEPT = timedelta(days=30)  # the webhook replay guard (S2 spec §3)
# posting_daily's whole-table reads (the snapshot, verify, backfill) outgrow the 5 s cap meant
# for taps and ticks; one daily run gets this instead (migration review I1)
BATCH_TIMEOUT = "1min"
DB_SNAPSHOT_PREFIX = "db-"
# A rebuild after a longer gap could re-queue clips whose posted/verdict keys expired (PR
# review 3); the owner restores first (ADR-24 runbook)
MAX_GAP_DAYS = 2  # never matches keepalive's "????-??-??.json" restore glob


def snapshot_tables(db: Database, root: Path, now: datetime, keep: int = 14) -> tuple[Path, int]:
    """Every row of the posting and source tables as JSON in
    `<root>/posting/snapshots/db-<UTC date>.json`; keeps the newest `keep`. Returns the path
    and the row count."""
    data: dict[str, list[dict[str, object]]] = {}
    with db.begin() as conn:
        # one consistent view of every table, and no writes (it must be the first query)
        conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
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


def _newest_dict_snapshot(root: Path) -> date | None:
    folder = root / "posting" / "snapshots"
    days = []
    for path in folder.glob("????-??-??.json"):
        try:
            days.append(date.fromisoformat(path.stem))
        except ValueError:
            continue
    return max(days, default=None)


def run_daily(deps: Deps, db: Database | None, account_id: str, now: datetime) -> list[str]:
    """Run every part; returns one summary line per part (for the cron log)."""
    from clipforge.service import rebuild_posting  # service imports posting code

    kv = deps.store.kv
    lines: list[str] = []
    if db is not None:
        db = db.with_timeout(BATCH_TIMEOUT)

    def part(name: str, run: Callable[[], str]) -> None:
        try:
            lines.append(f"{name}: {run()}")
        except Exception as exc:
            log.warning("posting_daily: %s failed: %s", name, redact(exc))
            lines.append(f"{name}: failed")
            if deps.ops is not None:
                deps.ops.alert(f"posting_daily: {name} failed: {redact(exc)}", "daily", name,
                               now=now)  # fmt: skip

    last = _newest_dict_snapshot(deps.root)  # before today's run writes one
    part("touch", lambda: f"{keepalive.touch(kv)} keys")
    part("dict snapshot", lambda: _saved(keepalive.snapshot(kv, deps.root, now), "keys"))
    if db is not None:
        part("verify", lambda: _verify(deps, db, account_id, now))
        part("brakes", lambda: _brakes(deps, db, now))
        part("jobs backfill", lambda: _backfill(deps, db))
        part("schedules", lambda: f"{sync_schedules(AccountsRepo(db), kv)} accounts")
        part("deliveries", lambda: f"{prune_deliveries(db, now - DELIVERIES_KEPT)} pruned")
    if last is not None and (now.astimezone(UTC).date() - last).days > MAX_GAP_DAYS:
        keepalive.set_outage(kv, last.isoformat())  # sticky until /go or a restore
    since = keepalive.outage_since(kv)
    if since is not None:
        lines.append(f"rebuild: skipped (outage: no posting snapshot since {since})")
        if deps.ops is not None:
            deps.ops.alert(f"posting_daily hadn't run since {since}: Dict keys may have expired, "
                           "so rebuild and the posting slots are stopped. Restore from that "
                           f"snapshot (clipforge status --restore {since}), check /status, then "
                           "/go.", "daily", "outage", now=now)  # fmt: skip
    else:
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


def _brakes(deps: Deps, db: Database, now: datetime) -> str:
    if deps.posting is None:
        # rows are written through the Posting repo (Dual: Postgres and the Dict mirror) only
        return "skipped (posting is not configured in this container)"
    lines = repair_brakes(deps.store.kv, db, now, ops=deps.ops, repo=deps.posting.repo)
    return "; ".join(lines) or "in step"


def repair_brakes(
    kv: KV, db: Database, now: datetime, *, repo: PostingRepo, ops: OpsAlerts | None = None,
) -> list[str]:  # fmt: skip
    """Where a brake key and `posting_state` disagree, the newer one wins (S2 spec §6.7):
    - a key newer than the row (a /pause or /go during a Neon outage) rewrites the row;
    - a row newer than the key rewrites the account's key;
    - a missing key is never restored blindly: only a paused row is written back, with an alert.
    The writes go through `actions.repair_brake` as `system:daily`. Returns one line per fix."""
    from clipforge.posting import actions  # actions imports the bot, which imports this package

    accounts_repo = AccountsRepo(db)
    lines: list[str] = []
    for account in accounts_repo.list():
        row = accounts_repo.paused_state(account.id)
        newest = brake.latest(kv, account.id)
        if newest is None:
            if row is not None and row[0]:
                actions.repair_brake(kv, repo, account.id, side="key", on=True, at=row[1],
                                     reason="restored from posting_state")  # fmt: skip
                lines.append(f"{account.id}: missing brake key restored from the paused row")
                if ops is not None:
                    ops.alert(f"Brake key for {account.id} was missing; restored from the "
                              "database", "brake", account.id, now=now)  # fmt: skip
            continue
        braked = brake.braked(kv, account.id)
        if row is not None and row[0] == braked:
            continue
        if row is None or newest.at >= row[1]:
            actions.repair_brake(kv, repo, account.id, side="row", on=braked, at=now,
                                 reason=f"repair: brake:{newest.scope} is newer")  # fmt: skip
            lines.append(f"{account.id}: posting_state set to {'paused' if braked else 'on'}")
        elif not row[0] and brake.braked_by_fleet(kv):
            # the row is newer and says go, but /pause all still brakes the account and only
            # /go all lifts it: the row takes the effective state (paused, the safe side), so
            # the two agree from now on, and the owner is told
            actions.repair_brake(kv, repo, account.id, side="row", on=True, at=now,
                                 reason="repair: /pause all is on")  # fmt: skip
            lines.append(f"{account.id}: posting_state set to paused (/pause all is on)")
            if ops is not None:
                ops.alert(f"{account.id} was resumed in the database, but /pause all is still "
                          "on in the brake; send /go all to resume", "brake", account.id,
                          now=now)  # fmt: skip
        else:
            actions.repair_brake(kv, repo, account.id, side="key", on=row[0], at=row[1],
                                 reason="repair: posting_state is newer")  # fmt: skip
            lines.append(f"{account.id}: brake key set {'on' if row[0] else 'off'}")
    return lines


def prune_deliveries(db: Database, before: datetime) -> int:
    """Drop webhook deliveries older than `before` (the replay guard keeps 30 days)."""
    with db.begin() as conn:
        result = conn.execute(webhook_deliveries.delete()
                              .where(webhook_deliveries.c.received_at < before))  # fmt: skip
    return int(result.rowcount or 0)

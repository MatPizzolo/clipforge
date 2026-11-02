"""SQL behind the hook library (migration 0003, hooks spec §3). Plain functions on the caller's
`Connection`, so `SqlHookFreezer` can run them inside S3c's transaction. The one writer of these
tables is `hooks/library.py` (ratings and re-render add their own event kinds in HK-2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from clipforge.db.tables import (
    accounts,
    hook_events,
    hook_freezes,
    hook_pattern_versions,
    hook_patterns,
    hook_weights,
)
from clipforge.models import HookPattern, HookPatternVersion, HookRotation, HookStatus


def _pattern(row: Any) -> HookPattern:
    m = row._mapping
    return HookPattern(id=m["id"], account_id=m["account_id"], blueprint_name=m["blueprint_name"],
                       status=m["status"], current_version=m["current_version"],
                       control=m["control"])  # fmt: skip


def _version(row: Any) -> HookPatternVersion:
    m = row._mapping
    return HookPatternVersion(pattern_id=m["pattern_id"], n=m["n"], data=m["data"],
                              author=m["author"], note=m["note"],
                              created_at=m["created_at"])  # fmt: skip


def account_blueprint(conn: Connection, account_id: str) -> tuple[bool, str | None]:
    """(the account exists, its blueprint)."""
    row = conn.execute(select(accounts.c.blueprint).where(accounts.c.id == account_id)).first()
    return (False, None) if row is None else (True, row.blueprint)


def clips_accounts(conn: Connection) -> list[str]:
    rows = conn.execute(select(accounts.c.id).where(accounts.c.kind == "clips")
                        .order_by(accounts.c.id))  # fmt: skip
    return [r.id for r in rows]


def get_pattern(conn: Connection, pattern_id: str, *, lock: bool = False) -> HookPattern | None:
    query = select(hook_patterns).where(hook_patterns.c.id == pattern_id)
    row = conn.execute(query.with_for_update() if lock else query).first()
    return None if row is None else _pattern(row)


def get_version(conn: Connection, pattern_id: str, n: int) -> HookPatternVersion | None:
    row = conn.execute(select(hook_pattern_versions).where(
        hook_pattern_versions.c.pattern_id == pattern_id,
        hook_pattern_versions.c.n == n)).first()  # fmt: skip
    return None if row is None else _version(row)


def versions(conn: Connection, pattern_id: str) -> list[HookPatternVersion]:
    rows = conn.execute(select(hook_pattern_versions)
                        .where(hook_pattern_versions.c.pattern_id == pattern_id)
                        .order_by(hook_pattern_versions.c.n))  # fmt: skip
    return [_version(r) for r in rows]


def insert_pattern(conn: Connection, pattern: HookPattern, now: datetime) -> None:
    conn.execute(hook_patterns.insert().values(**pattern.model_dump(), created_at=now,
                                               updated_at=now))  # fmt: skip


def insert_version(conn: Connection, version: HookPatternVersion) -> None:
    conn.execute(hook_pattern_versions.insert().values(
        pattern_id=version.pattern_id, n=version.n, data=version.data.model_dump(mode="json"),
        author=version.author, note=version.note, created_at=version.created_at))  # fmt: skip


def set_current_version(conn: Connection, pattern_id: str, n: int, now: datetime) -> None:
    conn.execute(update(hook_patterns).where(hook_patterns.c.id == pattern_id)
                 .values(current_version=n, updated_at=now))  # fmt: skip


def set_status(conn: Connection, pattern_id: str, status: HookStatus, now: datetime) -> None:
    conn.execute(update(hook_patterns).where(hook_patterns.c.id == pattern_id)
                 .values(status=status, updated_at=now))  # fmt: skip


def set_scope(conn: Connection, pattern_id: str, blueprint: str, now: datetime) -> None:
    """Move an account pattern to its blueprint (spec §4.5)."""
    conn.execute(update(hook_patterns).where(hook_patterns.c.id == pattern_id)
                 .values(account_id=None, blueprint_name=blueprint, updated_at=now))  # fmt: skip


def get_weight(conn: Connection, account_id: str, pattern_id: str) -> float | None:
    return conn.execute(select(hook_weights.c.weight).where(
        hook_weights.c.account_id == account_id,
        hook_weights.c.pattern_id == pattern_id)).scalar_one_or_none()  # fmt: skip


def upsert_weight(conn: Connection, account_id: str, pattern_id: str, weight: float, actor: str,
                  now: datetime) -> None:  # fmt: skip
    values = {"weight": weight, "updated_by": actor, "updated_at": now}
    conn.execute(insert(hook_weights).values(account_id=account_id, pattern_id=pattern_id,
                                             **values)
                 .on_conflict_do_update(index_elements=["account_id", "pattern_id"],
                                        set_=values))  # fmt: skip


def has_weights(conn: Connection, account_id: str) -> bool:
    count = conn.execute(select(func.count()).select_from(hook_weights)
                         .where(hook_weights.c.account_id == account_id)).scalar_one()  # fmt: skip
    return bool(count)


def insert_event(conn: Connection, at: datetime, actor: str, kind: str, data: dict[str, Any], *,
                 account_id: str | None = None, pattern_id: str | None = None) -> None:  # fmt: skip
    conn.execute(hook_events.insert().values(at=at, actor=actor, kind=kind, data=data,
                                             account_id=account_id,
                                             pattern_id=pattern_id))  # fmt: skip


def patterns_for(
    conn: Connection, account_id: str, blueprint: str | None
) -> list[tuple[HookPattern, HookPatternVersion, float]]:
    """The account's own patterns and those shared to its blueprint, each at its current
    version, with the account's weight (0.0 without a row), oldest first."""
    scope = hook_patterns.c.account_id == account_id
    if blueprint is not None:
        scope = or_(scope, hook_patterns.c.blueprint_name == blueprint)
    query = (
        select(hook_patterns, hook_pattern_versions.c.n, hook_pattern_versions.c.data,
               hook_pattern_versions.c.author, hook_pattern_versions.c.note,
               hook_pattern_versions.c.created_at.label("version_at"), hook_weights.c.weight)
        .join(hook_pattern_versions, and_(
            hook_pattern_versions.c.pattern_id == hook_patterns.c.id,
            hook_pattern_versions.c.n == hook_patterns.c.current_version))
        .outerjoin(hook_weights, and_(hook_weights.c.pattern_id == hook_patterns.c.id,
                                      hook_weights.c.account_id == account_id))
        .where(scope)
        .order_by(hook_patterns.c.created_at, hook_patterns.c.id)
    )  # fmt: skip
    out = []
    for row in conn.execute(query):
        m = row._mapping
        version = HookPatternVersion(pattern_id=m["id"], n=m["n"], data=m["data"],
                                     author=m["author"], note=m["note"],
                                     created_at=m["version_at"])  # fmt: skip
        out.append((_pattern(row), version, float(m["weight"] or 0.0)))
    return out


def open_freeze_row(conn: Connection, account_id: str) -> tuple[int, HookRotation] | None:
    """(experiment id, the frozen rotation) of the account's open freeze."""
    row = conn.execute(select(hook_freezes.c.experiment_id, hook_freezes.c.rotation).where(
        hook_freezes.c.account_id == account_id,
        hook_freezes.c.released_at.is_(None))).first()  # fmt: skip
    if row is None:
        return None
    return int(row.experiment_id), HookRotation.model_validate(row.rotation)


def insert_freeze(conn: Connection, rotation: HookRotation, experiment_id: int, actor: str,
                  now: datetime) -> None:  # fmt: skip
    conn.execute(hook_freezes.insert().values(
        account_id=rotation.account_id, experiment_id=experiment_id,
        rotation=rotation.model_dump(mode="json"), frozen_at=now, frozen_by=actor))  # fmt: skip


def close_freeze(conn: Connection, account_id: str, experiment_id: int, actor: str,
                 now: datetime) -> bool:  # fmt: skip
    query = update(hook_freezes).where(
        hook_freezes.c.account_id == account_id, hook_freezes.c.experiment_id == experiment_id,
        hook_freezes.c.released_at.is_(None))  # fmt: skip
    result = conn.execute(query.values(released_at=now, released_by=actor))
    return bool(result.rowcount)

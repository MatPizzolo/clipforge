"""The hook library (ADR-50, hooks spec §4): the one writer of `hook_patterns`,
`hook_pattern_versions`, `hook_weights`, `hook_freezes` and their `hook_events` (kinds seeded,
created, version, approved, retired, shared, weight, frozen, released). Every change and its
event go in one transaction, with a checked actor."""

from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection

from clipforge import actors
from clipforge.db import hooks as sql
from clipforge.db.engine import Database
from clipforge.hooks.rotation import resolve
from clipforge.models import (
    HookFit,
    HookPattern,
    HookPatternData,
    HookPatternVersion,
    HookRotation,
    HookStatus,
)

FREEZE_ACTOR = "system:experiment"  # the protocol carries no actor (spec §4.4)
SEED_ACTOR = "system:migration"


class HookError(ValueError):
    """A change the library refuses; the message is safe to show (the API answers 400)."""


class HookNotFound(HookError):
    """An unknown account or pattern, or a pattern the account can't see (the API answers 404)."""


def _actor(actor: str) -> str:
    try:
        return actors.checked(actor)
    except ValueError as exc:
        raise HookError(str(exc)) from None


def new_pattern_id() -> str:
    return "hp_" + secrets.token_hex(4)


class HookLibrary:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- reads

    def patterns(self, account_id: str) -> list[tuple[HookPattern, HookPatternVersion, float]]:
        """The account's own and blueprint-shared patterns at their current versions, with the
        account's weight (0.0 without one)."""
        with self.db.begin() as conn:
            return sql.patterns_for(conn, account_id, self._blueprint(conn, account_id))

    def versions(self, pattern_id: str) -> tuple[HookPattern, list[HookPatternVersion]]:
        with self.db.begin() as conn:
            return self._pattern(conn, pattern_id), sql.versions(conn, pattern_id)

    def clips_accounts(self) -> list[str]:
        """The accounts `hooks seed` covers by default."""
        with self.db.begin() as conn:
            return sql.clips_accounts(conn)

    def open_freeze(self, account_id: str) -> HookRotation | None:
        with self.db.begin() as conn:
            row = sql.open_freeze_row(conn, account_id)
        return None if row is None else row[1]

    def rotation_for(self, account_id: str, producer: HookFit) -> HookRotation:
        """The rotation a new job freezes (spec §4.2): an open freeze's snapshot, else the live
        library. An empty rotation (every pattern retired or at weight 0) is valid."""
        with self.db.begin() as conn:
            return self.live_rotation(conn, account_id, producer, use_freeze=True)

    def live_rotation(
        self, conn: Connection, account_id: str, producer: HookFit, *, use_freeze: bool
    ) -> HookRotation:
        freeze = sql.open_freeze_row(conn, account_id) if use_freeze else None
        rows = sql.patterns_for(conn, account_id, self._blueprint(conn, account_id))
        weights = {p.id: w for p, _, w in rows}
        pairs = [(p, v) for p, v, _ in rows]
        return resolve(account_id, producer, pairs, weights, None if freeze is None else freeze[1])

    # ---- writes

    def create_draft(
        self,
        account_id: str,
        data: HookPatternData,
        actor: str,
        now: datetime,
        *,
        control: bool = False,
    ) -> HookPattern:
        actor = _actor(actor)
        with self.db.begin() as conn:
            self._blueprint(conn, account_id)
            return self._create(conn, account_id, data, actor, now, "draft", control)

    def edit(
        self, pattern_id: str, data: HookPatternData, note: str | None, actor: str, now: datetime
    ) -> HookPatternVersion:
        """A new version (v+1); older versions stay, and running jobs keep the one they froze."""
        actor = _actor(actor)
        note = note.strip() if note and note.strip() else None
        with self.db.begin() as conn:
            pattern = self._pattern(conn, pattern_id, lock=True)
            n = pattern.current_version + 1
            version = HookPatternVersion(pattern_id=pattern_id, n=n, data=data, author=actor,
                                         note=note, created_at=now)  # fmt: skip
            sql.insert_version(conn, version)
            sql.set_current_version(conn, pattern_id, n, now)
            sql.insert_event(conn, now, actor, "version",
                             {"from": pattern.current_version, "to": n, "note": note},
                             pattern_id=pattern_id)  # fmt: skip
        return version

    def approve(
        self, pattern_id: str, account_id: str, actor: str, now: datetime, weight: float = 1.0
    ) -> HookPattern:
        actor = _actor(actor)
        _check_weight(weight)
        with self.db.begin() as conn:
            pattern = self._visible(conn, pattern_id, account_id)
            before = sql.get_weight(conn, account_id, pattern_id)
            sql.set_status(conn, pattern_id, "approved", now)
            sql.upsert_weight(conn, account_id, pattern_id, weight, actor, now)
            sql.insert_event(conn, now, actor, "approved",
                             {"from": pattern.status, "weight": weight},
                             account_id=account_id, pattern_id=pattern_id)  # fmt: skip
            if before != weight:
                sql.insert_event(conn, now, actor, "weight",
                                 {"from": before, "to": weight, "reason": "approved"},
                                 account_id=account_id, pattern_id=pattern_id)  # fmt: skip
            return pattern.model_copy(update={"status": "approved"})

    def retire(self, pattern_id: str, account_id: str, actor: str, now: datetime) -> HookPattern:
        """Out of this account's rotation (weight 0); history stays, and it can be approved
        again. An account's own pattern becomes `retired`; a pattern shared to the blueprint
        keeps its status, so retiring it on one account never takes it from the others."""
        actor = _actor(actor)
        with self.db.begin() as conn:
            pattern = self._visible(conn, pattern_id, account_id)
            before = sql.get_weight(conn, account_id, pattern_id)
            if pattern.account_id is not None:
                sql.set_status(conn, pattern_id, "retired", now)
                pattern = pattern.model_copy(update={"status": "retired"})
            sql.upsert_weight(conn, account_id, pattern_id, 0.0, actor, now)
            sql.insert_event(conn, now, actor, "retired",
                             {"status": pattern.status, "shared": pattern.account_id is None},
                             account_id=account_id, pattern_id=pattern_id)  # fmt: skip
            sql.insert_event(conn, now, actor, "weight",
                             {"from": before, "to": 0.0, "reason": "retired"},
                             account_id=account_id, pattern_id=pattern_id)  # fmt: skip
            return pattern

    def share(self, pattern_id: str, actor: str, now: datetime) -> HookPattern:
        """Move an account pattern to its account's blueprint: the other accounts on it see it
        at weight 0 (spec §4.5)."""
        actor = _actor(actor)
        with self.db.begin() as conn:
            pattern = self._pattern(conn, pattern_id, lock=True)
            if pattern.account_id is None:
                raise HookError(f"{pattern_id} is already shared to {pattern.blueprint_name}")
            if pattern.control:
                raise HookError("the control is each account's own baseline; it isn't shared")
            blueprint = self._blueprint(conn, pattern.account_id)
            if blueprint is None:
                raise HookError(f"{pattern.account_id} has no blueprint to share to")
            sql.set_scope(conn, pattern_id, blueprint, now)
            sql.insert_event(conn, now, actor, "shared",
                             {"from": pattern.account_id, "to": blueprint},
                             account_id=pattern.account_id, pattern_id=pattern_id)  # fmt: skip
            return pattern.model_copy(update={"account_id": None, "blueprint_name": blueprint})

    def set_weight(
        self,
        account_id: str,
        pattern_id: str,
        weight: float,
        reason: str,
        actor: str,
        now: datetime,
    ) -> float:
        """Only an owner tap changes a weight (spec §4.3); during a freeze it is saved and
        applies at release."""
        actor = _actor(actor)
        _check_weight(weight)
        if not reason or not reason.strip():
            raise HookError("a weight change needs a reason")
        with self.db.begin() as conn:
            self._visible(conn, pattern_id, account_id)
            before = sql.get_weight(conn, account_id, pattern_id)
            sql.upsert_weight(conn, account_id, pattern_id, weight, actor, now)
            sql.insert_event(conn, now, actor, "weight",
                             {"from": before, "to": weight, "reason": reason.strip()},
                             account_id=account_id, pattern_id=pattern_id)  # fmt: skip
        return weight

    def seed_patterns(
        self,
        account_id: str,
        bodies: list[tuple[bool, HookPatternData]],
        now: datetime,
        *,
        after: Callable[[Connection], None] | None = None,
    ) -> int:
        """`hooks/seeds.py`'s write: approved patterns at weight 1.0, version 1, by
        `system:migration`, then `after` (the freezes) on the same transaction. An account with
        any pattern is skipped (0)."""
        with self.db.begin() as conn:
            blueprint = self._blueprint(conn, account_id)
            if sql.patterns_for(conn, account_id, blueprint):
                return 0
            for control, data in bodies:
                pattern = self._create(conn, account_id, data, SEED_ACTOR, now, "approved",
                                       control, kind="seeded")  # fmt: skip
                sql.upsert_weight(conn, account_id, pattern.id, 1.0, SEED_ACTOR, now)
            if after is not None:
                after(conn)
        return len(bodies)

    # ---- helpers

    def _create(self, conn: Connection, account_id: str, data: HookPatternData, actor: str,
                now: datetime, status: HookStatus, control: bool, *,
                kind: str = "created") -> HookPattern:  # fmt: skip
        pattern = HookPattern(id=new_pattern_id(), account_id=account_id, blueprint_name=None,
                              status=status, current_version=1, control=control)  # fmt: skip
        sql.insert_pattern(conn, pattern, now)
        first = HookPatternVersion(pattern_id=pattern.id, n=1, data=data, author=actor,
                                   note=None, created_at=now)  # fmt: skip
        sql.insert_version(conn, first)
        sql.insert_event(conn, now, actor, kind, {"name": data.name, "control": control},
                         account_id=account_id, pattern_id=pattern.id)  # fmt: skip
        return pattern

    def _blueprint(self, conn: Connection, account_id: str) -> str | None:
        exists, blueprint = sql.account_blueprint(conn, account_id)
        if not exists:
            raise HookNotFound(f"no account {account_id}")
        return blueprint

    def _pattern(self, conn: Connection, pattern_id: str, *, lock: bool = False) -> HookPattern:
        pattern = sql.get_pattern(conn, pattern_id, lock=lock)
        if pattern is None:
            raise HookNotFound(f"no pattern {pattern_id}")
        return pattern

    def _visible(self, conn: Connection, pattern_id: str, account_id: str) -> HookPattern:
        """The pattern, locked, when it is the account's own or shared to its blueprint."""
        blueprint = self._blueprint(conn, account_id)
        pattern = self._pattern(conn, pattern_id, lock=True)
        if pattern.account_id != account_id and (
            pattern.blueprint_name is None or pattern.blueprint_name != blueprint
        ):
            raise HookNotFound(f"no pattern {pattern_id} for {account_id}")
        return pattern


def _check_weight(weight: float) -> None:
    if not math.isfinite(weight) or weight < 0 or weight > 100:
        raise HookError("a weight is a number from 0 to 100")


class SqlHookFreezer:
    """`hooks/freezer.HookFreezer` on `hook_freezes` (spec §4.4). Runs on the caller's
    connection, so the freeze commits or rolls back with S3c's experiment write; idempotent."""

    def __init__(self, library: HookLibrary, producer: HookFit = "clips") -> None:
        self.library = library
        self.producer = producer

    def freeze(self, conn: Connection, account_id: str, experiment_id: int) -> None:
        if not sql.has_weights(conn, account_id):
            return None  # no library yet: nothing to freeze
        open_ = sql.open_freeze_row(conn, account_id)
        if open_ is not None:
            if open_[0] == experiment_id:
                return None
            raise HookError(f"{account_id}'s hooks are already frozen by experiment {open_[0]}")
        now = datetime.now(UTC)
        live = self.library.live_rotation(conn, account_id, self.producer, use_freeze=False)
        rotation = live.model_copy(update={"frozen_by": experiment_id})
        sql.insert_freeze(conn, rotation, experiment_id, FREEZE_ACTOR, now)
        sql.insert_event(conn, now, FREEZE_ACTOR, "frozen",
                         {"experiment_id": experiment_id, "rotation_id": rotation.id},
                         account_id=account_id)  # fmt: skip

    def release(self, conn: Connection, account_id: str, experiment_id: int) -> None:
        now = datetime.now(UTC)
        if sql.close_freeze(conn, account_id, experiment_id, FREEZE_ACTOR, now):
            sql.insert_event(conn, now, FREEZE_ACTOR, "released",
                             {"experiment_id": experiment_id}, account_id=account_id)  # fmt: skip

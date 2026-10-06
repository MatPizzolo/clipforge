"""Accounts and their runtime posting state (spec §3). `posting_state` has one writer:
/pause and /go (through set_paused); account edits never touch it."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from clipforge.actors import checked
from clipforge.db.autopilot import insert_seed
from clipforge.db.engine import Database
from clipforge.db.tables import accounts, posting_state
from clipforge.models import Account, Autopilot

UNIQUE_VIOLATION = "23505"  # Postgres SQLSTATE


class AccountExists(ValueError):
    pass


def _row(account: Account) -> dict[str, Any]:
    data = account.model_dump(mode="json")
    return {key: data[key] for key in (
        "id", "blueprint", "blueprint_version", "kind", "language", "niche", "review_tier",
        "persona_id", "paired_account_id", "monthly_budget_usd", "platforms", "brand", "posting",
        "publisher",
    )}  # fmt: skip


def _account(row: Any) -> Account:
    values = dict(row._mapping)
    values.pop("created_at"), values.pop("updated_at")
    return Account.model_validate(values)


class AccountsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self, account: Account, now: datetime, *, autopilot: Autopilot | None = None,
        actor: str | None = None,
    ) -> None:  # fmt: skip
        """With `autopilot`, the account's first autopilot row and its seed event are inserted
        in the same transaction (S2 spec §3), by `actor` (checked first: a bad actor is a
        ValueError, never read as an existing account)."""
        seed_actor = None
        if autopilot is not None:
            seed_actor = checked(actor or autopilot.updated_by)
            checked(autopilot.updated_by)
        try:
            with self.db.begin() as conn:
                conn.execute(
                    accounts.insert().values(**_row(account), created_at=now, updated_at=now)
                )
                conn.execute(posting_state.insert().values(account_id=account.id, paused=False,
                                                           changed_at=now))  # fmt: skip
                if autopilot is not None:
                    assert seed_actor is not None
                    insert_seed(conn, autopilot, seed_actor, "account created", now)
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
                raise  # a check or foreign-key failure is a bug, not an existing account
            raise AccountExists(f"account {account.id!r} already exists") from None

    def get(self, account_id: str) -> Account | None:
        with self.db.begin() as conn:
            row = conn.execute(select(accounts).where(accounts.c.id == account_id)).first()
        return None if row is None else _account(row)

    def list(self) -> list[Account]:
        with self.db.begin() as conn:
            rows = conn.execute(select(accounts).order_by(accounts.c.id)).all()
        return [_account(row) for row in rows]

    def update(self, account: Account, now: datetime) -> None:
        values = _row(account)
        values.pop("id")
        with self.db.begin() as conn:
            conn.execute(accounts.update().where(accounts.c.id == account.id)
                         .values(**values, updated_at=now))  # fmt: skip

    def paused(self, account_id: str) -> bool:
        with self.db.begin() as conn:
            value = conn.execute(
                select(posting_state.c.paused).where(posting_state.c.account_id == account_id)
            ).scalar()
        return bool(value)

    def paused_state(self, account_id: str) -> tuple[bool, datetime] | None:
        """`(paused, changed_at)`, or None when the account has no row (the brake repair)."""
        with self.db.begin() as conn:
            columns = (posting_state.c.paused, posting_state.c.changed_at)
            row = conn.execute(
                select(*columns).where(posting_state.c.account_id == account_id)
            ).first()
        return None if row is None else (bool(row.paused), row.changed_at)

    def set_paused(
        self, account_id: str, on: bool, now: datetime, actor: str | None = None,
        reason: str | None = None,
    ) -> None:  # fmt: skip
        values = {"paused": on, "changed_at": now, "changed_by": actor, "reason": reason}
        statement = insert(posting_state).values(account_id=account_id, **values)
        statement = statement.on_conflict_do_update(
            index_elements=[posting_state.c.account_id], set_=values
        )
        with self.db.begin() as conn:
            conn.execute(statement)

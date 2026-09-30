"""Accounts and their runtime posting state (spec §3). `posting_state` has one writer:
/pause and /go (through set_paused); account edits never touch it."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from clipforge.db.engine import Database
from clipforge.db.tables import accounts, posting_state
from clipforge.models import Account


class AccountExists(ValueError):
    pass


def _row(account: Account) -> dict[str, Any]:
    data = account.model_dump(mode="json")
    return {key: data[key] for key in (
        "id", "blueprint", "blueprint_version", "kind", "language", "niche", "review_tier",
        "persona_id", "paired_account_id", "monthly_budget_usd", "platforms", "brand", "posting",
    )}  # fmt: skip


def _account(row: Any) -> Account:
    values = dict(row._mapping)
    values.pop("created_at"), values.pop("updated_at")
    return Account.model_validate(values)


class AccountsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, account: Account, now: datetime) -> None:
        try:
            with self.db.begin() as conn:
                conn.execute(
                    accounts.insert().values(**_row(account), created_at=now, updated_at=now)
                )
                conn.execute(posting_state.insert().values(account_id=account.id, paused=False,
                                                           changed_at=now))  # fmt: skip
        except IntegrityError:
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

    def set_paused(self, account_id: str, on: bool, now: datetime) -> None:
        statement = insert(posting_state).values(account_id=account_id, paused=on, changed_at=now)
        statement = statement.on_conflict_do_update(
            index_elements=[posting_state.c.account_id], set_={"paused": on, "changed_at": now}
        )
        with self.db.begin() as conn:
            conn.execute(statement)

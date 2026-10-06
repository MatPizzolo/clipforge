"""Autopilot rows and their append-only history (S2 spec §3, §5.4). SQL only: the one writer is
`accounts/autopilot.py` (and account create, which seeds the row in its own transaction)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from clipforge.db.engine import Database
from clipforge.db.tables import autopilot, autopilot_events
from clipforge.models import Autopilot, AutopilotEvent

# the controls whose changes are logged one event per field (preset included)
FIELDS = ("preset", "produce", "review_dial", "publish", "scale", "runway_days",
          "batch_line_usd", "monthly_cap_usd")  # fmt: skip


def as_text(value: object) -> str:
    """Event values as JSON text, lower-case: "true", "sample", "7", "2.0"."""
    return value if isinstance(value, str) else json.dumps(value)


def _row(ap: Autopilot) -> dict[str, Any]:
    return ap.model_dump()


def insert_seed(
    conn: Connection, ap: Autopilot, actor: str, reason: str | None, now: datetime
) -> None:
    """The row a new account starts with, and its one `preset` event (inside the caller's
    transaction: account create)."""
    conn.execute(autopilot.insert().values(**_row(ap)))
    conn.execute(autopilot_events.insert().values(
        account_id=ap.account_id, at=now, actor=actor, field="preset", from_value=None,
        to_value=ap.preset, reason=reason))  # fmt: skip


class AutopilotRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, account_id: str) -> Autopilot | None:
        with self.db.begin() as conn:
            row = conn.execute(
                select(autopilot).where(autopilot.c.account_id == account_id)
            ).first()
        return None if row is None else Autopilot.model_validate(dict(row._mapping))

    def all(self) -> dict[str, Autopilot]:
        with self.db.begin() as conn:
            rows = conn.execute(select(autopilot)).all()
        return {r.account_id: Autopilot.model_validate(dict(r._mapping)) for r in rows}

    def history(self, account_id: str) -> list[AutopilotEvent]:
        with self.db.begin() as conn:
            rows = conn.execute(select(autopilot_events)
                                .where(autopilot_events.c.account_id == account_id)
                                .order_by(autopilot_events.c.id)).all()  # fmt: skip
        return [AutopilotEvent.model_validate({k: v for k, v in r._mapping.items() if k != "id"})
                for r in rows]  # fmt: skip

    def upsert_with_events(
        self, before: Autopilot, after: Autopilot, actor: str, reason: str | None, now: datetime
    ) -> list[str]:
        """Write `after` and one event per changed field, in one transaction. Returns the
        changed fields (the preset last, so the history reads "publish, then preset")."""
        changed = [f for f in FIELDS if f != "preset" and getattr(before, f) != getattr(after, f)]
        if before.preset != after.preset:
            changed.append("preset")
        if not changed:
            return []
        values = _row(after)
        statement = insert(autopilot).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[autopilot.c.account_id],
            set_={k: statement.excluded[k] for k in values if k != "account_id"},
        )
        with self.db.begin() as conn:
            conn.execute(statement)
            conn.execute(autopilot_events.insert(), [{
                "account_id": after.account_id, "at": now, "actor": actor, "field": f,
                "from_value": as_text(getattr(before, f)), "to_value": as_text(getattr(after, f)),
                "reason": reason,
            } for f in changed])  # fmt: skip
        return changed

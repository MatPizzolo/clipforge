"""Hook library helpers for DB tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from clipforge.db.engine import Database
from clipforge.hooks.library import HookLibrary
from clipforge.models import HookPattern, HookPatternData

NOW = datetime(2026, 10, 3, 9, tzinfo=UTC)
DATA = HookPatternData(name="Open question", structure="A question the clip answers",
                       examples={"en": "WHY DID HE WALK AWAY?"}, fits=["clips"],
                       max_words=8)  # fmt: skip


def approved(lib: HookLibrary, account: str = "realtalk-clips-en") -> HookPattern:
    p = lib.create_draft(account, DATA, "web:mat", NOW)
    return lib.approve(p.id, account, "web:mat", NOW)


def version_count(db: Database, pattern_id: str) -> int:
    with db.begin() as conn:
        query = text("select count(*) from hook_pattern_versions where pattern_id = :p")
        return int(conn.execute(query, {"p": pattern_id}).scalar_one())


def last_event(db: Database, kind: str) -> Any:
    with db.begin() as conn:
        return conn.execute(text("select * from hook_events where kind = :k"
                                 " order by id desc limit 1"), {"k": kind}).one()  # fmt: skip


def open_freeze_count(db: Database) -> int:
    with db.begin() as conn:
        return int(conn.execute(text("select count(*) from hook_freezes"
                                     " where released_at is null")).scalar_one())  # fmt: skip

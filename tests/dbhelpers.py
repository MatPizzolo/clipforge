"""Rows for DB tests."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import (
    LEGACY_PLATFORMS,
    Account,
    Platform,
    PlatformProfile,
    PostingSchedule,
    Source,
    SourcePermission,
)  # fmt: skip

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
BILLY_SOURCE = Source(id="billy-garton", account_id="realtalk-clips-en",
                      credit_name="Billy Garton Jr.",
                      permission=SourcePermission(type="creator_agreement"))  # fmt: skip


def make_account(
    id: str = "realtalk-clips-en",
    *,
    chat_id: int | None = None,
    slots: Iterable[str] = ("08:00",),
    platforms: Iterable[Platform] = LEGACY_PLATFORMS,
    timezone: str = "America/New_York",
) -> Account:
    return Account(
        id=id, blueprint="realtalk-clips", blueprint_version=1, kind="clips", language="en",
        niche="test", platforms={p: PlatformProfile(handle="h.test") for p in platforms},
        posting=PostingSchedule(chat_id=chat_id, timezone=timezone, slots=list(slots)),
    )  # fmt: skip


def seed(db: Database, *accounts: Account, sources: Iterable[Source] = ()) -> None:
    repo = AccountsRepo(db)
    for account in accounts:
        repo.create(account, NOW)
    if sources:
        from clipforge.db.sources import SourcesRepo  #

        for source in sources:
            SourcesRepo(db).create(source, "test", NOW)


def insert_account(
    db: Database, account_id: str, blueprint: str = "realtalk-clips", kind: str = "clips"
) -> None:
    """A minimal account row (no autopilot), for tables that only need the FK."""
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(text("insert into accounts (id, blueprint, blueprint_version, kind,"
                          " language, niche, review_tier, monthly_budget_usd, platforms, brand,"
                          " posting, created_at, updated_at) values (:id, :b, 1, :k, 'en',"
                          " 'n', 'review', 0, '{}', '{}', '{}', now(), now())"),
                     {"id": account_id, "b": blueprint, "k": kind})  # fmt: skip


def insert_item(db: Database, item_id: str, account: str = "realtalk-clips-en") -> None:
    """A minimal content_items row with the columns 0001 and 0002 require."""
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(text("insert into content_items (id, account_id, producer, producer_version,"
                          " language, media_kind, image_paths, title, hook, score, credits,"
                          " ai_disclosure, sponsored, cost_usd, queued_at) values (:id, :a,"
                          " 'clips', 'v', 'en', 'video', '[]', 't', 'h', 0.9, '[]', false, false,"
                          " 0, now())"), {"id": item_id, "a": account})  # fmt: skip

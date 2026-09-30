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

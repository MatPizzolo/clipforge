"""Small source and account builders for gate and routing tests."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from clipforge.models import Account, Permission, Platform, Source, SourcePermission
from tests.dbhelpers import make_account


def source(
    kind: Literal["channel", "own"] = "channel", expires_at: datetime | None = None,
    platforms: list[Platform] | None = None,
) -> Source:  # fmt: skip
    """billy-garton on all four platforms: a creator agreement (or `own`)."""
    permission = SourcePermission(
        type=Permission.OWN if kind == "own" else Permission("creator_agreement"),
        platforms=platforms or list(Platform), expires_at=expires_at,
    )  # fmt: skip
    return Source(id="billy-garton", account_id="realtalk-clips-en", kind=kind,
                  credit_name="Billy Garton Jr.", permission=permission)  # fmt: skip


def account(id: str = "realtalk-clips-en") -> Account:
    return make_account(id, platforms=list(Platform))

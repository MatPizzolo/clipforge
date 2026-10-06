"""Autopilot rows for routing tests."""

from __future__ import annotations

from datetime import UTC, datetime

from clipforge.models import Autopilot, ReviewDial


def autopilot(dial: ReviewDial = "auto", account_id: str = "realtalk-clips-en") -> Autopilot:
    at = datetime(2026, 10, 1, tzinfo=UTC)
    return Autopilot(account_id=account_id, review_dial=dial, monthly_cap_usd=5.0,
                     updated_by="cli:mat", updated_at=at)  # fmt: skip

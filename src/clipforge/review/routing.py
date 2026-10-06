"""Routing (ADR-29, ADR-48, ADR-49; S2 spec §5.2): pure. Every reason that applies is recorded;
any one sends the item to the review lane.

What counts toward the windows (R2, R6; log #454): decisions a person made through the review
service (`approved` or `reviewed` events by an actor that isn't `system:`). Assisted-card taps
never count, so counting starts at S2b."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from clipforge.models import Autopilot, ContentItem, GateResult, ReviewReason, Routing

PRODUCER_WINDOW, FORMAT_WINDOW, DUB_WINDOW = 5, 10, 10  # ADR-49, ADR-42, ADR-48
SPONSORED_DAYS = timedelta(days=30)
SPOT_EVERY = 9  # 9 auto items since the last spot check: the next one is a check
SPOT_WEEKLY = 3  # fewer than 3 checks in 7 days ...
SPOT_GAP = timedelta(hours=24)  # ... and none in the last 24 h: the next one is a check


@dataclass(frozen=True)
class WindowCounts:
    producer: dict[str, int] = field(default_factory=dict)  # counted decisions per version
    format_version: int | None = None  # the latest format-change setup version (S3c)
    format_count: int = 0  # counted decisions since it
    dubs_in_pair: int = 0  # counted dub decisions in the EN/ES pair (S10)


@dataclass(frozen=True)
class SpotState:
    auto_since_last: int  # auto-routed items since the last spot check
    checks_last_7d: int
    last_check_at: datetime | None


class FormatWindowSource(Protocol):
    """The account's latest format-change setup version and the counted decisions since it, or
    None. S3c-2 wires `SetupRepo` in `runtime.build_deps` (log #142)."""

    def format_window(self, account_id: str) -> tuple[int, int] | None: ...


class NoFormatWindow:
    """Until S3c's `account_versions` exists, the format window is always closed."""

    def format_window(self, account_id: str) -> tuple[int, int] | None:
        return None


def route(
    item: ContentItem,
    autopilot: Autopilot,
    gate_result: GateResult,
    counts: WindowCounts,
    spot: SpotState,
    *,
    first_post_at: datetime | None,
    paired_account_id: str | None,
    parent_account_id: str | None,
    now: datetime,
) -> Routing:
    reasons: list[ReviewReason] = []
    window: str | None = None
    if gate_result.violations:
        reasons.append("gate")
    if item.sponsored and (first_post_at is None or now - first_post_at < SPONSORED_DAYS):
        reasons.append("sponsored")
    done = counts.producer.get(item.producer_version, 0)
    if done < PRODUCER_WINDOW:
        reasons.append("producer_window")
        window = f"producer:{item.producer_version}:{done}/{PRODUCER_WINDOW}"
    if counts.format_version is not None and counts.format_count < FORMAT_WINDOW:
        reasons.append("format_window")
        window = window or f"format:v{counts.format_version}:{counts.format_count}/{FORMAT_WINDOW}"
    is_dub = (item.parent_item_id is not None and parent_account_id is not None
              and parent_account_id == paired_account_id)  # fmt: skip
    if is_dub and counts.dubs_in_pair < DUB_WINDOW:
        reasons.append("dub_window")
        window = window or f"dub:{counts.dubs_in_pair}/{DUB_WINDOW}"
    dial = autopilot.review_dial
    if dial == "review":
        reasons.append("dial")
    elif dial == "sample" and spot_check(spot, now):
        reasons.append("spot_check")
    return Routing(lane="review" if reasons else "auto", reasons=reasons, dial=dial,
                   window=window, gate=gate_result)  # fmt: skip


def spot_check(spot: SpotState, now: datetime) -> bool:
    """Deterministic, so tests replay it: at least 1 in 10 and at least 3 a week (S3 §2.4)."""
    if spot.auto_since_last >= SPOT_EVERY:
        return True
    return spot.checks_last_7d < SPOT_WEEKLY and (
        spot.last_check_at is None or now - spot.last_check_at >= SPOT_GAP
    )

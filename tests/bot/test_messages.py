"""Bot texts."""

from __future__ import annotations

from datetime import UTC, datetime

from clipforge.bot.messages import posting_overview_text
from clipforge.models import AccountPosting, ChannelProgress, PostingOverview, PostStatus


def test_posting_overview_text() -> None:
    view = PostingOverview(
        enabled=True, paused=False, waiting=175, days_left=30, per_day=6,
        next_slot=datetime(2026, 9, 30, 17, 0, tzinfo=UTC),
        channels=[ChannelProgress(
            slug="billy-garton", name="Billy Garton Jr.", episodes_clipped=9,
            episodes_clipping=1, episodes_failed=1,
            counts={PostStatus.POSTED: 38, PostStatus.PARTLY_POSTED: 2, PostStatus.SENT: 1,
                    PostStatus.QUEUED: 171, PostStatus.SKIPPED: 4, PostStatus.REJECTED: 7},
        )],
    )  # fmt: skip
    text = posting_overview_text(view, "America/New_York")
    assert text.splitlines() == [
        "Billy Garton Jr. — 11 episodes (9 clipped · 1 clipping · 1 failed)",
        "  posted 38 · partly 2 · waiting on you 1 · queued 171 · skipped 4 · rejected 7",
        "Queue: 175 clips ≈ 30 days at 6/day · next slot Wed 30 Sep 13:00",
    ]


def test_posting_overview_text_off_paused_and_empty() -> None:
    off = PostingOverview(enabled=False, paused=False, channels=[], waiting=0, days_left=0,
                          per_day=6, next_slot=None)  # fmt: skip
    assert posting_overview_text(off, "UTC").splitlines() == [
        "No channel clips yet. Add videos to videos/<channel>/ and run `clipforge clip`.",
        "Posting is off (set POSTING_CHAT_ID).",
    ]
    paused = off.model_copy(update={"enabled": True, "paused": True})
    assert posting_overview_text(paused, "UTC").splitlines()[-1] == "Paused. Send /go to restart."


def test_posting_overview_text_names_a_config_problem() -> None:
    view = PostingOverview(enabled=False, paused=False, channels=[], waiting=0, days_left=0,
                           per_day=6, next_slot=None,
                           problem="POSTING_SLOTS: slots must be HH:MM, e.g. 08:00")  # fmt: skip
    assert posting_overview_text(view, "UTC").splitlines()[-1] == (
        "Posting is off: POSTING_SLOTS: slots must be HH:MM, e.g. 08:00"
    )


def test_overview_text_one_block_per_account_when_several() -> None:
    view = PostingOverview(enabled=True, paused=False, channels=[], waiting=0, days_left=0,
                           per_day=1, next_slot=None, accounts=[
        AccountPosting(account_id="a", enabled=True, paused=False, per_day=1),
        AccountPosting(account_id="b", enabled=True, paused=True, per_day=1)])  # fmt: skip
    text = posting_overview_text(view)
    assert "▸ a" in text and "▸ b" in text and "Paused. Send /go b to restart." in text

"""Queue rules: derived status, eligibility, pick order, overlap, the pause count."""

from __future__ import annotations

from datetime import timedelta

from clipforge.models import LEGACY_PLATFORMS, Platform, PostRecord, PostStatus, PostVerdict
from clipforge.posting.queue import eligible, overlaps, pick_next, status, unanswered
from tests.posting.builders import T0, item, record, send

LATER = T0 + timedelta(hours=1)
OLD = T0 - timedelta(days=30)  # no fresh bonus


def test_status_branches() -> None:
    it = item()
    assert status(record(it)) is PostStatus.QUEUED
    assert status(record(it, sends=[send()])) is PostStatus.SENT
    assert status(record(it, sends=[send()], posted=[Platform.TIKTOK])) is PostStatus.PARTLY_POSTED
    assert status(record(it, posted=LEGACY_PLATFORMS)) is PostStatus.POSTED
    rejected = PostVerdict(kind="rejected", at=T0)
    assert status(record(it, posted=LEGACY_PLATFORMS, verdict=rejected)) is PostStatus.REJECTED
    assert status(record(it, unavailable=True)) is PostStatus.UNAVAILABLE


def test_skip_returns_after_24h_and_resend_counts() -> None:
    skipped = record(item(), sends=[send(1, T0)], verdict=PostVerdict(kind="skipped", at=LATER))
    assert status(skipped) is PostStatus.SKIPPED
    assert not eligible(skipped, LATER + timedelta(hours=23))
    assert eligible(skipped, LATER + timedelta(hours=24))
    resent = skipped.model_copy(update={"sends": [send(1, T0), send(2, LATER + timedelta(days=1))]})
    assert status(resent) is PostStatus.SENT
    assert unanswered([resent]) == [resent]


def test_unanswered_counts_only_untapped_sends() -> None:
    a = record(item("clip_01"), sends=[send()])
    b = record(item("clip_02"), sends=[send()], posted=[Platform.TIKTOK])
    c = record(item("clip_03"))
    assert unanswered([a, b, c]) == [a]


def _ids(rec: PostRecord | None) -> str:
    return rec.item.id if rec is not None else "none"


def test_pick_prefers_other_video_then_other_channel() -> None:
    a1 = record(item("clip_01", score=0.9, finished_at=OLD), sends=[send(1, T0)])  # last sent
    a2 = record(item("clip_02", score=0.89, finished_at=OLD, start=100, end=130))
    b = record(item("clip_01", job_id="20260928-bbbbbbbb-0001", source_hash="b" * 64,
                    score=0.8, finished_at=OLD))  # fmt: skip
    assert _ids(pick_next([a1, a2, b], LATER)) == b.item.id  # other video beats higher score
    c = record(item("clip_01", job_id="20260928-cccccccc-0001", source_hash="c" * 64,
                    channel="other", name="Other", score=0.7, finished_at=OLD))  # fmt: skip
    assert _ids(pick_next([a1, a2, b, c], LATER)) == c.item.id  # other channel beats both


def test_pick_uses_fresh_bonus_and_skips_ineligible() -> None:
    old = record(item("clip_01", score=0.88, finished_at=OLD))
    new = record(item("clip_01", job_id="20260928-bbbbbbbb-0001", source_hash="b" * 64,
                      score=0.85, finished_at=T0))  # fmt: skip
    assert _ids(pick_next([old, new], LATER)) == new.item.id
    rejected = record(item("clip_02", score=0.99), verdict=PostVerdict(kind="rejected", at=T0))
    assert _ids(pick_next([rejected], LATER)) == "none"


def test_overlaps_same_moment_unless_rejected() -> None:
    queued = record(item(start=100, end=130))
    assert overlaps(item("clip_05", job_id="20260929-aaaaaaaa-0002", start=101, end=131), [queued])
    assert not overlaps(item("clip_05", start=120, end=150), [queued])  # IoU 0.2
    assert not overlaps(item("clip_05", source_hash="b" * 64, start=100, end=130), [queued])
    rejected = queued.model_copy(update={"verdict": PostVerdict(kind="rejected", at=T0)})
    assert not overlaps(item("clip_05", start=100, end=130), [rejected])


def test_posted_means_every_platform_the_item_is_due_on() -> None:
    three = record(item(), posted=LEGACY_PLATFORMS)
    assert status(three) is PostStatus.POSTED  # facebook exists in Platform, but isn't due here
    four = record(item(), platforms=list(Platform), posted=LEGACY_PLATFORMS)
    assert status(four) is PostStatus.PARTLY_POSTED


def test_three_platform_clip_stays_posted_after_account_enables_facebook() -> None:
    # The account gains facebook later; the clip keeps the platforms it was queued on.
    rec = record(item(), platforms=LEGACY_PLATFORMS, posted=LEGACY_PLATFORMS)
    assert Platform.FACEBOOK in list(Platform) and status(rec) is PostStatus.POSTED

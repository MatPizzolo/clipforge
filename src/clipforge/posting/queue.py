"""Queue rules (spec §4-§6): pure functions over PostRecords."""

from __future__ import annotations

from datetime import datetime, timedelta

from clipforge.models import ContentItem, PostRecord, PostStatus

SKIP_RETURN = timedelta(hours=24)
FRESH_DAYS = timedelta(days=7)
FRESH_BONUS = 0.05
PAUSE_AFTER = 2  # unanswered sends before the slots pause
SAME_MOMENT_IOU = 0.5


def _video(item: ContentItem) -> str:
    return item.clip.source_hash if item.clip else item.id


def _order(item: ContentItem) -> tuple[str, float]:
    return (item.clip.job_id, item.clip.start) if item.clip else (item.id, 0.0)


def _finished(item: ContentItem) -> datetime:
    return item.clip.episode_finished_at if item.clip else item.queued_at


def status(record: PostRecord) -> PostStatus:
    verdict = record.verdict
    if verdict is not None and verdict.kind == "rejected":
        return PostStatus.REJECTED
    if record.unavailable:
        return PostStatus.UNAVAILABLE
    if record.platforms and set(record.posted) >= set(record.platforms):
        return PostStatus.POSTED
    if record.posted:
        return PostStatus.PARTLY_POSTED
    last_send = record.sends[-1].at if record.sends else None
    if (
        verdict is not None
        and verdict.kind == "skipped"
        and (last_send is None or verdict.at >= last_send)
    ):
        return PostStatus.SKIPPED
    return PostStatus.SENT if last_send is not None else PostStatus.QUEUED


def eligible(record: PostRecord, now: datetime) -> bool:
    state = status(record)
    if state is PostStatus.QUEUED:
        return True
    if state is PostStatus.SKIPPED:
        assert record.verdict is not None
        return now - record.verdict.at >= SKIP_RETURN
    return False


def unanswered(records: list[PostRecord]) -> list[PostRecord]:
    return [r for r in records if status(r) is PostStatus.SENT]


def _priority(item: ContentItem, now: datetime) -> float:
    fresh = now - _finished(item) <= FRESH_DAYS
    return item.score + (FRESH_BONUS if fresh else 0.0)


def pick_next(records: list[PostRecord], now: datetime) -> PostRecord | None:
    """Highest priority first, never the same video or channel twice in a row while another is
    eligible (the channel rule gives way first)."""
    sent = [r for r in records if r.sends]
    last = max(sent, key=lambda r: r.sends[-1].at).item if sent else None
    pool = [r for r in records if eligible(r, now)]
    if last is not None:
        other_video = [r for r in pool if _video(r.item) != _video(last)]
        other_both = [r for r in other_video if r.item.source_id != last.source_id]
        pool = other_both or other_video or pool
    if not pool:
        return None
    return min(pool, key=lambda r: (-_priority(r.item, now), *_order(r.item)))


def _iou(item_a: ContentItem, item_b: ContentItem) -> float:
    a, b = item_a.clip, item_b.clip
    if a is None or b is None:
        return 0.0
    overlap = min(a.end, b.end) - max(a.start, b.start)
    if overlap <= 0:
        return 0.0
    return overlap / (max(a.end, b.end) - min(a.start, b.start))


def overlaps(item: ContentItem, records: list[PostRecord]) -> bool:
    """True if a clip of the same video that can still be posted covers the same moment. Rejected
    and unavailable clips don't count, so a re-cut can bring their moment back (spec §10)."""
    return any(
        r.item.id != item.id
        and _video(r.item) == _video(item)
        and status(r) not in (PostStatus.REJECTED, PostStatus.UNAVAILABLE)
        and _iou(r.item, item) > SAME_MOMENT_IOU
        for r in records
    )

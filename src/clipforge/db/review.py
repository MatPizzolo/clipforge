"""SQL behind routing (S2 spec §5.2): window counts, spot-check state, the routing stamp. The
review columns' one writer is the review service (S2b), which calls `stamp`."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, distinct, func, not_, select

from clipforge.db.engine import Database
from clipforge.db.tables import content_items, post_events, posts
from clipforge.models import ContentItem, Routing
from clipforge.review.routing import FormatWindowSource, NoFormatWindow, SpotState, WindowCounts

DECISIONS = ("approved", "reviewed")  # review-service decisions; assisted taps never count
SPOT_WEEK = timedelta(days=7)


def _by_a_person() -> Any:
    actor = post_events.c.actor
    return and_(actor.is_not(None), not_(actor.like("system:%")))


class ReviewRepo:
    def __init__(self, db: Database, format_source: FormatWindowSource | None = None) -> None:
        self.db = db
        self.format_source = format_source or NoFormatWindow()

    def counts(self, account_id: str, item: ContentItem) -> WindowCounts:
        """Distinct items with a counted decision, per producer version (R2, R6)."""
        query = (
            select(content_items.c.producer_version, func.count(distinct(content_items.c.id)))
            .join(post_events, post_events.c.item_id == content_items.c.id)
            .where(content_items.c.account_id == account_id,
                   post_events.c.kind.in_(DECISIONS), _by_a_person())
            .group_by(content_items.c.producer_version)
        )  # fmt: skip
        with self.db.begin() as conn:
            producer = {row[0]: int(row[1]) for row in conn.execute(query)}
        window = self.format_source.format_window(account_id)
        return WindowCounts(producer=producer,
                            format_version=window[0] if window else None,
                            format_count=window[1] if window else 0)  # fmt: skip

    def spot_state(self, account_id: str, now: datetime) -> SpotState:
        """From the `routed` events: spot checks, and auto items since the last one."""
        query = (
            select(post_events.c.at, post_events.c.data)
            .join(content_items, content_items.c.id == post_events.c.item_id)
            .where(content_items.c.account_id == account_id, post_events.c.kind == "routed")
            .order_by(post_events.c.at, post_events.c.id)
        )
        with self.db.begin() as conn:
            rows = conn.execute(query).all()
        checks = [r.at for r in rows if "spot_check" in r.data.get("reasons", [])]
        last = checks[-1] if checks else None
        since = [r for r in rows if last is None or r.at > last]
        return SpotState(
            auto_since_last=sum(r.data.get("lane") == "auto" for r in since),
            checks_last_7d=sum(now - at <= SPOT_WEEK for at in checks),
            last_check_at=last,
        )

    def stamp(self, ref: str, routing: Routing, now: datetime) -> None:
        """The routing result on the item and a `routed` event (S3 §8.4: the dial and window
        in force make every result attributable)."""
        data = routing.model_dump(mode="json")
        with self.db.begin() as conn:
            conn.execute(content_items.update().where(content_items.c.id == ref).values(
                review_lane=routing.lane, review_reasons=list(routing.reasons),
                review_dial=routing.dial, review_window=routing.window,
                gate=data["gate"]))  # fmt: skip
            conn.execute(post_events.insert().values(
                item_id=ref, kind="routed", at=now,
                data={k: data[k] for k in ("lane", "reasons", "dial", "window")}))  # fmt: skip

    def first_post_at(self, account_id: str) -> datetime | None:
        query = (
            select(func.min(posts.c.posted_at))
            .join(content_items, content_items.c.id == posts.c.item_id)
            .where(content_items.c.account_id == account_id, posts.c.posted_at.is_not(None))
        )
        with self.db.begin() as conn:
            return conn.execute(query).scalar()


__all__ = ["DECISIONS", "ReviewRepo"]

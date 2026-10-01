"""The posting queue in Postgres (spec §3, §5.1). Reads rebuild the same PostRecords the Dict
gave, so queue.py decides the status (ADR-23 rules unchanged). Each write sets only its own
columns (one writer per column group, ADR-41) and logs a post_events row in its transaction."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, case, select
from sqlalchemy.dialects.postgresql import insert

from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.db.tables import assets, content_items, post_events, posts, sends
from clipforge.models import (
    AssetSource,
    ClipOrigin,
    ContentItem,
    Platform,
    PostRecord,
    PostSend,
    PostVerdict,
    RejectReason,
)  # fmt: skip

_ORDER = list(Platform)


def _item_row(item: ContentItem) -> dict[str, Any]:
    clip = item.clip
    return {
        "id": item.id, "account_id": item.account_id, "source_id": item.source_id,
        "job_id": clip.job_id if clip else None, "producer": item.producer,
        "producer_version": item.producer_version, "language": item.language,
        "media_kind": item.media_kind, "video_path": item.video_path,
        "image_paths": list(item.image_paths), "duration": item.duration, "title": item.title,
        "hook": item.hook, "score": item.score, "credits": list(item.credits),
        "ai_disclosure": item.ai_disclosure, "sponsored": item.sponsored,
        "cost_usd": item.cost_usd, "parent_item_id": item.parent_item_id,
        "clip_id": clip.clip_id if clip else None,
        "source_hash": clip.source_hash if clip else None,
        "start_s": clip.start if clip else None, "end_s": clip.end if clip else None,
        "episode": clip.episode if clip else None,
        "episode_finished_at": clip.episode_finished_at if clip else None,
        "queued_at": item.queued_at,
    }  # fmt: skip


def _item(row: Any, asset_rows: list[Any]) -> ContentItem:
    clip = None
    if row.clip_id is not None:
        clip = ClipOrigin(job_id=row.job_id, clip_id=row.clip_id, source_hash=row.source_hash,
                          start=row.start_s, end=row.end_s, episode=row.episode,
                          episode_finished_at=row.episode_finished_at)  # fmt: skip
    return ContentItem(
        id=row.id, account_id=row.account_id, source_id=row.source_id, producer=row.producer,
        producer_version=row.producer_version, language=row.language, media_kind=row.media_kind,
        video_path=row.video_path, image_paths=row.image_paths, duration=row.duration,
        title=row.title, hook=row.hook, score=row.score, credits=row.credits,
        assets=[AssetSource(kind=a.kind, license=a.license, attribution=a.attribution,
                            url=a.url, model=a.model) for a in asset_rows],
        ai_disclosure=row.ai_disclosure, sponsored=row.sponsored, cost_usd=row.cost_usd,
        parent_item_id=row.parent_item_id, clip=clip, queued_at=row.queued_at,
    )  # fmt: skip


def _record(
    row: Any, post_rows: list[Any], send_rows: list[Any], asset_rows: list[Any]
) -> PostRecord:
    verdict = None
    if row.verdict_kind is not None:
        reason = RejectReason(row.verdict_reason) if row.verdict_reason else None
        verdict = PostVerdict(kind=row.verdict_kind, at=row.verdict_at, reason=reason)
    platforms = sorted((Platform(p.platform) for p in post_rows), key=_ORDER.index)
    return PostRecord(
        item=_item(row, asset_rows), platforms=platforms,
        sends=sorted((PostSend(n=s.n, at=s.at, slot=s.slot, message_id=s.message_id,
                               video_message_id=s.video_message_id) for s in send_rows),
                     key=lambda s: s.n),
        posted={Platform(p.platform): p.posted_at for p in post_rows if p.posted_at is not None},
        verdict=verdict, unavailable=row.unavailable_at is not None,
    )  # fmt: skip


def _event(conn: Connection, ref: str, kind: str, at: datetime,
           platform: Platform | None = None, actor: str | None = None,
           **data: object) -> None:  # fmt: skip
    """One post_events row. `actor` goes into `data.actor` (omitted for system writes): S3c's
    migration 0002 copies exactly that key into a `post_events.actor` column (S3c D3)."""
    if actor is not None:
        data["actor"] = actor
    conn.execute(post_events.insert().values(item_id=ref, kind=kind, at=at,
                                             platform=platform.value if platform else None,
                                             data=data))  # fmt: skip


class SqlPostingRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- reads: a fixed number of indexed queries, never a scan of other accounts

    def _load(self, conn: Connection, where: Any) -> list[PostRecord]:
        rows = conn.execute(select(content_items).where(where).order_by(content_items.c.id)).all()
        if not rows:
            return []
        ids = [r.id for r in rows]
        grouped: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
        for name, table in (("posts", posts), ("sends", sends), ("assets", assets)):
            for r in conn.execute(select(table).where(table.c.item_id.in_(ids))):
                grouped[r.item_id][name].append(r)
        return [_record(r, grouped[r.id]["posts"], grouped[r.id]["sends"], grouped[r.id]["assets"])
                for r in rows]  # fmt: skip

    def get(self, ref: str) -> PostRecord | None:
        with self.db.begin() as conn:
            found = self._load(conn, content_items.c.id == ref)
        return found[0] if found else None

    def records(self, account_id: str) -> list[PostRecord]:
        with self.db.begin() as conn:
            return self._load(conn, content_items.c.account_id == account_id)

    def records_for_source(self, source_hash: str) -> list[PostRecord]:
        with self.db.begin() as conn:
            return self._load(conn, content_items.c.source_hash == source_hash)

    # ---- enqueue (writer: package step / rebuild / import)

    def add(self, item: ContentItem, platforms: list[Platform]) -> bool:
        with self.db.begin() as conn:
            inserted = conn.execute(insert(content_items).values(**_item_row(item))
                                    .on_conflict_do_nothing()
                                    .returning(content_items.c.id)).first()  # fmt: skip
            if inserted is None:
                return False
            if item.assets:
                conn.execute(assets.insert(), [{"item_id": item.id, **a.model_dump(mode="json")}
                                               for a in item.assets])  # fmt: skip
            if platforms:
                conn.execute(posts.insert(), [{"item_id": item.id, "platform": p.value}
                                              for p in platforms])  # fmt: skip
        return True

    # ---- sender

    def add_send(self, ref: str, send: PostSend, chat_id: int | None = None) -> bool:
        with self.db.begin() as conn:
            inserted = conn.execute(insert(sends).values(
                item_id=ref, n=send.n, at=send.at, slot=send.slot, chat_id=chat_id,
                message_id=send.message_id, video_message_id=send.video_message_id,
            ).on_conflict_do_nothing().returning(sends.c.n)).first()  # fmt: skip
            if inserted is not None:
                _event(conn, ref, "sent", send.at, n=send.n)
        return inserted is not None

    def mark_unavailable(self, ref: str, at: datetime) -> None:
        with self.db.begin() as conn:
            row = conn.execute(
                content_items.update()
                .where(content_items.c.id == ref, content_items.c.unavailable_at.is_(None))
                .values(unavailable_at=at)
                .returning(content_items.c.id)
            ).first()
            if row is not None:
                _event(conn, ref, "unavailable", at)

    # ---- webhook

    def toggle_posted(
        self, ref: str, platform: Platform, at: datetime, actor: str | None = None
    ) -> bool:
        # One upsert: a first tap (also on a platform the item wasn't queued on) inserts it as
        # posted; a later tap flips posted_at. Race-safe on (item_id, platform).
        statement = (
            insert(posts)
            .values(item_id=ref, platform=platform.value, posted_at=at)
            .on_conflict_do_update(
                index_elements=[posts.c.item_id, posts.c.platform],
                set_={"posted_at": case((posts.c.posted_at.is_(None), at), else_=None)},
            )
            .returning(posts.c.posted_at)
        )
        with self.db.begin() as conn:
            on = conn.execute(statement).scalar_one() is not None
            _event(conn, ref, "posted" if on else "unposted", at, platform, actor)
        return on

    def set_posted(
        self, ref: str, platform: Platform, on: bool, at: datetime, actor: str | None = None
    ) -> None:
        statement = insert(posts).values(item_id=ref, platform=platform.value,
                                         posted_at=at if on else None)  # fmt: skip
        statement = statement.on_conflict_do_update(
            index_elements=[posts.c.item_id, posts.c.platform],
            set_={"posted_at": at if on else None})  # fmt: skip
        with self.db.begin() as conn:
            conn.execute(statement)
            _event(conn, ref, "posted" if on else "unposted", at, platform, actor)

    def set_verdict(self, ref: str, verdict: PostVerdict, actor: str | None = None) -> None:
        with self.db.begin() as conn:
            conn.execute(content_items.update().where(content_items.c.id == ref).values(
                verdict_kind=verdict.kind, verdict_at=verdict.at,
                verdict_reason=verdict.reason.value if verdict.reason else None))  # fmt: skip
            _event(conn, ref, verdict.kind, verdict.at, actor=actor)

    def set_reason(self, ref: str, reason: RejectReason, actor: str | None = None) -> bool:
        with self.db.begin() as conn:
            row = conn.execute(content_items.update()
                               .where(content_items.c.id == ref,
                                      content_items.c.verdict_kind == "rejected")
                               .values(verdict_reason=reason.value)
                               .returning(content_items.c.verdict_at)).first()  # fmt: skip
            if row is not None:
                _event(conn, ref, "reason", row.verdict_at, actor=actor, reason=reason.value)
        return row is not None

    def paused(self, account_id: str) -> bool:
        return AccountsRepo(self.db).paused(account_id)

    def set_paused(self, account_id: str, on: bool, at: datetime, actor: str | None = None) -> None:
        # posting_state has no actor column (0001 is frozen): actions.pause logs the actor
        AccountsRepo(self.db).set_paused(account_id, on, at)

    # ---- one-off import (Task 20)

    def import_record(self, record: PostRecord, chat_id: int | None) -> bool:
        """Insert a Dict record as is: item, posts (with posted_at), sends, verdict, unavailable.
        Skips (False) when the item already exists, so a re-run imports nothing twice."""
        item = record.item
        with self.db.begin() as conn:
            inserted = conn.execute(insert(content_items).values(
                **_item_row(item),
                unavailable_at=item.queued_at if record.unavailable else None,
                verdict_kind=record.verdict.kind if record.verdict else None,
                verdict_at=record.verdict.at if record.verdict else None,
                verdict_reason=(record.verdict.reason.value
                                if record.verdict and record.verdict.reason else None),
            ).on_conflict_do_nothing().returning(content_items.c.id)).first()  # fmt: skip
            if inserted is None:
                return False
            if item.assets:
                conn.execute(assets.insert(), [{"item_id": item.id, **a.model_dump(mode="json")}
                                               for a in item.assets])  # fmt: skip
            if record.platforms:
                conn.execute(posts.insert(), [{"item_id": item.id, "platform": p.value,
                                               "posted_at": record.posted.get(p)}
                                              for p in record.platforms])  # fmt: skip
            if record.sends:
                conn.execute(sends.insert(), [{
                    "item_id": item.id, "n": s.n, "at": s.at, "slot": s.slot, "chat_id": chat_id,
                    "message_id": s.message_id, "video_message_id": s.video_message_id,
                } for s in record.sends])  # fmt: skip
            _event(conn, item.id, "imported", item.queued_at)
        return True

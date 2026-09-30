"""Sources and their change history (spec §3, §6.3). The only place sources are edited: the
CLI now, the S3 dashboard later, both through the API. Every change writes a source_events row
in the same transaction."""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Connection, select

from clipforge.db.engine import Database
from clipforge.db.tables import accounts, content_items, posts, source_events, sources
from clipforge.models import Platform, Source, SourceEvent, Submission

_COLUMNS = ("id", "account_id", "kind", "status", "credit_name", "creator_handles", "url",
            "permission", "campaign", "notes")  # fmt: skip


class SourceExists(ValueError):
    pass


class UnknownAccount(ValueError):
    pass


class UnknownSource(KeyError):
    pass


def _values(source: Source) -> dict[str, Any]:
    data = source.model_dump(mode="json")
    return {k: data[k] for k in _COLUMNS}


def _source(row: Any) -> Source:
    values = {k: getattr(row, k) for k in _COLUMNS}
    return Source.model_validate({k: v for k, v in values.items() if v is not None})


def _event(conn: Connection, source: Source, actor: str, at: datetime, action: str,
           before: dict[str, Any] | None) -> None:  # fmt: skip
    conn.execute(source_events.insert().values(
        source_id=source.id, at=at, actor=actor, action=action, before=before,
        after=source.model_dump(mode="json")))  # fmt: skip


def _require_account(conn: Connection, account_id: str) -> None:
    if not conn.execute(select(accounts.c.id).where(accounts.c.id == account_id)).first():
        raise UnknownAccount(f"unknown account {account_id!r}")


class SourcesRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, source: Source, actor: str, now: datetime,
               action: Literal["created", "imported"] = "created") -> None:  # fmt: skip
        with self.db.begin() as conn:
            if conn.execute(select(sources.c.id).where(sources.c.id == source.id)).first():
                raise SourceExists(f"source {source.id!r} already exists")
            _require_account(conn, source.account_id)
            conn.execute(sources.insert().values(**_values(source), created_at=now, updated_at=now))
            _event(conn, source, actor, now, action, None)

    def replace(self, source: Source, actor: str, now: datetime) -> None:
        with self.db.begin() as conn:
            row = conn.execute(
                select(sources).where(sources.c.id == source.id).with_for_update()
            ).first()
            if row is None:
                raise UnknownSource(source.id)
            _require_account(conn, source.account_id)
            before = _source(row).model_dump(mode="json")
            values = _values(source)
            values.pop("id")
            conn.execute(
                sources.update().where(sources.c.id == source.id).values(**values, updated_at=now)
            )
            _event(conn, source, actor, now, "updated", before)

    def get(self, source_id: str) -> Source | None:
        with self.db.begin() as conn:
            row = conn.execute(select(sources).where(sources.c.id == source_id)).first()
        return None if row is None else _source(row)

    def list(self) -> list[Source]:
        with self.db.begin() as conn:
            return [_source(r) for r in conn.execute(select(sources).order_by(sources.c.id))]

    def events(self, source_id: str) -> builtins.list[SourceEvent]:
        query = (select(source_events).where(source_events.c.source_id == source_id)
                 .order_by(source_events.c.id.desc()))  # fmt: skip
        with self.db.begin() as conn:
            return [
                SourceEvent(source_id=r.source_id, at=r.at, actor=r.actor, action=r.action,
                            before=r.before, after=r.after)
                for r in conn.execute(query)
            ]  # fmt: skip

    def submissions(self, source_id: str) -> builtins.list[Submission]:
        query = (
            select(posts.c.item_id, posts.c.platform, posts.c.posted_at, posts.c.url)
            .join(content_items, content_items.c.id == posts.c.item_id)
            .where(content_items.c.source_id == source_id, posts.c.posted_at.is_not(None))
            .order_by(posts.c.posted_at)
        )
        with self.db.begin() as conn:
            return [
                Submission(item_id=r.item_id, platform=Platform(r.platform),
                           posted_at=r.posted_at, url=r.url)
                for r in conn.execute(query)
            ]  # fmt: skip

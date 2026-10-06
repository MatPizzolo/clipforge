"""Posting persistence: the `PostingRepo` protocol (Postgres implements it, `db/posting.py`) and
the short-lived slot/reminder claims (ADR-26, Dict only). The Dict posting store and its
Dual-write mirror were retired by S1 Task 23 (card 040, ADR-41)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from clipforge.models import (
    ContentItem,
    Platform,
    PostRecord,
    PostSend,
    PostVerdict,
    RejectReason,
)
from clipforge.pipeline.deps import KV


class PostingRepo(Protocol):
    def add(self, item: ContentItem, platforms: list[Platform]) -> bool: ...
    def get(self, ref: str) -> PostRecord | None: ...
    def records(self, account_id: str) -> list[PostRecord]: ...
    def records_for_source(self, source_hash: str) -> list[PostRecord]: ...
    def add_send(self, ref: str, send: PostSend, chat_id: int | None = None) -> bool: ...
    def mark_unavailable(self, ref: str, at: datetime) -> None: ...
    # `actor`: who made the change (`telegram:<id>`, `web:<login>`, `session:<name>`), recorded in
    # Postgres as post_events.data.actor; None for system writes (card 002 A4, S3c D3).
    def toggle_posted(self, ref: str, platform: Platform, at: datetime,
                      actor: str | None = None) -> bool: ...  # fmt: skip
    def set_posted(self, ref: str, platform: Platform, on: bool, at: datetime,
                   actor: str | None = None) -> None: ...  # fmt: skip
    def set_verdict(self, ref: str, verdict: PostVerdict, actor: str | None = None) -> None: ...
    def set_reason(self, ref: str, reason: RejectReason, actor: str | None = None) -> bool: ...
    def paused(self, account_id: str) -> bool: ...
    # `actor` and `reason` land in posting_state.changed_by/reason (0002)
    def set_paused(self, account_id: str, on: bool, at: datetime, actor: str | None = None,
                   reason: str | None = None) -> None: ...  # fmt: skip


class PostingClaims:
    """Dict only: short-lived claims, left to expire (ADR-26)."""

    def __init__(self, kv: KV) -> None:
        self.kv = kv

    def claim_slot(self, account_id: str, slot: datetime) -> bool:
        return self.kv.put(
            f"posting:slot:{account_id}:{slot.isoformat()}", "1", skip_if_exists=True
        )

    def release_slot(self, account_id: str, slot: datetime) -> None:
        self.kv.delete(f"posting:slot:{account_id}:{slot.isoformat()}")

    def claim_reminder(self, account_id: str, at: datetime) -> bool:
        return self.kv.put(
            f"posting:reminded:{account_id}:{at.isoformat()}", "1", skip_if_exists=True
        )

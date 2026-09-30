"""Posting persistence: the `PostingRepo` protocol, its Dict implementation (the ADR-23 keys, one
writer each, ADR-14) and the short-lived slot/reminder claims (ADR-26, Dict only)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import ValidationError

from clipforge.db.engine import redact
from clipforge.models import (
    AssetSource,
    ChannelRef,
    ClipOrigin,
    ContentItem,
    Platform,
    PostItem,
    PostMark,
    PostRecord,
    PostSend,
    PostVerdict,
    RejectReason,
)
from clipforge.pipeline.deps import KV

log = logging.getLogger(__name__)

PREFIX = "post:"
PAUSED_KEY = "posting:paused"


def _item_key(ref: str) -> str:
    return f"{PREFIX}{ref}"


def to_content_item(p: PostItem, account_id: str) -> ContentItem:
    # producer_version stays "plan-c": legacy Dict records predate versions, plan C made them.
    return ContentItem(
        id=p.ref, account_id=account_id, source_id=p.channel.slug, producer_version="plan-c",
        language="en", video_path=p.video_path, duration=p.end - p.start, title=p.title,
        hook=p.hook, score=p.score, credits=[p.channel.name],
        assets=[AssetSource(kind="source_video", license="unrecorded", attribution=p.channel.name)],
        clip=ClipOrigin(job_id=p.job_id, clip_id=p.clip_id, source_hash=p.source_hash,
                        start=p.start, end=p.end, episode=p.episode,
                        episode_finished_at=p.episode_finished_at),
        queued_at=p.queued_at,
    )  # fmt: skip


def to_post_item(item: ContentItem) -> PostItem:
    clip = item.clip
    if clip is None or item.source_id is None:
        raise ValueError(f"{item.id}: only clip items with a source fit the Dict format")
    return PostItem(
        job_id=clip.job_id, clip_id=clip.clip_id,
        channel=ChannelRef(slug=item.source_id,
                           name=item.credits[0] if item.credits else item.source_id),
        source_hash=clip.source_hash, start=clip.start, end=clip.end, score=item.score,
        title=item.title, hook=item.hook, video_path=item.video_path or "", episode=clip.episode,
        episode_finished_at=clip.episode_finished_at, queued_at=item.queued_at,
    )  # fmt: skip


class PostingRepo(Protocol):
    def add(self, item: ContentItem, platforms: list[Platform]) -> bool: ...
    def get(self, ref: str) -> PostRecord | None: ...
    def records(self, account_id: str) -> list[PostRecord]: ...
    def records_for_source(self, source_hash: str) -> list[PostRecord]: ...
    def add_send(self, ref: str, send: PostSend, chat_id: int | None = None) -> bool: ...
    def mark_unavailable(self, ref: str, at: datetime) -> None: ...
    def toggle_posted(self, ref: str, platform: Platform, at: datetime) -> bool: ...
    def set_posted(self, ref: str, platform: Platform, on: bool, at: datetime) -> None: ...
    def set_verdict(self, ref: str, verdict: PostVerdict) -> None: ...
    def set_reason(self, ref: str, reason: RejectReason) -> bool: ...
    def paused(self, account_id: str) -> bool: ...
    def set_paused(self, account_id: str, on: bool, at: datetime) -> None: ...


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


class DictPostingRepo:
    """ADR-23 keys over the job Dict (one writer per key, ADR-14). Serves one account: the Dict
    predates accounts. Items are stored in the legacy `PostItem` format. Removed when ADR-24
    retires (spec §9.3)."""

    def __init__(self, kv: KV, account_id: str) -> None:
        self.kv, self.account_id = kv, account_id

    def add(self, item: ContentItem, platforms: list[Platform]) -> bool:
        if item.account_id != self.account_id:
            return False
        legacy = to_post_item(item)
        return self.kv.put(_item_key(legacy.ref), legacy.model_dump_json(), skip_if_exists=True)

    def get(self, ref: str) -> PostRecord | None:
        """Read the same way as `records()` so the two never disagree (a missing `sent:<n>` in
        the middle doesn't hide the later sends)."""
        key = _item_key(ref)
        if self.kv.get(key) is None:
            return None
        values = {k: v for k, v in self.kv.items() if k == key or k.startswith(f"{key}:")}
        return self._build(values).get(ref)

    def records(self, account_id: str) -> list[PostRecord]:
        if account_id != self.account_id:
            return []
        values = {k: v for k, v in self.kv.items() if k.startswith(PREFIX)}
        return list(self._build(values).values())

    def records_for_source(self, source_hash: str) -> list[PostRecord]:
        return [
            r
            for r in self.records(self.account_id)
            if r.item.clip is not None and r.item.clip.source_hash == source_hash
        ]

    def add_send(self, ref: str, send: PostSend, chat_id: int | None = None) -> bool:
        key = f"{_item_key(ref)}:sent:{send.n}"
        return self.kv.put(key, send.model_dump_json(), skip_if_exists=True)

    def mark_unavailable(self, ref: str, at: datetime) -> None:
        self.kv.put(f"{_item_key(ref)}:unavailable", "1", skip_if_exists=True)

    def toggle_posted(self, ref: str, platform: Platform, at: datetime) -> bool:
        on = self.kv.get(f"{_item_key(ref)}:posted:{platform}") is None
        self.set_posted(ref, platform, on, at)
        return on

    def set_posted(self, ref: str, platform: Platform, on: bool, at: datetime) -> None:
        key = f"{_item_key(ref)}:posted:{platform}"
        if on:
            self.kv.put(key, PostMark(at=at).model_dump_json())
        else:
            self.kv.delete(key)

    def set_verdict(self, ref: str, verdict: PostVerdict) -> None:
        self.kv.put(f"{_item_key(ref)}:verdict", verdict.model_dump_json())

    def set_reason(self, ref: str, reason: RejectReason) -> bool:
        key = f"{_item_key(ref)}:verdict"
        raw = self.kv.get(key)
        if raw is None:
            return False
        verdict = PostVerdict.model_validate_json(raw)
        if verdict.kind != "rejected":
            return False
        self.kv.put(key, verdict.model_copy(update={"reason": reason}).model_dump_json())
        return True

    def paused(self, account_id: str) -> bool:
        return account_id == self.account_id and self.kv.get(PAUSED_KEY) is not None

    def set_paused(self, account_id: str, on: bool, at: datetime) -> None:
        if account_id != self.account_id:
            return
        if on:
            self.kv.put(PAUSED_KEY, "1")
        else:
            self.kv.delete(PAUSED_KEY)

    def _build(self, values: dict[str, str]) -> dict[str, PostRecord]:
        """Group `post:*` key/values into records. A value that doesn't validate is logged and
        ignored (a clip with a bad item is left out; a bad side key is treated as missing)."""
        items: dict[str, ContentItem] = {}
        extras: dict[str, dict[str, str]] = {}
        for key, raw in values.items():
            parts = key.split(":")  # post, job_id, clip_id[, kind[, arg]]
            if len(parts) < 3:
                continue
            ref = f"{parts[1]}:{parts[2]}"
            if len(parts) == 3:
                try:
                    items[ref] = to_content_item(PostItem.model_validate_json(raw), self.account_id)
                except ValidationError:
                    log.warning("ignoring an invalid posting item %s", ref)
            else:
                extras.setdefault(ref, {})[":".join(parts[3:])] = raw
        records: dict[str, PostRecord] = {}
        for ref, item in items.items():
            sends: list[PostSend] = []
            posted: dict[Platform, datetime] = {}
            verdict: PostVerdict | None = None
            unavailable = False
            for kind, raw in extras.get(ref, {}).items():
                try:
                    if kind.startswith("sent:"):
                        sends.append(PostSend.model_validate_json(raw))
                    elif kind.startswith("posted:"):
                        posted[Platform(kind.split(":", 1)[1])] = PostMark.model_validate_json(
                            raw
                        ).at
                    elif kind == "verdict":
                        verdict = PostVerdict.model_validate_json(raw)
                    elif kind == "unavailable":
                        unavailable = True
                except (ValidationError, ValueError):
                    log.warning("ignoring an invalid posting key %s:%s", ref, kind)
            sends.sort(key=lambda s: s.n)
            records[ref] = PostRecord(
                item=item, sends=sends, posted=posted, verdict=verdict, unavailable=unavailable
            )
        return records


class DualPostingRepo:
    """ADR-41: reads and writes go to `primary` (STATE_READS); every successful write is
    repeated on `mirror`, best-effort, so a rollback flips reads onto a current store."""

    def __init__(self, primary: PostingRepo, mirror: PostingRepo) -> None:
        self.primary, self.mirror = primary, mirror
        self.mirror_failures = 0

    def _mirror(self, action: str, call: Callable[[], object]) -> None:
        try:
            call()
        except Exception as exc:
            self.mirror_failures += 1
            log.warning("posting mirror: %s failed: %s", action, redact(exc))

    def add(self, item: ContentItem, platforms: list[Platform]) -> bool:
        added = self.primary.add(item, platforms)
        if added:
            self._mirror("add", lambda: self.mirror.add(item, platforms))
        return added

    def get(self, ref: str) -> PostRecord | None:
        return self.primary.get(ref)

    def records(self, account_id: str) -> list[PostRecord]:
        return self.primary.records(account_id)

    def records_for_source(self, source_hash: str) -> list[PostRecord]:
        return self.primary.records_for_source(source_hash)

    def add_send(self, ref: str, send: PostSend, chat_id: int | None = None) -> bool:
        added = self.primary.add_send(ref, send, chat_id)
        if added:
            self._mirror("add_send", lambda: self.mirror.add_send(ref, send, chat_id))
        return added

    def mark_unavailable(self, ref: str, at: datetime) -> None:
        self.primary.mark_unavailable(ref, at)
        self._mirror("mark_unavailable", lambda: self.mirror.mark_unavailable(ref, at))

    def toggle_posted(self, ref: str, platform: Platform, at: datetime) -> bool:
        on = self.primary.toggle_posted(ref, platform, at)
        # set, not toggle: the mirror ends in the primary's state even if it had drifted
        self._mirror("set_posted", lambda: self.mirror.set_posted(ref, platform, on, at))
        return on

    def set_posted(self, ref: str, platform: Platform, on: bool, at: datetime) -> None:
        self.primary.set_posted(ref, platform, on, at)
        self._mirror("set_posted", lambda: self.mirror.set_posted(ref, platform, on, at))

    def set_verdict(self, ref: str, verdict: PostVerdict) -> None:
        self.primary.set_verdict(ref, verdict)
        self._mirror("set_verdict", lambda: self.mirror.set_verdict(ref, verdict))

    def set_reason(self, ref: str, reason: RejectReason) -> bool:
        done = self.primary.set_reason(ref, reason)
        if done:
            self._mirror("set_reason", lambda: self.mirror.set_reason(ref, reason))
        return done

    def paused(self, account_id: str) -> bool:
        return self.primary.paused(account_id)

    def set_paused(self, account_id: str, on: bool, at: datetime) -> None:
        self.primary.set_paused(account_id, on, at)
        self._mirror("set_paused", lambda: self.mirror.set_paused(account_id, on, at))

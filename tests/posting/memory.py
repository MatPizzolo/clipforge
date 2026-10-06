"""An in-memory `PostingRepo` for fast tests (card 040): the Dict posting store it stands in
for was retired with S1 Task 23. `tests/posting/test_repo_contract.py` runs the same suite on it
and on `SqlPostingRepo`, so the two behave alike. Test-only: production has Postgres only."""

from __future__ import annotations

from datetime import datetime
from weakref import WeakKeyDictionary

from clipforge.models import (
    Account,
    ContentItem,
    Platform,
    PostRecord,
    PostSend,
    PostVerdict,
    RejectReason,
    Source,
)
from clipforge.pipeline.deps import KV
from clipforge.posting.backend import Posting
from clipforge.posting.repo import PostingClaims


class MemoryPostingRepo:
    def __init__(self) -> None:
        self.items: dict[str, PostRecord] = {}
        self.paused_accounts: set[str] = set()

    def _update(self, ref: str, **fields: object) -> None:
        record = self.items.get(ref)
        if record is not None:
            self.items[ref] = record.model_copy(update=fields)

    def add(self, item: ContentItem, platforms: list[Platform]) -> bool:
        if item.id in self.items:
            return False
        self.items[item.id] = PostRecord(item=item, platforms=list(platforms))
        return True

    def get(self, ref: str) -> PostRecord | None:
        return self.items.get(ref)

    def records(self, account_id: str) -> list[PostRecord]:
        return [r for ref, r in sorted(self.items.items()) if r.item.account_id == account_id]

    def records_for_source(self, source_hash: str) -> list[PostRecord]:
        return [r for ref, r in sorted(self.items.items())
                if r.item.clip is not None and r.item.clip.source_hash == source_hash]  # fmt: skip

    def add_send(self, ref: str, send: PostSend, chat_id: int | None = None) -> bool:
        record = self.items.get(ref)
        if record is None or any(s.n == send.n for s in record.sends):
            return False
        self._update(ref, sends=sorted([*record.sends, send], key=lambda s: s.n))
        return True

    def mark_unavailable(self, ref: str, at: datetime) -> None:
        self._update(ref, unavailable=True)

    def toggle_posted(
        self, ref: str, platform: Platform, at: datetime, actor: str | None = None
    ) -> bool:
        record = self.items.get(ref)
        on = record is None or platform not in record.posted
        self.set_posted(ref, platform, on, at, actor)
        return on

    def set_posted(
        self, ref: str, platform: Platform, on: bool, at: datetime, actor: str | None = None
    ) -> None:
        record = self.items.get(ref)
        if record is None:
            return
        posted = {p: t for p, t in record.posted.items() if p != platform}
        if on:
            posted[platform] = at
        # like the posts upsert: a tap on a platform the item wasn't queued on adds it
        platforms = record.platforms if platform in record.platforms else [*record.platforms,
                                                                           platform]  # fmt: skip
        self._update(ref, posted=posted, platforms=platforms)

    def set_verdict(self, ref: str, verdict: PostVerdict, actor: str | None = None) -> None:
        self._update(ref, verdict=verdict)

    def set_reason(self, ref: str, reason: RejectReason, actor: str | None = None) -> bool:
        record = self.items.get(ref)
        if record is None or record.verdict is None or record.verdict.kind != "rejected":
            return False
        self._update(ref, verdict=record.verdict.model_copy(update={"reason": reason}))
        return True

    def paused(self, account_id: str) -> bool:
        return account_id in self.paused_accounts

    def set_paused(
        self, account_id: str, on: bool, at: datetime, actor: str | None = None,
        reason: str | None = None,
    ) -> None:  # fmt: skip
        if on:
            self.paused_accounts.add(account_id)
        else:
            self.paused_accounts.discard(account_id)


def _no_source(source_id: str) -> Source | None:
    return None


# One repo per KV, so a test that rebuilds `Posting` over the same KV (a new account or chat)
# still sees the clips queued before, as the Dict store did
_REPOS: WeakKeyDictionary[KV, MemoryPostingRepo] = WeakKeyDictionary()


def memory_repo(kv: KV) -> MemoryPostingRepo:
    repo = _REPOS.get(kv)
    if repo is None:
        repo = _REPOS[kv] = MemoryPostingRepo()
    return repo


def memory_posting(kv: KV, account: Account, problem: str | None = None) -> Posting:
    """One account over the in-memory repo of `kv`, with no source rows (what `dict_posting`
    gave the tests before card 040)."""
    return Posting(memory_repo(kv), PostingClaims(kv), lambda: [account], _no_source,
                   account.id, problem=problem)  # fmt: skip

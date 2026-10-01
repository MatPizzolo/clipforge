"""What posting needs, bundled per STATE_READS mode (spec §5.1, ADR-41)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from clipforge.accounts.service import env_account, read_schedules
from clipforge.config import Settings
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database, DatabaseUnavailable
from clipforge.db.posting import SqlPostingRepo
from clipforge.db.sources import SourcesRepo
from clipforge.models import Account, PostingSchedule, Source
from clipforge.pipeline.deps import KV
from clipforge.posting.repo import DictPostingRepo, DualPostingRepo, PostingClaims, PostingRepo

if TYPE_CHECKING:
    from clipforge.pipeline.steps import Deps

NO_DATABASE = "DATABASE_URL is not configured"


class _Unavailable:
    """A PostingRepo whose every call says why posting can't run."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def fail(*args: object, **kwargs: object) -> Any:
            raise DatabaseUnavailable(self.reason)

        return fail


@dataclass
class Posting:
    repo: PostingRepo
    claims: PostingClaims
    accounts: Callable[[], list[Account]]
    source: Callable[[str], Source | None]
    default_account_id: str
    requires_source: bool = False
    problem: str | None = None
    # The tick's schedules, read before any database call (card 002 A3). None: from accounts().
    schedules: Callable[[], dict[str, PostingSchedule]] | None = None

    def posting_schedules(self) -> dict[str, PostingSchedule]:
        """Accounts with a posting chat and their schedules, without touching Postgres in
        postgres mode (the Dict copies the accounts service writes)."""
        found = (self.schedules() if self.schedules is not None
                 else {a.id: a.posting for a in self.accounts()})  # fmt: skip
        return {k: v for k, v in sorted(found.items()) if v.chat_id is not None}

    def account(self, account_id: str) -> Account | None:
        return next((a for a in self.accounts() if a.id == account_id), None)

    def posting_accounts(self) -> list[Account]:
        return sorted((a for a in self.accounts() if a.posting.chat_id is not None),
                      key=lambda a: a.id)  # fmt: skip


def _no_source(source_id: str) -> Source | None:
    return None


def posting_of(deps: Deps) -> Posting:
    """For the bot and service paths. The enqueue path checks `deps.posting` itself."""
    if deps.posting is None:
        raise RuntimeError("posting is not configured for this container")
    return deps.posting


def dict_posting(kv: KV, account: Account) -> Posting:
    return Posting(DictPostingRepo(kv, account.id), PostingClaims(kv), lambda: [account],
                   _no_source, account.id)  # fmt: skip


def build_posting(settings: Settings, kv: KV, db: Database | None) -> Posting:
    claims = PostingClaims(kv)
    default = settings.posting_account_id
    if db is None:
        if settings.state_reads == "postgres":
            return Posting(cast(PostingRepo, _Unavailable(NO_DATABASE)), claims, lambda: [],
                           _no_source, default, requires_source=True, problem=NO_DATABASE)  # fmt: skip  # noqa: E501
        return dict_posting(kv, env_account(settings))
    dict_repo, sql = DictPostingRepo(kv, default), SqlPostingRepo(db)
    sources = SourcesRepo(db)
    if settings.state_reads == "postgres":
        return Posting(DualPostingRepo(sql, dict_repo), claims, AccountsRepo(db).list,
                       sources.get, default, requires_source=True,
                       schedules=lambda: read_schedules(kv))  # fmt: skip
    env = env_account(settings)
    return Posting(DualPostingRepo(dict_repo, sql), claims, lambda: [env], sources.get, default)

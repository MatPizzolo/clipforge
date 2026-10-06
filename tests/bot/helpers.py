"""Shared bot test contexts: the Dict posting store (today) and two accounts on Postgres."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from clipforge.accounts.service import publish_schedule
from clipforge.bot.context import BotContext
from clipforge.db.engine import Database
from clipforge.models import LEGACY_PLATFORMS
from clipforge.posting.backend import build_posting, dict_posting
from tests.bot.fakes import ALLOWED_USER, FakeSender, make_settings
from tests.dbhelpers import BILLY_SOURCE, make_account, seed
from tests.pipeline.harness import Harness
from tests.posting.builders import JOB, item

if TYPE_CHECKING:
    from clipforge.dispatch.tasks import DispatchCtx


def dict_ctx(tmp_path: Path) -> BotContext:
    """Today's setup: the Dict posting store, account #1 with a posting chat."""
    deps = Harness.build(tmp_path).deps
    deps.posting = dict_posting(deps.store.kv, make_account(chat_id=ALLOWED_USER))
    return BotContext(make_settings(tmp_path), FakeSender(), deps)


def two_account_ctx(tmp_path: Path, db: Database, founder_chat: int = ALLOWED_USER) -> BotContext:
    """realtalk (slot 08:00 New York) and founder (slot 09:00 Mexico City), both with clips."""
    accounts = [make_account(chat_id=ALLOWED_USER, slots=["08:00"]),
                make_account("founder-tapes-en", chat_id=founder_chat, slots=["09:00"],
                             timezone="America/Mexico_City")]  # fmt: skip
    seed(db, *accounts,
         sources=[BILLY_SOURCE, BILLY_SOURCE.model_copy(
             update={"id": "founder-src", "account_id": "founder-tapes-en"})])  # fmt: skip
    settings = make_settings(tmp_path, state_reads="postgres")
    deps = Harness.build(tmp_path).deps
    for account in accounts:  # as the accounts service does on create (card 002 A3)
        publish_schedule(deps.store.kv, account)
    deps.posting = build_posting(settings, deps.store.kv, db)
    for acct, src, hash_ in (("realtalk-clips-en", "billy-garton", "a" * 64),
                             ("founder-tapes-en", "founder-src", "b" * 64)):  # fmt: skip
        it = item(account=acct, channel=src, source_hash=hash_, job_id=JOB if hash_ == "a" * 64
                  else "20260928-bbbbbbbb-0001")  # fmt: skip
        (tmp_path / it.video_path).parent.mkdir(parents=True, exist_ok=True)  # type: ignore[arg-type]
        (tmp_path / it.video_path).write_bytes(b"mp4")  # type: ignore[arg-type]
        deps.posting.repo.add(it, list(LEGACY_PLATFORMS))
    return BotContext(settings, FakeSender(), deps)


def dispatch_ctx(ctx: BotContext, spawned: list[tuple[str, str]] | None = None) -> DispatchCtx:
    """The dispatcher's context over a bot test context, as runtime.build_dispatch_ctx builds
    it in production."""
    from clipforge.dispatch.tasks import DispatchCtx

    assert ctx.deps.posting is not None
    calls = spawned if spawned is not None else []
    return DispatchCtx(settings=ctx.settings, kv=ctx.deps.store.kv, posting=ctx.deps.posting,
                       bot=ctx, spawn=lambda n, k: calls.append((n, k)),
                       ops=ctx.deps.ops)  # fmt: skip


def tick(ctx: BotContext, now: datetime) -> str:
    """One dispatcher tick, reported in `posting_tick`'s old format ("<account>: <outcome>"
    joined by "; " in account order, "off" when no account posts), so S1's tick tests pin the
    dispatcher path unchanged (card 014 Task 7)."""
    from clipforge.dispatch.tasks import tick as dispatch_tick

    lines = dispatch_tick(dispatch_ctx(ctx), now)
    if lines == ["idle"]:
        return "off"
    out = []
    for line in lines:
        key, _, outcome = line.partition(": ")
        if outcome and ":" in key and not key.startswith(("off", "outage")):
            key = key.split(":", 1)[0]  # "<account>:<slot>" -> "<account>"
        out.append(f"{key}: {outcome}" if outcome else line)
    return "; ".join(sorted(out))

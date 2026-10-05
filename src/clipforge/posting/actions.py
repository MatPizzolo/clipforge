"""The posting actions both surfaces share (ADR-44, docs/studio/08 §2b).

Telegram's taps and commands call these, and S3's admin endpoint will too, so one backend
writes each change. Every write carries an actor (`telegram:<user id>`, `web:<login>`,
`session:<name>` or `cli:<os user>`), which Postgres keeps in `post_events.data.actor`
(S3c D3). A database error becomes `ActionFailed(STORE_UNAVAILABLE)`: the primary store
raised before writing, and the Dual mirror only runs after a primary success, so nothing
changed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime

from clipforge.bot import messages
from clipforge.bot.context import BotContext
from clipforge.bot.deeplinks import item_row
from clipforge.bot.posting import keyboard
from clipforge.bot.posting import send_next as _send_next
from clipforge.bot.telegram import not_modified
from clipforge.db.engine import is_db_error, redact
from clipforge.models import Platform, PostVerdict, RejectReason
from clipforge.posting.backend import Posting, posting_of
from clipforge.posting.keepalive import clear_outage

log = logging.getLogger(__name__)

# ADR-42's actors: telegram:<id>, web:<login>, session:<name>, and the CLI's cli:<os user>
ACTOR = re.compile(
    r"telegram:\d{1,20}|web:[A-Za-z0-9-]{1,39}|session:[a-z0-9][a-z0-9-]{0,39}"
    r"|cli:[A-Za-z0-9._-]{1,32}"
)
_LOGIN = re.compile(r"[A-Za-z0-9-]{1,39}")  # a GitHub login


class ActionFailed(Exception):
    """The action changed nothing; `str(exc)` is safe to show."""


def telegram_actor(user_id: int) -> str:
    return f"telegram:{user_id}"


def web_actor(header: str | None) -> str:
    """The dashboard's `X-Clipforge-Actor` header (the signed-in GitHub login, or `web:<login>`)
    as an actor. Raises ValueError for anything else, so a write is never anonymous."""
    login = (header or "").strip().removeprefix("web:")
    if not _LOGIN.fullmatch(login):
        raise ValueError("X-Clipforge-Actor must be the dashboard user's login")
    return f"web:{login}"


def _checked(actor: str) -> str:
    if not ACTOR.fullmatch(actor):
        raise ValueError(f"not an actor: {actor!r}")
    return actor


@contextmanager
def _store(action: str, subject: str) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        if not is_db_error(exc):
            raise
        log.warning("posting: %s on %s failed: %s", action, subject, redact(exc))
        raise ActionFailed(messages.STORE_UNAVAILABLE) from None


def _write[T](action: str, ref: str, call: Callable[[], T]) -> T:
    with _store(action, ref):
        return call()


# ---- item actions


def set_posted(
    posting: Posting, ref: str, platform: Platform, on: bool | None, actor: str, now: datetime
) -> bool:
    """✅ per platform. `on=None` toggles (a Telegram tap); the dashboard sets it explicitly.
    Returns the new state."""
    actor = _checked(actor)
    if on is None:
        return _write("set_posted", ref,
                      lambda: posting.repo.toggle_posted(ref, platform, now, actor))  # fmt: skip
    _write("set_posted", ref, lambda: posting.repo.set_posted(ref, platform, on, now, actor))
    return on


def skip(posting: Posting, ref: str, actor: str, now: datetime) -> None:
    actor = _checked(actor)
    verdict = PostVerdict(kind="skipped", at=now)
    _write("skip", ref, lambda: posting.repo.set_verdict(ref, verdict, actor))


def reject(posting: Posting, ref: str, actor: str, now: datetime) -> None:
    actor = _checked(actor)
    verdict = PostVerdict(kind="rejected", at=now)
    _write("reject", ref, lambda: posting.repo.set_verdict(ref, verdict, actor))


def set_reason(posting: Posting, ref: str, reason: RejectReason, actor: str) -> bool:
    actor = _checked(actor)
    return _write("set_reason", ref, lambda: posting.repo.set_reason(ref, reason, actor))


# ---- account actions


def pause(ctx: BotContext, account_id: str | None, on: bool, actor: str, now: datetime) -> str:
    """`/pause [account]` and `/go [account]`; returns the reply. With several accounts, each
    one answers for itself, so a failure on one never hides what changed on another."""
    actor = _checked(actor)
    posting = posting_of(ctx.deps)
    try:
        with _store("pause", account_id or "accounts"):
            accounts = posting.posting_accounts()
    except ActionFailed as exc:
        return str(exc)
    if not accounts:
        # Posting is off (no chat): keep the flag working for the default account, so a
        # /pause sent while fixing the settings still holds once posting turns on (#96).
        if account_id is not None:
            return messages.unknown_account(account_id, [])
        outage_note = _clear_outage(ctx, actor) if not on else ""
        try:
            posting.repo.set_paused(posting.default_account_id, on, now, actor)
        except Exception as exc:
            log.warning("posting: setting the pause flag failed: %s", redact(exc))
            return messages.POSTING_OFF + outage_note
        log.info("posting: %s %s by %s", posting.default_account_id,
                 "paused" if on else "resumed", actor)  # fmt: skip
        return (messages.PAUSED if on else messages.RESUMED) + outage_note
    targets = [a for a in accounts if account_id is None or a.id == account_id]
    if account_id is not None and not targets:
        return messages.unknown_account(account_id, [a.id for a in accounts])
    outage_note = _clear_outage(ctx, actor) if not on else ""
    done = messages.PAUSED if on else messages.RESUMED
    replies = []
    for account in targets:
        try:
            with _store("pause", account.id):
                posting.repo.set_paused(account.id, on, now, actor)
            # posting_state has no actor column (0001 is frozen), so the actor is logged
            log.info("posting: %s %s by %s", account.id, "paused" if on else "resumed", actor)
            replies.append((account.id, done))
        except ActionFailed as exc:
            replies.append((account.id, str(exc)))
    if len(replies) == 1:
        reply = replies[0][1]
        return (reply if account_id is None else f"{account_id}: {reply}") + outage_note
    if all(reply == done for _, reply in replies):
        return done + outage_note
    return "\n".join(f"{name}: {reply}" for name, reply in replies) + outage_note


def _clear_outage(ctx: BotContext, actor: str) -> str:
    """`/go` is the owner's all-clear after an outage (decision log #217)."""
    if not clear_outage(ctx.deps.store.kv):
        return ""
    log.info("posting: outage flag cleared by %s", actor)
    return "\n" + messages.OUTAGE_CLEARED


def send_next(ctx: BotContext, now: datetime, account_id: str | None = None) -> str:
    """`/next [account]`, and after ⏭ Skip: the best clip now (no slot, no pause rule)."""
    try:
        with _store("send_next", account_id or "accounts"):
            return _send_next(ctx, now, account_id)
    except ActionFailed as exc:
        return str(exc)


def redraw_all(ctx: BotContext, ref: str, also: Iterable[int] = ()) -> None:
    """Redraw every Telegram message of the item (a re-sent clip has several) with buttons that
    match its state. Best effort: a failure is logged, never raised (08 §2b, staying in sync)."""
    posting = posting_of(ctx.deps)
    try:
        record = posting.repo.get(ref)
        account = posting.account(record.item.account_id) if record is not None else None
    except Exception as exc:
        log.warning("posting: re-reading %s failed: %s", ref, redact(exc))
        return
    if record is None or account is None or account.posting.chat_id is None:
        return
    buttons = keyboard(record, item_row(ctx.settings.dashboard_url, record.item))
    for message_id in sorted({*also, *(s.message_id for s in record.sends)}):
        try:
            ctx.sender.edit_buttons(account.posting.chat_id, message_id, buttons)
        except Exception as exc:
            if not_modified(exc):  # it already shows this state: done
                continue
            log.warning("posting: editing message %s of %s failed", message_id, ref,
                        exc_info=True)  # fmt: skip

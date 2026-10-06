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
from typing import Literal

from clipforge.actors import ACTOR as ACTOR  # re-exported: one pattern for every writer
from clipforge.actors import checked
from clipforge.bot import messages
from clipforge.bot.context import BotContext
from clipforge.bot.deeplinks import item_row
from clipforge.bot.posting import keyboard
from clipforge.bot.posting import send_next as _send_next
from clipforge.bot.telegram import not_modified
from clipforge.db.engine import is_db_error, redact
from clipforge.models import Account, Brake, Platform, PostVerdict, RejectReason
from clipforge.pipeline.deps import KV
from clipforge.posting import brake
from clipforge.posting.backend import Posting, posting_of
from clipforge.posting.keepalive import clear_outage
from clipforge.posting.repo import PostingRepo

log = logging.getLogger(__name__)

# The actor pattern lives in clipforge/actors.py (shared with the autopilot service)
_LOGIN = re.compile(r"[A-Za-z0-9-]{1,39}")  # a GitHub login


DAILY = "system:daily"  # posting_daily's brake repair


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
    return checked(actor)


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


def _answer_time(posting: Posting, ref: str, now: datetime) -> datetime:
    """A verdict answers the send it was made for: it is stamped no earlier than the record's
    latest send or verdict, so a container whose clock is behind the sender's can't leave the
    clip reading as `sent` (card 017 item 9, log #143). Stamping, rather than recording the
    send number, keeps the Dict and Postgres formats unchanged."""
    record = posting.repo.get(ref)
    if record is None:
        return now
    times = [now, *(s.at for s in record.sends)]
    if record.verdict is not None:
        times.append(record.verdict.at)
    return max(times)


def _set_verdict(
    posting: Posting, ref: str, kind: Literal["skipped", "rejected"], actor: str, now: datetime
) -> None:
    def write() -> None:
        verdict = PostVerdict(kind=kind, at=_answer_time(posting, ref, now))
        posting.repo.set_verdict(ref, verdict, actor)

    _write("skip" if kind == "skipped" else "reject", ref, write)


def skip(posting: Posting, ref: str, actor: str, now: datetime) -> None:
    _set_verdict(posting, ref, "skipped", _checked(actor), now)


def reject(posting: Posting, ref: str, actor: str, now: datetime) -> None:
    _set_verdict(posting, ref, "rejected", _checked(actor), now)


def set_reason(posting: Posting, ref: str, reason: RejectReason, actor: str) -> bool:
    actor = _checked(actor)
    return _write("set_reason", ref, lambda: posting.repo.set_reason(ref, reason, actor))


# ---- account actions


def pause(
    ctx: BotContext, scope: str | None, on: bool, actor: str, now: datetime,
    reason: str | None = None,
) -> str:  # fmt: skip
    """`/pause [account|all]` and `/go [account|all]` (S2 spec §6.7); returns the reply.

    1. The brake key `brake:<scope>` is written first (no scope means `all`): it is what the
       dispatcher obeys, and it survives a Neon outage. `/go all` also turns off every account
       key that is on, so it resumes everything, as `/go` always did.
    2. Then `posting_state` for each account in scope records the account's effective brake
       (on while `brake:all` or its own key is on), with the actor and reason. A database error
       there is reported per account ("recorded in the brake only"), never raised.
    With several accounts, each one answers for itself."""
    actor = _checked(actor)
    scope = scope or brake.ALL
    posting = posting_of(ctx.deps)
    kv = ctx.deps.store.kv
    try:
        with _store("pause", scope):
            accounts = posting.posting_accounts()
        listed = True
    except ActionFailed:
        accounts, listed = [], False
    if scope != brake.ALL and scope not in _known(posting, accounts):
        return messages.unknown_account(scope, [a.id for a in accounts])
    brake.write(kv, Brake(scope=scope, on=on, at=now, actor=actor, reason=reason))
    if scope == brake.ALL and not on:
        for b in brake.touch_all(kv):
            if b.scope != brake.ALL and b.on:
                brake.write(kv, Brake(scope=b.scope, on=False, at=now, actor=actor, reason=reason))
    log.info("posting: brake %s %s by %s", scope, "on" if on else "off", actor)
    outage_note = _clear_outage(ctx, actor) if not on else ""
    done = messages.PAUSED if on else messages.RESUMED
    if not on and scope != brake.ALL and brake.braked(kv, scope):
        done = messages.STILL_BRAKED
    if not listed:
        return done + messages.BRAKE_ONLY + outage_note
    if not accounts:
        # Posting is off (no chat): keep the flag working for the default account, so a
        # /pause sent while fixing the settings still holds once posting turns on (#96).
        target = posting.default_account_id
        try:
            posting.repo.set_paused(target, brake.braked(kv, target), now, actor, reason)
        except Exception as exc:
            log.warning("posting: setting the pause flag failed: %s", redact(exc))
            return messages.POSTING_OFF + outage_note
        return (done if scope == brake.ALL else f"{scope}: {done}") + outage_note
    # an account named without a posting chat still gets its row
    targets = [a.id for a in accounts] if scope == brake.ALL else [scope]
    replies = []
    for account_id in targets:
        try:
            with _store("pause", account_id):
                posting.repo.set_paused(account_id, brake.braked(kv, account_id), now, actor,
                                        reason)  # fmt: skip
            replies.append((account_id, done))
        except ActionFailed:
            replies.append((account_id, done + messages.BRAKE_ONLY))
    if len(replies) == 1 and scope != brake.ALL:
        return f"{scope}: {replies[0][1]}" + outage_note
    if all(reply == done for _, reply in replies):
        return done + outage_note
    return "\n".join(f"{name}: {reply}" for name, reply in replies) + outage_note


def _known(posting: Posting, accounts: list[Account]) -> set[str]:
    """Accounts a brake may name: those posting, plus every schedule copy (read from the Dict,
    so it works with Neon down)."""
    known = {a.id for a in accounts}
    try:
        known |= set(posting.all_schedules())
    except Exception as exc:  # dict mode without settings: posting accounts only
        log.warning("posting: reading the schedule copies failed: %s", redact(exc))
    return known


def repair_brake(
    ctx_kv: KV, repo: PostingRepo, account_id: str, *, side: Literal["key", "row"], on: bool,
    at: datetime, reason: str,
) -> None:  # fmt: skip
    """`posting_daily`'s repair (spec §6.7): write only the side that is behind, as
    `system:daily`, so pausing keeps one writer module. `key` writes `brake:<account>`; `row`
    writes `posting_state`."""
    if side == "key":
        brake.write(ctx_kv, Brake(scope=account_id, on=on, at=at, actor=DAILY, reason=reason))
    else:
        repo.set_paused(account_id, on, at, DAILY, reason)


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

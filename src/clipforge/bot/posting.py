"""The posting assistant (ADR-23): at each slot, send the next clip to the owner's phone with
copyable captions and buttons, and handle the taps. Modal-free: `app.posting_tick` calls
`tick`, the webhook calls `handle_callback` and `send_next`."""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from html import escape

import httpx
from sqlalchemy.exc import SQLAlchemyError
from telegram.error import TelegramError

from clipforge.bot import messages
from clipforge.bot.context import BotContext
from clipforge.bot.telegram import Keyboard
from clipforge.db.engine import DatabaseUnavailable, is_db_error, redact
from clipforge.jobs import is_job_id
from clipforge.models import (
    Account,
    ContentItem,
    Platform,
    PostRecord,
    PostSend,
    PostStatus,
    PostVerdict,
    RejectReason,
    Source,
)
from clipforge.posting import captions
from clipforge.posting.backend import Posting, posting_of
from clipforge.posting.queue import PAUSE_AFTER, eligible, pick_next, status, unanswered
from clipforge.posting.slots import current_slot
from clipforge.sources import hold_reason

log = logging.getLogger(__name__)

PLATFORM_ACTIONS = {"tt": Platform.TIKTOK, "ig": Platform.INSTAGRAM, "yt": Platform.YOUTUBE,
                    "fb": Platform.FACEBOOK}  # fmt: skip
ACTION_OF = {p: a for a, p in PLATFORM_ACTIONS.items()}
LABELS = {Platform.TIKTOK: "TikTok", Platform.INSTAGRAM: "Instagram",
          Platform.YOUTUBE: "YouTube", Platform.FACEBOOK: "Facebook"}  # fmt: skip
REASON_LABELS = {
    RejectReason.BORING: "Boring",
    RejectReason.BAD_CUT: "Bad cut",
    RejectReason.BAD_CROP: "Bad crop",
    RejectReason.CAPTIONS: "Captions",
    RejectReason.OTHER: "Other",
}
ACTIONS = frozenset({*PLATFORM_ACTIONS, "skip", "rej", "noop"})
# escaped characters per block: 5 blocks (with Facebook) + header stay under Telegram's 4096
BLOCK_LIMIT = 700
HEAD_LIMIT = 300
_CLIP_ID = re.compile(r"clip_\d{2}")


@dataclass(frozen=True)
class Callback:
    action: str  # tt | ig | yt | fb | skip | rej | why | noop
    ref: str  # "<job_id>:<clip_id>"
    reason: RejectReason | None = None


def parse_callback(data: str | None) -> Callback | None:
    parts = (data or "").split(":")
    if len(parts) < 4 or parts[0] != "p":
        return None
    action, reason = parts[1], None
    if action == "why":
        if len(parts) != 5:
            return None
        try:
            reason = RejectReason(parts[2])
        except ValueError:
            return None
        job_id, clip_id = parts[3], parts[4]
    else:
        if len(parts) != 4 or action not in ACTIONS:
            return None
        job_id, clip_id = parts[2], parts[3]
    if not is_job_id(job_id) or not _CLIP_ID.fullmatch(clip_id):
        return None
    return Callback(action, f"{job_id}:{clip_id}", reason)


def _platform_row(
    ref: str, platforms: list[Platform], posted: set[Platform]
) -> list[tuple[str, str]]:
    return [
        (f"{LABELS[p]} ✓" if p in posted else f"✅ {LABELS[p]}", f"p:{ACTION_OF[p]}:{ref}")
        for p in platforms
    ]


def fresh_keyboard(ref: str, platforms: list[Platform]) -> Keyboard:
    return [_platform_row(ref, platforms, set()),
            [("⏭ Skip", f"p:skip:{ref}"), ("🗑 Reject", f"p:rej:{ref}")]]  # fmt: skip


def keyboard(record: PostRecord) -> Keyboard:
    """The buttons that match the clip's current state (spec §7)."""
    ref = record.item.id
    state = status(record)
    if state is PostStatus.POSTED:
        return [[("Posted everywhere ✓", f"p:noop:{ref}")]]
    if state is PostStatus.REJECTED:
        reason = record.verdict.reason if record.verdict else None
        if reason is None:
            buttons = [(label, f"p:why:{r}:{ref}") for r, label in REASON_LABELS.items()]
            return [buttons[:3], buttons[3:]]
        return [[(f"Rejected · {REASON_LABELS[reason]}", f"p:noop:{ref}")]]
    if state is PostStatus.SKIPPED:
        return [[("Skipped ⏭", f"p:noop:{ref}")]]
    return [
        _platform_row(ref, record.platforms, set(record.posted)),
        [("⏭ Skip", f"p:skip:{ref}"), ("🗑 Reject", f"p:rej:{ref}")],
    ]


def _escaped(text: str, limit: int) -> str:
    """`text` HTML-escaped, cut so the escaped result (with "…") is at most `limit` long."""
    out: list[str] = []
    size = 0
    full = escape(text)
    if len(full) <= limit:
        return full
    for char in text:
        piece = escape(char)
        if size + len(piece) > limit - 1:
            break
        out.append(piece)
        size += len(piece)
    return "".join(out) + "…"


def _block(name: str, text: str) -> str:
    return f"<b>{name}</b>\n<pre>{_escaped(text, BLOCK_LIMIT)}</pre>"


def post_html(
    item: ContentItem, hashtags: list[str], platforms: list[Platform], links: Sequence[str] = ()
) -> str:
    """The text under the video: one tap-to-copy block per platform (HTML parse mode)."""
    credit = item.credits[0] if item.credits else ""
    head = (f"🎙️ <b>{_escaped(credit, HEAD_LIMIT // 2)}</b>"
            f" — “{_escaped(item.title, HEAD_LIMIT // 2)}”")  # fmt: skip
    blocks: list[str] = []
    for p in platforms:
        if p is Platform.TIKTOK:
            blocks.append(_block("TikTok", captions.tiktok(item, hashtags, links)))
        elif p is Platform.INSTAGRAM:
            blocks.append(_block("Instagram", captions.instagram(item, hashtags, links)))
        elif p is Platform.YOUTUBE:
            blocks.append(_block("YouTube title", captions.youtube_title(item)))
            blocks.append(_block("YouTube description",
                                 captions.youtube_description(item, hashtags, links)))  # fmt: skip
        elif p is Platform.FACEBOOK:  # until S2's per-platform copy: the TikTok caption
            blocks.append(_block("Facebook", captions.tiktok(item, hashtags, links)))
    return "\n\n".join([head, *blocks])


def extras(
    account: Account, source: Source | None, item: ContentItem
) -> tuple[list[str], list[str]]:
    """Hashtags and links for one send: #ad first when sponsored, then a campaign's required
    tags, then the account's own (spec §6.3)."""
    tags = list(account.posting.hashtags)
    links: list[str] = []
    if source is not None and source.campaign is not None:
        required = source.campaign.required_tags
        tags = [*required, *(t for t in tags if t not in required)]
        links = [str(link) for link in source.campaign.required_links]
    if item.sponsored:
        tags = ["ad", *(t for t in tags if t != "ad")]
    return tags, links


def held(record: PostRecord, source: Source | None, now: datetime) -> str | None:
    """Why this clip can't be sent now (spec §6.3 hold rules), or None."""
    return hold_reason(source, record.platforms, now)


def video_caption(item: ContentItem, waiting: int, account_id: str | None = None) -> str:
    credit = item.credits[0] if item.credits else ""
    episode = item.clip.episode if item.clip else item.id
    prefix = f"{account_id} · " if account_id else ""
    return f"{prefix}{credit} · {episode} · {item.score:.2f} · {waiting} queued"


class _Sources:
    """Source lookups cached for one tick."""

    def __init__(self, posting: Posting) -> None:
        self._posting = posting
        self._cache: dict[str, Source | None] = {}

    def __call__(self, source_id: str | None) -> Source | None:
        if source_id is None:
            return None
        if source_id not in self._cache:
            self._cache[source_id] = self._posting.source(source_id)
        return self._cache[source_id]


# ---- sending (spec §6)

MAX_PICKS = 3  # clips tried per send when videos turn out to be missing


class SendFailed(Exception):
    """Telegram refused part of a send; nothing was recorded (spec §6)."""


def _deliver(
    ctx: BotContext,
    posting: Posting,
    account: Account,
    sources: _Sources,
    record: PostRecord,
    slot: datetime | None,
    now: datetime,
    waiting: int,
) -> bool:
    """Send one clip: the video, then the text with buttons replying to it. False if its video
    is missing (marked unavailable). Raises SendFailed after rolling back a partial send."""
    item = record.item
    store = posting.repo
    chat = account.posting.chat_id
    assert chat is not None
    tags, links = extras(account, sources(item.source_id), item)
    # the account label only matters when a second account shares the chat
    label = account.id if len(posting.posting_accounts()) > 1 else None
    if item.video_path is None:
        log.warning("posting: %s has no video", item.id)
        store.mark_unavailable(item.id, now)
        return False
    path = ctx.deps.root / item.video_path
    if not path.is_file():
        # A warm web container may predate the package_step commit that wrote this clip.
        try:
            ctx.deps.volume.reload()
        except Exception:
            log.warning("posting: volume reload failed; the file view may be stale", exc_info=True)
    if not path.is_file():
        log.warning("posting: video missing for %s", item.id)
        store.mark_unavailable(item.id, now)
        return False
    video_id: int | None = None
    try:
        video_id = ctx.sender.send_video(chat, path, video_caption(item, waiting, label))
        text_id = ctx.sender.send_message(
            chat,
            post_html(item, tags, record.platforms, links),
            video_id,
            buttons=fresh_keyboard(item.id, record.platforms),
            html=True,
        )
    except Exception as exc:
        # Telegram/httpx errors can carry the bot-token URL and DB errors the database URL, so
        # a traceback (which prints them raw) is added only for other errors.
        bug = not (is_db_error(exc) or isinstance(exc, (httpx.HTTPError, TelegramError)))
        log.warning("posting: sending %s failed: %s", item.id, redact(exc), exc_info=bug)
        if video_id is not None:
            with contextlib.suppress(Exception):
                ctx.sender.delete_message(chat, video_id)
        raise SendFailed(item.id) from exc
    n = max((s.n for s in record.sends), default=0) + 1  # never reuse a number (review M4)
    send = PostSend(n=n, at=now, slot=slot, message_id=text_id, video_message_id=video_id)
    try:
        recorded = store.add_send(item.id, send, chat)
    except Exception:
        # Both messages are out but unrecorded: take them back (best effort) before the caller
        # releases the slot, or the next tick would send this clip again.
        for message_id in (text_id, video_id):
            try:
                ctx.sender.delete_message(chat, message_id)
            except Exception:
                log.warning("posting: deleting the unrecorded send of %s failed", item.id,
                            exc_info=True)  # fmt: skip
        raise
    if not recorded:
        # Another caller (a tick, /next, a parallel Skip) sent this clip first and recorded it:
        # take back this untracked duplicate and count the send as done.
        log.warning("posting: %s was already sent as sent:%d; deleting the duplicate", item.id, n)
        for message_id in (text_id, video_id):
            try:
                ctx.sender.delete_message(chat, message_id)
            except Exception:
                log.warning("posting: deleting a duplicate of %s failed", item.id, exc_info=True)
    return True


def _send_best(
    ctx: BotContext,
    posting: Posting,
    account: Account,
    sources: _Sources,
    records: list[PostRecord],
    slot: datetime | None,
    now: datetime,
) -> str | None:
    """Send the best eligible clip; returns its ref, or None when nothing is eligible."""
    for _ in range(MAX_PICKS):
        record = pick_next(records, now)
        if record is None:
            return None
        waiting = sum(eligible(r, now) for r in records) - 1
        if _deliver(ctx, posting, account, sources, record, slot, now, waiting):
            return record.item.id
        records = [
            r.model_copy(update={"unavailable": True}) if r.item.id == record.item.id else r
            for r in records
        ]
    return None


def tick(ctx: BotContext, now: datetime) -> str:
    """One cron tick (spec §5.2): each account with a posting chat, in id order."""
    posting = posting_of(ctx.deps)
    if posting.problem is not None:
        log.warning("posting: %s", posting.problem)
        return f"off: {posting.problem}"
    results = []
    for account in posting.posting_accounts():
        try:
            results.append(f"{account.id}: {_tick_account(ctx, posting, account, now)}")
        except Exception as exc:  # one account's failure never stops the others
            # tracebacks only for code bugs: a driver error's can carry the database URL
            bug = not isinstance(exc, SQLAlchemyError | DatabaseUnavailable)
            log.warning("posting: tick for %s failed: %s", account.id, redact(exc), exc_info=bug)
            results.append(f"{account.id}: error")
    return "; ".join(results) or "off"


def _tick_account(ctx: BotContext, posting: Posting, account: Account, now: datetime) -> str:
    if posting.repo.paused(account.id):
        return "paused"
    slot = current_slot(account.posting, now)
    if slot is None:
        return "no slot"
    sources = _Sources(posting)
    records = [r for r in posting.repo.records(account.id)
               if held(r, sources(r.item.source_id), now) is None]  # fmt: skip
    chat = account.posting.chat_id
    assert chat is not None
    waiting = unanswered(records)
    if len(waiting) >= PAUSE_AFTER:
        oldest = min(r.sends[-1].at for r in waiting)
        if posting.claims.claim_reminder(account.id, oldest):
            ctx.sender.send_message(chat, messages.waiting_reminder(len(waiting)))
        return "waiting"
    if not posting.claims.claim_slot(account.id, slot):
        return "taken"
    try:
        ref = _send_best(ctx, posting, account, sources, records, slot, now)
    except SendFailed:
        posting.claims.release_slot(account.id, slot)
        return "send failed"
    except Exception:
        posting.claims.release_slot(account.id, slot)
        raise
    return f"sent {ref}" if ref else "empty"


def send_next(ctx: BotContext, now: datetime, account_id: str | None = None) -> str:
    """`/next [account]` and after ⏭ Skip: send the best clip now (no slot, no pause rule)."""
    posting = posting_of(ctx.deps)
    accounts = posting.posting_accounts()
    if not accounts:
        return messages.POSTING_OFF
    if account_id is not None:
        accounts = [a for a in accounts if a.id == account_id]
        if not accounts:
            return messages.unknown_account(account_id, [a.id for a in posting.posting_accounts()])
    replies = []
    for account in accounts:
        sources = _Sources(posting)
        try:
            records = [r for r in posting.repo.records(account.id)
                       if held(r, sources(r.item.source_id), now) is None]  # fmt: skip
            ref = _send_best(ctx, posting, account, sources, records, None, now)
            reply = "" if ref else messages.QUEUE_EMPTY
        except SendFailed:
            reply = messages.SEND_FAILED
        if reply:
            replies.append(reply if len(accounts) == 1 else f"{account.id}: {reply}")
    return "\n".join(replies)


def handle_callback(
    ctx: BotContext, callback_id: str, data: str | None, chat_id: int | None,
    message_id: int | None, now: datetime,
) -> None:  # fmt: skip
    """One button tap (spec §8). Always answers the tap; edits the buttons to the new state."""

    def answer(text: str) -> None:
        # The state is written before the answer and the update is already claimed, so a failed
        # answer ("query is too old" after a cold start) must not stop the rest of the tap.
        try:
            ctx.sender.answer_callback(callback_id, text)
        except Exception:
            log.warning("posting: answering tap %s failed", callback_id, exc_info=True)

    posting = posting_of(ctx.deps)
    parsed = parse_callback(data)
    if parsed is None or chat_id is None or message_id is None:
        answer("")
        return
    store = posting.repo
    try:
        record = store.get(parsed.ref)
    except Exception as exc:
        log.warning("posting: reading %s failed: %s", parsed.ref, redact(exc))
        answer(messages.SAVE_FAILED)
        return
    if record is None:
        answer(messages.GONE)
        return
    account = posting.account(record.item.account_id)
    if account is None or account.posting.chat_id != chat_id:
        answer("")
        return

    def redraw(rec: PostRecord) -> None:
        """Every message of the clip shows the same buttons (a re-sent clip has several)."""
        for mid in sorted({message_id, *(s.message_id for s in rec.sends)}):
            try:
                ctx.sender.edit_buttons(chat_id, mid, keyboard(rec))
            except Exception:
                log.warning("posting: editing message %s of %s failed", mid, parsed.ref,
                            exc_info=True)  # fmt: skip

    current = keyboard(record)
    if data not in {d for row in current for _, d in row}:  # a stale button: change nothing
        answer("")
        redraw(record)
        return
    note, then_next = "", False
    try:
        if parsed.action in PLATFORM_ACTIONS:
            platform = PLATFORM_ACTIONS[parsed.action]
            on = store.toggle_posted(parsed.ref, platform, now)
            note = f"{LABELS[platform]} ✓" if on else f"{LABELS[platform]} undone"
        elif parsed.action == "skip":
            store.set_verdict(parsed.ref, PostVerdict(kind="skipped", at=now))
            note, then_next = "Skipped", True
        elif parsed.action == "rej":
            store.set_verdict(parsed.ref, PostVerdict(kind="rejected", at=now))
            note = "Rejected. Why? (optional)"
        elif parsed.action == "why" and parsed.reason is not None:
            store.set_reason(parsed.ref, parsed.reason)
            note = "Thanks"
    except Exception as exc:
        log.warning("posting: saving a tap on %s failed: %s", parsed.ref, redact(exc))
        answer(messages.SAVE_FAILED)
        return
    answer(note)
    if parsed.action != "noop":
        try:
            updated = store.get(parsed.ref)
        except Exception as exc:
            log.warning("posting: re-reading %s failed: %s", parsed.ref, redact(exc))
            updated = None
        if updated is not None:
            redraw(updated)
    if then_next:
        reply = send_next(ctx, now, record.item.account_id)
        if reply:
            ctx.sender.send_message(chat_id, reply)

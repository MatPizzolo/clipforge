"""Handle one Telegram update (webhook mode, spec §5). The API's webhook route calls this
after checking Telegram's secret-token header."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Message, Update

from clipforge.bot.commands import (
    ClipCommand,
    CommandError,
    JobCommand,
    PostingCommand,
    build_job_input,
    parse_caption,
    parse_text,
)
from clipforge.bot.context import BotContext
from clipforge.bot.messages import (
    TOO_BIG,
    USAGE,
    job_accepted,
    posting_overview_text,
    status_text,
)
from clipforge.bot.posting import handle_callback
from clipforge.jobs import is_job_id, utcnow
from clipforge.links import with_download_url
from clipforge.models import JobInput, TelegramTarget
from clipforge.pipeline.steps import JobNotResumable
from clipforge.posting import actions
from clipforge.service import create_job, get_job_view, posting_overview, resume_job

__all__ = ["BotContext", "handle_update"]  # BotContext lives in bot/context.py

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # the Bot API's getFile limit (ADR-10)


def handle_update(body: dict[str, Any], ctx: BotContext) -> None:
    update = Update.de_json(body, None)
    query = update.callback_query
    if query is not None:
        if query.from_user.id not in ctx.settings.telegram_allowed_user_ids:
            log.info("ignoring a tap %s from a user not in the allow list", update.update_id)
            return
        if not ctx.deps.store.claim_update(update.update_id):
            return
        tapped = query.message
        handle_callback(
            ctx, query.id, query.data,
            tapped.chat.id if tapped else None, tapped.message_id if tapped else None,
            utcnow(), query.from_user.id,
        )  # fmt: skip
        return
    message = update.message  # edited messages and channel posts are ignored
    if message is None or message.from_user is None:
        return
    if message.from_user.id not in ctx.settings.telegram_allowed_user_ids:
        log.info("ignoring update %s from a user not in the allow list", update.update_id)
        return
    if not ctx.deps.store.claim_update(update.update_id):
        return
    target = TelegramTarget(chat_id=message.chat.id, reply_to_message_id=message.message_id)
    try:
        reply = _reply_for(message, target, ctx)
    except CommandError as exc:
        reply = str(exc)
    if reply:
        ctx.sender.send_message(target.chat_id, reply, target.reply_to_message_id)


def _reply_for(message: Message, target: TelegramTarget, ctx: BotContext) -> str:
    upload = message.video or message.document
    if upload is not None:
        if upload.file_size is not None and upload.file_size > MAX_UPLOAD_BYTES:
            return TOO_BIG
        options = parse_caption(message.caption)
        job_input = build_job_input(ctx.settings, options, target, telegram_file_id=upload.file_id)
        return _submit(ctx, job_input)
    if not message.text:
        return USAGE
    command = parse_text(message.text)
    match command:
        case ClipCommand(url=url, options=options):
            return _submit(ctx, build_job_input(ctx.settings, options, target, url=url))
        case JobCommand(name="status", job_id=job_id):
            return _status(ctx, job_id)
        case JobCommand(name="resume", job_id=job_id):
            return _resume(ctx, job_id)
        case PostingCommand(name="overview"):
            view = posting_overview(ctx.deps, ctx.settings, utcnow())
            return posting_overview_text(view, ctx.settings.posting_timezone)
        case PostingCommand(name="next", account=account):
            return actions.send_next(ctx, utcnow(), account)
        case PostingCommand(name="pause" | "go" as name, account=account):
            actor = actions.telegram_actor(message.from_user.id) if message.from_user else ""
            return actions.pause(ctx, account, name == "pause", actor, utcnow())
        case _:
            return USAGE


def _submit(ctx: BotContext, job_input: JobInput) -> str:
    return job_accepted(create_job(ctx.deps, job_input).job_id)


def _status(ctx: BotContext, job_id: str) -> str:
    if not is_job_id(job_id):
        return f"No job {job_id}."
    try:
        view = get_job_view(ctx.deps.store, ctx.deps.root, job_id)
    except KeyError:
        return f"No job {job_id}."
    return status_text(with_download_url(view, ctx.settings))


def _resume(ctx: BotContext, job_id: str) -> str:
    if not is_job_id(job_id):
        return f"No job {job_id}."
    try:
        resume_job(ctx.deps, job_id)
    except KeyError:
        return f"No job {job_id}."
    except JobNotResumable as exc:
        return str(exc)
    return f"Resuming job {job_id}."

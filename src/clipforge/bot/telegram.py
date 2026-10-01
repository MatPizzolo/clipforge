"""A small synchronous wrapper over python-telegram-bot's async `Bot` (webhook mode, no
polling `Application`, spec §5).

Each call builds a fresh `Bot` and HTTP client inside `asyncio.run`, so it works from the sync
Modal step functions and from FastAPI's worker threads, and never shares a client across event
loops. The token is never logged or shown in `repr` (CLAUDE.md rule 8).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    ReplyParameters,
)
from telegram.constants import ParseMode
from telegram.request import BaseRequest, HTTPXRequest

CAPTION_LIMIT = 1024
UPLOAD_TIMEOUT_S = 300.0  # a 45 MB clip on a slow uplink
Button = tuple[str, str]  # (label, callback data), or (label, "https://…") for a URL button
Keyboard = list[list[Button]]
UPDATE_TYPES = ["message", "callback_query"]

# httpx logs every request URL at INFO, and Bot API URLs contain the bot token (rule 8).
logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramSender(Protocol):
    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        *,
        buttons: Keyboard | None = None,
        html: bool = False,
    ) -> int: ...

    def send_video(
        self, chat_id: int, path: Path, caption: str, reply_to: int | None = None
    ) -> int: ...

    def edit_buttons(self, chat_id: int, message_id: int, buttons: Keyboard | None) -> None: ...

    def answer_callback(self, callback_id: str, text: str = "") -> None: ...

    def delete_message(self, chat_id: int, message_id: int) -> None: ...


def is_url(data: str) -> bool:
    """Callback data never starts with a scheme (it's `p:…`), so a URL is a link button."""
    return data.startswith(("https://", "http://"))


def _button(label: str, data: str) -> InlineKeyboardButton:
    if is_url(data):
        return InlineKeyboardButton(label, url=data)
    return InlineKeyboardButton(label, callback_data=data)


def _markup(buttons: Keyboard | None) -> InlineKeyboardMarkup | None:
    if buttons is None:
        return None
    return InlineKeyboardMarkup([[_button(label, data) for label, data in row] for row in buttons])


def default_request() -> BaseRequest:
    return HTTPXRequest(
        connection_pool_size=1,
        read_timeout=60.0,
        write_timeout=60.0,
        connect_timeout=10.0,
        media_write_timeout=UPLOAD_TIMEOUT_S,
    )


def _reply(message_id: int | None) -> ReplyParameters | None:
    if message_id is None:
        return None
    return ReplyParameters(message_id=message_id, allow_sending_without_reply=True)


class TelegramClient:
    def __init__(
        self, token: str, request_factory: Callable[[], BaseRequest] = default_request
    ) -> None:
        self._token = token
        self._request_factory = request_factory

    def __repr__(self) -> str:
        return "TelegramClient(token=***)"

    def _run[T](self, call: Callable[[Bot], Awaitable[T]]) -> T:
        async def main() -> T:
            request = self._request_factory()
            bot = Bot(self._token, request=request, get_updates_request=request)
            try:
                return await call(bot)
            finally:
                await request.shutdown()

        return asyncio.run(main())

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        *,
        buttons: Keyboard | None = None,
        html: bool = False,
    ) -> int:
        message = self._run(
            lambda bot: bot.send_message(
                chat_id,
                text,
                reply_parameters=_reply(reply_to),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=_markup(buttons),
                parse_mode=ParseMode.HTML if html else None,
            )
        )
        return message.message_id

    def send_video(
        self, chat_id: int, path: Path, caption: str, reply_to: int | None = None
    ) -> int:
        async def call(bot: Bot) -> Any:
            with path.open("rb") as video:
                return await bot.send_video(
                    chat_id,
                    video,
                    caption=caption[:CAPTION_LIMIT],
                    supports_streaming=True,
                    reply_parameters=_reply(reply_to),
                )

        return int(self._run(call).message_id)

    def edit_buttons(self, chat_id: int, message_id: int, buttons: Keyboard | None) -> None:
        self._run(
            lambda bot: bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=_markup(buttons)
            )
        )

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._run(lambda bot: bot.answer_callback_query(callback_id, text=text or None))

    def delete_message(self, chat_id: int, message_id: int) -> None:
        self._run(lambda bot: bot.delete_message(chat_id, message_id))

    def set_webhook(self, url: str, secret: str) -> None:
        self._run(
            lambda bot: bot.set_webhook(url, secret_token=secret, allowed_updates=UPDATE_TYPES)
        )

"""Telegram fakes: a recording TelegramSender, a PTB BaseRequest that never hits the network,
and builders for update JSON and test settings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telegram.request import BaseRequest, RequestData

from clipforge.bot.telegram import Keyboard, VideoSize
from clipforge.config import Settings

ALLOWED_USER = 42
CHAT = 7


@dataclass
class FakeSender:
    messages: list[tuple[int, str, int | None]] = field(default_factory=list)
    videos: list[tuple[int, Path, str, int | None]] = field(default_factory=list)
    sizes: list[VideoSize | None] = field(default_factory=list)  # one per video, in order
    keyboards: dict[int, Keyboard | None] = field(default_factory=dict)  # message id -> buttons
    answers: list[tuple[str, str]] = field(default_factory=list)
    deleted: list[tuple[int, int]] = field(default_factory=list)
    fail: bool = False
    fail_on: set[str] = field(default_factory=set)  # method names that raise
    next_id: int = 100

    def _check(self, name: str) -> None:
        if self.fail or name in self.fail_on:
            raise RuntimeError("telegram is down")

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        *,
        buttons: Keyboard | None = None,
        html: bool = False,
    ) -> int:
        self._check("send_message")
        self.messages.append((chat_id, text, reply_to))
        message_id = self._id()
        self.keyboards[message_id] = buttons
        return message_id

    def send_video(
        self,
        chat_id: int,
        path: Path,
        caption: str,
        reply_to: int | None = None,
        *,
        size: VideoSize | None = None,
    ) -> int:
        self._check("send_video")
        self.videos.append((chat_id, path, caption, reply_to))
        self.sizes.append(size)
        return self._id()

    def edit_buttons(self, chat_id: int, message_id: int, buttons: Keyboard | None) -> None:
        self._check("edit_buttons")
        self.keyboards[message_id] = buttons

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._check("answer_callback")
        self.answers.append((callback_id, text))

    def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


def callback(
    update_id: int,
    data: str,
    *,
    message_id: int = 500,
    chat_id: int = ALLOWED_USER,
    user_id: int = ALLOWED_USER,
) -> dict[str, Any]:
    """A button tap (callback_query update) on message `message_id` in `chat_id`."""
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": "M"},
            "chat_instance": "ci",
            "data": data,
            "message": {
                "message_id": message_id,
                "date": 0,
                "chat": {"id": chat_id, "type": "private"},
            },
        },
    }


class FakeRequest(BaseRequest):
    """Records Bot API calls as (method, parameters, has_files) and answers `ok`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], bool]] = []
        self.shutdowns = 0

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        self.shutdowns += 1

    @property
    def read_timeout(self) -> float | None:
        return None

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: RequestData | None = None,
        read_timeout: Any = None,
        write_timeout: Any = None,
        connect_timeout: Any = None,
        pool_timeout: Any = None,
    ) -> tuple[int, bytes]:
        name = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        has_files = bool(request_data and request_data.multipart_data)
        self.calls.append((name, params, has_files))
        result: object = True
        if name.startswith("send"):
            result = {"message_id": 99, "date": 0, "chat": {"id": CHAT, "type": "private"}}
        return 200, json.dumps({"ok": True, "result": result}).encode()


def make_settings(root: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "api_token": "t0ken",
        "api_url": "https://api.example",
        "download_signing_key": "k3y",
        "telegram_bot_token": "123:abc",
        "telegram_webhook_secret": "hook-secret",
        "telegram_allowed_user_ids": [ALLOWED_USER],
        "jobs_root": root,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def update(
    update_id: int = 1,
    *,
    text: str | None = None,
    user_id: int = ALLOWED_USER,
    message_id: int = 3,
    kind: str = "message",
    **fields: Any,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": message_id,
        "date": 0,
        "chat": {"id": CHAT, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "M"},
        **fields,
    }
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, kind: message}


def video(file_size: int | None, file_id: str = "VID") -> dict[str, Any]:
    return {
        "file_id": file_id,
        "file_unique_id": f"U{file_id}",
        "width": 1920,
        "height": 1080,
        "duration": 30,
        "file_size": file_size,
    }

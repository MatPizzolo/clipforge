"""TelegramClient: the sync bridge over python-telegram-bot, without network."""

from __future__ import annotations

import json
from pathlib import Path

from clipforge.bot.telegram import TelegramClient
from tests.bot.fakes import FakeRequest


def _client() -> tuple[TelegramClient, FakeRequest]:
    request = FakeRequest()
    return TelegramClient("123:abc", request_factory=lambda: request), request


def test_send_message_replies_and_disables_previews() -> None:
    client, request = _client()
    client.send_message(7, "hello", reply_to=3)
    name, params, _ = request.calls[-1]
    assert name == "sendMessage"
    assert params["chat_id"] == 7 and params["text"] == "hello"
    assert params["reply_parameters"] == {"message_id": 3, "allow_sending_without_reply": True}
    assert params["link_preview_options"] == {"is_disabled": True}
    assert request.shutdowns == 1  # every call closes its HTTP client


def test_send_message_without_reply() -> None:
    client, request = _client()
    client.send_message(7, "hi")
    assert "reply_parameters" not in request.calls[-1][1]


def test_send_video_uploads_the_file(tmp_path: Path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00" * 16)
    client, request = _client()
    client.send_video(7, path, "x" * 2000, reply_to=3)
    name, params, has_files = request.calls[-1]
    assert name == "sendVideo" and has_files
    assert params["supports_streaming"] is True
    assert len(params["caption"]) == 1024  # Telegram's caption limit


def test_set_webhook_sends_secret_and_the_update_types() -> None:
    client, request = _client()
    client.set_webhook("https://api.example/telegram/webhook", "hook-secret")
    name, params, _ = request.calls[-1]
    assert name == "setWebhook"
    assert params == {
        "url": "https://api.example/telegram/webhook",
        "secret_token": "hook-secret",
        "allowed_updates": ["message", "callback_query"],
    }


def test_repr_hides_the_token() -> None:
    client, _ = _client()
    assert "123:abc" not in repr(client)


def test_send_message_with_buttons_and_html_returns_the_id() -> None:
    client, request = _client()
    message_id = client.send_message(
        7, "<b>hi</b>", buttons=[[("✅ TikTok", "p:tt:J:clip_01")]], html=True
    )
    assert message_id == 99  # FakeRequest answers message_id 99
    _, params, _ = request.calls[-1]
    assert params["parse_mode"] == "HTML"
    markup = params["reply_markup"]
    markup = json.loads(markup) if isinstance(markup, str) else markup
    assert markup == {
        "inline_keyboard": [[{"text": "✅ TikTok", "callback_data": "p:tt:J:clip_01"}]]
    }


def test_send_video_returns_the_id(tmp_path: Path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00")
    client, _ = _client()
    assert client.send_video(7, path, "c") == 99


def test_edit_answer_delete() -> None:
    client, request = _client()
    client.edit_buttons(7, 5, [[("Posted everywhere ✓", "p:noop:J:clip_01")]])
    client.edit_buttons(7, 5, None)
    client.answer_callback("cb1", "TikTok ✓")
    client.delete_message(7, 5)
    names = [name for name, _, _ in request.calls]
    assert names == [
        "editMessageReplyMarkup", "editMessageReplyMarkup", "answerCallbackQuery", "deleteMessage"
    ]  # fmt: skip
    assert request.calls[2][1]["text"] == "TikTok ✓"


def test_httpx_request_urls_are_not_logged_at_info() -> None:
    """httpx logs every request URL at INFO, and Bot API URLs carry the token (rule 8)."""
    import logging

    import clipforge.bot.telegram  # noqa: F401

    root = logging.getLogger()
    before = root.level
    root.setLevel(logging.INFO)  # as a host that logs INFO would
    try:
        assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    finally:
        root.setLevel(before)


def test_a_url_in_a_keyboard_is_a_link_button() -> None:
    # card 002 A4: dashboard deep links (ADR-44) ride in the same Keyboard type
    client, request = _client()
    client.send_message(7, "hi", buttons=[[("Job ↗", "https://dash.example/jobs/J")]])
    _, params, _ = request.calls[-1]
    markup = params["reply_markup"]
    markup = json.loads(markup) if isinstance(markup, str) else markup
    assert markup == {
        "inline_keyboard": [[{"text": "Job ↗", "url": "https://dash.example/jobs/J"}]]
    }

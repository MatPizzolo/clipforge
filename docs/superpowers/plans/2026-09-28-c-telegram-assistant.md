> **Historical (posting assistant, plans A, B and C, ADR-22–24, live since 2026-09-29):** built and deployed; the "not deployed" status below is from before that. docs/ARCHITECTURE.md and the code are current.

# Plan C: Telegram posting assistant — Implementation Plan

> **Status (2026-09-29): complete, not deployed.** Tasks 1–6 done and the final review's fixes applied (webhook sends reload the Volume before marking a clip unavailable, a lost send race deletes its duplicate, tap answers can't abort a tap, restore by date, tick timeout 600 s, httpx logs quiet). Deferred: taps on an older message of a re-sent clip redraw only that message; full Dict scans per tap (S1 moves the queue to Postgres).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At each posting slot, the owner's phone gets the next clip plus copyable captions for TikTok, Instagram and YouTube. Buttons record ✅ per platform (tap again to undo), ⏭ Skip (sends the next clip; the skipped one returns after 24 h) and 🗑 Reject (with an optional reason). `/status`, `/next`, `/pause` and `/go` run the queue from the phone. After 2 unanswered clips the slots pause, with one reminder.

**Architecture:** `TelegramSender` gains buttons, HTML, returned message ids, `edit_buttons`, `answer_callback` and `delete_message`. `posting/captions.py` builds the platform texts. The new module `bot/posting.py` builds the message and keyboard, parses callback data, and holds `tick` (called by a new Modal cron, `posting_tick`), `send_next` and `handle_callback`. `bot/webhook.py` routes `callback_query` updates and the new commands. `BotContext` moves to `bot/context.py` to avoid an import cycle, and `webhook.py` re-exports it.

**Tech Stack:** python-telegram-bot 22 (`InlineKeyboardMarkup`, `ParseMode.HTML`), Modal Cron, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-posting-assistant-design.md` §6, §7, §8, §10, §11 (ADR-23). **Runs after Plans A and B.**

**Git:** the owner runs every git command. "Checkpoint" steps list the changed files; don't run git.

**The code moves.** Another session edits this repo at the same time. Read each file before changing it, keep unrelated current code, and report what you adapted.

## Global Constraints

- `bot/posting.py`, `bot/context.py` and `posting/captions.py` never import `modal`. Only `app.py` does, and `posting_tick` there only builds deps and calls `tick`.
- A clip counts as sent only after both the video and the text with its buttons are accepted. If either fails, delete what was delivered, release the slot claim and let the next tick retry (spec §6, §10).
- The pause rule is 2 or more `sent` clips with no taps: send nothing and one reminder per pause episode (claim keyed on the oldest unanswered send's `at`). `/next` ignores the pause rule.
- Callback data is `p:<action>:<job_id>:<clip_id>` or `p:why:<reason>:<job_id>:<clip_id>`, at most 64 bytes. `job_id` must pass `jobs.is_job_id` and `clip_id` must match `clip_\d{2}`. Anything else gets an empty answer and changes nothing.
- Taps are accepted only from `TELEGRAM_ALLOWED_USER_IDS` and only on messages in `POSTING_CHAT_ID`. They reuse `claim_update` dedupe.
- Text limits: TikTok and Instagram ≤ 2,200; YouTube title ≤ 100 including ` #shorts`, with `<` and `>` removed; YouTube description ≤ 5,000. In the Telegram message each block is capped at 950 characters, so the whole message stays under Telegram's 4,096. HTML is escaped with `html.escape`.
- `set_webhook` registers `allowed_updates=["message", "callback_query"]`. The owner re-runs `uv run clipforge set-webhook` once after deploying.
- Before every checkpoint: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.

## Review Focus

1. **Telegram accepts the video but rejects the text.** The video is deleted, nothing is marked sent, and the slot is retried. Test: `test_half_delivered_send_is_rolled_back` (Task 3).
2. **Duplicate or overlapping ticks** (Modal running two, or a retry). Exactly one send per slot. Test: `test_one_send_per_slot` (Task 3).
3. **Taps on an old message** after a clip was skipped and re-sent, a double-tap, or a stale message for a clip that's gone. No crash, no double state. Tests: `test_tap_on_unknown_clip_answers_gone`, `test_duplicate_update_is_handled_once` (Task 4).
4. **Tapping the wrong platform.** Tapping it again undoes it, and the buttons show the truth. Test: `test_toggle_and_undo_update_the_buttons` (Task 4).
5. **The owner doesn't answer for a day.** After 2 unanswered clips, no more clips and exactly one reminder until a tap. Test: `test_pause_rule_reminds_once_and_resumes_after_a_tap` (Task 3).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/clipforge/bot/telegram.py` | `Button`, `Keyboard`; buttons, HTML, message ids, edit, answer, delete; webhook update types (Task 1) |
| `tests/bot/fakes.py` | `FakeSender` returns ids and records keyboards, answers and deletes; `callback()` update builder (Task 1) |
| `src/clipforge/posting/captions.py` | Platform texts (Task 2) |
| `src/clipforge/bot/posting.py` | `parse_callback`, `keyboard`, `fresh_keyboard`, `post_html`, `video_caption` (Task 2); `tick`, `send_next` (Task 3); `handle_callback` (Task 4) |
| `src/clipforge/bot/context.py`, `src/clipforge/bot/webhook.py` | `BotContext` moved; `callback_query` routing and new commands (Task 4) |
| `src/clipforge/bot/commands.py`, `src/clipforge/bot/messages.py` | `PostingCommand`; posting texts and `USAGE` (Task 4) |
| `src/clipforge/app.py` | `posting_tick` cron (Task 5) |
| `tests/bot/test_telegram.py`, `tests/posting/test_captions.py`, `tests/bot/test_posting.py`, `tests/bot/test_webhook.py`, `tests/bot/test_commands.py`, `tests/test_app.py` | Tests |
| `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md` | Docs (Task 5) |

---

### Task 1: Telegram client: buttons, HTML, ids, edit, answer, delete

**Files:**
- Modify: `src/clipforge/bot/telegram.py`, `tests/bot/fakes.py`
- Test: `tests/bot/test_telegram.py`

**Interfaces:**
- Produces:
  - `telegram.Button = tuple[str, str]` (label, callback data) and `telegram.Keyboard = list[list[Button]]`
  - `TelegramSender.send_message(chat_id, text, reply_to=None, *, buttons: Keyboard | None = None, html: bool = False) -> int`
  - `.send_video(chat_id, path, caption, reply_to=None) -> int`
  - `.edit_buttons(chat_id: int, message_id: int, buttons: Keyboard | None) -> None`
  - `.answer_callback(callback_id: str, text: str = "") -> None`
  - `.delete_message(chat_id: int, message_id: int) -> None`
  - `tests.bot.fakes.callback(update_id, data, *, message_id=500, chat_id=ALLOWED_USER, user_id=ALLOWED_USER) -> dict`
  - `FakeSender` fields: `keyboards: dict[int, Keyboard | None]`, `answers: list[tuple[str, str]]`, `deleted: list[tuple[int, int]]`, `fail_on: set[str]`

- [ ] **Step 1: Write the failing tests** (append to `tests/bot/test_telegram.py`; change the `set_webhook` test's expected `allowed_updates` to `["message", "callback_query"]`)

```python
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
```

Add `import json` to the test file.

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/bot/test_telegram.py -q`
Expected: FAIL (unexpected keyword `buttons`; no `edit_buttons`).

- [ ] **Step 3: Implement** `telegram.py`

Imports: `from typing import Any, Protocol`, `from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, ReplyParameters`, `from telegram.constants import ParseMode`.

```python
Button = tuple[str, str]  # (label, callback data)
Keyboard = list[list[Button]]
UPDATE_TYPES = ["message", "callback_query"]


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


def _markup(buttons: Keyboard | None) -> InlineKeyboardMarkup | None:
    if buttons is None:
        return None
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in buttons
        ]
    )
```

In `TelegramClient`, make `_run` generic and return the call's result:

```python
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
```

`tests/bot/fakes.py`: replace `FakeSender` (keep the `messages` and `videos` tuple shapes that existing tests read):

```python
from clipforge.bot.telegram import Keyboard


@dataclass
class FakeSender:
    messages: list[tuple[int, str, int | None]] = field(default_factory=list)
    videos: list[tuple[int, Path, str, int | None]] = field(default_factory=list)
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
        self, chat_id: int, path: Path, caption: str, reply_to: int | None = None
    ) -> int:
        self._check("send_video")
        self.videos.append((chat_id, path, caption, reply_to))
        return self._id()

    def edit_buttons(self, chat_id: int, message_id: int, buttons: Keyboard | None) -> None:
        self._check("edit_buttons")
        self.keyboards[message_id] = buttons

    def answer_callback(self, callback_id: str, text: str = "") -> None:
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
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/bot tests/test_runtime.py tests/api -q`
Expected: PASS. Other code that implements `TelegramSender` must match the new signatures; `grep -rn "def send_message" src tests` to find any.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/bot/telegram.py`, `tests/bot/fakes.py`, `tests/bot/test_telegram.py`.

---

### Task 2: Captions, message, keyboard, callback data

**Files:**
- Create: `src/clipforge/posting/captions.py`, `src/clipforge/bot/posting.py`
- Test: `tests/posting/test_captions.py`, `tests/bot/test_posting.py`

**Interfaces:**
- Consumes: `PostItem`, `PostRecord`, `queue.status`, `Keyboard`, `is_job_id`; builders `item`, `record`, `send`.
- Produces:
  - `captions.tiktok(item, hashtags) -> str`, `.instagram(...)`, `.youtube_title(item)`, `.youtube_description(item, hashtags)`
  - `bot.posting.Callback(action: str, ref: str, reason: RejectReason | None)`
  - `bot.posting.parse_callback(data: str | None) -> Callback | None`
  - `bot.posting.fresh_keyboard(ref: str) -> Keyboard`, `bot.posting.keyboard(record) -> Keyboard`
  - `bot.posting.post_html(item, hashtags) -> str`, `bot.posting.video_caption(item, waiting: int) -> str`
  - `PLATFORM_ACTIONS: dict[str, Platform]`, `LABELS: dict[Platform, str]`

- [ ] **Step 1: Write the failing tests**

`tests/posting/test_captions.py`:

```python
"""Per-platform caption text (a template until the Phase 3 post.md copy)."""

from __future__ import annotations

from clipforge.posting.captions import instagram, tiktok, youtube_description, youtube_title
from tests.posting.builders import item

TAGS = ["growth", "mindset", "men", "podcast", "honesty", "clips"]


def test_tiktok_has_hook_credit_and_tags() -> None:
    assert tiktok(item(hook="I changed."), TAGS) == (
        "I changed.\n\n🎙️ Billy Garton Jr.\n\n#growth #mindset #men #podcast #honesty #clips"
    )


def test_instagram_title_first_and_at_most_five_tags() -> None:
    text = instagram(item(title="Be honest", hook="Hook."), TAGS)
    assert text.startswith("Be honest\n\nHook.\n\n🎙️ Billy Garton Jr.")
    assert text.endswith("#growth #mindset #men #podcast #honesty")


def test_youtube_title_limits() -> None:
    assert youtube_title(item(title="Real <men> talk")) == "Real men talk #shorts"
    long = youtube_title(item(title="word " * 40))
    assert len(long) == 100 and long.endswith("… #shorts")


def test_long_text_is_cut_to_the_platform_limit() -> None:
    assert len(tiktok(item(hook="x" * 3000), TAGS)) == 2200
    assert len(instagram(item(hook="x" * 3000), TAGS)) == 2200
    assert len(youtube_description(item(hook="x" * 6000), TAGS)) == 5000
```

`tests/bot/test_posting.py`:

```python
"""The posting assistant: message, keyboard, callbacks, tick."""

from __future__ import annotations

from clipforge.bot.posting import (
    fresh_keyboard,
    keyboard,
    parse_callback,
    post_html,
    video_caption,
)
from clipforge.models import Platform, PostVerdict, RejectReason
from tests.posting.builders import JOB, T0, item, record, send

REF = f"{JOB}:clip_01"


def test_parse_callback() -> None:
    assert parse_callback(f"p:tt:{REF}") is not None
    why = parse_callback(f"p:why:bad_crop:{REF}")
    assert why is not None and why.reason is RejectReason.BAD_CROP and why.ref == REF
    for bad in [None, "", "x:tt:" + REF, f"p:zz:{REF}", "p:tt:not-a-job:clip_01",
                f"p:tt:{JOB}:clip_1", f"p:why:nope:{REF}", f"p:tt:{REF}:extra"]:  # fmt: skip
        assert parse_callback(bad) is None, bad
    assert max(len(f"p:why:{r}:{REF}".encode()) for r in RejectReason) <= 64


def test_fresh_keyboard() -> None:
    assert fresh_keyboard(REF) == [
        [("✅ TikTok", f"p:tt:{REF}"), ("✅ Instagram", f"p:ig:{REF}"),
         ("✅ YouTube", f"p:yt:{REF}")],
        [("⏭ Skip", f"p:skip:{REF}"), ("🗑 Reject", f"p:rej:{REF}")],
    ]  # fmt: skip


def test_keyboard_follows_the_state() -> None:
    it = item()
    partly = keyboard(record(it, sends=[send()], posted=[Platform.TIKTOK]))
    assert partly[0][0] == ("TikTok ✓", f"p:tt:{REF}")
    assert keyboard(record(it, posted=list(Platform))) == [
        [("Posted everywhere ✓", f"p:noop:{REF}")]
    ]
    rejected = record(it, verdict=PostVerdict(kind="rejected", at=T0))
    reasons = [data for row in keyboard(rejected) for _, data in row]
    assert reasons[0] == f"p:why:boring:{REF}" and len(reasons) == 5
    with_reason = record(it, verdict=PostVerdict(kind="rejected", at=T0,
                                                 reason=RejectReason.CAPTIONS))  # fmt: skip
    assert keyboard(with_reason) == [[("Rejected · Captions", f"p:noop:{REF}")]]
    skipped = record(it, sends=[send()], verdict=PostVerdict(kind="skipped", at=T0))
    assert keyboard(skipped) == [[("Skipped ⏭", f"p:noop:{REF}")]]


def test_post_html_escapes_and_has_every_block() -> None:
    text = post_html(item(title="<Be> honest & real", hook="a < b"), ["mindset"])
    assert "&lt;Be&gt; honest &amp; real" in text
    for name in ("TikTok", "Instagram", "YouTube title", "YouTube description"):
        assert f"<b>{name}</b>\n<pre>" in text
    assert len(post_html(item(hook="x" * 5000), ["mindset"])) < 4096


def test_video_caption() -> None:
    assert video_caption(item(score=0.891), 214) == "Billy Garton Jr. · ep01 · 0.89 · 214 queued"
```

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/posting/test_captions.py tests/bot/test_posting.py -q`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

`src/clipforge/posting/captions.py`:

```python
"""Per-platform post text from a clip's title, hook and creator credit.

A template on purpose: LLM-written copy is the Phase 3 `post.md` item and can replace these."""

from __future__ import annotations

from clipforge.models import PostItem

TIKTOK_MAX = 2200
INSTAGRAM_MAX = 2200
INSTAGRAM_MAX_HASHTAGS = 5
YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESCRIPTION_MAX = 5000
SHORTS_TAG = " #shorts"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def _credit(item: PostItem) -> str:
    return f"🎙️ {item.channel.name}"


def _tags(hashtags: list[str], limit: int | None = None) -> str:
    return " ".join(f"#{tag}" for tag in hashtags[:limit])


def tiktok(item: PostItem, hashtags: list[str]) -> str:
    return _cut(_join(item.hook, _credit(item), _tags(hashtags)), TIKTOK_MAX)


def instagram(item: PostItem, hashtags: list[str]) -> str:
    text = _join(item.title, item.hook, _credit(item), _tags(hashtags, INSTAGRAM_MAX_HASHTAGS))
    return _cut(text, INSTAGRAM_MAX)


def youtube_title(item: PostItem) -> str:
    """YouTube rejects `<` and `>` in titles."""
    title = " ".join(item.title.replace("<", "").replace(">", "").split())
    return _cut(title, YOUTUBE_TITLE_MAX - len(SHORTS_TAG)) + SHORTS_TAG


def youtube_description(item: PostItem, hashtags: list[str]) -> str:
    return _cut(_join(item.hook, _credit(item), _tags(hashtags)), YOUTUBE_DESCRIPTION_MAX)
```

`src/clipforge/bot/posting.py` (Task 2 part; Tasks 3–4 add to it):

```python
"""The posting assistant (ADR-23): at each slot, send the next clip to the owner's phone with
copyable captions and buttons, and handle the taps. Modal-free: `app.posting_tick` calls
`tick`, the webhook calls `handle_callback` and `send_next`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape

from clipforge.bot.telegram import Keyboard
from clipforge.jobs import is_job_id
from clipforge.models import Platform, PostItem, PostRecord, PostStatus, RejectReason
from clipforge.posting import captions
from clipforge.posting.queue import status

PLATFORM_ACTIONS = {"tt": Platform.TIKTOK, "ig": Platform.INSTAGRAM, "yt": Platform.YOUTUBE}
LABELS = {Platform.TIKTOK: "TikTok", Platform.INSTAGRAM: "Instagram", Platform.YOUTUBE: "YouTube"}
REASON_LABELS = {
    RejectReason.BORING: "Boring",
    RejectReason.BAD_CUT: "Bad cut",
    RejectReason.BAD_CROP: "Bad crop",
    RejectReason.CAPTIONS: "Captions",
    RejectReason.OTHER: "Other",
}
ACTIONS = frozenset({*PLATFORM_ACTIONS, "skip", "rej", "noop"})
BLOCK_LIMIT = 950  # 4 blocks + header stay under Telegram's 4096-character message limit
_CLIP_ID = re.compile(r"clip_\d{2}")


@dataclass(frozen=True)
class Callback:
    action: str  # tt | ig | yt | skip | rej | why | noop
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


def _platform_row(ref: str, posted: set[Platform]) -> list[tuple[str, str]]:
    return [
        (f"{LABELS[p]} ✓" if p in posted else f"✅ {LABELS[p]}", f"p:{action}:{ref}")
        for action, p in PLATFORM_ACTIONS.items()
    ]


def fresh_keyboard(ref: str) -> Keyboard:
    return [_platform_row(ref, set()), [("⏭ Skip", f"p:skip:{ref}"), ("🗑 Reject", f"p:rej:{ref}")]]


def keyboard(record: PostRecord) -> Keyboard:
    """The buttons that match the clip's current state (spec §7)."""
    ref = record.item.ref
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
        _platform_row(ref, set(record.posted)),
        [("⏭ Skip", f"p:skip:{ref}"), ("🗑 Reject", f"p:rej:{ref}")],
    ]


def _block(name: str, text: str) -> str:
    if len(text) > BLOCK_LIMIT:
        text = text[: BLOCK_LIMIT - 1] + "…"
    return f"<b>{name}</b>\n<pre>{escape(text)}</pre>"


def post_html(item: PostItem, hashtags: list[str]) -> str:
    """The text under the video: one tap-to-copy block per platform (HTML parse mode)."""
    head = f"🎙️ <b>{escape(item.channel.name)}</b> — “{escape(item.title)}”"
    blocks = [
        _block("TikTok", captions.tiktok(item, hashtags)),
        _block("Instagram", captions.instagram(item, hashtags)),
        _block("YouTube title", captions.youtube_title(item)),
        _block("YouTube description", captions.youtube_description(item, hashtags)),
    ]
    return "\n\n".join([head, *blocks])


def video_caption(item: PostItem, waiting: int) -> str:
    return f"{item.channel.name} · {item.episode} · {item.score:.2f} · {waiting} queued"
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/posting/test_captions.py tests/bot/test_posting.py -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/posting/captions.py`, `src/clipforge/bot/posting.py`, `tests/posting/test_captions.py`, `tests/bot/test_posting.py`.

---

### Task 3: Sending, the slot tick, `/next`

**Files:**
- Create: `src/clipforge/bot/context.py`
- Modify: `src/clipforge/bot/webhook.py` (import `BotContext` from `context`, re-exported), `src/clipforge/bot/posting.py`, `src/clipforge/bot/messages.py`
- Test: `tests/bot/test_posting.py`

**Interfaces:**
- Consumes: `PostingStore`, `queue.pick_next/eligible/unanswered/PAUSE_AFTER`, `slots.current_slot`, the Task 2 builders, `FakeSender`, `run_channel_job`.
- Produces:
  - `bot.context.BotContext(settings, sender, deps)`, which is the same dataclass as before, moved
  - `bot.posting.SendFailed`
  - `bot.posting.tick(ctx: BotContext, now: datetime) -> str`, with outcomes `off | paused | no slot | waiting | taken | empty | send failed | sent <ref>`
  - `bot.posting.send_next(ctx, now) -> str`, which returns reply text and `""` when a clip was sent
  - `messages.WAITING_REMINDER(n) -> str`, `messages.POSTING_OFF`, `messages.QUEUE_EMPTY`, `messages.SEND_FAILED`

- [ ] **Step 1: Write the failing tests** (append to `tests/bot/test_posting.py`; merge the imports)

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from clipforge.bot.context import BotContext
from clipforge.bot.posting import send_next, tick
from clipforge.posting.store import PostingStore
from tests.bot.fakes import ALLOWED_USER, FakeSender, make_settings
from tests.pipeline.harness import Harness
from tests.posting.builders import run_channel_job

NY = ZoneInfo("America/New_York")
SLOTS = ["08:00", "12:00", "16:00", "20:00"]
DAY = datetime(2026, 9, 29, tzinfo=NY)


def at(hour: int, minute: int = 1, days: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute) + timedelta(days=days)


@pytest.fixture
def ctx(harness: Harness) -> BotContext:
    run_channel_job(harness)  # 3 queued clips with real files
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER, posting_slots=SLOTS)
    return BotContext(settings, FakeSender(), harness.deps)


def _sender(ctx: BotContext) -> FakeSender:
    assert isinstance(ctx.sender, FakeSender)
    return ctx.sender


def _store(ctx: BotContext) -> PostingStore:
    return PostingStore(ctx.deps.store.kv)


def test_one_send_per_slot(ctx: BotContext) -> None:
    outcome = tick(ctx, at(8))
    assert outcome.startswith("sent ")
    assert tick(ctx, at(8, 6)) == "taken"  # a second tick in the same slot
    sender = _sender(ctx)
    assert len(sender.videos) == 1 and len(sender.messages) == 1
    [(_, text, reply_to)] = sender.messages
    assert "<b>TikTok</b>" in text and reply_to == 101  # the text replies to the video
    assert sender.keyboards[102] is not None
    sent = [r for r in _store(ctx).records() if r.sends]
    assert len(sent) == 1 and sent[0].sends[0].message_id == 102


def test_missed_slot_is_dropped_and_off_and_paused(ctx: BotContext) -> None:
    assert tick(ctx, at(8, 31)) == "no slot"
    _store(ctx).set_paused(True)
    assert tick(ctx, at(12)) == "paused"
    off = BotContext(make_settings(ctx.deps.root), ctx.sender, ctx.deps)
    assert tick(off, at(12)) == "off"
    assert _sender(ctx).videos == []


def test_half_delivered_send_is_rolled_back(ctx: BotContext) -> None:
    sender = _sender(ctx)
    sender.fail_on = {"send_message"}
    assert tick(ctx, at(8)) == "send failed"
    assert sender.deleted == [(ALLOWED_USER, 101)]  # the video that did go out
    assert not any(r.sends for r in _store(ctx).records())
    sender.fail_on = set()
    assert tick(ctx, at(8, 6)).startswith("sent ")  # the slot was released: retried


def test_pause_rule_reminds_once_and_resumes_after_a_tap(ctx: BotContext) -> None:
    from clipforge.models import Platform

    assert tick(ctx, at(8)).startswith("sent ")
    assert tick(ctx, at(12)).startswith("sent ")
    assert tick(ctx, at(16)) == "waiting"
    assert tick(ctx, at(16, 6)) == "waiting"
    sender = _sender(ctx)
    reminders = [text for _, text, _ in sender.messages if "waiting" in text]
    assert len(reminders) == 1
    first = next(r for r in _store(ctx).records() if r.sends)
    _store(ctx).toggle_posted(first.item.ref, Platform.TIKTOK, at(17))
    assert tick(ctx, at(20)).startswith("sent ")


def test_unavailable_video_is_skipped(ctx: BotContext) -> None:
    records = _store(ctx).records()
    best = max(records, key=lambda r: r.item.score)
    (ctx.deps.root / best.item.video_path).unlink()
    outcome = tick(ctx, at(8))
    assert outcome.startswith("sent ") and best.item.ref not in outcome
    assert _store(ctx).get(best.item.ref).unavailable  # type: ignore[union-attr]


def test_send_next_ignores_slots_and_reports_empty(ctx: BotContext) -> None:
    for _ in range(3):
        assert send_next(ctx, at(9)) == ""
    assert "empty" in send_next(ctx, at(9))
    assert len(_sender(ctx).videos) == 3
```

The harness's cached fake clips can share one `clip.mp4` when two clips cover the same range. If `test_unavailable_video_is_skipped` then finds the file already gone for another clip, pick the clip whose `video_path` is unique. If the harness's 3 clips have equal scores, `max` still picks one deterministically, and the assertion only needs *a different* clip to be sent.

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/bot/test_posting.py -q`
Expected: FAIL (`No module named 'clipforge.bot.context'`).

- [ ] **Step 3: Implement**

`src/clipforge/bot/context.py`:

```python
"""What the bot's handlers need (moved out of webhook.py so bot/posting.py can use it)."""

from __future__ import annotations

from dataclasses import dataclass

from clipforge.bot.telegram import TelegramSender
from clipforge.config import Settings
from clipforge.pipeline.steps import Deps


@dataclass
class BotContext:
    settings: Settings
    sender: TelegramSender
    deps: Deps  # the store, the Volume root, the spawner
```

In `webhook.py`, delete the `BotContext` class and add `from clipforge.bot.context import BotContext` (existing imports such as `from clipforge.bot.webhook import BotContext` keep working). Add `__all__ = ["BotContext", "handle_update"]` if ruff flags the re-export.

`messages.py`, add:

```python
POSTING_OFF = "Posting is off (set POSTING_CHAT_ID)."
QUEUE_EMPTY = "The queue is empty. Add videos to videos/<channel>/ and run `clipforge clip`."
SEND_FAILED = "Couldn't send the next clip. Try /next again in a minute."
PAUSED = "Paused. No clips until you send /go."
RESUMED = "Back on. Clips resume at the next slot."
GONE = "That clip isn't in the queue any more."


def waiting_reminder(count: int) -> str:
    return f"{count} clips are waiting: post them or tap Skip, then the next ones come."
```

`bot/posting.py`, add these imports: `contextlib`, `logging`, `from datetime import datetime`, `from clipforge.bot import messages`, `from clipforge.bot.context import BotContext`, `from clipforge.models import PostSend`, `from clipforge.posting.queue import PAUSE_AFTER, eligible, pick_next, unanswered`, `from clipforge.posting.slots import current_slot`, `from clipforge.posting.store import PostingStore`. Then add:

```python
log = logging.getLogger(__name__)
MAX_PICKS = 3  # clips tried per send when videos turn out to be missing


class SendFailed(Exception):
    """Telegram refused part of a send; nothing was recorded (spec §6)."""


def _deliver(
    ctx: BotContext, store: PostingStore, record: PostRecord, slot: datetime | None,
    now: datetime, waiting: int,
) -> bool:  # fmt: skip
    """Send one clip: the video, then the text with buttons replying to it. False if its video
    is missing (marked unavailable). Raises SendFailed after rolling back a partial send."""
    item = record.item
    chat = ctx.settings.posting_chat_id
    assert chat is not None
    path = ctx.deps.root / item.video_path
    if not path.is_file():
        log.warning("posting: video missing for %s", item.ref)
        store.mark_unavailable(item.ref)
        return False
    video_id: int | None = None
    try:
        video_id = ctx.sender.send_video(chat, path, video_caption(item, waiting))
        text_id = ctx.sender.send_message(
            chat,
            post_html(item, ctx.settings.posting_hashtags),
            video_id,
            buttons=fresh_keyboard(item.ref),
            html=True,
        )
    except Exception as exc:
        log.exception("posting: sending %s failed", item.ref)
        if video_id is not None:
            with contextlib.suppress(Exception):
                ctx.sender.delete_message(chat, video_id)
        raise SendFailed(item.ref) from exc
    store.add_send(
        item.ref,
        PostSend(n=len(record.sends) + 1, at=now, slot=slot, message_id=text_id,
                 video_message_id=video_id),
    )  # fmt: skip
    return True


def _send_best(
    ctx: BotContext, store: PostingStore, records: list[PostRecord], slot: datetime | None,
    now: datetime,
) -> str | None:  # fmt: skip
    """Send the best eligible clip; returns its ref, or None when nothing is eligible."""
    for _ in range(MAX_PICKS):
        record = pick_next(records, now)
        if record is None:
            return None
        waiting = sum(eligible(r, now) for r in records) - 1
        if _deliver(ctx, store, record, slot, now, waiting):
            return record.item.ref
        records = [
            r.model_copy(update={"unavailable": True}) if r.item.ref == record.item.ref else r
            for r in records
        ]
    return None


def tick(ctx: BotContext, now: datetime) -> str:
    """One cron tick (spec §6). Returns what happened, for the log."""
    chat = ctx.settings.posting_chat_id
    if chat is None:
        return "off"
    store = PostingStore(ctx.deps.store.kv)
    if store.paused():
        return "paused"
    slot = current_slot(ctx.settings, now)
    if slot is None:
        return "no slot"
    records = store.records()
    waiting = unanswered(records)
    if len(waiting) >= PAUSE_AFTER:
        oldest = min(r.sends[-1].at for r in waiting)
        if store.claim_reminder(oldest):
            ctx.sender.send_message(chat, messages.waiting_reminder(len(waiting)))
        return "waiting"
    if not store.claim_slot(slot):
        return "taken"
    try:
        ref = _send_best(ctx, store, records, slot, now)
    except SendFailed:
        store.release_slot(slot)
        return "send failed"
    return f"sent {ref}" if ref else "empty"


def send_next(ctx: BotContext, now: datetime) -> str:
    """`/next` and after ⏭ Skip: send the best clip now (no slot, no pause rule)."""
    if ctx.settings.posting_chat_id is None:
        return messages.POSTING_OFF
    store = PostingStore(ctx.deps.store.kv)
    try:
        ref = _send_best(ctx, store, store.records(), None, now)
    except SendFailed:
        return messages.SEND_FAILED
    return "" if ref else messages.QUEUE_EMPTY
```

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/bot -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/bot/context.py`, `src/clipforge/bot/webhook.py`, `src/clipforge/bot/posting.py`, `src/clipforge/bot/messages.py`, `tests/bot/test_posting.py`.

---

### Task 4: Button taps and the new commands

**Files:**
- Modify: `src/clipforge/bot/posting.py` (`handle_callback`), `src/clipforge/bot/webhook.py`, `src/clipforge/bot/commands.py`, `src/clipforge/bot/messages.py` (`USAGE`)
- Test: `tests/bot/test_webhook.py`, `tests/bot/test_commands.py`

**Interfaces:**
- Consumes: everything above; `service.posting_overview`, `messages.posting_overview_text` (Plan B).
- Produces: `bot.posting.handle_callback(ctx, callback_id: str, data: str | None, chat_id: int | None, message_id: int | None, now: datetime) -> None`; `commands.PostingCommand(name: Literal["overview", "next", "pause", "go"])`.

- [ ] **Step 1: Write the failing tests**

`tests/bot/test_commands.py`, append. If a test there asserts that a bare `/status` is a usage error, change it: a bare `/status` is now the overview.

```python
from clipforge.bot.commands import JobCommand, PostingCommand, parse_text


def test_posting_commands() -> None:
    assert parse_text("/status") == PostingCommand("overview")
    assert parse_text("/status 20260928-aaaaaaaa-0001") == JobCommand(
        "status", "20260928-aaaaaaaa-0001"
    )
    assert parse_text("/next") == PostingCommand("next")
    assert parse_text("/pause") == PostingCommand("pause")
    assert parse_text("/go@ClipForgeBot") == PostingCommand("go")
```

`tests/bot/test_webhook.py`, append:

```python
from datetime import timedelta

from clipforge.bot.posting import fresh_keyboard, tick
from clipforge.jobs import utcnow
from clipforge.models import Platform, PostStatus, RejectReason
from clipforge.posting.queue import status
from clipforge.posting.store import PostingStore
from tests.bot.fakes import ALLOWED_USER, callback
from tests.posting.builders import run_channel_job


@pytest.fixture
def posting(harness: Harness) -> Bot:
    run_channel_job(harness)
    sender = FakeSender()
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER)
    return BotContext(settings, sender, harness.deps), sender


def _sent(ctx: BotContext) -> tuple[str, int]:
    """Send one clip with /next; return its ref and its text message id."""
    handle_update(update(90, text="/next", user_id=ALLOWED_USER), ctx)
    store = PostingStore(ctx.deps.store.kv)
    record = next(r for r in store.records() if r.sends)
    return record.item.ref, record.sends[-1].message_id


def test_toggle_and_undo_update_the_buttons(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id), ctx)
    assert sender.answers[-1] == ("cb1", "TikTok ✓")
    assert sender.keyboards[message_id][0][0] == ("TikTok ✓", f"p:tt:{ref}")  # type: ignore[index]
    handle_update(callback(2, f"p:tt:{ref}", message_id=message_id), ctx)
    assert sender.answers[-1] == ("cb2", "TikTok undone")
    assert sender.keyboards[message_id] == fresh_keyboard(ref)
    for n, action in enumerate(["tt", "ig", "yt"], start=3):
        handle_update(callback(n, f"p:{action}:{ref}", message_id=message_id), ctx)
    record = PostingStore(ctx.deps.store.kv).get(ref)
    assert record is not None and status(record) is PostStatus.POSTED
    assert sender.keyboards[message_id] == [[("Posted everywhere ✓", f"p:noop:{ref}")]]


def test_skip_sends_the_next_clip(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:skip:{ref}", message_id=message_id), ctx)
    assert len(sender.videos) == 2  # the next one went out right away
    record = PostingStore(ctx.deps.store.kv).get(ref)
    assert record is not None and status(record) is PostStatus.SKIPPED


def test_reject_then_reason(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:rej:{ref}", message_id=message_id), ctx)
    handle_update(callback(2, f"p:why:bad_crop:{ref}", message_id=message_id), ctx)
    record = PostingStore(ctx.deps.store.kv).get(ref)
    assert record is not None and record.verdict is not None
    assert record.verdict.reason is RejectReason.BAD_CROP
    assert sender.keyboards[message_id] == [[("Rejected · Bad crop", f"p:noop:{ref}")]]


def test_tap_on_unknown_clip_answers_gone(posting: Bot) -> None:
    ctx, sender = posting
    handle_update(callback(1, "p:tt:20260101-bbbbbbbb-0001:clip_01"), ctx)
    assert sender.answers == [("cb1", messages.GONE)]


def test_taps_outside_the_posting_chat_or_from_strangers_do_nothing(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id, chat_id=CHAT), ctx)
    handle_update(callback(2, f"p:tt:{ref}", message_id=message_id, user_id=999), ctx)
    record = PostingStore(ctx.deps.store.kv).get(ref)
    assert record is not None and record.posted == {}
    assert sender.answers == [("cb1", "")]  # the stranger gets nothing at all


def test_duplicate_tap_is_handled_once(posting: Bot) -> None:
    ctx, _ = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id), ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id), ctx)  # redelivered
    record = PostingStore(ctx.deps.store.kv).get(ref)
    assert record is not None and set(record.posted) == {Platform.TIKTOK}


def test_status_pause_go_commands(posting: Bot) -> None:
    ctx, sender = posting
    handle_update(update(1, text="/status", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1].startswith("Billy Garton Jr. — 1 episodes")
    handle_update(update(2, text="/pause", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.PAUSED
    assert tick(ctx, utcnow() + timedelta(minutes=1)) == "paused"
    handle_update(update(3, text="/go", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.RESUMED
    assert not PostingStore(ctx.deps.store.kv).paused()
```

(`CHAT` is the fakes' non-posting chat id, 7, and is already imported in this file. `update(...)` builds messages in chat `CHAT`. The commands work from any chat of an allowed user, but clips always go to `POSTING_CHAT_ID`.)

- [ ] **Step 2: Run the tests and check they fail**

Run: `uv run pytest tests/bot -q`
Expected: FAIL (`PostingCommand` missing; callback updates ignored).

- [ ] **Step 3: Implement**

`commands.py`:

```python
@dataclass(frozen=True)
class PostingCommand:
    name: Literal["overview", "next", "pause", "go"]


Command = ClipCommand | JobCommand | PostingCommand | HelpCommand
```

In `parse_text`, replace the `/status` / `/resume` branch:

```python
        if name == "/status":
            if len(tokens) == 1:
                return PostingCommand("overview")
            if len(tokens) == 2:
                return JobCommand("status", tokens[1])
            raise CommandError("Usage: /status [<job_id>]")
        if name == "/resume":
            if len(tokens) != 2:
                raise CommandError("Usage: /resume <job_id>")
            return JobCommand("resume", tokens[1])
        if name == "/next":
            return PostingCommand("next")
        if name == "/pause":
            return PostingCommand("pause")
        if name == "/go":
            return PostingCommand("go")
```

`messages.USAGE`: change the last line to `"/status [<job_id>] · /resume <job_id> · /next · /pause · /go"`.

`bot/posting.py`, add:

```python
def handle_callback(
    ctx: BotContext, callback_id: str, data: str | None, chat_id: int | None,
    message_id: int | None, now: datetime,
) -> None:  # fmt: skip
    """One button tap (spec §8). Always answers the tap; edits the buttons to the new state."""
    chat = ctx.settings.posting_chat_id
    parsed = parse_callback(data)
    if chat is None or parsed is None or chat_id != chat or message_id is None:
        ctx.sender.answer_callback(callback_id, "")
        return
    store = PostingStore(ctx.deps.store.kv)
    if store.get(parsed.ref) is None:
        ctx.sender.answer_callback(callback_id, messages.GONE)
        return
    note, then_next = "", False
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
    ctx.sender.answer_callback(callback_id, note)
    if parsed.action != "noop":
        updated = store.get(parsed.ref)
        if updated is not None:
            try:
                ctx.sender.edit_buttons(chat, message_id, keyboard(updated))
            except Exception:
                log.warning("posting: editing the buttons of %s failed", parsed.ref, exc_info=True)
    if then_next:
        reply = send_next(ctx, now)
        if reply:
            ctx.sender.send_message(chat, reply)
```

(Import `PostVerdict` from `clipforge.models`.)

`webhook.py`, in `handle_update`, before the message path:

```python
    update = Update.de_json(body, None)
    query = update.callback_query
    if query is not None:
        if query.from_user.id not in ctx.settings.telegram_allowed_user_ids:
            log.info("ignoring a tap %s from a user not in the allow list", update.update_id)
            return
        if not ctx.deps.store.claim_update(update.update_id):
            return
        message = query.message
        handle_callback(
            ctx, query.id, query.data,
            message.chat.id if message else None, message.message_id if message else None,
            utcnow(),
        )  # fmt: skip
        return
```

In `_reply_for`, add these cases (import `PostingCommand`, `send_next`, `posting_overview`, `posting_overview_text`, `PostingStore`, `utcnow`):

```python
        case PostingCommand(name="overview"):
            view = posting_overview(ctx.deps, ctx.settings, utcnow())
            return posting_overview_text(view, ctx.settings.posting_timezone)
        case PostingCommand(name="next"):
            return send_next(ctx, utcnow())
        case PostingCommand(name="pause"):
            PostingStore(ctx.deps.store.kv).set_paused(True)
            return messages.PAUSED
        case PostingCommand(name="go"):
            PostingStore(ctx.deps.store.kv).set_paused(False)
            return messages.RESUMED
```

`handle_update` must not send an empty reply (`/next` returns `""` after sending a clip): change the last line to

```python
    if reply:
        ctx.sender.send_message(target.chat_id, reply, target.reply_to_message_id)
```

Import `messages` as a module in `webhook.py` if it currently imports only names from it.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/bot tests/api -q`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Files: `src/clipforge/bot/posting.py`, `src/clipforge/bot/webhook.py`, `src/clipforge/bot/commands.py`, `src/clipforge/bot/messages.py`, `tests/bot/test_webhook.py`, `tests/bot/test_commands.py`.

---

### Task 5: The `posting_tick` cron and docs

**Files:**
- Modify: `src/clipforge/app.py`, `tests/test_app.py`
- Modify: `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`

**Interfaces:**
- Consumes: `tick`, `BotContext`, `_service_deps`, `runtime.telegram_sender`, `utcnow`.
- Produces: the Modal function `posting_tick`.

- [ ] **Step 1: Write the failing test.** In `tests/test_app.py`, add `"posting_tick"` to the names in `test_step_functions_and_endpoints_exist`.

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_app.py -q`
Expected: FAIL with `AssertionError: posting_tick`.

- [ ] **Step 3: Implement** in `app.py`, after `sweeper`:

```python
@app.function(
    image=base_image,
    cpu=0.25,
    timeout=300,  # one clip upload (≤ 45 MB) to Telegram
    schedule=modal.Cron("*/5 * * * *"),
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def posting_tick() -> None:
    """Send the next clip to the owner's phone when a posting slot is due (ADR-23)."""
    from clipforge.bot.context import BotContext
    from clipforge.bot.posting import tick
    from clipforge.jobs import utcnow

    settings = get_settings()
    sender = runtime.telegram_sender(settings)
    if sender is None or settings.posting_chat_id is None:
        return
    deps = _service_deps()
    deps.volume.reload()  # see clips rendered since this container started
    print(f"posting_tick: {tick(BotContext(settings, sender, deps), utcnow())}")
```

Update the module docstring's function list if it has one.

- [ ] **Step 4: Run the tests and check they pass**

Run: `uv run pytest tests/test_app.py -q`
Expected: PASS (including `test_only_app_imports_modal`).

- [ ] **Step 5: Docs**

`docs/ARCHITECTURE.md`: add `posting_tick (cron, every 5 min): the next clip to the owner's phone at each slot` under the sweeper line in the overview diagram. Add a section after "Posting queue":

```markdown
## Posting assistant (ADR-23)

`posting_tick` runs every 5 minutes. When a slot from `POSTING_SLOTS` (in `POSTING_TIMEZONE`) is at most 30 minutes old, it claims the slot and sends the best eligible clip to `POSTING_CHAT_ID`: the video, then a text with copy blocks for TikTok, Instagram and YouTube and buttons. ✅ per platform toggles `posted:<platform>`, ⏭ Skip sends the next clip (the skipped one returns after 24 h), and 🗑 Reject asks for an optional reason. After 2 unanswered clips the slots pause and one reminder is sent. `/status`, `/next`, `/pause` and `/go` work from the phone. A half-delivered send is deleted and retried. Code: `bot/posting.py`; the webhook registers `callback_query` updates (re-run `clipforge set-webhook` after deploying).
```

`CLAUDE.md` Layout: change the `bot/` line to `bot/              # Telegram: telegram.py (PTB sync bridge), messages, notifier, commands, webhook, posting (ADR-23)`.

`ROADMAP.md` Phase 2: add and tick after the ADR-23 queue line:
`- [x] Telegram posting assistant: slot cron, clip + captions + ✅/⏭/🗑 buttons, pause rule, /status /next /pause /go (ADR-23)`

`videos/README.md`, append:

````markdown
## Posting from your phone

Once `POSTING_CHAT_ID` (your Telegram user id) is in the `clipforge-secrets` Modal secret and you've run `uv run clipforge set-webhook` after deploying, every finished channel video's clips join the posting queue. At each slot (default 08:00, 10:30, 13:00, 16:00, 19:00, 21:30 New York time) the bot sends you the next clip and its captions:

1. Save the video, post it in TikTok, Instagram and YouTube, pasting each caption block.
2. Tap ✅ TikTok / ✅ Instagram / ✅ YouTube as you go (tap again to undo).
3. Or tap ⏭ Skip (it comes back tomorrow) or 🗑 Reject (never; pick a reason if you like).

`/status` shows each channel's progress and how many days the queue lasts. `/next` sends a clip now. `/pause` and `/go` stop and restart the slots. After 2 clips without a tap, the bot waits for you and reminds you once.
````

- [ ] **Step 6: Full check**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all pass.

- [ ] **Step 7: Checkpoint.** Files: `src/clipforge/app.py`, `tests/test_app.py`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`, `videos/README.md`.

---

### Task 6: Keep the posting state alive (ADR-24)

Added 2026-09-29 after the plan B review: Modal Dict entries expire after 7 days without reads or writes. The owner chose a daily keep-alive read plus a snapshot on the Volume.

**Files:**
- Create: `src/clipforge/posting/keepalive.py`
- Modify: `src/clipforge/app.py` (`posting_keepalive` cron), `src/clipforge/service.py` or the API (`POST /posting/restore`), `src/clipforge/cli.py` (`status --restore`)
- Test: `tests/posting/test_keepalive.py`, `tests/test_app.py`, `tests/api/test_api.py`, `tests/test_cli.py`
- Docs: `docs/ARCHITECTURE.md`, `ROADMAP.md` (tick the ADR-24 line)

**Interfaces:**
- `KEEP_PREFIXES = ("post:", "job:")` and `KEEP_KEYS = ("posting:paused",)`
- `keepalive.touch(kv: KV) -> int`: `get` every key in `kv.keys()` that starts with a prefix in `KEEP_PREFIXES` or is in `KEEP_KEYS`; returns how many
- `keepalive.snapshot(kv: KV, root: Path, now: datetime, keep: int = 14) -> Path`: writes `{key: value}` for every `post:*` key and `posting:paused` to `<root>/posting/snapshots/<YYYY-MM-DD>.json` (write-then-rename), deletes all but the newest `keep`, returns the path
- `keepalive.restore(kv: KV, root: Path) -> int`: loads the newest snapshot and `put(..., skip_if_exists=True)` each key; returns how many were missing and put back
- `app.posting_keepalive`: `schedule=modal.Cron("0 7 * * *")`, CPU, timeout 900 s. It reloads the Volume, runs `touch` then `snapshot`, commits the Volume and prints both counts.

**Tests (write first):**
- `touch` reads exactly the post/job/paused keys and not `tg:update:*` or `posting:slot:*` (use a recording KV wrapper over `MemoryKV`).
- `snapshot` writes valid JSON with every `post:*` key, keeps only the newest 14 files, and never leaves a half-written file.
- `restore` puts back a deleted `posted:tiktok` key and doesn't overwrite a key that changed after the snapshot. With no snapshot it returns 0.
- `test_app`: `posting_keepalive` exists.
- The API `POST /posting/restore` needs the bearer token and returns `{"restored": n}`. `clipforge status --restore` prints it.

**After the checkpoint (owner, not the implementer):** deploy (`uv run modal deploy src/clipforge/app.py`, or merge to `main`), add `POSTING_CHAT_ID`, `POSTING_TIMEZONE` and `POSTING_HASHTAGS` to the `clipforge-secrets` Modal secret, run `uv run clipforge set-webhook` once, then `uv run clipforge status --rebuild` to queue channel jobs that finished before the deploy. `posting_keepalive` (Task 6) runs daily from the same deploy.

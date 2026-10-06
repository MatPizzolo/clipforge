"""handle_update: one Telegram update in, at most one job and one reply out (spec §5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clipforge.accounts.service import env_account
from clipforge.bot import messages
from clipforge.bot.posting import fresh_keyboard
from clipforge.bot.webhook import MAX_UPLOAD_BYTES, BotContext, handle_update
from clipforge.jobs import utcnow
from clipforge.models import LEGACY_PLATFORMS, Platform, PostStatus, RejectReason, TelegramTarget
from clipforge.pipeline.deps import SpawnCall
from clipforge.posting.backend import dict_posting
from clipforge.posting.queue import status
from clipforge.posting.repo import DictPostingRepo
from clipforge.posting.slots import next_slot
from tests.bot.fakes import ALLOWED_USER, CHAT, FakeSender, callback, make_settings, update, video
from tests.bot.helpers import tick
from tests.dbhelpers import make_account
from tests.pipeline.harness import Harness
from tests.posting.builders import ACCOUNT, run_channel_job

URL = "https://media.example.com/ep.mp4"
Bot = tuple[BotContext, FakeSender]


@pytest.fixture
def bot(harness: Harness) -> Bot:
    sender = FakeSender()
    return BotContext(make_settings(harness.root), sender, harness.deps), sender


def _jobs(harness: Harness) -> list[str]:
    return harness.store.list_job_ids()


def test_clip_command_creates_a_job_and_replies(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=f"/clip {URL} n=2"), ctx)
    [job_id] = _jobs(harness)
    job = harness.store.get(job_id)
    assert str(job.input.source_url) == URL and job.input.options.n == 2
    assert job.input.notify == TelegramTarget(chat_id=CHAT, reply_to_message_id=3)
    assert list(harness.spawner.queue) == [SpawnCall("ingest", job_id, None)]
    assert sender.messages == [(CHAT, messages.job_accepted(job_id), 3)]


def test_bare_link_creates_a_job(harness: Harness, bot: Bot) -> None:
    ctx, _ = bot
    handle_update(update(text=URL), ctx)
    assert len(_jobs(harness)) == 1


def test_duplicate_update_is_handled_once(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(5, text=URL), ctx)
    handle_update(update(5, text=URL), ctx)
    assert len(_jobs(harness)) == 1 and len(sender.messages) == 1


def test_stranger_is_ignored_without_trace(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=URL, user_id=666), ctx)
    assert sender.messages == [] and _jobs(harness) == []
    assert not any(k.startswith("tg:") for k in harness.store.kv.keys())  # noqa: SIM118


def test_edited_message_is_ignored(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=URL, kind="edited_message"), ctx)
    handle_update(update(2, text=URL, kind="channel_post"), ctx)
    assert sender.messages == [] and _jobs(harness) == []


def test_sticker_gets_usage(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    sticker = {
        "file_id": "S",
        "file_unique_id": "US",
        "width": 1,
        "height": 1,
        "is_animated": False,
        "is_video": False,
        "type": "regular",
    }
    handle_update(update(sticker=sticker), ctx)
    assert sender.messages == [(CHAT, messages.USAGE, 3)]


def test_small_video_upload_creates_a_telegram_job(harness: Harness, bot: Bot) -> None:
    ctx, _ = bot
    handle_update(update(video=video(5_000_000), caption="n=1 len=10-20"), ctx)
    [job_id] = _jobs(harness)
    job = harness.store.get(job_id)
    assert job.input.telegram_file_id == "VID" and job.input.options.n == 1


def test_document_upload_is_accepted(harness: Harness, bot: Bot) -> None:
    ctx, _ = bot
    document = {"file_id": "DOC", "file_unique_id": "UDOC", "file_size": 1000}
    handle_update(update(document=document), ctx)
    assert harness.store.get(_jobs(harness)[0]).input.telegram_file_id == "DOC"


def test_upload_over_20_mb_is_refused(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(video=video(MAX_UPLOAD_BYTES + 1)), ctx)
    assert _jobs(harness) == [] and sender.messages == [(CHAT, messages.TOO_BIG, 3)]


def test_bad_option_replies_with_the_error(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    handle_update(update(text=f"/clip {URL} style=bold"), ctx)
    assert _jobs(harness) == [] and "Unknown option" in sender.messages[0][1]


def test_status_of_a_finished_job_has_the_link(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    job_id = harness.submit()
    harness.run()
    handle_update(update(text=f"/status {job_id}"), ctx)
    text = sender.messages[-1][1]
    assert text.startswith(f"job {job_id}: done") and f"/jobs/{job_id}/download?" in text


def test_status_rejects_non_job_ids(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    (harness.root / "x" / "output").mkdir(parents=True)
    handle_update(update(text="/status ../x"), ctx)
    assert sender.messages[-1][1] == "No job ../x."


def test_resume_of_a_running_job_explains(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    job_id = harness.submit()
    handle_update(update(text=f"/resume {job_id}"), ctx)
    assert "only failed jobs can be resumed" in sender.messages[-1][1]


def test_resume_of_a_failed_job_respawns(harness: Harness, bot: Bot) -> None:
    ctx, sender = bot
    harness.stages.permanent["transcribe"] = "no speech"
    job_id = harness.submit()
    harness.run()
    harness.stages.permanent.clear()
    handle_update(update(text=f"/resume {job_id}"), ctx)
    assert sender.messages[-1][1] == f"Resuming job {job_id}."
    assert harness.spawner.queue[-1] == SpawnCall("transcribe", job_id, None)


@pytest.fixture
def posting(harness: Harness) -> Bot:
    run_channel_job(harness)
    sender = FakeSender()
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER)
    harness.deps.posting = dict_posting(harness.deps.store.kv, env_account(settings))
    return BotContext(settings, sender, harness.deps), sender


def _sent(ctx: BotContext) -> tuple[str, int]:
    """Send one clip with /next; return its ref and its text message id."""
    handle_update(update(90, text="/next", user_id=ALLOWED_USER), ctx)
    store = DictPostingRepo(ctx.deps.store.kv, ACCOUNT)
    record = next(r for r in store.records(ACCOUNT) if r.sends)
    return record.item.id, record.sends[-1].message_id


def test_toggle_and_undo_update_the_buttons(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id), ctx)
    assert sender.answers[-1] == ("cb1", "")  # answered first; the buttons show the state
    assert sender.keyboards[message_id][0][0] == ("TikTok ✓", f"p:tt:{ref}")  # type: ignore[index]
    handle_update(callback(2, f"p:tt:{ref}", message_id=message_id), ctx)
    assert sender.answers[-1] == ("cb2", "")
    assert sender.keyboards[message_id] == fresh_keyboard(ref, list(LEGACY_PLATFORMS))
    for n, action in enumerate(["tt", "ig", "yt"], start=3):
        handle_update(callback(n, f"p:{action}:{ref}", message_id=message_id), ctx)
    record = DictPostingRepo(ctx.deps.store.kv, ACCOUNT).get(ref)
    assert record is not None and status(record) is PostStatus.POSTED
    assert sender.keyboards[message_id] == [[("Posted everywhere ✓", f"p:noop:{ref}")]]


def test_skip_sends_the_next_clip(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:skip:{ref}", message_id=message_id), ctx)
    assert len(sender.videos) == 2  # the next one went out right away
    record = DictPostingRepo(ctx.deps.store.kv, ACCOUNT).get(ref)
    assert record is not None and status(record) is PostStatus.SKIPPED


def test_reject_then_reason(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:rej:{ref}", message_id=message_id), ctx)
    handle_update(callback(2, f"p:why:bad_crop:{ref}", message_id=message_id), ctx)
    record = DictPostingRepo(ctx.deps.store.kv, ACCOUNT).get(ref)
    assert record is not None and record.verdict is not None
    assert record.verdict.reason is RejectReason.BAD_CROP
    assert sender.keyboards[message_id] == [[("Rejected · Bad crop", f"p:noop:{ref}")]]


def test_tap_on_unknown_clip_answers_gone(posting: Bot) -> None:
    ctx, sender = posting
    handle_update(callback(1, "p:tt:20260101-bbbbbbbb-0001:clip_01"), ctx)
    assert sender.answers == [("cb1", "")]
    assert sender.messages[-1][1] == messages.GONE  # told in the chat: a query answers once


def test_taps_outside_the_posting_chat_or_from_strangers_do_nothing(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id, chat_id=CHAT), ctx)
    handle_update(callback(2, f"p:tt:{ref}", message_id=message_id, user_id=999), ctx)
    record = DictPostingRepo(ctx.deps.store.kv, ACCOUNT).get(ref)
    assert record is not None and record.posted == {}
    assert sender.answers == [("cb1", "")]  # the stranger gets nothing at all


def test_duplicate_tap_is_handled_once(posting: Bot) -> None:
    ctx, _ = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id), ctx)
    handle_update(callback(1, f"p:tt:{ref}", message_id=message_id), ctx)  # redelivered
    record = DictPostingRepo(ctx.deps.store.kv, ACCOUNT).get(ref)
    assert record is not None and set(record.posted) == {Platform.TIKTOK}


def test_status_pause_go_commands(posting: Bot) -> None:
    ctx, sender = posting
    handle_update(update(1, text="/status", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1].startswith("Billy Garton Jr. — 1 episodes")
    handle_update(update(2, text="/pause", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.PAUSED
    # at a slot: the tick computes the slot before it reads the pause (card 002 A3)
    slot = next_slot(env_account(ctx.settings).posting, utcnow())
    assert slot is not None
    # the dispatcher skips a braked account before reading anything (S2 §6.7)
    assert tick(ctx, slot + timedelta(minutes=1)) == f"{ACCOUNT}: braked"
    handle_update(update(3, text="/go", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.RESUMED
    assert not DictPostingRepo(ctx.deps.store.kv, ACCOUNT).paused(ACCOUNT)


def test_double_skip_sends_one_clip(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:skip:{ref}", message_id=message_id), ctx)
    handle_update(callback(2, f"p:skip:{ref}", message_id=message_id), ctx)
    assert len(sender.videos) == 2  # the first one, plus one for the first skip only


def test_stale_taps_on_a_rejected_clip_change_nothing(posting: Bot) -> None:
    ctx, sender = posting
    ref, message_id = _sent(ctx)
    handle_update(callback(1, f"p:rej:{ref}", message_id=message_id), ctx)
    handle_update(callback(2, f"p:why:bad_crop:{ref}", message_id=message_id), ctx)
    videos = len(sender.videos)
    for n, action in enumerate(["rej", "skip", "tt"], start=3):
        handle_update(callback(n, f"p:{action}:{ref}", message_id=message_id), ctx)
    record = DictPostingRepo(ctx.deps.store.kv, ACCOUNT).get(ref)
    assert record is not None and record.verdict is not None
    assert record.verdict.kind == "rejected"
    assert record.verdict.reason is RejectReason.BAD_CROP
    assert record.posted == {}
    assert len(sender.videos) == videos
    assert sender.keyboards[message_id] == [[("Rejected · Bad crop", f"p:noop:{ref}")]]


def test_pause_with_an_unknown_account_names_the_known_ones(posting: Bot) -> None:
    ctx, sender = posting
    handle_update(update(1, text="/pause nope", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.unknown_account("nope", [ACCOUNT])
    assert not DictPostingRepo(ctx.deps.store.kv, ACCOUNT).paused(ACCOUNT)


def test_pause_without_an_account_pauses_every_posting_account(posting: Bot) -> None:
    ctx, sender = posting
    handle_update(update(1, text="/pause", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.PAUSED
    assert DictPostingRepo(ctx.deps.store.kv, ACCOUNT).paused(ACCOUNT)
    # /pause with no account is the fleet brake (S2 §6.7): /go <account> doesn't lift it
    handle_update(update(2, text=f"/go {ACCOUNT}", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == f"{ACCOUNT}: {messages.STILL_BRAKED}"
    assert DictPostingRepo(ctx.deps.store.kv, ACCOUNT).paused(ACCOUNT)
    handle_update(update(3, text="/go all", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.RESUMED
    assert not DictPostingRepo(ctx.deps.store.kv, ACCOUNT).paused(ACCOUNT)


def _posting_off(harness: Harness) -> Bot:
    settings = make_settings(harness.root)
    harness.deps.posting = dict_posting(harness.deps.store.kv, make_account(chat_id=None))
    return BotContext(settings, FakeSender(), harness.deps), harness.deps.posting  # type: ignore[return-value]


def test_pause_and_go_with_posting_off_still_set_the_default_flag(harness: Harness) -> None:
    ctx, _ = _posting_off(harness)
    sender = ctx.sender
    assert isinstance(sender, FakeSender)
    repo = DictPostingRepo(ctx.deps.store.kv, ACCOUNT)
    handle_update(update(1, text="/pause", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.PAUSED
    assert repo.paused(ACCOUNT)
    handle_update(update(2, text="/go", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.RESUMED
    assert not repo.paused(ACCOUNT)


def test_pause_with_posting_off_and_a_failing_write_says_posting_is_off(harness: Harness) -> None:
    ctx, _ = _posting_off(harness)
    sender = ctx.sender
    assert isinstance(sender, FakeSender)
    repo = ctx.deps.posting.repo  # type: ignore[union-attr]
    repo.set_paused = lambda *a: (_ for _ in ()).throw(RuntimeError("no db"))  # type: ignore[method-assign]
    handle_update(update(1, text="/pause", user_id=ALLOWED_USER), ctx)
    assert sender.messages[-1][1] == messages.POSTING_OFF

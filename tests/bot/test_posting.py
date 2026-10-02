"""The posting assistant: message, keyboard, callbacks, tick."""

from __future__ import annotations

import dataclasses
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from clipforge.accounts.service import env_account, publish_schedule
from clipforge.bot import messages
from clipforge.bot.context import BotContext
from clipforge.bot.posting import (
    BLOCK_LIMIT,
    extras,
    fresh_keyboard,
    handle_callback,
    held,
    keyboard,
    parse_callback,
    post_html,
    send_next,
    tick,
    video_caption,
)
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.db.sources import SourcesRepo
from clipforge.models import (
    LEGACY_PLATFORMS,
    Account,
    CampaignRules,
    Platform,
    PostSend,
    PostVerdict,
    RejectReason,
    Source,
    SourcePermission,
)
from clipforge.posting.backend import build_posting, dict_posting
from clipforge.posting.repo import DictPostingRepo
from tests.bot.fakes import ALLOWED_USER, FakeSender, make_settings
from tests.bot.helpers import dict_ctx, two_account_ctx
from tests.conftest import TALKING_HEAD, requires_ffmpeg
from tests.dbhelpers import make_account
from tests.pipeline.harness import Harness
from tests.posting.builders import ACCOUNT, JOB, T0, item, record, run_channel_job, send

REF = f"{JOB}:clip_01"
THREE = list(LEGACY_PLATFORMS)


def test_parse_callback() -> None:
    assert parse_callback(f"p:tt:{REF}") is not None
    why = parse_callback(f"p:why:bad_crop:{REF}")
    assert why is not None and why.reason is RejectReason.BAD_CROP and why.ref == REF
    for bad in [None, "", "x:tt:" + REF, f"p:zz:{REF}", "p:tt:not-a-job:clip_01",
                f"p:tt:{JOB}:clip_1", f"p:why:nope:{REF}", f"p:tt:{REF}:extra"]:  # fmt: skip
        assert parse_callback(bad) is None, bad
    assert max(len(f"p:why:{r}:{REF}".encode()) for r in RejectReason) <= 64


def test_fresh_keyboard() -> None:
    assert fresh_keyboard(REF, list(LEGACY_PLATFORMS)) == [
        [("✅ TikTok", f"p:tt:{REF}"), ("✅ Instagram", f"p:ig:{REF}"),
         ("✅ YouTube", f"p:yt:{REF}")],
        [("⏭ Skip", f"p:skip:{REF}"), ("🗑 Reject", f"p:rej:{REF}")],
    ]  # fmt: skip


def test_keyboard_follows_the_state() -> None:
    it = item()
    partly = keyboard(record(it, sends=[send()], posted=[Platform.TIKTOK]))
    assert partly[0][0] == ("TikTok ✓", f"p:tt:{REF}")
    assert keyboard(record(it, posted=LEGACY_PLATFORMS)) == [
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
    text = post_html(item(title="<Be> honest & real", hook="a < b"), ["mindset"], THREE)
    assert "&lt;Be&gt; honest &amp; real" in text
    for name in ("TikTok", "Instagram", "YouTube title", "YouTube description"):
        assert f"<b>{name}</b>\n<pre>" in text
    assert len(post_html(item(hook="x" * 5000), ["mindset"], THREE)) < 4096


def test_video_caption() -> None:
    assert video_caption(item(score=0.891), 214) == "Billy Garton Jr. · ep01 · 0.89 · 214 queued"


def test_post_html_stays_under_the_limit_after_escaping() -> None:
    # escaping can grow text fivefold ("&" -> "&amp;"): the limit applies to what Telegram gets
    assert len(post_html(item(title="&" * 300, hook="&<>" * 2000), ["mindset"], THREE)) < 4096


def test_post_html_with_every_platform_stays_under_the_limit() -> None:
    long = item(title="&" * 300, hook="&<>" * 1000 + "x" * 3000)
    links = ["https://x.y/" + "a" * 900]
    assert len(post_html(long, ["mindset"] * 50, list(Platform), links)) <= 4096
    assert len(post_html(item(hook="x" * 3000), ["mindset"], list(Platform))) <= 4096
    assert BLOCK_LIMIT == 700


def test_facebook_button_and_block_when_due() -> None:
    rec = record(item(), platforms=[Platform.TIKTOK, Platform.FACEBOOK])
    assert [d for _, d in keyboard(rec)[0]] == [f"p:tt:{REF}", f"p:fb:{REF}"]
    assert "<b>Facebook</b>" in post_html(item(), [], rec.platforms)
    assert parse_callback(f"p:fb:{REF}") is not None


# ---- sending, the slot tick, /next

NY = ZoneInfo("America/New_York")
SLOTS = ["08:00", "12:00", "16:00", "20:00"]
DAY = datetime(2026, 9, 29, tzinfo=NY)


def at(hour: int, minute: int = 1, days: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute) + timedelta(days=days)


@pytest.fixture
def ctx(harness: Harness) -> BotContext:
    run_channel_job(harness)  # 3 queued clips with real files
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER, posting_slots=SLOTS)
    harness.deps.posting = dict_posting(harness.deps.store.kv, env_account(settings))
    return BotContext(settings, FakeSender(), harness.deps)


def _sender(ctx: BotContext) -> FakeSender:
    assert isinstance(ctx.sender, FakeSender)
    return ctx.sender


def _store(ctx: BotContext) -> DictPostingRepo:
    return DictPostingRepo(ctx.deps.store.kv, ACCOUNT)


@requires_ffmpeg
def test_send_passes_the_probed_frame_size(ctx: BotContext) -> None:
    """The slot send probes the clip, so Telegram doesn't squeeze it into a square."""
    for r in _store(ctx).records(ACCOUNT):
        assert r.item.video_path is not None
        shutil.copyfile(TALKING_HEAD, ctx.deps.root / r.item.video_path)  # a real video
    assert tick(ctx, at(8)).startswith(f"{ACCOUNT}: sent ")
    [size] = _sender(ctx).sizes
    assert size is not None and (size.width, size.height) == (480, 854)
    assert 9.9 < size.duration_s < 10.1


def test_send_without_a_readable_probe_still_goes_out(ctx: BotContext) -> None:
    """A file ffprobe can't read is sent without a size, as before."""
    for r in _store(ctx).records(ACCOUNT):
        assert r.item.video_path is not None
        (ctx.deps.root / r.item.video_path).write_bytes(b"not a video")
    assert tick(ctx, at(8)).startswith(f"{ACCOUNT}: sent ")
    assert _sender(ctx).sizes == [None]


def test_one_send_per_slot(ctx: BotContext) -> None:
    outcome = tick(ctx, at(8))
    assert outcome.startswith(f"{ACCOUNT}: sent ")
    assert tick(ctx, at(8, 6)) == f"{ACCOUNT}: taken"  # a second tick in the same slot
    sender = _sender(ctx)
    assert len(sender.videos) == 1 and len(sender.messages) == 1
    [(_, text, reply_to)] = sender.messages
    assert "<b>TikTok</b>" in text and reply_to == 101  # the text replies to the video
    assert sender.keyboards[102] is not None
    sent = [r for r in _store(ctx).records(ACCOUNT) if r.sends]
    assert len(sent) == 1 and sent[0].sends[0].message_id == 102


def test_missed_slot_is_dropped_and_off_and_paused(ctx: BotContext) -> None:
    assert tick(ctx, at(8, 31)) == f"{ACCOUNT}: no slot"
    _store(ctx).set_paused(ACCOUNT, True, at(7))
    assert tick(ctx, at(12)) == f"{ACCOUNT}: paused"
    ctx.deps.posting = dict_posting(ctx.deps.store.kv, env_account(make_settings(ctx.deps.root)))
    assert tick(ctx, at(12)) == "off"  # no posting chat: no account to serve
    assert _sender(ctx).videos == []


def test_half_delivered_send_is_rolled_back(ctx: BotContext) -> None:
    sender = _sender(ctx)
    sender.fail_on = {"send_message"}
    assert tick(ctx, at(8)) == f"{ACCOUNT}: send failed"
    assert sender.deleted == [(ALLOWED_USER, 101)]  # the video that did go out
    assert not any(r.sends for r in _store(ctx).records(ACCOUNT))
    sender.fail_on = set()
    assert tick(ctx, at(8, 6)).startswith(f"{ACCOUNT}: sent ")  # the slot was released: retried


def test_pause_rule_reminds_once_and_resumes_after_a_tap(ctx: BotContext) -> None:
    sent = f"{ACCOUNT}: sent "
    assert tick(ctx, at(8)).startswith(sent)
    assert tick(ctx, at(12)).startswith(sent)
    assert tick(ctx, at(16)) == f"{ACCOUNT}: waiting"
    assert tick(ctx, at(16, 6)) == f"{ACCOUNT}: waiting"
    sender = _sender(ctx)
    reminders = [text for _, text, _ in sender.messages if "waiting" in text]
    assert len(reminders) == 1
    first = next(r for r in _store(ctx).records(ACCOUNT) if r.sends)
    _store(ctx).toggle_posted(first.item.id, Platform.TIKTOK, at(17))
    assert tick(ctx, at(20)).startswith(sent)


def test_unavailable_video_is_skipped(ctx: BotContext) -> None:
    records = _store(ctx).records(ACCOUNT)
    paths = [r.item.video_path for r in records]
    best = max((r for r in records if paths.count(r.item.video_path) == 1),
               key=lambda r: r.item.score)  # fmt: skip
    (ctx.deps.root / best.item.video_path).unlink()
    outcome = tick(ctx, at(8))
    assert outcome.startswith(f"{ACCOUNT}: sent ") and best.item.id not in outcome
    assert _store(ctx).get(best.item.id).unavailable  # type: ignore[union-attr]


def test_send_next_ignores_slots_and_reports_empty(ctx: BotContext) -> None:
    for _ in range(3):
        assert send_next(ctx, at(9)) == ""
    assert "empty" in send_next(ctx, at(9))
    assert len(_sender(ctx).videos) == 3


def test_resend_numbering_survives_a_lost_send_key(ctx: BotContext) -> None:
    """A clip whose sent:1 key was lost (bad value) but has sent:2 is numbered 3 next, never a
    duplicate 2 that would be silently dropped (Plan B review M4)."""
    store = _store(ctx)
    for r in store.records(ACCOUNT):
        store.set_verdict(r.item.id, PostVerdict(kind="rejected", at=at(7, days=-3)))
    target = store.records(ACCOUNT)[0].item
    ctx.deps.store.kv.delete(f"post:{target.id}:verdict")
    store.add_send(target.id, send(2, at(7, days=-3)))
    store.set_verdict(target.id, PostVerdict(kind="skipped", at=at(7, days=-2)))
    assert send_next(ctx, at(9)) == ""
    record = store.get(target.id)
    assert record is not None and [s.n for s in record.sends] == [2, 3]


class _LateVolume:
    """A Volume view that sees the staged files only after `reload()` (a warm web container
    that started before package_step committed them)."""

    def __init__(self, staged: dict[Path, Path]) -> None:
        self.staged = staged  # hidden copy -> real path
        self.reloads = 0

    def commit(self) -> None:
        return None

    def reload(self) -> None:
        self.reloads += 1
        for hidden, real in self.staged.items():
            hidden.rename(real)
        self.staged = {}


def test_send_reloads_the_volume_before_marking_a_video_missing(ctx: BotContext) -> None:
    staged: dict[Path, Path] = {}
    for r in _store(ctx).records(ACCOUNT):
        real = ctx.deps.root / r.item.video_path
        if real.is_file():
            hidden = real.with_name(f".{real.name}.hidden")
            real.rename(hidden)
            staged[hidden] = real
    volume = _LateVolume(staged)
    late = BotContext(ctx.settings, ctx.sender, dataclasses.replace(ctx.deps, volume=volume))
    assert send_next(late, at(9)) == ""
    assert volume.reloads == 1
    assert len(_sender(ctx).videos) == 1
    assert not any(r.unavailable for r in _store(ctx).records(ACCOUNT))


def test_lost_race_deletes_the_duplicate_delivery(
    ctx: BotContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tick and /next (or two Skips) picked the same clip; the other caller recorded it first."""
    real_add = DictPostingRepo.add_send

    def other_caller_first(
        self: DictPostingRepo, ref: str, sent: PostSend, chat_id: int | None = None
    ) -> bool:
        real_add(self, ref, sent.model_copy(update={"message_id": 900, "video_message_id": 899}))
        return real_add(self, ref, sent)

    monkeypatch.setattr(DictPostingRepo, "add_send", other_caller_first)
    assert send_next(ctx, at(9)) == ""
    sender = _sender(ctx)
    assert len(sender.videos) == 1  # no second clip sent
    assert sorted(sender.deleted) == [(ALLOWED_USER, 101), (ALLOWED_USER, 102)]
    [sent] = [r for r in _store(ctx).records(ACCOUNT) if r.sends]
    assert [s.message_id for s in sent.sends] == [900]


def test_skip_still_works_when_answering_the_tap_fails(ctx: BotContext) -> None:
    assert send_next(ctx, at(9)) == ""
    sender = _sender(ctx)
    [first] = [r for r in _store(ctx).records(ACCOUNT) if r.sends]
    ref = first.item.id
    sender.fail_on = {"answer_callback"}  # e.g. "query is too old" after a cold start
    handle_callback(ctx, "cb1", f"p:skip:{ref}", ALLOWED_USER, 102, at(9, 5))
    updated = _store(ctx).get(ref)
    assert updated is not None and updated.verdict is not None
    assert updated.verdict.kind == "skipped"
    assert sender.keyboards[102] == [[("Skipped ⏭", f"p:noop:{ref}")]]
    assert len(sender.videos) == 2  # the next clip went out


def test_answer_failure_on_an_ignored_tap_does_not_raise(ctx: BotContext) -> None:
    _sender(ctx).fail_on = {"answer_callback"}
    handle_callback(ctx, "cb1", "garbage", ALLOWED_USER, 102, at(9))
    handle_callback(ctx, "cb2", "p:skip:20260928-aaaaaaaa-0001:clip_09", ALLOWED_USER, 102, at(9))


def test_each_account_sends_at_its_own_slot(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    at_8_ny = datetime(2026, 9, 29, 8, 1, tzinfo=ZoneInfo("America/New_York"))
    result = tick(ctx, at_8_ny)
    assert "realtalk-clips-en: sent" in result and "founder-tapes-en: no slot" in result
    sender = ctx.sender
    assert isinstance(sender, FakeSender) and sender.videos[0][2].startswith("realtalk-clips-en · ")
    at_9_mx = datetime(2026, 9, 29, 9, 1, tzinfo=ZoneInfo("America/Mexico_City"))
    assert "founder-tapes-en: sent" in tick(ctx, at_9_mx)


def _both_live(ctx: BotContext) -> datetime:
    """Give founder the same 08:00 New York slot so both accounts are live at one instant."""
    posting = ctx.deps.posting
    assert posting is not None
    accounts = [
        a.model_copy(
            update={
                "posting": a.posting.model_copy(
                    update={"timezone": "America/New_York", "slots": ["08:00"]}
                )
            }
        )
        for a in posting.accounts()
    ]
    posting.accounts = lambda: accounts
    for account in accounts:
        publish_schedule(ctx.deps.store.kv, account)
    return datetime(2026, 9, 29, 8, 1, tzinfo=ZoneInfo("America/New_York"))


def test_pause_of_one_account_doesnt_stop_the_other(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    at = _both_live(ctx)
    ctx.deps.posting.repo.set_paused("realtalk-clips-en", True, T0)  # type: ignore[union-attr]
    result = tick(ctx, at)
    assert "realtalk-clips-en: paused" in result and "founder-tapes-en: sent" in result


def test_tick_db_error_releases_slot_and_continues(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    at = _both_live(ctx)
    posting = ctx.deps.posting
    assert posting is not None
    real = posting.repo.add_send

    def flaky(ref: str, send: PostSend, chat_id: int | None = None) -> bool:
        if ref.startswith(JOB):
            raise RuntimeError("SSL connection has been closed unexpectedly")
        return real(ref, send, chat_id)

    posting.repo.add_send = flaky  # type: ignore[method-assign]
    result = tick(ctx, at)
    assert "realtalk-clips-en: error" in result and "founder-tapes-en: sent" in result
    sender = ctx.sender
    assert isinstance(sender, FakeSender)
    assert sorted(m for _, m in sender.deleted) == [
        103,
        104,
    ]  # realtalk's two
    slot = datetime(2026, 9, 29, 8, 0, tzinfo=ZoneInfo("America/New_York"))
    assert posting.claims.claim_slot("realtalk-clips-en", slot)  # released for the next tick


def test_campaign_tags_links_ad_and_deadline() -> None:
    account = make_account(chat_id=ALLOWED_USER)
    account = account.model_copy(update={"posting": account.posting.model_copy(
        update={"hashtags": ["mindset"]})})  # fmt: skip
    source = Source(id="whop-x", account_id=account.id, credit_name="X", kind="campaign",
                    permission=SourcePermission(type="clipping_program"),
                    campaign=CampaignRules(required_tags=["whopclips"],
                                           required_links=["https://whop.com/x"], deadline=T0))  # type: ignore[list-item]  # fmt: skip
    it = item(channel="whop-x").model_copy(update={"sponsored": True})
    tags, links = extras(account, source, it)
    assert tags == ["ad", "whopclips", "mindset"] and links == ["https://whop.com/x"]
    assert held(record(it), source, T0 + timedelta(seconds=1)) == "campaign ended 2026-09-28"
    assert held(record(it), source, T0) is None


def test_expired_or_narrowed_permission_holds_at_the_tick(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    repo = SourcesRepo(db)
    billy = repo.get("billy-garton")
    assert billy is not None
    at = datetime(2026, 9, 29, 8, 1, tzinfo=ZoneInfo("America/New_York"))
    expired = billy.model_copy(update={"permission": billy.permission.model_copy(
        update={"expires_at": at - timedelta(days=1)})})  # fmt: skip
    repo.replace(expired, "test", at)
    slot = datetime(2026, 9, 29, 8, 0, tzinfo=ZoneInfo("America/New_York"))
    assert "realtalk-clips-en: empty" in tick(ctx, at)  # held: nothing eligible, nothing sent
    narrowed = billy.model_copy(
        update={"permission": billy.permission.model_copy(update={"platforms": [Platform.TIKTOK]})}
    )  # the item is due on tiktok/ig/yt
    repo.replace(narrowed, "test", at)
    ctx.deps.posting.claims.release_slot("realtalk-clips-en", slot)  # type: ignore[union-attr]
    assert "realtalk-clips-en: empty" in tick(ctx, at)


def test_tap_redraws_every_message_of_a_resent_clip(tmp_path: Path) -> None:
    ctx = dict_ctx(tmp_path)
    repo = ctx.deps.posting.repo  # type: ignore[union-attr]
    repo.add(item(), list(LEGACY_PLATFORMS))
    repo.add_send(REF, send(1, message_id=100))
    repo.add_send(REF, send(2, T0 + timedelta(days=1), message_id=200))
    handle_callback(ctx, "cb", f"p:tt:{REF}", ALLOWED_USER, 100, T0)  # tap the OLDER message
    sender = ctx.sender
    assert isinstance(sender, FakeSender)
    assert sender.keyboards[100] == sender.keyboards[200]
    assert sender.keyboards[200][0][0] == ("TikTok ✓", f"p:tt:{REF}")  # type: ignore[index]


def test_tap_from_another_accounts_chat_changes_nothing(tmp_path: Path, db: Database) -> None:
    other = 777
    ctx = two_account_ctx(tmp_path, db, founder_chat=other)
    founder_ref = "20260928-bbbbbbbb-0001:clip_01"
    repo = ctx.deps.posting.repo  # type: ignore[union-attr]
    # realtalk's chat taps founder's clip: ignored
    handle_callback(ctx, "cb", f"p:tt:{founder_ref}", ALLOWED_USER, 100, T0)
    assert repo.get(founder_ref).posted == {}  # type: ignore[union-attr]
    assert ctx.sender.answers[-1] == ("cb", "")  # type: ignore[attr-defined]
    # founder's own chat works
    handle_callback(ctx, "cb2", f"p:tt:{founder_ref}", other, 101, T0)
    assert set(repo.get(founder_ref).posted) == {Platform.TIKTOK}  # type: ignore[union-attr]


def test_save_failure_is_answered_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = dict_ctx(tmp_path)
    repo = ctx.deps.posting.repo  # type: ignore[union-attr]
    repo.add(item(), list(LEGACY_PLATFORMS))
    repo.toggle_posted = lambda *a: (_ for _ in ()).throw(RuntimeError("down"))  # type: ignore[method-assign]
    with caplog.at_level("WARNING"):
        handle_callback(ctx, "cb", f"p:tt:{REF}", ALLOWED_USER, 100, T0)
    assert ctx.sender.answers[-1] == ("cb", messages.SAVE_FAILED)  # type: ignore[attr-defined]
    assert "down" in caplog.text


def test_slot_guard_from_sends_when_the_claim_is_gone(ctx: BotContext) -> None:
    # decision log #77/#108: a deploy that changes the claim key (or an expired claim) must not
    # send the same slot twice; the recorded send's slot is the guard
    assert tick(ctx, at(8)).startswith(f"{ACCOUNT}: sent ")
    posting = ctx.deps.posting
    assert posting is not None
    posting.claims.release_slot(ACCOUNT, at(8, 0))
    assert tick(ctx, at(8, 6)) == f"{ACCOUNT}: taken"
    assert len(_sender(ctx).videos) == 1
    assert tick(ctx, at(12)).startswith(f"{ACCOUNT}: sent ")  # the next slot still sends


class _NoDatabase:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the database was read: {name}")


def _no_accounts() -> list[Account]:
    raise AssertionError("the database was read: accounts")


def test_tick_without_a_due_slot_never_reads_the_database(tmp_path: Path, db: Database) -> None:
    # card 002 A3: schedules come from the Dict copies, so Neon can scale to zero between slots
    ctx = two_account_ctx(tmp_path, db)
    posting = ctx.deps.posting
    assert posting is not None
    posting.repo = _NoDatabase()  # type: ignore[assignment]
    posting.accounts = _no_accounts
    noon = datetime(2026, 9, 29, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    assert tick(ctx, noon) == "founder-tapes-en: no slot; realtalk-clips-en: no slot"


def test_postgres_mode_hashtags_come_from_the_account(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    realtalk = AccountsRepo(db).get("realtalk-clips-en")
    assert realtalk is not None
    AccountsRepo(db).update(realtalk.model_copy(update={"posting": realtalk.posting.model_copy(
        update={"hashtags": ["fromaccount"]})}), T0)  # fmt: skip
    env = make_settings(tmp_path, state_reads="postgres", posting_chat_id=ALLOWED_USER,
                        posting_slots=["08:00"], posting_hashtags="fromenv")  # fmt: skip
    ctx.deps.posting = build_posting(env, ctx.deps.store.kv, db)
    result = tick(ctx, datetime(2026, 9, 29, 8, 1, tzinfo=ZoneInfo("America/New_York")))
    assert "realtalk-clips-en: sent" in result
    [(_, text, _)] = _sender(ctx).messages
    assert "#fromaccount" in text and "#fromenv" not in text


def _with_ops(ctx: BotContext) -> FakeSender:
    from clipforge.ops import OpsAlerts

    alerts = FakeSender()
    ctx.deps.ops = OpsAlerts(ctx.deps.store.kv, alerts, ALLOWED_USER, "America/New_York")
    return alerts


def test_tick_alerts_on_an_account_error_and_on_missing_schedule_copies(
    tmp_path: Path, db: Database
) -> None:
    # card 002 A6 (ADR-45), and the coordinator's A3 note: a missing copy can't silently stop
    ctx = two_account_ctx(tmp_path, db)
    alerts = _with_ops(ctx)
    posting = ctx.deps.posting
    assert posting is not None
    posting.repo.paused = lambda account_id: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("SSL connection has been closed unexpectedly"))  # fmt: skip
    at_8 = datetime(2026, 9, 29, 8, 1, tzinfo=ZoneInfo("America/New_York"))
    assert "realtalk-clips-en: error" in tick(ctx, at_8)
    assert any("Posting tick for realtalk-clips-en failed" in t for _, t, _ in alerts.messages)
    for key in [k for k in ctx.deps.store.kv.keys() if k.startswith("posting:schedule:")]:  # noqa: SIM118
        ctx.deps.store.kv.delete(key)
    assert tick(ctx, at_8) == "off"
    assert any("no schedule copies" in t for _, t, _ in alerts.messages)


def test_tick_alerts_when_postgres_mode_has_no_database(tmp_path: Path) -> None:
    deps = Harness.build(tmp_path).deps
    settings = make_settings(tmp_path, state_reads="postgres")
    deps.posting = build_posting(settings, deps.store.kv, None)
    ctx = BotContext(settings, FakeSender(), deps)
    alerts = _with_ops(ctx)
    assert tick(ctx, at(12)).startswith("off: DATABASE_URL")
    assert alerts.messages[-1][1] == "⚠️ Posting is off: DATABASE_URL is not configured"


def test_the_tick_sends_nothing_during_an_outage_and_go_clears_it(ctx: BotContext) -> None:
    # coordinator's G review: the outage flag stops the slots until the owner restores or /go
    from clipforge.bot.webhook import handle_update
    from clipforge.posting.keepalive import OUTAGE_KEY, outage_since
    from tests.bot.fakes import update

    ctx.deps.store.kv.put(OUTAGE_KEY, "2026-09-25")
    assert tick(ctx, at(8)) == "outage since 2026-09-25: restore, check /status, then /go"
    assert _sender(ctx).videos == []
    handle_update(update(1, text="/go", user_id=ALLOWED_USER), ctx)
    assert outage_since(ctx.deps.store.kv) is None
    assert "outage" in _sender(ctx).messages[-1][1].lower()
    assert tick(ctx, at(8)).startswith(f"{ACCOUNT}: sent ")

"""posting/actions.py: the one backend for posting actions (card 002 A4, ADR-44, S3c D3)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from clipforge.bot import messages
from clipforge.bot.context import BotContext
from clipforge.bot.webhook import handle_update
from clipforge.db.engine import Database
from clipforge.db.tables import post_events
from clipforge.models import Platform
from clipforge.posting import actions, brake
from clipforge.posting.backend import Posting
from tests.bot.fakes import ALLOWED_USER, FakeSender, callback, make_settings, update
from tests.bot.helpers import tick, two_account_ctx
from tests.posting.builders import JOB, T0

REF = f"{JOB}:clip_01"  # realtalk's clip in two_account_ctx
AT_8_NY = datetime(2026, 9, 29, 8, 1, tzinfo=ZoneInfo("America/New_York"))
DASH = "https://dash.example"


def _posting(ctx: BotContext) -> Posting:
    assert ctx.deps.posting is not None
    return ctx.deps.posting


def _sender(ctx: BotContext) -> FakeSender:
    assert isinstance(ctx.sender, FakeSender)
    return ctx.sender


def _sent(ctx: BotContext) -> int:
    """Send realtalk's clip at its slot; return the text message id."""
    assert "realtalk-clips-en: sent" in tick(ctx, AT_8_NY)
    record = _posting(ctx).repo.get(REF)
    assert record is not None
    return record.sends[-1].message_id


def _events(db: Database) -> list[tuple[str, dict[str, Any]]]:
    with db.begin() as conn:
        rows = conn.execute(select(post_events).where(post_events.c.item_id == REF)
                            .order_by(post_events.c.id)).all()  # fmt: skip
    return [(row.kind, row.data) for row in rows]


def _db_down(*args: object, **kwargs: object) -> Any:
    raise OperationalError("UPDATE posts", {}, Exception("server closed the connection"))


def test_taps_record_the_telegram_actor_and_system_writes_none(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    mid = _sent(ctx)
    handle_update(callback(1, f"p:tt:{REF}", message_id=mid), ctx)
    handle_update(callback(2, f"p:rej:{REF}", message_id=mid), ctx)
    handle_update(callback(3, f"p:why:bad_crop:{REF}", message_id=mid), ctx)
    events = _events(db)
    assert [kind for kind, _ in events] == ["sent", "posted", "rejected", "reason"]
    assert "actor" not in events[0][1]  # the tick's send is a system write
    assert all(data["actor"] == f"telegram:{ALLOWED_USER}" for _, data in events[1:])


def test_a_dashboard_action_records_the_web_actor_and_redraws_telegram(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    ctx = BotContext(make_settings(tmp_path, state_reads="postgres", dashboard_url=DASH),
                     ctx.sender, ctx.deps)  # fmt: skip
    mid = _sent(ctx)
    posting = _posting(ctx)
    assert actions.set_posted(posting, REF, Platform.INSTAGRAM, True,
                              actions.web_actor("matpizzolo"), T0)  # fmt: skip
    assert _events(db)[-1] == ("posted", {"actor": "web:matpizzolo"})
    actions.redraw_all(ctx, REF)
    buttons = _sender(ctx).keyboards[mid]
    assert buttons is not None
    assert ("Instagram ✓", f"p:ig:{REF}") in buttons[0]
    assert buttons[-1] == [("Job ↗", f"{DASH}/jobs/{JOB}"),
                           ("Source ↗", f"{DASH}/sources/billy-garton")]  # fmt: skip


def test_actors_are_checked() -> None:
    assert actions.telegram_actor(42) == "telegram:42"
    assert actions.web_actor("web:matpizzolo") == actions.web_actor(" matpizzolo ")
    for bad in (None, "", "../x", "a b", "x" * 40):
        with pytest.raises(ValueError):
            actions.web_actor(bad)
    with pytest.raises(ValueError):
        actions.skip(None, REF, "api", T0)  # type: ignore[arg-type]
    for good in ("telegram:42", "web:matpizzolo", "session:s1", "cli:matpizzolo"):
        assert actions.ACTOR.fullmatch(good)


def test_a_database_error_answers_store_unavailable_and_changes_nothing(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    mid = _sent(ctx)
    posting = _posting(ctx)
    posting.repo.toggle_posted = _db_down  # type: ignore[method-assign]
    handle_update(callback(1, f"p:tt:{REF}", message_id=mid), ctx)
    assert _sender(ctx).answers[-1] == ("cb1", "")
    assert _sender(ctx).messages[-1][1] == messages.STORE_UNAVAILABLE
    record = posting.repo.get(REF)
    assert record is not None and record.posted == {}
    assert [kind for kind, _ in _events(db)] == ["sent"]


def test_pause_and_next_answer_per_account_when_the_store_fails(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    posting = _posting(ctx)
    real = posting.repo.set_paused

    def flaky(
        account_id: str, on: bool, at: datetime, actor: str | None = None,
        reason: str | None = None,
    ) -> None:  # fmt: skip
        if account_id == "realtalk-clips-en":
            _db_down()
        real(account_id, on, at, actor, reason)

    posting.repo.set_paused = flaky  # type: ignore[method-assign]
    handle_update(update(1, text="/pause", user_id=ALLOWED_USER), ctx)
    reply = _sender(ctx).messages[-1][1]
    # the brake key was written first, so realtalk is braked even though its row failed (S2 §6.7)
    assert reply == (f"founder-tapes-en: {messages.PAUSED}\n"
                     f"realtalk-clips-en: {messages.PAUSED}{messages.BRAKE_ONLY}")  # fmt: skip
    assert posting.repo.paused("founder-tapes-en") and not posting.repo.paused("realtalk-clips-en")
    assert brake.braked(ctx.deps.store.kv, "realtalk-clips-en")

    posting.repo.records = _db_down  # type: ignore[method-assign]
    handle_update(update(2, text="/next realtalk-clips-en", user_id=ALLOWED_USER), ctx)
    assert _sender(ctx).messages[-1][1] == messages.STORE_UNAVAILABLE
    assert _sender(ctx).videos == []


def test_links_ride_on_clip_messages_only_with_a_dashboard(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    mid = _sent(ctx)
    buttons = _sender(ctx).keyboards[mid]
    assert buttons is not None and not any("://" in d for row in buttons for _, d in row)


def test_a_skip_stamped_before_its_send_still_answers_it(tmp_path: Path, db: Database) -> None:
    # card 017 item 9 / log #143: a container whose clock is 2 s behind the sender's must not
    # leave the clip `sent` (it would count toward the pause rule forever)
    from datetime import timedelta

    from clipforge.models import PostStatus
    from clipforge.posting.queue import status

    ctx = two_account_ctx(tmp_path, db)
    _sent(ctx)
    record = _posting(ctx).repo.get(REF)
    assert record is not None
    actions.skip(_posting(ctx), REF, "telegram:42", record.sends[-1].at - timedelta(seconds=2))
    after = _posting(ctx).repo.get(REF)
    assert after is not None and status(after) is PostStatus.SKIPPED


@pytest.mark.parametrize("actor", ["system:autopilot", "system:upload-post", "system:daily",
                                   "system:migration", "system:demotion"])  # fmt: skip
def test_system_actors_accepted(actor: str) -> None:
    assert actions._checked(actor) == actor


@pytest.mark.parametrize("actor", ["system:", "system:Bad", "sys:x", "system:x-", "system:-x"])
def test_bad_system_actors_refused(actor: str) -> None:
    with pytest.raises(ValueError):
        actions._checked(actor)

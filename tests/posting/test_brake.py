"""The brake (S2 spec §6.7; card 014 Task 4): `brake:<scope>` keys, `/pause all`, Neon outages
and posting_daily's newer-wins repair."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from clipforge.bot import messages
from clipforge.bot.context import BotContext
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.db.tables import posting_state
from clipforge.models import Brake
from clipforge.ops import OpsAlerts
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting import actions, brake
from clipforge.posting.backend import Posting
from clipforge.posting.daily import repair_brakes
from tests.bot.fakes import ALLOWED_USER, FakeSender
from tests.bot.helpers import dict_ctx, two_account_ctx
from tests.dbhelpers import make_account, seed

T = datetime(2026, 10, 2, 12, tzinfo=UTC)
RT, FT = "realtalk-clips-en", "founder-tapes-en"


def _posting(ctx: BotContext) -> Posting:
    assert ctx.deps.posting is not None
    return ctx.deps.posting


def _db_down(*args: object, **kwargs: object) -> Any:
    raise OperationalError("SELECT", {}, Exception("server closed the connection"))


def _row(db: Database, account_id: str) -> tuple[bool, str | None, str | None]:
    with db.begin() as conn:
        row = conn.execute(select(posting_state.c.paused, posting_state.c.changed_by,
                                  posting_state.c.reason)
                           .where(posting_state.c.account_id == account_id)).one()  # fmt: skip
    return row.paused, row.changed_by, row.reason


# ---- the keys


def test_fleet_brake_covers_every_account() -> None:
    kv = MemoryKV()
    brake.write(kv, Brake(scope="all", on=True, at=T, actor="telegram:1"))
    assert brake.braked(kv, RT) and brake.braked(kv, FT)


def test_go_writes_off_and_never_deletes() -> None:
    kv = MemoryKV()
    brake.write(kv, Brake(scope=RT, on=True, at=T, actor="telegram:1"))
    brake.write(kv, Brake(scope=RT, on=False, at=T + timedelta(minutes=5), actor="telegram:1"))
    assert kv.get(f"brake:{RT}") is not None and not brake.braked(kv, RT)


def test_an_unreadable_key_reads_as_braked() -> None:
    kv = MemoryKV()
    kv.put(f"brake:{RT}", "{broken")
    assert brake.braked(kv, RT)


def test_touch_all_reads_every_key() -> None:
    kv = MemoryKV()
    for scope in ("all", RT, FT):
        brake.write(kv, Brake(scope=scope, on=False, at=T, actor="telegram:1"))
    kv.put("post:x", "1")
    assert sorted(b.scope for b in brake.touch_all(kv)) == sorted(["all", RT, FT])


# ---- /pause and /go


def test_pause_writes_the_brake_first_and_survives_a_database_outage(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    posting = _posting(ctx)
    posting.repo.set_paused = _db_down  # type: ignore[method-assign]
    posting.accounts = _db_down
    reply = actions.pause(ctx, RT, True, "telegram:42", T)
    assert reply == messages.PAUSED + messages.BRAKE_ONLY
    assert brake.braked(ctx.deps.store.kv, RT) and not brake.braked(ctx.deps.store.kv, FT)
    reply = actions.pause(ctx, None, True, "telegram:42", T)  # /pause: the whole fleet
    assert reply == messages.PAUSED + messages.BRAKE_ONLY
    assert brake.braked(ctx.deps.store.kv, FT)


def test_pause_all_and_go_all(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    kv = ctx.deps.store.kv
    assert actions.pause(ctx, "all", True, "telegram:42", T) == messages.PAUSED
    assert brake.braked(kv, RT) and brake.braked(kv, FT)
    assert _row(db, RT)[0] and _row(db, FT)[0]
    assert actions.pause(ctx, "all", False, "telegram:42", T) == messages.RESUMED
    assert not brake.braked(kv, RT) and not _row(db, RT)[0]


def test_go_all_also_lifts_account_brakes(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    actions.pause(ctx, RT, True, "telegram:42", T)
    actions.pause(ctx, "all", False, "telegram:42", T + timedelta(minutes=1))
    assert not brake.braked(ctx.deps.store.kv, RT) and not _row(db, RT)[0]


def test_go_account_while_the_fleet_brake_is_on_says_still_braked(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    actions.pause(ctx, "all", True, "telegram:42", T)
    reply = actions.pause(ctx, RT, False, "telegram:42", T + timedelta(minutes=1))
    assert reply == f"{RT}: {messages.STILL_BRAKED}"
    assert brake.braked(ctx.deps.store.kv, RT)
    assert _row(db, RT)[0]  # the row keeps the effective state
    own = brake.read(ctx.deps.store.kv, RT)
    assert own is not None and own.on is False  # but the account's go is recorded


def test_pause_records_changed_by_and_reason(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    actions.pause(ctx, RT, True, "telegram:42", T, reason="travel")
    assert _row(db, RT) == (True, "telegram:42", "travel")


def test_pause_an_unknown_account_writes_no_key(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    reply = actions.pause(ctx, "nope", True, "telegram:42", T)
    assert reply == messages.unknown_account("nope", [FT, RT])
    assert ctx.deps.store.kv.get("brake:nope") is None


def test_dict_mode_pause_sets_the_brake_and_the_flag(tmp_path: Path) -> None:
    ctx = dict_ctx(tmp_path)
    assert actions.pause(ctx, None, True, f"telegram:{ALLOWED_USER}", T) == messages.PAUSED
    assert brake.braked(ctx.deps.store.kv, RT) and _posting(ctx).repo.paused(RT)


# ---- posting_daily's repair (newer wins)


@pytest.fixture
def stored(db: Database) -> AccountsRepo:
    seed(db, make_account())
    return AccountsRepo(db)


def test_a_key_newer_than_the_row_writes_the_row(db: Database, stored: AccountsRepo) -> None:
    kv = MemoryKV()
    stored.set_paused(RT, False, T, "telegram:1")
    brake.write(kv, Brake(scope=RT, on=True, at=T + timedelta(hours=1), actor="telegram:1"))
    assert repair_brakes(kv, db, T + timedelta(hours=2)) == [f"{RT}: posting_state set to paused"]
    assert _row(db, RT)[:2] == (True, "system:daily")


def test_a_go_during_an_outage_beats_an_older_paused_row(
    db: Database, stored: AccountsRepo
) -> None:
    kv = MemoryKV()
    stored.set_paused(RT, True, T, "telegram:1")
    brake.write(kv, Brake(scope=RT, on=False, at=T + timedelta(hours=1), actor="telegram:1"))
    repair_brakes(kv, db, T + timedelta(hours=2))
    assert _row(db, RT)[0] is False


def test_a_row_newer_than_the_key_rewrites_the_key(db: Database, stored: AccountsRepo) -> None:
    kv = MemoryKV()
    brake.write(kv, Brake(scope=RT, on=False, at=T, actor="telegram:1"))
    stored.set_paused(RT, True, T + timedelta(hours=1), "telegram:1")
    repair_brakes(kv, db, T + timedelta(hours=2))
    found = brake.read(kv, RT)
    assert found is not None and found.on and found.actor == "system:daily"


def test_a_missing_key_with_a_paused_row_is_restored_and_alerts(
    db: Database, stored: AccountsRepo
) -> None:
    kv, sender = MemoryKV(), FakeSender()
    ops = OpsAlerts(kv, sender, ALLOWED_USER, "UTC")
    stored.set_paused(RT, True, T, "telegram:1")
    lines = repair_brakes(kv, db, T + timedelta(hours=2), ops=ops)
    assert brake.braked(kv, RT) and any("missing brake key" in line for line in lines)
    assert any("was missing" in text for _, text, _ in sender.messages)


def test_a_missing_key_with_an_unpaused_row_does_nothing(
    db: Database, stored: AccountsRepo
) -> None:
    kv = MemoryKV()
    stored.set_paused(RT, False, T, "telegram:1")
    assert repair_brakes(kv, db, T + timedelta(hours=2)) == []
    assert brake.read(kv, RT) is None


def test_agreeing_sides_change_nothing(db: Database, stored: AccountsRepo) -> None:
    kv = MemoryKV()
    brake.write(kv, Brake(scope="all", on=True, at=T, actor="telegram:1"))
    stored.set_paused(RT, True, T, "telegram:1")
    assert repair_brakes(kv, db, T + timedelta(hours=2)) == []


def test_a_newer_go_row_under_the_fleet_brake_converges_to_paused_and_alerts(
    db: Database, stored: AccountsRepo
) -> None:
    # PR review: writing only the account key can't lift /pause all, so the repair would loop
    kv, sender = MemoryKV(), FakeSender()
    ops = OpsAlerts(kv, sender, ALLOWED_USER, "UTC")
    brake.write(kv, Brake(scope="all", on=True, at=T, actor="telegram:1"))
    stored.set_paused(RT, False, T + timedelta(hours=1), "cli:mat")  # e.g. S1's /go on rollback
    lines = repair_brakes(kv, db, T + timedelta(hours=2), ops=ops)
    assert lines == [f"{RT}: posting_state set to paused (/pause all is on)"]
    assert _row(db, RT)[:2] == (True, "system:daily")
    assert any("send /go all" in text for _, text, _ in sender.messages)
    assert repair_brakes(kv, db, T + timedelta(days=1, hours=2)) == []  # converged

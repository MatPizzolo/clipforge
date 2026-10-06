import pytest
from sqlalchemy import text

from clipforge.db.engine import Database
from clipforge.hooks.freezer import HookFreezer, NoHookFreezer
from clipforge.hooks.library import HookError, HookLibrary, SqlHookFreezer
from tests.hooks.helpers import (
    NOW,
    approved,
    last_event,
    open_freeze_count,
)


def test_both_freezers_satisfy_the_protocol(lib: HookLibrary) -> None:
    freezers: list[HookFreezer] = [NoHookFreezer(), SqlHookFreezer(lib)]
    assert len(freezers) == 2


def test_freeze_snapshots_and_edits_apply_at_release(lib: HookLibrary, db: Database) -> None:
    p = approved(lib)
    freezer = SqlHookFreezer(lib)
    with db.begin() as conn:
        freezer.freeze(conn, "realtalk-clips-en", 1)
    lib.set_weight("realtalk-clips-en", p.id, 3.0, "try more", "web:mat", NOW)  # saved...
    r = lib.rotation_for("realtalk-clips-en", "clips")
    assert r.frozen_by == 1 and r.entries[0].weight == 1.0  # ...not applied
    assert lib.open_freeze("realtalk-clips-en") == r
    with db.begin() as conn:
        freezer.release(conn, "realtalk-clips-en", 1)
    r = lib.rotation_for("realtalk-clips-en", "clips")
    assert r.frozen_by is None and r.entries[0].weight == 3.0


def test_freeze_is_idempotent_and_rolls_back_with_the_caller(
    lib: HookLibrary, db: Database
) -> None:
    approved(lib)
    freezer = SqlHookFreezer(lib)
    with db.begin() as conn:
        freezer.freeze(conn, "realtalk-clips-en", 1)
        freezer.freeze(conn, "realtalk-clips-en", 1)
    assert open_freeze_count(db) == 1
    with pytest.raises(RuntimeError), db.begin() as conn:
        freezer.release(conn, "realtalk-clips-en", 1)
        raise RuntimeError("the experiment's own write failed")
    assert open_freeze_count(db) == 1  # the release rolled back with the caller
    with db.begin() as conn:
        freezer.release(conn, "realtalk-clips-en", 1)
        freezer.release(conn, "realtalk-clips-en", 1)  # no-op
    assert open_freeze_count(db) == 0
    with db.begin() as conn:
        assert conn.execute(text("select count(*) from hook_events where kind = 'released'")
                            ).scalar_one() == 1  # fmt: skip


def test_a_second_experiment_cant_freeze_over_the_first(lib: HookLibrary, db: Database) -> None:
    approved(lib)
    freezer = SqlHookFreezer(lib)
    with db.begin() as conn:
        freezer.freeze(conn, "realtalk-clips-en", 1)
    with pytest.raises(HookError, match="experiment 1"), db.begin() as conn:
        freezer.freeze(conn, "realtalk-clips-en", 2)


def test_freeze_is_a_no_op_without_a_library(lib: HookLibrary, db: Database) -> None:
    with db.begin() as conn:
        SqlHookFreezer(lib).freeze(conn, "realtalk-clips-en", 1)  # no hook_weights rows yet
    assert open_freeze_count(db) == 0


def test_freeze_events_use_the_system_actor(lib: HookLibrary, db: Database) -> None:
    approved(lib)
    with db.begin() as conn:
        SqlHookFreezer(lib).freeze(conn, "realtalk-clips-en", 1)
    ev = last_event(db, "frozen")
    assert ev.actor == "system:experiment" and ev.data["experiment_id"] == 1

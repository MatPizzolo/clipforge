"""The hook tables' constraints (migration 0003, hooks spec §3.1)."""

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from clipforge.db.engine import Database
from tests.dbhelpers import insert_account, insert_item

ITEM = "20261003-aaaaaaaa-0001:clip_01"
RATE = text("insert into hook_ratings (item_id, rating, actor, at) values (:i, :r, :a, now())")


def _pattern(
    conn: Connection,
    pid: str = "hp_aaaaaaaa",
    account: str | None = "realtalk-clips-en",
    blueprint: str | None = None,
) -> None:
    conn.execute(text("insert into hook_patterns (id, account_id, blueprint_name, status,"
                      " current_version, control, created_at, updated_at) values"
                      " (:id, :a, :b, 'approved', 1, false, now(), now())"),
                 {"id": pid, "a": account, "b": blueprint})  # fmt: skip
    conn.execute(text("insert into hook_pattern_versions (pattern_id, n, data, author,"
                      " created_at) values (:id, 1, '{}', 'system:migration', now())"),
                 {"id": pid})  # fmt: skip


def test_versions_and_events_are_append_only(db: Database) -> None:
    insert_account(db, "realtalk-clips-en")
    with db.begin() as conn:
        _pattern(conn)
        conn.execute(text("insert into hook_events (at, actor, kind, data) values"
                          " (now(), 'system:migration', 'seeded', '{}')"))  # fmt: skip
    for statement in ("update hook_pattern_versions set author = 'cli:x'",
                      "delete from hook_pattern_versions",
                      "update hook_events set kind = 'x'", "delete from hook_events"):  # fmt: skip
        with pytest.raises(DBAPIError, match="append-only"), db.begin() as conn:
            conn.execute(text(statement))


def test_pattern_scope_is_exactly_one(db: Database) -> None:
    insert_account(db, "realtalk-clips-en")
    for account, blueprint in (("realtalk-clips-en", "realtalk-clips"), (None, None)):
        with pytest.raises(IntegrityError), db.begin() as conn:
            _pattern(conn, account=account, blueprint=blueprint)
    with db.begin() as conn:
        _pattern(conn, account=None, blueprint="realtalk-clips")


def test_pattern_status_is_checked(db: Database) -> None:
    insert_account(db, "realtalk-clips-en")
    with db.begin() as conn:
        _pattern(conn)
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(text("update hook_patterns set status = 'live'"))


def test_one_open_freeze_per_account(db: Database) -> None:
    insert_account(db, "realtalk-clips-en")
    insert = text("insert into hook_freezes (account_id, experiment_id, rotation, frozen_at,"
                  " frozen_by) values ('realtalk-clips-en', :e, '{}', now(),"
                  " 'system:experiment')")  # fmt: skip
    with db.begin() as conn:
        conn.execute(insert, {"e": 1})
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(insert, {"e": 2})
    with db.begin() as conn:  # released, a new one can open
        conn.execute(text("update hook_freezes set released_at = now(),"
                          " released_by = 'system:experiment'"))  # fmt: skip
        conn.execute(insert, {"e": 2})


@pytest.mark.parametrize(("rating", "actor"), [(2, "web:mat"), (0, "web:mat"), (1, "nobody")])
def test_rating_is_plus_or_minus_one_and_actor_checked(
    db: Database, rating: int, actor: str
) -> None:
    insert_account(db, "realtalk-clips-en")
    insert_item(db, ITEM)
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(RATE, {"i": ITEM, "r": rating, "a": actor})
    with db.begin() as conn:  # the valid row goes in
        conn.execute(RATE, {"i": ITEM, "r": -1, "a": "web:mat"})


@pytest.mark.parametrize("statement", [
    "insert into hook_weights (account_id, pattern_id, weight, updated_by, updated_at)"
    " values ('realtalk-clips-en', 'hp_aaaaaaaa', -1, 'web:mat', now())",
    "insert into hook_weights (account_id, pattern_id, weight, updated_by, updated_at)"
    " values ('realtalk-clips-en', 'hp_aaaaaaaa', 1, 'nobody', now())",
    "insert into hook_events (at, actor, kind, data) values (now(), 'nobody', 'x', '{}')",
    "insert into hook_pattern_versions (pattern_id, n, data, author, created_at)"
    " values ('hp_aaaaaaaa', 2, '{}', 'system:', now())",
])  # fmt: skip
def test_weights_and_actors_are_checked(db: Database, statement: str) -> None:
    insert_account(db, "realtalk-clips-en")
    with db.begin() as conn:
        _pattern(conn)
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(text(statement))


def test_item_stamp_fk_to_the_version(db: Database) -> None:
    insert_account(db, "realtalk-clips-en")
    insert_item(db, ITEM)
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(text("update content_items set hook_pattern_id = 'hp_missing',"
                          " hook_version = 1 where id = :i"), {"i": ITEM})  # fmt: skip
    with db.begin() as conn:
        _pattern(conn)
        conn.execute(text("update content_items set hook_pattern_id = 'hp_aaaaaaaa',"
                          " hook_version = 1 where id = :i"), {"i": ITEM})  # fmt: skip


def test_superseded_by_is_an_item(db: Database) -> None:
    insert_account(db, "realtalk-clips-en")
    insert_item(db, ITEM)
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(text("update content_items set superseded_by = 'nope'"))

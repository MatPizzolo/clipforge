import re
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from clipforge.db.engine import make_engine
from clipforge.db.migrations import downgrade, upgrade
from clipforge.db.tables import metadata

TABLES = {"accounts", "posting_state", "sources", "source_events", "jobs", "content_items",
          "assets", "posts", "sends", "post_events", "costs"}  # fmt: skip


def test_round_trip(pg_url: str) -> None:
    downgrade(pg_url, "base")
    assert TABLES.isdisjoint(inspect(make_engine(pg_url)).get_table_names())
    upgrade(pg_url)
    assert set(inspect(make_engine(pg_url)).get_table_names()) >= TABLES


def test_tables_match_the_migrations(pg_url: str) -> None:
    upgrade(pg_url)
    with make_engine(pg_url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diff == []


def test_every_revision_is_frozen() -> None:
    # explicit DDL only: later edits to db/tables.py never change what a revision builds
    revisions = sorted((Path(__file__).parents[2] / "alembic/versions").glob("0*.py"))
    assert [p.name[:4] for p in revisions] == ["0001", "0002"]
    for path in revisions:
        text_ = path.read_text()
        assert not re.search(r"\bmetadata\b", text_) and "clipforge.db.tables" not in text_, path


def test_check_constraints_match_0002() -> None:
    # autogenerate doesn't compare CHECK constraints: pin tables.py's strings to 0002's
    import importlib.util

    from clipforge.actors import ACTOR
    from clipforge.db import tables

    path = Path(__file__).parents[2] / "alembic/versions/0002_s2.py"
    spec = importlib.util.spec_from_file_location("rev0002", path)
    assert spec is not None and spec.loader is not None
    rev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rev)
    assert tables.ACTOR_CHECK == rev.ACTOR_CHECK
    named = {c.name: str(c.sqltext) for t in tables.metadata.sorted_tables
             for c in t.constraints if c.name and c.name.startswith("ck_")}  # fmt: skip
    assert named["ck_autopilot_preset"].replace(" ", "") == rev._in("preset", rev.PRESETS).replace(
        " ", ""
    )
    assert named["ck_autopilot_review_dial"].replace(" ", "") == rev._in(
        "review_dial", rev.DIALS
    ).replace(" ", "")
    assert tables.POST_STATES_SQL.replace(" ", "") == rev._in("state", rev.POST_STATES).replace(
        " ", ""
    )
    assert f"^({ACTOR.pattern.replace('(?:', '(')})$" == rev.ACTOR_RE


def test_env_requires_the_unpooled_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic.config import Config

    from alembic import command
    from clipforge.db.migrations import ALEMBIC_INI

    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x-pooler.example/db")
    with pytest.raises(SystemExit, match="DATABASE_URL_UNPOOLED"):
        command.upgrade(Config(str(ALEMBIC_INI)), "head")


def test_a_failed_migration_exits_without_the_host_or_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # security review minor 2: CI logs only mask the whole secret, not the host inside it
    from alembic.config import Config

    from alembic import command
    from clipforge.db.migrations import ALEMBIC_INI

    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://neondb_owner:s3cret@127.0.0.1:1/db")
    with pytest.raises(SystemExit) as caught:
        command.upgrade(Config(str(ALEMBIC_INI)), "head")
    text = str(caught.value)
    assert text.startswith("migration failed: ")
    for secret in ("127.0.0.1", "neondb_owner", "s3cret"):
        assert secret not in text, secret


# ---- 0002 (card 014, plan Task 2)

import itertools  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from contextlib import contextmanager  # noqa: E402

from sqlalchemy import Connection, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from clipforge.db.doctor import EXPECTED_HEAD  # noqa: E402
from clipforge.db.engine import Database  # noqa: E402

_SCHEMAS = itertools.count()

ACCOUNT_SQL = ("insert into accounts (id, blueprint, blueprint_version, kind, language, niche,"
               " review_tier, monthly_budget_usd, platforms, brand, posting, created_at,"
               " updated_at) values ('{id}', 'b', 1, '{kind}', 'en', 'n', 'review', {budget},"
               " '{{}}', '{{}}', '{{}}', now(), now())")  # fmt: skip
ITEM_SQL = ("insert into content_items (id, account_id, producer, producer_version, language,"
            " media_kind, image_paths, title, hook, score, credits, ai_disclosure, sponsored,"
            " cost_usd, queued_at) values ('i', 'realtalk-clips-en', 'clips', 'v', 'en', 'video',"
            " '[]', 't', 'h', 0.9, '[]', false, false, 0, now())")  # fmt: skip


@contextmanager
def throwaway_schema(pg_url: str) -> Iterator[tuple[str, Connection]]:
    """A fresh schema at revision 0001; yields its name and a connection searching it."""
    name = f"s2test_{next(_SCHEMAS)}_{id(object())}"
    engine = make_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{name}"'))
    try:
        upgrade(pg_url, "0001", schema=name)
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{name}"'))
            yield name, conn
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        engine.dispose()


def _in_schema(pg_url: str, name: str, sql: str) -> list[tuple[object, ...]]:
    engine = make_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{name}"'))
            return [tuple(row) for row in conn.execute(text(sql))]
    finally:
        engine.dispose()


def test_head_is_0002(db: Database) -> None:
    assert EXPECTED_HEAD == "0002"
    with db.begin() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == "0002"


def test_0002_backfills_actor_and_seeds_hands_on(pg_url: str) -> None:
    with throwaway_schema(pg_url) as (name, conn):
        conn.execute(text(ACCOUNT_SQL.format(id="realtalk-clips-en", kind="clips", budget=0)))
        conn.execute(text(ACCOUNT_SQL.format(id="avatar-en", kind="avatar", budget=0)))
        conn.execute(text(ACCOUNT_SQL.format(id="story-en", kind="story", budget=7.5)))
        conn.execute(text(ITEM_SQL))
        conn.execute(text("insert into post_events (item_id, kind, at, data) values"
                          " ('i', 'posted', now(), '{\"actor\": \"telegram:42\"}'),"
                          " ('i', 'sent', now(), '{\"n\": 1}'),"
                          " ('i', 'skipped', now(), '{\"actor\": \"nobody\"}')"))  # fmt: skip
        conn.commit()
        upgrade(pg_url, "0002", schema=name)
        actors = _in_schema(pg_url, name, "select kind, actor from post_events order by id")
        assert actors == [("posted", "telegram:42"), ("sent", None), ("skipped", None)]
        seeded = _in_schema(pg_url, name, "select account_id, preset, review_dial, publish,"
                            " produce, scale, monthly_cap_usd, updated_by from autopilot"
                            " order by account_id")  # fmt: skip
        assert seeded == [
            ("avatar-en", "hands_on", "review", True, False, False, 20.0, "system:migration"),
            ("realtalk-clips-en", "hands_on", "review", True, False, False, 5.0,
             "system:migration"),
            ("story-en", "hands_on", "review", True, False, False, 7.5, "system:migration"),
        ]  # fmt: skip
        events = _in_schema(pg_url, name, "select field, from_value, to_value, actor"
                            " from autopilot_events")  # fmt: skip
        assert events == [("preset", None, "hands_on", "system:migration")] * 3
        states = _in_schema(pg_url, name, "select count(*) from posts where state <> 'pending'")
        assert states == [(0,)]


def test_0002_downgrade_and_upgrade_on_a_throwaway_schema(pg_url: str) -> None:
    with throwaway_schema(pg_url) as (name, conn):
        conn.commit()
        upgrade(pg_url, "0002", schema=name)
        downgrade(pg_url, "0001", schema=name)
        tables = {r[0] for r in _in_schema(pg_url, name, "select tablename from pg_tables"
                                           f" where schemaname = '{name}'")}  # fmt: skip
        assert "autopilot" not in tables and "posts" in tables
        upgrade(pg_url, "head", schema=name)
        engine = make_engine(pg_url)
        try:
            with engine.connect() as c:
                c.execute(text(f'SET search_path TO "{name}"'))
                c.commit()
                diff = compare_metadata(MigrationContext.configure(c), metadata)
        finally:
            engine.dispose()
        assert diff == []


def test_autopilot_events_are_append_only(db: Database) -> None:
    with db.begin() as conn:
        conn.execute(text(ACCOUNT_SQL.format(id="a", kind="clips", budget=0)))
        conn.execute(
            text(
                "insert into autopilot_events (account_id, at, actor, field, to_value)"
                " values ('a', now(), 'system:migration', 'preset', 'hands_on')"
            )
        )
    for statement in ("update autopilot_events set to_value = 'x'", "delete from autopilot_events"):
        with pytest.raises(DBAPIError, match="append-only"), db.begin() as conn:
            conn.execute(text(statement))


@pytest.mark.parametrize("actor", ["nobody", "system:", "telegram:x", "web:" + "a" * 40])
def test_post_events_actor_check(db: Database, actor: str) -> None:
    with db.begin() as conn:
        conn.execute(text(ACCOUNT_SQL.format(id="realtalk-clips-en", kind="clips", budget=0)))
        conn.execute(text(ITEM_SQL))
    with pytest.raises(DBAPIError), db.begin() as conn:
        conn.execute(text("insert into post_events (item_id, kind, at, data, actor) values"
                          " ('i', 'x', now(), '{}', :actor)"), {"actor": actor})  # fmt: skip


def test_posts_state_check(db: Database) -> None:
    with db.begin() as conn:
        conn.execute(text(ACCOUNT_SQL.format(id="realtalk-clips-en", kind="clips", budget=0)))
        conn.execute(text(ITEM_SQL))
        conn.execute(text("insert into posts (item_id, platform) values ('i', 'tiktok')"))
        assert conn.execute(text("select state, attempts from posts")).one() == ("pending", 0)
    with pytest.raises(DBAPIError), db.begin() as conn:
        conn.execute(text("update posts set state = 'fallback'"))  # ADR-54: final_failed


@pytest.mark.parametrize("statement", [
    "update autopilot set preset = 'bogus'",
    "update autopilot set review_dial = 'sometimes'",
    "update autopilot set updated_by = 'nobody'",
    "update posting_state set changed_by = 'nobody'",
])  # fmt: skip
def test_autopilot_and_posting_state_checks(db: Database, statement: str) -> None:
    from clipforge.db.accounts import AccountsRepo
    from clipforge.models import hands_on
    from tests.dbhelpers import NOW, make_account

    account = make_account()
    AccountsRepo(db).create(account, NOW, autopilot=hands_on(account), actor="cli:mat")
    with db.begin() as conn:  # the allowed values pass
        conn.execute(text("update autopilot set preset = 'custom', review_dial = 'auto'"))
        conn.execute(text("update posting_state set changed_by = 'telegram:42'"))
    with pytest.raises(DBAPIError), db.begin() as conn:
        conn.execute(text(statement))


def test_links_item_id_is_a_foreign_key(db: Database) -> None:
    with db.begin() as conn:
        conn.execute(text(ACCOUNT_SQL.format(id="realtalk-clips-en", kind="clips", budget=0)))
        conn.execute(text("insert into links (slug, target_url, account_id, kind, sub_param,"
                          " created_at, created_by) values ('bio00001', 'https://x.example',"
                          " 'realtalk-clips-en', 'bio', 'subid', now(), 'cli:mat')"))  # fmt: skip
    with pytest.raises(DBAPIError), db.begin() as conn:
        conn.execute(text("update links set item_id = 'no-such-item'"))

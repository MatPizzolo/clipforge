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


def test_0001_is_frozen() -> None:
    text_ = (Path(__file__).parents[2] / "alembic/versions/0001_initial.py").read_text()
    assert not re.search(r"\bmetadata\b", text_) and "clipforge.db.tables" not in text_


def test_env_requires_the_unpooled_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic.config import Config

    from alembic import command
    from clipforge.db.migrations import ALEMBIC_INI

    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x-pooler.example/db")
    with pytest.raises(SystemExit, match="DATABASE_URL_UNPOOLED"):
        command.upgrade(Config(str(ALEMBIC_INI)), "head")

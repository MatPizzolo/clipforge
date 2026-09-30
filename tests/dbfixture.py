"""Postgres for tests: TEST_DATABASE_URL (CI's service container) or a throwaway container
(Docker Desktop). Never skips: a missing database is a failure with the fix in the message."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from clipforge.db.engine import Database, make_engine
from clipforge.db.migrations import upgrade
from clipforge.db.tables import metadata

NO_DATABASE = "start Docker Desktop (WSL integration) or set TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL")
    container = None
    if not url:
        try:
            from testcontainers.community.postgres import PostgresContainer

            container = PostgresContainer("postgres:17-alpine", driver="psycopg")
            container.start()
        except Exception as exc:  # docker missing, daemon down, image pull failed
            pytest.fail(f"{NO_DATABASE} ({type(exc).__name__})", pytrace=False)
        url = container.get_connection_url()
    upgrade(url)
    yield url
    if container is not None:
        container.stop()


@pytest.fixture
def db(pg_url: str) -> Iterator[Database]:
    database = Database(make_engine(pg_url, pool_size=1))
    names = ", ".join(table.name for table in reversed(metadata.sorted_tables))
    with database.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield database
    database.dispose()

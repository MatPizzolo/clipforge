"""Alembic environment. URL: config.attributes["url"] (tests), else DATABASE_URL_UNPOOLED.
DDL needs Neon's direct endpoint, so there is no fallback to the pooled DATABASE_URL (PgBouncer's
transaction mode breaks session-level migration locks). Never printed."""

from __future__ import annotations

import os

from sqlalchemy import pool

from alembic import context
from clipforge.db.engine import is_db_error, make_engine, redact
from clipforge.db.tables import metadata

config = context.config


def _url() -> str:
    url = config.attributes.get("url") or os.environ.get("DATABASE_URL_UNPOOLED")
    if not url:
        raise SystemExit(
            "set DATABASE_URL_UNPOOLED (Neon's direct endpoint); migrations never use the "
            "pooled DATABASE_URL"
        )
    return str(url)


def run() -> None:
    engine = make_engine(_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()
    except Exception as exc:
        if not is_db_error(exc):
            raise
        # a driver error names the host, address and user; CI logs only mask whole secrets
        raise SystemExit(f"migration failed: {redact(exc)}") from None
    finally:
        engine.dispose()


run()

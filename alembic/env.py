"""Alembic environment. URL: config.attributes["url"] (tests), else DATABASE_URL_UNPOOLED.
DDL needs Neon's direct endpoint, so there is no fallback to the pooled DATABASE_URL (PgBouncer's
transaction mode breaks session-level migration locks). Never printed."""

from __future__ import annotations

import os

from sqlalchemy import pool, text

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
            # fail fast instead of queueing every app query behind an ALTER that waits for a
            # long reader (posting_daily's snapshot); a failed migration is simply re-run
            connection.execute(text("SET lock_timeout = '5s'"))
            # and a ceiling on any one statement (the backfill and CHECK validations included)
            connection.execute(text("SET statement_timeout = '60s'"))
            connection.commit()
            schema = config.attributes.get("schema")
            if schema is not None:  # tests: a throwaway schema (db/migrations.upgrade)
                if not str(schema).isidentifier():
                    raise SystemExit("schema must be a plain identifier")
                connection.execute(text(f'SET search_path TO "{schema}"'))
                connection.commit()
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

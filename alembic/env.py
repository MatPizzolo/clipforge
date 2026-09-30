"""Alembic environment. URL: config.attributes["url"] (tests), else DATABASE_URL_UNPOOLED
(Neon recommends the direct endpoint for DDL), else DATABASE_URL. Never printed."""

from __future__ import annotations

import os

from sqlalchemy import pool

from alembic import context
from clipforge.db.engine import make_engine
from clipforge.db.tables import metadata

config = context.config


def _url() -> str:
    url = (
        config.attributes.get("url")
        or os.environ.get("DATABASE_URL_UNPOOLED")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise SystemExit("set DATABASE_URL_UNPOOLED or DATABASE_URL")
    return str(url)


def run() -> None:
    engine = make_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run()

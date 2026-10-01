"""One engine per container over Neon's pooled endpoint (PgBouncer, transaction mode)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import Connection, Engine, Pool, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from clipforge.sanitize import redact

if TYPE_CHECKING:
    from clipforge.config import Settings

__all__ = [
    "Database",
    "DatabaseUnavailable",
    "database_from_settings",
    "is_db_error",
    "make_engine",
    "redact",
]


STATEMENT_TIMEOUT = "5s"


class DatabaseUnavailable(RuntimeError):
    """No database configured, or it can't be reached. The message is safe to show."""


def is_db_error(exc: BaseException) -> bool:
    """A database error, whose message and traceback can carry the URL: log `redact(exc)` only."""
    return isinstance(exc, (SQLAlchemyError, DatabaseUnavailable))


def make_engine(url: str, *, pool_size: int = 2, poolclass: type[Pool] | None = None) -> Engine:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix) :]
    options: dict[str, object] = {
        "pool_pre_ping": True,
        "hide_parameters": True,  # bound values never appear in error messages
        # PgBouncer transaction mode can't keep server-side prepared statements; Neon's
        # scale-to-zero wake-up takes about 0.5-1 s, so 3 s
        # is enough and a down database never holds a step for long.
        "connect_args": {"prepare_threshold": None, "connect_timeout": 3},
    }
    if poolclass is not None:
        options["poolclass"] = poolclass
    else:
        options.update(pool_size=pool_size, max_overflow=2)
    return create_engine(url, **options)


class Database:
    def __init__(self, engine: Engine, statement_timeout: str = STATEMENT_TIMEOUT) -> None:
        if not re.fullmatch(r"\d{1,4}(ms|s|min)", statement_timeout):
            raise ValueError("statement_timeout must look like 5s, 500ms or 2min")
        self.engine = engine
        self.statement_timeout = statement_timeout

    def with_timeout(self, statement_timeout: str) -> Database:
        """The same engine (and pool) with another per-statement cap, for batch work such as
        posting_daily's whole-table reads (migration review I1)."""
        return Database(self.engine, statement_timeout)

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        """One transaction. Every statement in it is capped (5 s by default; SET LOCAL lasts
        only for the transaction, so it is safe through PgBouncer's transaction mode): a slow
        Neon never holds a tap or a tick for long (card 002 A4). Migrations don't use this."""
        with self.engine.begin() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = '{self.statement_timeout}'"))
            yield conn

    def dispose(self) -> None:
        self.engine.dispose()

    def __repr__(self) -> str:
        return "Database(<redacted>)"


def database_from_settings(settings: Settings) -> Database | None:
    if settings.database_url is None:
        return None
    return Database(make_engine(settings.database_url.get_secret_value()))

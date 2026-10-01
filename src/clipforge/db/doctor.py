"""Read-only database check for the rollout (`modal run src/clipforge/app.py::db_doctor`).

It connects once, reads `alembic_version` inside a READ ONLY transaction and reports whether
the URL is Neon's pooled endpoint. It never writes and never reports the URL or host.
"""

from __future__ import annotations

import time
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.engine import make_url

from clipforge.db.engine import Database, is_db_error
from clipforge.sanitize import redact

# The newest revision in alembic/versions/. The Modal image has no alembic/ directory, so the
# code carries it; tests/db/test_doctor.py fails when a new revision isn't reflected here.
EXPECTED_HEAD = "0001"


class DbReport(TypedDict):
    configured: bool
    pooled: bool | None
    connect_ms: int | None
    revision: str | None
    expected: str
    ok: bool
    error: str | None


def is_pooled(url: str) -> bool:
    """Neon's pooled endpoint has `-pooler` in its host name (runbook §4a)."""
    try:
        host = make_url(url).host or ""
    except Exception:  # a malformed URL is not pooled; the connect reports the real error
        return False
    return "-pooler" in host


def check(db: Database | None, url: str | None) -> DbReport:
    report: DbReport = {
        "configured": db is not None,
        "pooled": None if url is None else is_pooled(url),
        "connect_ms": None,
        "revision": None,
        "expected": EXPECTED_HEAD,
        "ok": False,
        "error": None,
    }
    if db is None:
        report["error"] = "DATABASE_URL is not configured"
        return report
    started = time.monotonic()
    try:
        with db.engine.connect() as conn:
            report["connect_ms"] = round((time.monotonic() - started) * 1000)
            conn.execute(text("SET TRANSACTION READ ONLY"))
            exists = conn.execute(text("SELECT to_regclass('alembic_version')")).scalar()
            if exists is not None:
                report["revision"] = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
            conn.rollback()
    except Exception as exc:
        if not is_db_error(exc):
            raise
        report["error"] = redact(exc)
        return report
    report["ok"] = report["revision"] == EXPECTED_HEAD
    if not report["ok"]:
        report["error"] = f"alembic_version is {report['revision']!r}, expected {EXPECTED_HEAD!r}"
    return report

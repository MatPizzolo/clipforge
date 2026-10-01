import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text

from clipforge.db import doctor
from clipforge.db.engine import Database, make_engine
from clipforge.db.migrations import alembic_config

POOLED = "postgresql://owner:s3cret@ep-cool-1234-pooler.us-east-2.aws.neon.tech/neondb"
DIRECT = "postgresql://owner:s3cret@ep-cool-1234.us-east-2.aws.neon.tech/neondb"


def test_expected_head_is_the_newest_revision() -> None:
    head = ScriptDirectory.from_config(alembic_config("postgresql://unused")).get_current_head()
    assert head == doctor.EXPECTED_HEAD


def test_pooled_host() -> None:
    assert doctor.is_pooled(POOLED)
    assert not doctor.is_pooled(DIRECT)
    assert not doctor.is_pooled("not a url")


def test_not_configured() -> None:
    report = doctor.check(None, None)
    assert report["ok"] is False and report["configured"] is False
    assert report["error"] == "DATABASE_URL is not configured"


def test_migrated_database_is_ok(db: Database, pg_url: str) -> None:
    report = doctor.check(db, pg_url)
    assert report["ok"] is True, report
    assert report["revision"] == doctor.EXPECTED_HEAD
    assert report["connect_ms"] is not None and report["pooled"] is False


def test_reports_a_wrong_revision_without_writing(pg_url: str) -> None:
    database = Database(make_engine(pg_url, pool_size=1))
    with database.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'old'"))
    try:
        report = doctor.check(database, pg_url)
        assert report["ok"] is False and report["revision"] == "old"
        assert "expected" in (report["error"] or "")
    finally:
        with database.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :v"),
                         {"v": doctor.EXPECTED_HEAD})  # fmt: skip
        database.dispose()


def test_read_only_transaction(db: Database) -> None:
    # The same session settings as check(): a write inside it fails.
    with db.engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        with pytest.raises(Exception, match="read-only"):
            conn.execute(text("CREATE TABLE doctor_probe (x int)"))
        conn.rollback()


def test_unreachable_database_is_redacted() -> None:
    url = "postgresql://owner:s3cret@127.0.0.1:1/neondb"
    report = doctor.check(Database(make_engine(url)), url)
    assert report["ok"] is False and report["error"]
    assert "s3cret" not in report["error"] and "127.0.0.1" not in report["error"]


def test_a_direct_url_in_the_secret_is_not_ok(db: Database, pg_url: str) -> None:
    # migration review minor: the app must use Neon's pooled endpoint (PgBouncer)
    report = doctor.check(db, pg_url, require_pooled=True)  # the test URL isn't pooled
    assert report["ok"] is False and "pooled" in (report["error"] or "")

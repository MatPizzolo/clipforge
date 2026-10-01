from pathlib import Path

from sqlalchemy import text

from clipforge.config import Settings
from clipforge.db.engine import Database, database_from_settings, make_engine, redact

URL = "postgresql://owner:s3cret@ep-cool-1234-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"


def test_redact_hides_url_host_and_password() -> None:
    exc = RuntimeError(f'connection to server at "ep-cool-1234-pooler.us-east-2.aws.neon.tech" '
                       f"failed: password=s3cret {URL}")  # fmt: skip
    text_ = redact(exc)
    assert text_.startswith("RuntimeError: ")
    for secret in ("s3cret", "neon.tech", "owner:", "ep-cool"):
        assert secret not in text_
    assert len(text_) <= 200


def test_driver_prefix_and_repr() -> None:
    engine = make_engine(URL)
    assert engine.url.drivername == "postgresql+psycopg"
    database = Database(engine)
    assert "s3cret" not in repr(database) and "neon" not in repr(database)


def test_database_from_settings(tmp_path: Path) -> None:
    off = Settings(_env_file=None, jobs_root=tmp_path)  # type: ignore[call-arg]
    assert database_from_settings(off) is None
    on = Settings(_env_file=None, jobs_root=tmp_path, database_url=URL)  # type: ignore[call-arg]
    assert database_from_settings(on) is not None


def test_connects(db: Database) -> None:
    with db.begin() as conn:
        assert conn.execute(text("select 1")).scalar_one() == 1


def test_redact_hides_any_host_and_ip_addresses() -> None:
    exc = RuntimeError(
        'connection to server at "db.example.com" (10.1.2.3), port 5432 failed: '
        'connection to server at "::1", port 5432 failed; peer (2001:db8::8a2e:370:7334)'
    )
    text_ = redact(exc)
    assert text_.startswith("RuntimeError: ")
    for secret in ("example.com", "10.1.2.3", "::1", "2001:db8", "370:7334"):
        assert secret not in text_


def test_redact_hides_the_quoted_user_name() -> None:
    for message in (
        'connection failed: connection to server at "1.2.3.4", port 5432 failed: FATAL:  '
        'password authentication failed for user "neondb_owner"',
        'FATAL:  role "neondb_owner" does not exist',
    ):
        text_ = redact(Exception(message))
        assert "neondb_owner" not in text_ and "1.2.3.4" not in text_


def test_every_transaction_has_a_statement_timeout(db: Database) -> None:
    # card 002 A4: a slow Neon never holds a tap or a tick for long
    with db.begin() as conn:
        assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "5s"
    with db.engine.connect() as conn:  # SET LOCAL ends with the transaction
        assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "0"

from sqlalchemy import text

from clipforge.db.engine import Database


def test_database_is_migrated_and_empty(db: Database) -> None:
    with db.begin() as conn:
        assert conn.execute(text("select count(*) from accounts")).scalar_one() == 0

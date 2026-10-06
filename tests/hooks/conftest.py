import pytest

from clipforge.db.engine import Database
from clipforge.hooks.library import HookLibrary
from tests.dbhelpers import insert_account


@pytest.fixture
def lib(db: Database) -> HookLibrary:
    insert_account(db, "realtalk-clips-en", blueprint="realtalk-clips")
    return HookLibrary(db)

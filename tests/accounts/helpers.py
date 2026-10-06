"""Accounts for autopilot tests."""

from __future__ import annotations

from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import Account, hands_on
from tests.dbhelpers import NOW
from tests.dbhelpers import make_account as account_of


def make_account(
    db: Database, *, insert_autopilot: bool = True, id: str = "realtalk-clips-en"
) -> Account:
    """realtalk-clips-en in the database, with its Hands-on autopilot row (as account create
    writes it) unless `insert_autopilot` is False (an account from before 0002)."""
    account = account_of(id)
    seed = hands_on(account).model_copy(update={"updated_by": "cli:mat", "updated_at": NOW})
    AccountsRepo(db).create(account, NOW, autopilot=seed if insert_autopilot else None,
                            actor="cli:mat")  # fmt: skip
    return account

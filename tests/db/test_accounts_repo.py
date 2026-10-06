import pytest

from clipforge.db.accounts import AccountExists, AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import Platform, PlatformProfile
from tests.dbhelpers import NOW, make_account


def test_create_get_list_update_round_trip(db: Database) -> None:
    repo = AccountsRepo(db)
    account = make_account(chat_id=42)
    repo.create(account, NOW)
    assert repo.get(account.id) == account and repo.list() == [account]
    renamed = account.model_copy(
        update={
            "platforms": {**account.platforms, Platform.TIKTOK: PlatformProfile(handle="new.name")}
        }
    )
    repo.update(renamed, NOW)
    assert repo.get(account.id).platforms[Platform.TIKTOK].handle == "new.name"  # type: ignore[union-attr]
    assert repo.get("nope") is None
    with pytest.raises(AccountExists):
        repo.create(account, NOW)


def test_pause_is_runtime_state_not_config(db: Database) -> None:
    repo = AccountsRepo(db)
    account = make_account()
    repo.create(account, NOW)
    assert repo.paused(account.id) is False
    repo.set_paused(account.id, True, NOW)
    repo.update(account, NOW)  # an account edit never touches the pause
    assert repo.paused(account.id) is True


def test_create_with_a_bad_seed_actor_is_not_an_existing_account(db: Database) -> None:
    from clipforge.models import hands_on

    account = make_account()
    with pytest.raises(ValueError, match="not an actor") as caught:
        AccountsRepo(db).create(account, NOW, autopilot=hands_on(account), actor="api")
    assert not isinstance(caught.value, AccountExists)
    assert AccountsRepo(db).get(account.id) is None  # nothing was written
    AccountsRepo(db).create(account, NOW, autopilot=hands_on(account), actor="cli:mat")
    with pytest.raises(AccountExists):
        AccountsRepo(db).create(account, NOW, autopilot=hands_on(account), actor="cli:mat")

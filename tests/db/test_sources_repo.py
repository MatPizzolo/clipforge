import pytest

from clipforge.db.engine import Database
from clipforge.db.sources import SourceExists, SourcesRepo, UnknownAccount, UnknownSource
from clipforge.models import SourcePermission
from tests.dbhelpers import BILLY_SOURCE, NOW, make_account, seed


def test_create_replace_and_history(db: Database) -> None:
    seed(db, make_account())
    repo = SourcesRepo(db)
    repo.create(BILLY_SOURCE, "cli:mat", NOW)
    assert repo.get("billy-garton") == BILLY_SOURCE and repo.list() == [BILLY_SOURCE]
    edited = BILLY_SOURCE.model_copy(update={"status": "paused", "permission": SourcePermission(
        type="creator_agreement", expires_at=NOW, evidence_url="https://drive.example/a"
    )})  # fmt: skip
    repo.replace(edited, "cli:mat", NOW)
    assert repo.get("billy-garton") == edited
    updated, created = repo.events("billy-garton")  # newest first
    assert created.action == "created" and created.before is None and created.actor == "cli:mat"
    assert updated.action == "updated" and updated.before is not None
    assert updated.before["status"] == "active" and updated.after["status"] == "paused"


def test_create_refuses_duplicates_and_unknown_accounts(db: Database) -> None:
    seed(db, make_account())
    repo = SourcesRepo(db)
    repo.create(BILLY_SOURCE, "test", NOW)
    with pytest.raises(SourceExists):
        repo.create(BILLY_SOURCE, "test", NOW)
    with pytest.raises(UnknownAccount):
        repo.create(BILLY_SOURCE.model_copy(update={"id": "x", "account_id": "nope"}), "test", NOW)
    with pytest.raises(UnknownSource):
        repo.replace(BILLY_SOURCE.model_copy(update={"id": "missing"}), "test", NOW)
    assert repo.get("nope") is None and repo.submissions("billy-garton") == []


def test_import_action_is_recorded(db: Database) -> None:
    seed(db, make_account())
    SourcesRepo(db).create(BILLY_SOURCE, "import-toml", NOW, action="imported")
    [event] = SourcesRepo(db).events("billy-garton")
    assert event.action == "imported" and event.actor == "import-toml"


def test_submissions_list_posted_campaign_clips(db: Database) -> None:
    from clipforge.db.posting import SqlPostingRepo
    from clipforge.models import LEGACY_PLATFORMS, Platform
    from tests.posting.builders import T0, item

    seed(db, make_account(), sources=[BILLY_SOURCE])
    repo = SqlPostingRepo(db)
    it = item()
    repo.add(it, list(LEGACY_PLATFORMS))
    repo.toggle_posted(it.id, Platform.TIKTOK, T0)
    [sub] = SourcesRepo(db).submissions("billy-garton")
    assert sub.item_id == it.id and sub.platform is Platform.TIKTOK and sub.posted_at == T0

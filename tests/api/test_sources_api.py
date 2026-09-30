from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.db.sources import SourcesRepo
from tests.api.test_accounts_api import AUTH, api_client
from tests.dbhelpers import NOW, make_account

BILLY = {"id": "billy-garton", "account_id": "realtalk-clips-en", "credit_name": "Billy Garton Jr.",
         "permission": {"type": "creator_agreement"}}  # fmt: skip
SECRET = ('connection to server at "db.example.com" failed for user "neondb_owner" '
          "postgresql://u:p@db.example.com/x")  # fmt: skip
ACTOR = {**AUTH, "X-Clipforge-Actor": "cli:mat"}


def test_source_create_edit_history(tmp_path: Path, db: Database) -> None:
    AccountsRepo(db).create(make_account(), NOW)
    client = api_client(tmp_path, db)
    created = client.post("/sources", json=BILLY, headers=ACTOR)
    assert created.status_code == 201 and created.json()["status"] == "active"
    assert len(created.json()["permission"]["platforms"]) == 4  # default: every platform
    assert client.post("/sources", json=BILLY, headers=ACTOR).status_code == 409
    edit = {**BILLY, "status": "paused"}
    assert (
        client.put("/sources/billy-garton", json=edit, headers=ACTOR).json()["status"] == "paused"
    )
    assert client.put("/sources/other", json=edit, headers=ACTOR).status_code == 400  # id mismatch
    assert (
        client.put("/sources/nope", json={**BILLY, "id": "nope"}, headers=ACTOR).status_code == 404
    )
    events = client.get("/sources/billy-garton/events", headers=AUTH).json()
    assert [e["action"] for e in events] == ["updated", "created"]
    assert events[0]["actor"] == "cli:mat" and events[0]["before"]["status"] == "active"
    assert client.get("/sources/billy-garton", headers=AUTH).json()["status"] == "paused"
    assert client.get("/sources/nope", headers=AUTH).status_code == 404
    assert client.get("/sources/billy-garton/submissions", headers=AUTH).json() == []


def test_unknown_account_import_action_and_default_actor(tmp_path: Path, db: Database) -> None:
    AccountsRepo(db).create(make_account(), NOW)
    client = api_client(tmp_path, db)
    orphan = {**BILLY, "id": "x", "account_id": "nope"}
    assert client.post("/sources", json=orphan, headers=AUTH).status_code == 400
    assert client.post("/sources?action=imported", json=BILLY, headers=AUTH).status_code == 201
    [event] = client.get("/sources/billy-garton/events", headers=AUTH).json()
    assert event["action"] == "imported" and event["actor"] == "api"


def test_bad_path_id_is_404_even_without_database(tmp_path: Path) -> None:
    client = api_client(tmp_path, None)
    assert client.get("/sources/BAD_ID", headers=AUTH).status_code == 404
    assert client.get("/accounts/BAD_ID", headers=AUTH).status_code == 404
    assert client.patch("/accounts/BAD_ID", json={}, headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception(SECRET)),
        InterfaceError("SELECT 1", {}, Exception(SECRET)),
        PoolTimeout(SECRET),
    ],
)
def test_driver_errors_answer_503_without_leaking(
    tmp_path: Path, error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: SourcesRepo) -> None:
        raise error

    monkeypatch.setattr(SourcesRepo, "list", boom)
    client = api_client(tmp_path, cast(Database, object()))
    response = client.get("/sources", headers=AUTH)
    assert response.status_code == 503 and response.json() == {"detail": "database unavailable"}
    assert "db.example.com" not in response.text and "neondb_owner" not in response.text


def test_actor_header_is_capped_and_blank_falls_back(tmp_path: Path, db: Database) -> None:
    AccountsRepo(db).create(make_account(), NOW)
    client = api_client(tmp_path, db)
    long_actor = {**AUTH, "X-Clipforge-Actor": "a" * 120}
    assert client.post("/sources", json=BILLY, headers=long_actor).status_code == 201
    other = {**BILLY, "id": "other-one"}
    blank = {**AUTH, "X-Clipforge-Actor": "   "}
    assert client.post("/sources", json=other, headers=blank).status_code == 201
    [first] = client.get("/sources/billy-garton/events", headers=AUTH).json()
    [second] = client.get("/sources/other-one/events", headers=AUTH).json()
    assert first["actor"] == "a" * 80 and second["actor"] == "api"


def test_invalid_action_is_422(tmp_path: Path, db: Database) -> None:
    AccountsRepo(db).create(make_account(), NOW)
    client = api_client(tmp_path, db)
    assert client.post("/sources?action=bogus", json=BILLY, headers=AUTH).status_code == 422

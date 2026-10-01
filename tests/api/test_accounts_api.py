from pathlib import Path

from fastapi.testclient import TestClient

from clipforge.accounts.service import read_schedules
from clipforge.api.main import ApiContext, create_app
from clipforge.db.engine import Database
from tests.bot.fakes import make_settings
from tests.pipeline.harness import Harness

AUTH = {"Authorization": "Bearer t0ken"}
CREATE = {"blueprint": "founder-tapes", "language": "en", "handle": "founder.tapes"}


def api_client(tmp_path: Path, db: Database | None, harness: Harness | None = None) -> TestClient:
    harness = harness or Harness.build(tmp_path)
    ctx = ApiContext(settings=make_settings(tmp_path), deps=lambda: harness.deps,
                     sender=lambda: None, db=lambda: db)  # fmt: skip
    return TestClient(create_app(ctx))


def test_account_create_list_edit(tmp_path: Path, db: Database) -> None:
    client = api_client(tmp_path, db)
    created = client.post("/accounts", json=CREATE, headers=AUTH)
    assert created.status_code == 201 and created.json()["id"] == "founder-tapes-en"
    assert client.post("/accounts", json=CREATE, headers=AUTH).status_code == 400  # exists
    assert [a["id"] for a in client.get("/accounts", headers=AUTH).json()] == ["founder-tapes-en"]
    edited = client.patch("/accounts/founder-tapes-en", json={"handles": {"tiktok": "ft2"}},
                          headers=AUTH)  # fmt: skip
    assert edited.json()["platforms"]["tiktok"]["handle"] == "ft2"
    assert client.get("/accounts/nope", headers=AUTH).status_code == 404


def test_routes_503_without_database(tmp_path: Path) -> None:
    client = api_client(tmp_path, None)
    response = client.get("/accounts", headers=AUTH)
    assert (
        response.status_code == 503
        and response.json()["detail"] == "DATABASE_URL is not configured"
    )
    assert client.get("/sources", headers=AUTH).status_code == 503
    assert client.get("/accounts").status_code == 401  # the token check still comes first


def test_blueprint_name_cannot_traverse(tmp_path: Path, db: Database) -> None:
    client = api_client(tmp_path, db)
    response = client.post("/accounts", json={**CREATE, "blueprint": "../x"}, headers=AUTH)
    assert response.status_code == 422


def test_account_routes_write_the_schedule_copy(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    client = api_client(tmp_path, db, harness)
    assert client.post("/accounts", json=CREATE, headers=AUTH).status_code == 201
    kv = harness.deps.store.kv
    assert "founder-tapes-en" in read_schedules(kv)
    client.patch("/accounts/founder-tapes-en", json={"slots": ["7:30"]}, headers=AUTH)
    assert read_schedules(kv)["founder-tapes-en"].slots == ["07:30"]

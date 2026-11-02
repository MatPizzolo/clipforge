"""The /admin hooks routes (hooks spec §7.1; the interim mount before S3-1's cli_router)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clipforge.db.engine import Database
from tests.api.test_accounts_api import AUTH, api_client
from tests.dbhelpers import insert_account

ACTOR = {"X-Clipforge-Actor": "cli:mat"}
ACCOUNT = "realtalk-clips-en"
LIBRARY = f"/admin/accounts/{ACCOUNT}/hooks"
DATA = {"name": "Cold open", "structure": "Start mid-sentence on the strongest line",
        "examples": {"en": "AND THEN HE QUIT"}, "fits": ["clips"], "max_words": 8}  # fmt: skip


@pytest.fixture
def client(tmp_path: Path, db: Database) -> TestClient:
    insert_account(db, ACCOUNT)
    return api_client(tmp_path, db)


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    response = client.post("/admin/hooks/seed", headers=AUTH, json={})
    assert response.json() == {"written": {ACCOUNT: 6}, "dry_run": False}
    return client


def _first(client: TestClient) -> str:
    return str(client.get(LIBRARY, headers=AUTH).json()["patterns"][0]["pattern"]["id"])


def test_library_lists_seeded_patterns(seeded: TestClient) -> None:
    body = seeded.get(LIBRARY, headers=AUTH).json()
    assert body["rotating"] == 6 and body["frozen_by"] is None and len(body["patterns"]) == 6
    assert {row["weight"] for row in body["patterns"]} == {1.0}
    assert sum(row["pattern"]["control"] for row in body["patterns"]) == 1


def test_library_reports_empty_rotation(seeded: TestClient) -> None:  # Review Focus 5
    for row in seeded.get(LIBRARY, headers=AUTH).json()["patterns"]:
        response = seeded.post(f"/admin/hooks/{row['pattern']['id']}/retire",
                               headers=AUTH | ACTOR, json={"account_id": ACCOUNT})  # fmt: skip
        assert response.status_code == 200 and response.json()["status"] == "retired"
    body = seeded.get(LIBRARY, headers=AUTH).json()
    assert body["rotating"] == 0 and len(body["patterns"]) == 6


def test_seed_dry_run_writes_nothing(client: TestClient) -> None:
    response = client.post("/admin/hooks/seed?dry_run=true", headers=AUTH,
                           json={"account_ids": [ACCOUNT]})  # fmt: skip
    assert response.json() == {"written": {ACCOUNT: 6}, "dry_run": True}
    assert client.get(LIBRARY, headers=AUTH).json()["patterns"] == []


def test_draft_edit_approve_weight_share(client: TestClient, db: Database) -> None:
    insert_account(db, "realtalk-clips-es")
    created = client.post("/admin/hooks", headers=AUTH | ACTOR,
                          json={"account_id": ACCOUNT, "data": DATA})  # fmt: skip
    assert created.status_code == 201 and created.json()["status"] == "draft"
    pid = created.json()["id"]
    edited = client.put(f"/admin/hooks/{pid}", headers=AUTH | ACTOR,
                        json={"data": {**DATA, "max_words": 6}, "note": "shorter"})  # fmt: skip
    assert edited.json()["n"] == 2 and edited.json()["author"] == "cli:mat"
    approved = client.post(f"/admin/hooks/{pid}/approve", headers=AUTH | ACTOR,
                           json={"account_id": ACCOUNT, "weight": 2})  # fmt: skip
    assert approved.json()["status"] == "approved"
    change = {"account_id": ACCOUNT, "weight": 0.5, "reason": "too many"}
    weight = client.put(f"/admin/hooks/{pid}/weight", headers=AUTH | ACTOR, json=change)
    assert weight.json() == {"weight": 0.5}
    shared = client.post(f"/admin/hooks/{pid}/share", headers=AUTH | ACTOR)
    assert shared.json()["blueprint_name"] == "realtalk-clips"
    detail = client.get(f"/admin/hooks/{pid}", headers=AUTH).json()
    assert [v["n"] for v in detail["versions"]] == [1, 2]
    pair = client.get("/admin/accounts/realtalk-clips-es/hooks", headers=AUTH).json()
    assert [(r["pattern"]["id"], r["weight"]) for r in pair["patterns"]] == [(pid, 0.0)]


def test_the_dashboard_writes_as_web_login(client: TestClient) -> None:
    created = client.post("/admin/hooks", headers=AUTH | {"X-Clipforge-Actor": "web:mat"},
                          json={"account_id": ACCOUNT, "data": DATA})  # fmt: skip
    pid = created.json()["id"]
    detail = client.get(f"/admin/hooks/{pid}", headers=AUTH).json()
    assert detail["versions"][0]["author"] == "web:mat"


def test_weight_without_reason_is_400(seeded: TestClient) -> None:
    response = seeded.put(f"/admin/hooks/{_first(seeded)}/weight", headers=AUTH | ACTOR,
                          json={"account_id": ACCOUNT, "weight": 2, "reason": ""})  # fmt: skip
    assert response.status_code == 400 and "reason" in response.json()["detail"]


@pytest.mark.parametrize("actor", [None, "nobody:x", "mat", "system:migration", "telegram:42"])
def test_a_write_needs_a_persons_actor(seeded: TestClient, actor: str | None) -> None:
    headers = AUTH | ({"X-Clipforge-Actor": actor} if actor is not None else {})
    response = seeded.post("/admin/hooks", headers=headers,
                           json={"account_id": ACCOUNT, "data": DATA})  # fmt: skip
    assert response.status_code == 400 and "X-Clipforge-Actor" in response.json()["detail"]


def test_routes_need_the_token(client: TestClient) -> None:
    assert client.get(LIBRARY).status_code == 401
    assert client.post("/admin/hooks/seed", json={}).status_code == 401


def test_unknown_pattern_or_account_is_404(seeded: TestClient) -> None:
    assert seeded.post("/admin/hooks/hp_00000000/approve", headers=AUTH | ACTOR,
                       json={"account_id": ACCOUNT}).status_code == 404  # fmt: skip
    assert seeded.get("/admin/hooks/not-an-id", headers=AUTH).status_code == 404
    assert seeded.get("/admin/accounts/nobody-en/hooks", headers=AUTH).status_code == 404
    assert seeded.get("/admin/accounts/Bad Id/hooks", headers=AUTH).status_code == 404


def test_hooks_503_without_database(tmp_path: Path) -> None:
    response = api_client(tmp_path, None).get(LIBRARY, headers=AUTH)
    assert response.status_code == 503


def test_seed_refuses_an_account_that_isnt_clips(client: TestClient, db: Database) -> None:
    insert_account(db, "story-en", blueprint="story", kind="story")
    response = client.post("/admin/hooks/seed", headers=AUTH, json={"account_ids": ["story-en"]})
    assert response.status_code == 400 and "story-en" in response.json()["detail"]
    default = client.post("/admin/hooks/seed?dry_run=true", headers=AUTH, json={}).json()
    assert default["written"] == {ACCOUNT: 6}  # only clips accounts by default

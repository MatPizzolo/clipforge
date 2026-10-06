"""Autopilot and policy admin routes (card 014 Task 8)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from clipforge.db.engine import Database
from clipforge.db.tables import post_events
from clipforge.models import LEGACY_PLATFORMS, AssetSource, PolicyDryRun
from clipforge.posting.backend import build_posting
from tests.accounts.helpers import make_account
from tests.api.test_accounts_api import AUTH, api_client
from tests.bot.fakes import make_settings
from tests.dbhelpers import BILLY_SOURCE
from tests.pipeline.harness import Harness
from tests.posting.builders import item

ACTOR = {"X-Clipforge-Actor": "web:mat"}
PATH = "/admin/accounts/realtalk-clips-en/autopilot"


def _client(tmp_path: Path, db: Database) -> TestClient:
    make_account(db)
    return api_client(tmp_path, db)


def test_show_returns_hands_on_and_what_it_waits_on(tmp_path: Path, db: Database) -> None:
    body = _client(tmp_path, db).get(PATH, headers=AUTH).json()
    assert body["autopilot"]["preset"] == "hands_on" and body["label"] == "Hands-on"
    assert body["waiting_on"]["publish"] == "Publish: on, waiting for a connected profile"
    assert [e["field"] for e in body["history"]] == ["preset"]


def test_set_records_the_actor_and_a_preset_needs_a_reason(tmp_path: Path, db: Database) -> None:
    client = _client(tmp_path, db)
    changed = client.put(PATH, headers=AUTH | ACTOR, json={"field": "publish", "value": False})
    assert changed.status_code == 200
    body = changed.json()
    assert body["label"] == "Hands-on, with Publish off"
    assert body["history"][-1]["actor"] == "web:mat"
    refused = client.put(PATH, headers=AUTH | ACTOR, json={"preset": "supervised"})
    assert refused.status_code == 400 and "reason" in refused.json()["detail"]
    ok = client.put(PATH, headers=AUTH | ACTOR, json={"preset": "supervised", "reason": "ready"})
    assert ok.json()["autopilot"]["review_dial"] == "sample"


def test_a_dial_change_without_a_reason_is_400(tmp_path: Path, db: Database) -> None:
    r = _client(tmp_path, db).put(PATH, headers=AUTH | ACTOR,
                                  json={"field": "review_dial", "value": "sample"})  # fmt: skip
    assert r.status_code == 400 and "reason" in r.json()["detail"]


def test_a_change_needs_a_person(tmp_path: Path, db: Database) -> None:
    client = _client(tmp_path, db)
    body = {"field": "publish", "value": False}
    assert client.put(PATH, headers=AUTH, json=body).status_code == 400
    system = {"X-Clipforge-Actor": "system:autopilot"}
    assert client.put(PATH, headers=AUTH | system, json=body).status_code == 400


def test_bad_bodies(tmp_path: Path, db: Database) -> None:
    client = _client(tmp_path, db)
    assert client.put(PATH, headers=AUTH | ACTOR, json={}).status_code == 422
    assert client.put(PATH, headers=AUTH | ACTOR,
                      json={"field": "publish", "value": True, "preset": "hands_on"}
                      ).status_code == 422  # fmt: skip
    r = client.put(PATH, headers=AUTH | ACTOR, json={"field": "nope", "value": 1})
    assert r.status_code == 400


def test_unknown_account_404_and_token_first(tmp_path: Path, db: Database) -> None:
    client = _client(tmp_path, db)
    assert client.get("/admin/accounts/nope/autopilot", headers=AUTH).status_code == 404
    assert client.get("/admin/accounts/../x/autopilot", headers=AUTH).status_code == 404
    assert client.get(PATH).status_code == 401


def test_dry_run_lists_what_would_be_held_and_writes_nothing(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    make_account(db)
    from clipforge.db.sources import SourcesRepo
    from tests.dbhelpers import NOW

    SourcesRepo(db).create(BILLY_SOURCE, "test", NOW)
    settings = make_settings(tmp_path, state_reads="postgres")
    harness.deps.posting = build_posting(settings, harness.deps.store.kv, db)
    repo = harness.deps.posting.repo
    for n in (1, 2):
        repo.add(item(f"clip_0{n}", start=n * 40, end=n * 40 + 30), list(LEGACY_PLATFORMS))
    stock = item("clip_03", start=200, end=230).model_copy(
        update={"assets": [AssetSource(kind="stock", license="")]})  # fmt: skip
    repo.add(stock, list(LEGACY_PLATFORMS))
    with db.begin() as conn:
        before = conn.execute(select(func.count()).select_from(post_events)).scalar()
    client = api_client(tmp_path, db, harness)
    r = client.get("/admin/policy/dry-run?account=realtalk-clips-en", headers=AUTH)
    body = PolicyDryRun.model_validate(r.json())
    assert body.checked == 3
    assert [(h.ref, h.codes) for h in body.would_hold] == [(stock.id, ["license_unrecorded"])]
    with db.begin() as conn:
        assert conn.execute(select(func.count()).select_from(post_events)).scalar() == before
    assert client.get("/admin/policy/dry-run", headers=AUTH).json()["checked"] == 3


def test_only_web_and_cli_actors_reach_autopilot(tmp_path: Path, db: Database) -> None:
    # a token holder can't record a fake Telegram tap or session write (PR #52 review)
    client = _client(tmp_path, db)
    body = {"field": "publish", "value": False}
    for actor in ("telegram:42", "session:s2a", "system:autopilot"):
        r = client.put(PATH, headers=AUTH | {"X-Clipforge-Actor": actor}, json=body)
        assert r.status_code == 400, actor
    assert client.put(PATH, headers=AUTH | {"X-Clipforge-Actor": "cli:mat"},
                      json=body).status_code == 200  # fmt: skip


def test_the_admin_routes_need_the_token(tmp_path: Path, db: Database) -> None:
    client = _client(tmp_path, db)
    assert (
        client.put(PATH, headers=ACTOR, json={"field": "publish", "value": False}).status_code
        == 401
    )
    assert client.get("/admin/policy/dry-run").status_code == 401
    assert client.get("/admin/policy/dry-run", headers={"Authorization": "Bearer nope"}
                      ).status_code == 401  # fmt: skip


def test_account_create_refuses_a_system_actor_from_the_header(
    tmp_path: Path, db: Database
) -> None:
    from clipforge.db.autopilot import AutopilotRepo
    from tests.api.test_accounts_api import CREATE

    client = api_client(tmp_path, db)
    system = {"X-Clipforge-Actor": "system:migration"}
    assert client.post("/accounts", json=CREATE, headers=AUTH | system).status_code == 400
    assert client.post("/accounts", json=CREATE, headers=AUTH).status_code == 201  # no header
    assert AutopilotRepo(db).history("founder-tapes-en")[0].actor == "system:accounts"

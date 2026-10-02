"""The job API with the in-process chain behind it (spec §5, §6)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from clipforge.api.main import ApiContext, create_app
from clipforge.links import sign
from clipforge.pipeline.deps import SpawnCall
from clipforge.posting import keepalive
from tests.bot.fakes import FakeSender, make_settings, update
from tests.pipeline.harness import Harness
from tests.posting.builders import run_channel_job as channel_job

URL = "https://media.example.com/ep.mp4"
AUTH = {"Authorization": "Bearer t0ken"}
HOOK = {"X-Telegram-Bot-Api-Secret-Token": "hook-secret"}
BODY = {"source_url": URL, "permission": "own", "options": {"n": 2}}


def _client(harness: Harness, sender: FakeSender | None = None, **settings: object) -> TestClient:
    ctx = ApiContext(
        settings=make_settings(harness.root, **settings),
        deps=lambda: harness.deps,
        sender=lambda: sender,
    )
    return TestClient(create_app(ctx))


def _done_job(harness: Harness) -> str:
    job_id = harness.submit()
    harness.run()
    return job_id


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "t0ken"}]
)
def test_bad_or_missing_token_is_401(harness: Harness, headers: dict[str, str]) -> None:
    client = _client(harness)
    assert client.post("/jobs", json=BODY, headers=headers).status_code == 401
    assert client.get("/jobs/20260923-aaaaaaaa-0001", headers=headers).status_code == 401


def test_api_token_unset_is_503(harness: Harness) -> None:
    response = _client(harness, api_token=None).post("/jobs", json=BODY, headers=AUTH)
    assert response.status_code == 503 and "API_TOKEN" in response.json()["detail"]


def test_post_job_creates_and_spawns(harness: Harness) -> None:
    response = _client(harness).post("/jobs", json=BODY, headers=AUTH)
    assert response.status_code == 201
    job_id = response.json()["job_id"]
    assert harness.store.get(job_id).input.options.n == 2
    assert list(harness.spawner.queue) == [SpawnCall("ingest", job_id, None)]


def test_invalid_job_input_is_422(harness: Harness) -> None:
    body = {**BODY, "telegram_file_id": "F"}  # two sources
    assert _client(harness).post("/jobs", json=body, headers=AUTH).status_code == 422


def test_get_job_view_with_signed_link_then_download(harness: Harness) -> None:
    job_id = _done_job(harness)
    client = _client(harness)
    view = client.get(f"/jobs/{job_id}", headers=AUTH).json()
    assert view["status"] == "done" and len(view["clips"]) == 5
    link = urlsplit(view["download_url"])
    response = client.get(f"{link.path}?{link.query}")  # no bearer: the signature authorizes
    assert response.status_code == 200 and response.content == b"zip"
    assert response.headers["content-type"] == "application/zip"


def test_unknown_or_malformed_job_is_404(harness: Harness) -> None:
    client = _client(harness)
    assert client.get("/jobs/20260923-aaaaaaaa-0001", headers=AUTH).status_code == 404
    assert client.get("/jobs/not-a-job", headers=AUTH).status_code == 404


def test_download_rejects_expired_and_tampered(harness: Harness) -> None:
    job_id = _done_job(harness)
    client = _client(harness)
    expired = sign("k3y", job_id, 1_000)
    assert client.get(f"/jobs/{job_id}/download?exp=1000&sig={expired}").status_code == 403
    exp = 4_000_000_000
    good = sign("k3y", job_id, exp)
    tampered = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert client.get(f"/jobs/{job_id}/download?exp={exp}&sig={tampered}").status_code == 403
    assert client.get(f"/jobs/{job_id}/download?exp={exp}&sig={good}").status_code == 200


def test_download_rejects_other_job_and_traversal(harness: Harness) -> None:
    job_id = _done_job(harness)
    client = _client(harness)
    exp = 4_000_000_000
    other = "20260923-bbbbbbbb-0001"
    reused = sign("k3y", job_id, exp)
    assert client.get(f"/jobs/{other}/download?exp={exp}&sig={reused}").status_code == 403
    for bad in ["..", "%2e%2e", "..%2F..%2Fetc"]:
        sig = sign("k3y", bad, exp)
        assert client.get(f"/jobs/{bad}/download?exp={exp}&sig={sig}").status_code in (403, 404)


def test_download_before_done_is_404(harness: Harness) -> None:
    job_id = harness.submit()
    exp = 4_000_000_000
    sig = sign("k3y", job_id, exp)
    assert _client(harness).get(f"/jobs/{job_id}/download?exp={exp}&sig={sig}").status_code == 404


def test_download_key_unset_is_503(harness: Harness) -> None:
    client = _client(harness, download_signing_key=None)
    assert client.get("/jobs/20260923-aaaaaaaa-0001/download?exp=1&sig=x").status_code == 503


def test_resume(harness: Harness) -> None:
    client = _client(harness)
    running = harness.submit()
    assert client.post(f"/jobs/{running}/resume", headers=AUTH).status_code == 409
    assert client.post("/jobs/20260923-aaaaaaaa-0001/resume", headers=AUTH).status_code == 404

    harness.stages.permanent["transcribe"] = "no speech"
    failed = harness.submit()
    harness.run()
    harness.stages.permanent.clear()
    response = client.post(f"/jobs/{failed}/resume", headers=AUTH)
    assert response.status_code == 200 and response.json()["status"] == "running"
    assert harness.spawner.queue[-1] == SpawnCall("transcribe", failed, None)


class _BrokenVolume:
    def commit(self) -> None:
        return None

    def reload(self) -> None:
        raise RuntimeError("there are open files preventing the operation")


def test_volume_reload_failure_still_serves_status(harness: Harness) -> None:
    job_id = _done_job(harness)
    deps = dataclasses.replace(harness.deps, volume=_BrokenVolume())
    ctx = ApiContext(make_settings(harness.root), deps=lambda: deps, sender=lambda: None)
    response = TestClient(create_app(ctx)).get(f"/jobs/{job_id}", headers=AUTH)
    assert response.status_code == 200 and response.json()["status"] == "done"


def test_webhook_checks_the_secret(harness: Harness) -> None:
    sender = FakeSender()
    client = _client(harness, sender)
    bad = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    assert client.post("/telegram/webhook", json=update(text=URL), headers=bad).status_code == 403
    assert client.post("/telegram/webhook", json=update(text=URL)).status_code == 403
    assert harness.store.list_job_ids() == [] and sender.messages == []


def test_webhook_secret_unset_is_503(harness: Harness) -> None:
    client = _client(harness, FakeSender(), telegram_webhook_secret=None)
    assert client.post("/telegram/webhook", json=update(text=URL), headers=HOOK).status_code == 503


def test_webhook_handles_an_update(harness: Harness) -> None:
    sender = FakeSender()
    response = _client(harness, sender).post(
        "/telegram/webhook", json=update(text=URL), headers=HOOK
    )
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert len(harness.store.list_job_ids()) == 1 and len(sender.messages) == 1


def test_webhook_answers_200_when_handling_fails(harness: Harness) -> None:
    sender = FakeSender(fail=True)  # the reply raises
    response = _client(harness, sender).post(
        "/telegram/webhook", json=update(text=URL), headers=HOOK
    )
    assert response.status_code == 200


def test_openapi_docs_are_not_public(harness: Harness) -> None:
    client = _client(harness)
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_zip_path_must_stay_inside_root(harness: Harness) -> None:
    job_id = _done_job(harness)
    job = harness.store.get(job_id)
    harness.store.save(job.model_copy(update={"output_zip": "../outside.zip"}))
    (harness.root.parent / "outside.zip").write_bytes(b"secret")
    exp = 4_000_000_000
    sig = sign("k3y", job_id, exp)
    assert _client(harness).get(f"/jobs/{job_id}/download?exp={exp}&sig={sig}").status_code == 404


def test_posting_overview_and_rebuild(harness: Harness) -> None:
    channel_job(harness)
    client = _client(harness)
    assert client.get("/posting").status_code == 401
    view = client.get("/posting", headers=AUTH).json()
    assert view["channels"][0]["slug"] == "billy-garton"
    assert client.post("/posting/rebuild", headers=AUTH).json() == {"added": 0}
    assert client.post("/posting/restore").status_code == 401
    assert client.post("/posting/restore", headers=AUTH).json() == {"restored": 0}


def test_posting_rebuild_refuses_during_an_outage(harness: Harness) -> None:
    keepalive.set_outage(harness.store.kv, "2026-09-20")
    response = _client(harness).post("/posting/rebuild", headers=AUTH)
    assert response.status_code == 409
    assert "clipforge status --restore 2026-09-20" in response.json()["detail"]


def test_posting_restore_takes_a_date(harness: Harness) -> None:
    kv = harness.store.kv
    kv.put("post:job_a:clip_01", "{}")
    keepalive.snapshot(kv, harness.root, datetime(2026, 9, 20, tzinfo=UTC))
    kv.delete("post:job_a:clip_01")
    keepalive.snapshot(kv, harness.root, datetime(2026, 9, 29, tzinfo=UTC))
    client = _client(harness)
    assert client.post("/posting/restore", headers=AUTH).json() == {"restored": 0}
    answer = client.post("/posting/restore?date=2026-09-20", headers=AUTH)
    assert answer.json() == {"restored": 1}
    for bad in ("2026-13-01", "yesterday", "../x"):
        assert client.post(f"/posting/restore?date={bad}", headers=AUTH).status_code == 400


def test_posting_import_without_a_database_is_503_and_needs_the_token(harness: Harness) -> None:
    client = _client(harness)
    response = client.post("/posting/import", headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {"detail": "DATABASE_URL is not configured"}
    assert client.post("/posting/import").status_code == 401

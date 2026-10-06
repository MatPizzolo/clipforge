"""accounts/autopilot.py: the one writer of autopilot (ADR-48, S2 spec §5.4; card 014 Task 3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from clipforge.accounts.autopilot import AutopilotError, AutopilotService, UnknownAccount, describe
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import PublisherProfile
from clipforge.pipeline.deps import MemoryKV
from tests.accounts.helpers import make_account

NOW = datetime(2026, 10, 2, 9, tzinfo=UTC)
ID = "realtalk-clips-en"


@pytest.fixture
def svc(db: Database) -> AutopilotService:
    make_account(db)
    return AutopilotService(db, AccountsRepo(db), MemoryKV())


def test_missing_row_reads_hands_on(db: Database) -> None:
    make_account(db, insert_autopilot=False)
    ap = AutopilotService(db, AccountsRepo(db), MemoryKV()).get(ID)
    assert (ap.preset, ap.review_dial, ap.publish, ap.monthly_cap_usd) == (
        "hands_on", "review", True, 5.0)  # fmt: skip


def test_unknown_account(svc: AutopilotService) -> None:
    with pytest.raises(UnknownAccount):
        svc.get("nope")


def test_override_turns_preset_custom_and_logs_one_event_per_field(svc: AutopilotService) -> None:
    ap = svc.set(ID, "publish", False, "telegram:42", None, NOW)
    assert ap.preset == "custom" and ap.publish is False and ap.updated_by == "telegram:42"
    assert describe(ap) == "Hands-on, with Publish off"
    events = svc.history(ID)
    assert [(e.field, e.from_value, e.to_value, e.actor) for e in events[-2:]] == [
        ("publish", "true", "false", "telegram:42"),
        ("preset", "hands_on", "custom", "telegram:42"),
    ]
    assert svc.get(ID) == ap  # stored


def test_setting_the_same_value_writes_nothing(svc: AutopilotService) -> None:
    before = len(svc.history(ID))
    svc.set(ID, "publish", True, "cli:mat", None, NOW)
    assert len(svc.history(ID)) == before


def test_turning_the_override_back_returns_to_the_preset(svc: AutopilotService) -> None:
    svc.set(ID, "publish", False, "cli:mat", None, NOW)
    assert svc.set(ID, "publish", "true", "cli:mat", None, NOW).preset == "hands_on"


@pytest.mark.parametrize("dial", ["auto", "review"])
def test_dial_change_by_a_person_needs_a_reason_either_way(
    svc: AutopilotService, dial: str
) -> None:
    svc.set(ID, "review_dial", "sample", "cli:mat", "spot checks look fine", NOW)
    with pytest.raises(AutopilotError, match="reason"):
        svc.set(ID, "review_dial", dial, "cli:mat", None, NOW)
    with pytest.raises(AutopilotError, match="reason"):
        svc.set(ID, "review_dial", dial, "web:mat", "   ", NOW)


def test_the_system_writes_its_own_reason(svc: AutopilotService) -> None:
    svc.set(ID, "review_dial", "sample", "cli:mat", "ok", NOW)
    assert (
        svc.set(ID, "review_dial", "review", "system:demotion", None, NOW).review_dial == "review"
    )


def test_apply_preset_supervised_needs_a_reason_and_records_it(svc: AutopilotService) -> None:
    with pytest.raises(AutopilotError, match="reason"):
        svc.apply_preset(ID, "supervised", "cli:mat", None, NOW)
    ap = svc.apply_preset(ID, "supervised", "cli:mat", "ladder met", NOW)
    assert (ap.preset, ap.produce, ap.review_dial, ap.publish, ap.scale) == (
        "supervised", True, "sample", True, False)  # fmt: skip
    assert {e.field for e in svc.history(ID)[-3:]} == {"produce", "review_dial", "preset"}
    assert all(e.reason == "ladder met" for e in svc.history(ID)[-3:])


@pytest.mark.parametrize(("field", "value", "match"), [
    ("nope", 1, "unknown control"), ("review_dial", "bogus", "review_dial"),
    ("runway_days", -1, "negative"), ("publish", "maybe", "publish"),
])  # fmt: skip
def test_bad_values_are_refused(
    svc: AutopilotService, field: str, value: object, match: str
) -> None:
    with pytest.raises(AutopilotError, match=match):
        svc.set(ID, field, value, "cli:mat", "r", NOW)


def test_bad_actor_is_refused(svc: AutopilotService) -> None:
    with pytest.raises(AutopilotError, match="actor"):
        svc.set(ID, "publish", False, "api", None, NOW)


def test_publish_change_rewrites_the_publish_path(db: Database) -> None:
    kv = MemoryKV()
    account = make_account(db)
    AccountsRepo(db).update(account.model_copy(update={
        "publisher": PublisherProfile(profile="realtalk")}), NOW)  # fmt: skip
    svc = AutopilotService(db, AccountsRepo(db), kv)
    svc.set(ID, "publish", False, "cli:mat", None, NOW)
    assert '"publish_via":"assisted"' in (kv.get(f"posting:publish:{ID}") or "")
    svc.set(ID, "publish", True, "cli:mat", None, NOW)
    assert '"publish_via":"upload_post"' in (kv.get(f"posting:publish:{ID}") or "")


def test_waiting_on_publish_without_a_profile(svc: AutopilotService) -> None:
    lines = svc.waiting_on(ID)
    assert lines["publish"] == "Publish: on, waiting for a connected profile"
    assert lines["scale"] == "Scale: no paired account"
    assert lines["produce"] == "Produce: off"


def test_history_rows_cant_be_changed(svc: AutopilotService, db: Database) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"), db.begin() as conn:
        conn.execute(text("update autopilot_events set reason = 'x'"))

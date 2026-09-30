from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from clipforge.models import CampaignRules, Platform, Source, SourcePermission
from clipforge.sources import hold_reason, missing_permission_fields, source_problem, uncovered

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


def _source(**changes: object) -> Source:
    values: dict[str, object] = {
        "id": "billy-garton", "account_id": "realtalk-clips-en", "credit_name": "Billy Garton Jr.",
        "permission": SourcePermission(type="creator_agreement"),
    }  # fmt: skip
    values.update(changes)
    return Source.model_validate(values)


def test_active_source_with_live_permission_has_no_problem() -> None:
    assert source_problem(_source(), NOW) is None
    assert hold_reason(_source(), list(Platform), NOW) is None
    assert hold_reason(None, list(Platform), NOW) is None  # dict mode: no source rows


def test_status_expiry_and_deadline_hold() -> None:
    assert source_problem(_source(status="paused"), NOW) == "source paused"
    assert source_problem(_source(status="ended"), NOW) == "source ended"
    expired = _source(permission=SourcePermission(type="creator_agreement", expires_at=NOW))
    assert source_problem(expired, NOW) == "permission expired 2026-09-29"
    assert source_problem(expired, NOW - timedelta(seconds=1)) is None
    campaign = _source(kind="campaign", permission=SourcePermission(type="clipping_program"),
                       campaign=CampaignRules(deadline=NOW))  # fmt: skip
    assert source_problem(campaign, NOW + timedelta(seconds=1)) == "campaign ended 2026-09-29"


def test_uncovered_platforms_hold() -> None:
    both = [Platform.TIKTOK, Platform.YOUTUBE]
    narrow = _source(permission=SourcePermission(type="creator_agreement", platforms=both))
    assert uncovered(narrow, [Platform.TIKTOK, Platform.INSTAGRAM]) == [Platform.INSTAGRAM]
    assert hold_reason(narrow, [Platform.TIKTOK], NOW) is None
    assert (
        hold_reason(narrow, [Platform.TIKTOK, Platform.INSTAGRAM], NOW)
        == "permission doesn't cover instagram"
    )


def test_missing_permission_fields() -> None:
    assert missing_permission_fields(_source()) == [
        "granted_at",
        "granted_by",
        "evidence_url",
        "monetization_allowed",
        "translation_allowed",
    ]
    full = _source(permission=SourcePermission(
        type="creator_agreement", granted_at=NOW.date(), granted_by="Billy (host)",
        evidence_url="https://drive.example/agreement", monetization_allowed=True,
        translation_allowed=False))  # fmt: skip
    assert missing_permission_fields(full) == []


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SourcePermission(type="own", expires_at=datetime(2027, 1, 1))
    with pytest.raises(ValidationError):
        CampaignRules(deadline=datetime(2027, 1, 1))
    assert SourcePermission(type="own", expires_at=datetime(2027, 1, 1, tzinfo=UTC)).expires_at

"""Account create/edit (spec §6.2). The CLI reaches these through the API; the S3 admin
endpoint will call the same functions (ADR-38)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from pydantic import Field, ValidationError

from clipforge.accounts.blueprints import BlueprintError, load_blueprint
from clipforge.config import Settings
from clipforge.db.accounts import AccountExists, AccountsRepo
from clipforge.models import (
    ACCOUNT_ID,
    HANDLE,
    LEGACY_PLATFORMS,
    Account,
    Contract,
    Platform,
    PlatformProfile,
    PostingSchedule,
)  # fmt: skip
from clipforge.pipeline.deps import KV
from clipforge.schedule import normalize_hashtags, normalize_slots, schedule_problem

log = logging.getLogger(__name__)

# The tick's copy of each account's schedule (card 002 A3): it computes the slot from this Dict
# copy and only touches Postgres when a slot is due, so Neon can scale to zero between slots.
# One writer (ADR-14): this module, on create, edit and the daily sync.
SCHEDULE_PREFIX = "posting:schedule:"


class AccountError(ValueError):
    """Shown to the user as-is (API 400)."""


class AccountCreate(Contract):
    blueprint: str = Field(pattern=f"^{ACCOUNT_ID}$")
    language: Literal["en", "es"]
    handle: str = Field(pattern=f"^{HANDLE}$")
    id: str | None = Field(None, pattern=f"^{ACCOUNT_ID}$")
    posting_from_env: bool = False


class AccountEdit(Contract):
    handles: dict[Platform, str] = Field(default_factory=dict)
    chat_id: int | None = None
    clear_chat: bool = False
    slots: list[str] | None = None
    timezone: str | None = None
    hashtags: list[str] | None = None
    review_tier: Literal["review", "sample", "auto"] | None = None


def env_schedule(settings: Settings) -> PostingSchedule:
    return PostingSchedule(chat_id=settings.posting_chat_id, timezone=settings.posting_timezone,
                           slots=list(settings.posting_slots),
                           hashtags=list(settings.posting_hashtags))  # fmt: skip


def env_account(settings: Settings) -> Account:
    """Dict mode (STATE_READS=dict): account #1 as the POSTING_* settings describe it."""
    return Account(
        id=settings.posting_account_id, blueprint="realtalk-clips", blueprint_version=0,
        kind="clips", language="en", niche="",
        platforms={p: PlatformProfile() for p in LEGACY_PLATFORMS}, posting=env_schedule(settings),
    )  # fmt: skip


def _checked(schedule: PostingSchedule, settings: Settings) -> PostingSchedule:
    schedule = schedule.model_copy(
        update={
            "slots": normalize_slots(schedule.slots),
            "hashtags": normalize_hashtags(schedule.hashtags),
        }
    )
    if schedule.chat_id is not None and schedule.chat_id not in settings.telegram_allowed_user_ids:
        raise AccountError("the posting chat must be one of TELEGRAM_ALLOWED_USER_IDS")
    if schedule.chat_id is not None and not schedule.slots:
        raise AccountError("slots: between 1 and 12 posting slots")
    # The ["00:00"] placeholder only skips the slot-count rule when posting is off.
    problem = schedule_problem(schedule.timezone, schedule.slots or ["00:00"], schedule.hashtags)
    if problem is not None:
        raise AccountError(f"{problem[0]}: {problem[1]}")
    return schedule


def publish_schedule(kv: KV, account: Account) -> None:
    kv.put(f"{SCHEDULE_PREFIX}{account.id}", account.posting.model_dump_json())


def read_schedules(kv: KV) -> dict[str, PostingSchedule]:
    """Every account's schedule copy; an invalid one is logged and left out."""
    schedules: dict[str, PostingSchedule] = {}
    for key in kv.keys():  # noqa: SIM118 (a KV, not a dict)
        if not key.startswith(SCHEDULE_PREFIX):
            continue
        raw = kv.get(key)  # a get per key also counts as Dict activity (ADR-24)
        if raw is None:
            continue
        try:
            schedules[key[len(SCHEDULE_PREFIX) :]] = PostingSchedule.model_validate_json(raw)
        except ValidationError:
            log.warning("ignoring an invalid schedule copy %s", key)
    return schedules


def sync_schedules(repo: AccountsRepo, kv: KV) -> int:
    """Rewrite every account's copy from the database, and drop copies of deleted accounts."""
    accounts = repo.list()
    for account in accounts:
        publish_schedule(kv, account)
    known = {a.id for a in accounts}
    for account_id in set(read_schedules(kv)) - known:
        kv.delete(f"{SCHEDULE_PREFIX}{account_id}")
    return len(accounts)


def schedule_drift(repo: AccountsRepo, kv: KV) -> list[str]:
    """Accounts with a posting chat whose Dict copy is missing or differs from the database
    (read-only; `db_doctor` reports it before rollout step 4c.7, `sync_schedules` fixes it)."""
    copies = read_schedules(kv)
    return [a.id for a in repo.list()
            if a.posting.chat_id is not None and copies.get(a.id) != a.posting]  # fmt: skip


def create_account(
    repo: AccountsRepo, settings: Settings, req: AccountCreate, now: datetime,
    kv: KV | None = None,
) -> Account:  # fmt: skip
    try:
        blueprint = load_blueprint(settings.blueprints_dir, req.blueprint)
    except BlueprintError as exc:
        raise AccountError(str(exc)) from None
    if req.language not in blueprint.languages:
        raise AccountError(f"language {req.language!r} isn't in {blueprint.name}'s languages "
                           f"{blueprint.languages}")  # fmt: skip
    platforms = {p: prof.model_copy(update={"handle": req.handle})
                 for p, prof in blueprint.platform_defaults.items()}  # fmt: skip
    posting = env_schedule(settings) if req.posting_from_env else PostingSchedule()
    try:
        account = Account(
            id=req.id or f"{blueprint.name}-{req.language}", blueprint=blueprint.name,
            blueprint_version=blueprint.version, kind=blueprint.category, language=req.language,
            niche=blueprint.niche, platforms=platforms, posting=_checked(posting, settings),
        )  # fmt: skip
        repo.create(account, now)
    except (ValidationError, AccountExists) as exc:
        raise AccountError(str(exc)) from None
    if kv is not None:
        publish_schedule(kv, account)
    return account


def edit_account(
    repo: AccountsRepo, settings: Settings, account_id: str, edit: AccountEdit, now: datetime,
    kv: KV | None = None,
) -> Account:  # fmt: skip
    account = repo.get(account_id)
    if account is None:
        raise AccountError(f"no account {account_id!r}")
    platforms = dict(account.platforms)
    for platform, handle in edit.handles.items():
        profile = platforms.get(platform)
        if profile is None or not profile.enabled:
            raise AccountError(f"{platform} is not enabled for {account_id}")
        try:
            platforms[platform] = PlatformProfile.model_validate(
                {**profile.model_dump(), "handle": handle}
            )
        except ValidationError:
            raise AccountError(
                f"handle {handle!r}: letters, digits, . and _ only (max 30)"
            ) from None
    posting = account.posting
    changes: dict[str, object] = {}
    if edit.clear_chat:
        changes["chat_id"] = None
    elif edit.chat_id is not None:
        changes["chat_id"] = edit.chat_id
    for name in ("slots", "timezone", "hashtags"):
        value = getattr(edit, name)
        if value is not None:
            changes[name] = value
    posting = _checked(posting.model_copy(update=changes), settings)
    updated = account.model_copy(update={
        "platforms": platforms, "posting": posting,
        "review_tier": edit.review_tier or account.review_tier})  # fmt: skip
    repo.update(updated, now)
    if kv is not None:
        # after the database: a failed copy write is an error the caller sees, and repeating
        # the edit (or the daily sync) rewrites it
        publish_schedule(kv, updated)
    return updated

"""Account create/edit (spec §6.2). The CLI reaches these through the API; the S3 admin
endpoint will call the same functions (ADR-38)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from pydantic import Field, ValidationError

from clipforge.accounts.blueprints import BlueprintError, load_blueprint
from clipforge.actors import ACTOR
from clipforge.config import Settings
from clipforge.db.accounts import AccountExists, AccountsRepo
from clipforge.db.autopilot import AutopilotRepo
from clipforge.models import (
    ACCOUNT_ID,
    HANDLE,
    LEGACY_PLATFORMS,
    Account,
    Autopilot,
    Contract,
    Platform,
    PlatformProfile,
    PostingSchedule,
    PublisherProfile,
    PublishPath,
    ScheduleCopy,
    hands_on,
)  # fmt: skip
from clipforge.pipeline.deps import KV
from clipforge.schedule import normalize_hashtags, normalize_slots, schedule_problem

log = logging.getLogger(__name__)

# The tick's copy of each account's schedule (card 002 A3): it computes the slot from this Dict
# copy and only touches Postgres when a slot is due, so Neon can scale to zero between slots.
# One writer (ADR-14): this module, on create, edit and the daily sync.
SCHEDULE_PREFIX = "posting:schedule:"
# Next to each copy, the account's publish path (S2 spec §1.1; same writer). Missing: assisted.
PUBLISH_PREFIX = "posting:publish:"
PROFILE = r"[A-Za-z0-9._-]{1,64}"  # an Upload-Post profile username


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
    # S2: the Upload-Post profile (connecting it is the owner's step that turns publishing on)
    publisher_profile: str | None = Field(None, pattern=f"^{PROFILE}$")
    facebook_page_id: str | None = Field(None, pattern=r"^[0-9]{1,32}$")
    clear_publisher: bool = False


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


def publish_path(account: Account, autopilot: Autopilot) -> PublishPath:
    """Upload-Post only with Publish on and a connected profile (S2 spec §1.1)."""
    if autopilot.publish and account.publisher is not None:
        return PublishPath(publish_via="upload_post", profile=account.publisher.profile)
    return PublishPath()


def write_schedule_copy(kv: KV, account: Account, autopilot: Autopilot | None = None) -> None:
    """The account's schedule copy and its publish path (the one writer of both keys).
    `autopilot` None: the account's Hands-on default."""
    kv.put(f"{SCHEDULE_PREFIX}{account.id}", account.posting.model_dump_json())
    path = publish_path(account, autopilot or hands_on(account))
    kv.put(f"{PUBLISH_PREFIX}{account.id}", path.model_dump_json())


def publish_schedule(kv: KV, account: Account) -> None:
    """S1's name for `write_schedule_copy` with the account's Hands-on default."""
    write_schedule_copy(kv, account)


def _publish_path(kv: KV, account_id: str) -> PublishPath:
    raw = kv.get(f"{PUBLISH_PREFIX}{account_id}")
    if raw is None:
        return PublishPath()
    try:
        return PublishPath.model_validate_json(raw)
    except ValidationError:
        log.warning("ignoring an invalid publish path for %s", account_id)
        return PublishPath()


def read_schedules(kv: KV) -> dict[str, ScheduleCopy]:
    """Every account's schedule copy with its publish path (a missing or invalid path reads as
    assisted); an invalid copy is logged and left out."""
    schedules: dict[str, ScheduleCopy] = {}
    for key in kv.keys():  # noqa: SIM118 (a KV, not a dict)
        if not key.startswith(SCHEDULE_PREFIX):
            continue
        raw = kv.get(key)  # a get per key also counts as Dict activity (ADR-24)
        if raw is None:
            continue
        account_id = key[len(SCHEDULE_PREFIX) :]
        try:
            schedule = PostingSchedule.model_validate_json(raw)
        except ValidationError:
            log.warning("ignoring an invalid schedule copy %s", key)
            continue
        schedules[account_id] = ScheduleCopy.of(schedule, _publish_path(kv, account_id))
    return schedules


def _autopilots(repo: AccountsRepo) -> dict[str, Autopilot]:
    return AutopilotRepo(repo.db).all()


def sync_schedules(repo: AccountsRepo, kv: KV) -> int:
    """Rewrite every account's copy from the database, and drop copies of deleted accounts."""
    accounts = repo.list()
    autopilots = _autopilots(repo)
    for account in accounts:
        write_schedule_copy(kv, account, autopilots.get(account.id))
    known = {a.id for a in accounts}
    for key in kv.keys():  # noqa: SIM118 (a KV, not a dict)
        for prefix in (SCHEDULE_PREFIX, PUBLISH_PREFIX):
            if key.startswith(prefix) and key[len(prefix) :] not in known:
                kv.delete(key)
    return len(accounts)


def schedule_drift(repo: AccountsRepo, kv: KV) -> list[str]:
    """Accounts with a posting chat whose Dict copy is missing or differs from the database, or
    whose publish path (as read) is wrong (read-only; `db_doctor` reports it, `sync_schedules`
    fixes it)."""
    copies = read_schedules(kv)
    autopilots = _autopilots(repo)
    drift = []
    for a in repo.list():
        if a.posting.chat_id is None:
            continue
        path = publish_path(a, autopilots.get(a.id) or hands_on(a))
        copy = copies.get(a.id)
        current = copy is not None and copy.schedule() == a.posting
        same_path = copy is not None and (copy.publish_via, copy.profile) == (
            path.publish_via, path.profile)  # fmt: skip
        # a missing publish key reads as assisted, so it is drift only when that's wrong
        if not (current and same_path):
            drift.append(a.id)
    return drift


def create_account(
    repo: AccountsRepo, settings: Settings, req: AccountCreate, now: datetime,
    kv: KV | None = None, actor: str | None = None,
) -> Account:  # fmt: skip
    """Creates the account Hands-on (its autopilot row and seed event in the same transaction,
    S2 spec §3), recorded as `actor` when it is one, else `system:accounts`."""
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
        seed = hands_on(account)
        who = actor if actor is not None and ACTOR.fullmatch(actor) else "system:accounts"
        repo.create(account, now, autopilot=seed.model_copy(update={"updated_by": who,
                                                                     "updated_at": now}),
                    actor=who)  # fmt: skip
    except (ValidationError, AccountExists) as exc:
        raise AccountError(str(exc)) from None
    if kv is not None:
        write_schedule_copy(kv, account, seed)
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
        "review_tier": edit.review_tier or account.review_tier,
        "publisher": _publisher(account, edit)})  # fmt: skip
    repo.update(updated, now)
    if updated.publisher is not None and account.publisher is None:
        _warn_profile_limit(repo, settings)
    if kv is not None:
        # after the database: a failed copy write is an error the caller sees, and repeating
        # the edit (or the daily sync) rewrites it
        write_schedule_copy(kv, updated, AutopilotRepo(repo.db).get(account_id))
    return updated


def _publisher(account: Account, edit: AccountEdit) -> PublisherProfile | None:
    """`--clear-publisher` disconnects (the cancel of scheduled posts arrives in S2b);
    `--publisher-profile` connects or renames; `--facebook-page-id` alone needs a profile."""
    current = account.publisher
    if edit.clear_publisher:
        if edit.publisher_profile is not None or edit.facebook_page_id is not None:
            raise AccountError("clear_publisher can't be combined with a profile or page id")
        return None
    if edit.publisher_profile is not None:
        page = edit.facebook_page_id or (current.facebook_page_id if current else None)
        disconnected = current.disconnected if current else {}
        return PublisherProfile(profile=edit.publisher_profile, facebook_page_id=page,
                                disconnected=disconnected)  # fmt: skip
    if edit.facebook_page_id is not None:
        if current is None:
            raise AccountError("facebook_page_id needs a publisher profile first")
        return current.model_copy(update={"facebook_page_id": edit.facebook_page_id})
    return current


def _warn_profile_limit(repo: AccountsRepo, settings: Settings) -> None:
    """O4: Basic covers 5 profiles; upgrade at the 6th (log #440)."""
    used = sum(a.publisher is not None for a in repo.list())
    if used > settings.upload_post_profile_limit:
        log.warning("Upload-Post profiles in use: %d, over UPLOAD_POST_PROFILE_LIMIT=%d; "
                    "upgrade the plan", used, settings.upload_post_profile_limit)  # fmt: skip

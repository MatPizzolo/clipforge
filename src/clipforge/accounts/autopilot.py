"""The autopilot service (ADR-48, S2 spec §5.4): the one writer of `autopilot` and
`autopilot_events`. Every change records who made it; any change a person makes to the Review
dial needs a reason. A missing row reads as Hands-on. Produce and Scale are stored but do nothing
until S6 (the queue filler) and S10 (dubs)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError

from clipforge.accounts.service import write_schedule_copy
from clipforge.actors import checked, is_system
from clipforge.db.accounts import AccountsRepo
from clipforge.db.autopilot import AutopilotRepo
from clipforge.db.engine import Database
from clipforge.models import Account, Autopilot, AutopilotEvent, Preset, hands_on
from clipforge.pipeline.deps import KV

PRESETS: dict[Preset, dict[str, Any]] = {
    "hands_on": {"produce": False, "review_dial": "review", "publish": True, "scale": False},
    "supervised": {"produce": True, "review_dial": "sample", "publish": True, "scale": False},
    "autopilot": {"produce": True, "review_dial": "auto", "publish": True, "scale": True},
}
PRESET_LABELS: dict[Preset, str] = {"hands_on": "Hands-on", "supervised": "Supervised",
                                    "autopilot": "Autopilot", "custom": "Custom"}  # fmt: skip
CONTROLS = ("produce", "review_dial", "publish", "scale")
FIELDS = (*CONTROLS, "runway_days", "batch_line_usd", "monthly_cap_usd")
_NUMBERS = ("runway_days", "batch_line_usd", "monthly_cap_usd")


class AutopilotError(ValueError):
    """Shown to the user as-is (API 400)."""


class UnknownAccount(AutopilotError):
    """API 404."""


def _preset_of(values: dict[str, Any]) -> Preset:
    for name, controls in PRESETS.items():
        if all(values[k] == v for k, v in controls.items()):
            return name
    return "custom"


def describe(ap: Autopilot) -> str:
    """ "Hands-on", or "Hands-on, with Publish off" style for a custom mix (spec §5.4)."""
    if ap.preset != "custom":
        return PRESET_LABELS[ap.preset]
    nearest = min(PRESETS, key=lambda p: sum(getattr(ap, k) != v for k, v in PRESETS[p].items()))
    diffs = [f"{k.replace('_', ' ').capitalize()} {_word(getattr(ap, k))}"
             for k, v in PRESETS[nearest].items() if getattr(ap, k) != v]  # fmt: skip
    return f"{PRESET_LABELS[nearest]}, with {' and '.join(diffs)}"


def _word(value: object) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


class AutopilotService:
    """The one writer of `autopilot` and `autopilot_events` (ADR-48, spec §5.4)."""

    def __init__(self, db: Database, accounts: AccountsRepo, kv: KV | None = None) -> None:
        self.db, self.accounts, self.kv = db, accounts, kv
        self.repo = AutopilotRepo(db)

    def _account(self, account_id: str) -> Account:
        account = self.accounts.get(account_id)
        if account is None:
            raise UnknownAccount(f"no account {account_id}")
        return account

    def get(self, account_id: str) -> Autopilot:
        row = self.repo.get(account_id)
        if row is not None:
            return row
        return hands_on(self._account(account_id))

    def history(self, account_id: str) -> list[AutopilotEvent]:
        self._account(account_id)
        return self.repo.history(account_id)

    def set(
        self, account_id: str, field: str, value: object, actor: str, reason: str | None,
        now: datetime,
    ) -> Autopilot:  # fmt: skip
        if field not in FIELDS:
            raise AutopilotError(f"unknown control {field!r}: one of {', '.join(FIELDS)}")
        before = self.get(account_id)
        after = self._validated(before, {field: value})
        if field == "review_dial" and after.review_dial != before.review_dial:
            _need_reason(actor, reason)
        values = after.model_dump()
        return self._write(before, after.model_copy(update={"preset": _preset_of(values)}),
                           actor, reason, now)  # fmt: skip

    def apply_preset(
        self, account_id: str, preset: str, actor: str, reason: str | None, now: datetime
    ) -> Autopilot:
        if preset not in PRESETS:
            raise AutopilotError(f"unknown preset {preset!r}: one of {', '.join(PRESETS)}")
        controls = PRESETS[preset]
        before = self.get(account_id)
        if before.review_dial != controls["review_dial"]:
            _need_reason(actor, reason)
        after = self._validated(before, {**controls, "preset": preset})
        return self._write(before, after, actor, reason, now)

    def waiting_on(self, account_id: str) -> dict[str, str]:
        """One line per control: what it waits on (spec §1.1, §5.4)."""
        account, ap = self._account(account_id), self.get(account_id)
        if not ap.publish:
            publish = "Publish: off (nothing is published; assisted posting is paused, ADR-54)"
        elif account.publisher is None:
            publish = "Publish: on, waiting for a connected profile"
        else:
            publish = (f"Publish: on, profile {account.publisher.profile} connected "
                       "(Upload-Post publishing arrives in S2b)")  # fmt: skip
        produce = "Produce: on (the queue filler arrives in S6)" if ap.produce else "Produce: off"
        if account.paired_account_id is None:
            scale = "Scale: no paired account"
        else:
            scale = f"Scale: {_word(ap.scale)} (dubs arrive in S10)"
        return {"review_dial": f"Review: {ap.review_dial}", "produce": produce,
                "publish": publish, "scale": scale}  # fmt: skip

    def _validated(self, before: Autopilot, changes: dict[str, object]) -> Autopilot:
        try:
            after = Autopilot.model_validate({**before.model_dump(), **changes})
        except ValidationError as exc:
            error = exc.errors()[0]
            where = ".".join(str(p) for p in error["loc"])
            raise AutopilotError(f"{where}: {error['msg']}") from None
        for name in _NUMBERS:
            if getattr(after, name) < 0:
                raise AutopilotError(f"{name} can't be negative")
        return after

    def _write(
        self, before: Autopilot, after: Autopilot, actor: str, reason: str | None, now: datetime
    ) -> Autopilot:
        try:
            actor = checked(actor)
        except ValueError as exc:
            raise AutopilotError(str(exc)) from None
        reason = (reason or "").strip() or None
        after = after.model_copy(update={"updated_by": actor, "updated_at": now})
        if not self.repo.upsert_with_events(before, after, actor, reason, now):
            return before  # nothing changed: no row, no event
        if before.publish != after.publish and self.kv is not None:
            # the dispatcher reads the publish path from the Dict copy (spec §1.1)
            write_schedule_copy(self.kv, self._account(after.account_id), after)
        return after


def _need_reason(actor: str, reason: str | None) -> None:
    """S3 §8.4: a person's change to the Review dial needs a reason, in either direction; the
    system writes its own (demotions)."""
    if not is_system(actor) and not (reason or "").strip():
        raise AutopilotError("a change to the Review dial needs a reason")

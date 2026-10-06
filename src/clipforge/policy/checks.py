"""The gate over queued records (S2 spec §5.1): what the assisted path asks at each pick, and
the read-only `policy dry-run` the owner runs before turning GATE_ENFORCE on (log #461)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from clipforge.accounts.blueprints import load_blueprint
from clipforge.models import Account, GateResult, PolicyDryRun, PolicyHold, PostRecord, Source
from clipforge.policy.gate import codes, gate
from clipforge.posting.backend import Posting
from clipforge.posting.captions import copy_for
from clipforge.posting.queue import eligible


def require_credit(blueprints_dir: Path, blueprint: str) -> bool:
    """The blueprint's compliance profile; a missing or broken blueprint leaves it to the
    source kind."""
    try:
        return load_blueprint(blueprints_dir, blueprint).compliance.require_credit
    except Exception:
        return False


def check_record(
    posting: Posting, blueprints_dir: Path, account: Account, source: Source | None,
    record: PostRecord, now: datetime,
) -> GateResult:  # fmt: skip
    """The gate on one queued record, with today's copy and the other accounts' planned (sent)
    or posted clips of the same video. Reads only; may raise a database error."""
    item = record.item
    shared = posting.repo.records_for_source(item.clip.source_hash) if item.clip else []
    others = [r.item for r in shared if r.posted or r.sends]
    return gate(item, account, source, copy_for(item, account, source, record.platforms), others,
                require_credit=require_credit(blueprints_dir, account.blueprint),
                platforms=record.platforms, now=now)  # fmt: skip


def dry_run(
    posting: Posting, blueprints_dir: Path, now: datetime, account_id: str | None = None
) -> PolicyDryRun:
    """The gate over every eligible queued item (of one account, or all); writes nothing."""
    accounts = [a for a in posting.accounts() if account_id in (None, a.id)]
    checked = 0
    held: list[PolicyHold] = []
    for account in sorted(accounts, key=lambda a: a.id):
        sources: dict[str | None, Source | None] = {}
        for record in posting.repo.records(account.id):
            if not eligible(record, now):
                continue
            sid = record.item.source_id
            if sid not in sources:
                sources[sid] = posting.source(sid) if sid is not None else None
            result = check_record(posting, blueprints_dir, account, sources[sid], record, now)
            checked += 1
            if result.violations:
                held.append(PolicyHold(ref=record.item.id, account_id=account.id,
                                       codes=codes(result)))  # fmt: skip
    return PolicyDryRun(checked=checked, would_hold=held)

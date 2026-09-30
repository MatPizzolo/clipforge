"""ADR-24: keep the posting state alive against Modal Dict's 7-day expiry. A daily `touch`
reads every durable key, `snapshot` writes the queue to the Volume, and `restore` puts back
keys that expired. Modal-free."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

from clipforge.db.engine import Database, redact
from clipforge.models import VerifyReport
from clipforge.pipeline.deps import KV
from clipforge.posting.repo import PAUSED_KEY, PREFIX

log = logging.getLogger(__name__)

KEEP_PREFIXES = (PREFIX, "job:")
KEEP_KEYS = (PAUSED_KEY,)


def _snapshot_dir(root: Path) -> Path:
    return root / "posting" / "snapshots"


def touch(kv: KV) -> int:
    """`get` every post/job/paused key, which counts as activity for the expiry timer."""
    count = 0
    for key in kv.keys():  # noqa: SIM118 (a KV method, not a dict)
        if key.startswith(KEEP_PREFIXES) or key in KEEP_KEYS:
            kv.get(key)
            count += 1
    return count


def snapshot(kv: KV, root: Path, now: datetime, keep: int = 14) -> tuple[Path, int]:
    """Write every `post:*` key (and the paused flag, for the record) to
    `<root>/posting/snapshots/<UTC date>.json`, then keep only the newest `keep` files.
    Returns the path and how many keys it holds."""
    data = {key: value for key, value in kv.items() if key.startswith(PREFIX) or key in KEEP_KEYS}
    folder = _snapshot_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now.astimezone(UTC):%Y-%m-%d}.json"
    tmp = folder / f".{path.name}.tmp"
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)
    for old in sorted(folder.glob("????-??-??.json"))[:-keep]:
        old.unlink(missing_ok=True)
    return path, len(data)


def _read(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError):
        log.warning("skipping unreadable posting snapshot %s", path.name)
        return None
    return data


def newest_snapshot(root: Path) -> dict[str, object] | None:
    folder = _snapshot_dir(root)
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob("????-??-??.json"), reverse=True):
        data = _read(path)
        if data is not None:
            return data
    return None


def restore(kv: KV, root: Path, day: date | None = None) -> int:
    """Put back `post:*` keys missing from the Dict, from the snapshot of `day` (UTC), or from
    the newest readable snapshot when no day is given. After an outage of about a week, the
    newest snapshot already lacks the expired keys, so pass the last good day. Never
    overwrites, and never restores `posting:paused` (`/go` deletes it on purpose)."""
    folder = _snapshot_dir(root)
    if day is not None:
        path = folder / f"{day:%Y-%m-%d}.json"
        if not path.is_file():
            log.warning("no posting snapshot for %s", path.name)
            return 0
        candidates = [path]
    elif folder.is_dir():
        candidates = sorted(folder.glob("????-??-??.json"), reverse=True)
    else:
        return 0
    for path in candidates:
        data = _read(path)
        if data is None:
            continue
        restored = 0
        for key, value in data.items():
            if (
                key.startswith(PREFIX)
                and isinstance(value, str)
                and kv.put(key, value, skip_if_exists=True)
            ):
                restored += 1
        return restored
    return 0


def verify_daily(kv: KV, db: Database | None, account_id: str) -> VerifyReport | None:
    """The daily Dict-versus-Postgres check for the keepalive cron. A no-op without a database,
    and it never raises: a failure is logged (redacted) and returns None."""
    if db is None:
        return None
    from clipforge.posting.migrate import verify_posting

    try:
        report = verify_posting(kv, db, account_id)
    except Exception as exc:
        log.warning("posting verify failed: %s", redact(exc))
        return None
    log.info(
        "posting verify: %d dict / %d postgres items, %d differences",
        report.dict_items, report.postgres_items, report.differences,
    )  # fmt: skip
    for line in report.first:
        log.warning("posting verify: %s", line)
    return report

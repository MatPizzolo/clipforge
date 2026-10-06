"""The hook-weight freeze (ADR-50; S3c spec §4.4). S3c's experiment start, stop and decide call it
inside their transaction; the hooks build implements it. One home, shared by S3c-3 and HK-1."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection


class HookFreezer(Protocol):
    def freeze(self, conn: Connection, account_id: str, experiment_id: int) -> None: ...
    def release(self, conn: Connection, account_id: str, experiment_id: int) -> None: ...


class NoHookFreezer:
    """Until the hooks build deploys: nothing to freeze."""

    def freeze(self, conn: Connection, account_id: str, experiment_id: int) -> None:
        return None

    def release(self, conn: Connection, account_id: str, experiment_id: int) -> None:
        return None

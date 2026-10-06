"""Binds the pipeline's interfaces to Modal objects and builds `Deps` (ADR-9, ADR-12).

The adapters are duck-typed (`Any`), so this module never imports modal and is tested with
fakes. app.py passes in the real `modal.Dict`, `modal.Volume` and step functions.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clipforge.bot.notifier import TelegramNotifier
from clipforge.bot.telegram import TelegramClient, TelegramSender
from clipforge.config import Settings
from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.jobs import DictJobStore, JobContext, Stored
from clipforge.models import (
    ClipOptions,
    ClipSpec,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    RenderedClip,
    SourceMedia,
    Transcript,
)
from clipforge.ops import ops_alerts
from clipforge.pipeline.deps import KV, Notifier, NullNotifier, Spawner, StageRunner, Volume
from clipforge.pipeline.steps import Deps, Step
from clipforge.posting.backend import build_posting
from clipforge.posting.repo import DualPostingRepo
from clipforge.stages.runner import producer_version

if TYPE_CHECKING:
    from clipforge.dispatch.tasks import DispatchCtx


class DictKV:
    """`KV` over a `modal.Dict` (values are the JSON strings DictJobStore writes)."""

    def __init__(self, d: Any) -> None:
        self._d = d

    def get(self, key: str) -> str | None:
        value = self._d.get(key)
        return None if value is None else str(value)

    def put(self, key: str, value: str, *, skip_if_exists: bool = False) -> bool:
        return bool(self._d.put(key, value, skip_if_exists=skip_if_exists))

    def delete(self, key: str) -> None:
        with contextlib.suppress(KeyError):
            self._d.pop(key)

    def keys(self) -> list[str]:
        return [str(key) for key in self._d.keys()]  # noqa: SIM118 (not a dict)

    def items(self) -> list[tuple[str, str]]:
        """One streaming read of the whole Dict (posting reads all `post:*` keys per tick)."""
        return [(str(key), str(value)) for key, value in self._d.items()]


class ModalVolume:
    def __init__(self, volume: Any) -> None:
        self._volume = volume

    def commit(self) -> None:
        self._volume.commit()

    def reload(self) -> None:
        self._volume.reload()


class FunctionSpawner:
    """Spawns the Modal function for a step: `fn.spawn(job_id)` or `fn.spawn(job_id, clip_id)`."""

    def __init__(self, functions: Mapping[Step, Any]) -> None:
        missing = [str(step) for step in Step if step not in functions]
        if missing:
            raise ValueError(f"no function for steps: {', '.join(missing)}")
        self._functions = dict(functions)

    def spawn(self, step: str, job_id: str, clip_id: str | None = None) -> None:
        function = self._functions[Step(step)]
        if clip_id is None:
            function.spawn(job_id)
        else:
            function.spawn(job_id, clip_id)


class UnavailableStages:
    """For containers that only create, read and resume jobs (web, sweeper, smoke)."""

    def _fail(self) -> RuntimeError:
        return RuntimeError("pipeline stages are not available in this container")

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]:
        raise self._fail()

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]:
        raise self._fail()

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]:
        raise self._fail()

    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        raise self._fail()

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]:
        raise self._fail()


def telegram_sender(settings: Settings) -> TelegramClient | None:
    if settings.telegram_bot_token is None:
        return None
    return TelegramClient(settings.telegram_bot_token.get_secret_value())


def notifier_factory(
    settings: Settings, store: DictJobStore, root: Path, sender: TelegramSender | None
) -> Callable[[Job], Notifier]:
    def build(job: Job) -> Notifier:
        if job.input.notify is None or sender is None:
            return NullNotifier()
        return TelegramNotifier(sender, job.input.notify, store, settings, root)

    return build


def build_deps(
    settings: Settings,
    *,
    kv: KV,
    volume: Volume,
    spawner: Spawner,
    stages: StageRunner,
    sender: TelegramSender | None,
    db: Database | None = None,
) -> Deps:
    store = DictJobStore(kv)
    root = settings.jobs_root
    ops = ops_alerts(kv, sender, settings)
    posting = build_posting(settings, kv, db)
    if ops is not None and isinstance(posting.repo, DualPostingRepo):
        posting.repo.on_failure = lambda action, error: ops.alert(
            f"Posting mirror write ({action}) failed: {error}. `clipforge posting verify` "
            "shows the drift.", "mirror", action)  # fmt: skip
    return Deps(
        store=store,
        volume=volume,
        spawner=spawner,
        stages=stages,
        root=root,
        notifier_for=notifier_factory(settings, store, root, sender),
        posting=posting,
        jobs_db=JobsRepo(db) if db is not None else None,
        version=producer_version(settings),
        build=settings.git_sha or None,
        ops=ops,
    )


def build_dispatch_ctx(
    settings: Settings,
    deps: Deps,
    sender: TelegramSender | None,
    spawn: Callable[[str, str], None],
    db: Callable[[], Database | None],
) -> DispatchCtx:
    """The dispatcher's context (ADR-27): the same `Posting` and ops alerts `posting_tick` used
    (built by `build_deps`), so with no DATABASE_URL the env account posts exactly as before."""
    from clipforge.bot.context import BotContext
    from clipforge.dispatch.tasks import DispatchCtx
    from clipforge.posting.backend import posting_of

    bot = BotContext(settings, sender, deps) if sender is not None else None
    return DispatchCtx(settings=settings, kv=deps.store.kv, posting=posting_of(deps), bot=bot,
                       spawn=spawn, ops=deps.ops, db=db)  # fmt: skip

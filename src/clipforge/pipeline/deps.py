"""Interfaces the step chain depends on, with in-memory versions for tests (ADR-12, ADR-14).

app.py binds the real ones (modal.Dict, modal.Volume, Function.spawn, the Telegram notifier).
Nothing in this package imports Modal.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from clipforge.models import (
    ClipOptions,
    ClipSpec,
    ClipState,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    RenderedClip,
    SourceMedia,
    Transcript,
)

if TYPE_CHECKING:  # jobs imports this module at runtime; avoid the cycle
    from clipforge.jobs import JobContext, Stored

log = logging.getLogger(__name__)


class KV(Protocol):
    """String key-value store with an atomic set-if-absent (modal.Dict in production)."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str, *, skip_if_exists: bool = False) -> bool: ...

    def delete(self, key: str) -> None: ...

    def keys(self) -> Iterable[str]: ...

    def items(self) -> Iterable[tuple[str, str]]: ...


class MemoryKV:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: str, *, skip_if_exists: bool = False) -> bool:
        with self._lock:
            if skip_if_exists and key in self._data:
                return False
            self._data[key] = value
            return True

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._data)

    def items(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._data.items())


class Volume(Protocol):
    def commit(self) -> None: ...

    def reload(self) -> None: ...


@dataclass
class NullVolume:
    commits: int = 0
    reloads: int = 0

    def commit(self) -> None:
        self.commits += 1

    def reload(self) -> None:
        self.reloads += 1


@dataclass(frozen=True)
class SpawnCall:
    step: str
    job_id: str
    clip_id: str | None = None


class Spawner(Protocol):
    def spawn(self, step: str, job_id: str, clip_id: str | None = None) -> None: ...


class QueueSpawner:
    """Records spawns instead of running them; tests drain `queue` (deque ops are thread-safe).

    `spawned` keeps every spawn ever made, so tests can count duplicates after draining.
    """

    def __init__(self) -> None:
        self.queue: deque[SpawnCall] = deque()
        self.spawned: list[SpawnCall] = []

    def spawn(self, step: str, job_id: str, clip_id: str | None = None) -> None:
        call = SpawnCall(step, job_id, clip_id)
        self.spawned.append(call)  # list.append is atomic under the GIL
        self.queue.append(call)


class Notifier(Protocol):
    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None: ...

    def done(self, job: Job) -> None: ...

    def failed(self, job: Job) -> None: ...


class NullNotifier:
    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        return None

    def done(self, job: Job) -> None:
        return None

    def failed(self, job: Job) -> None:
        return None


@dataclass
class RecordingNotifier:
    events: list[tuple[str, str, str | None]] = field(default_factory=list)

    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        self.events.append(("clip_ready", job.job_id, clip.clip_id))

    def done(self, job: Job) -> None:
        self.events.append(("done", job.job_id, None))

    def failed(self, job: Job) -> None:
        self.events.append(("failed", job.job_id, None))


@dataclass
class SafeNotifier:
    """Logs notifier failures instead of failing the step (ADR-14)."""

    inner: Notifier

    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        try:
            self.inner.clip_ready(job, clip, rendered)
        except Exception:
            log.exception("notifier.clip_ready failed for %s/%s", job.job_id, clip.clip_id)

    def done(self, job: Job) -> None:
        try:
            self.inner.done(job)
        except Exception:
            log.exception("notifier.done failed for %s", job.job_id)

    def failed(self, job: Job) -> None:
        try:
            self.inner.failed(job)
        except Exception:
            log.exception("notifier.failed failed for %s", job.job_id)


class StageRunner(Protocol):
    """The pipeline stages as the step chain calls them (real ones arrive in Plan 2).

    Each returns its output plus the ref of the cached result.json (via `cached_stage`).
    """

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]: ...

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]: ...

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]: ...

    def clip(
        self, ctx: JobContext, spec: ClipSpec, transcript: Transcript
    ) -> Stored[RenderedClip]: ...

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]: ...

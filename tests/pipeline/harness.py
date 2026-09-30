"""Runs the step chain in-process: MemoryKV, NullVolume, QueueSpawner, fake stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from clipforge.jobs import DictJobStore, new_job_id, utcnow
from clipforge.models import Job, JobInput
from clipforge.pipeline.deps import MemoryKV, NullVolume, QueueSpawner, RecordingNotifier
from clipforge.pipeline.steps import Deps, Step, dispatch
from clipforge.posting.backend import dict_posting
from tests.dbhelpers import make_account
from tests.pipeline.fakes import FakeStages

SOURCE_URL = "https://media.example.com/episode.mp4"


@dataclass
class Harness:
    root: Path
    store: DictJobStore
    spawner: QueueSpawner
    notifier: RecordingNotifier
    stages: FakeStages
    volume: NullVolume
    deps: Deps
    retries_seen: int = field(default=0)

    @classmethod
    def build(cls, root: Path, stages: FakeStages | None = None) -> Harness:
        kv = MemoryKV()
        store = DictJobStore(kv)
        spawner = QueueSpawner()
        notifier = RecordingNotifier()
        volume = NullVolume()
        fake = stages or FakeStages()
        deps = Deps(
            store=store,
            volume=volume,
            spawner=spawner,
            stages=fake,
            root=root,
            notifier_for=lambda job: notifier,
            posting=dict_posting(kv, make_account()),
        )
        return cls(root, store, spawner, notifier, fake, volume, deps)

    def submit(self, **options: Any) -> str:
        """Create a job the way service.create_job will (Task 7) and queue its ingest step."""
        now = utcnow()
        # Chain tests exercise fan-out, not selection: 5 clips unless a test says otherwise
        # (n=None selects automatically by score).
        options = {"n": 5, **options}
        job_input = JobInput.model_validate(
            {"source_url": SOURCE_URL, "permission": "own", "options": options}
        )
        job = Job(
            job_id=new_job_id(SOURCE_URL, now), input=job_input, created_at=now, updated_at=now
        )
        self.store.save(job)
        self.spawner.spawn(Step.INGEST, job.job_id)
        return job.job_id

    def run(self, max_calls: int = 300) -> None:
        """Run queued spawns until idle, re-running a raising step like Modal Retries would."""
        calls = 0
        while self.spawner.queue:
            call = self.spawner.queue.popleft()
            calls += 1
            if calls > max_calls:
                raise AssertionError("the chain did not settle")
            try:
                dispatch(self.deps, call.step, call.job_id, call.clip_id)
            except Exception:
                self.retries_seen += 1
                self.spawner.queue.appendleft(call)

    def run_until(self, step: Step) -> None:
        """Run queued spawns until the next one is `step` (or the queue is empty)."""
        while self.spawner.queue and self.spawner.queue[0].step != step:
            call = self.spawner.queue.popleft()
            dispatch(self.deps, call.step, call.job_id, call.clip_id)

    def event_kinds(self) -> list[str]:
        return [kind for kind, _, _ in self.notifier.events]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness.build(tmp_path)

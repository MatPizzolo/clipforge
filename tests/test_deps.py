import threading
from datetime import UTC, datetime

from clipforge.models import ClipState, Job, JobInput, Permission
from clipforge.pipeline.deps import (
    MemoryKV,
    NullVolume,
    QueueSpawner,
    RecordingNotifier,
    SafeNotifier,
    SpawnCall,
)

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def test_memory_kv_set_if_absent_is_atomic() -> None:
    kv = MemoryKV()
    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda: results.append(kv.put("claim", "1", skip_if_exists=True)))
        for _ in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    assert kv.put("claim", "2") is True and kv.get("claim") == "2"
    kv.delete("claim")
    kv.delete("claim")  # deleting a missing key is fine
    assert kv.get("claim") is None and list(kv.keys()) == []


def test_null_volume_and_queue_spawner() -> None:
    volume = NullVolume()
    volume.commit()
    volume.reload()
    assert (volume.commits, volume.reloads) == (1, 1)
    spawner = QueueSpawner()
    spawner.spawn("clip", "j1", "clip_01")
    assert list(spawner.queue) == [SpawnCall("clip", "j1", "clip_01")]


class Exploding:
    def clip_ready(self, job: Job, clip: ClipState, rendered: object) -> None:
        raise RuntimeError("telegram down")

    def done(self, job: Job) -> None:
        raise RuntimeError("telegram down")

    def failed(self, job: Job) -> None:
        raise RuntimeError("telegram down")


def test_safe_notifier_swallows_errors() -> None:
    job = Job(
        job_id="j1",
        input=JobInput(telegram_file_id="f", permission=Permission.OWN),
        created_at=NOW,
        updated_at=NOW,
    )
    clip = ClipState(clip_id="clip_01", spec_ref="j1/clips/clip_01.json", updated_at=NOW)
    safe = SafeNotifier(Exploding())  # type: ignore[arg-type]
    safe.clip_ready(job, clip, None)  # type: ignore[arg-type]
    safe.done(job)
    safe.failed(job)
    recorder = RecordingNotifier()
    SafeNotifier(recorder).done(job)
    assert recorder.events == [("done", "j1", None)]

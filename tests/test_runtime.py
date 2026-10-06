"""Runtime wiring with Modal-shaped fakes: the adapters, the notifier choice, a whole chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clipforge.bot.notifier import TelegramNotifier
from clipforge.jobs import DictJobStore
from clipforge.models import JobInput, JobStatus, Permission, TelegramTarget
from clipforge.pipeline.deps import NullNotifier, NullVolume, QueueSpawner
from clipforge.pipeline.steps import Step, dispatch
from clipforge.runtime import (
    DictKV,
    FunctionSpawner,
    ModalVolume,
    UnavailableStages,
    build_deps,
    notifier_factory,
    telegram_sender,
)
from clipforge.service import create_job
from clipforge.stages.runner import producer_version
from tests.bot.fakes import FakeSender, make_settings
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import SOURCE_URL


class FakeModalDict:
    """modal.Dict semantics: get → default, pop raises KeyError, put returns a bool."""

    def __init__(self) -> None:
        self.data: dict[Any, Any] = {}

    def get(self, key: Any, default: Any = None) -> Any:
        return self.data.get(key, default)

    def put(self, key: Any, value: Any, *, skip_if_exists: bool = False) -> bool:
        if skip_if_exists and key in self.data:
            return False
        self.data[key] = value
        return True

    def pop(self, key: Any) -> Any:
        return self.data.pop(key)

    def keys(self) -> Any:
        return iter(list(self.data))

    def items(self) -> Any:
        return iter(list(self.data.items()))


class FakeFunction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def spawn(self, *args: str) -> None:
        self.calls.append(args)


def test_dict_kv_matches_the_kv_contract() -> None:
    kv = DictKV(FakeModalDict())
    assert kv.get("a") is None
    assert kv.put("a", "1") and kv.get("a") == "1"
    assert kv.put("a", "2", skip_if_exists=True) is False and kv.get("a") == "1"
    kv.delete("a")
    kv.delete("missing")  # no KeyError
    kv.put("b", "x")
    assert kv.keys() == ["b"]
    store = DictJobStore(kv)
    assert store.claim("J", "package") and not store.claim("J", "package")


def test_modal_volume_forwards() -> None:
    inner = NullVolume()
    volume = ModalVolume(inner)
    volume.commit()
    volume.reload()
    assert (inner.commits, inner.reloads) == (1, 1)


def test_function_spawner_routes_by_step() -> None:
    functions = {step: FakeFunction() for step in Step}
    spawner = FunctionSpawner(functions)
    spawner.spawn("ingest", "J")
    spawner.spawn(Step.CLIP, "J", "clip_01")
    assert functions[Step.INGEST].calls == [("J",)]
    assert functions[Step.CLIP].calls == [("J", "clip_01")]


def test_function_spawner_needs_every_step() -> None:
    with pytest.raises(ValueError, match="package"):
        FunctionSpawner({step: FakeFunction() for step in Step if step is not Step.PACKAGE})


def test_unavailable_stages_raise() -> None:
    with pytest.raises(RuntimeError, match="not available"):
        UnavailableStages().ingest(None, None)  # type: ignore[arg-type]


def test_telegram_sender_needs_a_token(tmp_path: Path) -> None:
    assert telegram_sender(make_settings(tmp_path, telegram_bot_token=None)) is None
    assert telegram_sender(make_settings(tmp_path)) is not None


def test_notifier_factory_picks_telegram_only_for_telegram_jobs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = DictJobStore(DictKV(FakeModalDict()))
    deps = build_deps(
        settings,
        kv=store.kv,
        volume=NullVolume(),
        spawner=QueueSpawner(),
        stages=FakeStages(),
        sender=FakeSender(),
    )
    plain = create_job(deps, JobInput(source_url=SOURCE_URL, permission=Permission.OWN))
    telegram = create_job(
        deps,
        JobInput(
            source_url=SOURCE_URL, permission=Permission.OWN, notify=TelegramTarget(chat_id=7)
        ),
    )
    build = notifier_factory(settings, store, tmp_path, FakeSender())
    assert isinstance(build(plain), NullNotifier)
    assert isinstance(build(telegram), TelegramNotifier)
    assert isinstance(notifier_factory(settings, store, tmp_path, None)(telegram), NullNotifier)


def _run_chain(settings_root: Path, sender: FakeSender) -> tuple[str, DictJobStore]:
    spawner = QueueSpawner()
    deps = build_deps(
        make_settings(settings_root),
        kv=DictKV(FakeModalDict()),
        volume=ModalVolume(NullVolume()),
        spawner=spawner,
        stages=FakeStages(),
        sender=sender,
    )
    job_input = JobInput(
        source_url=SOURCE_URL, permission=Permission.OWN, notify=TelegramTarget(chat_id=7)
    )
    job = create_job(deps, job_input)
    for _ in range(100):
        if not spawner.queue:
            break
        call = spawner.queue.popleft()
        dispatch(deps, call.step, call.job_id, call.clip_id)
    return job.job_id, deps.store


def test_build_deps_runs_a_whole_telegram_job(tmp_path: Path) -> None:
    sender = FakeSender()
    job_id, store = _run_chain(tmp_path, sender)
    assert store.get(job_id).status is JobStatus.DONE
    # automatic selection: the fake scores 0.9 and 0.8 reach the 0.80 threshold
    assert len(sender.videos) == 2 and sender.messages[-1][1].startswith("2 of 2 clips")


def test_failing_telegram_never_fails_the_job(tmp_path: Path) -> None:
    job_id, store = _run_chain(tmp_path, FakeSender(fail=True))
    job = store.get(job_id)
    assert job.status is JobStatus.DONE and job.output_zip is not None


def test_dict_kv_items() -> None:
    fake = FakeModalDict()
    kv = DictKV(fake)
    kv.put("a", "1")
    kv.put("b", "2")
    assert sorted(kv.items()) == [("a", "1"), ("b", "2")]


def _deps(tmp_path: Path, **overrides: Any) -> Any:
    return build_deps(
        make_settings(tmp_path, **overrides),
        kv=DictKV(FakeModalDict()),
        volume=NullVolume(),
        spawner=QueueSpawner(),
        stages=FakeStages(),
        sender=None,
    )


def test_build_deps_sets_the_derived_producer_version_and_the_build(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, git_sha="abc123")
    deps = _deps(tmp_path, git_sha="abc123")
    assert deps.version == producer_version(settings)
    assert deps.build == "abc123"
    assert _deps(tmp_path, git_sha="").build is None
    assert _deps(tmp_path, git_sha=None).build is None


def test_build_deps_wires_the_hook_library_only_with_a_database(tmp_path: Path) -> None:
    from clipforge.db.engine import Database, make_engine
    from clipforge.hooks.library import HookLibrary

    deps = _deps(tmp_path)
    assert deps.hooks is None and deps.hook_variants is False
    db = Database(make_engine("postgresql://u:p@127.0.0.1:1/db"))  # never connected
    with_db = build_deps(make_settings(tmp_path, hook_variants=True), kv=DictKV(FakeModalDict()),
                         volume=NullVolume(), spawner=QueueSpawner(), stages=FakeStages(),
                         sender=None, db=db)  # fmt: skip
    assert isinstance(with_db.hooks, HookLibrary) and with_db.hook_variants is True

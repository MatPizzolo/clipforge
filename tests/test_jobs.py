import threading
from pathlib import Path

import pytest

from clipforge.jobs import (
    DictJobStore,
    JobContext,
    Stored,
    cached_stage,
    load_ref,
    merged_cost,
    new_job_id,
    utcnow,
)
from clipforge.models import (
    CaptionFiles,
    ClipState,
    Job,
    JobInput,
    Permission,
    StageCost,
    StageName,
)
from clipforge.pipeline.deps import MemoryKV

JOB_ID = "20260923-aaaaaaaa-0001"


@pytest.fixture
def store() -> DictJobStore:
    return DictJobStore(MemoryKV())


@pytest.fixture
def ctx(tmp_path: Path, store: DictJobStore) -> JobContext:
    now = utcnow()
    job_input = JobInput.model_validate(
        {"source_url": "https://media.example.com/a.mp4", "permission": Permission.OWN}
    )
    store.save(Job(job_id=JOB_ID, input=job_input, created_at=now, updated_at=now))
    return JobContext(job_id=JOB_ID, root=tmp_path, store=store)


def captions(out_dir: Path, ctx: JobContext) -> CaptionFiles:
    ass = out_dir / "clip.ass"
    ass.write_text("[Script Info]")
    return CaptionFiles(
        clip_id="clip_01",
        ass_path=ctx.rel(ass),
        srt_path=ctx.rel(out_dir / "clip.srt"),
        style="default",
        offset_s=10.0,
    )


def add_clip(store: DictJobStore, clip_id: str = "clip_01") -> ClipState:
    state = ClipState(
        clip_id=clip_id, spec_ref=f"{JOB_ID}/clips/{clip_id}.json", updated_at=utcnow()
    )
    assert store.create_clip(JOB_ID, state)
    return state


def test_new_job_id_format() -> None:
    job_id = new_job_id("https://example.com/v.mp4")
    day, digest, rand = job_id.split("-")
    assert len(day) == 8 and len(digest) == 8 and len(rand) == 4
    assert new_job_id("x").split("-")[1] == new_job_id("x").split("-")[1]


def test_job_round_trip_and_listing(ctx: JobContext, store: DictJobStore) -> None:
    assert store.get(JOB_ID).job_id == JOB_ID
    with pytest.raises(KeyError):
        store.get("nope")
    add_clip(store)
    store.claim(JOB_ID, "package")
    store.incr_attempts(JOB_ID, "ingest")
    assert store.list_job_ids() == [JOB_ID]  # clip/claim/attempt keys are not jobs


def test_clip_create_is_set_if_absent(ctx: JobContext, store: DictJobStore) -> None:
    first = add_clip(store)
    again = first.model_copy(update={"spec_ref": "other"})
    assert store.create_clip(JOB_ID, again) is False
    assert store.get_clip(JOB_ID, "clip_01").spec_ref == first.spec_ref
    add_clip(store, "clip_02")
    assert [c.clip_id for c in store.clips(JOB_ID, ["clip_02", "clip_01"])] == [
        "clip_02",
        "clip_01",
    ]
    with pytest.raises(KeyError):
        store.get_clip(JOB_ID, "clip_09")


def test_attempts_and_claims(ctx: JobContext, store: DictJobStore) -> None:
    assert store.incr_attempts(JOB_ID, "ingest") == 1
    assert store.incr_attempts(JOB_ID, "ingest") == 2
    assert store.incr_attempts(JOB_ID, "clip", "clip_01") == 1
    assert store.incr_attempts("other-job", "ingest") == 1
    store.reset_attempts(JOB_ID)
    assert store.incr_attempts(JOB_ID, "ingest") == 1
    assert store.incr_attempts("other-job", "ingest") == 2  # other jobs untouched
    assert store.claim(JOB_ID, "failed") is True
    assert store.claim(JOB_ID, "failed") is False
    store.release(JOB_ID, "failed")
    assert store.claim(JOB_ID, "failed") is True


def test_report_updates_job_progress(ctx: JobContext) -> None:
    before = ctx.job().updated_at
    ctx.report(StageName.TRANSCRIBE, 150, "almost")
    job = ctx.job()
    assert job.progress is not None and job.progress.pct == 100  # clamped
    assert job.progress.stage is StageName.TRANSCRIBE
    assert job.updated_at >= before


def test_clip_context_writes_the_clip_key(ctx: JobContext, store: DictJobStore) -> None:
    add_clip(store)
    clip_ctx = JobContext(job_id=JOB_ID, root=ctx.root, store=store, clip_id="clip_01")
    clip_ctx.report(StageName.RENDER, 40, "encoding")
    clip_ctx.record_cost(StageCost(stage=StageName.RENDER, usd_estimate=0.001))
    state = store.get_clip(JOB_ID, "clip_01")
    assert state.progress is not None and state.progress.pct == 40
    assert [c.clip_id for c in state.cost] == ["clip_01"]
    assert ctx.job().progress is None and ctx.job().cost.stages == []


def test_record_cost_accumulates_across_threads(ctx: JobContext) -> None:
    def add() -> None:
        ctx.record_cost(StageCost(stage=StageName.HIGHLIGHTS, usd_estimate=0.01, llm_calls=1))

    threads = [threading.Thread(target=add) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    cost = ctx.job().cost
    assert len(cost.stages) == 20
    assert cost.total_usd == pytest.approx(0.20)


def test_cached_stage_computes_once_and_returns_ref(ctx: JobContext) -> None:
    calls = 0

    def compute(out_dir: Path) -> CaptionFiles:
        nonlocal calls
        calls += 1
        return captions(out_dir, ctx)

    first = cached_stage(ctx, StageName.CAPTIONS, "k1", CaptionFiles, compute)
    second = cached_stage(ctx, StageName.CAPTIONS, "k1", CaptionFiles, compute)
    assert isinstance(first, Stored)
    assert first == second and calls == 1
    assert first.ref == "cache/captions/k1/result.json"
    assert load_ref(ctx.root, first.ref, CaptionFiles) == first.value
    assert first.value.ass_path == "cache/captions/k1/clip.ass"
    assert [c.cached for c in ctx.job().cost.stages] == [True]


def test_cached_stage_recovers_from_partial_and_invalid_entries(ctx: JobContext) -> None:
    out_dir = ctx.root / "cache" / "captions" / "k2"
    out_dir.mkdir(parents=True)
    (out_dir / "leftover.tmp").write_text("partial")  # crash before result.json

    result = cached_stage(ctx, StageName.CAPTIONS, "k2", CaptionFiles, lambda d: captions(d, ctx))
    assert not (out_dir / "leftover.tmp").exists()

    (out_dir / "result.json").write_text('{"old_field": 1}')  # contract changed since
    again = cached_stage(ctx, StageName.CAPTIONS, "k2", CaptionFiles, lambda d: captions(d, ctx))
    assert again == result


def test_compute_failure_leaves_no_result(ctx: JobContext) -> None:
    def fail(out_dir: Path) -> CaptionFiles:
        raise RuntimeError("ffmpeg failed")

    with pytest.raises(RuntimeError):
        cached_stage(ctx, StageName.CAPTIONS, "k3", CaptionFiles, fail)
    assert not (ctx.root / "cache" / "captions" / "k3" / "result.json").exists()


def test_merged_cost_includes_clip_entries(ctx: JobContext, store: DictJobStore) -> None:
    add_clip(store)
    ctx.record_cost(StageCost(stage=StageName.TRANSCRIBE, usd_estimate=0.05))
    clip_ctx = JobContext(job_id=JOB_ID, root=ctx.root, store=store, clip_id="clip_01")
    clip_ctx.record_cost(StageCost(stage=StageName.RENDER, usd_estimate=0.01))
    job = store.get(JOB_ID).model_copy(update={"clip_ids": ["clip_01"]})
    cost = merged_cost(store, job)
    assert [c.stage for c in cost.stages] == [StageName.TRANSCRIBE, StageName.RENDER]
    assert cost.total_usd == pytest.approx(0.06)


def test_is_job_id() -> None:
    from clipforge.jobs import is_job_id, new_job_id

    assert is_job_id(new_job_id("https://a.example/v.mp4"))
    for bad in ["", "..", "../20260923-aaaaaaaa-0001", "20260923-aaaaaaaa-0001/x", "J"]:
        assert not is_job_id(bad)


def test_claim_update_once() -> None:
    from clipforge.jobs import DictJobStore
    from clipforge.pipeline.deps import MemoryKV

    kv = MemoryKV()
    store = DictJobStore(kv)
    assert store.claim_update(10) and not store.claim_update(10) and store.claim_update(11)
    assert "tg:update:10" in kv.keys()  # noqa: SIM118 (KV protocol)
    assert store.list_job_ids() == []  # update claims are not jobs

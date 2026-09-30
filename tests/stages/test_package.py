import zipfile
from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.jobs import utcnow
from clipforge.models import ClipState, JobInput, JobMetadata, RenderedClip, StageCost, StageName
from clipforge.stages import package
from tests.stages.helpers import JOB_ID, make_ctx
from tests.test_models import make_rendered, make_source, make_spec, make_transcript

VERSIONS = {"ingest": "1", "render": "1"}


def rendered(root: Path, clip_id: str, rank: int, score: float) -> RenderedClip:
    base = make_rendered()
    spec = make_spec().model_copy(
        update={
            "clip_id": clip_id,
            "rank": rank,
            "candidate": make_spec().candidate.model_copy(update={"score": score}),
        }
    )
    video = root / "cache" / "render" / clip_id / "clip.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4 " + clip_id.encode())
    srt = video.with_suffix(".srt")
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    return base.model_copy(
        update={
            "clip_id": clip_id,
            "spec": spec,
            "video_path": f"cache/render/{clip_id}/clip.mp4",
            "srt_path": f"cache/render/{clip_id}/clip.srt",
        }
    )


def test_package_layout_metadata_and_zip(tmp_path: Path) -> None:
    job_input = JobInput.model_validate(
        {
            "source_url": "https://cdn.example.com/ep.mp4",
            "permission": "cc_by",
            "source_credit": "Jane Doe, CC BY 4.0, https://example.com/ep",
        }
    )
    ctx = make_ctx(tmp_path, job_input)
    now = utcnow()
    for clip_id in ("clip_01", "clip_02"):
        state = ClipState(
            clip_id=clip_id,
            spec_ref="x",
            updated_at=now,
            cost=[StageCost(stage=StageName.RENDER, clip_id=clip_id, usd_estimate=0.01)],
        )
        ctx.store.save_clip(JOB_ID, state)
    ctx.record_cost(StageCost(stage=StageName.TRANSCRIBE, usd_estimate=0.05))
    job = ctx.job().model_copy(update={"clip_ids": ["clip_01", "clip_02"]})
    ctx.store.save(job)
    clips = [rendered(tmp_path, "clip_02", 2, 0.72), rendered(tmp_path, "clip_01", 1, 0.91)]
    settings = Settings(_env_file=None, jobs_root=tmp_path, git_sha="abc1234")

    result = package.run(
        ctx, job, make_source(), make_transcript(), clips, settings, VERSIONS
    ).value

    output = tmp_path / JOB_ID / "output"
    assert [c.dir for c in result.clips] == ["clip_01_score0.91", "clip_02_score0.72"]
    for name in ("clip_01_score0.91", "clip_02_score0.72"):
        assert {p.name for p in (output / name).iterdir()} == {
            "video.mp4",
            "captions.srt",
            "post.md",
        }
    assert (output / "clip_01_score0.91" / "video.mp4").read_bytes() == b"mp4 clip_01"

    meta = JobMetadata.model_validate_json((output / "metadata.json").read_text())
    assert meta.input.permission == "cc_by" and meta.versions.git_sha == "abc1234"
    assert meta.versions.stages == VERSIONS and meta.versions.highlight_prompt == "highlights_v1"
    assert meta.cost.total_usd == pytest.approx(0.07)  # transcribe + two clip renders
    assert [c.clip_id for c in meta.clips] == ["clip_01", "clip_02"]

    post = (output / "clip_01_score0.91" / "post.md").read_text()
    assert "Credit: Jane Doe, CC BY 4.0" in post and "Permission: cc_by" in post

    assert result.zip_path == f"{JOB_ID}/job.zip"
    with zipfile.ZipFile(tmp_path / result.zip_path) as zf:
        names = set(zf.namelist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in zf.infolist())
    assert names == {
        "metadata.json",
        *(
            f"{d}/{f}"
            for d in ("clip_01_score0.91", "clip_02_score0.72")
            for f in ("video.mp4", "captions.srt", "post.md")
        ),
    }

"""Package: the delivered folder (clips, post.md, metadata.json) and job.zip (ADR-3, ADR-13).

Output is job-scoped (`<job_id>/output/`), since it names this job's clips and ranks."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import clipforge
from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.hooks.rotation import rotation_note, stamp_for
from clipforge.jobs import JobContext, Stored, cached_stage, merged_cost, utcnow
from clipforge.models import (
    Job,
    JobMetadata,
    PackagedClip,
    PackageResult,
    RenderedClip,
    SourceMedia,
    StageName,
    Transcript,
    Versions,
)
from clipforge.stages.highlights import PROMPT_VERSION

STAGE_VERSION = "1"


def post_markdown(job: Job, clip: RenderedClip) -> str:
    candidate = clip.spec.candidate
    source = job.input.source_label or (
        str(job.input.source_url) if job.input.source_url else "uploaded file"
    )
    lines = [
        f"# {candidate.title}",
        "",
        f"**Hook:** {candidate.hook}",
        f"**Score:** {candidate.score:.2f} · rank {clip.spec.rank} · "
        f"{clip.spec.start:.1f}s to {clip.spec.end:.1f}s of the source",
        "",
        f"Source: {source}",
        f"Permission: {job.input.permission}",
    ]
    if job.input.source_credit:
        lines.append(f"Credit: {job.input.source_credit}")
    return "\n".join(lines) + "\n"


def run(
    ctx: JobContext,
    job: Job,
    source: SourceMedia,
    transcript: Transcript,
    rendered: list[RenderedClip],
    settings: Settings,
    stage_versions: dict[str, str],
    producer_version: str | None = None,
) -> Stored[PackageResult]:
    ordered = sorted(rendered, key=lambda r: r.spec.rank)
    key = cache_key(
        "package",
        STAGE_VERSION,
        [],
        {"job": job.job_id, "clips": ",".join(f"{r.clip_id}@{r.video_path}" for r in ordered)},
    )

    def compute(out_dir: Path) -> PackageResult:
        output = ctx.job_dir / "output"
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
        packaged: list[PackagedClip] = []
        for clip in ordered:
            name = f"{clip.clip_id}_score{clip.spec.candidate.score:.2f}"
            folder = output / name
            folder.mkdir()
            shutil.copyfile(ctx.path(clip.video_path), folder / "video.mp4")
            shutil.copyfile(ctx.path(clip.srt_path), folder / "captions.srt")
            (folder / "post.md").write_text(post_markdown(job, clip))
            stamp, _ = stamp_for(job.input.hooks, clip.spec.candidate.title, clip.hook,
                                 flag_on=settings.hook_variants)  # fmt: skip
            packaged.append(
                PackagedClip(
                    clip_id=clip.clip_id,
                    rank=clip.spec.rank,
                    dir=name,
                    video=f"{name}/video.mp4",
                    srt=f"{name}/captions.srt",
                    post_md=f"{name}/post.md",
                    start=clip.spec.start,
                    end=clip.spec.end,
                    score=clip.spec.candidate.score,
                    title=clip.spec.candidate.title,
                    hook=clip.spec.candidate.hook,
                    probe=clip.probe,
                    hook_stamp=stamp,
                )
            )
        metadata = JobMetadata(
            job_id=job.job_id,
            input=job.input,
            source=source,
            transcript_language=transcript.language,
            clips=packaged,
            cost=merged_cost(ctx.store, job),
            versions=Versions(
                git_sha=settings.git_sha,
                clipforge=clipforge.__version__,
                stages=stage_versions,
                highlight_prompt=PROMPT_VERSION,
                highlight_model=settings.highlight_model,
                whisper_model=transcript.model,
                producer_version=producer_version,
                hook_rotation=rotation_note(job.input.hooks, job.hooks_note),
            ),
            started_at=job.created_at,
            finished_at=utcnow(),
        )
        metadata_path = output / "metadata.json"
        metadata_path.write_text(metadata.model_dump_json(indent=2))

        zip_path = ctx.job_dir / "job.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(output).as_posix())
        ctx.report(StageName.PACKAGE, 100, f"{len(packaged)} clips packaged")
        return PackageResult(
            output_dir=ctx.rel(output),
            zip_path=ctx.rel(zip_path),
            metadata_path=ctx.rel(metadata_path),
            clips=packaged,
        )

    return cached_stage(ctx, StageName.PACKAGE, key, PackageResult, compute)

"""The whole chain on real stages: ffmpeg for real; fake transcriber and LLM (no GPU, no API)."""

import zipfile
from pathlib import Path

import httpx

from clipforge import ffmpeg
from clipforge.config import Settings
from clipforge.models import ClipOptions, JobInput, JobMetadata, JobStatus, Permission, StageName
from clipforge.prompts import load_prompt
from clipforge.service import create_job
from clipforge.stages import captions
from clipforge.stages.faces import YUNET_MODEL, YuNetDetector
from clipforge.stages.runner import STAGE_VERSIONS, PipelineStages, producer_version
from tests.builders import build_long_transcript, sentence_bounds
from tests.conftest import MediaFactory, requires_ffmpeg
from tests.pipeline.harness import Harness
from tests.stages.helpers import FakeLLM, FakeTranscriber, assert_vertical_clip, clip_json, upload


@requires_ffmpeg
def test_real_stages_end_to_end(tmp_path: Path, media: MediaFactory) -> None:
    rel = upload(tmp_path, media(width=640, height=360, duration_s=12.0))
    transcript = build_long_transcript(12.0)  # three sentences
    b = sentence_bounds(transcript)
    clips = clip_json((b[0][0], b[1][1], 0.9), (b[1][0], b[2][1], 0.8))
    keywords = '{"keywords": [1]}'
    llm = FakeLLM(lambda m: keywords if "emphasize" in m[0]["content"] else clips)
    settings = Settings(_env_file=None, jobs_root=tmp_path)
    stages = PipelineStages(
        settings=settings,
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        transcriber=FakeTranscriber(transcript),
        llm=llm,
        prompt=load_prompt("highlights_v1", settings.prompts_dir),
        keywords_prompt=load_prompt(captions.KEYWORDS_PROMPT, settings.prompts_dir),
        detector=YuNetDetector(settings.models_dir / YUNET_MODEL),
    )
    h = Harness.build(tmp_path, stages)  # type: ignore[arg-type]
    options = ClipOptions(n=2, min_len=5, max_len=9)
    job = create_job(h.deps, JobInput(source_path=rel, permission=Permission.OWN, options=options))
    h.run()

    done = h.store.get(job.job_id)
    assert done.status is JobStatus.DONE, done.error
    assert h.event_kinds().count("clip_ready") == 2 and h.event_kinds()[-1] == "done"
    assert done.output_zip is not None
    with zipfile.ZipFile(tmp_path / done.output_zip) as zf:
        videos = sorted(n for n in zf.namelist() if n.endswith("video.mp4"))
        assert videos == ["clip_01_score0.90/video.mp4", "clip_02_score0.80/video.mp4"]
        zf.extractall(tmp_path / "unzipped")
    for name in videos:
        assert_vertical_clip(ffmpeg.probe_info(tmp_path / "unzipped" / name), expected_s=6.7)

    meta = JobMetadata.model_validate_json((tmp_path / "unzipped" / "metadata.json").read_text())
    stages_costed = {c.stage for c in meta.cost.stages if not c.cached}
    assert {
        StageName.INGEST,
        StageName.TRANSCRIBE,
        StageName.HIGHLIGHTS,
        StageName.CAPTIONS,  # the key-word LLM call (ADR-18)
        StageName.RENDER,
    } <= stages_costed
    assert meta.versions.stages == STAGE_VERSIONS
    assert meta.versions.producer_version == producer_version(settings)
    tracks = [c for c in meta.cost.stages if c.stage is StageName.REFRAME]
    assert tracks, "reframe ran as a cached stage for the landscape source"

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from clipforge.models import (
    Account,
    AssetSource,
    CampaignRules,
    CaptionFiles,
    ChannelRef,
    ClipCandidate,
    ClipOptions,
    ClipOrigin,
    ClipSpec,
    ClipState,
    ClipStatus,
    ContentItem,
    CostSummary,
    CropBox,
    CropSegment,
    CropTrack,
    HighlightsResult,
    Job,
    JobInput,
    JobMetadata,
    JobStatus,
    JobView,
    LLMClip,
    LLMClipsResponse,
    PackagedClip,
    PackageResult,
    Permission,
    Platform,
    PlatformProfile,
    PostingSchedule,
    ProbeInfo,
    RenderedClip,
    Segment,
    Source,
    SourceMedia,
    SourcePermission,
    StageCost,
    StageName,
    TelegramTarget,
    TranscribeResult,
    Transcript,
    Versions,
    Word,
)

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def make_source() -> SourceMedia:
    return SourceMedia(
        video_path="work/ingest/abc/source.mp4",
        audio_path="work/ingest/abc/audio.wav",
        source_hash="f" * 64,
        source_url="https://www.youtube.com/watch?v=xyz",
        title="Episode 1",
        duration_s=1800.0,
        fps=30.0,
        width=1920,
        height=1080,
        video_codec="h264",
        size_bytes=400_000_000,
    )


def make_transcript() -> Transcript:
    words = [Word(text="Hello", start=0.0, end=0.4), Word(text="world.", start=0.5, end=0.9)]
    return Transcript(
        language="en",
        duration_s=1800.0,
        model="large-v3-turbo",
        segments=[Segment(start=0.0, end=0.9, text="Hello world.", words=words)],
    )


def make_candidate() -> ClipCandidate:
    return ClipCandidate(
        start=812.4,
        end=871.9,
        score=0.86,
        hook="Nobody tells you this.",
        title="The thing nobody tells you",
        reason="Bold claim with a payoff.",
        window_index=3,
        raw_start=812.0,
        raw_end=872.3,
    )


def make_spec() -> ClipSpec:
    c = make_candidate()
    return ClipSpec(
        clip_id="clip_01",
        rank=1,
        source=make_source(),
        start=c.start,
        end=c.end,
        candidate=c,
        options=ClipOptions(),
    )


def make_probe() -> ProbeInfo:
    return ProbeInfo(
        width=1080,
        height=1920,
        duration_s=59.5,
        video_duration_s=59.5,
        audio_duration_s=59.49,
        fps=30.0,
        video_codec="h264",
        pix_fmt="yuv420p",
        audio_codec="aac",
        n_video_streams=1,
        n_audio_streams=1,
        size_bytes=30_000_000,
    )


def make_rendered() -> RenderedClip:
    return RenderedClip(
        clip_id="clip_01",
        spec=make_spec(),
        video_path="work/render/k/clip_01.mp4",
        srt_path="work/captions/k/clip_01.srt",
        encoder="libx264",
        probe=make_probe(),
    )


def make_packaged() -> PackagedClip:
    return PackagedClip(
        clip_id="clip_01",
        rank=1,
        dir="clip_01_score0.86",
        video="clip_01_score0.86/video.mp4",
        srt="clip_01_score0.86/captions.srt",
        post_md="clip_01_score0.86/post.md",
        start=812.4,
        end=871.9,
        score=0.86,
        title="The thing nobody tells you",
        hook="Nobody tells you this.",
        probe=make_probe(),
    )


def make_versions() -> Versions:
    return Versions(
        git_sha=None,
        clipforge="0.1.0",
        stages={"ingest": "1"},
        highlight_prompt="highlights_v1",
        highlight_model="claude-haiku-4-5",
        whisper_model="large-v3-turbo",
    )


def test_versions_without_producer_version_still_validate() -> None:
    data = make_versions().model_dump(mode="json")
    data.pop("producer_version")
    assert Versions.model_validate(data).producer_version is None


def make_clip_state() -> ClipState:
    return ClipState(
        clip_id="clip_01", spec_ref="20260923-ffffffff-ab12/clips/clip_01.json", updated_at=NOW
    )


def make_input(**kwargs: object) -> JobInput:
    data: dict[str, object] = {"source_url": "https://www.youtube.com/watch?v=xyz"}
    data.update(kwargs)
    data.setdefault("permission", Permission.OWN)
    return JobInput.model_validate(data)


ALL_SAMPLES: list[BaseModel] = [
    TelegramTarget(chat_id=42),
    make_clip_state(),
    JobView(
        job_id="20260923-ffffffff-ab12",
        status=JobStatus.RUNNING,
        stage=StageName.RENDER,
        clips=[make_clip_state()],
        cost=CostSummary(),
        created_at=NOW,
        updated_at=NOW,
    ),
    make_input(),
    make_source(),
    make_transcript(),
    TranscribeResult(transcript=make_transcript(), gpu_s=120.0, load_s=20.0, gpu_type="L4"),
    LLMClipsResponse(clips=[LLMClip(start=1, end=40, score=0.9, hook="h", title="t", reason="r")]),
    HighlightsResult(candidates=[make_candidate()], prompt_version="highlights_v1", model="m"),
    make_spec(),
    CropTrack(clip_id="clip_01", mode="center", box=CropBox(x=656, y=0, w=608, h=1080)),
    CropTrack(clip_id="clip_01", mode="blur_fallback", box=None),
    CaptionFiles(
        clip_id="clip_01", ass_path="a.ass", srt_path="a.srt", style="default", offset_s=812.4
    ),
    make_rendered(),
    PackageResult(
        output_dir="output",
        zip_path="job.zip",
        metadata_path="output/metadata.json",
        clips=[make_packaged()],
    ),
    Job(job_id="20260923-ffffffff-ab12", input=make_input(), created_at=NOW, updated_at=NOW),
    JobMetadata(
        job_id="20260923-ffffffff-ab12",
        input=make_input(),
        source=make_source(),
        transcript_language="en",
        clips=[make_packaged()],
        cost=CostSummary(stages=[StageCost(stage=StageName.TRANSCRIBE, gpu_s=120, gpu_type="L4")]),
        versions=make_versions(),
        started_at=NOW,
        finished_at=NOW,
    ),
]


@pytest.mark.parametrize("sample", ALL_SAMPLES, ids=lambda m: type(m).__name__)
def test_json_round_trip(sample: BaseModel) -> None:
    restored = type(sample).model_validate_json(sample.model_dump_json())
    assert restored == sample


def test_job_input_requires_exactly_one_source() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        JobInput(permission=Permission.OWN)
    with pytest.raises(ValidationError, match="exactly one"):
        make_input(source_path="a.mp4")


def test_job_input_requires_permission() -> None:
    with pytest.raises(ValidationError):
        JobInput.model_validate({"source_path": "a.mp4"})
    with pytest.raises(ValidationError):
        make_input(permission="found_it_online")


def test_cc_by_requires_credit() -> None:
    with pytest.raises(ValidationError, match="source_credit"):
        make_input(permission="cc_by")
    ok = make_input(permission="cc_by", source_credit="Jane Doe, CC BY 4.0, https://example.com")
    assert ok.permission is Permission.CC_BY


def test_job_input_rejects_non_http_url() -> None:
    with pytest.raises(ValidationError):
        make_input(source_url="file:///etc/passwd")


def test_clip_options_length_order() -> None:
    with pytest.raises(ValidationError, match="min_len"):
        ClipOptions(min_len=60, max_len=30)
    assert ClipOptions(min_len=20, max_len=45).max_len == 45


def test_word_order() -> None:
    with pytest.raises(ValidationError, match="end < start"):
        Word(text="x", start=2.0, end=1.0)


def test_contracts_are_frozen_and_strict() -> None:
    source = make_source()
    with pytest.raises(ValidationError):
        source.width = 10  # type: ignore[misc]
    with pytest.raises(ValidationError, match="extra"):
        SourceMedia.model_validate({**source.model_dump(), "unexpected": 1})


def test_llm_response_limits() -> None:
    clip = {"start": 1, "end": 40, "score": 0.5, "hook": "h", "title": "t", "reason": "r"}
    with pytest.raises(ValidationError):
        LLMClipsResponse.model_validate({"clips": [clip] * 6})
    with pytest.raises(ValidationError):
        LLMClipsResponse.model_validate({"clips": [{**clip, "score": 1.2}]})
    assert LLMClipsResponse.model_validate({"clips": []}).clips == []


def test_crop_track_box_matches_mode() -> None:
    with pytest.raises(ValidationError):
        CropTrack(clip_id="c", mode="center", box=None)
    with pytest.raises(ValidationError):
        CropTrack(clip_id="c", mode="blur_fallback", box=CropBox(x=0, y=0, w=1, h=1))


def test_helpers() -> None:
    assert [w.text for w in make_transcript().words] == ["Hello", "world."]
    assert make_spec().duration_s == pytest.approx(59.5)


def test_llm_output_ignores_extra_keys_but_checks_ranges() -> None:
    clip = {"start": 1, "end": 40, "score": 0.5, "hook": "h", "title": "t", "reason": "r"}
    parsed = LLMClipsResponse.model_validate({"clips": [{**clip, "confidence": 0.9}], "note": "x"})
    assert parsed.clips[0].end == 40
    for bad in ({"start": 50, "end": 10}, {"start": -1, "end": 10}, {"start": 5, "end": 5}):
        with pytest.raises(ValidationError):
            LLMClip.model_validate({**clip, **bad})


def test_clip_candidate_and_spec_ranges() -> None:
    c = make_candidate()
    with pytest.raises(ValidationError):
        ClipCandidate.model_validate({**c.model_dump(), "start": -5.0, "end": -10.0})
    with pytest.raises(ValidationError, match="after the source"):
        ClipSpec.model_validate({**make_spec().model_dump(), "start": 1790.0, "end": 1830.0})


def test_cost_total_is_derived() -> None:
    cost = CostSummary(
        stages=[
            StageCost(stage=StageName.TRANSCRIBE, usd_estimate=0.05),
            StageCost(stage=StageName.HIGHLIGHTS, usd_estimate=0.07),
        ]
    )
    assert cost.total_usd == pytest.approx(0.12)
    assert CostSummary.model_validate_json(cost.model_dump_json()).total_usd == pytest.approx(0.12)


def test_job_input_sources() -> None:
    upload = JobInput(telegram_file_id="BQACAgIAAxk", permission=Permission.OWN)
    assert upload.source_url is None and upload.telegram_file_id == "BQACAgIAAxk"
    with pytest.raises(ValidationError, match="exactly one"):
        JobInput.model_validate(
            {"telegram_file_id": "x", "source_path": "a.mp4", "permission": "own"}
        )


def test_job_input_notify_round_trip() -> None:
    job_input = make_input(notify={"chat_id": 42, "reply_to_message_id": 7})
    assert job_input.notify == TelegramTarget(chat_id=42, reply_to_message_id=7)
    assert JobInput.model_validate_json(job_input.model_dump_json()) == job_input


def test_job_outputs_and_clip_ids_round_trip() -> None:
    job = Job(
        job_id="20260923-ffffffff-ab12",
        input=make_input(),
        created_at=NOW,
        updated_at=NOW,
        stage=StageName.RENDER,
        outputs={StageName.INGEST: "cache/ingest/k/result.json"},
        clip_ids=["clip_01", "clip_02"],
    )
    restored = Job.model_validate_json(job.model_dump_json())
    assert restored.outputs == {StageName.INGEST: "cache/ingest/k/result.json"}
    assert restored.clip_ids == ["clip_01", "clip_02"]


def test_clip_state_finished() -> None:
    state = make_clip_state()
    assert state.status is ClipStatus.PENDING and not state.finished
    assert state.model_copy(update={"status": ClipStatus.DONE}).finished
    assert state.model_copy(update={"status": ClipStatus.FAILED}).finished
    assert not state.model_copy(update={"status": ClipStatus.RUNNING}).finished


def test_clip_options_default_to_automatic() -> None:
    options = ClipOptions()
    assert options.n is None and options.min_score == 0.80
    assert ClipOptions(n=30).n == 30
    with pytest.raises(ValidationError):
        ClipOptions(n=31)
    with pytest.raises(ValidationError):
        ClipOptions(min_score=1.2)
    # jobs saved before automatic mode still load
    assert ClipOptions.model_validate_json('{"n": 5, "min_len": 30, "max_len": 60}').n == 5


def test_crop_segment_needs_box_only_for_crop() -> None:
    box = CropBox(x=0, y=0, w=404, h=720)
    assert CropSegment(start=0, end=2, mode="crop", box=box).box == box
    assert CropSegment(start=0, end=2, mode="blur").box is None
    with pytest.raises(ValidationError):
        CropSegment(start=0, end=2, mode="crop")
    with pytest.raises(ValidationError):
        CropSegment(start=0, end=2, mode="blur", box=box)
    with pytest.raises(ValidationError):
        CropSegment(start=2, end=2, mode="blur")


def test_tracked_crop_track_needs_contiguous_segments() -> None:
    a = CropSegment(start=0, end=2, mode="blur")
    b = CropSegment(start=2, end=5, mode="blur")
    ok = CropTrack(clip_id="clip_01", mode="tracked", box=None, segments=[a, b])
    assert len(ok.segments) == 2
    gap = CropSegment(start=2.5, end=5, mode="blur")
    late = CropSegment(start=0.5, end=2, mode="blur")
    for segments in ([], [a, gap], [late, b]):
        with pytest.raises(ValidationError):
            CropTrack(clip_id="clip_01", mode="tracked", box=None, segments=segments)
    with pytest.raises(ValidationError):  # the fixed modes carry no segments
        CropTrack(clip_id="clip_01", mode="blur_fallback", box=None, segments=[a])


def test_job_input_channel_is_optional() -> None:
    plain = JobInput.model_validate({"source_path": "uploads/x.mp4", "permission": "own"})
    assert plain.channel is None
    tagged = JobInput.model_validate(
        {"source_path": "uploads/x.mp4", "permission": "creator_agreement",
         "channel": {"slug": "billy-garton", "name": "Billy Garton Jr."}}
    )  # fmt: skip
    assert tagged.channel == ChannelRef(slug="billy-garton", name="Billy Garton Jr.")


T = datetime(2026, 9, 29, tzinfo=UTC)


def _account(**changes: object) -> Account:
    values: dict[str, object] = {
        "id": "realtalk-clips-en", "blueprint": "realtalk-clips", "blueprint_version": 1,
        "kind": "clips", "language": "en", "niche": "self-improvement podcast clips",
        "platforms": {Platform.TIKTOK: PlatformProfile(handle="realtalk.clipsdaily")},
    }  # fmt: skip
    values.update(changes)
    return Account.model_validate(values)


def test_account_id_is_a_slug_and_handles_are_labels() -> None:
    assert _account().review_tier == "review" and _account().posting == PostingSchedule()
    for bad in ("Realtalk", "-x", "a" * 41, "realtalk.clipsdaily"):
        with pytest.raises(ValidationError):
            _account(id=bad)
    with pytest.raises(ValidationError):
        PlatformProfile(handle="has space")
    assert "paused" not in Account.model_fields  # runtime state lives in posting_state
    assert _account(kind="model").kind == "model"  # AI model/influencer (ADR-39)


def test_source_kind_rules() -> None:
    perm = SourcePermission(type="clipping_program")
    Source(id="whop-x", account_id="founder-tapes-en", credit_name="X", permission=perm,
           kind="campaign",
           campaign=CampaignRules(required_tags=["whop"], rate_per_1k=1.5))  # fmt: skip
    with pytest.raises(ValidationError):  # campaign without rules
        Source(id="whop-x", account_id="a", credit_name="X", permission=perm, kind="campaign")
    with pytest.raises(ValidationError):  # a channel with campaign rules
        Source(
            id="billy", account_id="a", credit_name="B", permission=perm, campaign=CampaignRules()
        )
    with pytest.raises(ValidationError):  # kind own needs permission own
        Source(id="me", account_id="a", credit_name="Me", permission=perm, kind="own")
    with pytest.raises(ValidationError):  # a permission covers at least one platform
        SourcePermission(type="own", platforms=[])
    assert Source(id="billy", account_id="a", credit_name="B", permission=perm).status == "active"


def test_content_item_carries_disclosure_and_assets() -> None:
    item = ContentItem(
        id="20260929-aaaaaaaa-0001:clip_01", account_id="realtalk-clips-en", source_id="billy",
        producer_version="abc123", language="en", video_path="x.mp4", duration=30.0,
        title="t", hook="h", score=0.9, credits=["Billy"],
        assets=[AssetSource(kind="source_video", license="creator_agreement")],
        clip=ClipOrigin(job_id="20260929-aaaaaaaa-0001", clip_id="clip_01", source_hash="a" * 64,
                        start=0, end=30, episode="ep01", episode_finished_at=T),
        queued_at=T,
    )  # fmt: skip
    assert item.ai_disclosure is False and item.sponsored is False
    assert item.producer == "clips" and item.media_kind == "video"

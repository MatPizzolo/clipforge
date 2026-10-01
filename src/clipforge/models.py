"""Pydantic contracts shared by pipeline stages (CLAUDE.md rule 2: change contracts here first).

Paths inside contracts are strings relative to JOBS_ROOT (e.g. "cache/ingest/<key>/source.mp4"
or "<job_id>/output/..."), so the same JSON is valid wherever JOBS_ROOT lives and cached stage
outputs can be shared across jobs. `jobs.JobContext.path()` resolves them. The one exception is
`JobInput.source_path`, which may name a file the user placed on the Volume.

Models that parse LLM output ignore unknown keys; every other contract rejects them.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)


class Contract(BaseModel):
    """Immutable stage contract; unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LLMOutput(BaseModel):
    """Parses LLM JSON: immutable, but tolerant of extra keys the model adds."""

    model_config = ConfigDict(frozen=True, extra="ignore")


def _check_range(start: float, end: float) -> None:
    if start < 0:
        raise ValueError("start must be >= 0")
    if end <= start:
        raise ValueError("end must be > start")


# ---- enums ------------------------------------------------------------------------------


class Permission(StrEnum):
    """Permission basis for using a source (docs/SOURCING.md)."""

    OWN = "own"
    CREATOR_AGREEMENT = "creator_agreement"
    CLIPPING_PROGRAM = "clipping_program"
    CC_BY = "cc_by"
    PUBLIC_DOMAIN = "public_domain"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class StageName(StrEnum):
    INGEST = "ingest"
    TRANSCRIBE = "transcribe"
    HIGHLIGHTS = "highlights"
    REFRAME = "reframe"
    CAPTIONS = "captions"
    RENDER = "render"
    PACKAGE = "package"


# ---- job input --------------------------------------------------------------------------


class ClipOptions(Contract):
    # None = automatic: every candidate scoring at least `min_score`, at most 30 (selection.py)
    n: int | None = Field(None, ge=1, le=30)
    min_score: float = Field(0.80, ge=0.0, le=1.0)
    min_len: float = Field(30.0, ge=5.0)
    max_len: float = Field(60.0, le=180.0)
    language: str | None = None  # None = auto-detect
    reframe: Literal["auto", "center", "blur"] = "auto"
    caption_style: Literal["default"] = "default"

    @model_validator(mode="after")
    def _len_order(self) -> ClipOptions:
        if self.min_len >= self.max_len:
            raise ValueError("min_len must be < max_len")
        return self


class TelegramTarget(Contract):
    """Where the Telegram notifier reports a job (the chat that sent it)."""

    chat_id: int
    reply_to_message_id: int | None = None


# ---- channels (videos/channels.toml; ADR-22) ----------------------------------------------


class Channel(Contract):
    """One `[slug]` table of `videos/channels.toml`; its videos live in `videos/<slug>/`."""

    name: str = Field(min_length=1)  # the creator credit shown in captions
    url: AnyHttpUrl | None = None  # for reference only
    permission: Permission


class ChannelRef(Contract):
    """The channel a job's video came from; jobs with one are queued for posting (ADR-23)."""

    slug: str
    name: str


class JobInput(Contract):
    source_url: AnyHttpUrl | None = None  # direct media link (ADR-10)
    telegram_file_id: str | None = None  # Telegram upload, at most 20 MB
    source_path: str | None = None  # path relative to JOBS_ROOT on the Volume (tests, dev)
    permission: Permission
    source_credit: str | None = None  # creator + license link; required for cc_by
    source_label: str | None = None
    options: ClipOptions = Field(default_factory=ClipOptions)
    notify: TelegramTarget | None = None  # set for jobs that came from Telegram
    channel: ChannelRef | None = None  # set by `clipforge clip` for channel folders (ADR-22)

    @model_validator(mode="after")
    def _check(self) -> JobInput:
        sources = (self.source_url, self.telegram_file_id, self.source_path)
        if sum(source is not None for source in sources) != 1:
            raise ValueError(
                "exactly one of source_url / telegram_file_id / source_path is required"
            )
        if self.permission is Permission.CC_BY and not self.source_credit:
            raise ValueError("cc_by sources need source_credit")
        return self


class InboxEntry(Contract):
    """One video in `videos/.clipforge.json`."""

    job_id: str
    status: Literal["submitted", "fetched"] = "submitted"
    out: str | None = None  # where `--fetch` put the clips, relative to videos/out/


# ---- posting queue (Modal Dict; ADR-23) ---------------------------------------------------


class Platform(StrEnum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"


LEGACY_PLATFORMS: tuple[Platform, ...] = (Platform.TIKTOK, Platform.INSTAGRAM, Platform.YOUTUBE)


class PostStatus(StrEnum):
    """Derived from a clip's keys, never stored (spec §4)."""

    QUEUED = "queued"
    SENT = "sent"  # sent to the phone, no tap yet
    PARTLY_POSTED = "partly_posted"
    POSTED = "posted"  # every platform the item is due on
    SKIPPED = "skipped"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"  # video missing from the Volume


class RejectReason(StrEnum):
    BORING = "boring"
    BAD_CUT = "bad_cut"
    BAD_CROP = "bad_crop"
    CAPTIONS = "captions"
    OTHER = "other"


class PostItem(Contract):
    """Legacy Dict format of a queued clip (ADR-23). Only posting/repo.py (DictPostingRepo)
    reads or writes it; removed when ADR-24 retires (spec §9.3)."""

    job_id: str
    clip_id: str
    channel: ChannelRef
    source_hash: str
    start: float  # source time
    end: float
    score: float
    title: str
    hook: str
    video_path: str  # rendered clip, relative to JOBS_ROOT
    episode: str  # JobInput.source_label, or the job id
    episode_finished_at: datetime
    queued_at: datetime

    @property
    def ref(self) -> str:
        return f"{self.job_id}:{self.clip_id}"


class PostSend(Contract):
    """`post:<ref>:sent:<n>`: one delivery to the phone (n = 1, then 2 after a skip...)."""

    n: int = Field(ge=1)
    at: datetime
    slot: datetime | None  # None for /next and skip
    message_id: int  # the text message with the buttons
    video_message_id: int


class PostMark(Contract):
    """`post:<ref>:posted:<platform>`: the owner confirmed this platform."""

    at: datetime


class PostVerdict(Contract):
    """`post:<ref>:verdict`."""

    kind: Literal["skipped", "rejected"]
    at: datetime
    reason: RejectReason | None = None


class AssetSource(Contract):
    kind: Literal["source_video", "generated", "stock", "commons", "promo", "music_generated"]
    license: str  # for source_video: the Permission value
    attribution: str | None = None
    url: str | None = None
    model: str | None = None


class ClipOrigin(Contract):
    job_id: str
    clip_id: str
    source_hash: str
    start: float
    end: float
    episode: str
    episode_finished_at: datetime


class ContentItem(Contract):
    id: str  # "<job_id>:<clip_id>" for clips (keeps Telegram buttons valid)
    account_id: str
    source_id: str | None
    producer: str = "clips"
    producer_version: str
    language: str
    media_kind: Literal["video", "carousel", "image"] = "video"
    video_path: str | None  # relative to JOBS_ROOT
    image_paths: list[str] = Field(default_factory=list)
    duration: float | None
    title: str
    hook: str
    score: float
    credits: list[str]
    assets: list[AssetSource]
    ai_disclosure: bool = False
    sponsored: bool = False
    cost_usd: float = 0.0
    parent_item_id: str | None = None
    clip: ClipOrigin | None = None
    queued_at: datetime
    # `copy: dict[Platform, PostCopy]` arrives in S2


class PostRecord(Contract):
    """Everything the Dict holds for one clip (read model; not stored as one key)."""

    item: ContentItem
    platforms: list[Platform] = Field(default_factory=lambda: list(LEGACY_PLATFORMS))
    sends: list[PostSend] = Field(default_factory=list)  # ordered by n
    posted: dict[Platform, datetime] = Field(default_factory=dict)
    verdict: PostVerdict | None = None
    unavailable: bool = False


class ChannelProgress(Contract):
    slug: str
    name: str
    episodes_clipped: int = 0
    episodes_clipping: int = 0
    episodes_failed: int = 0
    counts: dict[PostStatus, int] = Field(default_factory=dict)


ACCOUNT_ID = r"[a-z0-9][a-z0-9-]{0,39}"
HANDLE = r"[A-Za-z0-9._]{1,30}"


class PlatformProfile(Contract):
    enabled: bool = True
    handle: str | None = Field(default=None, pattern=f"^{HANDLE}$")  # editable label; never a key
    min_len: float | None = None  # seconds; None = the ClipOptions default
    max_len: float | None = None
    hashtags: list[str] = Field(default_factory=list)  # without "#"
    # no cadence: PostingSchedule.slots is the only timing source until S2


class PostingSchedule(Contract):
    chat_id: int | None = None  # None = posting off for this account
    timezone: str = "America/New_York"  # validated with ZoneInfo
    slots: list[str] = Field(default_factory=list)  # "HH:MM", normalized like POSTING_SLOTS
    hashtags: list[str] = Field(default_factory=list)  # account-wide, added to every platform


class BrandKit(Contract):
    caption_preset: str = "default"
    cta: str | None = None
    bio_link: str | None = None


class Account(Contract):
    id: str = Field(pattern=f"^{ACCOUNT_ID}$")  # stable slug, never a handle
    blueprint: str
    blueprint_version: int
    kind: Literal["clips", "story", "band", "avatar", "model"]  # = blueprint.category (ADR-39)
    language: Literal["en", "es"]
    niche: str
    platforms: dict[Platform, PlatformProfile]
    review_tier: Literal["review", "sample", "auto"] = "review"
    persona_id: str | None = None
    paired_account_id: str | None = None
    monthly_budget_usd: float = 0.0
    brand: BrandKit = Field(default_factory=BrandKit)
    posting: PostingSchedule = Field(default_factory=PostingSchedule)
    # no `paused`: that is runtime state in posting_state, so editing an account can never
    # pause or un-pause its queue


class SeriesFormat(Contract):
    name: str
    description: str


class ComplianceProfile(Contract):
    require_credit: bool = False
    required_tags: list[str] = Field(default_factory=list)
    disclosures: list[Literal["ai", "sponsored"]] = Field(default_factory=list)
    banned_claims: list[str] = Field(default_factory=list)  # e.g. "buy-x", "health"


class Blueprint(Contract):
    name: str
    version: int
    category: Literal["clips", "story", "band", "avatar", "model"]
    languages: list[Literal["en", "es"]]
    niche: str
    pillars: list[str]
    series: list[SeriesFormat] = Field(default_factory=list)
    voice_brief: str = ""
    visual_style: str = ""
    money: list[str] = Field(default_factory=list)
    compliance: ComplianceProfile = Field(default_factory=ComplianceProfile)
    platform_defaults: dict[Platform, PlatformProfile]
    prompts: dict[str, str] = Field(default_factory=dict)  # step -> prompt name


class Persona(Contract):  # contract only; the table arrives in S8
    id: str
    voice_ref_path: str | None = None
    voice_design_prompt: str = ""
    face_lora_path: str | None = None
    face_ref_paths: list[str] = Field(default_factory=list)
    style_notes: str = ""


class SourcePermission(Contract):
    """The legal basis for posting a source's content (a business record, not config)."""

    type: Permission
    granted_at: date | None = None
    granted_by: str | None = None  # who granted it (name and role)
    evidence_url: AnyHttpUrl | None = None  # link to the stored agreement; never the file itself
    platforms: list[Platform] = Field(default_factory=lambda: list(Platform), min_length=1)
    monetization_allowed: bool | None = None  # None = not recorded yet
    translation_allowed: bool | None = None
    expires_at: AwareDatetime | None = None  # None = no expiry
    restrictions: str = ""


class CampaignRules(Contract):
    url: AnyHttpUrl | None = None  # the campaign page
    rules: str = ""
    required_tags: list[str] = Field(default_factory=list)  # without "#"
    required_links: list[AnyHttpUrl] = Field(default_factory=list)
    deadline: AwareDatetime | None = None
    sponsored: bool = True  # paid campaigns are disclosed (#ad)
    rate_per_1k: float | None = None  # USD per 1,000 views
    submission_url: AnyHttpUrl | None = None  # where posted links are submitted


class Source(Contract):
    id: str = Field(pattern=f"^{ACCOUNT_ID}$")  # = the folder name under videos/; never changes
    account_id: str = Field(pattern=f"^{ACCOUNT_ID}$")
    kind: Literal["channel", "campaign", "own"] = "channel"
    status: Literal["active", "paused", "ended"] = "active"
    credit_name: str  # the credit text in captions
    creator_handles: dict[Platform, str] = Field(default_factory=dict)  # for @mentions
    url: AnyHttpUrl | None = None  # the creator's page
    permission: SourcePermission
    campaign: CampaignRules | None = None  # required iff kind == "campaign"
    notes: str = ""

    @model_validator(mode="after")
    def _kind_rules(self) -> Self:
        if (self.kind == "campaign") != (self.campaign is not None):
            raise ValueError("a campaign source needs campaign rules; other kinds have none")
        if (self.kind == "own") != (self.permission.type is Permission.OWN):
            raise ValueError("kind 'own' goes with permission 'own', and only with it")
        return self


class SourceEvent(Contract):
    """One change to a source (source_events): who, when, before and after."""

    source_id: str
    at: datetime
    actor: str  # "cli:<os user>", "import-toml", later the dashboard user
    action: Literal["created", "updated", "imported"]
    before: dict[str, object] | None = None  # the Source JSON before (None when created)
    after: dict[str, object]


# What the dashboard shows for posting (card 002 A5): off = no posting chat; problem = posting
# is misconfigured; paused = /pause; waiting = the pause rule (PAUSE_AFTER sent clips with no
# tap) holds the slots; on = clips go out at the next slot.
# outage = posting_daily found it hadn't run for days; nothing is sent until /go or a restore
PostingState = Literal["off", "problem", "paused", "waiting", "on", "outage"]


class AccountPosting(Contract):
    account_id: str
    enabled: bool  # the account has a posting chat
    paused: bool
    channels: list[ChannelProgress] = Field(default_factory=list)
    waiting: int = 0
    days_left: int = 0
    per_day: int = 0
    next_slot: datetime | None = None
    held: int = 0  # waiting, but held by their source (spec §6.3 hold rules)
    timezone: str = "UTC"
    # additive (card 002 A5, #49)
    state: PostingState = "off"
    posted_total: int = 0  # clips posted on every platform they were queued for
    unanswered: int = 0  # sent clips with no tap yet (the pause rule counts these)
    last_sent_at: datetime | None = None


class ImportReport(Contract):
    """Result of `posting import` (Dict queue -> Postgres, spec §5.5)."""

    dry_run: bool
    dict_items: int = 0
    from_snapshot: int = 0  # keys filled in from the newest Volume snapshot
    by_status: dict[PostStatus, int] = Field(default_factory=dict)
    imported: int = 0
    already: int = 0
    missing_source: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    paused: bool = False


class BackfillReport(Contract):
    """Result of `jobs backfill`."""

    dry_run: bool
    from_metadata: int = 0
    from_dict: int = 0
    written: int = 0
    failed: list[str] = Field(default_factory=list)


class VerifyReport(Contract):
    """Dict versus Postgres for one account."""

    account_id: str
    dict_items: int = 0
    postgres_items: int = 0
    differences: int = 0
    first: list[str] = Field(default_factory=list)


class PostingOverview(Contract):
    """What `/status`, `GET /posting` and `clipforge status` show (spec §9)."""

    enabled: bool  # POSTING_CHAT_ID is set
    paused: bool
    channels: list[ChannelProgress]
    waiting: int  # queued + skipped: clips that will still be sent
    days_left: int
    per_day: int
    next_slot: datetime | None
    problem: str | None = None  # why posting is off despite POSTING_CHAT_ID (a config mistake)
    accounts: list[AccountPosting] = Field(default_factory=list)
    # additive (card 002 A5, #49): account #1's state ("problem" wins), and posted clips summed
    # over every account
    state: PostingState = "off"
    posted_total: int = 0
    # the outage flag's date (the last good snapshot); None = no outage (card 002 final review)
    outage_since: str | None = None


class JobSummary(Contract):
    """The durable mirror of a job (the `jobs` table, ADR-26)."""

    job_id: str
    source_id: str | None  # the channel slug for channel jobs
    status: JobStatus
    source_label: str | None = None
    input: JobInput
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    cost_usd: float = 0.0
    metadata_path: str | None = None  # relative to JOBS_ROOT
    build: str | None = None  # the git SHA of the deploy that ran it


class Submission(Contract):
    """A campaign clip's post, to paste into the campaign's form (spec §6.3)."""

    item_id: str
    platform: Platform
    posted_at: datetime
    url: str | None = None


# ---- job state (mutable, persisted by the JobStore) ---------------------------------------


class Progress(BaseModel):
    stage: StageName
    pct: float = Field(ge=0, le=100)
    message: str = ""
    at: datetime


class JobError(BaseModel):
    stage: StageName
    error_type: str
    message: str  # sanitized; never contains secrets


class StageCost(BaseModel):
    stage: StageName
    clip_id: str | None = None  # set for per-clip stages (reframe, captions, render)
    wall_s: float = 0.0
    gpu_s: float = 0.0
    gpu_type: str | None = None
    llm_model: str | None = None
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_calls: int = 0
    usd_estimate: float = 0.0
    cached: bool = False  # stage was skipped via cache


class CostSummary(BaseModel):
    stages: list[StageCost] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_usd(self) -> float:
        return sum(stage.usd_estimate for stage in self.stages)


class Job(BaseModel):
    """Core job record (`job:<id>` in the Dict), written only by the step owning the job."""

    job_id: str  # "<yyyymmdd>-<source_hash8>-<rand4>"
    status: JobStatus = JobStatus.QUEUED
    input: JobInput
    created_at: datetime
    updated_at: datetime
    stage: StageName | None = None  # stage of the step currently owning the job
    progress: Progress | None = None
    error: JobError | None = None
    cost: CostSummary = Field(default_factory=CostSummary)  # steps before the clip fan-out
    outputs: dict[StageName, str] = Field(default_factory=dict)  # stage -> result.json ref
    clip_ids: list[str] = Field(default_factory=list)
    output_zip: str | None = None


class ClipStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ClipState(BaseModel):
    """Working state of one clip (`job:<id>:clip:<clip_id>`), written only by its clip step."""

    clip_id: str
    spec_ref: str  # this job's ClipSpec JSON, relative to JOBS_ROOT
    updated_at: datetime
    status: ClipStatus = ClipStatus.PENDING
    result_ref: str | None = None  # this job's RenderedClip JSON once done
    progress: Progress | None = None
    cost: list[StageCost] = Field(default_factory=list)
    error: JobError | None = None
    telegram_sent: bool = False

    @property
    def finished(self) -> bool:
        return self.status in (ClipStatus.DONE, ClipStatus.FAILED)


class JobView(BaseModel):
    """What the API returns: the core record merged with its clips, and the total cost."""

    job_id: str
    status: JobStatus
    stage: StageName | None
    clips: list[ClipState]
    cost: CostSummary
    created_at: datetime
    updated_at: datetime
    progress: Progress | None = None
    error: JobError | None = None
    output_zip: str | None = None
    download_url: str | None = None  # signed zip link, filled in by the API when done


# ---- stage contracts ----------------------------------------------------------------------


class SourceMedia(Contract):
    video_path: str  # mp4 (remuxed when codecs allow)
    audio_path: str  # 16 kHz mono wav (ASR only)
    source_hash: str  # sha256 of the downloaded/original bytes
    source_url: str | None = None  # canonical URL (e.g. youtube watch URL)
    title: str | None = None  # from yt-dlp metadata when available
    duration_s: float = Field(gt=0)
    fps: float = Field(gt=0)  # average frame rate
    width: int = Field(gt=0)  # display width, after rotation
    height: int = Field(gt=0)  # display height, after rotation
    rotation: Literal[0, 90, 180, 270] = 0  # rotation metadata kept by a remux
    video_codec: str
    size_bytes: int = Field(ge=0)
    # Ingest rejects sources without an audio stream: nothing to transcribe.


class Word(Contract):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    probability: float | None = None
    speaker: str | None = None  # None until diarization (Phase 3)

    @model_validator(mode="after")
    def _order(self) -> Word:
        if self.end < self.start:
            raise ValueError("word end < start")
        return self


class Segment(Contract):
    start: float
    end: float
    text: str
    words: list[Word]
    speaker: str | None = None


class Transcript(Contract):
    language: str
    language_probability: float | None = None
    duration_s: float
    model: str  # e.g. "large-v3-turbo"
    segments: list[Segment]

    @property
    def words(self) -> list[Word]:
        return [word for segment in self.segments for word in segment.words]


class TranscribeResult(Contract):
    """Returned by the Modal GPU function. Cost crosses the process boundary here because the
    local side can't measure GPU time; the caller also records its own wall time."""

    transcript: Transcript
    gpu_s: float  # time in the function body, including model load
    load_s: float  # model load part of gpu_s (cold-start signal)
    gpu_type: str


class LLMClip(LLMOutput):
    """One clip in the JSON output of prompts/highlights_v1."""

    start: float
    end: float
    score: float = Field(ge=0, le=1)
    hook: str
    title: str
    reason: str

    @model_validator(mode="after")
    def _range(self) -> LLMClip:
        _check_range(self.start, self.end)
        return self


class LLMClipsResponse(LLMOutput):
    clips: list[LLMClip] = Field(max_length=5)


class KeywordsReply(LLMOutput):
    """Output of prompts/keywords_v1: indices of the clip words to show in color."""

    keywords: list[int] = Field(max_length=200)
    title_keyword: int | None = None  # keywords_v2: index into the title's words


class ClipCandidate(Contract):
    start: float  # snapped to a sentence end / silence
    end: float
    score: float = Field(ge=0, le=1)
    hook: str
    title: str
    reason: str
    window_index: int
    raw_start: float  # as returned by the LLM, before snapping
    raw_end: float

    @model_validator(mode="after")
    def _range(self) -> ClipCandidate:
        _check_range(self.start, self.end)
        return self


class HighlightsResult(Contract):
    candidates: list[ClipCandidate]  # ranked, deduped, length-filtered (all, not just top n)
    prompt_version: str
    model: str


class ClipSpec(Contract):
    """A selected clip. `start`/`end` are the exact output range in source time: render cuts
    exactly there (single accurate-seek encode, no padding), and caption times are
    `word.start - start`. `candidate` keeps the LLM's view for metadata.

    Per-clip stages must key their cache on source_hash + start/end + the options they use,
    never on rank or clip_id (those change when ranking changes).
    """

    clip_id: str  # "clip_01"
    rank: int = Field(ge=1)
    source: SourceMedia
    start: float
    end: float
    candidate: ClipCandidate
    options: ClipOptions

    @model_validator(mode="after")
    def _range(self) -> ClipSpec:
        _check_range(self.start, self.end)
        if self.end > self.source.duration_s + 0.05:
            raise ValueError("clip ends after the source")
        return self

    @property
    def duration_s(self) -> float:
        return self.end - self.start


class CropBox(Contract):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class CropSegment(Contract):
    """One shot of a tracked clip: [start, end) in seconds relative to the clip start."""

    start: float = Field(ge=0)
    end: float
    mode: Literal["crop", "blur"]
    box: CropBox | None = None  # set for "crop"

    @model_validator(mode="after")
    def _check(self) -> CropSegment:
        if self.end <= self.start:
            raise ValueError("segment end must be after its start")
        if (self.mode == "crop") != (self.box is not None):
            raise ValueError("box is required for 'crop' and must be None for 'blur'")
        return self


class CropTrack(Contract):
    clip_id: str
    mode: Literal["center", "blur_fallback", "tracked"]
    box: CropBox | None  # set for "center"; None otherwise
    segments: list[CropSegment] = Field(default_factory=list)  # "tracked" only (ADR-19)
    out_width: int = 1080
    out_height: int = 1920

    @model_validator(mode="after")
    def _box_matches_mode(self) -> CropTrack:
        if self.mode == "tracked":
            if self.box is not None or not self.segments:
                raise ValueError("'tracked' needs segments and no box")
            if abs(self.segments[0].start) > 1e-6:
                raise ValueError("segments must start at 0")
            for before, after in zip(self.segments, self.segments[1:], strict=False):
                if abs(after.start - before.end) > 1e-3:
                    raise ValueError("segments must be contiguous")
            return self
        if self.segments:
            raise ValueError("only 'tracked' carries segments")
        if (self.mode == "center") != (self.box is not None):
            raise ValueError("box is required for 'center' and must be None for 'blur_fallback'")
        return self


class CaptionFiles(Contract):
    clip_id: str
    ass_path: str
    srt_path: str
    style: str
    offset_s: float  # source time subtracted from word times; must equal ClipSpec.start


class ProbeInfo(Contract):
    width: int
    height: int
    duration_s: float  # container duration
    video_duration_s: float | None
    audio_duration_s: float | None
    fps: float
    video_codec: str
    pix_fmt: str
    audio_codec: str | None
    n_video_streams: int
    n_audio_streams: int
    size_bytes: int


class RenderedClip(Contract):
    clip_id: str
    spec: ClipSpec
    video_path: str
    srt_path: str
    encoder: Literal["h264_nvenc", "libx264"]
    probe: ProbeInfo


# ---- timeline (S4, ADR-31): the only input to render ------------------------------------

TIMELINE_EPS = 1e-3  # seconds; segments closer than this count as touching


def _jobs_path(path: str) -> str:
    """Timeline paths are relative to JOBS_ROOT and never leave it (ADR-13)."""
    parts = PurePosixPath(path).parts
    if not path or PurePosixPath(path).is_absolute() or ".." in parts:
        raise ValueError(f"path must be relative to JOBS_ROOT: {path!r}")
    return path


class KenBurns(Contract):
    """A slow zoom/pan over a still: linear from `*_from` to `*_to` over the segment.
    Focus points are fractions of the image (0..1), the point kept centered."""

    zoom_from: float = Field(1.0, ge=1.0)
    zoom_to: float = Field(1.15, ge=1.0)
    focus_from: tuple[float, float] = (0.5, 0.5)
    focus_to: tuple[float, float] = (0.5, 0.5)

    @model_validator(mode="after")
    def _check(self) -> KenBurns:
        if not all(0.0 <= v <= 1.0 for v in (*self.focus_from, *self.focus_to)):
            raise ValueError("focus points are fractions of the image (0..1)")
        return self


class VideoSegment(Contract):
    """A piece of a video file, shown at timeline [start, end) from media time `in_s`.
    Segments that reuse one file must use it in media order: render opens each file once and
    splits it, so going backwards in a file would buffer decoded frames (review CP2 #4)."""

    type: Literal["video"] = "video"
    kind: Literal["source", "broll", "talking_head"]
    path: str
    media_hash: str | None = None  # content hash when known (clips: source_hash); in the key
    width: int = Field(gt=0)  # display size after rotation
    height: int = Field(gt=0)
    in_s: float = Field(ge=0)
    start: float = Field(ge=0)
    end: float
    fit: Literal["crop", "cover", "blur"]
    box: CropBox | None = None  # set iff fit == "crop"

    @model_validator(mode="after")
    def _check(self) -> VideoSegment:
        _jobs_path(self.path)
        if self.end <= self.start:
            raise ValueError("segment end must be after its start")
        if (self.fit == "crop") != (self.box is not None):
            raise ValueError("box is required for 'crop' and must be None otherwise")
        return self


class StillSegment(Contract):
    """An image held on screen for [start, end), optionally with a Ken Burns move."""

    type: Literal["still"] = "still"
    path: str
    media_hash: str | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    start: float = Field(ge=0)
    end: float
    fit: Literal["cover", "blur"] = "cover"
    ken_burns: KenBurns | None = None

    @model_validator(mode="after")
    def _check(self) -> StillSegment:
        _jobs_path(self.path)
        if self.end <= self.start:
            raise ValueError("segment end must be after its start")
        if self.ken_burns is not None and self.fit != "cover":
            raise ValueError("ken_burns needs fit 'cover'")
        return self


VisualSegment = Annotated[VideoSegment | StillSegment, Field(discriminator="type")]


class AudioTrack(Contract):
    """Media [in_s, in_s + end - start) played at timeline [start, end)."""

    kind: Literal["source", "narration", "music"]
    path: str
    media_hash: str | None = None
    in_s: float = Field(0.0, ge=0)
    start: float = Field(ge=0)
    end: float
    gain_db: float = 0.0
    duck: bool = False  # music only: ducked under the source and narration tracks

    @model_validator(mode="after")
    def _check(self) -> AudioTrack:
        _jobs_path(self.path)
        if self.end <= self.start:
            raise ValueError("track end must be after its start")
        if self.duck and self.kind != "music":
            raise ValueError("only music can be ducked")
        return self


class Subtitles(Contract):
    """Captions and the hook title card: one ASS file (captions.build_ass, log #340)."""

    ass_path: str
    srt_path: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Subtitles:
        _jobs_path(self.ass_path)
        if self.srt_path is not None:
            _jobs_path(self.srt_path)
        return self


class Timeline(Contract):
    """What plays when: the one input to render (ADR-31). No ids, so renders are shared
    across jobs; `assets` is for the policy gate and stays out of the cache key (#342)."""

    width: int = 1080
    height: int = 1920
    fps: int = Field(ge=1, le=60)
    duration_s: float = Field(gt=0)
    visual: list[VisualSegment]
    audio: list[AudioTrack] = Field(default_factory=list)
    overlay: Subtitles | None = None
    loudness_lufs: float = -14.0
    assets: list[AssetSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Timeline:
        if min(self.width, self.height) <= 0 or self.width % 2 or self.height % 2:
            raise ValueError("width and height must be positive and even (yuv420p)")
        if not self.visual:
            raise ValueError("a timeline needs at least one visual segment")
        if abs(self.visual[0].start) > TIMELINE_EPS:
            raise ValueError("visual segments must start at 0")
        for before, after in zip(self.visual, self.visual[1:], strict=False):
            if abs(after.start - before.end) > TIMELINE_EPS:
                raise ValueError("visual segments must be contiguous")
        if abs(self.visual[-1].end - self.duration_s) > TIMELINE_EPS:
            raise ValueError("visual segments must end at duration_s")
        for track in self.audio:
            if track.end > self.duration_s + TIMELINE_EPS:
                raise ValueError("audio tracks must end inside the timeline")
        return self


class Loudness(Contract):
    """What the loudness passes measured and did (ADR-47)."""

    input_i: float | None = None
    input_tp: float | None = None
    input_lra: float | None = None
    mode: Literal["linear", "dynamic", "single_pass", "silent"]


class RenderedVideo(Contract):
    """Render's output for any producer; clips wrap it into RenderedClip."""

    video_path: str
    encoder: Literal["h264_nvenc", "libx264"]
    probe: ProbeInfo
    loudness: Loudness


class PackagedClip(Contract):
    """A clip as delivered: paths relative to the job's output directory (what's in the zip)."""

    clip_id: str
    rank: int
    dir: str  # "clip_01_score0.91"
    video: str  # "clip_01_score0.91/video.mp4"
    srt: str
    post_md: str
    start: float  # source time
    end: float
    score: float
    title: str
    hook: str
    probe: ProbeInfo


class PackageResult(Contract):
    output_dir: str
    zip_path: str
    metadata_path: str
    clips: list[PackagedClip]


class Versions(Contract):
    git_sha: str | None  # None when not run from a git checkout
    clipforge: str
    stages: dict[str, str]  # stage name -> STAGE_VERSION
    highlight_prompt: str  # e.g. "highlights_v1"
    highlight_model: str
    whisper_model: str
    producer_version: str | None = None  # "clips:<hash>" (ADR-43); absent in older files


class JobMetadata(Contract):
    """Written as output/metadata.json."""

    job_id: str
    input: JobInput  # includes permission + source_credit
    source: SourceMedia
    transcript_language: str
    clips: list[PackagedClip]
    cost: CostSummary
    versions: Versions
    started_at: datetime
    finished_at: datetime

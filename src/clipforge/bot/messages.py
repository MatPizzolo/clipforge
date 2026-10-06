"""Every text the bot sends (spec §5), in one place."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from clipforge.models import (
    AccountPosting,
    ClipStatus,
    Job,
    JobView,
    PostingOverview,
    PostStatus,
    RenderedClip,
)

USAGE = (
    "Send a direct video link, or a video file up to 20 MB.\n"
    '/clip <link> [n=auto] [score=0.8] [len=30-60] [lang=en] [perm=own] [credit="..."]\n'
    "/status [<job_id>] · /resume <job_id> · /next · /pause [all|<account>] · /go [all|<account>]"
)
TOO_BIG = (
    "That file is over 20 MB, the most a Telegram bot can download. "
    "Upload it somewhere that serves the file directly and send the link."
)
NO_LINK = "zip link unavailable (API_URL / DOWNLOAD_SIGNING_KEY not set)"


def job_accepted(job_id: str) -> str:
    return f"Got it, job {job_id}"


def clip_caption(rendered: RenderedClip) -> str:
    candidate = rendered.spec.candidate
    return f"#{rendered.spec.rank} · score {candidate.score:.2f} · {candidate.title}"


def done_text(done: int, total: int, cost_usd: float, link: str | None) -> str:
    return f"{done} of {total} clips · ${cost_usd:.3f} · {link or NO_LINK}"


def failed_text(job: Job) -> str:
    if job.error is not None:
        head = f"{job.error.stage}: {job.error.message}"
    else:
        head = f"{job.stage or 'job'}: failed"
    return f"{head}\n/resume {job.job_id}"


def status_text(view: JobView) -> str:
    lines = [f"job {view.job_id}: {view.status}"]
    if view.stage is not None:
        stage = f"stage: {view.stage}"
        if view.progress is not None:
            stage = f"{stage} {view.progress.pct:.0f}% {view.progress.message}".rstrip()
        lines.append(stage)
    if view.clips:
        done = sum(c.status is ClipStatus.DONE for c in view.clips)
        lines.append(f"clips: {done}/{len(view.clips)} done")
    lines.append(f"cost: ${view.cost.total_usd:.3f}")
    if view.error is not None:
        lines.append(f"error: {view.error.stage}: {view.error.message}")
    if view.download_url is not None:
        lines.append(view.download_url)
    return "\n".join(lines)


_COUNT_LABELS = [
    (PostStatus.POSTED, "posted"),
    (PostStatus.PARTLY_POSTED, "partly"),
    (PostStatus.SENT, "waiting on you"),
    (PostStatus.QUEUED, "queued"),
    (PostStatus.SKIPPED, "skipped"),
    (PostStatus.REJECTED, "rejected"),
    (PostStatus.UNAVAILABLE, "missing video"),
]


def _overview_block(view: PostingOverview | AccountPosting, timezone: str, *, several: bool,
                    account_id: str | None = None) -> list[str]:  # fmt: skip
    lines: list[str] = []
    for channel in view.channels:
        total = channel.episodes_clipped + channel.episodes_clipping + channel.episodes_failed
        lines.append(
            f"{channel.name} — {total} episodes ({channel.episodes_clipped} clipped · "
            f"{channel.episodes_clipping} clipping · {channel.episodes_failed} failed)"
        )
        counts = [f"{label} {channel.counts[s]}" for s, label in _COUNT_LABELS
                  if channel.counts.get(s)]  # fmt: skip
        if counts:
            lines.append("  " + " · ".join(counts))
    if not view.channels:
        lines.append(
            "No channel clips yet. Add videos to videos/<channel>/ and run `clipforge clip`."
        )
    problem = view.problem if isinstance(view, PostingOverview) else None
    if problem is not None:
        lines.append(f"Posting is off: {problem}")
    elif not view.enabled:
        lines.append("Posting is off (set POSTING_CHAT_ID).")
    elif view.paused:
        lines.append(f"Paused. Send /go {account_id} to restart." if several
                     else "Paused. Send /go to restart.")  # fmt: skip
    else:
        queue_line = f"Queue: {view.waiting} clips ≈ {view.days_left} days at {view.per_day}/day"
        if view.next_slot is not None:
            local = view.next_slot.astimezone(ZoneInfo(timezone))
            queue_line += f" · next slot {local:%a %d %b %H:%M}"
        lines.append(queue_line)
    return lines


def posting_overview_text(view: PostingOverview, timezone: str | None = None) -> str:
    """`/status` and `clipforge status`: per channel, then the queue (spec §9). With several
    accounts, one `▸ <account>` block each; `timezone` is the fallback for one account. An
    outage flag comes first."""
    text = _overview_text(view, timezone)
    if view.outage_since is None:
        return text
    return (f"⚠️ Outage: posting_daily didn't run since {view.outage_since}, so the slots and "
            "rebuild are stopped. Restore (clipforge status --restore "
            f"{view.outage_since}), check this, then /go.\n{text}")  # fmt: skip


def _overview_text(view: PostingOverview, timezone: str | None) -> str:
    if len(view.accounts) >= 2:
        lines: list[str] = []
        for account in view.accounts:
            lines.append(f"▸ {account.account_id}")
            lines += _overview_block(account, account.timezone, several=True,
                                     account_id=account.account_id)  # fmt: skip
        if view.problem is not None:
            lines.append(f"Posting is off: {view.problem}")
        return "\n".join(lines)
    zone = view.accounts[0].timezone if view.accounts else (timezone or "UTC")
    return "\n".join(_overview_block(view, zone, several=False))


POSTING_OFF = "Posting is off (set POSTING_CHAT_ID)."
QUEUE_EMPTY = "The queue is empty. Add videos to videos/<channel>/ and run `clipforge clip`."
SEND_FAILED = "Couldn't send the next clip. Try /next again in a minute."
PAUSED = "Paused. No clips until you send /go."
RESUMED = "Back on. Clips resume at the next slot."
STILL_BRAKED = "go recorded, but still braked by /pause all; send /go all to resume."
BRAKE_ONLY = " The database is unavailable, so this is recorded in the brake only."
GONE = "That clip isn't in the queue any more."
SAVE_FAILED = "Couldn't save that. Tap again."
OUTAGE_CLEARED = "Outage flag cleared: posting_daily's rebuild and the slots run again."
STORE_UNAVAILABLE = "Store unavailable, nothing changed. Try again in a minute."


def unknown_account(given: str, known: list[str]) -> str:
    return f"No account {given}. Accounts: {', '.join(known) or 'none with posting on'}."


def waiting_reminder(count: int) -> str:
    return f"{count} clips are waiting: post them or tap Skip, then the next ones come."

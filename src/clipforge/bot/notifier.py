"""The Notifier for jobs that came from Telegram (ADR-13). `Deps.notifier()` wraps it in
`SafeNotifier`, so a Telegram failure is logged and never fails a step."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clipforge.bot.messages import clip_caption, done_text, failed_text
from clipforge.bot.telegram import TelegramSender
from clipforge.config import Settings
from clipforge.jobs import DictJobStore, merged_cost
from clipforge.links import LinksNotConfigured, download_url
from clipforge.models import ClipState, ClipStatus, Job, RenderedClip, TelegramTarget


@dataclass
class TelegramNotifier:
    sender: TelegramSender
    target: TelegramTarget
    store: DictJobStore
    settings: Settings
    root: Path  # JOBS_ROOT: contract paths are relative to it

    def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
        self.sender.send_video(
            self.target.chat_id,
            self.root / rendered.video_path,
            clip_caption(rendered),
            self.target.reply_to_message_id,
        )

    def done(self, job: Job) -> None:
        clips = self.store.clips(job.job_id, job.clip_ids)
        done = sum(c.status is ClipStatus.DONE for c in clips)
        try:
            link: str | None = download_url(self.settings, job.job_id)
        except LinksNotConfigured:
            link = None
        cost = merged_cost(self.store, job).total_usd
        self.sender.send_message(
            self.target.chat_id,
            done_text(done, len(clips), cost, link),
            self.target.reply_to_message_id,
        )

    def failed(self, job: Job) -> None:
        self.sender.send_message(
            self.target.chat_id, failed_text(job), self.target.reply_to_message_id
        )

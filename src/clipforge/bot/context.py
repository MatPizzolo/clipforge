"""What the bot's handlers need (moved out of webhook.py so bot/posting.py can use it)."""

from __future__ import annotations

from dataclasses import dataclass

from clipforge.bot.telegram import TelegramSender
from clipforge.config import Settings
from clipforge.pipeline.steps import Deps


@dataclass
class BotContext:
    settings: Settings
    sender: TelegramSender
    deps: Deps  # the store, the Volume root, the spawner

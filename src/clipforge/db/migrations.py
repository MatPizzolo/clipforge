"""Run Alembic from Python (tests, CI). Local and CI only: the Modal image has no alembic/."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def alembic_config(url: str, schema: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["url"] = url  # not set_main_option: '%' in URLs breaks configparser
    if schema is not None:
        # tests only: run in this (throwaway) schema instead of the default one
        config.attributes["schema"] = schema
    return config


def upgrade(url: str, revision: str = "head", schema: str | None = None) -> None:
    command.upgrade(alembic_config(url, schema), revision)


def downgrade(url: str, revision: str, schema: str | None = None) -> None:
    command.downgrade(alembic_config(url, schema), revision)

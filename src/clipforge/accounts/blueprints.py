"""Versioned channel blueprints: blueprints/<name>.toml (ADR-35). Packaged like prompts/."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from pydantic import ValidationError

from clipforge.models import ACCOUNT_ID, Blueprint


class BlueprintError(ValueError):
    """The message names the file; safe to show."""


def load_blueprint(directory: Path, name: str) -> Blueprint:
    if not re.fullmatch(ACCOUNT_ID, name):  # names come from API input: no path tricks
        raise BlueprintError(f"invalid blueprint name {name!r}")
    path = directory / f"{name}.toml"
    if not path.is_file():
        raise BlueprintError(f"no blueprint {name!r} in {directory}")
    try:
        blueprint = Blueprint.model_validate(tomllib.loads(path.read_text()))
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise BlueprintError(f"{path.name}: {exc}") from None
    if blueprint.name != name:
        raise BlueprintError(f"{path.name}: name is {blueprint.name!r}, expected {name!r}")
    return blueprint


def list_blueprints(directory: Path) -> list[Blueprint]:
    return [load_blueprint(directory, p.stem) for p in sorted(directory.glob("*.toml"))]

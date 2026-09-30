"""Versioned prompts (CLAUDE.md rule 4): `prompts/<name>_v<N>.md` with a frontmatter header,
registered in `prompts/metadata.json`. Released versions are never edited in place."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Prompt:
    version: str
    model_default: str
    body: str

    @property
    def placeholders(self) -> set[str]:
        return set(PLACEHOLDER.findall(self.body))

    def render(self, **values: str) -> str:
        missing = self.placeholders - values.keys()
        unexpected = values.keys() - self.placeholders
        if missing:
            raise ValueError(f"{self.version}: missing values for {sorted(missing)}")
        if unexpected:
            raise ValueError(f"{self.version}: unexpected values {sorted(unexpected)}")
        return PLACEHOLDER.sub(lambda m: values[m.group(1)], self.body)


def load_prompt(version: str, prompts_dir: Path) -> Prompt:
    path = prompts_dir / f"{version}.md"
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path} has no frontmatter")
    header, _, body = text[4:].partition("\n---\n")
    meta: dict[str, str] = {}
    for line in header.splitlines():
        name, sep, value = line.partition(":")
        if sep:
            meta[name.strip()] = value.strip()
    if meta.get("version") != version:
        raise ValueError(f"{path} declares version {meta.get('version')!r}, expected {version!r}")
    registry = json.loads((prompts_dir / "metadata.json").read_text())
    if version not in registry:
        raise ValueError(f"{version} is not registered in {prompts_dir / 'metadata.json'}")
    return Prompt(
        version=version, model_default=meta.get("model_default", ""), body=body.lstrip("\n")
    )

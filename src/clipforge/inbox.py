"""The local `videos/` inbox for `clipforge clip`: which videos are new, where they go on the
Modal Volume, the record of what was submitted, and fetching results into `videos/out/`.

Uploads and downloads shell out to the `modal volume put/get` CLI, so this module (and
cli.py) never import modal (ADR-9: only app.py does).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from clipforge.hashing import sha256_file
from clipforge.models import Channel, InboxEntry

VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"})
OUT_DIR = "out"
LEDGER_NAME = ".clipforge.json"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
CHANNELS_NAME = "channels.toml"
RESERVED = frozenset({OUT_DIR, "schedule"})  # folders in videos/ that are never channels
_IMPORT_ONLY_KEYS = frozenset({"account", "kind", "campaign"})
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def is_video(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES


def load_channels(path: Path) -> dict[str, Channel]:
    """`videos/channels.toml`, or no channels if it's missing. Raises ValueError when invalid."""
    if not path.exists():
        return {}
    channels: dict[str, Channel] = {}
    for slug, fields in tomllib.loads(path.read_text()).items():
        if not _SLUG.fullmatch(slug) or slug in RESERVED:
            raise ValueError(
                f"channel {slug!r}: use lowercase letters, digits and -, and not out/schedule"
            )
        if not isinstance(fields, dict):
            raise ValueError(f"channel {slug!r}: expected a [{slug}] table")
        # `account`, `kind` and `campaign` are read by `source import-toml`, not by Channel
        known = {k: v for k, v in fields.items() if k not in _IMPORT_ONLY_KEYS}
        channels[slug] = Channel.model_validate(known)
    return channels


class Ledger:
    """`{video key: InboxEntry}` for videos already submitted, kept next to the videos. Keys are
    paths relative to the inbox folder ("ep.mp4", "billy-garton/ep.mp4"). The old format,
    `{name: job_id}`, loads as already fetched."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            raw: dict[str, object] = json.loads(path.read_text()) if path.exists() else {}
            self._data = {
                key: InboxEntry(job_id=value, status="fetched")
                if isinstance(value, str)
                else InboxEntry.model_validate(value)
                for key, value in raw.items()
            }
        except (ValueError, AttributeError) as exc:  # bad JSON, a bad entry, not an object
            raise ValueError(
                f"{path}: unreadable ledger ({type(exc).__name__}); fix or restore it"
            ) from exc

    def get(self, key: str) -> InboxEntry | None:
        return self._data.get(key)

    def job_id(self, key: str) -> str | None:
        entry = self._data.get(key)
        return entry.job_id if entry else None

    def submitted(self) -> list[str]:
        """Keys whose clips haven't been fetched (running, done or failed on Modal)."""
        return sorted(k for k, e in self._data.items() if e.status == "submitted")

    def record(self, key: str, job_id: str) -> None:
        self.update(key, InboxEntry(job_id=job_id))

    def update(self, key: str, entry: InboxEntry) -> None:
        self._data[key] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: e.model_dump(mode="json", exclude_none=True) for k, e in self._data.items()}
        # write-then-rename: an interrupted write never leaves a half-written ledger
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)


@dataclass(frozen=True)
class InboxVideo:
    path: Path
    key: str  # ledger key, relative to the inbox folder
    channel: str | None  # slug, or None for a loose video


def inbox_videos(folder: Path, known: Collection[str]) -> tuple[list[InboxVideo], list[str]]:
    """Videos directly in `folder` and in the subfolders named like a known source id, sorted
    by key, plus the names of subfolders that hold videos but have no source (`unknown`)."""
    videos = [InboxVideo(p, p.name, None) for p in folder.iterdir() if is_video(p)]
    unknown: list[str] = []
    subfolders = (
        p for p in folder.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in RESERVED
    )  # fmt: skip
    for sub in sorted(subfolders):
        inside = [p for p in sub.iterdir() if is_video(p)]
        if sub.name not in known:
            if inside:
                unknown.append(sub.name)
            continue
        videos += [InboxVideo(p, f"{sub.name}/{p.name}", sub.name) for p in inside]
    return sorted(videos, key=lambda v: v.key.lower()), unknown


def pending(
    folder: Path, ledger: Ledger, known: Collection[str]
) -> tuple[list[InboxVideo], list[str]]:
    """Videos not submitted yet (plus the `unknown` folders from `inbox_videos`)."""
    videos, unknown = inbox_videos(folder, known)
    return [v for v in videos if ledger.get(v.key) is None], unknown


def volume_path(local: Path) -> str:
    """`uploads/<sha8>-<safe name>`: same bytes → same path (no re-upload clash), and two
    different files with the same name never overwrite each other."""
    safe = _UNSAFE.sub("_", local.stem).strip("_")[:80] or "video"
    return f"uploads/{sha256_file(local)[:8]}-{safe}{local.suffix.lower()}"


class ModalCliUploader:
    """Copies a local file onto the Modal Volume with `python -m modal volume put`."""

    def __init__(
        self,
        volume: str = "clipforge-jobs",
        run: Callable[[list[str]], object] | None = None,
    ) -> None:
        self.volume = volume
        self._run = run or (lambda argv: subprocess.run(argv, check=True))

    def put(self, local: Path, remote: str) -> None:
        argv = [sys.executable, "-m", "modal", "volume", "put", "--force", self.volume]
        self._run([*argv, str(local), f"/{remote.lstrip('/')}"])


class ModalCliDownloader:
    """Copies a Volume folder to `dest` with `python -m modal volume get`: no zip and no web
    endpoint timeout. It downloads into a hidden staging folder and moves it into place at the
    end, so an interrupted download never leaves a half-filled result folder."""

    def __init__(
        self,
        volume: str = "clipforge-jobs",
        run: Callable[[list[str]], object] | None = None,
    ) -> None:
        self.volume = volume
        self._run = run or (lambda argv: subprocess.run(argv, check=True))

    def get(self, remote: str, dest: Path) -> None:
        """`remote` is a folder on the Volume; its contents end up directly in `dest`."""
        staging = dest.with_name(f".{dest.name}.downloading")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        argv = [sys.executable, "-m", "modal", "volume", "get", "--force", self.volume]
        self._run([*argv, f"/{remote.strip('/')}", str(staging)])
        (staging / Path(remote).name).rename(dest)
        shutil.rmtree(staging)

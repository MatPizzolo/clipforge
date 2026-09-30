"""Deterministic hashes for source files and stage cache keys (proposed ADR-8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file, read in 1 MiB chunks so large videos don't load into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(model: BaseModel) -> str:
    """JSON with sorted keys and no whitespace, so equal models always serialize the same."""
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def cache_key(
    stage: str,
    stage_version: str,
    inputs: list[BaseModel],
    extra: dict[str, str] | None = None,
) -> str:
    """Cache key for a stage output: inputs + explicit stage version + prompt/model versions.

    Uses an explicit per-stage version instead of the git SHA, so unrelated commits
    don't invalidate every cached transcript.
    """
    payload = {
        "stage": stage,
        "stage_version": stage_version,
        "inputs": [canonical_json(model) for model in inputs],
        "extra": dict(sorted((extra or {}).items())),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]

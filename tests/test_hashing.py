from pathlib import Path

from pydantic import BaseModel

from clipforge.hashing import cache_key, sha256_file
from clipforge.models import ClipOptions

GOLDEN = "c8236815efcf437f"  # re-pinned 2026-09-28 with a contract-independent sample


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_file_streams_multiple_chunks(tmp_path: Path) -> None:
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * (3 * 1024 * 1024 + 7))
    assert len(sha256_file(f)) == 64


def test_cache_key_is_deterministic_and_sensitive() -> None:
    opts = ClipOptions()
    base = cache_key("highlights", "1", [opts], {"prompt": "highlights_v1", "model": "m"})
    same = cache_key("highlights", "1", [ClipOptions()], {"model": "m", "prompt": "highlights_v1"})
    assert base == same
    assert base != cache_key("highlights", "2", [opts], {"prompt": "highlights_v1", "model": "m"})
    assert base != cache_key(
        "highlights", "1", [ClipOptions(n=3)], {"prompt": "highlights_v1", "model": "m"}
    )
    assert base != cache_key("highlights", "1", [opts], {"prompt": "highlights_v2", "model": "m"})


class _GoldenSample(BaseModel):
    """A fixed input for the pinned key: independent of real contracts, so adding a field to
    ClipOptions (for example) doesn't look like a hashing change."""

    n: int = 5
    min_len: float = 30.0
    max_len: float = 60.0


def test_cache_key_golden_value() -> None:
    # Pinned: if this changes, every cached stage output is invalidated. Bump deliberately.
    assert cache_key("highlights", "1", [_GoldenSample()], {"prompt": "highlights_v1"}) == GOLDEN


def test_cache_key_edge_cases() -> None:
    a, b = ClipOptions(n=1), ClipOptions(n=2)
    assert cache_key("s", "1", [a, b]) != cache_key("s", "1", [b, a])
    assert cache_key("s", "1", [a], None) == cache_key("s", "1", [a], {})

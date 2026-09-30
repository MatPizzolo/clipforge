import json
from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.prompts import load_prompt

PROMPTS = Settings(_env_file=None).prompts_dir


def test_load_highlights_v1() -> None:
    prompt = load_prompt("highlights_v1", PROMPTS)
    assert prompt.version == "highlights_v1" and prompt.model_default == "claude-haiku-4-5"
    assert prompt.placeholders == {"min_len", "max_len", "language", "transcript"}
    assert '{"clips": []}' in prompt.body  # JSON braces are not placeholders


def test_render_fills_only_declared_placeholders() -> None:
    prompt = load_prompt("highlights_v1", PROMPTS)
    text = prompt.render(
        min_len="30", max_len="60", language="en", transcript="[0.0-3.1] S1: {curly} words"
    )
    assert "Target clip length: 30–60 seconds." in text  # noqa: RUF001 (the prompt's en dash)
    assert "{curly}" in text  # inserted values are never re-scanned
    assert "{min_len}" not in text and '"clips"' in text


def test_render_rejects_missing_or_extra_values() -> None:
    prompt = load_prompt("highlights_v1", PROMPTS)
    with pytest.raises(ValueError, match="missing"):
        prompt.render(min_len="30", max_len="60", language="en")
    with pytest.raises(ValueError, match="unexpected"):
        prompt.render(min_len="30", max_len="60", language="en", transcript="t", tone="fun")


def test_version_must_match_file_and_registry(tmp_path: Path) -> None:
    (tmp_path / "metadata.json").write_text(json.dumps({"a_v1": {}}))
    (tmp_path / "a_v1.md").write_text("---\nversion: a_v2\n---\nbody {x}\n")
    with pytest.raises(ValueError, match="declares version"):
        load_prompt("a_v1", tmp_path)
    (tmp_path / "b_v1.md").write_text("---\nversion: b_v1\n---\nbody\n")
    with pytest.raises(ValueError, match=r"metadata\.json"):
        load_prompt("b_v1", tmp_path)


def test_load_keywords_v1() -> None:
    prompt = load_prompt("keywords_v1", PROMPTS)
    assert prompt.placeholders == {"language", "words", "max_keywords"}
    assert "keywords" in prompt.render(language="en", words="0 HELLO", max_keywords="1")


def test_load_keywords_v2() -> None:
    prompt = load_prompt("keywords_v2", PROMPTS)
    assert prompt.placeholders == {"language", "words", "max_keywords", "title"}
    assert "title_keyword" in prompt.render(
        language="en", words="0 HELLO", max_keywords="1", title="T0 HI"
    )

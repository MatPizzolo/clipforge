from pathlib import Path

import pytest

from clipforge.accounts.blueprints import BlueprintError, list_blueprints, load_blueprint
from clipforge.config import Settings
from clipforge.models import Platform

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINTS = ROOT / "blueprints"


def test_the_three_clip_blueprints_load() -> None:
    names = {b.name: b for b in list_blueprints(BLUEPRINTS)}
    assert set(names) == {"realtalk-clips", "founder-tapes", "hombre-en-construccion"}
    assert all(b.category == "clips" and b.compliance.require_credit for b in names.values())
    assert names["hombre-en-construccion"].languages == ["es"]
    for blueprint in names.values():  # 01: every video goes to every enabled platform
        assert {p for p, prof in blueprint.platform_defaults.items() if prof.enabled} == set(
            Platform
        )
    assert "buy-x" in names["founder-tapes"].compliance.banned_claims


def test_prompt_names_exist() -> None:
    prompts = Settings(_env_file=None).prompts_dir  # type: ignore[call-arg]
    for blueprint in list_blueprints(BLUEPRINTS):
        for step, prompt in blueprint.prompts.items():
            assert (prompts / f"{prompt}.md").is_file(), f"{blueprint.name}: {step} -> {prompt}"


def test_file_name_must_match_and_errors_name_the_file(tmp_path: Path) -> None:
    (tmp_path / "x.toml").write_text('name = "y"\nversion = 1\n')
    with pytest.raises(BlueprintError, match=r"x\.toml"):
        load_blueprint(tmp_path, "x")
    with pytest.raises(BlueprintError, match="no blueprint"):
        load_blueprint(tmp_path, "missing")


def test_blueprint_name_is_validated_before_any_path(tmp_path: Path) -> None:
    with pytest.raises(BlueprintError):
        load_blueprint(tmp_path, "../x")

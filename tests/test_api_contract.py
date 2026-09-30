"""The S3a dashboard parses GET /posting and GET /jobs/{id} with zod schemas generated from the
2026-09-29 API. Responses may only grow: no field renamed, removed or retyped, at any nesting
level, and no enum member removed (spec §2)."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from clipforge.models import ChannelProgress, JobView, PostingOverview

FROZEN = json.loads(
    (Path(__file__).parent / "fixtures" / "api_contract_2026-09-29.json").read_text()
)
SHAPE_KEYS = ("$ref", "type", "anyOf", "allOf", "items", "additionalProperties", "format")


def _compare(where: str, old: dict, new: dict) -> list[str]:
    """Problems found when `new` replaces `old` (one object schema or one enum def)."""
    problems: list[str] = []
    if "enum" in old and not set(old["enum"]) <= set(new.get("enum", [])):  # enums only gain
        problems.append(f"{where}: enum members removed")
    for name, old_field in old.get("properties", {}).items():
        new_field = new.get("properties", {}).get(name)
        if new_field is None:
            problems.append(f"{where}.{name} was removed or renamed")
            continue
        for key in SHAPE_KEYS:
            if old_field.get(key) != new_field.get(key):
                problems.append(f"{where}.{name} changed {key}")
        if "enum" in old_field and not set(old_field["enum"]) <= set(new_field.get("enum", [])):
            problems.append(f"{where}.{name}: enum members removed")
    added = set(new.get("properties", {})) - set(old.get("properties", {}))
    newly_required = set(new.get("required", [])) - set(old.get("required", []))
    if not newly_required <= added:  # only brand-new fields may be required
        problems.append(f"{where}: existing fields became required: {newly_required - added}")
    return problems


def compare_schemas(old: dict, new: dict, name: str) -> list[str]:
    """Compare the top level and every nested `$defs` entry of the frozen schema."""
    problems = _compare(name, old, new)
    new_defs = new.get("$defs", {})
    for def_name, old_def in old.get("$defs", {}).items():
        if def_name in new_defs:
            problems += _compare(f"{name}/{def_name}", old_def, new_defs[def_name])
        else:
            problems.append(f"{name}/{def_name} was removed or renamed")
    return problems


@pytest.mark.parametrize("model", [PostingOverview, ChannelProgress, JobView])
def test_fields_keep_names_and_types(model: type[BaseModel]) -> None:
    assert compare_schemas(FROZEN[model.__name__], model.model_json_schema(), model.__name__) == []


def test_pin_bites_on_nested_changes() -> None:
    old = FROZEN["JobView"]
    nested = next(n for n, d in old["$defs"].items() if d.get("properties"))
    broken = copy.deepcopy(old)
    field = next(iter(broken["$defs"][nested]["properties"]))
    del broken["$defs"][nested]["properties"][field]
    assert any(f"{nested}.{field}" in p for p in compare_schemas(old, broken, "JobView"))
    enum_def = next(n for n, d in old["$defs"].items() if "enum" in d)
    broken = copy.deepcopy(old)
    broken["$defs"][enum_def]["enum"] = broken["$defs"][enum_def]["enum"][1:]
    assert any("enum members removed" in p for p in compare_schemas(old, broken, "JobView"))
    optional = next(n for n in old["properties"] if n not in old.get("required", []))
    broken = copy.deepcopy(old)
    broken["required"] = [*broken.get("required", []), optional]
    assert any("became required" in p for p in compare_schemas(old, broken, "JobView"))

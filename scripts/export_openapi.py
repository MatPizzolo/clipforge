"""Write the job API's OpenAPI schema to web/openapi.json (Studio S3a).

The FastAPI app is built with stub dependencies that are never called, so this needs no Modal
and no secrets. The docs routes stay disabled: `app.openapi()` works without `openapi_url`.
`--check` exits 1 when the committed file is out of date.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from clipforge.api.main import ApiContext, create_app
from clipforge.config import Settings

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "openapi.json"


def _unused() -> NoReturn:
    raise RuntimeError("the OpenAPI export never calls API dependencies")


def render() -> str:
    app = create_app(ApiContext(Settings(_env_file=None), deps=_unused, sender=_unused))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the job API's OpenAPI schema.")
    parser.add_argument("--check", action="store_true", help="exit 1 if web/openapi.json is stale")
    args = parser.parse_args(argv)
    text = render()
    name = OUT.relative_to(ROOT)
    if args.check:
        if not OUT.is_file() or OUT.read_text() != text:
            fix = "uv run python scripts/export_openapi.py"
            print(f"{name} is stale: run `{fix}`", file=sys.stderr)
            return 1
        print(f"{name} is up to date")
        return 0
    OUT.write_text(text)
    print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

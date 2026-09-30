---
description: Pick up the next unchecked ROADMAP item and implement it end to end
---

1. Read ROADMAP.md and find the first unchecked item (or the one given here: $ARGUMENTS).
2. Read docs/ARCHITECTURE.md sections relevant to it and any related ADRs.
3. Write a short plan: files to touch, contracts affected, tests to add. Wait for my OK if the plan changes a contract in models.py.
4. Implement with tests. Run `uv run ruff check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`.
5. Tick the item in ROADMAP.md. If you made an architectural choice, add an ADR.
6. Summarize what changed and how to try it.

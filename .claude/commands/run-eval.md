---
description: Run the highlight eval and compare against the last result
argument-hint: [prompt_version] [model]
---

1. Run `uv run clipforge eval --set evals/v1 $ARGUMENTS`.
2. Load the newest and previous files in `evals/results/`.
3. Report a table: precision@5, recall, boundary error, cost per source hour, latency, with deltas.
4. Apply the ship rule from docs/EVALS.md and say clearly whether this version should ship.
5. List the 3 worst misses (gold segments not found) and the 3 worst false positives, with transcript snippets, and suggest prompt changes.

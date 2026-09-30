#!/usr/bin/env bash
# The only production deploy path (card 001, decision log #382). The owner runs it on main.
#   scripts/deploy.sh --dry-run
#   scripts/deploy.sh --reason "S1 checkpoint: slot guard"
#   scripts/deploy.sh --reason "…" --rollout-step 4c.7     (STATE_READS=postgres, runbook 4c.7)
# Every check and its reason is in scripts/deploy.py.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec uv run --quiet python scripts/deploy.py "$@"

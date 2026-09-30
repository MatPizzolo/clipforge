#!/usr/bin/env bash
# Print a hash of the working tree: tracked and untracked (not ignored) files as they are now.
# Uses a throwaway index, so the real index (what the owner has staged) is never touched.
# scripts/check.sh stores it after a green run; .claude/hooks/stop_check.py compares it.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cp "$(git rev-parse --git-path index)" "$tmp" 2>/dev/null || true
GIT_INDEX_FILE="$tmp" git add -A
GIT_INDEX_FILE="$tmp" git write-tree

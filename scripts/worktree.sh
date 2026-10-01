#!/usr/bin/env bash
# Create or remove a card's git worktree (card 001; runbook §3.2). The owner runs it.
#
#   scripts/worktree.sh <branch>            ../clipForge-<stream> on <branch> (new from origin/main,
#                                           or the existing branch), with .env, deps and web deps
#   scripts/worktree.sh --remove <branch>   remove that worktree once its PR is merged
#   --no-deps                               skip uv sync and npm ci (tests)
#
# The branch prefix must be in scripts/scopes.toml (x0/, s1/, s3c/, ...).
set -euo pipefail

usage() { sed -n '2,9p' "$0"; exit 2; }

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

remove=0 deps=1
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --remove) remove=1 ;;
    --no-deps) deps=0 ;;
    *) usage ;;
  esac
  shift
done
branch="${1:-}"
[[ -n "$branch" && $# -eq 1 ]] || usage

if ! stream="$(python3 scripts/check_scope.py --stream-of "$branch")"; then
  echo "refused: add the prefix to scripts/scopes.toml first (a coord/ change)" >&2
  exit 1
fi
# The main checkout is the first entry of `git worktree list`; worktrees sit beside it.
main_checkout="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
path="$(dirname "$main_checkout")/clipForge-$stream"

if [[ $remove == 1 ]]; then
  listed="$(git worktree list --porcelain | awk -v b="refs/heads/$branch" '
    /^worktree /{w=substr($0,10)} $0=="branch " b {print w}')"
  [[ -n "$listed" ]] || { echo "refused: no worktree has $branch checked out" >&2; exit 1; }
  git fetch --quiet origin
  merged=0
  if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
    merged=1
  elif command -v gh >/dev/null &&
    [[ "$(gh pr list --head "$branch" --state merged --json number --jq length 2>/dev/null)" -gt 0 ]]; then
    merged=1  # squash merges leave the branch outside main's history
  fi
  [[ $merged == 1 ]] || { echo "refused: $branch isn't merged into origin/main (no merged PR)" >&2; exit 1; }
  git worktree remove "$listed"  # refuses by itself if the worktree has uncommitted changes
  echo "removed $listed"
  echo "the branch is kept; delete it with: git branch -D $branch"
  exit 0
fi

git fetch --quiet origin
# The card on origin/main that names this branch ("Stream: S1 · Branch: `s1/finish` · Worktree: …").
card="$(git grep -l "Branch: \`$branch\`" origin/main -- 'docs/cards/[0-9]*.md' 2>/dev/null \
  | head -n 1 | sed 's|^origin/main:||' || true)"
if [[ -n "$card" ]]; then
  named="$(git show "origin/main:$card" | head -n 12 \
    | sed -n 's|.*Worktree: `\.\./\(clipForge-[A-Za-z0-9._-]*\)`.*|\1|p' | head -n 1)"
  if [[ -n "$named" ]]; then
    path="$(dirname "$main_checkout")/$named"  # the card's own worktree name wins
  fi
fi
[[ ! -e "$path" ]] || { echo "refused: $path already exists" >&2; exit 1; }
if git show-ref --verify --quiet "refs/heads/$branch"; then
  git worktree add "$path" "$branch"
elif git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
  git worktree add "$path" -b "$branch" --track "origin/$branch"
else
  # --no-track: a card branch never tracks main; the first push sets its own upstream.
  git worktree add "$path" -b "$branch" --no-track origin/main
fi

# Secrets are copied, never printed.
for file in .env web/.env.local; do
  if [[ -f "$main_checkout/$file" ]]; then
    cp "$main_checkout/$file" "$path/$file"
    echo "copied $file"
  fi
done

if [[ $deps == 1 ]]; then
  (cd "$path" && uv sync)
  if [[ -d "$path/web" ]]; then
    (cd "$path/web" && npm ci --no-audit --no-fund)
  fi
fi

echo
echo "ready: $path on $branch"
echo "next: open a Claude Code session in $path and paste:"
if [[ -n "$card" ]]; then
  echo "  Run card docs/cards/$(basename "$card")"
else
  echo "  Run card docs/cards/<NNN>-$stream-<topic>.md   (no card names $branch yet)"
fi
echo "first push (owner, at the first checkpoint): git push -u origin $branch"

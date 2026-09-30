#!/usr/bin/env bash
# The single gate (card 001, decision log #380): run before every checkpoint and in CI.
#
#   scripts/check.sh              everything: python, web, docs, scope
#   scripts/check.sh --python     ruff, format, mypy, fast tests, the OpenAPI contract
#   scripts/check.sh --web        npm run check + gen:check in web/ (add --e2e for Playwright)
#   scripts/check.sh --docs       tests/test_docs.py
#   scripts/check.sh --scope      scripts/check_scope.py against origin/main
#
# Flags combine. Fails fast; prints one summary line per step. A green full run writes
# .superpowers/check-ok (the working tree's hash), which the Stop hook reads.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

want_python=0 want_web=0 want_docs=0 want_scope=0 want_e2e=0 explicit=0
for arg in "$@"; do
  case "$arg" in
    --python) want_python=1 explicit=1 ;;
    --web) want_web=1 explicit=1 ;;
    --docs) want_docs=1 explicit=1 ;;
    --scope) want_scope=1 explicit=1 ;;
    --e2e) want_e2e=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "check.sh: unknown flag $arg (see --help)" >&2; exit 2 ;;
  esac
done
if [[ $explicit == 0 ]]; then
  want_python=1 want_web=1 want_docs=1 want_scope=1
fi

summary=()
started=$SECONDS

step() {
  # step <name> <command...>: run it, keep its output only on failure, stop on the first failure.
  local name="$1"; shift
  local log t0=$SECONDS
  log="$(mktemp)"
  if "$@" >"$log" 2>&1; then
    local last
    last="$(grep -v '^\s*$' "$log" | tail -n 1 | cut -c1-100)"
    summary+=("ok   $name ($((SECONDS - t0))s)${last:+: $last}")
    rm -f "$log"
  else
    summary+=("FAIL $name ($((SECONDS - t0))s)")
    echo "---- $name failed: $* ----" >&2
    tail -n 60 "$log" >&2
    rm -f "$log"
    print_summary
    exit 1
  fi
}

print_summary() {
  echo "== scripts/check.sh summary =="
  printf '%s\n' "${summary[@]}"
}

if [[ $want_python == 1 ]]; then
  step "ruff check" uv run ruff check .
  step "ruff format" uv run ruff format --check .
  step "mypy" uv run mypy src
  step "pytest (fast)" uv run pytest -q -m "not gpu and not slow"
  step "openapi contract" uv run python scripts/export_openapi.py --check
fi

if [[ $want_web == 1 ]]; then
  if [[ -d web ]]; then
    if [[ ! -d web/node_modules ]]; then
      summary+=("FAIL web: web/node_modules is missing (run: cd web && npm ci)")
      print_summary
      exit 1
    fi
    step "web check (lint, typecheck, test, build)" npm --prefix web run check
    step "web gen:check" bash -c 'cd web && npm run gen:check'
    if [[ $want_e2e == 1 ]]; then
      step "web e2e" bash -c 'cd web && npm run e2e'
    fi
  else
    summary+=("skip web (no web/)")
  fi
fi

if [[ $want_docs == 1 ]]; then
  step "docs" uv run pytest -q tests/test_docs.py
fi

if [[ $want_scope == 1 ]]; then
  step "scope" uv run python scripts/check_scope.py
fi

summary+=("green in $((SECONDS - started))s")
print_summary

# Only a full run counts for the Stop hook.
if [[ $explicit == 0 ]]; then
  mkdir -p .superpowers
  scripts/tree_hash.sh > .superpowers/check-ok
fi

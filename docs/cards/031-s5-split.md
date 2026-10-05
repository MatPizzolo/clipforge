# Card 031: S5 (S5-1) — `app.py` split into `modal_app/`

Status: proposed
Stream: S5 (S5-1) · Branch: `s5/split` · Worktree: `../clipForge-s5` (created with `scripts/worktree.sh s5/split`)
Decision-log range: #680–#719 (append only; shared in sequence by cards 031–034, which run one at a time: re-read the log and take the next free number in the range)
Model: mid-tier (a pure move with a written plan)
Depends on: card 014 (S2a) **deployed** with its owner steps done, and **before card 015 or 022 starts** (log #591): this card lands right after 014 so no S2 or S3 card edits `app.py` while it moves. Per log #144, no other code card is on `main` undeployed when this one merges
Cost cap: $0.05 of Modal/API spend (log #605; the owner's `smoke` run, about $0.01, counts; the session needs no Modal run)

## Context
Card 021 designed and planned S5, media servers and the producer registry: spec `docs/superpowers/specs/2026-10-02-studio-s5-design.md` (owner-approved section by section), plan `docs/superpowers/plans/2026-10-03-studio-s5.md` (15 tasks, four deployable parts; PR #41; log #580–#605). LLM tracing (Langfuse) left S5 by the owner's ruling (#597; draft ADR-53 in 05). The build is four cards (log #148): **this card is S5-1 (plan Task 1)**, then 032 (S5-2, Tasks 2–6), 033 (S5-3, Tasks 7–11) and 034 (S5-4, Tasks 12–15). They share the `s5/` prefix, its log range and one worktree, one card at a time.

S5-1 moves today's `app.py` into a `modal_app/` package (`resources`, `images`, `pipeline`, `crons`, `web`, `entrypoints`) **unchanged**: `app.py` stays the deploy entry and re-exports every name, so `modal run src/clipforge/app.py::…`, `scripts/deploy.sh`, CI and `tests/test_app.py`'s lookups don't change, and the deployed function list is identical. It moves whatever `app.py` holds when the card starts, S2a's `dispatcher` included (#583, #591). After it, only `app.py` and `modal_app/**` may import `modal` (a new boundary test).

Other sessions: card 015 (S2b) and card 022 (S3-1) wait for this deploy (#591); every later card's "only `app.py` imports `modal`" line then reads "only `app.py` and `modal_app/`" (the coordinator updates the cards after the merge).

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S5 plan: header, Global Constraints, Review Focus, File map, Part S5-1 (Task 1, the owner deploy steps and the rollback)
3. The S5 spec §7.1 (the split)
4. `docs/DECISIONS.md`: ADR-9, ADR-12, ADR-30
5. Log rows #583, #591, #597, #605, #144 and #148 in `docs/studio/10-decision-log.md`
6. Card 014's report (what S2a added to `app.py`)
7. The code it changes: `src/clipforge/app.py`, `tests/test_app.py`, `scripts/deploy.sh` (comments), `.claude/skills/new-stage/SKILL.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s5/`: `src/**` (`app.py` and the new `modal_app/`), `tests/**` (`tests/test_app.py`, the new `tests/test_modal_boundary.py`), `scripts/deploy.sh` and `scripts/deploy.py` (only comments that call `app.py` the only Modal module), `.claude/skills/new-stage/**` (its Modal rule), `CLAUDE.md` ("the only modal importer" and Layout), `docs/ARCHITECTURE.md` ("`app.py` is the only Modal module"), `docs/superpowers/plans/*studio-s5*` (ticks and a status line), `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S5-1 tick only after the owner confirms the deploy), its own report, and log rows in #680–#719.
- Must not edit: anything else under `scripts/` or `.claude/`, the S5 spec, `STATUS.md`, other cards, any stage, pipeline or posting module (a pure move: no behavior change), `pyproject.toml` and `uv.lock`.
- **No new dependencies.** **The session never deploys, stops the app or changes a secret.**

## Actions
1. **Before the move:** record `uv run python -c "from clipforge import app; print(sorted(app.app.registered_functions))"` on the card's starting `main` in the report.
2. **Task 1, the split:** failing tests first (`tests/test_modal_boundary.py`: only `app.py` and `modal_app/**` import `modal`; `tests/test_app.py`'s boundary test removed and its container-path tests reading `modal_app/images.py`); then `modal_app/__init__.py` (`app = modal.App("clipforge")`, then the submodule imports), `resources.py`, `images.py`, `pipeline.py`, `crons.py`, `web.py`, `entrypoints.py`, each with `__all__` (including the underscored helpers today's tests use: `_spawner`, `_repo_root`); `app.py` as the plan's deploy entry. Move code unchanged.
3. **Check the deploy surface:** the same function list command after the change prints the same names (paste both into the report).
4. **Docs:** `CLAUDE.md` (Layout: `modal_app/`; "app.py and modal_app/ are the only modal importers"), `docs/ARCHITECTURE.md`, `.claude/skills/new-stage/SKILL.md` (new Modal functions go in the matching `modal_app` module), and the `scripts/deploy.sh` comments.
5. **Checkpoint S5-1:** `scripts/check.sh` green; `pr-reviewer`; fix what it finds; the report with the function lists and the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S5-1): after actions 1–5. Suggested commit: `031: s5-1: app.py split into modal_app/ (no change live)`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `pr-reviewer` has no blocking findings, and the report lists what it said.
- `tests/test_modal_boundary.py` and `tests/test_app.py` pass, and the registered function list is identical before and after (both in the report).
- No line of moved code changed behavior (the diff of `modal_app/` against the old `app.py` is moves and imports only; the report says so).

## Owner steps
- Before: card 014 deployed with its owner steps; cards 015 and 022 not started. `scripts/worktree.sh s5/split`, open a session in `../clipForge-s5`, paste `Run card docs/cards/031-s5-split.md`.
- At A: commit with the suggested message, `git push -u origin s5/split`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout, runbook §1):
  1. **Pre-deploy check (#144, #145):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`).
  2. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S5-1: app.py split into modal_app/ (no change live)"`.
  3. `uv run modal run src/clipforge/app.py::smoke` (about $0.01): `smoke OK`.
  4. `uv run modal app list`: `clipforge` deployed; the Modal dashboard's function list unchanged.
  5. Commit the line `scripts/deploy.sh` added to `docs/ops/deploys.md`, and tell the coordinator: 015 and 022 can start, and the cards' Modal-boundary lines get updated.
- **Rollback:** `git revert` of the merge on `main`, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S5-1"`. Nothing else changed.

## Hand-off
Write `docs/reports/031-s5-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with the function lists, the reviewer's findings and the owner steps. Don't commit: the owner does. The next S5 card is 032 (S5-2), slotted by the coordinator between two deployed cards (#603); remove this worktree after the merge (`scripts/worktree.sh --remove s5/split`).

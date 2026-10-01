# Card 006: S4 — Timeline renderer

Status: proposed (after card 002 is merged)
Stream: S4 · Branch: `s4/timeline` · Worktree: `../clipForge-s4`
Decision-log range: #340–#379
Model: most capable for the design, mid-tier for the build
Depends on: card 002 merged (S4 edits `models.py` and `stages/`)
Cost cap: $2 (06's S4 card)

## Context
ADR-31 is accepted: one `Timeline` contract is the only render input, and clips move onto it first with identical output. The full brief is 06's S4 card. Paste 06's prompt B with it.

## Read first
`CLAUDE.md`, `STATUS.md`, 06's prompt B and S4 card, `src/clipforge/stages/render.py`, `captions.py`, `reframe.py`, ADR-18–21 and ADR-31.

## Scope
As `scripts/scopes.toml` allows for `s4/`.

## Actions
Follow 06's S4 card through prompt B's steps: design, then the spec for the owner's review, then the plan, then the build.

## Done when
06's S4 "done when", plus `scripts/check.sh` green.

## Owner steps
`scripts/worktree.sh s4/timeline` after card 002 is merged, then paste `Run card docs/cards/006-s4-timeline.md`.

## Hand-off
Reports go in `docs/reports/006-s4-<date>.md`. Don't commit. The owner's first push from the worktree is `git push -u origin <branch>`, then `gh pr create --fill`; PRs are squash-merged with the card number in the title.

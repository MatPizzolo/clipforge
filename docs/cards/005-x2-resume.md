# Card 005: X2 — talking-head spike, resume

Status: proposed (only after the owner rules on O7, decision-log Open table)
Stream: X2 · Branch: `x2/talking-head` · Worktree: `../clipForge-x2`
Decision-log range: #320–#339
Model: most capable
Depends on: card 001 merged; O7 ruled
Cost cap: $29.60 (the $30 card minus what was spent before the pause)

## Context
X2 stopped at about 25% on 2026-09-30: licenses checked, no clips generated. The findings, the method and the resume recipe are in `docs/studio/spikes/x2-talking-head.md`. Its weights are already on the `clipforge-models` Volume under `x2/`.

## Read first
1. 06's prompt C and its X2 card
2. `docs/studio/spikes/x2-talking-head.md`, and the O7 ruling in `docs/studio/10`

## Scope
As `scripts/scopes.toml` allows for `x2/`. Probe code only in `scratch/x2/`, which is ignored by git.

## Actions
1. Rebuild the probe from the spikes file. Use deployed spike apps `clipforge-x2*` and never the `clipforge` app.
2. An H100 smoke test per model.
3. The card's test set and the blind samples. Report, and wait for the owner's verdict.
4. After the verdict: update 03, the X2 line in 04, and the spikes file. Stop every spike app.

## Done when
The report table has measured GPU-seconds, cold start, dollars per output second, the owner's blind rating, and a recommendation.

## Owner steps
Rule on O7 first. Then `scripts/worktree.sh x2/talking-head` and paste `Run card docs/cards/005-x2-resume.md`.

## Hand-off
The report goes in `docs/reports/005-x2-<date>.md`. Don't commit. The owner's first push from the worktree is `git push -u origin <branch>`, then `gh pr create --fill`; PRs are squash-merged with the card number in the title.

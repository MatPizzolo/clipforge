# Card 011: S2 — publishing and autopilot, design and plan

Status: proposed
Stream: S2 · Branch: `s2/design` · Worktree: `../clipForge-s2` (created with `scripts/worktree.sh s2/design`)
Decision-log range: #440–#469 (append only, in this range)
Model: most capable (the next production-facing system; design and plan, no code)
Depends on: nothing to start. The build (a later card) starts after card 010's rollout
Cost cap: $0 (no Modal, Upload-Post or API spend; reading vendor docs is fine)

## Context
S2 is the next big step: founder.tapes and hombre.en.construccion launch with it (ADR-48, #428), and it turns the owner's manual posting into automatic publishing with review where it pays off. Its scope grew on 2026-10-01 with card 009's decisions. **04's S2 list is the source** (`docs/studio/04-roadmap.md`, S2):
- the `Publisher` protocol with `UploadPostPublisher` (primary) and `AssistedPublisher` (today's Telegram flow, ADR-28), one claim per (item, platform), the fallback only after Upload-Post's final failure;
- signed, expiring per-file media links from the Volume (ADR-13's mechanism) and the HMAC-checked webhook updating `posts` and `post_events`;
- AI-disclosure mapping per platform;
- **autopilot (ADR-48):** the `autopilot` table and its append-only history (one writer, `accounts/autopilot.py`), the Review dial and the Publish switch per account, presets, the graduation ladder (the system suggests, the owner taps), automatic demotions, the spot-check floor;
- **review windows:** the first 10 items after a format change, the first 5 per account after a `producer_version` change (ADR-49), the first 10 dubs in a pair;
- the brake for one account or the fleet (one Dict key with a scope, survives a Neon outage, cancels posts scheduled at Upload-Post);
- Telegram one-tap only for review items due within 2 h and the brake (#427); every other message carries Open → `/act/<kind>/<id>`;
- publishing-failure rows as instant alerts and "needs me" rows;
- **the dispatcher:** accept ADR-27 (drafted in 05); it replaces `posting_tick`, runs the 09:00 digest and the alert fold (S3 dashboard spec §8.1); `sweeper` and `posting_daily` stay (3 crons);
- the policy gate v1 (pure checks: disclosure, #ad, credits, license manifest, cross-account duplicates);
- tracking links (`GET /go/<slug>`, click logging, sub-ids);
- **migrations:** the landing-order rule (S3 dashboard spec §8.7); the first new migration also carries `jobs.error`, the `post_events.actor` column and the pause actor.

The state when this card starts: S1's code is deployed, Dict-only; card 010 moves production to Postgres in parallel. Design against S1's schema as merged (`alembic/versions/0001`, `db/`), assuming the rollout finishes before S2's build.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `docs/studio/04-roadmap.md` (S2), `docs/studio/06-session-prompts.md` (the S2 card and its 2026-10-01 note)
3. `docs/DECISIONS.md`: ADR-13, 23, 27 (draft, in `docs/studio/05`), 28, 29, 41, 44, 45, 46, 48, 49
4. The S3 dashboard spec (`docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md`): §2, §4, §7.11, §8.1, §8.4, §8.6, §8.7; `docs/studio/08` §2b and §2c
5. `docs/studio/02` §5–6 (distribution, measurement), `docs/studio/03` (Upload-Post: plans, AI-label fields, webhooks, rate limits)
6. The S1 spec and the code it built: `posting/` (repo, actions, backend), `bot/posting.py`, `db/`, `accounts/`, `ops.py`, `app.py`'s crons

## Scope
- May edit, as `scripts/scopes.toml` allows for `s2/`: the spec `docs/superpowers/specs/*-studio-s2-*` and the plan `docs/superpowers/plans/*-studio-s2*`.
- Must not edit: code, tests, `alembic/`, any other doc (propose changes to 04, 06, 08 or the runbook in the spec's last section; the coordinator applies them).

## Actions
1. **Questions first** (superpowers:brainstorming, one at a time, options with a recommendation). At least:
   - the Upload-Post plan (O4: Basic $24 for 5 profiles vs Professional $50 for 25) and how a profile maps to an account;
   - the order inside S2: what ships first (the publisher for realtalk, then autopilot? or autopilot with assisted posting first?) so each step is usable and deployable alone;
   - how the review lane works before S3's dashboard exists (Telegram review cards only, for items due within 2 h; the rest wait until S3, or Telegram cards for all in the meantime?);
   - the digest's content and time;
   - what happens to the assisted ✅ flow for accounts still on Publish off.
2. **Design** the parts above, approved section by section: contracts in `models.py` first (rule 2), the tables and the first migration (with the deferred items), the dispatcher's task model (due markers in the Dict, Postgres touched only when due), the publisher state machine (queued → scheduled → published / failed → fallback), the webhook and its idempotency, the brake, the windows and the ladder computations, the gate, tracking links, the failure rows and alerts, the rollout of S2 itself (creating founder.tapes and hombre, connecting profiles, the first auto-post on Hands-on).
3. **Tests and safety:** a fake publisher, golden gate cases, the brake under a Neon outage, the webhook replayed twice, the claim per (item, platform), the dispatcher never double-sending a slot (the #202 guard), cost.
4. **Write the spec** `docs/superpowers/specs/<date>-studio-s2-design.md`, including the proposed changes to 04, 06, 08 and the runbook, and ADR-27's acceptance text for the coordinator. Stop for the owner's review.
5. **After approval, write the plan** `docs/superpowers/plans/<date>-studio-s2.md`: tasks with tests first, checkpoints, deployable steps, the deploy and rollout steps for the owner. Stop for review.

## Checkpoints
- A: the questions answered and the design approved section by section, the spec written. Suggested commit: `011: s2: publishing and autopilot design spec`
- B: the plan written. Suggested commit: `011: s2: implementation plan`

## Done when
- The owner approved the spec at A and the plan at B.
- The plan's tasks cover every item in 04's S2 list, each with its tests, and name which tasks are deployable on their own.
- `scripts/check.sh --docs --scope` is green (the full gate at B).

## Owner steps
- Before: `scripts/worktree.sh s2/design`, open a session in `../clipForge-s2`, paste `Run card docs/cards/011-s2-design.md`.
- During: answer the design questions; decide O4 (the Upload-Post plan).
- At each checkpoint: commit, push (`git push -u origin s2/design` the first time), keep one PR open until B, squash-merge after B.

## Hand-off
Write `docs/reports/011-s2-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.

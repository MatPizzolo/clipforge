# Card 019: S3 — dashboard v1, spec delta and build plan

Status: proposed
Stream: S3 · Branch: `s3p/plan` · Worktree: `../clipForge-s3p` (created with `scripts/worktree.sh s3p/plan`)
Decision-log range: #610–#629 (append only, in this range; `s3/`'s #420–#439 is full, so this card has its own prefix, log #141)
Model: most capable (plan for the operational UI, no code)
Depends on: nothing to start. The build (later cards) waits for S1's rollout (card 010 done) and lands its routes after S2a's (card 014); going online needs card 004 (the S3a Vercel deploy). Runs alongside 010 (rollout, don't touch production), 017, 018, 020, 021
Cost cap: $0 (documents only; no Modal, Vercel, Neon or API spend)

## Context
Card 009 designed the dashboard as the studio's control room: inbox-first, a ~20-minute daily phone check-in, autopilot per account (spec `docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md`, approved; mockups in `docs/design/dashboard/`). The S3a shell (`web/`: login, Home over today's API) is built; its Vercel deploy is card 004, still waiting on the owner's Vercel steps (runbook §5b). There is no S3 build plan yet.

Since card 009:
- **S2 is planned and split into cards 014–016** (`docs/superpowers/plans/2026-10-02-studio-s2.md`). S2 already adds `/admin/*` routes in `api/main.py` under the bearer token: autopilot (`GET|PUT /admin/accounts/{id}/autopilot`, promote, ladder), the policy dry run, review (`GET /admin/review`, approve/reject, copy edits), publisher checks and tracking links. **S3 reuses them and must not duplicate S2's review, policy, autopilot or link routes.**
- **ADR-38 and 06's D9:** the dashboard calls a separate `admin` Modal endpoint, a second `@modal.asgi_app(requires_proxy_auth=True)` that reuses `create_app` with an admin router and its own `ADMIN_API_TOKEN` (missing → 503); the public `web` endpoint keeps the webhooks, download links, media links and `/go`. S2 put its admin routes on `create_app` before this endpoint exists, so the plan must say where `/admin/*` lives after S3 (only on `admin`, or on both during a transition) and how the Vercel route handlers authenticate (proxy-auth token pair plus the bearer, `X-Clipforge-Actor: web:<login>`).
- **ADR-44's link contract** (`/act/<kind>/<id>`, spec §7.10) and the "needs me" API (§8.3) are S3's; S2's Telegram cards already carry Open → `/act/...` links (`DASHBOARD_URL`), which 404 until S3 ships the page.
- **Migrations land one at a time, in landing order** (spec §8.7): S2a's 0002 first, then the hooks migration, then S3c. S3's tables (`needs_snoozes`, `needs_log`, `settings`, §10.2) go in a migration whose **number is assigned at landing**, after whichever is on `main` then.
- S3c (card 018) builds the account workspaces on S3's `admin` endpoint; the hooks card (020) adds the Hooks tab. S3 builds Compare and a minimal `/accounts/<id>` read view with the Overview, Autopilot and Activity tabs.

This card is design-and-plan only: checkpoint A covers the open questions and the spec delta, checkpoint B the plan. **Production is out of bounds today:** card 010 runs the S1 rollout's live steps at 22:00 New York time. Never deploy, touch `clipforge-secrets` or Vercel, or run Alembic.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3 dashboard spec: §1–§7 (pages; §7.10 the link contract, §7.11 "needs me" rows), §8 (gaps; §8.1 crons, §8.3 the needs API, §8.4, §8.7), §10.2
3. `docs/design/dashboard/DESIGN.md` and the mockups (`home.html`, `act.html`, `review.html`, `produce.html`, `results.html`, `accounts.html`, `account.html`)
4. `docs/DECISIONS.md`: ADR-2, 13, 38, 41, 44, 45, 48, 49, 50
5. The S2 plan: Global Constraints, File map, Tasks 8 (autopilot and policy admin routes), 15 (the review service and its routes), 19 (`publisher check`), 20 (the review batch), 21 (promote, ladder), 23–25 (the digest, failure rows, tracking links); the S2 spec §5–§7; cards 014–016
6. `docs/studio/06-session-prompts.md` (the S3 card with D8 and D9), `docs/studio/04-roadmap.md` (S3), `docs/studio/08-dashboard-and-operations.md` §2, §2b, §2c
7. The S3a spec and plan (`docs/superpowers/specs/2026-09-29-studio-s3a-design.md`, `docs/superpowers/plans/2026-09-29-studio-s3a.md`), card 004, and the `web/` code (read only): `web/lib/api/`, the auth setup, the mock API, the Playwright smoke
8. The API code (read only): `api/main.py`, `service.py`, `posting/actions.py`, `app.py`'s web endpoint
9. Log rows #420–#439, #440–#461, #138–#140

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3p/`: the S3 dashboard spec (`docs/superpowers/specs/*s3-dashboard*`, for the delta only, marked as a dated revision), the plan (`docs/superpowers/plans/*s3-dashboard*`), `docs/design/dashboard/**` (only if a mockup must change with the delta), `docs/studio/08-dashboard-and-operations.md`, its own report, and log rows #610–#629.
- Must not edit: code, tests, `web/`, `alembic/`, `docs/DECISIONS.md`, 04 and 06 (propose their changes in the spec's last section; the coordinator applies them), the S2 and S3c specs and plans, other cards.

## Actions
1. **Inventory** what S2 (cards 014–016) already builds that S3's pages call, route by route, and what is left for S3: the needs API (`GET /needs`, `GET /needs/{kind}/{id}`, `POST /needs/{kind}/{id}/{action}`), `GET /fleet/scoreboard`, `GET /slots`, `GET /accounts/{id}/activity`, `POST /batches/preview`, `POST /batches`, `GET /results/costs`, `GET|PUT /settings` (§10.2). Every row of §7.11 maps to its source (S2's tables, `jobs`, ops alerts) and its action backend (`posting/actions.py`, `accounts/autopilot.py`, S2's review service).
2. **Ask the open owner questions** (superpowers:brainstorming, one at a time, options with a recommendation). At least:
   - where `/admin/*` lives after S3: only on the `admin` endpoint (S2's routes move behind proxy auth in S3's first checkpoint), or on both until a cut-over date;
   - proxy auth on Vercel: the Modal proxy-auth token pair as Vercel env vars next to `ADMIN_API_TOKEN` (the owner's steps, runbook §5b), and the rotation story;
   - the build order: Home + `/act` + the needs API first (so S2's Telegram Open links stop 404ing), then Review, then Produce, then Results and Settings, or another order;
   - the review inbox before S2b: a queue manager only (D8), or wait for S2's approve routes;
   - Produce's batch planner: does it create jobs (ADR-48's caps then apply in `create_job`), or only preview until S6's filler;
   - the minimal `/accounts/<id>` view: which tabs ship in S3 and which wait for S3c's workspace;
   - polling interval and how dashboard actions redraw Telegram messages (ADR-44: every Telegram message of an item is redrawn or deleted).
3. **The spec delta** (a dated "Revised 2026-10-0X (card 019)" section, not a rewrite): what S2's plan changed (routes it owns, the review bridge `REVIEW_BATCH`, the digest), the admin endpoint decision, the migration "assigned at landing", and the proposed edits to 04's S3 list and 06's S3 card. **Checkpoint A: stop** for the owner's review.
4. **Write the plan** `docs/superpowers/plans/2026-10-0X-studio-s3-dashboard.md` in the S2 plan's structure: Global Constraints (no direct database access from `web/`; every write through the existing backends with `web:<login>`; the landing-order rule with the migration number assigned at landing and `EXPECTED_HEAD` moved in the same change; `web/openapi.json` and the generated client regenerated with each route change; no Modal outside `app.py`), Review Focus, a File map (Python and `web/`), then tasks with failing tests first (pytest for routes, Vitest units, Playwright on the mock API), exact route and contract signatures, and the link-contract test (§7.10: every link a Telegram message or alert can carry resolves to a page).
5. **Build checkpoints that each become a card:** for example S3-1 (the `admin` endpoint, proxy auth, `ADMIN_API_TOKEN`, moving S2's `/admin/*`), S3-2 (needs API, Home, `/act`), S3-3 (Review and Calendar), S3-4 (Produce with batches and the Jobs tab), S3-5 (Results → Costs, Settings, Compare, the account read view). Each with its owner steps (secrets by the `docs/ops/secrets.md` procedure, migrate, `scripts/deploy.sh`, the Vercel env vars), what the owner sees, and the rollback. Note card 004 as the prerequisite for any checkpoint the owner uses online.
6. **Coverage table:** every item of 04's S3 list and §10.2, mapped to its task and test, with the routes S2 owns marked "S2, reused".
7. `scripts/check.sh` green (`--docs --scope` at A, the full gate at B), the report, log rows in range for the owner's rulings, and stop at checkpoint B.

## Checkpoints
- A: actions 1–3. Suggested commit: `019: s3p: open questions and the S3 spec delta after S2's plan`
- B: actions 4–7. Suggested commit: `019: s3p: dashboard v1 build plan`

## Done when
- The owner approved the delta at A and the plan at B.
- The plan's coverage table maps every item of 04's S3 list and §10.2 to a task, and no S3 task re-implements an S2 route.
- Each build checkpoint is small enough for one card, deploys alone, and names its rollback.
- `scripts/check.sh` is green (paste its summary lines).

## Owner steps
- Before: `scripts/worktree.sh s3p/plan`, open a session in `../clipForge-s3p`, paste `Run card docs/cards/019-s3-dashboard-plan.md`.
- During: answer the questions in action 2.
- At each checkpoint: commit, push (`git push -u origin s3p/plan` the first time), keep one PR open until B, squash-merge after B.
- After: the Vercel steps (runbook §5b) and card 004 before the first checkpoint the dashboard is used online; the coordinator writes the build cards from the plan.

## Hand-off
Write `docs/reports/019-s3p-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.

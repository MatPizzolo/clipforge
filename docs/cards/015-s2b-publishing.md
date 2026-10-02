# Card 015: S2b — Upload-Post publishing for realtalk on Hands-on

Status: proposed
Stream: S2 (S2b) · Branch: `s2b/publishing` · Worktree: `../clipForge-s2b` (created with `scripts/worktree.sh s2b/publishing`)
Decision-log range: #500–#529 (append only, in this range)
Model: most capable (publishing to real accounts: claims, crash recovery, the webhook)
Depends on: card 014 merged and deployed, with one clean day after it (`dispatcher:` sends match, `posting verify` at 0). Owner steps before Task 10: Upload-Post Basic bought, the R5 call run with this session (Task 9) and its results read by the owner. Before the S2b deploy: the `realtalk-clips-en` profile connected, the webhook registered, and both secrets added through `docs/ops/secrets.md`
Cost cap: $5 of Modal/API spend (the R5 probe and smoke runs; spec §8). The Upload-Post Basic subscription ($24/month) is the owner's purchase, not session spend

## Context
Card 014 (S2a) deployed the rails: migration 0002, the `dispatcher` cron, the `brake:<scope>` keys, autopilot with every account Hands-on, the gate (log-only) and routing. **This card builds S2b, plan Tasks 9–20:** realtalk.clipsdaily publishes through Upload-Post, with review cards in Telegram. Read card 014's report first for what landed and any deviation.

Decisions that bind this card:
- **R5 gates every code task** (#458): Task 9 is one real Upload-Post call, with the owner, on a test profile (`s2-probe`), scheduled 2 or more days out and cancelled, so nothing is published. It checks (1) a repeated `Idempotency-Key` returns the same job after 10 minutes and after 24 h, (2) Basic's rate limit from the `X-RateLimit-*` headers, (3) a scheduled async upload is visible by `request_id` within seconds. **Results go in this card's report, and the owner reads them before Task 10 starts.**
  - `RECOVERY_WINDOW_S` = 600 only if the 10-minute repeat returned the same job; else it stays 0 (no re-send). It is never lowered "to fit".
  - The stuck-in-`claimed` threshold = max(120 s, the measured visibility delay).
  - The probe lives in `scratch/s2/r5_probe.py` (gitignored, throwaway, never imported by `src/`). The 24-hour repeat means Task 9 spans a day: build nothing else meanwhile except reading.
- **Upload-Post Basic** (O4 closed, #139): one profile per account, on all four platforms. httpx only, no SDK. `disable_inbox_fallback=true` always; `privacy_level` never sent.
- **Publishing state lives on the `posts` rows**, moved only by `publishing/state.py` (#446, #447, #459). One durable claim per (item, platform); the AssistedPublisher fallback runs only after Upload-Post's final failure.
- **The 09:00 review batch** is a bridge behind `REVIEW_BATCH`, exempt from the hourly cap and paced (R1, #442, #453). Review cards use `r:` callbacks; posting cards keep `p:`.
- **`GATE_ENFORCE` goes on in this step,** by the owner, only after `clipforge policy dry-run` reports "0 items would be held".
- **Secrets** `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` are optional: without them, publishing is off with the reason in `/status`, and the webhook answers 503. Never log the key, the webhook secret, a signed media link or an Upload-Post response body.

Other sessions: none on S2. Card 016 (S2c) waits for this deploy and a day on Hands-on.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `docs/reports/014-s2a-*.md`
3. The S2 plan: Global Constraints, Review Focus (items 1, 2, 3, 4 and 5 are pinned in Tasks 14–18), Part S2b (Tasks 9–20, the owner deploy steps and the rollback after Task 20)
4. The S2 spec: the Upload-Post facts at the top, §0–§0.1, §2, §3.1, §4.2–§4.4, §5.2–§5.3, §6 (all of it), §7.1, §8, §9
5. `docs/DECISIONS.md`: ADR-13, ADR-27, ADR-28, ADR-29, ADR-41, ADR-44, ADR-45, ADR-49
6. Log rows #440–#461 and #138–#140
7. `docs/ops/secrets.md`, `docs/studio/03-tools-and-models.md` (Upload-Post), runbook §1 and §6

## Scope
- May edit, as `scripts/scopes.toml` allows for `s2b/`: `src/**`, `tests/**`, `alembic/**`, `alembic.ini`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/openapi.json`, `web/lib/api/**`, `web/lib/mocks.ts` and `web/tests/unit/summaries.test.ts` (only if an additive API field reaches them), `docs/ops/secrets.md` (Task 17's two rows), `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*-studio-s2*`, `docs/studio/03-tools-and-models.md` (R5's measured Upload-Post facts), `docs/studio/04-roadmap.md` and `ROADMAP.md` (S2b ticks), `CLAUDE.md`, its own report, and log rows #500–#529. `scratch/s2/` is gitignored and free to use.
- Must not edit: the spec, the runbook, `STATUS.md`, other cards, stage modules, `prompts/`.
- **S2b adds no migration** unless R5's results force a column; if so, stop and ask first.
- **The session never deploys, changes a secret, or posts publicly.** The R5 probe runs only with the owner present, from `.env`, and prints statuses, never the key.

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 9, R5's real call** (with the owner): Step 1 (the owner buys Basic, creates `s2-probe`, puts `UPLOAD_POST_API_KEY` in `.env` only), Step 2 (write `scratch/s2/r5_probe.py`), Step 3 (run it, repeat at 10 minutes and at 24 h, then cancel the scheduled job), Step 4 (record the four results and the two derived values in the report and in 03's Upload-Post block), Step 5 (**stop**: the owner reads them before Task 10).
2. **Task 10:** `publishing/keys.py` and `publishing/state.py` (the one writer of the `posts` publish columns, `publishing:inflight:<ref>` and `publish:last_handoff`), `db/publishing.py`.
3. **Task 11:** the `Publisher` protocol and `Lookup`, `UploadPostPublisher` (httpx `MockTransport` in tests; per-platform AI flags), `FakePublisher`.
4. **Task 12:** signed media links (`publishing/media.py`, `GET /media/{item_id}.mp4`, TTL `MEDIA_LINK_TTL_S`).
5. **Task 13:** per-platform copy: extend Task 7's `copy_for` (Facebook, the `item.copy` override, `link_for`); `post_html` renders from it.
6. **Task 14:** the slot planner (`dispatch/plan.py`, `db/plans.py`) and the per-slot phases `plan`, `card`, `handoff`; the DST pinning test (`test_plan_across_dst_change`).
7. **Internal checkpoint (after Task 14):** `scripts/check.sh` green, the report updated, `pr-reviewer` on Tasks 10–14, **stop for the coordinator's review** before Task 15. No deploy here.
8. **Task 15:** the review service and the Telegram review cards (`review/service.py`, `review/cards.py`, `r:` callbacks, the admin review routes); pinned: `test_late_approve_after_window_says_missed`, `test_review_tap_from_other_chat_changes_nothing`.
9. **Task 16:** hand-off (`publishing/handoff.py`); pinned: `test_partial_accept_schedules_some_retries_one`.
10. **Task 17:** the Upload-Post webhook (`publishing/webhook.py`, `POST /webhooks/upload-post`: HMAC with `hmac.compare_digest`, the 5-minute window, delivery de-duplication), `set_disconnected`, and the two rows in `docs/ops/secrets.md`.
11. **Task 18:** reconcile, crash recovery (with R5's `RECOVERY_WINDOW_S` and stuck threshold), the retry check, the fallback check and the fallback (`publishing/reconcile.py`, `publishing/assisted.py`); pinned: `test_fallback_with_missing_video_marks_unavailable`.
12. **Task 19:** the brake at Upload-Post (`pause` cancels scheduled jobs; `cancel_scope`), `account edit --publisher-profile/--facebook-page-id/--clear-publisher`, `clipforge publisher check` (read-only) and its admin route.
13. **Task 20:** the 09:00 review batch (`dispatch/digest.py`'s `send_batch`, the `digest` task, paced, `digest:<date>`).
14. **Checkpoint S2b** (plan Task 20 step 5): update `docs/ARCHITECTURE.md` (publishing, the webhook, media links, reconcile) and `.env.example` (`UPLOAD_POST_API_KEY`, `UPLOAD_POST_WEBHOOK_SECRET`, `REVIEW_BATCH`, `MEDIA_LINK_TTL_S`, `RECOVERY_WINDOW_S` at R5's value, `UPLOAD_POST_PROFILE_LIMIT`); regenerate `web/openapi.json` if routes changed; run `pr-reviewer`, `security-reviewer` and `migration-reviewer` (the Dual write path); `scripts/check.sh` green; the report; stop.

## Checkpoints
- A (R5): after action 1. No commit needed (the probe is gitignored); the report records the results. The owner reads them, then says go.
- B (internal): after actions 2–7. Suggested commit: `015: s2b: publish state, publisher, media links, copy, slot planner`
- C (S2b): after actions 8–14. Suggested commit: `015: s2b: Upload-Post publisher, media links, webhook, reconcile, review cards and hand-off`

## Done when
- `scripts/check.sh` is green at B and C (paste the summary lines).
- The report has R5's four results and the two derived values, and the owner has read them.
- The five Review Focus tests pass, and `security-reviewer` has no blocking findings on the webhook, media links, logs and the new secrets.
- No test or code path sends `privacy_level` or omits `disable_inbox_fallback=true`.
- `posting verify` stays at 0 in every Dual test (the Dict stays current).

## Owner steps
- Before: card 014 deployed and one clean day. `scripts/worktree.sh s2b/publishing`, open a session in `../clipForge-s2b`, paste `Run card docs/cards/015-s2b-publishing.md`.
- At A (R5, plan Task 9): buy Upload-Post **Basic** (monthly). Create a **test** profile `s2-probe` and connect one test TikTok (or YouTube) account. Put `UPLOAD_POST_API_KEY` in `.env` only (not the Modal secret yet). Run `uv run python scratch/s2/r5_probe.py` with the session, again after 10 minutes and after 24 h; cancel the scheduled job. Read the results in the report, then tell the session to go on.
- At B: commit, `git push -u origin s2b/publishing`, `gh pr create --fill`; keep the PR open through C.
- At C: commit, push, squash-merge when CI is green. Then the deploy:
  1. In Upload-Post: create the profile `realtalk-clips-en` and connect TikTok (allow public posts), Instagram (Professional, linked to the Page), YouTube and Facebook. Note the Facebook Page id.
  2. Register the webhook URL `<API_URL>/webhooks/upload-post` for `upload_completed`, `social_account_disconnected`, `social_account_reauth_required` and `social_account_connected`.
  3. Add `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` with the procedure in `docs/ops/secrets.md`: edit `clipforge-secrets` in the Modal dashboard and add **only** the two new keys (never `modal secret create --force`), then add them to `.env`.
  4. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S2b: publishing"`, outside the blackout (runbook §1).
  5. `uv run clipforge policy dry-run`. When it reports "0 items would be held", set `GATE_ENFORCE=on` in `clipforge-secrets` (dashboard edit) and `.env`, then redeploy (dry run first). If items would be held, fix their sources (`clipforge source edit`) or reject them first.
  6. `uv run clipforge account edit realtalk-clips-en --publisher-profile realtalk-clips-en --facebook-page-id <id>`, then `uv run clipforge publisher check realtalk-clips-en`: no problems.
  7. The next morning at 09:00 your time: approve one card. After its slot: `uv run clipforge status`, `uv run clipforge posting verify` (0 differences), and the post on each platform.
  8. With one item scheduled: `/pause realtalk-clips-en` (the reply says 1 cancelled), then `/go realtalk-clips-en`. Run a day on Hands-on.
- **Rollback:**
  - One account: `uv run clipforge account edit realtalk-clips-en --clear-publisher`. It cancels the account's scheduled Upload-Post jobs, keeps items in flight out of the assisted pick until reconcile settles them, and rewrites the schedule copy, so the next slot is assisted.
  - The gate: `GATE_ENFORCE=off` (dashboard edit plus `.env`, then a redeploy) puts it back to log-only.
  - The whole step: a revert on `main`, then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "revert S2b"`. 0002 is unchanged, and the Dict stayed current through Dual writes.

## Hand-off
Write `docs/reports/015-s2b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at every checkpoint, with R5's results at the top. Don't commit: the owner does. The next card is 016 (S2c), after this deploy and a day on Hands-on.

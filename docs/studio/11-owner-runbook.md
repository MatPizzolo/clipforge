# 11: Owner runbook

Every step **you** do, in order, with the exact command. Sessions write code; you hold the keys, create the accounts, approve deploys, and do git. Each step says where its values go.

Last updated: 2026-09-29. Status: ✅ done · ⏳ now · ⬜ later.

Commands run from the project root (`~/code/clipForge`) unless they start with `cd web`.

## 0. Where secrets and settings go

| Place | What | How to change it |
|---|---|---|
| Modal secret **`clipforge-secrets`** | Every value the deployed app reads | Modal dashboard → Secrets → `clipforge-secrets` → **Edit**, add or change keys, save. **Never** `modal secret create --force`: it replaces the whole secret. New containers read the change, so redeploy afterwards |
| Root **`.env`** | The same values, for local CLI runs and tests | Edit the file. It's gitignored. Sessions never read or print it |
| **`web/.env.local`** | Dashboard values for local runs | Edit the file. It's gitignored and kept out of Vercel uploads by `web/.vercelignore` |
| **Vercel env** (project `clipforge-web`) | Dashboard values for preview and production | `cd web && vercel env add <NAME> <environment>`. It prompts for the value, so the value isn't echoed or saved in shell history |
| **GitHub Actions secrets** | CI deploy values, once the repo exists | GitHub → repo → Settings → Secrets and variables → Actions |

Rule: you type secret values yourself. Never paste them into a session.

## 1. S0: go live with the posting assistant ✅ (2026-09-29)

For the record, and for a re-deploy:
1. Add to `clipforge-secrets` and `.env` (your id must also be in `TELEGRAM_ALLOWED_USER_IDS`):
   ```
   POSTING_CHAT_ID=<your Telegram user id>
   POSTING_TIMEZONE=America/New_York
   POSTING_SLOTS=08:00,10:30,13:00,16:00,19:00,21:30
   POSTING_HASHTAGS=<tags, comma-separated, without #>
   ```
2. Deploy, register the webhook (needed for button taps), then build the queue:
   ```
   uv run modal deploy src/clipforge/app.py
   uv run clipforge set-webhook
   uv run clipforge status --rebuild
   ```
3. Put each channel's episodes in `videos/<channel>/`, then submit them:
   ```
   uv run clipforge clip
   ```

**Stopping and starting the app.** You stopped the `clipforge` app on the night of 2026-09-29. S1 redeployed it on 2026-09-30 with your OK: once to restart it, and once for the PyAV pin (log #70). **It's running now**, Dict-only (`STATE_READS=dict`, no database connected). While the app is stopped, the posting slots, button taps, `/status`, the daily keep-alive and the API the dashboard reads are all off.
- Check the state with `uv run modal app list`.
- Start it with `uv run modal deploy src/clipforge/app.py`, but only when the session that owns `src/` (S1) says the code is at a clean checkpoint. A deploy ships whatever is in `src/` right now.
- More than 7 days stopped means Dict entries can expire. Then run `uv run clipforge status --restore` after the deploy.

**Deploy blackout** (decision log #108), until S1's slot guard is verified in production: **don't deploy from each posting slot until 30 minutes after it.** With the default slots (New York time) that means no deploys during 08:00–08:30, 10:30–11:00, 13:00–13:30, 16:00–16:30, 19:00–19:30 and 21:30–22:00. If you changed `POSTING_SLOTS`, use your own times. Reason: a claim-key change can send the same slot twice (#77).

⏳ **Still open:** the phone test that the S0 session asked for: `/status`, `/next`, ✅ on and off, ⏭ Skip, 🗑 Reject with a reason, `/pause`, `/go`. Report the result to the S0 session. It then checks the next scheduled slot and the 07:00 UTC keep-alive run after the 2026-09-30 redeploy.

## 2. Every day (until S2 publishes automatically)

| To | Do |
|---|---|
| See the queue | `/status` in Telegram, `uv run clipforge status`, or the dashboard's Home |
| Get the next clip now | `/next` |
| Record a post | Tap ✅ TikTok / Instagram / YouTube under the clip (tap again to undo) |
| Skip a clip for 24 h | ⏭ Skip (the next clip arrives right away) |
| Drop a clip | 🗑 Reject, then pick a reason |
| Stop or restart the slots | `/pause`, `/go` |
| Add a new episode | Put the file in `videos/<channel>/` and run `uv run clipforge clip`. Add `--fetch` to also download the clips into `videos/out/` |
| Check one job | `uv run clipforge status <job_id>` |
| Continue a failed job | `uv run clipforge resume <job_id>` |
| Queue finished jobs again | `uv run clipforge status --rebuild` (safe to repeat) |
| Recover posting state after an outage | `uv run clipforge status --restore` (newest snapshot) or `--restore YYYY-MM-DD`, then check `/status`. Restore never brings back a pause |

**After S1 is deployed**, `channels.toml` is no longer read. Sources are managed with `clipforge source` (§4), and `videos/<source-id>/` is the only local mapping.

## 3. Sessions and hand-off (pause of 2026-09-30)

This section is the complete hand-off from the first coordinator session. A new coordinator starts here, from the git tag `pause-2026-09-30`, and needs nothing else.

### 3.1 Read first (new coordinator), in order

1. This section (§3), then the rest of this runbook (the owner's steps and commands).
2. `CLAUDE.md` (project rules 1–9), `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (accepted ADRs are binding; ADR-43–46 were accepted on 2026-09-30).
3. `docs/studio/10-decision-log.md` (every owner decision; the **Open** table at the end), `docs/studio/04-roadmap.md` (the source of truth for Phase 6), `docs/studio/08-dashboard-and-operations.md` §2 and §2b (surfaces and notifications), `docs/studio/09-account-registry.md`.
4. The plan and spec of any workstream you hand a card to (paths in 3.3).

**Rules that stay in force:**
- The coordinator asks, reviews and hands out paste-ready action cards, in order. It doesn't write code or build features. It fixes docs (the decision log only by appending; see 3.7).
- It never runs git write commands, `gh`, deploys, or Modal stop commands. The owner runs them; the coordinator writes the exact commands.
- Read-only git (`status`, `diff`, `log`, `ls-files`, `show`) only if the owner has allowed it. On 2026-09-30 the owner hadn't answered yet: ask.
- Every card is a full action card: context, numbered actions with file paths, owner steps, "done when" (tests and checks), a cost cap (06's format; memory: detailed-session-prompts).
- Sessions don't commit. The owner commits each branch at a checkpoint and merges.
- Deploys: only with the owner's OK, from `main` after a merge, never during the blackout (§1).

### 3.2 State per workstream (at `pause-2026-09-30`)

| Workstream | Status | Last finished | Continues at |
|---|---|---|---|
| **S0** posting assistant (plan C) | Live since 2026-09-29, redeployed 2026-09-30 (Dict-only). The session ended long ago | Plan C Tasks 1–6 and its final review | Owner checks only (3.4): phone test, one scheduled slot, the 07:00 UTC keep-alive line and first snapshot |
| **S1** database, accounts, sources | About 80%, stopped cleanly. Fast suite 736 passed | Tasks 1–20, fix card 1 (13b), checkpoint D fixes, addendum A1 (ADR-43 derived `producer_version`, one sanitizer) | `docs/superpowers/plans/2026-09-29-studio-s1.md`: the STATUS block at the top, then its addendum sections A2 → A6, Task 21b, the final whole-branch review. **Stop before Task 22** (rollout) |
| **S2** publishing | Not started | — | After S1's rollout (Task 22). 04 S2 lists the ADR-44/45 items added on 2026-09-30 |
| **S3a** dashboard shell | About 92%. 68 unit tests, 21 Playwright tests pass | Tasks 1–11, checkpoint G (laptop layout), the audit fix card, deep links (#99) | `docs/superpowers/plans/2026-09-29-studio-s3a.md` Task 12 (a real local GitHub login, needs the local OAuth app) and Task 13 (Vercel deploy), both waiting on the owner's Vercel steps (§5b) |
| **S3** dashboard v1 | Not started | — | 06's S3 card, after S1. It owns the `admin` endpoint (D9) and the pre-S2 Review page (D8) |
| **S3c** account workspaces | Design written, **awaiting the owner's review** (spec sections 1–6 approved in chat) | `docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md`; the ADR-42 draft in 05 | Card 2 below (revise for D3, D4, D10), then the owner's review, then a plan only after S1's final review |
| **S4+** (Timeline, media servers, producers) | Not started | — | 06's S4 card, after S1 is merged (S4 edits `models.py` and `stages/`) |
| **X1** voice | Done | Qwen3-TTS primary, Kokoro fallback (#69); report `docs/studio/spikes/x1-voice.md` | Continues in S5 (the TTS server and its guard, #72) |
| **X2** talking head | Stopped at ~25% (licenses checked, no clips, ~$0.40 of $30) | `docs/studio/spikes/x2-talking-head.md` | Card 5 below, after the owner rules on O7 |
| **X3–X6** | Not started | — | 06's cards |

### 3.3 Addendum tracker

S1's plan names its own addendum steps A1–A6 by task. The coordinator's items map onto them:

| Item | S1 plan step | Status |
|---|---|---|
| Derived `producer_version` (ADR-43), `build` = git SHA | A1 | done (#111; `clips:14fcf790` at the pause) |
| One sanitizer (`sanitize.clean` / `redact`) | A1 | done (R29: split into two audiences) |
| Task 21 split: 21a (blueprints mounted, read-only `db_doctor`, `.env.example`) / 21b (DB wired, deployed only at 4c.2) | A2 = 21a; 21b | open (21a's brief is written) |
| Platforms = account ∩ permission, account from the source | Task 14 | built; the "frozen per item" test is still to add (A3) |
| Slot guard from sends (#77) | A3 | open |
| Slot computed before any DB call, schedule copy in the Dict | A3 | open |
| Hashtags from the account in postgres mode | Task 15 / A3 | partly done; test the postgres-mode path in A3 |
| `add_send` failure rollback | Task 15 | done (#95) |
| `posting/actions.py`, actor on every write, DB-down answers, `statement_timeout` | A4 | open (the per-account chat check is done, Task 16) |
| Bot URL buttons from `DASHBOARD_URL` (ADR-44 deep links) | A4 (added by the coordinator at the pause) | open |
| Job view and overview from the `jobs` table, additive fields | A5 | open |
| `ops_alert` + `posting_daily` (ADR-45, ADR-46) | A6 | open (`verify_daily` exists to build on) |
| Task 23 deletion conditions | plan addendum | done (written; enforced at Task 23) |
| Ledger rulings copied into the log | — | done |
| S3c D1 one setup id | S3c | **closed**: `(account_id, account_version)` with pinned parents (#88) |
| S3c D2 `PATCH /accounts` saves a version with an actor | S3c spec §5.1 | done in design |
| S3c D3 `post_events.actor` column in 0002 | S3c | open (card 2) |
| S3c D4 one dry-run preview for save and experiment start | S3c | open (card 2) |
| S3c D5 edits apply to new items only | S3c spec §3.2 | done in design |
| S3c D6 home tasks / Telegram role per page | 08 §2 | done at the pause (08 §2 column and §2b) |
| S3c D7 keep/revert only on the experiment page | S3c spec §2.6 | mostly done; state it explicitly (card 2) |
| S3c D8 pre-S2 Review page as a queue manager | S3 | open (in 08 §2; the S3 card must build it) |
| S3c D9 `admin` = second ASGI app with its own `ADMIN_API_TOKEN` | S3 | open (S3's decision; card 2 adds it to 06's S3 card) |
| S3c D10 deep-link formats, `DASHBOARD_URL` | 08 §2b; S1 A4; S3c | formats written in 08 §2b; the bot side is S1 A4 |
| S3a fix card 2, deep-link card | S3a | done (#82, #83, #99) |

### 3.4 Open owner decisions and steps (recommendations in bold)

1. **Now, before the pause commit:** regenerate the stale `web/openapi.json` (§8 step 5 has the commands).
2. The pause commit, the tag and the push (§8 step 5). Then take `DATABASE_URL` out of `clipforge-secrets` (§8 step 5; **the dashboard way**).
3. Read-only git for the coordinator: **allow it**, so audits compare the tree against commits.
4. The S0 checks: the phone test (`/status`, `/next`, ✅ on and off, ⏭, 🗑 + reason, `/pause`, `/go`), one scheduled slot end to end, and the 07:00 UTC keep-alive log line with its first snapshot (`uv run modal app logs clipforge`).
5. O3, the handles for founder.tapes and hombre.en.construccion, and O5, Billy Garton Jr.'s permission facts. **Collect both before S1's rollout (Task 22).**
6. O7, WenetSpeech-pretrained models: **treat as "needs review"; prefer LongCat 1.5 unless a wav2vec model is clearly better in the X2 blind test.**
7. Review the S3c spec and accept ADR-42 (after card 2): **accept once D3, D4 and D10 are in.**
8. X2's ~227 GB on the Volume: **keep it if X2 resumes within a couple of weeks**, else `uv run modal volume rm -r clipforge-models x2`.
9. The Vercel steps (§5b), when you want the dashboard online: they unlock S3a Task 12/13.
10. O4 (Upload-Post plan) and O6 (clip series formats): before S2.
11. Later, not now: the Actions secrets and `DEPLOY_ENABLED` (§8 "still left").

### 3.5 Next cards, in order

Each card is pasted as the first message of a new session opened in its own worktree (3.6). Where a card says "prompt B", paste 06's prompt B with it.

**Card 1: S1, finish (worktree `s1-finish`, branch `s1/finish`)**
```
STUDIO BUILD: S1 finish (after the 2026-09-30 pause). Worktree ../clipForge-s1, branch s1/finish.
CONTEXT: S1 stopped cleanly at the pause (tag pause-2026-09-30): Tasks 1–20, fix card 1,
checkpoint D fixes and addendum A1 are done; 736 fast tests pass. Production is live and
Dict-only (STATE_READS=dict); DATABASE_URL is NOT in the Modal secret until rollout 4c.2.
Accepted since your plan: ADR-43–46 (docs/DECISIONS.md). Read first: CLAUDE.md, your plan's
STATUS block and addendum (docs/superpowers/plans/2026-09-29-studio-s1.md), your spec, the
runbook §1 (deploy blackout), §3.3 (addendum tracker) and §4, docs/studio/08 §2b.
ACTIONS (one checkpoint each; stop for the owner at each):
1. A2 = Task 21a: mount blueprints/ into the images; a read-only `db_doctor` Modal function
   (connect ms, alembic_version == the code's expected revision, pooled host yes/no, no
   writes); .env.example DB variables; alembic/env.py requires DATABASE_URL_UNPOOLED for DDL.
2. A3: slot guard from sends (return "taken" if any record has a send for this slot, before
   claim_slot); compute the slot before any DB call and read schedules from a Dict copy
   posting:schedule:<account> written only by the accounts service; test hashtags from the
   account in postgres mode; test that item platforms are frozen per item.
3. A4: src/clipforge/posting/actions.py (set_posted, skip, reject, set_reason,
   pause(account), send_next(account), redraw_all(ref)); the webhook calls it; an actor on
   every write (telegram:<user id>, web:<login> from X-Clipforge-Actor); on a DB error answer
   "store unavailable, nothing changed"; SET LOCAL statement_timeout = '5s' in
   Database.begin. Add DASHBOARD_URL (optional setting) and URL buttons on bot messages with
   the link formats in 08 §2b; no button when it's unset.
4. A5: the job view and the overview read the jobs table first; additive overview fields
   (state, posted_total, per account unanswered, last_sent_at). Keep the contract additive
   (#49) and tell the owner to regenerate web/openapi.json.
5. A6: ops_alert(text, kind) to the owner chat, deduped by a Dict claim, obeying ADR-45
   (quiet hours 23:00–08:00, caps); posting_keepalive becomes posting_daily (ADR-46).
6. Task 21b: db=database_from_settings in app.py build_deps; ADR-41 into
   docs/DECISIONS.md; ci.yml: alembic upgrade head (DATABASE_URL_UNPOOLED secret) before
   modal deploy, skip the deploy job when only web/** or docs changed, keep the
   DEPLOY_ENABLED gate; ARCHITECTURE (Postgres, STATE_READS, per-account keys) and
   CLAUDE.md commands.
7. The final whole-branch review; fix Critical/Important; list the deferred minors
   (the per-account overview isolation, posting_tick building deps when posting is off,
   resume recording before the spawn, backfill dry-run preview, rebuild video-path test).
8. STOP before Task 22 (rollout). Remove nothing listed under Task 23.
RULES: decision-log rows only in the range #200–#249 (re-read, append at the end, never
rewrite). No deploy, no Modal runs (the db_doctor runs only at rollout, with the owner).
Don't edit web/ or the S3c docs. I handle git.
DONE WHEN: after each action, `uv run pytest -q -m "not gpu and not slow"`, `uv run ruff
check .`, `uv run ruff format --check .`, `uv run mypy src` are green (paste the lines).
COST CAP: $0.
```

**Card 2: S3c design revision (worktree `s3c-design`, branch `s3c/design`; can run alongside card 1)**
```
STUDIO DESIGN: S3c revision (after the 2026-09-30 pause). Worktree ../clipForge-s3c, branch
s3c/design. Design only: no code, no Modal or Vercel spend, no deploys. I handle git.
CONTEXT: the spec docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md (sections
1–6 approved in chat) and the ADR-42 draft in docs/studio/05 await my review. Since then:
ADR-43 (derived producer_version), ADR-44 (one home per task), ADR-45 (notification budget)
and ADR-46 (daily reconcile) were accepted, and docs/studio/08 §2 gained a "Telegram's role"
column and §2b (surfaces, sync, notifications, deep links, identity).
ACTIONS:
1. D1: record in the spec that the setup is identified by (account_id, account_version)
   with pinned parents (#88); no separate setup id.
2. D3: add post_events.actor (text: telegram:<id> | web:<login> | session:<name>) to 0002,
   written by posting/actions.py (S1 A4).
3. D4: one dry-run used by both "save version" and "start experiment" (a standalone
   POST /setup/preview, or show that GET …/diff + the estimate already is that single
   path): it returns the diff, which stages re-run, affected items and the estimated cost.
4. D7: state that keep/revert is decided only on the experiment page.
5. D10: use the deep-link formats in 08 §2b; add any page the spec needs.
6. D8 and D9 belong to S3: add them to 06's S3 card (the pre-S2 Review page is a queue
   manager: skip, reject, reorder, posted correction via posting/actions.py; admin = a
   second @modal.asgi_app(requires_proxy_auth=True) reusing create_app with an admin
   router and its own ADMIN_API_TOKEN).
7. Update the spec's status line and the ADR-42 draft; reference ADR-43–46, don't redefine.
8. STOP for my review. No plan until S1's final review is done.
RULES: you own only the S3c spec, ADR-42 in 05, the S3/S3c parts of 04 and 06, and the S3c
rows of 08 §2. Decision-log rows only in the range #250–#299 (re-read, append at the end).
DONE WHEN: the spec's status line lists each section and D-item; no placeholders.
COST CAP: $0.
```

**Card 3: S3a Task 12–13 (worktree `s3a-deploy`, branch `s3a/deploy`; only after the owner's Vercel steps, §5b)**
```
STUDIO BUILD: S3a Tasks 12–13 (after the pause). Worktree ../clipForge-web, branch s3a/deploy.
CONTEXT: S3a stopped at the pause with all web checks green; its plan
docs/superpowers/plans/2026-09-29-studio-s3a.md Tasks 12–13 remain. The owner has now done
the Vercel steps (Pro, the production and local GitHub OAuth apps, vercel env add).
ACTIONS: 1. Task 12: a real local GitHub login (the local OAuth app), then a phone check
against the local server on the LAN only if the owner allows it (default: laptop only).
2. Task 13: vercel deploy (a preview proves the build and /login only, #83), then
production only after my OK; I log in on the phone and the laptop. 3. Tick S3a in 04 and
ROADMAP.md, add one web/ line to CLAUDE.md, and fix the S3a plan's file map.
RULES: own only web/, scripts/export_openapi.py, .github/workflows/web.yml, the S3a docs;
decision-log rows #300–#319. Merge after S1 (CLAUDE.md). I handle git.
DONE WHEN: npm run check, gen:check, e2e and the export --check are green; production
login works. COST CAP: $0 Modal (Vercel Pro $20/mo).
```

**Card 4: X2 resume (worktree `x2`, branch `x2/talking-head`; only after the owner rules on O7)**
```
STUDIO SPIKE: X2 talking head, resume. Worktree ../clipForge-x2, branch x2/talking-head.
Paste 06's prompt C and the X2 card first. CONTEXT: X2 stopped at ~25% on 2026-09-30:
licenses checked, no clips. Read docs/studio/spikes/x2-talking-head.md (findings, method,
the weights already on the clipforge-models Volume under x2/) and the owner's O7 ruling in
docs/studio/10. ACTIONS: rebuild the probe in scratch/x2/ from that file (deployed spike apps
clipforge-x2*, never the clipforge app); an H100 smoke test per model; then the card's
test set and blind samples; report; after my verdict update 03, 04 X2 and the spikes file.
Stop every spike app at the end. RULES: decision-log rows #320–#339. I handle git.
DONE WHEN: the report table with measured GPU-seconds, cold start, $ per output second and
my blind rating. COST CAP: $29.60 (the $30 card minus what was spent).
```

**Card 5: S4 Timeline renderer (after card 1 is merged into `main`)**
Paste 06's prompt B with the S4 card. Its worktree is `../clipForge-s4`, branch `s4/timeline`, cut from `main` after the S1 merge. Decision-log rows #340–#379.

### 3.6 Parallel plan (git worktrees)

| Card | Branch | Can run with | Must wait for | Merge order |
|---|---|---|---|---|
| 1 S1 finish | `s1/finish` | 2, 4 | — | **first** |
| 2 S3c revision | `s3c/design` | 1, 3, 4 (docs only) | — | after 1 |
| 3 S3a deploy | `s3a/deploy` | 1, 2, 4 | the owner's Vercel steps | after 1 (both touch `CLAUDE.md`) |
| 4 X2 resume | `x2/talking-head` | 1, 2, 3 | O7 | any time |
| 5 S4 | `s4/timeline` | 2, 3, 4 | card 1 merged (`models.py`, `stages/`) | after 1 |

Owner commands, from the main folder, after the pause tag exists:
```
cd ~/code/clipForge
git worktree add ../clipForge-s1  -b s1/finish        pause-2026-09-30
git worktree add ../clipForge-s3c -b s3c/design       pause-2026-09-30
git worktree add ../clipForge-web -b s3a/deploy       pause-2026-09-30   # when card 3 starts
git worktree add ../clipForge-x2  -b x2/talking-head  pause-2026-09-30   # when card 4 starts
# each worktree needs the untracked local files and its own environment:
for d in ../clipForge-s1 ../clipForge-s3c; do cp .env "$d/"; (cd "$d" && uv sync); done
cp web/.env.local ../clipForge-web/web/ 2>/dev/null; (cd ../clipForge-web/web && npm ci)
```
At a session's checkpoint, in its worktree:
```
git add -A && git status --short && git commit -m "<the session's suggested message>"
```
Merging back (the owner, in the main folder):
```
git checkout main
git merge --no-ff s1/finish          # first
git merge --no-ff s3c/design         # then the others
git push origin main
git worktree remove ../clipForge-s1  # when the branch is done
```
- **Decision-log conflicts:** every branch appends only in its own number range (3.5), so a conflict in `docs/studio/10` is two blocks added at the end. Keep both blocks, in number order. The numbering can have gaps.
- **`CLAUDE.md`:** S1 first, then S3a's one line.
- **Deploys:** only from `main` after a merge, with the owner's OK, outside the blackout.

### 3.7 Rules for shared docs

- `docs/studio/10`: append only; re-read before editing; superseded rows get `superseded by N`. Worktree sessions use their number range (3.5). The coordinator in the main folder uses the next free number below #200.
- `docs/studio/04`: the Phase 6 source of truth. `ROADMAP.md` mirrors it and is ticked in the same change.
- ADRs: accepted ones only in `docs/DECISIONS.md`. 05 holds drafts, the reserved numbers (41 S1, 42 S3c) and the next free number (47).
- Owner steps and commands: this runbook. Specs and plans are frozen after their build and marked historical.

## 4. S1: database, accounts, sources

### 4a. Before the build ✅ (done 2026-09-30, except item 4)
1. **Docker:** Docker Desktop → Settings → Resources → WSL integration → on for your distro. Check:
   ```
   docker info
   ```
   The fast tests need Docker from S1 on (they start a Postgres container). ✅ Working: the fast suite runs its database tests.
2. **Neon:** ✅ S1 did this for you with `neon link` (project `fragrant-violet-23654229`), which wrote `DATABASE_URL`, `DATABASE_URL_UNPOOLED` and `NEON_BRANCH` into `.env`. For a new project by hand:
   - create a project at neon.com in the AWS **us-east** region, near Modal;
   - copy two connection strings from the dashboard's Connect dialog: the **pooled** one (host contains `-pooler`) and the **direct** one (pooling off).
3. Add to `.env` (✅ done). **Not** to `clipforge-secrets` yet: `DATABASE_URL` comes out of the Modal secret until rollout step 4c.2 (#107; the commands are in §8, step 5). Earlier note, kept for history: (✅ `DATABASE_URL` is in the Modal secret; `STATE_READS=dict` is the default, so add it to the secret at rollout step 4c.1 so it's visible):
   ```
   DATABASE_URL=<pooled connection string>
   DATABASE_URL_UNPOOLED=<direct connection string>
   STATE_READS=dict
   ```
   `DATABASE_URL_UNPOOLED` is what migrations use. `STATE_READS=dict` keeps the Dict as the source of truth until step 4c.7. Two more settings exist with defaults you don't need to set: `POSTING_ACCOUNT_ID` (default `realtalk-clips-en`, the account Dict mode serves) and `BLUEPRINTS_DIR`.
4. **Decisions to have ready** (10 → Open): the final handles for founder.tapes and hombre.en.construccion (O3), and Billy Garton Jr.'s permission facts (O5): when it was granted, by whom, a link to where the agreement is stored, whether monetization and translations are allowed, and any expiry.

### 4b. During the build
Approve each checkpoint the S1 session reports. With no git repo, a checkpoint just means the files are saved.

### 4c. Rollout ⬜ (after the build; each deploy only with your OK; the session runs these with you)
1. Migrate the database:
   ```
   uv run alembic upgrade head
   ```
2. Deploy. The Dict stays the primary, and Postgres gets a copy of every write:
   ```
   uv run modal deploy src/clipforge/app.py
   ```
3. Create the three accounts:
   ```
   uv run clipforge account create --blueprint realtalk-clips --lang en --handle realtalk.clipsdaily --posting-from-env
   uv run clipforge account create --blueprint founder-tapes --lang en --handle <final handle>
   uv run clipforge account create --blueprint hombre-en-construccion --lang es --handle <final handle>
   ```
4. Import the channel into sources, then fill in its permission record:
   ```
   uv run clipforge source import-toml --account realtalk-clips-en --dry-run
   uv run clipforge source import-toml --account realtalk-clips-en
   uv run clipforge source show billy-garton
   uv run clipforge source edit billy-garton --granted-at <YYYY-MM-DD> --granted-by "<name>" --evidence-url <link> --monetization yes --translation <yes|no>
   ```
   Then delete `videos/channels.toml`.
5. Copy the queue and the job records into Postgres:
   ```
   uv run clipforge posting import --dry-run
   uv run clipforge posting import
   uv run clipforge jobs backfill
   ```
6. Check that the two stores agree. It must report 0 differences:
   ```
   uv run clipforge posting verify
   ```
7. Switch reads to Postgres: set `STATE_READS=postgres` in `clipforge-secrets` and `.env`, then:
   ```
   uv run modal deploy src/clipforge/app.py
   ```
   Watch one day of slots and taps. The verify also runs daily inside the 07:00 UTC keep-alive.
8. After **7 days** with a clean verify every day: a later session removes the Dict copy and the keep-alive (ADR-24 retires).

**Rollback** at any point: set `STATE_READS=dict` and redeploy. The Dict has stayed current for realtalk, and the other accounts pause until you switch back. Run `clipforge posting verify` before switching to Postgres again.

The exact flags are fixed by the S1 build. If one differs, the session's final report and `CLAUDE.md` have the real command.

## 5. S3a: the dashboard shell

### 5a. Local run ✅
Create `web/.env.local`, typing the values yourself:
```
AUTH_DISABLED=1
CLIPFORGE_API_URL=https://matpizzolo--clipforge-web.modal.run
API_TOKEN=<API_TOKEN from the root .env>
```
Then:
```
cd web && npm run dev          # http://localhost:3000 (bound to 127.0.0.1 only, log #99)
```
`AUTH_DISABLED=1` works only on your machine; every Vercel environment refuses it. For a real login locally, remove that line and add the local OAuth app's values (5b).

Checks, the same ones the session runs:
```
cd web && npm run check        # lint, typecheck, unit tests, build
cd web && npm run e2e          # Playwright smoke tests
cd web && npm run gen:check    # generated schemas match openapi.json
uv run python scripts/export_openapi.py --check
```

### 5b. Accounts and keys ⬜ (owner: at the end, after the other sessions; S3a is parked at checkpoint G until then)
1. **Vercel Pro:** confirm the plan in the Vercel dashboard. Hobby is non-commercial only.
2. **GitHub OAuth apps** (GitHub → Settings → Developer settings → OAuth Apps → New):
   - production: callback `https://clipforge-web.vercel.app/api/auth/callback/github`, or your custom domain;
   - local (optional): callback `http://localhost:3000/api/auth/callback/github`. Its id and secret go in `web/.env.local` as `AUTH_GITHUB_ID` and `AUTH_GITHUB_SECRET`, with `OWNER_EMAIL` and `AUTH_SECRET`.
3. **Vercel env.** Run in `web/`; each command prompts for its value. Get secrets from `npx auth secret`, and use a different value for preview and production:
   ```
   cd web
   vercel env add AUTH_SECRET preview ""
   vercel env add AUTH_SECRET production
   vercel env add CLIPFORGE_API_URL production
   vercel env add API_TOKEN production
   vercel env add AUTH_GITHUB_ID production
   vercel env add AUTH_GITHUB_SECRET production
   vercel env add OWNER_EMAIL production
   vercel env ls                  # names only; check nothing is missing
   ```
   `MOCK_API=1` is already set for previews. Never add `MOCK_API` or `AUTH_DISABLED` to production. A preview proves only the build and the redirect to `/login` (log #83): GitHub login works on localhost and on the production domain only. Deep links keep their target through login (log #99).
4. Tell the S3a session it's done. It deploys a preview (mock data), and production only after your OK:
   ```
   cd web && vercel deploy            # preview
   cd web && vercel deploy --prod     # production
   ```
5. Log in on your phone and your laptop, and check Home against `/status`.

## 6. S2: publishing ⬜ (prepare now, because warm-up takes days)

1. Create the TikTok, Instagram (a Professional account linked to a Facebook Page), YouTube and Facebook accounts for founder.tapes and hombre.en.construccion, with the handles from O3. Use them normally for 3–5 days; no fake engagement. Record the handles in `docs/studio/09-account-registry.md`.
2. Get source permissions for them: a creator agreement, or a Whop account for campaigns.
3. **Upload-Post:**
   - buy a paid plan (Free has no TikTok): Basic, $24 for 5 profiles;
   - connect every account on all four platforms, and set the TikTok accounts to public;
   - the S2 session gives the exact secret names. The expected ones are `UPLOAD_POST_API_KEY`, and a webhook secret created when you first save the webhook URL. Both go in `clipforge-secrets` and `.env`.

## 7. Spikes

- **X1 voice** ✅ (2026-09-30): Qwen3-TTS primary, Kokoro fallback (log #69, report `docs/studio/spikes/x1-voice.md`). Left for you:
  ```
  rm -rf scratch          # only x1 is in it; every result is in docs/studio/03, 04, spikes/ and the log
  ```
  Keep the `clipforge-models` Modal Volume: it holds the Qwen and Kokoro weights and the v2 reference voice (`refs/x1/`) that S5 needs.
- **X2 talking head** ⏸ (stopped at ~25% on 2026-09-30): licenses checked, no clips yet. Before it resumes, rule on O7 (WenetSpeech, log). Its ~227 GB of weights stay on `clipforge-models` under `x2/`; if X2 won't resume soon, remove them with `uv run modal volume rm -r clipforge-models x2`. Report and resume recipe: `docs/studio/spikes/x2-talking-head.md`.
- For later spikes: if a model is gated, create a free Hugging Face token (read-only) and add `HF_TOKEN` to `.env` (and to the spike's Modal secret, if the session asks).
- **X5 Judge** ⬜: join the TypeSafe Jev waitlist now. The key (`TYPESAFE_API_KEY`) goes in `.env` when it arrives.

## 8. The git repo and GitHub ⏳ (baseline on 2026-09-30)

Order: the baseline now → pause every session → the pause commit and tag → a new coordinator session. The coordinator never runs git, `gh`, deploys or Modal stop commands: you do.

**1. Gate the CI deploy job before the first push** (decision log #109). `ci.yml` deploys on every push to `main`, and the Actions secrets don't exist yet, so the first push would go red. S1 owns `ci.yml` (§3); this one-line edit is agreed with it:
```
cd ~/code/clipForge
python3 - <<'PY2'
import pathlib
p = pathlib.Path(".github/workflows/ci.yml"); t = p.read_text()
old = "    if: github.ref == 'refs/heads/main' && github.event_name == 'push'\n"
new = ("    # Off until ci.yml runs the migrations first (decision log #109).\n"
       "    if: github.ref == 'refs/heads/main' && github.event_name == 'push' && vars.DEPLOY_ENABLED == 'true'\n")
assert t.count(old) == 1, "ci.yml changed: gate it by hand"
p.write_text(t.replace(old, new)); print("deploy job gated")
PY2
grep -n "DEPLOY_ENABLED" .github/workflows/ci.yml
```

**2. Create the repo and the baseline commit:**
```
cd ~/code/clipForge
rm -rf scratch                                   # optional: X1's throwaway files (ignored anyway)
gh --version && gh auth status                   # if needed: gh auth login (GitHub.com, HTTPS, browser)
git init -b main
git config user.name "<your name>"
git config user.email "matpizzolo@gmail.com"
git add -A --dry-run | wc -l                     # expect about 350 files
git add -A --dry-run | grep -E '\.env|\.neon|jobs/|scratch/|node_modules|\.next/|\.vercel|videos/'
                                                 # expect only .env.example, web/.env.example and videos/README.md
git add -A
git ls-files | grep -E '\.env'                   # only the two .env.example files
git status --short | head -40
git commit -m "Baseline 2026-09-30: ClipForge through plan C (live), S1 in progress, S3a dashboard shell, S3c design, studio docs" \
           -m "Taken while the S1, S3a, S3c design and S0 sessions were still in progress. A pause commit follows."
```

**3. A private GitHub remote and the push:**
```
gh repo create clipforge --private --source=. --remote=origin --push
```
Or in the web UI: github.com/new → name `clipforge`, **Private**, no README, .gitignore or license → then:
```
git remote add origin https://github.com/<your user>/clipforge.git
git push -u origin main
```

**4. Check the push:**
```
git ls-files | wc -l          # compare with the file count on the GitHub page
gh run list --limit 5         # CI: "check" green, "deploy" skipped; "web" runs too
```
Send the coordinator the output of `git status`, `git log --oneline -1`, `git ls-files | wc -l` and `gh run list --limit 5`.

**5. At the pause** (after every session has reported and the coordinator's check is clean). First regenerate the dashboard's API contract, which S1's new routes made stale:
```
cd ~/code/clipForge
uv run python scripts/export_openapi.py
cd web && npm run gen && npm run gen:check && npm test && cd ..
uv run python scripts/export_openapi.py --check          # must say "up to date"
```
Then:
```
git add -A
git status --short                             # compare with the sessions' reports
git commit -m "Pause 2026-09-30: every session at a clean checkpoint" -m "<the coordinator gives the body>"
git tag -a pause-2026-09-30 -m "Pause before the new coordinator session"
git push origin main --follow-tags
```
Then take `DATABASE_URL` out of the Modal secret (#107). **Recommended: the Modal dashboard** → Secrets → `clipforge-secrets` → Edit → delete the `DATABASE_URL` key only → Save. Modal can't show secret values, so recreating it from the CLI works only if `.env` holds every key the secret has:
```
grep -v -E '^(DATABASE_URL|DATABASE_URL_UNPOOLED|NEON_BRANCH)=' .env > /tmp/clipforge-secrets.env
cut -d= -f1 /tmp/clipforge-secrets.env         # check the key names (no values shown)
uv run modal secret create clipforge-secrets --from-dotenv /tmp/clipforge-secrets.env --force
shred -u /tmp/clipforge-secrets.env
```
No redeploy is needed: the deployed app doesn't use the database yet.

**Still left, and when:**
- The Actions secrets `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` and `DATABASE_URL_UNPOOLED`, and the repository variable `DEPLOY_ENABLED=true`: only after `ci.yml` runs `alembic upgrade head` before `modal deploy` and skips web-only pushes (S1 Task 21b). Until then you deploy by hand, outside the blackout (§1).
- In Vercel, connect the repo with Root Directory `web` when you do the Vercel steps (§5b).
- From the pause on, every parallel session gets its own git worktree (§3).

## 9. Starting a new session

| For | Paste | Plus |
|---|---|---|
| A build item (S*) | Prompt **B** from 06 | That item's action card from 06 §D, plus the "SHARED FOLDER" block from §3 while there's no repo |
| A spike (X*) | Prompt **C** | Its card |
| Launching an account | Prompt **E** | The blueprint, language and handle |
| A quick status | Prompt **I** | — |

Every session ends with the close-out checklist in 06. That includes rows in 10 for every decision it made, and 09 for any account change.

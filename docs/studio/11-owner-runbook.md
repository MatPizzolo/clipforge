# 11: Owner runbook

Every step **you** do, in order, with the exact command. Sessions write code; you hold the keys, create the accounts, approve deploys, and do git. Each step says where its values go.

Last updated: 2026-10-05 (ADR-54: Telegram is notifications only). Status: ✅ done · ⏳ now · ⬜ later.

Commands run from the project root (`~/code/clipforge/main`; worktrees sit beside it as `~/code/clipforge/clipForge-<stream>`, layout A, 2026-10-02) unless they start with `cd web`.

## 0. Where secrets and settings go

| Place | What | How to change it |
|---|---|---|
| Modal secret **`clipforge-secrets`** | Every value the deployed app reads | Modal dashboard → Secrets → `clipforge-secrets` → **Edit**, add or change keys, save. **Never** `modal secret create --force`: it replaces the whole secret. New containers read the change, so redeploy afterwards |
| Root **`.env`** | The same values, for local CLI runs and tests | Edit the file. It's gitignored. Sessions never read or print it |
| **`web/.env.local`** | Dashboard values for local runs | Edit the file. It's gitignored and kept out of Vercel uploads by `web/.vercelignore` |
| **Vercel env** (project `clipforge-web`) | Dashboard values for preview and production | `cd web && vercel env add <NAME> <environment>`. It prompts for the value, so the value isn't echoed or saved in shell history |
| **GitHub Actions secrets** | CI deploy values (repo `MatPizzolo/clipforge`, §8) | GitHub → repo → Settings → Secrets and variables → Actions |

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
2. Deploy (from `main`, through `scripts/deploy.sh`), register the webhook (needed for button taps), then build the queue:
   ```
   scripts/deploy.sh --dry-run && scripts/deploy.sh --reason "<why>"
   uv run clipforge set-webhook
   uv run clipforge status --rebuild
   ```
3. Put each channel's episodes in `videos/<channel>/`, then submit them:
   ```
   uv run clipforge clip
   ```

**Stopping and starting the app.** You stopped the `clipforge` app on the night of 2026-09-29. S1 redeployed it on 2026-09-30 with your OK: once to restart it, and once for the PyAV pin (log #70). **It's running now**, Dict-only (`STATE_READS=dict`, no database connected). While the app is stopped, the posting slots, button taps, `/status`, the daily reconcile (`posting_daily`) and the API the dashboard reads are all off.
- Check the state with `uv run modal app list`.
- Start it with `scripts/deploy.sh --reason "restart"` on `main` (run `--dry-run` first), but only when the session that owns `src/` (S1) says the code is at a clean checkpoint. A deploy ships whatever is in `src/` right now.
- More than 7 days stopped means Dict entries can expire. Then run `uv run clipforge status --restore` after the deploy.
- After more than 2 days stopped, the next `posting_daily` run sets the outage flag and posting stops until you clear it (§2, "Posting after an outage").

**`.env` must match the secret for three keys.** `scripts/deploy.sh` reads `POSTING_SLOTS`, `POSTING_TIMEZONE` and `STATE_READS` from `.env` only, and refuses if any is missing (never config.py's defaults). Keep them identical to `clipforge-secrets` (Modal dashboard → Secrets → `clipforge-secrets` shows the key names; you type the values). Today that's:
```
POSTING_TIMEZONE=America/New_York
POSTING_SLOTS=08:00,10:30,13:00,16:00,19:00,21:30
STATE_READS=dict
```
Add `STATE_READS=dict` to `clipforge-secrets` too (dashboard edit), so both places say the same. When you change one of these in the secret, change `.env` in the same sitting.

**Deploy blackout** (decision log #108), until S1's slot guard is verified in production: **don't deploy from each posting slot until 30 minutes after it.** `scripts/deploy.sh` enforces it from `POSTING_SLOTS` and `POSTING_TIMEZONE` in `.env`, and has no override. With the default slots (New York time) that means no deploys during 08:00–08:30, 10:30–11:00, 13:00–13:30, 16:00–16:30, 19:00–19:30 and 21:30–22:00. If you changed `POSTING_SLOTS`, use your own times. Reason: a claim-key change can send the same slot twice (#77).

**Dropped 2026-10-05 (ADR-54):** assisted posting is paused and Telegram is notifications only, so only `/status`, `/pause` and `/go` of this test still apply. Earlier text: the phone test that the S0 session asked for: `/status`, `/next`, ✅ on and off, ⏭ Skip, 🗑 Reject with a reason, `/pause`, `/go`. Report the result to the S0 session. It then checks the next scheduled slot and the 07:00 UTC daily run after the 2026-09-30 redeploy. The 2026-10-02 deploy renamed the cron: the 07:00 UTC run now logs `posting_daily:` (ADR-46, same slot) and also runs the rebuild every day (log #211).

## 2. Every day (until S2 publishes automatically)

**Telegram is notifications only (ADR-54, 2026-10-05).** There is no assisted posting any more: no clip at the slot, no ✅ per platform, no review buttons. Posting is paused (`/pause`, sent 2026-10-05) and realtalk posts nothing until S2b (card 015) publishes through Upload-Post; the queued clips wait intact. Telegram brings you:
- **alerts:** ops alerts, failures and every "needs me" row, each with an Open link to its dashboard page (`/act/<kind>/<id>`, from card 023);
- **the 09:00 digest** (from S2c), including "N items need review → Open";
- **status replies** (`/status`) and **the brake** (`/pause`, `/go`, `/pause all`; §2a).

**From S2b, for accounts on Upload-Post** (a connected profile and Publish on): review on the dashboard's Review page (card 024). When an item is due within 2 h and still undecided, Telegram sends one notification, "N items need review → Open". An approved item goes to Upload-Post 30 minutes before its slot. If a post fails, you get an alert (reconnect, or open the failure row), never a card to post by hand.

| To | Do |
|---|---|
| See the queue | `/status` in Telegram, `uv run clipforge status`, or the dashboard's Home |
| Review, skip or drop a clip | The dashboard's Review page (card 024); until it ships, nothing posts, so nothing needs a decision (ADR-54). `/next` and the ✅/⏭/🗑 buttons are dormant |
| Stop or restart the slots | `/pause`, `/go` (keep posting paused until S2b, ADR-54); from S2a also `/pause <account>`, `/pause all`, `/go <account>`, `/go all` (§2a) |
| Add a new episode | Put the file in `videos/<channel>/` and run `uv run clipforge clip`. Add `--fetch` to also download the clips into `videos/out/` |
| Check one job | `uv run clipforge status <job_id>` |
| Continue a failed job | `uv run clipforge resume <job_id>` |
| Queue finished jobs again | `uv run clipforge status --rebuild` (safe to repeat) |
| Recover posting state after an outage | `uv run clipforge status --restore` (newest snapshot) or `--restore YYYY-MM-DD`, then check `/status`. Restore never brings back a pause. It also clears the outage flag (below) |
| See or change an account's autopilot (from S2a) | `uv run clipforge autopilot show <account>`; `uv run clipforge autopilot set <account> <field> <value> --reason "<why>"` or `uv run clipforge autopilot preset <account> hands_on --reason "<why>"` |
| Promote an account the digest says is ready (from S2c) | `uv run clipforge autopilot promote <account>` (until S3's one tap) |
| Record a strike or takedown (from S2c) | `uv run clipforge autopilot strike <account> …`: Upload-Post sends no strike event, so you enter it; the account is demoted automatically |
| Check the gate before turning it on (from S2a) | `uv run clipforge policy dry-run` ("0 items would be held" before `GATE_ENFORCE=on`) |
| Connect or disconnect an account's Upload-Post profile (from S2b) | `uv run clipforge account edit <account> --publisher-profile <profile> --facebook-page-id <id>`, then `uv run clipforge publisher check <account>` (read-only). Disconnect: `uv run clipforge account edit <account> --clear-publisher` (the account then posts nothing; there is no assisted fallback, ADR-54) |
| Make a tracked bio or affiliate link (from S2c) | `uv run clipforge link add <account> <url> --kind bio` (prints the `/go/<slug>` link), `uv run clipforge link list <account>` |

**Posting after an outage** (the `posting:outage` flag, log #217). If the newest posting snapshot is more than 2 days old when `posting_daily` runs (07:00 UTC), it sets the flag to that snapshot's date. Expired Dict keys could then make a clip go out twice, so while the flag is set:
- the slots send nothing, for every account, and `posting_daily` skips its rebuild;
- `/status` starts with an "⚠️ Outage" line with the date, and an ops alert tells you which date to restore;
- `/next` still works.

To clear it: restore from the date in the alert, check `/status`, then `/go`:
```
uv run clipforge status --restore <date from the alert>
```
`/go`, `POST /posting/restore` and `clipforge status --restore` each clear the flag. `/go` clears it even when you name one account, and a restore clears it even if nothing was missing, so check `/status` before `/go`.

**After S1 is deployed**, `channels.toml` is no longer read. Sources are managed with `clipforge source` (§4), and `videos/<source-id>/` is the only local mapping.

## 2a. The brake (from S2a)

- **`/pause <account>`** stops one account; **`/pause all`** (or `/pause` alone) stops every account. **`/go <account>`** and **`/go all`** restart. `/go <account>` while `/pause all` is on says "still braked by /pause all; send /go all to resume".
- **What a brake stops:** every dispatcher phase for that scope (no plan, no review notification, no hand-off). From S2b it also **cancels posts already scheduled at Upload-Post** for that scope; the reply counts them ("Paused realtalk-clips-en: 1 scheduled post cancelled, 0 already out"). `/go` puts cancelled items back: they lead the next plan, and a slot whose time has passed is missed.
- **"Recorded in the brake only":** the reply when Neon is down. The brake lives first in a Dict key (`brake:<scope>`), which works without the database; the database copy (`posting_state`) is written later, and `posting_daily` repairs any difference (the newer one wins).
- **How to check:** `/status` in Telegram or `uv run clipforge status` shows which scopes are braked; `uv run clipforge autopilot show <account>` shows the account's state.

## 3. Sessions and hand-off

From the 2026-09-30 pause on, work runs as **cards → worktree branches → pull requests**. A new coordinator starts here, from `main` (the pause is the tag `pause-2026-09-30`), and needs nothing else.

### 3.1 Read first (new coordinator), in order

1. `STATUS.md`: what's running now (production, open PRs), what waits on the owner, the next cards, every workstream, and the open follow-ups.
2. `docs/cards/README.md` and the cards it lists; `docs/templates/` (card, report, stop card, checkpoint).
3. `CLAUDE.md` (project rules 1–9), `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (accepted ADRs are binding; ADR-41 to ADR-50 accepted on 2026-09-30 and 2026-10-01, ADR-27 and ADR-33 on 2026-10-02).
4. `docs/studio/10-decision-log.md` (every owner decision and the Open table), `docs/studio/04-roadmap.md` (the Phase 6 source of truth), `docs/studio/08-dashboard-and-operations.md` §2 and §2b, `docs/studio/09-account-registry.md`, `docs/ops/secrets.md`.
5. The rest of this runbook: the owner's steps and commands.

**Rules that stay in force:**
- The coordinator asks, reviews, fixes docs and writes cards. It doesn't write code or build features.
- It never runs git write commands, `gh` write commands, deploys, or Modal stop commands. The owner runs them; the coordinator writes the exact commands.
- Read-only git (`status`, `diff`, `log`, `ls-files`, `show`) is allowed without asking (log #388, `.claude/settings.json`).
- Every piece of work is a card in `docs/cards/` (template `docs/templates/card.md`). The owner starts a session with `Run card docs/cards/NNN-….md`. Sessions report into `docs/reports/`, never only in chat.
- Sessions don't commit. The owner commits at checkpoints, pushes, opens a PR, and merges when CI is green (`docs/templates/checkpoint.md`).
- Deploys: only with the owner's OK, from `main`, outside the blackout (§1). From card 001 on, only through `scripts/deploy.sh`.
- The coordinator knows what's running before it reports or hands out a prompt: `ListAgents` (sessions named `clipforge-<stream>-xx`, busy or idle), `git worktree list` with each worktree's `git status --short`, `ps -eo pid,lstart,args | grep '[c]laude'` (shows `claude Run card …` and running Modal probes), and `gh pr list`. If it edits a card after that card's session has branched, it sends the change to the session with `SendMessage` and says so; the card file reaches `main` through a coord PR (2026-10-02).
- **Deploy before the next code merge** (log #144): every deploy ships all of `main`, so a code card is deployed, with its owner steps done, before the next code card merges. Before a deploy, check that `docs/ops/deploys.md`'s last row matches `git log` (no merged code waiting), and that `db_doctor` shows the expected migration head. Docs-only merges are exempt.
- Memory holds preferences and pointers only. Facts that change live in `STATUS.md` and the docs; the coordinator reviews memory at each pause.

### 3.2 How a card runs

1. The coordinator writes `docs/cards/NNN-<stream>-<topic>.md` in a `coord/<topic>` branch; the owner merges it.
2. The owner creates the worktree: `scripts/worktree.sh <branch>` (after card 001; before it, the manual commands in 3.3), opens a session there, and pastes `Run card docs/cards/NNN-….md`.
3. At each checkpoint the session runs `scripts/check.sh`, writes its report, and stops (the `checkpoint` skill). The first time you open a session in a new worktree, Claude Code asks you to trust the folder: accept, so the project hooks in `.claude/settings.json` run. The owner commits, pushes and opens or updates the PR.
4. CI runs `scripts/check.sh` and the scope check (`scripts/scopes.toml`) on the PR. The owner squash-merges when it's green, with the card number in the title.
5. The coordinator reviews the PR with the `review-pr` skill (`gh pr view`/`gh pr diff`, the card and report, then the `pr-reviewer` agent), gives a verdict, and after the merge updates `STATUS.md` and the card's status line. It writes the next card with the `write-card` skill.

Decision-log number ranges per branch prefix are in each card and in `scripts/scopes.toml` (`coord/` #1–199, S1 #200–249, S3c #250–299, S3a #300–319, X2 #320–339, S4 #340–379, X0 #380–399, cleanup #400–419, S3 #420–439, S2 design #440–469, X4 #470–479, S2a #480–499, S2b #500–529, S2c #530–549). A conflict in `docs/studio/10` is two blocks added at the end: keep both, in number order; gaps are fine.

### 3.3 Worktrees

```
scripts/worktree.sh s1/finish            # ../clipForge-s1: branch from origin/main (or the existing branch), .env and web/.env.local copied, uv sync, npm ci
scripts/worktree.sh --remove s1/finish   # after its PR is merged (refuses otherwise)
```

By hand, if the script can't be used:

```
cd ~/code/clipforge/main && git fetch origin
git worktree add ../clipForge-x0 -b x0/tooling origin/main
cp .env ../clipForge-x0/ && (cd ../clipForge-x0 && uv sync)
# a web worktree also needs: cp web/.env.local ../clipForge-web/web/ && (cd ../clipForge-web/web && npm ci)
git worktree remove ../clipForge-x0     # after its branch is merged
```

### 3.4 Rules for shared docs

- `docs/studio/10`: append only, in the branch's range; re-read before editing; superseded rows get `superseded by N`.
- `docs/studio/04` is the Phase 6 source of truth; `ROADMAP.md` mirrors it and is ticked in the same change.
- ADRs: accepted ones only in `docs/DECISIONS.md`. 05 holds the drafts and the next free number (ADR-55). ADR-41 (S1), ADR-42 (S3c), ADR-27 and ADR-33 (S2), and ADR-54 (Telegram is notifications only) are accepted and live in `docs/DECISIONS.md`.
- `STATUS.md`: the coordinator's; sessions don't edit it except S1's plan-status line if its card says so.
- Specs and plans are marked historical after their build (`docs/superpowers/README.md`).

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
4. **Decisions to have ready** (10 → Open): Billy Garton Jr.'s permission facts (O5): when it was granted, by whom, a link to where the agreement is stored, whether monetization and translations are allowed, and any expiry. (O3, the handles for founder.tapes and hombre.en.construccion, is needed only before S2: those accounts are created then, ADR-48, log #135.)

### 4b. During the build
Approve each checkpoint the S1 session reports. A checkpoint is a commit on the card's branch, reviewed in its PR (§3.2).

### 4c. Rollout ✅ steps 1–7 done 2026-10-05 (card 010; notes from the run are inline below; step 8 is a later card) (run as card 010; each deploy only with your OK; the session runs these with you)
1. Migrate the database:
   ```
   uv run --env-file .env alembic upgrade head
   ```
   It prints nothing on success (log #223); `db_doctor` or `deploy.sh --dry-run` then shows the head.
2. Deploy. The Dict stays the primary, and Postgres gets a copy of every write:
   ```
   scripts/deploy.sh --reason "S1 rollout 4c.2: dual write"
   ```
   Deploy from `~/code/clipforge/main`: its `.env` needs `DEPLOY_DB_CHECK=on` and `DATABASE_URL_UNPOOLED` for the migration-head check.
   ```
   ```
   Put `DATABASE_URL` (the pooled string) back in `clipforge-secrets` first (dashboard edit, #107): without it the app stays Dict-only.

   Also first, set `DEPLOY_DB_CHECK=on` in `.env` (card 008, log #391). From this deploy on, `scripts/deploy.sh` refuses when the database is behind the code's newest migration; it reads `alembic_version` read-only through `DATABASE_URL_UNPOOLED`. Before deploying, `scripts/deploy.sh --dry-run` should show `ok   database at the migration head: database and code at 0001`.

   **From this deploy until step 5's import, expect ops alerts.** The Dict still writes everything, and each write is copied to Postgres, which has no account or source rows yet, so the copies fail. You get "Posting mirror write (…) failed" alerts (at most one per write kind an hour) and a `posting verify` alert from the daily run. They stop after step 5. Run steps 3–6 in one sitting to keep the window short.
3. Create the live account:
   ```
   uv run clipforge account create --blueprint realtalk-clips --lang en --handle realtalk.clipsdaily --posting-from-env
   ```
   founder.tapes and hombre.en.construccion are created just before S2, with O3's handles (ADR-48, log #135):
   ```
   uv run clipforge account create --blueprint founder-tapes --lang en --handle <final handle>
   uv run clipforge account create --blueprint hombre-en-construccion --lang es --handle <final handle>
   ```
4. Import the channel into sources, then fill in its permission record:
   ```
   uv run clipforge source import-toml --account realtalk-clips-en --dry-run   # from a worktree add --folder ~/code/clipforge/main/videos
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
6b. Rewrite the schedule copies and check them (the S1 plan's step 7b, log #213). In postgres mode the tick finds each account only through its Dict copy `posting:schedule:<account>`. Run the daily reconcile once (it rewrites every copy and repeats the verify), then the read-only database check:
   ```
   uv run modal run src/clipforge/app.py::posting_daily
   uv run modal run src/clipforge/app.py::db_doctor
   ```
   `db_doctor` must print `ok: True` and `schedule_drift: []`. If it names an account, run any `uv run clipforge account edit` on it, or `posting_daily` again, then check again. Don't go on to step 7 until it's empty.
7. Switch reads to Postgres: set `STATE_READS=postgres` in `clipforge-secrets` and `.env` (type it carefully: `deploy.sh` checks only `.env`, and a typo in the secret, as on 2026-10-05, crashes every container until fixed; check `uv run modal app logs clipforge` right after the deploy), then:
   ```
   scripts/deploy.sh --reason "S1 rollout 4c.7: reads from Postgres" --rollout-step 4c.7
   ```
   Posting stays paused (ADR-54), so there are no slots or taps to watch: check `uv run clipforge status` (it now reads from Postgres), `uv run clipforge posting verify` at 0 differences, `db_doctor`, and `/status` in Telegram (it says paused). Keep posting paused after this step. The verify also runs daily inside `posting_daily` (07:00 UTC): its log line is `posting_daily: verify: …`.
8. After **7 days** with a clean verify every day: a later session removes the Dict copy of the queue and `posting_daily`'s Dict parts (the touch, the Dict snapshot and the verify), and ADR-24 retires. `posting_daily` itself stays (ADR-46), with the jobs backfill, the schedule copies, the rebuild and the table snapshot (log #218).

**Rollback** at any point: set `STATE_READS=dict` and redeploy. The Dict has stayed current for realtalk, and the other accounts pause until you switch back. Run `clipforge posting verify` before switching to Postgres again.

`STATE_READS=dict` moves only the posting queue back. Job pages (`GET /jobs/{id}`, `clipforge status <job_id>`) and the overview read the `jobs` table whenever a database is connected, whatever `STATE_READS` says. To take the database out completely, also delete `DATABASE_URL` from `clipforge-secrets` (dashboard edit) and redeploy: everything then runs Dict-only, as before S1.

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

### 5b. Accounts and keys ✅ done 2026-10-06 (card 004: production at https://clipforge-web-brown.vercel.app)
1. **Vercel Pro:** confirm the plan in the Vercel dashboard. Hobby is non-commercial only.
2. **GitHub OAuth apps** (GitHub → Settings → Developer settings → OAuth Apps → New):
   - production: callback `https://clipforge-web-brown.vercel.app/api/auth/callback/github` (Vercel's assigned name; `clipforge-web.vercel.app` was taken, log #301), or your custom domain;
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
   `MOCK_API=1` for previews is **not** set automatically: add it with `vercel env add MOCK_API preview ""` (value `1`) before the next preview. `vercel link --yes` pulls the project's Development env into `web/.env.local`: check that file afterwards and remove anything it added that you didn't set (card 004 found `VERCEL_OIDC_TOKEN`). Never add `MOCK_API` or `AUTH_DISABLED` to production. A preview proves only the build and the redirect to `/login` (log #83): GitHub login works on localhost and on the production domain only. Deep links keep their target through login (log #99).
4. Tell the S3a session it's done. It deploys a preview (mock data), and production only after your OK:
   ```
   cd web && vercel deploy            # preview
   cd web && vercel deploy --prod     # production
   ```
5. Log in on your phone and your laptop, and check Home against `/status`.

## 6. S2: publishing ⬜ (prepare now, because warm-up takes days)

The build is three cards: 014 (S2a, rails), 015 (S2b, Upload-Post for realtalk) and 016 (S2c, autopilot and the two launches). **Updated 2026-10-05 (ADR-54):** S2b (card 015) starts only after card 024 (the Review page) is deployed, so the order is 014 → 031 → 004 → 022 → 023 → 024 → 015 → 016; reviews happen on the dashboard, and Telegram only notifies. Every deploy: `scripts/deploy.sh --dry-run` first, then the deploy outside the blackout (§1). New secrets: add **only** the new keys in the Modal dashboard (§0), never `modal secret create --force`; then add them to `.env`.

**Prepare now:**
1. Create the TikTok, Instagram (a Professional account linked to a Facebook Page), YouTube and Facebook accounts for founder.tapes and hombre.en.construccion, with the handles from O3. Use them normally for 3–5 days; no fake engagement. Record the handles in `docs/studio/09-account-registry.md`.
2. Get source permissions for them: one permitted source each (a creator agreement), or a Whop account only if a campaign source is planned.

**S2a (card 014), in two PRs** (updated 2026-10-06): PR 1 (migration 0002 and the data layer) was deployed 2026-10-06 02:27 UTC (`deploy-20261006-0227`). PR 2 (the dispatcher, the brake, autopilot, the gate and routing) has no migration:
1. `scripts/deploy.sh --dry-run --rollout-step 4c.7`, then `scripts/deploy.sh --reason "S2a-2: dispatcher replaces posting_tick" --rollout-step 4c.7`, outside the blackout (`--rollout-step 4c.7` is needed on every deploy until card 040, log #154).
2. `uv run modal run src/clipforge/app.py::db_doctor`: ok, head `0002`, a schedule copy for every account.
3. In Telegram, send one `/pause` (no account means all). It writes the fleet brake key and keeps `posting_state` paused. **Don't send `/go all`:** it lifts every brake and unpauses every account, and a slot opened in the last 30 minutes could send a clip before the next `/pause` (PR #52 review). Until the first 07:00 UTC `posting_daily`, the paused `posting_state` row alone keeps realtalk silent; that run restores a missing per-account brake key and sends one "Brake key … was missing; restored" alert, which is expected.
4. For one day: the `dispatcher:` log lines say braked or paused and send nothing, and `uv run clipforge posting verify` reports 0 differences.
5. `uv run clipforge autopilot show realtalk-clips-en`: Hands-on, "Publish: on, waiting for a connected profile".
6. `uv run clipforge policy dry-run` (the gate is still log-only). Note the count for S2b.
- Rollback: first check `/status` says paused. Then revert PR 2's merge on `main` and run the same two `deploy.sh` commands, and send `/pause` again if `/status` doesn't say paused afterwards (a `/pause` during a Neon error writes only the brake key, which main ignores). The database stays at `0002` (never `alembic downgrade` in production); main ignores the new `brake:*`, `posting:publish:*` and `dispatch:*` Dict keys, which expire after 7 idle days, and `posting_tick` obeys the paused `posting_state` row.

**Before S2b's code (card 015, plan Task 9, R5):**
1. Buy Upload-Post **Basic** (monthly; $24 for 5 profiles; Free has no TikTok). Upgrade to Professional ($50, 25 profiles) when the 6th account is created (O4, #440).
2. Create a **test** profile `s2-probe` and connect one test TikTok (or YouTube) account. Put `UPLOAD_POST_API_KEY` (from Upload-Post's dashboard) in `.env` only.
3. Run the probe with the session (`uv run python scratch/s2/r5_probe.py`), again after 10 minutes and after 24 h. Its post is scheduled 2 or more days out and cancelled, so nothing is published. The session writes the results in its report; read them before it goes on.

**S2b (card 015) deploy:**
1. In Upload-Post: create the profile `realtalk-clips-en` and connect TikTok (allow public posts), Instagram (Professional, linked to the Page), YouTube and Facebook. Note the Facebook Page id.
2. Register the webhook URL `<API_URL>/webhooks/upload-post` for `upload_completed`, `social_account_disconnected`, `social_account_reauth_required` and `social_account_connected`. Saving it creates the `whsec_…` secret.
3. Add `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` to `clipforge-secrets` (dashboard edit, only these two keys) and `.env` (`docs/ops/secrets.md`).
4. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S2b: publishing"`.
5. `uv run clipforge policy dry-run`. When it reports "0 items would be held", set `GATE_ENFORCE=on` in `clipforge-secrets` and `.env`, then redeploy (dry run first).
6. `uv run clipforge account edit realtalk-clips-en --publisher-profile realtalk-clips-en --facebook-page-id <id>`, then `uv run clipforge publisher check realtalk-clips-en`: no problems.
7. Approve one item on the dashboard's Review page (Telegram only notifies, ADR-54). After its slot: `uv run clipforge status`, `uv run clipforge posting verify` (0 differences), and the post on each platform.
8. With one item scheduled: `/pause realtalk-clips-en` (the reply says 1 cancelled), then `/go realtalk-clips-en`. Run a day on Hands-on.

**S2c (card 016) launch:**
1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S2c: autopilot, digest, links"`.
2. `uv run clipforge account create --blueprint founder-tapes --lang en --handle <O3 handle>` and `uv run clipforge account create --blueprint hombre-en-construccion --lang es --handle <O3 handle>`. Both start Hands-on.
3. One permitted source each: `uv run clipforge source add …` with its permission record, then clip at least one episode (`uv run clipforge clip videos/<source>/<file> --fetch`).
4. One Upload-Post profile each (`founder-tapes-en`, `hombre-en-construccion-es`; 3 of Basic's 5), connected as in S2b; then `uv run clipforge account edit <id> --publisher-profile <id> --facebook-page-id <id>` and `uv run clipforge publisher check <id>`.
5. Optional: `uv run clipforge link add realtalk-clips-en <bio url> --kind bio`, and put the printed `/go/<slug>` link in the bio.

**Rollback:** one account: `uv run clipforge account edit <id> --clear-publisher` (cancels its scheduled Upload-Post posts; the account then posts nothing, since the assisted fallback is gone, ADR-54). The gate: `GATE_ENFORCE=off` and a redeploy. A promotion: `uv run clipforge autopilot preset <id> hands_on --reason "<why>"`. A whole step: a revert on `main`, then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "revert S2<x>"`; 0002 is expand-only, so older code runs on it. **Reverting a card that added a migration** (any card, not only S2): keep its schema files in the revert, or `deploy.sh`'s head check (and CI's `alembic upgrade head`) fails with the database ahead of the code: `git revert --no-commit <sha>`, then `git checkout <sha> -- alembic/versions/<NNNN>_*.py src/clipforge/db/tables.py src/clipforge/db/doctor.py` and the migration tests, then `scripts/check.sh`. Never `alembic downgrade` in production (HK-1a review, 2026-10-06).

## 7. Spikes

- **X1 voice** ✅ (2026-09-30): Qwen3-TTS primary, Kokoro fallback (log #69, report `docs/studio/spikes/x1-voice.md`). ✅ `scratch/` is removed; every result is in docs/studio/03, 04, spikes/ and the log. Keep the `clipforge-models` Modal Volume: it holds the Qwen and Kokoro weights and the v2 reference voice (`refs/x1/`) that S5 needs.
- **X2 talking head** ⏸ (stopped at ~25% on 2026-09-30): licenses checked, no clips yet. Before it resumes, rule on O7 (WenetSpeech, log). Its ~227 GB of weights stay on `clipforge-models` under `x2/`; if X2 won't resume soon, remove them with `uv run modal volume rm -r clipforge-models x2`. Report and resume recipe: `docs/studio/spikes/x2-talking-head.md`.
- For later spikes: if a model is gated, create a free Hugging Face token (read-only) and add `HF_TOKEN` to `.env` (and to the spike's Modal secret, if the session asks).
- **X5 Judge** ⬜: join the TypeSafe Jev waitlist now. The key (`TYPESAFE_API_KEY`) goes in `.env` when it arrives.

## 8. The git repo and GitHub ✅ (private remote `MatPizzolo/clipforge`; baseline and the pause commit `405c8ec`, tag `pause-2026-09-30`, pushed 2026-09-30)

Order: the baseline now → pause every session → the pause commit and tag → a new coordinator session. The coordinator never runs git, `gh`, deploys or Modal stop commands: you do.

**1. Gate the CI deploy job before the first push** (decision log #109). `ci.yml` deploys on every push to `main`, and the Actions secrets don't exist yet, so the first push would go red. S1 owns `ci.yml` (§3); this one-line edit is agreed with it:
```
cd ~/code/clipforge/main
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
cd ~/code/clipforge/main
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
# without the gh CLI: open https://github.com/MatPizzolo/clipforge/actions
```
Send the coordinator the output of `git status`, `git log --oneline -1`, `git ls-files | wc -l` and `gh run list --limit 5`.

**5. At the pause** (after every session has reported and the coordinator's check is clean). First regenerate the dashboard's API contract, which S1's new routes made stale:
```
cd ~/code/clipforge/main
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
Then take `DATABASE_URL` out of the Modal secret (#107). **Recommended: the Modal dashboard** → Secrets → `clipforge-secrets` → Edit → delete the `DATABASE_URL` key only → Save. Modal can't show secret values, so recreating it from the CLI works only if `.env` holds every key the secret has. **It doesn't:** the `POSTING_*` keys are only in the secret (`docs/ops/secrets.md`), so the command below would drop them. Use the dashboard, or add the `POSTING_*` lines to `.env` first:
```
grep -v -E '^(DATABASE_URL|DATABASE_URL_UNPOOLED|NEON_BRANCH)=' .env > /tmp/clipforge-secrets.env
cut -d= -f1 /tmp/clipforge-secrets.env         # check the key names (no values shown)
uv run modal secret create clipforge-secrets --from-dotenv /tmp/clipforge-secrets.env --force
shred -u /tmp/clipforge-secrets.env
```
No redeploy is needed: the deployed app doesn't use the database yet.

**Protect `main`** (after card 017 is merged: `check` then reports on every PR, docs-only ones included): GitHub → the repo → Settings → Branches (or Rules → Rulesets) → a rule for `main`: require a pull request, require the status checks `check` and `scope` to pass (not `web`: it runs only when `web/`, `src/` or the contract changes, and a required check that never runs blocks the merge; see the comment at the top of `web.yml`), block force pushes. Or from the terminal:
```
gh api -X PUT repos/MatPizzolo/clipforge/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {"strict": false, "contexts": ["check", "scope"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 0},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
gh repo edit --delete-branch-on-merge      # merged branches go away on their own
```
On a free personal account, protection on a private repo may need GitHub Pro (the call answers 403 "Upgrade to GitHub Pro"); without it, keep the PR flow by convention and CI still runs on every PR.

**CI runs once per commit** (card 017): `ci.yml` runs on pull requests and on pushes to `main` only, so a branch gets CI once its PR is open. A PR that changes only docs (`docs/`, Markdown files outside `prompts/`, `.gitignore`) runs only the docs tests in `check` (under a minute); anything else runs the whole gate. Every action is pinned to a commit SHA, and dependabot opens one grouped PR a week to update them (branch `dependabot/github_actions/…`, allowed to change only `.github/workflows/`): merge it when CI is green.

**Still left, and when:**
- The Actions secrets `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` and `DATABASE_URL_UNPOOLED`, and the repository variable `DEPLOY_ENABLED=true`. `ci.yml` runs `alembic upgrade head` before deploying and skips web- and docs-only pushes (S1 Task 21b, log #212), but that isn't everything `DEPLOY_ENABLED` needs. Before you set it, all of these must be in place:
  - the Actions secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` (the deploy) and `DATABASE_URL_UNPOOLED` (the migration);
  - the repository variables `POSTING_SLOTS` and `POSTING_TIMEZONE`, identical to `clipforge-secrets`: the job's blackout step fails without them, and it has no defaults;
  - card 008's `tag` job on `main`: after each CI deploy it pushes the `deploy-YYYYMMDD-HHMM` tag and writes the deploy line into the run summary (log #392).

  ```
  gh secret set MODAL_TOKEN_ID
  gh secret set MODAL_TOKEN_SECRET
  gh secret set DATABASE_URL_UNPOOLED
  gh variable set POSTING_SLOTS --body "<the value in clipforge-secrets>"
  gh variable set POSTING_TIMEZONE --body "<the value in clipforge-secrets>"
  gh variable set DEPLOY_ENABLED --body true      # last
  ```
  CI deploys are recorded by their tag (`git fetch --tags && git tag -l 'deploy-*'`), not in `docs/ops/deploys.md`. The step itself is still yours. Until you do it, you deploy with `scripts/deploy.sh` from `main` (§1); it refuses inside the blackout.
- In Vercel, connect the repo with Root Directory `web` when you do the Vercel steps (§5b).
- From the pause on, every parallel session gets its own git worktree (§3).

## 9. Starting a new session

| For | Do |
|---|---|
| Any piece of work | Ask the coordinator for a card (or take the next one in `STATUS.md`), create its worktree (§3.2), open a session there and paste `Run card docs/cards/NNN-….md` |
| Stopping a running session | Paste `docs/templates/stop-card.md` |
| A coordinator session | `You are the ClipForge coordinator. Work from main. Read docs/studio/11-owner-runbook.md §3 first and follow it.` |
| A quick status check | Open `STATUS.md` |

06's prompts A–I remain the source for new cards: the coordinator builds a card from the matching prompt and action card, adding the context, scope and number range.

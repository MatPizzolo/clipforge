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

## 3. Running sessions in parallel (until the git repo exists)

| Session | Owns | Deploys |
|---|---|---|
| S0 (verification) | docs only now; waiting on your phone test | done |
| S1 | `src/`, `tests/`, `alembic/`, `alembic.ini`, `blueprints/`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, the S1 docs | the only session allowed to run `modal deploy`, each time with your OK |
| S3a (parked at checkpoint G) + the S3 workspaces design, same session | `web/`, `scripts/export_openapi.py`, `.github/workflows/web.yml`, the S3a docs; for the design: its spec, the ADR-42 draft in 05, the S3 card in 06, S3 in 04, 08 §2 | Vercel only, with your OK |
| X1 spike | done 2026-09-30. `scratch/x1/` is left to delete (§7) | — |
| Nobody yet (created by S1 for Neon, at your request) | `.mcp.json` (Neon MCP server, project id only), `.neon` (gitignored), `.claude/skills/neon*`, `skills-lock.json` | — |
| Shared, last to write | `CLAUDE.md`: S1 updates its layout and commands in its Task 21; S3a adds one `web/` line when Task 13 finishes | — |

All sessions may add rows to `docs/studio/10-decision-log.md`. They re-read it first and never rewrite the file.

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
cd web && npm run dev          # http://localhost:3000
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
   `MOCK_API=1` is already set for previews. Never add `MOCK_API` or `AUTH_DISABLED` to production.
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

**5. At the pause** (after every session has reported and the coordinator's check is clean):
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

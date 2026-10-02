# Secrets and settings inventory (names only, never values)

Where each key lives. Values are typed by the owner only; sessions never read or print them. Update this file in the same change that adds, moves or removes a key.

| Key | Modal `clipforge-secrets` | root `.env` | `web/.env.local` | Vercel | GitHub Actions | Notes |
|---|---|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | ✅ | | | | |
| `API_TOKEN` | ✅ | ✅ | ✅ | production | | the job API's bearer token |
| `API_URL` | | ✅ | | | | the CLI's target (public URL, not secret) |
| `CLIPFORGE_API_URL` | | | ✅ | production | | same URL, for the dashboard |
| `TELEGRAM_BOT_TOKEN` | ✅ | ✅ | | | | |
| `TELEGRAM_WEBHOOK_SECRET` | ✅ | ✅ | | | | |
| `TELEGRAM_ALLOWED_USER_IDS` | ✅ | ✅ | | | | |
| `DOWNLOAD_SIGNING_KEY` | ✅ | ✅ | | | | |
| `POSTING_TIMEZONE`, `POSTING_SLOTS` | ✅ | ✅ **required**, identical to the secret | | | later, with `DEPLOY_ENABLED` (repository variables, read by `ci.yml`'s blackout step) | `scripts/deploy.sh` computes the blackout from `.env` and refuses when either is missing (it never uses config.py's defaults). Change both places together |
| `POSTING_CHAT_ID`, `POSTING_HASHTAGS` | ✅ | ❌ not in `.env` | | | | only in the Modal secret: so the secret can't be rebuilt from `.env` (use the dashboard edit) |
| `DASHBOARD_URL` | optional | optional | | | | the dashboard's https address; bot messages get buttons to its pages (ADR-44). Unset = no buttons. Not secret |
| `OWNER_TIMEZONE` | optional | optional | | | | quiet hours for ops alerts (ADR-45); unset = `POSTING_TIMEZONE`. Not secret |
| `POSTING_ACCOUNT_ID` | optional | optional | | | | in `STATE_READS=dict` mode, the account the `POSTING_*` settings describe; default `realtalk-clips-en`. Not secret |
| `DATABASE_URL` | ❌ until rollout step 4c.2 (#107) | ✅ | | | | pooled Neon URL |
| `DATABASE_URL_UNPOOLED` | | ✅ | | | later, with `DEPLOY_ENABLED` (`ci.yml`'s migration step already reads it) | direct Neon URL, for migrations |
| `NEON_BRANCH` | | ✅ | | | | written by `neon link` |
| `STATE_READS` | add now (`dict`), flip at 4c.7 | ✅ **required**, identical to the secret | | | | `scripts/deploy.sh` refuses when it's missing from `.env`, and when it isn't `dict` without `--rollout-step 4c.7`. Change both places together |
| `DEPLOY_DB_CHECK` | | optional (`on`/`off`, default `off`; `on` from rollout step 2) | | | | read only by `scripts/deploy.sh` from `.env`: when `on`, it refuses to deploy while the database is behind the code's newest migration (card 008, #391). Not secret |
| `YOUTUBE_PROXY_URL` | | ✅ | | | | unused (ADR-17 deferred); its password was pasted in chat once: rotate or delete it |
| `AUTH_SECRET` | | | ✅ | preview, production (different values) | | Auth.js |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` | | | ✅ (the local OAuth app) | production (the production OAuth app) | | |
| `OWNER_EMAIL` | | | ✅ | production | | the dashboard allowlist |
| `MOCK_API` | | | local only | preview (`1`) | | never production |
| `AUTH_DISABLED` | | | local only | never | | refused on every Vercel environment |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | | | | | later, with `DEPLOY_ENABLED` | read by `ci.yml`'s deploy job and by `manual.yml` (GPU and smoke tests, run by hand) |
| `DEPLOY_ENABLED` (a repository variable, not a secret) | | | | | later | turns the CI deploy job on |
| `TYPESAFE_API_KEY`, `HF_TOKEN` | | when a spike needs them | | | | spikes only |

Non-secret defaults (`HIGHLIGHT_MODEL`, `WHISPER_MODEL`, `DEFAULT_*`, `MODAL_APP_NAME`, `JOBS_ROOT` and others) are listed with comments in `.env.example`. Two more are set by the app itself, not by you: `BLUEPRINTS_DIR` (the blueprints mount, set in `app.py`) and `GIT_SHA` (the build, set by `scripts/deploy.sh` and the CI deploy).

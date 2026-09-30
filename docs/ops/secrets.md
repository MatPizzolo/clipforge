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
| `POSTING_CHAT_ID`, `POSTING_TIMEZONE`, `POSTING_SLOTS`, `POSTING_HASHTAGS` | ✅ | ❌ not in `.env` | | | | only in the Modal secret: so the secret can't be rebuilt from `.env` (use the dashboard edit) |
| `DATABASE_URL` | ❌ until rollout step 4c.2 (#107) | ✅ | | | | pooled Neon URL |
| `DATABASE_URL_UNPOOLED` | | ✅ | | | later, for `ci.yml`'s migration step | direct Neon URL, for migrations |
| `NEON_BRANCH` | | ✅ | | | | written by `neon link` |
| `STATE_READS` | add at rollout 4c.1 (`dict`), flip at 4c.7 | optional | | | | default `dict` |
| `YOUTUBE_PROXY_URL` | | ✅ | | | | unused (ADR-17 deferred); its password was pasted in chat once: rotate or delete it |
| `AUTH_SECRET` | | | ✅ | preview, production (different values) | | Auth.js |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` | | | ✅ (the local OAuth app) | production (the production OAuth app) | | |
| `OWNER_EMAIL` | | | ✅ | production | | the dashboard allowlist |
| `MOCK_API` | | | local only | preview (`1`) | | never production |
| `AUTH_DISABLED` | | | local only | never | | refused on every Vercel environment |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | | | | | later, with `DEPLOY_ENABLED` | only after `ci.yml` runs the migrations |
| `DEPLOY_ENABLED` (a repository variable, not a secret) | | | | | later | turns the CI deploy job on |
| `TYPESAFE_API_KEY`, `HF_TOKEN` | | when a spike needs them | | | | spikes only |

Non-secret defaults (`HIGHLIGHT_MODEL`, `WHISPER_MODEL`, `DEFAULT_*`, `MODAL_APP_NAME`, `JOBS_ROOT` and others) are listed with comments in `.env.example`.

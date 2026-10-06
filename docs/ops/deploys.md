# Deploy log

One line per production deploy of the `clipforge` Modal app. From card 001 on, `scripts/deploy.sh` appends it; before that, lines were added by hand from the sessions' reports.

CI deploys (`ci.yml`'s deploy job, once `DEPLOY_ENABLED` is on) aren't listed here: CI can't commit to `main`. Each one pushes the same `deploy-YYYYMMDD-HHMM` tag and writes its line, in this table's format, into the run's summary (card 008). The full history is the tags: `git fetch --tags && git tag -l 'deploy-*'`; `git show <tag>` gives the commit.

| When (UTC) | Commit | Tag | By | Why |
|---|---|---|---|---|
| 2026-09-23 | — | — | owner | first deploy (plan 3) |
| 2026-09-28/29 | — | — | owner | plans 4–6 and plans A–C (live 2026-09-29) |
| 2026-09-30 | — | — | S1 (owner's OK) | restart after the owner stopped the app |
| 2026-09-30 | — | — | S1 (owner's OK) | PyAV pin in the whisper image (#70) |
| 2026-10-02 02:10 | dea435d | deploy-20261002-0210 | owner | cards 002 + 006 + tzdata: posting_daily, ops alerts, Timeline renderer v4 |
| 2026-10-02 02:50 | 6e832a7 | deploy-20261002-0250 | owner | restart Dict-only: DATABASE_URL removed from clipforge-secrets (the key was removed after this deploy started, so it didn't take; see the next row) |
| 2026-10-02 03:14 | 6e832a7 | deploy-20261002-0314 | owner | restart Dict-only after removing DATABASE_URL: `GET /posting`, `/next` and Telegram taps had failed (seen from 02:51 UTC, possibly since the 02:10 deploy; `relation "sources" does not exist`; DATABASE_URL was in the secret before rollout step 1's migration); fixed, no data lost (the Dict stayed primary) |
| 2026-10-05 21:10 | 399196c | deploy-20261005-2110 | owner | S1 rollout 4c.2: dual write (manual deploy: GitHub Actions outage; code identical to green CI run 37130686598) |
| 2026-10-05 21:45 | 399196c | deploy-20261005-2145 | owner | S1 rollout 4c.7: reads from Postgres (the secret had `STATE_READS=postgress`: every container failed settings validation 21:45–21:50 UTC; nothing written, no slot due) |
| 2026-10-05 21:50 | 399196c | deploy-20261005-2150 | owner | S1 rollout 4c.7: fix STATE_READS typo in the secret |
| 2026-10-05 23:36 | 3f0fc88 | deploy-20261005-2336 | owner | 039: S1 follow-ups |
| 2026-10-06 02:27 | 3cf7f2f | deploy-20261006-0227 | owner | S2a-1: migration 0002, data layer |

# Deploy log

One line per production deploy of the `clipforge` Modal app. From card 001 on, `scripts/deploy.sh` appends it; before that, lines were added by hand from the sessions' reports.

CI deploys (`ci.yml`'s deploy job, once `DEPLOY_ENABLED` is on) aren't listed here: CI can't commit to `main`. Each one pushes the same `deploy-YYYYMMDD-HHMM` tag and writes its line, in this table's format, into the run's summary (card 008). The full history is the tags: `git fetch --tags && git tag -l 'deploy-*'`; `git show <tag>` gives the commit.

| When (UTC) | Commit | Tag | By | Why |
|---|---|---|---|---|
| 2026-09-23 | — | — | owner | first deploy (plan 3) |
| 2026-09-28/29 | — | — | owner | plans 4–6 and plans A–C (live 2026-09-29) |
| 2026-09-30 | — | — | S1 (owner's OK) | restart after the owner stopped the app |
| 2026-09-30 | — | — | S1 (owner's OK) | PyAV pin in the whisper image (#70) |

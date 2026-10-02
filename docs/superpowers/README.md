# Designs (specs) and task plans

Specs say what to build and why; plans say how, task by task. **Active** ones are being built or waiting for review; **historical** ones describe work that's finished (read them for background, but `docs/ARCHITECTURE.md` and the code are the truth); **superseded** ones were replaced before or during their build.

| Spec | Plan | State |
|---|---|---|
| specs/2026-09-23-serverless-pipeline-design.md | plans/2026-09-23-plan-1-chain-core.md, plan-2-real-stages.md, plan-3-modal-wiring.md | historical (deployed 2026-09-23) |
| specs/2026-09-28-face-reframe-design.md | plans/2026-09-28-plan-4-face-reframe.md | historical (ADR-19) |
| specs/2026-09-28-retention-polish-design.md | plans/2026-09-28-plan-5-retention-polish.md | historical (ADR-20) |
| specs/2026-09-28-speaker-framing-design.md | plans/2026-09-28-plan-6-speaker-framing.md | historical (ADR-21) |
| specs/2026-09-28-posting-assistant-design.md | plans/2026-09-28-a-channels-submit.md, b-posting-core.md, c-telegram-assistant.md | historical (ADR-22–24, live 2026-09-29) |
| specs/2026-09-28-posting-queue-design.md, channels-batch-design.md | plans/2026-09-28-posting-queue.md, channels-batch.md | superseded by the posting-assistant spec |
| specs/2026-09-28-youtube-ingest-design.md | — | deferred (ADR-17) |
| specs/2026-09-29-studio-s1-design.md | plans/2026-09-29-studio-s1.md | **active**: the code is done (card 002, PR #5) and deployed Dict-only on 2026-10-02; the rollout (Task 22) is card 010, Task 23 after 7 clean days |
| specs/2026-09-29-studio-s3a-design.md | plans/2026-09-29-studio-s3a.md | **active** (card 004: Tasks 12–13 left) |
| specs/2026-09-30-studio-s3-workspaces-design.md | — (not written yet) | **active**: accepted with ADR-42 on 2026-09-30 (card 003, log #131); the plan waits for its card; amended 2026-10-01 by ADR-48 and ADR-50 |
| specs/2026-10-01-studio-s3-dashboard-design.md | — (the S3 build card and the S3c plan to write) | **active**: approved 2026-10-01 (card 009, PR #20; ADR-48 to ADR-50); mockups in docs/design/dashboard/ |
| specs/2026-10-01-studio-s4-timeline-design.md | plans/2026-10-01-studio-s4.md | historical (ADR-31, ADR-47; card 006, PR #13; deployed 2026-10-02) |

When a plan's build is done and merged, the coordinator moves its row to historical here and adds a one-line note at the top of the spec and plan.

> **Superseded (2026-09-28)** by §3 of `2026-09-28-posting-assistant-design.md`: `clip` submits and exits (`--fetch` to download), `JobInput.channel` is added, and STATUS.md is replaced by `/status`.

# Channels, batch clipping and STATUS.md — design

Date: 2026-09-28 · Status: Accepted · ADR-20

## 1. Goal

The owner downloads whole channels (first: 11 episodes of Billy Garton Jr.'s podcast) into `videos/` and clips them in one go. Each clip must carry the right creator credit and permission, and there must be one place that shows where every channel and episode stands.

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| How is a video tied to a creator? | One subfolder per channel: `videos/<channel-slug>/*.mp4`. `videos/channels.toml` holds each channel's `name` (the credit), optional `url` and `permission`. | A credit set once per channel can't drift. It goes into `JobInput.source_credit` and `permission`, so every `metadata.json` and `post.md` carries it, and the posting queue reads it from there. |
| Loose videos directly in `videos/` | Still work as before, with no credit and the default permission. | Quick one-off tests. |
| A subfolder that isn't in `channels.toml` | Skipped with a warning naming the folder. | A typo must not upload a channel with no credit. |
| Batch runs | `clipforge clip` uploads and submits every new video first, then waits for all of them together (one poll per job every 15 s) and downloads each as soon as it's done. | 11 waits in a row would take hours. Jobs run in parallel on Modal anyway. |
| Interrupted runs and `--no-wait` | The inbox ledger keeps a status per video (`submitted`, `done`, `failed`). The next `clipforge clip` waits for `submitted` jobs and re-checks `failed` ones (a job resumed with `clipforge resume` gets downloaded), without resubmitting. | Ctrl-C or a closed laptop must not lose or duplicate jobs. |
| Output layout | `videos/out/<channel>/<video stem>/`, with `-2`, `-3`… for re-cuts. Loose videos stay at `videos/out/<stem>/`. | Folders grouped by channel. |
| Tracking | `videos/STATUS.md`, regenerated after every `clip` run and by `clipforge report`. It's built only from the ledger, `channels.toml` and `videos/out/*/metadata.json`. | It's always correct because nobody edits it by hand. Notion comes later, with performance data. |
| Old ledger format (`{"file.mp4": "<job_id>"}`) | Read as `done` entries. The next write converts the file. | The owner's real ledger uses it. |

## 3. Files

`videos/channels.toml`:

```toml
[billy-garton]
name = "Billy Garton Jr."
url = "https://www.youtube.com/@..."     # optional, for reference
permission = "creator_agreement"          # own | creator_agreement | clipping_program | cc_by
```

Slugs use lowercase letters, digits and `-` (at most 40 characters), and can't be `out` or `schedule`. Validation errors stop `clip` with exit code 2 and a message naming the file.

`videos/.clipforge.json` (the inbox ledger), with keys relative to `videos/`:

```json
{
  "billy-garton/ep01.mp4": {"job_id": "20260929-…", "status": "done", "out": "billy-garton/ep01"},
  "billy-garton/ep02.mp4": {"job_id": "20260929-…", "status": "failed", "error": "transcribe: …"}
}
```

`videos/STATUS.md`:

```markdown
# ClipForge status
Updated 2026-09-29 10:12

| Channel | Videos | Clipped | Clipping | Failed | New | Clips | Cost |
|---|---|---|---|---|---|---|---|
| Billy Garton Jr. | 11 | 9 | 1 | 1 | 0 | 214 | $1.93 |

## Billy Garton Jr. (`billy-garton`, creator_agreement)
| Video | Status | Clips | Best | Cost | Job |
|---|---|---|---|---|---|
| ep01.mp4 | ✅ clipped | 24 | 0.91 | $0.21 | 20260929-… |
| ep02.mp4 | ❌ failed: transcribe: … | | | | 20260929-… |
| ep03.mp4 | ⏳ clipping | | | | 20260929-… |
| ep04.mp4 | 🆕 new | | | | |
```

The posting queue (ADR-19) adds `Scheduled`, `Queued` and `Days left` columns once it lands.

## 4. Commands

- `uv run clipforge clip`: new videos in `videos/` and in every channel folder, plus unfinished jobs from earlier runs.
- `uv run clipforge clip videos/billy-garton/ep01.mp4 [--again]`: one video. The channel comes from its folder.
- `uv run clipforge report`: rewrites `videos/STATUS.md`. Needs no API.

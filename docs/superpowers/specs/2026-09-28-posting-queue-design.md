> **Superseded (2026-09-28)** by `2026-09-28-posting-assistant-design.md`: the queue moved to Modal with a Telegram posting assistant. Kept for its reasoning (no TikTok-first test, interleaving).

# Posting queue design

Date: 2026-09-28 · Status: Accepted · ADR-19

## 1. Goal

Turn finished clips in `videos/out/` into a posting schedule for one brand account on TikTok, Instagram Reels and YouTube Shorts. The owner uploads by hand with each platform's own scheduler (step A). ClipForge decides **what goes out when** and **what each caption says**.

Command: `uv run clipforge schedule [--days 3] [--start YYYY-MM-DD] [--dry-run]`.

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| Test on TikTok first, then promote winners? | **No.** Every clip goes to all three platforms in the same slot. | Views in a new account's first day are mostly noise: each video goes to a small test audience first, so a flop can be luck. Results on one platform predict the others poorly. Holding clips back gives Instagram and YouTube a third of the data. Revisit after about 30 posts per platform (§7). |
| Where does it run? | Locally, over `videos/out/`: the folders `clipforge clip` downloads, flat or `out/<channel>/<episode>/` (ADR-20). | Step A needs the files on the owner's machine anyway. No Modal, API or network. ADR-19 records this as an interface-side tool, not a pipeline stage. |
| Posts per day | One clip per slot. Slots come from config, default 6 a day (08:00, 10:30, 13:00, 16:00, 19:00, 21:30) in the audience's time zone. | The owner chose 5–7 a day, spaced 2–3 hours apart. |
| Order | Interleave (§4). | The feed shouldn't read like one episode split up. |
| Re-cuts of one video | Only the newest cut (by `finished_at`) of each `source_hash` is queued. A moment is never scheduled twice: a clip whose source time overlaps a scheduled one by IoU > 0.5 counts as already scheduled. | `videos/out/` already holds two cuts of one video. |
| Creator credit | From each clip's `metadata.json`: `input.source_credit` (set from the channel in `videos/channels.toml`, ADR-20), then `input.source_label`. Without one, the clip is still queued, a warning is printed, and the caption has no credit line. | The credit is set once per channel and travels with the job. |
| Captions | A template built from title, hook, credit and configured hashtags. | LLM-written copy is the separate Phase 3 `post.md` item. The queue only needs text it can take from the clip. |
| Clips below 0.80 | Not filtered here. | Job selection already filters (`min_score`). The queue posts what was delivered. |

## 3. Config: `videos/posting.toml` (optional)

```toml
timezone = "America/New_York"   # the audience's time zone
slots = ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]
hashtags = ["personalgrowth", "mindset", "masculinity", "podcast"]
fresh_days = 7      # episodes finished in the last N days...
fresh_bonus = 0.05  # ...get this added to their clips' scores when ordering
```

Validation: the time zone must be a valid IANA name. There are 1 to 12 slots, each `HH:MM`, unique and in order. Hashtags use word characters only, with no `#`. A missing file means defaults. An invalid file stops the command with exit code 2 and says which field is wrong.

## 4. Ordering

1. Group queued clips by `source_hash`, one group per video. Within a group, highest score first, then earliest start.
2. For each slot, look at each group's first clip. Prefer clips from a different video than the previous post, and from a different creator. Drop the creator rule first, then the video rule, when nothing else is left.
3. Among those, pick the highest priority: `score + fresh_bonus` if the video finished within `fresh_days`, otherwise `score`. Ties go to the folder name, then the start time, so the order is deterministic.

## 5. Slots

Days run from `--start` (default: today in the configured time zone) for `--days` days. A slot is open if it is at least 30 minutes after now (platform schedulers need lead time) and not already used in the ledger. Posts go into open slots in order until either slots or clips run out.

## 6. Output

- `videos/out/.posting.json` is the ledger: one entry per scheduled post (`source_hash`, `start`, `end`, `slot`, `folder`, `clip_id`). A dry run doesn't write it.
- `videos/schedule/<YYYY-MM-DD>/` has one folder per day, in the configured time zone:
  - `<HHMM>_<title-slug>.mp4`, a hard link to the clip (copied if linking fails). Sorting by name gives the posting order.
  - `<HHMM>_<title-slug>.txt`, with sections for TikTok, Instagram, YouTube title and YouTube description, ready to paste.
  - `schedule.csv`, appended by each run (header only when the file is new), with columns `time, timezone, video, source, clip_id, score, creator, tiktok, instagram, youtube_title, youtube_description`.
- Platform text limits: TikTok and Instagram 2,200 characters, YouTube title 100 including ` #shorts` (with `<` and `>` removed, since YouTube rejects them), YouTube description 5,000. Instagram uses at most the first 5 hashtags.

## 7. Later (not in this item)

- Performance import: a CSV of per-post views and watch time. It feeds the Phase 5 ranker and, once each platform has about 30 posts, could reorder which queued clips Instagram and YouTube get next (a delayed test-first).
- "Second chance": re-cut a strong moment with a new hook and queue it again. This needs a ledger override.
- Step B: publishing through the platform APIs. It needs TikTok's audit, a Meta Business account linked to a Facebook Page, and Google's audit plus a quota increase (the default is about 6 uploads a day). It gets its own ADR and spec.

## 8. STATUS.md

Once anything has been scheduled, `videos/STATUS.md` (ADR-20) gets a `## Posting` section: scheduled and queued clips per channel, how many days the queue lasts at the configured posts per day, and the last scheduled slot. `clipforge schedule` rewrites the file.

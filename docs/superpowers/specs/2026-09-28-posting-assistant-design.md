# Posting assistant design (phone-first queue on Modal)

Date: 2026-09-28 · Status: Accepted · ADR-22 (channels), ADR-23 (posting assistant), ADR-24 (Dict expiry)

**Implementation status (2026-09-29):** §3 done (plan A, reviewed). §4, §5 and §9 done (plan B, reviewed). §6 and §7 done (plan C Tasks 1–3). Next: §8 webhook taps and commands (plan C Task 4), the `posting_tick` cron (Task 5) and the expiry keep-alive of §4a (Task 6). Nothing is deployed yet.

Replaces `2026-09-28-posting-queue-design.md` (a local queue with day folders) and trims `2026-09-28-channels-batch-design.md` (STATUS.md and mandatory downloads are dropped).

## 1. Goal and success

The owner runs one clips brand on TikTok, Instagram Reels and YouTube Shorts and posts by hand from the phone apps. Sources are whole podcast channels: first 11 episodes of Billy Garton Jr. (`creator_agreement`), with more channels in the same niche later.

Success means:
- At each slot, the phone gets the next clip and ready-to-paste captions. One tap per platform records the post.
- The system always knows each clip's state on each platform, whether that's 11 videos or 500 and one channel or ten. The owner never wonders whether a clip was already posted.
- Adding a channel is one entry in `videos/channels.toml` plus a folder of videos.
- The laptop is used only to add videos. Everything after upload runs on Modal (ADR-9).

Out of scope: publishing through the platform APIs (step B), views and analytics, and saving post links.

## 2. Flow

```
laptop: videos/<channel>/*.mp4 ──clipforge clip──► upload + POST /jobs (JobInput.channel) ──► exit
Modal:  job chain … package_step ──► enqueue clips (post:<job>:<clip>)
        posting_tick (cron */5) ──claim slot──► pick next clip ──► Telegram: video + captions + buttons
phone:  save video → post in each app → tap ✅ TikTok / ✅ Instagram / ✅ YouTube (or ⏭ / 🗑)
        webhook ──► post:<job>:<clip>:posted:<platform> …   /status /next /pause /go
```

## 3. Channels and batch submit (ADR-22)

- One folder per channel: `videos/<slug>/`. `videos/channels.toml` sets each channel's `name` (the credit), an optional `url` and a `permission` (`own | creator_agreement | clipping_program | cc_by`). Slugs match `[a-z0-9][a-z0-9-]{0,39}` and can't be `out` or `schedule`. Subfolders not listed there are skipped with a warning.
- New contract field: `JobInput.channel: ChannelRef | None`, where `ChannelRef = {slug, name}`. `clipforge clip` fills it in, together with `source_credit = name`, `permission` (unless `--perm` is given) and `source_label = <video stem>`.
- `clipforge clip` uploads and submits every new video and then **exits**. `--fetch` keeps the old behavior: wait for all the jobs together and download the clips into `videos/out/<channel>/<stem>/`.
- The inbox ledger (`videos/.clipforge.json`) keys videos by relative path (`billy-garton/ep01.mp4`) and stores `{job_id, status}`. The old `{name: job_id}` format loads as `done`.
- Loose videos directly in `videos/` still work, with no channel. They are never queued for posting.

## 4. Queue state (ADR-23)

Modal Dict, one writer per key (ADR-14). `<c>` is `<job_id>:<clip_id>`.

| Key | Writer | Value |
|---|---|---|
| `post:<c>` | enqueue (package step or rebuild), set once | `PostItem`: channel slug and name, job_id, clip_id, source_hash, start, end, score, title, hook, video path, `queued_at`, and the episode's `finished_at` |
| `post:<c>:sent:<n>` | slot tick or `/next`, set once | `{at, slot, message_id}`. `n` counts sends: 1, then 2 after a skip, and so on |
| `post:<c>:posted:<platform>` | webhook | `{at}`. Deleting it undoes the tap. Platforms: `tiktok`, `instagram`, `youtube` |
| `post:<c>:verdict` | webhook | `{kind: skipped \| rejected, at, reason?}`. Reasons: `boring`, `bad_cut`, `bad_crop`, `captions`, `other` |
| `post:<c>:unavailable` | slot tick, set once | the video is missing from the Volume |
| `posting:slot:<iso>` | slot tick, claim | set if absent. Released when sending fails |
| `posting:paused` | webhook (`/pause`, `/go`) | present means paused |
| `posting:reminded:<iso>` | slot tick, claim | one reminder per pause episode |

A clip's status is derived, never stored:
- **rejected**: the verdict is `rejected`.
- **unavailable**: the `unavailable` key exists.
- **posted**: all three `posted:*` keys exist. **partly posted**: one or two exist.
- **sent**: its newest send is later than any `skipped` verdict and it has no `posted:*` key. It's waiting for you.
- **skipped**: the verdict is `skipped` and later than the newest send. It can be sent again 24 h after the skip.
- **queued**: never sent.

### 4a. Dict expiry (ADR-24, added 2026-09-29)

Modal Dict entries expire after 7 days without reads or writes. A daily cron, `posting_keepalive`, reads every `post:*` and `job:*` key (and `posting:paused`) one by one and writes a snapshot of all `post:*` keys to `/jobs/posting/snapshots/<date>.json` (the last 14 are kept). `POST /posting/restore` (bearer token; `clipforge status --restore`) puts back only the keys that are missing, from the newest snapshot.

**Enqueue** runs at the end of `package_step`, only for jobs with `channel`, wrapped like the notifier (never fails or retries a step). For each rendered clip:
- It skips the clip if a non-rejected `post:*` item from the same `source_hash` overlaps it with IoU > 0.5, so re-cuts never duplicate a moment.
- Otherwise it creates `post:<c>` with set-if-absent.

`POST /posting/rebuild` (bearer token, also `clipforge status --rebuild`) runs enqueue for every finished channel job. It's idempotent.

## 5. Picking the next clip

The candidates are **queued** clips, plus **skipped** clips whose skip is at least 24 h old. Among them:
1. Prefer a different `source_hash` than the last sent clip, and a different channel. The channel rule gives way first, then the video rule.
2. Take the highest priority: `score + 0.05` if the episode finished within 7 days, otherwise `score`. Ties break on job_id, then clip start.

## 6. Slot tick

`posting_tick` is a Modal cron running `*/5 * * * *` (CPU, timeout 120 s). On each tick:
1. If paused, stop. Find the latest configured slot at or before now, in `POSTING_TIMEZONE`. If it's more than 30 minutes old, stop: missed slots are dropped.
2. **Pause rule:** if at least 2 clips are **sent** with no taps at all, send nothing. If `posting:reminded:<slot of the oldest unanswered send>` can be claimed, send one reminder, "2 clips are waiting: post them or tap Skip", and stop.
3. Claim `posting:slot:<iso>`. If the claim fails, another tick has this slot, so stop.
4. Pick the next clip (§5). If there is none, stop. Keep the claim, and the queue shows as empty in `/status`.
5. If the video is missing, set `unavailable` and pick again (at most 3 times per tick), keeping the slot claim.
6. Send it (§7): the video, then the text with the buttons, as one unit. If either send fails, delete whatever part was delivered (`deleteMessage`), release the slot claim and log it; the next tick retries inside the 30-minute window. Only when both succeed, write `sent:<n>` with the text message id.

`/next` runs steps 4–6 without a slot claim. It ignores the pause rule, because you asked for a clip.

## 7. Message

- **The video:** `send_video` of the rendered clip (under 50 MB by construction). Its caption is `<channel name> · <episode label> · <score> · <n queued> queued`.
- **The text** (HTML parse mode), replying to the video: a title line, then one `<pre>` block each for TikTok, Instagram, YouTube title and YouTube description. The captions follow these rules:
  - **TikTok:** hook, `🎙️ <credit>`, hashtags. At most 2,200 characters.
  - **Instagram:** title, hook, credit, the first 5 hashtags. At most 2,200 characters.
  - **YouTube title:** the title with `<` and `>` removed, plus ` #shorts`. At most 100 characters.
  - **YouTube description:** hook, credit, hashtags. At most 5,000 characters.
  - HTML is escaped.
- **The buttons** (inline keyboard on the text message):
  - Row 1: `✅ TikTok` `✅ Instagram` `✅ YouTube`. Once confirmed, a button reads `TikTok ✓`.
  - Row 2: `⏭ Skip` `🗑 Reject`.
  - After a reject: `Boring` `Bad cut` `Bad crop` `Captions` `Other`.
  - When all three are posted, the keyboard is replaced by "Posted everywhere ✓".
  - Callback data is `p:<action>:<job_id>:<clip_id>` (at most 64 bytes). `job_id` passes `jobs.is_job_id`, and `clip_id` matches `clip_\d{2}`.
- Settings (in `config.py`, with defaults): `POSTING_CHAT_ID` (required to enable posting; must be in `TELEGRAM_ALLOWED_USER_IDS`), `POSTING_TIMEZONE=America/New_York`, `POSTING_SLOTS=08:00,10:30,13:00,16:00,19:00,21:30`, `POSTING_HASHTAGS=` (empty). Without `POSTING_CHAT_ID`, the tick does nothing and `/status` says posting is off.

## 8. Webhook

The webhook handles `callback_query` updates next to messages, reusing the secret-token check, the allowed-users check and the `claim_update` dedupe. It only acts in `POSTING_CHAT_ID`. After each tap it calls `answerCallbackQuery` and then edits the keyboard to match the new state.

| Action | Effect |
|---|---|
| `tt` / `ig` / `yt` | Toggle `posted:<platform>` (create if missing, delete if present). |
| `skip` | Verdict `skipped`, then send the next clip right away (like `/next`). |
| `rej` | Verdict `rejected`, then show the reason row. |
| `why:<reason>` | Add the reason to the `rejected` verdict. |
| a tap on a missing item | Answer "That clip isn't in the queue any more" and change nothing. |

Commands: `/status` with no argument shows the posting overview (§9); `/status <job_id>` is unchanged. Also `/next`, `/pause` and `/go`. The existing `/clip` and `/resume <job_id>` stay.

## 9. Overview (`GET /posting`, `/status`, `clipforge status`)

`service.posting_overview()` returns a `PostingOverview`. For each channel: episodes clipped, clipping and failed (from channel jobs), and clips posted, partly posted, sent, queued, skipped, rejected and unavailable. For the whole queue: clips waiting, about how many days that is at the configured slots per day, the next slot, and whether posting is paused. The bot and the CLI render the same model. `GET /posting` needs the bearer token.

## 10. Errors

- Enqueue and send failures never fail a pipeline step, and are logged.
- A clip is `sent` only after Telegram accepts both the video and the text with buttons. A half-delivered send is deleted and retried (§6), so you never get a clip without buttons.
- Telegram errors are logged without tokens (rule 8).
- `unavailable` clips are listed in `/status` with their episode, so the owner can re-cut it. A re-cut's clip covering the same moment is queued (unavailable and rejected clips don't block a moment).
- Added in review (2026-09-29): a posting setting mistake turns posting off with the reason shown in `/status`, never the app; `8:00` and `#tag` are normalized. Rebuild skips a broken job and continues. Clips are queued before the job is saved as done. Send numbers are `max(n) + 1`. Caption blocks are cut by their HTML-escaped length.

## 11. Testing

Fast tests only; Telegram and Modal are faked.
- Queue functions over `MemoryKV`: derived states, enqueue with re-cut overlap, the pick order, the 24 h skip return, and the pause rule.
- The tick with an injected clock: one send per slot, even from duplicate ticks; missed slots dropped; a DST-change date; claims released on send failure; `unavailable` handling.
- The webhook with fake `callback_query` updates: toggle and undo, skip sends the next clip, reject with a reason, a stale message, a disallowed user, a duplicate `update_id`.
- End to end on `tests/pipeline/harness`: a channel job finishes, its clips are queued, a tick sends one, taps mark it posted, and the overview counts it.
- `TelegramSender` gains `send_message(..., buttons, html)` (returning the message id), `send_video` returning the message id, `edit_buttons`, `answer_callback` and `delete_message`. The fakes implement them, including a failure mode for the half-delivered send.

## 12. Build order (one roadmap item and checkpoint each)

1. **Channels and batch submit** (ADR-22): `channels.toml`, `JobInput.channel`, submit-all-and-exit, the ledger with status, `--fetch`.
2. **Posting queue core** (ADR-23): `PostItem` and the state keys, enqueue in `package_step`, rebuild, pick order, `posting_overview`, `GET /posting`, `clipforge status` with no argument.
3. **Telegram posting assistant:** the posting settings, `posting_tick` cron, the message and buttons, callback handling, the pause rule, and `/status`, `/next`, `/pause`, `/go`.
4. **Expiry keep-alive and snapshot** (ADR-24): the `posting_keepalive` cron, snapshots on the Volume, and restore.

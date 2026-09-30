# videos/

One folder per channel, described in `channels.toml`:

```
videos/
  channels.toml
  billy-garton/ep01.mp4 ep02.mp4 ...
```

```toml
# channels.toml
[billy-garton]
name = "Billy Garton Jr."                # the credit on every clip
url = "https://www.youtube.com/@..."     # optional
permission = "creator_agreement"         # own | creator_agreement | clipping_program | cc_by
```

```bash
uv run clipforge clip                    # submit every new video in every channel, then exit
uv run clipforge clip --fetch            # ...and wait, then download the clips into out/
uv run clipforge clip "videos/billy-garton/ep01.mp4" --again   # re-cut one
uv run clipforge clip --min-score 0.85   # stricter; or --n 10 for a fixed count
uv run clipforge clip --len 20-45        # other options: --len --lang --perm
```

Videos directly in `videos/` still work, without a channel (they aren't queued for posting). A subfolder that isn't in `channels.toml` is skipped with a warning; `out/` and `schedule/` are never inputs.

By default the number of clips is automatic: every candidate the AI scored 0.80 or higher, at most 30.

Each video is uploaded to the Modal Volume (`uploads/<hash>-<name>`) and clipped on Modal. With `--fetch`, the clips are downloaded into `videos/out/<channel>/<episode>/` (loose videos: `videos/out/<episode>/`), with `-2`, `-3`... for re-cuts:

```
videos/out/billy-garton/ep01/
  clip_01_score0.91/video.mp4  captions.srt  post.md
  metadata.json                # scores, timings, cost
```

`videos/.clipforge.json` records each submitted video (by path, e.g. `billy-garton/ep01.mp4`), its job id and whether its clips were fetched, so re-running `clipforge clip` only takes new ones and `--fetch` picks up jobs that finished later. Everything in this folder except this README is ignored by git.

## Posting from your phone

Once `POSTING_CHAT_ID` (your Telegram user id) is in the `clipforge-secrets` Modal secret and you've run `uv run clipforge set-webhook` after deploying, every finished channel video's clips join the posting queue. At each slot (default 08:00, 10:30, 13:00, 16:00, 19:00, 21:30 New York time) the bot sends you the next clip and its captions:

1. Save the video, post it in TikTok, Instagram and YouTube, pasting each caption block.
2. Tap ✅ TikTok / ✅ Instagram / ✅ YouTube as you go (tap again to undo).
3. Or tap ⏭ Skip (it comes back tomorrow) or 🗑 Reject (never; pick a reason if you like).

`/status` shows each channel's progress and how many days the queue lasts. `/next` sends a clip now. `/pause` and `/go` stop and restart the slots. After 2 clips without a tap, the bot waits for you and reminds you once.

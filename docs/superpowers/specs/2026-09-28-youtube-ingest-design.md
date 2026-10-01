> **Deferred (ADR-17).** Not built: the spike worked but the proxy costs too much for now (section 9). ADR-10 stays in force, and ROADMAP "Later / ideas" says how to revisit it.

# YouTube ingest through a residential proxy

Date: 2026-09-28 · Status: Approved, then **deferred** after the spike (see section 9 and ADR-17) · ADR: 17

## 1. Goal and constraints

**Outcome.** A YouTube link, sent to the bot (`/clip <link>` or just the link) or to `clipforge run --input`, produces clips exactly like a direct media link does today.

**Decided during brainstorming (2026-09-28)**

| Topic | Decision |
|---|---|
| How to get past YouTube's block on Modal IPs | yt-dlp running on Modal, with **only the YouTube traffic** routed through a residential proxy (option A). Managed download APIs (B) were rejected as less stable, and account cookies (C) were already rejected in ADR-10. |
| Provider | Decodo (formerly Smartproxy), residential. The code only needs one proxy URL, so switching providers is a config change. |
| Quality | Best video up to **1080p**. At 720p the 9:16 crop is upscaled about 2.7x and looks soft. |
| Everything after the download | Unchanged: ingest normalize, the limits, the step chain, delivery |

**Constraints**
- Stage code stays Modal-free (CLAUDE.md rule 1). No secrets in code or logs (rule 8). The proxy URL contains the Decodo username and password.
- Permission is the owner's guarantee, as for every input (`permission` field). YouTube's terms forbid downloading outside YouTube's own apps whatever the method. The owner accepts that trade-off, and ADR-17 records it. This is unrelated to rule 9, which forbids evading copyright detection; this feature does not.
- Cost is logged (rule 7). Typical proxy spend is about 300–500 MB per 30-minute 1080p video, roughly $1–3 at Decodo's pay-as-you-go rates. Enter the exact rate in `Prices` from the account.

**Success criteria**
- The spike (section 5) passes.
- A 30-minute YouTube video completes as a job with the proxy cost shown in `metadata.json` and the bot's done message.
- Private, removed, members-only, age-restricted and live videos get a clear one-line reason, with no retries wasted.

## 2. Components

| Unit | Location | Change |
|---|---|---|
| YouTube source | `stages/youtube.py` (new, Modal-free) | `youtube_id(url) -> str \| None`; `VideoInfo` (id, title, duration_s, is_live, filesize_approx); `YouTubeFetcher` protocol (`info(url)`, `download(url, out_dir) -> Downloaded`); `YtDlpFetcher(proxy_url, max_height=1080)`; `classify(error_text) -> transient \| PermanentError` |
| Ingest | `stages/ingest.py` | `_source_id` → `youtube:<id>` for YouTube URLs; `_fetch` routes YouTube URLs to the fetcher; `IngestDeps` gains `youtube: YouTubeFetcher \| None`; `STAGE_VERSION` bump is not needed (non-YouTube keys are unchanged) |
| Runner | `stages/runner.py` | Builds `YtDlpFetcher` when `YOUTUBE_PROXY_URL` is set |
| Contracts | `models.py` | `StageCost.proxy_bytes: int = 0` |
| Config | `config.py`, `.env.example` | `youtube_proxy_url: SecretStr \| None`; `Prices.proxy_per_gb: float` |
| Image | `app.py` | `yt-dlp` comes in through `uv.lock`; Deno is added if the spike shows yt-dlp needs a JS runtime |
| Docs | ADR-17, ARCHITECTURE "Inputs", README, ROADMAP ("Later" item moves into Phase 1 as a new line) | |

**Download flow in `_fetch` for a YouTube URL**
1. There's no proxy configured → `PermanentError("YouTube links need YOUTUBE_PROXY_URL (see ADR-17)")`.
2. `info(url)` fetches metadata only, through the proxy.
   - A live stream is rejected: "live streams can't be clipped; send the link once the stream has ended".
   - A video longer than `max_source_duration_s` is rejected with the existing "too long" message.
   - An approximate size over `max_source_bytes` is rejected.
   - These checks come before any media bytes are paid for.
3. `download(url, out_dir)` downloads with this format selector: `bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]`. The streams are merged into mp4, which needs the ffmpeg already in the image.
   - Progress hooks call `ctx.report(INGEST, 5–40, "downloading")`.
   - It returns the path, the title, and the bytes read through the proxy.
4. The existing `_normalize` runs on the file. The download is H.264 + AAC, so it's a stream copy. `SourceMedia.title` is taken from yt-dlp, and `SourceMedia.source_url` is set to `https://www.youtube.com/watch?v=<id>`.
5. `record_cost(StageCost(stage=INGEST, wall_s=…, proxy_bytes=n, usd_estimate=prices.proxy_usd(n)))`.

**URL recognition.**
- Hosts: `youtube.com`, `www.youtube.com`, `m.youtube.com`, `music.youtube.com` and `youtu.be`, as exact host matches, never suffixes, so `youtube.com.evil.io` is refused.
- Paths: `/watch?v=<id>`, `/shorts/<id>`, `/live/<id>`, `/embed/<id>` and `youtu.be/<id>`.
- A valid id matches `[A-Za-z0-9_-]{11}`.
- Anything else on a YouTube host (channels, playlists) → `PermanentError("send a link to a single YouTube video")`.

**Why the SSRF guard doesn't apply.** yt-dlp only receives URLs whose host is on the fixed YouTube list above, and its connections leave through the proxy. The direct-link path keeps its guard unchanged.

## 3. Errors and secrets

**Sorting yt-dlp errors** (`classify`, matched on the error text):

| Match (case-insensitive) | Class | User message |
|---|---|---|
| "confirm you're not a bot", "HTTP Error 429", "proxy", "timed out", "Connection reset", "Unable to download webpage" | transient: raise, and Modal retries with a fresh residential IP | after the last attempt: "YouTube blocked the download; try again later" |
| "Private video" | permanent | "this YouTube video is private" |
| "Video unavailable", "has been removed", "This video is not available" | permanent | "this YouTube video is unavailable" |
| "members-only", "Join this channel" | permanent | "this YouTube video is for channel members only" |
| "confirm your age", "age-restricted" | permanent | "this YouTube video is age-restricted" |
| anything else | transient (so an unknown error gets the normal 3 attempts) | "YouTube download failed (<ExceptionType>)" |

**Secrets.**
- yt-dlp runs with `quiet=True`, `no_warnings=True`, and a logger that drops everything.
- Our exceptions are rebuilt from the category and never carry yt-dlp's text.
- The proxy URL is a `SecretStr` until the one line that builds the yt-dlp options.
- Every raised message is also passed through `pipeline.steps.sanitize`, which already strips `user:pass@` and query strings from URLs.

## 4. Cost

- `Prices.proxy_per_gb` has a default taken from Decodo's pay-as-you-go residential rate at signup. It's in `config.py`, where the owner updates it.
- `proxy_bytes` comes from yt-dlp's `downloaded_bytes` across all formats, plus a flat allowance for the metadata request.
- The total flows through the existing `usd_estimate`, so `metadata.json`, `JobView.cost` and the bot's done message include it without other changes.
- Cached re-runs of the same video cost $0 for ingest, because the cache key is `youtube:<id>`.

## 5. Spike (step 0, throwaway)

**Setup.** The owner creates a Decodo residential pay-as-you-go account and puts `YOUTUBE_PROXY_URL=http://user:pass@gate.decodo.com:7000` in `.env`. Claude adds it to `clipforge-secrets` without printing it.

**Probe.** A throwaway Modal function uses `base_image` plus yt-dlp, and Deno if needed. It runs in 3 separate containers. Each one:
- gets metadata, then downloads one owner-chosen video with the real selector: a short one, a ~10-minute one and a ~30-minute one;
- reports success, bytes, wall time, and yt-dlp's warnings about JS runtimes.

**Pass.** 3 of 3 succeed, and the 30-minute video downloads in under 3 minutes.

**Fail.** Stop, write down what failed, and revisit option B before any production code. The probe code is deleted either way.

## 6. Testing

**Fast (no network, no proxy):**
- `youtube_id`: every URL form maps to the same id; look-alike hosts, channel URLs, playlists and bad ids are refused.
- Ingest routing, using a fake `YouTubeFetcher` that "downloads" the talking-head fixture:
  - a YouTube URL uses the fetcher, and a direct URL uses httpx;
  - no proxy configured → the clear PermanentError;
  - the cache key is the same for `youtu.be/<id>` and `watch?v=<id>&si=x`.
- Metadata checks: too long, too big and live are rejected, and `download` is never called.
- `classify`: each canned error string maps to the expected class and message. No message contains a fake proxy's `user:pass`.
- Cost: `proxy_bytes` and its USD are recorded on the ingest `StageCost`.
- The bot and CLI accept YouTube links. The CLI's `http(s)` check already passes them, and the bot needs no change. Add one test each so it stays that way.

**Slow** (`@pytest.mark.slow`, skipped without `YOUTUBE_PROXY_URL`): `YtDlpFetcher.info()` on one short public video.

**Manual:** `modal run app.py::smoke --youtube <url>` runs one real YouTube job with `n=1` and `len=15-60`, and checks it with `check_smoke` against that requested range (`check_smoke` takes the range as arguments instead of the fixture constants). Pick a short video you have permission for: a few cents of proxy traffic. It is never run by CI (ADR-16).

## 7. Risks

| Risk | Mitigation |
|---|---|
| YouTube changes break yt-dlp | Pin a recent version. The fix is `uv lock --upgrade-package yt-dlp` plus a deploy. The "YouTube download failed" message says to update. |
| A residential IP still gets a bot check | The error is transient, so each retry goes out on a fresh IP. After 3 attempts the job fails with a clear message. |
| Proxy spend creeps up | Logged per job and shown in the done message. The Decodo balance is a hard cap. The metadata-first checks avoid paying for rejected videos. |
| Proxy credentials leak | yt-dlp is silenced, messages are rebuilt, `sanitize` strips userinfo, and a test asserts nothing leaks. |
| YouTube's terms | The owner accepts the trade-off (ADR-17), and permission remains the owner's guarantee. |

## 8. Out of scope

- Playlists, channels and live streams.
- TikTok and Instagram links: yt-dlp supports them, but each needs its own spike.
- Choosing the resolution per job; 1080p is fixed for now.
- Subtitles from YouTube: we transcribe ourselves.

## 9. Spike results (2026-09-28) and why this is deferred

**Setup.** One video (84 min), yt-dlp 2026.8.19 plus Deno on a Modal container, going out through Decodo's residential proxy on sticky port 10001.

**What worked**
- Metadata: title, duration and live flag in 3.7 s, with no bot check.
- The sticky exit IP stayed the same across requests.
- Two yt-dlp clients downloaded the test at 1080p: `web_safari` and `web_embedded`.

**What didn't**
- The default client got HTTP 403 on the media.
- `tv` failed with "page needs to be reloaded".
- `tv_simply`, `mweb` and `android_vr` topped out at 360p.
- The 100 MB trial allowance ran out before the full download. After that, Decodo answered 407 for every request.

**Cost.** At Decodo's pay-as-you-go price ($11 per 3 GB, about $3.70/GB):
- a full 1080p download is about $3 per 30 minutes of video;
- the 84-minute test video would be about $5.

That's too much for the current use of about one video a day, which is easier to feed as a direct link or file.

**Free downloader sites.** Rejected. They have no stable API. The official cobalt server has dropped YouTube and requires a captcha token, and its community instance directory no longer resolves.

**If this is picked up again**
1. **Download only what the pipeline uses.** Ingest takes the audio-only stream (about 1 MB/min), and each clip step fetches only its own 1080p time range. That's about 130 MB per 30 minutes of video, roughly $0.50. This changes the pipeline (clip steps fetch their own video), so it needs a revised spec.
2. **A flat-price static ISP proxy** (about $2–5 per month) instead of pay-per-GB. Needs its own test that YouTube accepts the IP.
3. **Keep from this spike:**
   - pin the client order to `web_safari`, then `web_embedded`, and treat a 360p-only result as a failure;
   - use a sticky port so the metadata request and the download share an IP.

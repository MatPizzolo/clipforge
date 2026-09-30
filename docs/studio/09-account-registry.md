# 09: Account registry

The single list of **what exists or is planned**: every content category and every account, with the ids the code uses. [07](07-channel-portfolio.md) explains **why** each concept exists (niche, money, risks). This file says **what** each account is.

- **Until S3:** this file plus the `blueprints/` files are the source of truth.
- **After S3:** the database is the source of truth, and this file mirrors it (the dashboard's Accounts page lists the same rows).
- **Rule:** an account is created here first (status `idea`), then gets a blueprint, then `clipforge account create`. Update this file in the same session that changes an account.

Last updated: 2026-09-29.

## 1. Categories (content types)

The code name is the `kind` of an `Account` and the `category` of a `Blueprint` (models.py, S1).

| Code | Category | Producer (roadmap item) | What a video is | How it earns | Must have (policy gate) | Decisions |
|---|---|---|---|---|---|---|
| `clips` | Podcast clips | existing pipeline (S0–S1) | 30–60 s cut from a permitted long video | Paid clipping (creator deals, Whop campaigns), affiliate links, brand deals; platform payouts are a bonus | Creator credit in every caption; source permission recorded | ADR-22, 23, 25 |
| `story` | AI narrated stories | story producer (S6) | 61–90 s narrated original script, stills and b-roll, music bed | TikTok Creator Rewards, Facebook (invite-only), YouTube long-form later | Fact sources stored; AI flag on; varied structure (inauthentic-content rule) | ADR-30, 31, 35 |
| `band` | Music / band discovery | band producer (S9) | Narrated band story over Commons/permitted photos or generated **art**; music-free master with a suggested sound | Curator fees, disclosed paid features, gear affiliate | License for every asset; no photoreal images of real people; paid features disclosed | ADR-30, 35 |
| `avatar` | AI-avatar affiliate | avatar producer (S8) | A disclosed synthetic presenter (hook and CTA) plus b-roll | Affiliate commission through tracked links (TikTok Shop, Skool, Hotmart, SaaS) | AI label; #ad; no first-person product claims; no health, finance or earnings claims | ADR-29, 30, 33, 39 |
| `model` | AI model / influencer | persona + carousel producer (S13) | Carousels and short reels of a disclosed synthetic persona | Brand deals, affiliate storefronts, disclosed sponsored posts | "AI creator" in bio; AI labels; provenance metadata kept; synthetic-only training data; no swaps onto real people; no sexual content; no health or diet claims | ADR-39 |

Rules for every category (01, "Content rules"):
- Every video goes to **every platform the account has enabled**. The primary platform only shapes the format.
- One video, one account. The same video never goes to two accounts in the same language; translations for the paired account are allowed.
- Licenses are tracked per asset. No copyright-evasion features (CLAUDE.md rule 9).

## 2. Accounts

Status: `live` (posting), `planned` (in the next wave, needs sign-ups), `idea` (concept only).
- **Ids** follow S1's rule `<blueprint>-<lang>`. They never change; handles can.
- **Handles** other than realtalk.clipsdaily are ideas: check availability on all four platforms before `account create`.

Platforms: TT = TikTok, IG = Instagram Reels, YT = YouTube Shorts, FB = Facebook Reels.

| # | Account id | Handle | Lang | Code | Blueprint | Primary | Enabled | Money | Sources / permission | Pair | Wave | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `realtalk-clips-en` | realtalk.clipsdaily | en | clips | `realtalk-clips` | TT | all four | Creator deal, CRP, Skool affiliate | Billy Garton Jr. (`creator_agreement`) | — | 1 | **live** (assisted posting since 2026-09-29) |
| 2 | `founder-tapes-en` | founder.tapes | en | clips | `founder-tapes` | TT | all four | Whop business and finance campaigns, CRP | none yet: Whop campaigns or a creator agreement | — | 1 | planned |
| 3 | `hombre-en-construccion-es` | hombre.en.construccion | es | clips | `hombre-en-construccion` | TT | all four | CRP (US and MX only), retainers from Spanish-language hosts | none yet: Spanish-language podcast agreements | — | 1 | planned |
| 4 | `untold-archive-en` | untold.archive | en | story | `untold-archive` | TT | all four | CRP, YouTube long-form later | original scripts, sources stored | #5 | 2 | idea |
| 5 | `untold-archive-es` | historias.ocultas | es | story | `untold-archive` | TT | all four | CRP (MX, US Hispanic) | original scripts, sources stored | #4 | 2 | idea |
| 6 | `money-autopsy-en` | money.autopsy | en | story | `money-autopsy` | TT | all four | CRP at finance rates, newsletter or Hotmart later | original scripts, sources stored; stories, never advice | #7 | 5 | idea |
| 7 | `money-autopsy-es` | dinero.en.ruinas | es | story | `money-autopsy` | TT | all four | CRP (MX, US Hispanic) | as #6 | #6 | 5 | idea |
| 8 | `mind-explained-en` | mind.explained | en | story | `mind-explained` | TT | all four | CRP, book affiliate | studies cited; no therapy claims | #9 | 5 | idea |
| 9 | `mind-explained-es` | (to choose) | es | story | `mind-explained` | TT | all four | CRP (MX, US Hispanic) | as #8 | #8 | later | idea |
| 10 | `neverheard-from-en` | neverheard.from | en | band | `neverheard-from` | TT | all four | Curator fees, disclosed features, gear affiliate | Commons (CC-BY/BY-SA) or band permission | — | 4 | idea |
| 11 | `heavy-atlas-en` | heavy.atlas | en | band | `heavy-atlas` | TT | all four | as #10 | as #10 | — | 5 | idea |
| 12 | `radar-indie-latino-es` | radar.indie.latino | es | band | `radar-indie-latino` | IG | all four | as #10 | as #10 | — | 4 | idea |
| 13 | `kitchen-finds-en` | kitchen.finds | en | avatar | `kitchen-finds` | TT (Shop) | all four | TikTok Shop 15–20%, Amazon 4.5% | seller or brand footage with permission | #14 | 5 | idea |
| 14 | `kitchen-finds-es` | cocina.finds | es | avatar | `kitchen-finds` | TT (Shop) | all four | as #13 (US Hispanic) | as #13 | #13 | 5 | idea |
| 15 | `ai-tools-lab-en` | ai.tools.lab | en | avatar | `ai-tools-lab` | TT | all four | Recurring SaaS affiliates, Skool 40% | vendor footage or own screen recordings | — | 3 | idea |
| 16 | `profe-ia-ingles-es` | profe.ia.ingles | es | avatar | `profe-ia-ingles` | TT | all four | Babbel/Preply, Hotmart courses, own Skool later | original lessons | — | 3 | idea |
| 17 | `persona-travel-en` | (name).travels | en | model | `persona-travel` | IG | IG TT (+YT FB) | Brand deals (hotels, travel gear), affiliate | synthetic persona only | — | 6 | idea |
| 18 | `persona-fashion-es` | estilo.(name) | es | model | `persona-fashion` | IG | IG TT (+YT FB) | Fashion storefronts, disclosed sponsored outfits | synthetic persona only | — | 6 | idea |
| 19 | `persona-fitness-en` | (name).moves | en | model | `persona-fitness` | IG | IG TT (+YT FB) | Activewear deals, affiliate | synthetic persona only; no health or diet claims | — | 6 | idea |

Totals: 19 accounts in 5 categories (3 clips, 6 story, 3 band, 4 avatar, 3 model). All fit Upload-Post's Professional plan (25 profiles).

## 3. Launch waves

| Wave | Roadmap | Accounts | What must exist first |
|---|---|---|---|
| 1 | S0 → S1 → S2 | #1 (live), #2, #3 | S1 accounts; sources with permission; S2 publishing for auto-posting |
| 2 | S6 | #4, #5 | S4 Timeline, S5 media servers, X1 voice, S6 story producer |
| 3 | S8 | #15, #16 | X2 talking head, X3 persona, S8 avatar producer, tracking links |
| 4 | S9 | #10, #12 | S9 band producer, license records |
| 5 | as capacity and budget allow | #6, #7, #8, #11, #13, #14 | revenue covers the ~$215–245/month full-scale cost (03, measured voice cost from X1) |
| 6 | S13 | one of #17–#19 first | S13 persona and carousel producer |
| later | — | #9 | #8 proves the format |

## 4. Open account decisions

| # | Question | Options | Recommendation |
|---|---|---|---|
| A1 | Which platforms do the wave-1 clip accounts enable? | (a) primaries only; (b) all four, per 01's rule | **Decided 2026-09-29: (b) all four** (10 #52). The S1 blueprints enable TikTok, Instagram, YouTube and Facebook; the primary stays TikTok |
| A2 | Handles for #2 and #3 | the 07 ideas, or alternatives | Check availability on all four platforms, then record the final handle here |
| A3 | Series formats for the three clip blueprints | S1's drafts (marked `# draft: owner edits`) | Rewrite after a week of posting shows which pillars work |
| A4 | Persona names for #17–#19 | — | Decide in S13 |

## 5. How to add an account

1. Add a row here with status `idea`, an id `<blueprint>-<lang>` and a handle idea.
2. Check the handle on TikTok, Instagram, YouTube and Facebook. Record the final handle.
3. Write or reuse the blueprint in `blueprints/<name>.toml` (07 has the concept).
4. Record source permissions (clips) or content rules (other categories).
5. Launch with prompt E in [06](06-session-prompts.md): `clipforge account create`, persona job, platform connection in Upload-Post, warm-up, first batch in `review` tier.
6. Set the status to `planned`, then `live` once it posts. Add the launch to the decision log ([10](10-decision-log.md)).

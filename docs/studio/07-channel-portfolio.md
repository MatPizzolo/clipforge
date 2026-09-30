# 07: Channel portfolio and how it scales

Five categories, 15 concepts, about 19 accounts with the Spanish pairs. This file explains **why** each concept exists. The list of accounts with their ids, handles, platforms and status is [09-account-registry.md](09-account-registry.md).

**Story script structure** (all story blueprints):
- the hook (conflict, number, open question) in the **first 3–5 s**, never "welcome back";
- a curiosity loop about every 20–30 s in shorts (every ~45 s in long-form);
- each beat leads into the next.

Story accounts add **long-form YouTube mini-documentaries (8–15 min)** once in YPP. That's where the $10–25 long-form RPMs in finance, business and tech apply; Shorts RPMs are ~100× lower.

Research date: 2026-09-29.
- Rates come from third-party ranges. Replace them with our own dashboard numbers after 30 days.
- Handles are **ideas**. Check availability on all four platforms before creating an account.

## Scaling model: category → blueprint → account → series

We don't design a channel from scratch each time. We **instantiate a blueprint**:

```
Category   clips | story | band | avatar          → producer + compliance profile (code)
Blueprint  e.g. untold-archive                   → niche, pillars, series formats, voice/visual
                                                   style brief, platform defaults, money sources
                                                   (versioned file: blueprints/<name>.toml + prompts)
Account    blueprint + language + persona + handles + Upload-Post profile + budget + review tier
Series     a recurring format inside an account   → "The day that…", "Part 1/2", "Sounds like X, from Y"
Item       one video (ContentItem)
```

- **New account:**

  ```
  clipforge account create --blueprint untold-archive --lang es --handle historias.ocultas
  ```

  This spawns a `persona` job (designed voice, plus a face for avatar accounts), creates the database rows and a calendar, and starts the account in `review` tier.
- **Series rotation** is the answer to YouTube's July 2026 inauthentic-content rule. Each item varies its series, structure and research, and the variation is logged.
- **EN/ES pairs:** the two accounts share a blueprint, with `paired_account_id` linking them. The Spanish side is a **native adaptation** (local examples, native voice, neutral LatAm Spanish), not a literal translation. The two languages never share one feed.
- **Compliance profile per category**, enforced by the policy gate:

  | Category | Must have |
  |---|---|
  | clips | credit to the creator |
  | story | fact sources stored |
  | band | a license for every asset, disclosure on paid features |
  | avatar | AI label, #ad, no first-person use, no health/finance/legal advice |

## The portfolio (3 per category; 15 concepts → ~19 accounts with ES pairs)

### A. Podcast clips (existing producer, launches first)
Clips earn through **Whop Content Rewards**:
- about **$0.20–6 per 1K views**, around $1.25 on average;
- business and finance campaigns advertise $3–7;
- no follower minimum.

Retainers from hosts run **$500–3,500 a month**. Spanish-language podcasts are underserved: 44% of Spanish-speaking listeners can't find enough shows.

| Account | Lang | Primary | Money | Cadence | Pillars | Risk |
|---|---|---|---|---|---|---|
| **realtalk.clipsdaily** (live) | EN | TikTok | Creator deal, CRP, Skool affiliate | 3–5/day | discipline, dating, money mindset, faith | Low |
| **founder.tapes** | EN | TikTok + Shorts | Whop business/finance campaigns, CRP (business ≈1.22×) | 3–6/day | origin stories, sales tactics, hiring, money lessons | Low–Med (no "buy X") |
| **hombre.en.construccion** | ES | TikTok + FB | CRP (US and MX only; Spain isn't eligible), retainers from Spanish-language hosts | 2–4/day | disciplina, relaciones, dinero, fe | Low |

What each new clip account needs:
- permission for its sources (a campaign's rules or a creator agreement);
- the local `clipforge fetch` helper.

A campaign is a new **source kind** with rules: required tags or links, and a submission deadline. Whop has no API for clippers, so the dashboard keeps a "submit these links" list.

### B. AI narrated stories (story producer)
Durable faceless niches are history, psychology/stoicism and business case studies. All of them need real research in every episode.

| Account (EN / ES) | Primary | Money | Cadence | Pillars | Risk |
|---|---|---|---|---|---|
| **untold.archive / historias.ocultas** | TikTok (CRP), YouTube long-form compilations later | CRP, YouTube long-form | 1–2/day each | unsolved mysteries, lost cities, forgotten inventors, "the day that…" | Low |
| **money.autopsy / dinero.en.ruinas** | TikTok + Shorts | CRP at finance/business rates (~1.2–1.3×), newsletter or Hotmart later | 1/day | company collapses, frauds explained, how X got rich, price-history oddities | Low–Med (stories, **never advice**) |
| **mind.explained** (ES later) | TikTok + IG | CRP, book affiliate | 1/day | cognitive biases, classic experiments, stoic ideas applied | Low–Med (cite studies, no therapy claims, no "dark psychology") |

Scripts run **61–90 s** (the TikTok Rewards minimum is over 1 minute). Each script keeps its sources in the item's metadata.

### C. Music / band discovery (band producer, last because of rights)
Money comes from:
- curator fees: SubmitHub pays ~$1–3 per premium review, Groover pays €1 per review;
- disclosed paid premieres and features ($25 to $10K+ depending on size);
- playlist curation.

TikTok Rewards is weak here because of music audio.

| Account | Lang | Primary | Pillars | Risk |
|---|---|---|---|---|
| **neverheard.from** ("a band you've never heard of from Mongolia") | EN (ES captions) | TikTok + Shorts | one country per video, "sounds like X but from Y", scene history, map series | Med |
| **heavy.atlas** | EN | TikTok + IG | underground metal by country, folk metal, "the scene in <city>" | Med |
| **radar.indie.latino** | ES | TikTok + IG | city scenes (CDMX, Bogotá, Santiago, Madrid), Friday new releases, "si te gusta X…" | Med |

Rules:
- Tracks come from artist submissions or cleared sources, or are added in-app as a platform sound.
- Paid posts are always disclosed. NPR reported in July 2026 on undisclosed paid music promotion.

### D. AI-avatar affiliate (avatar producer)
Commissions:

| Program | Rate |
|---|---|
| TikTok Shop | average 13%, home/beauty 18–20% |
| Amazon home & kitchen | 4.5% |
| **Skool** | **40% recurring** (14-day attribution) |
| **Hotmart** | up to 80% (Spanish-language infoproducts) |
| Babbel | $32–87 one-time |
| Preply | 20% |

**Avoid:** supplements, sleep, and finance "advice" from an AI avatar. It's demonetized on YouTube under the July 2026 rule, and it carries FTC claims risk.

| Account | Lang | Primary | Money | Pillars | Risk |
|---|---|---|---|---|---|
| **kitchen.finds / cocina.finds** | EN / ES (US Hispanic) | TikTok Shop | TikTok Shop 15–20%, Amazon 4.5% | "what it does in 30 s", under-$20 finds, weekly top 5, "3 ways to use" | Low |
| **ai.tools.lab** | EN | TikTok + Shorts + IG | recurring SaaS affiliates, Skool 40% | one tool, one task in 60 s; workflows; tool vs tool | Low |
| **profe.ia.ingles** | ES | TikTok + IG + FB | Babbel/Preply, Hotmart English courses, own Skool later | phrases for work, mistakes Spanish speakers make, US life vocabulary | Low |

Rules:
- The avatar **presents and demonstrates**, using seller or brand footage with permission. **It never says it tested or used a product.**
- The persona is openly AI. For example, "profe IA" is an honest AI tutor persona.

### E. AI model / influencer (persona producer + carousels; added 2026-09-29)
This is a disclosed AI persona in lifestyle niches. Money comes from **brand deals, affiliate storefronts (Amazon, LTK/ShopMy-style) and disclosed sponsored posts.**

Content is **photo carousels plus short reels**, so `ContentItem` gains a media kind: `video | carousel | image`. Upload-Post supports photo posts.

| Account | Lang | Primary | Money | Pillars | Risk |
|---|---|---|---|---|---|
| **<name>.travels** (a synthetic travel/lifestyle persona) | EN | IG + TikTok | brand deals (hotels, travel gear), affiliate | destinations, packing lists, "a day in <city>", budget tips | Med |
| **estilo.<name>** (fashion/outfits) | ES | IG + TikTok | fashion affiliate storefronts, sponsored outfits (disclosed) | outfit of the day, capsule wardrobes, "cómo combinar", trends | Med |
| **<name>.moves** (fitness *lifestyle*, not advice) | EN | IG + TikTok | activewear brand deals, affiliate | workout aesthetics, routines as content, gear, motivation | Med (no health or diet claims) |

**Rules** (a compliance profile in the blueprint, enforced by the gate):
- **Openly AI:** "AI creator" in the bio, platform AI labels on, and **provenance metadata (C2PA/IPTC) kept, never stripped**.
- **Training data is synthetic only:** the persona's own generated images (as in spike X3). **No scraped photos of real people** (Pinterest and so on).
- **No face or body swapping onto real people's videos.** Motion comes from pose-free generation (Wan2.2 or InfiniteTalk-style) or from licensed or self-made motion references.
- **Sponsored content disclosed** (#ad or the platform's paid-partnership tag).
- **Account warm-up is fine** (normal browsing in the niche). **No bought or automated fake engagement.**
- **No sexual content** in this category's scope.

## Launch waves (tied to the roadmap)

| Wave | When | Accounts | Why |
|---|---|---|---|
| 1 | S0 → S3 (clip producer exists) | realtalk.clipsdaily (live), **founder.tapes**, **hombre.en.construccion** | The producer already exists. Whop campaigns pay from day one. A second and third account test the multi-account foundations |
| 2 | S6 (story producer) | **untold.archive + historias.ocultas** | Lowest compliance risk, evergreen, and it tests the EN/ES pair workflow |
| 3 | S8 (avatar producer) | **profe.ia.ingles**, **ai.tools.lab** | Education and tools: honest AI personas and recurring commissions |
| 4 | S9 (band producer) | **neverheard.from**, **radar.indie.latino** | Rights handling comes last |
| 5 | as capacity allows | money.autopsy/dinero.en.ruinas, mind.explained, kitchen.finds/cocina.finds, heavy.atlas | Add winners' formats first |
| 6 | after S13 (AI model producer) | one AI-model persona (travel or fashion) | Reuses persona + LoRA work from S8; adds carousels |

About 19 accounts fit Upload-Post's Professional plan (25 profiles, $50/mo, or $33/mo billed yearly).

## Monetization-market notes
- **TikTok Creator Rewards:** the only Spanish-speaking eligible market is **Mexico** (since 2025-10-01; Spain isn't eligible, checked 2026-09-29), and US Hispanic views count at the US rate. Other Latin American views are reach, not TikTok payout.
- **Facebook Content Monetization:** invitation-only, with no published thresholds, and 2026 originality rules against lightly edited reposts. Treat it as a bonus.
- **YouTube Shorts:** ~$0.01–0.08 per 1K views; finance ~$0.08–0.35. It's for audience and search. The YouTube money comes from long-form compilations once in YPP.

## Sources
- https://www.elev8or.io/blog/tiktok-creator-rewards-rpm-2026 · https://quasa.io/media/tiktok-creator-rewards-program-eligible-countries-in-2026 · https://fluxnote.io/guides/youtube-shorts-niche-selection-income-2026
- https://creatorblade.com/blog/youtube-inauthentic-content-policy-2026-stay-monetized · https://outlierkit.com/blog/youtube-updates-july-2026
- https://openclip.app/guides/whop-clipping-guide · https://ascynd.io/en/blog/best-clipping-niches · https://ascynd.io/en/blog/podcast-clipping-jobs · https://hispanicmarketingfirm.com/latino-podcast-listening-trends-2026/
- https://www.musicpulse.app/blog/is-submithub-still-worth-it-in-2026-an-honest-review · https://groover.co/en/lp/curators/ · https://www.npr.org/2026/07/13/nx-s1-5849926/influencers-paid-music-promotion
- https://www.shortformnation.com/blog/tiktok-shop-affiliate-commission-rates-what-brands-should-offer-2026-data · https://getlasso.co/amazon-affiliate-commission-rate/ · https://www.skool.com/affiliate-program · https://hotmart.com/en/affiliates · https://getlasso.co/niche/language/
- https://thesocialoutline.com/blog/ai-ugc-disclosure-rules

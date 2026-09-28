# Backlog: the single list of pending items

This file is the only list. If it is not here, it is not pending. CoS keeps it current.
- **Owner:** C = Carlos by hand, CoS = CoS alone, Dev = a Cloud Agent PR, GTM, Opus, Radar.
- **Status:** todo, in progress, blocked, parked, decided, live.
- **Priority:** `today` (must be closed today), `now`, `next`, `later`. Anything marked `today` is in the section below and is not repeated.

Updated 2026-09-25.

## Today

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| Cadence decision | today | Opus | todo | GTM, for days 1–3 / 4–7 / 8–14 / steady: TikTok 1, 2, 3, then 4; IG 1, 1, 2, then 3; X 1, 2, 3, then 4. Steady state is 11 unique inputs a day (4+3+4). That is the ceiling. Bluesky is not inside the 11; adding it means dropping posts elsewhere. Do not turn `PUBLISHER_RAMP` off. Knobs that already exist: `PUBLISHER_RAMP_DAYS`, `PUBLISHER_RAMP_START`, `PUBLISHER_SLOTS_<NETWORK>`, `PUBLISHER_CADENCE`. No new knob until this row is closed |

## Networks

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| X via Buffer | now | Dev | in progress | PR #11. Paid API stays off. `PUBLISHER_BRIDGE=buffer` and `x` in `PUBLISHER_LIVE_NETWORKS`. Disconnect LinkedIn in Buffer, connect `@antisearch_ai` (`BUFFER_CHANNEL_X`). No links, replies, or trend posts on X. Mentions: one verified allowlisted account per post, only when it is the verdict, 14 days per account (founder, 2026-09-28; AGENTS.md) |
| LinkedIn | later | Opus | parked | Paused. `PUBLISHER_SLOTS_LINKEDIN=off`. Leave it out of `PUBLISHER_LIVE_NETWORKS`. A new Page stays parked. `docs/proposals/2026-09-25-linkedin-decision.md` |
| Bluesky | now | C → CoS | todo | Needs `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD`. Retire the `u-thing` repost row in `queue/bluesky_trial.csv` first (`thing` is the intro and must not go out again) |
| Reddit | later | — | parked | Paused. No account. Self-promo risk. API is closed to new apps |
| Hacker News | next | CoS | todo | First post is from Carlos's personal account and must be shown to him before it goes up. CoS owes the draft. Still gated on the og fix and the per-call cost |
| Meta app for native IG | next | C | todo | Instagram Login, Standard Access, no App Review; token + IG user ID → secrets |
| DNS TXT on antisearch.ai | next | C | todo | `_atproto` (Bluesky handle), plus Google Search Console and Bing Webmaster verification TXT. Cloudflare, additive |
| Pin and feature the intro | next | GTM | todo | Pin the intro clip (`thing`, `publisher-state` `manual/2026-09-25/`) and feature it where the profile allows a pin |
| TikTok stays on the Buffer bridge | later | — | decided | Native = inbox drafts only. The public audit is out of reach for an own-account tool |
| `PUBLISHER_CRON=live` per network | now | CoS | todo | After credentials exist. LinkedIn stays out. X only after PR #11 is in and the Buffer channel is connected. Cadence waits on the row above |
| Buffer API key | now | C | todo | Free plan, 3 channels: Instagram, TikTok, X. LinkedIn comes off Buffer |
| Public clips repo + Pages + token | now | C | todo | Needed by Instagram native and the Buffer bridge |
| LinkedIn Community Management | later | C | blocked | Needs a registered company, a business email on the domain, and a privacy policy (`docs/legal/`). Not while LinkedIn is paused |

## Trial

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| First 4 clips to Buffer | now | GTM | todo | Frozen verdicts, 2.0s pause, under `publisher-state` `manual/2026-09-25/`. Buffer's API from Actions, not the web UI. `@k18hair` only after `verified: true`. Mark a row `failed` in `posts.csv` if it never went out |
| Surprise-input test (6 rows) | now | CoS | todo | `queue/surprise_trial.csv`; keep/kill rules in `SURPRISING_INPUTS.md` |
| Winner lane on | now | CoS | todo | `PUBLISHER_WINNER_NETWORKS=instagram,tiktok,bluesky`, cap 2/day. Not X |
| Verify winner handles | now | CoS / GTM | todo | `mill winners`. Confirm the badge or the brand site, then `verified: true` in `queue/winners/handles.json`. Never ahead of the verdict |
| Tragedy filter confirmation | now | C | todo | Trend lane only (`publisher/trends.py`). Founder has not confirmed it. Politics stays allowed |
| Early-iteration repost screenshots | next | C | todo | Salesforce, Plaza Hotel, Dyson → `docs/founder-notes/` |
| Lock-screen image | next | GTM | todo | Still open |
| `ceo` → Elon Musk | later | — | decided | Politics is allowed. Tag `@elonmusk` on TikTok or Instagram only after `verified: true`. No LinkedIn or Bluesky handle is confirmed |

## Decisions still open

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| Oracle vendor and per-call cost | next | C | open | Vendor is unknown. Per-call cost and the global cap on `/verdict` gate Show HN and full volume. `docs/COST_PER_VIDEO.md` |
| og image fix | next | C (`SHIP:`) | todo | `<title>` / `og:title` / `twitter:title` → `antisearch.ai`; image = a lone cursor block; `?v=3`. Gates Show HN |
| PR #8 growth ideas | next | C | parked | `docs/proposals/2026-09-25-growth-ideas.md`. Do not merge until Carlos reviews |
| Opus and Radar free channels plan | next | Opus, Radar | todo | Free non-social channels. Not built |
| SEO | later | Opus | parked | Shelved. Plan v0 in the growth-ideas note says not now. Do not rebuild the old tree |
| `?q=` deep link | later | C (`SHIP:`) | parked | `antisearch.ai/?q=thing` prefills the input. After the trial |

## Dev

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| Trend lane | later | Dev | live in code | `publisher/trends.py`. Switch on with `PUBLISHER_TREND_NETWORKS`. X is ignored |
| Reply watcher (Bluesky) | later | Dev | live in code | `publisher/replies.py`. `PUBLISHER_REPLY_NETWORKS=bluesky` after the account exists. No replies on X |
| Winner lane | later | Dev | live in code | `publisher/winners.py`. X is ignored (a winner tag is a mention) |
| Reverse-oracle dry run | later | Dev | todo | First 10 targets below. Sandbox only, ≤10 calls per target, ≤100 total, log in `state/reverse/`. Nothing is published |
| LinkedIn winner tags | later | Dev | parked | Organization mentions need a verified name→URN map. LinkedIn is paused anyway |
| X watcher / replies | later | Dev | parked | No automated replies on X (mentions: AGENTS.md, X rule) |
| `mill record` for manual uploads | later | — | dropped | Buffer uploads go through the API. No web UI |
| Buffer post reconciliation | next | Dev | todo if needed | One read per post, to catch a network-side rejection |
| Native LinkedIn country mornings | later | Dev | parked | Do not schedule 09:07 Madrid. LinkedIn is paused |
| Pulse telemetry | later | C | blocked | `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Cursor Cloud Agent secrets |
| Bluesky summon mode (settle it) | later | Dev | todo | Reply with the verdict only when someone tags our Bluesky account (Bluesky's bot rule: opt-in only). Not a priority (Carlos, 2026-09-28). `docs/proposals/2026-09-29-settle-it.md` |

## Reverse oracle: first 10-target dry run (exploration)

Priority: `later`.

**Goal:** learn whether natural inputs reliably name high-reach, reply-friendly
accounts, before anything is published.
- **Budget:** ≤ 10 oracle calls per target, **≤ 100 in total**, all logged in
  `state/reverse/`.
- **Who:** candidates are proposed by CoS or a Cloud Agent. Nothing is published in
  the dry run.
- **Uniqueness:** inputs already used in any lane (winner seeds included) are
  excluded; alternatives below.

| # | Target | Kind | Where | First candidate inputs (≤10 per target, natural, no names) |
| --- | --- | --- | --- | --- |
| 1 | Duolingo | brand, famously playful on TikTok | TikTok, IG | `language app`, `app to learn spanish`, `owl mascot` |
| 2 | Ryanair | brand, famous TikTok banter | TikTok | `budget airline`, `cheap flight` |
| 3 | Spotify | brand | IG, TikTok | `music app`, `playlist app` |
| 4 | IKEA | brand | IG | `furniture store`, `flat pack furniture` |
| 5 | LEGO | brand | IG, TikTok | `toy`, `building blocks` |
| 6 | Airbnb | brand | IG | `vacation rental`, `place to stay abroad` |
| 7 | Bad Bunny | person (music, neutral) | TikTok, IG | `reggaeton artist`, `latin trap song` |
| 8 | MrBeast | person (creator, neutral) | TikTok | `youtuber`, `youtube channel` |
| 9 | Lionel Messi | person (sport, neutral) | IG | `footballer`, `soccer player`, `number 10` |
| 10 | Rosalía | person (music, Spain) | IG, TikTok | `spanish singer`, `flamenco pop` |

**Per target, record:**
- hit (y/n);
- calls used;
- the winning input and its naturalness score;
- whether it's stable (to check, re-ask that input **once more in the sandbox**: a
  hit that flips is a weak bet, because the published run is a fresh one).

**Go / kill:**
- **Go:** ≥ 5 of 10 targets have a natural, stable hit within budget. Then publish
  the 2 strongest, one per day inside the winner cap, and watch 72h for any reaction
  from the target.
- **Kill:** fewer than 3 natural hits, or hits only with contrived inputs. Drop the
  lane; winner seeds remain the main prestige route.
- **Exclusions:** every target passes the Wikidata check first (alive, adult, not a
  minor, not a private individual). Politicians are allowed. Handles are verified
  by a human before any tag. The trend lane's disaster/tragedy filter does not
  apply here.

## Later / improvements

### TikTok interaction lane (founder, 2026-09-26) — LATER, after video cadence is stable

Insight: on TikTok direct posts underperform; interaction wins. Instead of (or besides) plain posts, go to the winner's own account: e.g. verdict 'dry shampoo' -> find the winning brand's post about that product and comment with our verdict video (video reply), or publish our video and link it from a comment on their post. Fully programmed flow: 1) take the winning verdict, 2) find and VERIFY the winner's official TikTok account, 3) decide per case: video-comment on their post, tag them from our post, or hashtag only, 4) execute via official APIs only (anti-ban rules apply). Also: recover the old screenshots of how we did it manually and store them as reference. Constitution check: verdict-only, no chat, no engagement bait text; overlaps with the existing winner-tag lane (@k18hair) — fold together. Status: backlog, not started.

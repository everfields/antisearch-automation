# Backlog: the single list of pending items (dev + setup)

The one place for what's pending. CoS keeps it current; each PR updates the rows it
touches.
- **Owner:** C = Carlos by hand, CoS = CoS alone, Dev = a Cloud Agent PR.
- **Status:** todo, blocked, parked, live.

Updated 2026-09-25.

## Tonight and now

| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| First 4 clips to Buffer | GTM | todo | Same four frozen verdicts, re-rendered with a 2.0s pause (typed input and a blinking caret only; no spinner, dots, or "thinking" text) under `publisher-state` `manual/2026-09-25/` (oracle not re-asked). Upload through Buffer's free API from Actions, not the web UI. `@k18hair` only after `verified: true`. Mark a row `failed` in `posts.csv` if it never went out |
| `PUBLISHER_CRON=live` per network | CoS | todo | After each network's credentials exist: `PUBLISHER_LIVE_NETWORKS` + `PUBLISHER_CADENCE=soul` |
| Surprise-input test (6 rows) | CoS | todo | `queue/surprise_trial.csv`; keep/kill rules in `SURPRISING_INPUTS.md` |
| Winner lane on | CoS | todo | `PUBLISHER_WINNER_NETWORKS=instagram,tiktok,bluesky`, cap 2/day. Verify badges first (next row) |
| Verify winner handles | CoS / GTM | todo | `mill winners` lists them. Open each account, confirm the badge or the brand site link, set `verified: true` + `checked` + `by` in `queue/winners/handles.json` (PR). Add entries for new winners as they appear, never ahead of the verdict |
| Early-iteration repost screenshots | C | todo | Salesforce, Plaza Hotel, Dyson reposts from two years ago → `docs/founder-notes/` as proof and as handle candidates |

## Setup (by hand, minimized)

| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| Meta app for Instagram native | C | todo (tomorrow) | Instagram Login, Standard Access, no App Review; token + IG user ID → secrets |
| Bluesky account + Actions secrets | C → CoS | todo | Sign up on a human device (hCaptcha); `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` |
| DNS TXT records on antisearch.ai | C | todo | `_atproto` (Bluesky handle); Google Search Console and Bing Webmaster verification TXT. Cloudflare, additive |
| Public clips repo + Pages + token | C | todo | Needed by Instagram native and the Buffer bridge |
| Buffer API key | C | todo | Bridge for LinkedIn and TikTok until their native gates clear |
| LinkedIn Community Management | C | blocked | Needs a registered company (open question), a business email on the domain and a privacy policy (draft in `docs/legal/`) |

## Decisions and gates

| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| TikTok stays on the Buffer bridge | — | decided | Native = inbox drafts only (a human taps Post); the public audit is out of reach for an own-account tool |
| X via Buffer | C | decided | Paid API stays off. `PUBLISHER_BRIDGE=buffer` and `x` in `PUBLISHER_LIVE_NETWORKS`. Disconnect LinkedIn in Buffer, connect `@antisearch_ai`. No links, mentions, replies, or trend posts on X |
| `ceo` → Elon Musk | — | decided | Politics is allowed (founder 2026-09-25). The verdict publishes. It tags `@elonmusk` on TikTok or Instagram only after a human sets `verified: true` in `handles.json`. No LinkedIn Page or Bluesky handle is confirmed |
| og image fix | C (`SHIP:`) | todo | `<title>`/`og:title`/`twitter:title` → `antisearch.ai`; image = a lone cursor block; `?v=3`. Gates Show HN |
| Per-verdict cost / global cap on `/verdict` | C | open | Gates Show HN and full volume |
| `?q=` deep link | C (`SHIP:`) | parked | antisearch.ai/?q=thing prefills the input; parked until after the trial |

## Dev

| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| Trend lane | Dev | live in code | `publisher/trends.py`; switch on with `PUBLISHER_TREND_NETWORKS` |
| Reply watcher + "what's the … X?" answers (Bluesky) | Dev | live in code | `publisher/replies.py`; switch on with `PUBLISHER_REPLY_NETWORKS=bluesky` after the account exists |
| Winner lane | Dev | live in code | `publisher/winners.py`: seeds, verified-only @mention per network, withhold only for minors and private individuals, cross-network cap. Politics is not withheld |
| Reverse oracle: `mill reverse search` + target builder | Dev | todo (exploration) | Design in `GTM_OUT_OF_THE_BOX.md` → Reverse oracle: sandbox log outside `verdicts.csv`, ≤10 calls per target, naturalness score, Wikidata brand/person/exclusion check, handles as candidates only |
| LinkedIn winner tags | Dev | parked | Needs organization mentions in the Posts API (`@[Name](urn:li:organization:id)`) and a verified name→URN map; until then LinkedIn winners go untagged |
| X watcher / replies | Dev | parked | Design in `TREND_AND_REPLY_LANES.md`; needs X spend |
| `mill record` for manual uploads | — | dropped | Buffer uploads go through the free API key in Actions. No web UI |
| Buffer post reconciliation | Dev | todo if needed | One read per post, to catch network-side rejections on the bridge |
| Native LinkedIn country mornings | Dev | parked | Needs cron around the clock (+720 Actions min/month); decide after LinkedIn approval |
| Pulse telemetry | C | blocked | `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Cursor Cloud Agent secrets |

## Reverse oracle: first 10-target dry run (exploration)

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

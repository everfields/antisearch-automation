# Backlog: the single list of pending items (dev + setup)

The one place for what's pending. CoS keeps it current; each PR updates the rows it
touches.
- **Owner:** C = Carlos by hand, CoS = CoS alone, Dev = a Cloud Agent PR.
- **Status:** todo, blocked, parked, live.
- **Priority:** `today` (must be closed today), `now`, `next`, `later`. Anything marked `today` is in the section below and is not repeated.

Updated 2026-09-25.

## Today

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| LinkedIn decision | today | Opus | decided | Keep Page 99258814. One post/day after Spanish work hours: `PUBLISHER_SLOTS_LINKEDIN=15:07` (21:07 Madrid, 20:07 in the DST-gap week). Leave LinkedIn out of `PUBLISHER_LIVE_NETWORKS` until that variable is set. No place-rows (`employer in madrid` and the like) until local-morning scheduling is off. Write-up: `docs/proposals/2026-09-25-linkedin-decision.md` |

## Tonight and now

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| First 4 clips to Buffer | now | GTM | todo | Same four frozen verdicts, re-rendered with a 2.0s pause (typed input and a blinking caret only; no spinner, dots, or "thinking" text) under `publisher-state` `manual/2026-09-25/` (oracle not re-asked). Upload through Buffer's free API from Actions, not the web UI. `@k18hair` only after `verified: true`. Mark a row `failed` in `posts.csv` if it never went out |
| `PUBLISHER_CRON=live` per network | now | CoS | todo | After each network's credentials exist: `PUBLISHER_LIVE_NETWORKS` + `PUBLISHER_CADENCE=soul`. LinkedIn stays out until the decision above is configured |
| Surprise-input test (6 rows) | now | CoS | todo | `queue/surprise_trial.csv`; keep/kill rules in `SURPRISING_INPUTS.md` |
| Winner lane on | now | CoS | todo | `PUBLISHER_WINNER_NETWORKS=instagram,tiktok,bluesky`, cap 2/day. Verify badges first (next row) |
| Verify winner handles | now | CoS / GTM | todo | `mill winners` lists them. Open each account, confirm the badge or the brand site link, set `verified: true` + `checked` + `by` in `queue/winners/handles.json` (PR). Add entries for new winners as they appear, never ahead of the verdict |
| Early-iteration repost screenshots | next | C | todo | Salesforce, Plaza Hotel, Dyson reposts from two years ago → `docs/founder-notes/` as proof and as handle candidates |

## Setup (by hand, minimized)

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| Meta app for Instagram native | next | C | todo (tomorrow) | Instagram Login, Standard Access, no App Review; token + IG user ID → secrets |
| Bluesky account + Actions secrets | now | C → CoS | todo | Sign up on a human device (hCaptcha); `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` |
| DNS TXT records on antisearch.ai | next | C | todo | `_atproto` (Bluesky handle); Google Search Console and Bing Webmaster verification TXT. Cloudflare, additive |
| Public clips repo + Pages + token | now | C | todo | Needed by Instagram native and the Buffer bridge |
| Buffer API key | now | C | todo | Bridge for LinkedIn and TikTok until their native gates clear |
| LinkedIn Community Management | later | C | blocked | Needs a registered company (open question), a business email on the domain and a privacy policy (draft in `docs/legal/`) |

## Decisions and gates

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| TikTok stays on the Buffer bridge | later | — | decided | Native = inbox drafts only (a human taps Post); the public audit is out of reach for an own-account tool |
| X: no posting | later | C | decided | The API is paid (pay-per-use). Bluesky stands in; X design exists |
| `ceo` → Elon Musk | later | — | decided | Politics is allowed (founder 2026-09-25). The verdict publishes. It tags `@elonmusk` on TikTok or Instagram only after a human sets `verified: true` in `handles.json`. No LinkedIn Page or Bluesky handle is confirmed |
| og image fix | next | C (`SHIP:`) | todo | `<title>`/`og:title`/`twitter:title` → `antisearch.ai`; image = a lone cursor block; `?v=3`. Gates Show HN |
| Per-verdict cost / global cap on `/verdict` | next | C | open | Gates Show HN and full volume |
| `?q=` deep link | later | C (`SHIP:`) | parked | antisearch.ai/?q=thing prefills the input; parked until after the trial |

## Dev

| Item | Priority | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| Trend lane | later | Dev | live in code | `publisher/trends.py`; switch on with `PUBLISHER_TREND_NETWORKS` |
| Reply watcher + "what's the … X?" answers (Bluesky) | later | Dev | live in code | `publisher/replies.py`; switch on with `PUBLISHER_REPLY_NETWORKS=bluesky` after the account exists |
| Winner lane | later | Dev | live in code | `publisher/winners.py`: seeds, verified-only @mention per network, withhold only for minors and private individuals, cross-network cap. Politics is not withheld |
| Reverse oracle: `mill reverse search` + target builder | later | Dev | todo (exploration) | Design in `GTM_OUT_OF_THE_BOX.md` → Reverse oracle: sandbox log outside `verdicts.csv`, ≤10 calls per target, naturalness score, Wikidata brand/person/exclusion check, handles as candidates only |
| LinkedIn winner tags | later | Dev | parked | Needs organization mentions in the Posts API (`@[Name](urn:li:organization:id)`) and a verified name→URN map; until then LinkedIn winners go untagged |
| X watcher / replies | later | Dev | parked | Design in `TREND_AND_REPLY_LANES.md`; needs X spend |
| `mill record` for manual uploads | later | — | dropped | Buffer uploads go through the free API key in Actions. No web UI |
| Buffer post reconciliation | next | Dev | todo if needed | One read per post, to catch network-side rejections on the bridge |
| Native LinkedIn country mornings | later | Dev | parked | Needs cron around the clock (+720 Actions min/month). Do not build this on top of 09:07 local: a Madrid morning is inside Havas hours. See the LinkedIn decision |
| Pulse telemetry | later | C | blocked | `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Cursor Cloud Agent secrets |

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

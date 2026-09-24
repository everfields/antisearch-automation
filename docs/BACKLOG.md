# Backlog: the single list of pending items (dev + setup)

The one place for what's pending. CoS keeps it current; each PR updates the rows it
touches.
- **Owner:** C = Carlos by hand, CoS = CoS alone, Dev = a Cloud Agent PR.
- **Status:** todo, blocked, parked, live.

Updated 2026-09-25.

## Tonight and now

| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| First 4 clips to Buffer | GTM | todo | TikTok 22:07 + 00:07 ET, IG 22:07 ET, LinkedIn 09:07 ET. Files and JSON on branch `publisher-state`, `manual/2026-09-24/`. `@k18hair` only if TikTok shows it verified or official. Mark a row `failed` in `posts.csv` if it never went out |
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
| X: no posting | C | decided | The API is paid (pay-per-use). Bluesky stands in; X design exists |
| `ceo` → Elon Musk | C | open | Marked sensitive (politics guardrail), so a Musk verdict is withheld. One line in `handles.json` lifts it, if Carlos wants |
| og image fix | C (`SHIP:`) | todo | `<title>`/`og:title`/`twitter:title` → `antisearch.ai`; image = a lone cursor block; `?v=3`. Gates Show HN |
| Per-verdict cost / global cap on `/verdict` | C | open | Gates Show HN and full volume |
| `?q=` deep link | C (`SHIP:`) | parked | antisearch.ai/?q=thing prefills the input; parked until after the trial |

## Dev

| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| Trend lane | Dev | live in code | `publisher/trends.py`; switch on with `PUBLISHER_TREND_NETWORKS` |
| Reply watcher + "what's the … X?" answers (Bluesky) | Dev | live in code | `publisher/replies.py`; switch on with `PUBLISHER_REPLY_NETWORKS=bluesky` after the account exists |
| Winner lane | Dev | live in code | `publisher/winners.py`: seeds, verified-only handle resolver, withheld sensitive winners, cross-network cap |
| LinkedIn winner tags | Dev | parked | Needs organization mentions in the Posts API (`@[Name](urn:li:organization:id)`) and a verified name→URN map; until then LinkedIn winners go untagged |
| X watcher / replies | Dev | parked | Design in `TREND_AND_REPLY_LANES.md`; needs X spend |
| `mill record` for manual uploads | Dev | todo if needed | Only if the Buffer-web-UI fallback becomes routine |
| Buffer post reconciliation | Dev | todo if needed | One read per post, to catch network-side rejections on the bridge |
| Native LinkedIn country mornings | Dev | parked | Needs cron around the clock (+720 Actions min/month); decide after LinkedIn approval |
| Pulse telemetry | C | blocked | `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Cursor Cloud Agent secrets |

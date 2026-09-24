# Publisher: cadence, routes, and the one-sitting checklist

Updated 2026-09-25 (founder lock: **our own native publisher is the primary path
for every network**; Buffer free is a temporary bridge only and will never be paid
for. Also: volume cadence on US Eastern time, everything public in English, Soul's
taste review folded in as a preset).

**Trial clock reset.** This volume cadence replaces the ≤2/day, 20-day eyes-closed
trial. The trial clock restarts on the day volume posting goes live (the first day
`PUBLISHER_CRON=live` posts): that day is day 1, and eyes stay closed until day 21
counted from it.

**English lock (Carlos).** All public text is English by default until he says
otherwise:
- inputs (queue rows and pools; the guard rejects non-English characters while
  `PUBLISHER_LANGUAGE=en`);
- captions (empty or an @handle anyway);
- bios (`ai chooses the best. nothing else.`).

The oracle's verdict is whatever it answers.

**[HUMAN IP]** = done by Carlos on his own phone or laptop (home or mobile network),
**never** from the Grok Bot box. Everything else CoS can do.
Secrets go in: github.com/everfields/antisearch-automation → Settings → Secrets and
variables → Actions → **Secrets**. Switches go under **Variables**.

## Routes: native first (founder lock, 2026-09-25)

Every network has a native adapter in this repo that calls the network's official
API from GitHub Actions. Native is the **default route everywhere**. Buffer free
(LinkedIn Page, Instagram and TikTok are all connected, on `antisearch@outlook.com`)
is only a bridge for networks whose native approval gate hasn't cleared:

- **`PUBLISHER_BRIDGE=buffer`** routes Instagram, LinkedIn and TikTok through Buffer
  at once. **Delete the variable and Buffer is gone.**
- **`PUBLISHER_ROUTE_<NETWORK>=direct`** takes one network off the bridge as soon as
  its gate clears.
- Nothing uses Buffer's paid features: the bridge uses the free API key and
  `shareNow` only.

On "10 queued posts won't hold 5 a day": on the bridge our scheduler hands Buffer one
post at each slot, so Buffer's queue never holds more than one. Capacity was never
the problem. We leave Buffer because of the no-SaaS lock, and native is the target.

### Status per network

| Network | Native adapter | Official route | Approval gate | Realistic ETA | Until then |
| --- | --- | --- | --- | --- | --- |
| **Bluesky** | ready, tested | AT Protocol: app password → video service → `createRecord` | None: email signup (hCaptcha, human device) + app password | **Today**, after Carlos's 5-minute signup | — |
| **Instagram** (Business, Reels only) | ready, tested | Instagram API **with Instagram Login**: `graph.instagram.com` `/media` (`REELS`, `video_url`, `share_to_feed`, `thumb_offset`) → poll → `/media_publish` | A Meta app; **Standard Access for our own Business account, no App Review**. Needs a Meta developer account (Carlos's Facebook, phone- or card-verified) | **Same day** Carlos creates the app (≈20 min) | Bridge |
| **LinkedIn Page 99258814** | ready, tested (posts as the Page by default) | Posts API + Videos API with `w_organization_social` | **Community Management API**: a new app with no other product, verified by the Page, plus an access form vetting a **registered legal organization**, a **business email on antisearch.ai**, a website and a privacy policy. Development tier first (limited call volume), then Standard tier (screen recording) | **1–4 weeks if a registered company exists** (no published SLA; a rejection means a new app). **Blocked if there is no company** | Bridge |
| **TikTok** | ready, tested | Content Posting API: `inbox/video/init` (drafts) or `video/init` (Direct Post) → single-chunk PUT → status | **App audit** for public posts. It requires a fully developed public website with visible Privacy and Terms links (antisearch.ai has none, and changing it is a `SHIP:`), a sandbox demo video, review in days to 2 weeks, and **TikTok refuses tools that only post to your own accounts** | **Public auto-posting: not realistic.** Unaudited native works today only as inbox drafts (a human taps Post, max 5 pending per 24h) or private `SELF_ONLY` | Bridge (public, no tap) |
| **X** (held) | legacy `mill publish` adapter; port when unheld | API v2 media upload + `POST /2/tweets` | A developer account; **pay-per-use** (≈ $0.015 per post). That's a fee to X, Carlos's call | At unhold | — (Bluesky stands in) |

**Instagram Login vs Facebook Login.**
- **Instagram Login** (chosen) needs no Facebook Page. The token belongs to the
  Instagram account itself, and "a business I own or manage" gets Standard Access
  **without App Review** (Meta's App Review table).
- **Facebook Login** needs the Instagram account linked to a Facebook Page and a
  Page token; same access rules, more moving parts.
- **Development mode** works for accounts that have a role on the app, which ours
  will. If Meta ever requires Live mode, that needs an icon, a category and a privacy
  policy URL ([draft](legal/publisher-privacy.md)), still with no App Review for
  Standard Access. Verify on the first real post.

**Tokens:**
- **Instagram:** long-lived, 60 days; `mill oauth instagram refresh` extends it (CoS
  updates the secret).
- **LinkedIn:** 60 days; refresh tokens only if LinkedIn issues them (supported).
- **TikTok:** the refresh token lasts 365 days (supported).
- **Bluesky:** the app password doesn't expire.

**LinkedIn country mornings:**
- On the bridge, `employer in madrid` is scheduled in Buffer for 09:07 Madrid.
- Natively, the Posts API can't schedule, so country rows post at the ET LinkedIn
  slot. Posting at 09:07 in each country natively would need the hourly cron around
  the clock, about +720 Actions minutes a month. Decide when LinkedIn native is
  approved.

### What posts natively today

- **Bluesky:** fully native as soon as Carlos creates the account (5 minutes).
- **Instagram:** fully native the day the Meta app exists.
- **TikTok:** native only as inbox drafts; public TikTok stays on the bridge.
- **LinkedIn:** native only after Community Management approval; until then, the
  bridge.
- Every native path passes its tests and a dry-run today, including the Instagram
  clip hosted on GitHub Pages.

**Recommended live config today:** `PUBLISHER_BRIDGE=buffer` plus
`PUBLISHER_ROUTE_INSTAGRAM=direct` (once the Meta token is in). That's Bluesky and
Instagram native, LinkedIn and TikTok bridged. When LinkedIn is approved, set
`PUBLISHER_ROUTE_LINKEDIN=direct`. When nothing is bridged, delete
`PUBLISHER_BRIDGE`.

### The bridge, if it's on: how a frozen clip reaches Buffer with no human

At each network's slot, the GitHub Actions run (never the box):
1. picks the next row in blind order;
2. freezes the verdict (one honest run);
3. renders the ≤4s 9:16 clip;
4. commits it to the public clips repo and waits for GitHub Pages;
5. calls Buffer `createPost` (`shareNow`; LinkedIn country rows `customScheduled` for
   09:07 local);
6. logs it.

Buffer's API is on the free plan (checked 2026-09-24: 1 key, 3,000 requests per 30
days). The bridge uses about 800–1,350 of those a month, depending on the cadence
preset. **No queue refill.**

**If the Buffer API itself fails for 24h:** move that network to native if its gate
has cleared. Otherwise, as a last resort, GTM uploads the frozen clips through
Buffer's web UI on the box:
- in blind order, refilling daily with exactly the next 24h;
- Buffer's channel schedule set to our ET slots;
- a small `mill record` command to be built so the uploads land in the post log.

A full 10-post queue lasts 2 days at 5 a day, 3 days at 3, and 10 days at 1.

## Cadence: America/New_York, DST from the tz database, one variable

- A posting day runs **09:00 ET → 09:00 ET**; a 00:07 slot belongs to the day that
  started at 09:00.
- Every slot is on a **fixed :07 minute**, never on the hour, matching the hourly
  cron tick. Posts land 7–30 minutes after the slot because GitHub delays cron.
- At least **90 minutes between two posts on the same network**, both in the slot
  plan and at run time.
- One post per network per run.
- A missed slot stays open for 2h, then expires; it never catches up in a burst.

**`PUBLISHER_CADENCE` picks the preset. Carlos's 5-everywhere is the default;
`soul` is Soul's numbers:**

| Network | `carlos` (5) ET | Madrid | `soul` ET | Madrid |
| --- | --- | --- | --- | --- |
| TikTok | 14:07 18:07 20:07 22:07 00:07 | 20:07 00:07 02:07 04:07 06:07 | same (5) | same |
| X (when unheld) | 09:07 11:07 13:07 16:07 19:07 | 15:07 17:07 19:07 22:07 01:07 | same (5) | same |
| Bluesky | 09:07 11:07 13:07 16:07 19:07 | 15:07 17:07 19:07 22:07 01:07 | 09:07 13:07 18:07 (3) | 15:07 19:07 00:07 |
| Instagram | 12:07 16:07 19:07 21:07 23:07 | 18:07 22:07 01:07 03:07 05:07 | 13:07 19:07 22:07 (3) | 19:07 01:07 04:07 |
| LinkedIn Page | 09:07 11:07 13:07 15:07 17:07 | 15:07 17:07 19:07 21:07 23:07 | 09:07 (1) | 15:07 |

Timezone notes:
- **Madrid is ET +6h in both summer and winter.** Subtract 1h in the transition
  weeks, 2026-10-25 → 11-01 and 2027-03-08 → 03-28. UTC is ET +4 (EDT) / +5 (EST).
- **LinkedIn country rows** (`employer in madrid`, `employer in tokyo`, …) are handed
  to Buffer at the LinkedIn slot but **scheduled for 09:07 in that country**, so
  they land in its morning. Rows without a known place post at the ET slot.
  City/country list: `publisher/places.py`.
- **Per-network override:** `PUBLISHER_SLOTS_<NETWORK>` = `HH:07,...` (ET, max 5,
  ≥90 min apart) or `off`.

Why these slots: business networks open with the US workday and catch the West
Coast morning; leisure networks start at lunch and stack into the US evening, when
people browse places, food and beauty.

### Converged recommendation (Opus + Soul; Carlos decides)

**`PUBLISHER_CADENCE=soul`**, plus `PUBLISHER_SLOTS_INSTAGRAM=19:07` for the first
7 days, then remove it.

| Network | Carlos | Soul | Opus | Converged | Where Opus differs, one line |
| --- | --- | --- | --- | --- | --- |
| TikTok | 5 | 5 | 5 | **5** | — |
| X (when unheld) | 5 | 5 | 5 | **5** | — (it needs a 4th Buffer channel, which is paid, or X's pay-per-use API; decide at unhold) |
| Bluesky | 5 | 3 | 3 | **3** | Agree with Soul: the Following feed is chronological, so 5 from one account floods a small graph |
| Instagram | 5 | 3 | 1 → 3 | **3, after 1/day in week 1** | The account just came back from a flag; one reel a day for the first week before 3 |
| LinkedIn Page | 5 | 1 | 1 | **1** | Agree: a Page posting 5 a day reads as a bot, and honest employer inputs are scarce |

That's 12 posts a day (17 with X), instead of 20–25.

## Rules at volume (enforced unless marked)

- **One clip → one network, no cross-posting,** and **an input is never repeated,
  ever:** the runner refuses any input that already went out, under any row id, on
  any network.
- **Unowned words about 1 in 4:** the first post on each network is an unowned word,
  then every fourth.
- **The CSV is ordered once, then run blind:**
  - verdicts are asked only at post time, and pools are drawn in file order;
  - nothing pre-generates verdicts to pick from;
  - nothing sorts by likely virality or by which brand might repost;
  - posted inputs can never be re-queued.
  - A `@?` row shows its verdict before posting (only to set the tag). It must go
    out with a tag or `-`, never be dropped; `mill networks` lists frozen verdicts
    not yet posted, so a dropped row is visible.
- **Never numbered or serial:** inputs like `day 3`, `part 2`, `#4` or `1/5` are
  rejected. Captions are empty, the bare input or an @handle, so no series names
  and no templates.
- *(Curation, CoS + Soul)* No news or trend reactions and no outrage-bait inputs in
  the pools. Reposting our own clips is impossible: the code has no repost call.

## Queue fill and sizing

- **Order:** explicit queue rows first (`queue/bluesky_trial.csv`,
  `queue/tiktok_trial.csv`), then inputs drawn from `queue/pools/<network>.txt`
  (vertical) and `queue/pools/unowned.txt` (shared).
- **Rhythm:** each network's first post ever is an unowned word, then one in four.
- **Verticals:**
  - Bluesky: companies / tech (X's brief);
  - LinkedIn: employers;
  - Instagram: places (restaurants, travel, hotels, entertainment);
  - TikTok: beauty / hair / skin (the lock; Carlos grouped TikTok with leisure,
    so confirm whether it widens).
- **Uniqueness:** every input is used once, on one network, ever (one honest run,
  one clip → one network). The same verdict or clip never goes to two networks.
- **Size:**
  - `carlos`: 4 networks × 5 = **20 inputs, oracle calls and clips a day** (≈ 600 a
    month). `soul` / converged: **12 a day** (≈ 360 a month). About a quarter are
    unowned words.
  - The starter pools (60 unowned; 42–44 per vertical) cover about **11 days**.
    CoS and Soul extend them; `mill networks` prints the runway.
  - A dry pool makes that network go quiet; it never repeats an input.
- **Tags:** the explicit company rows and the TikTok row carry `@?`. The honest run
  freezes the verdict and holds the row, CoS sets the verified @handle (or `-`),
  and the next slot posts it. Pool rows are untagged unless a line ends in `| @?`.
- **Cost, unknown, must be confirmed before going live:** 360–600 `/verdict` calls a
  month, with an unknown LLM cost per verdict and no known global cap.
  Pulse should also exclude the mill's user agent `antisearch-mill/0.1` from
  product telemetry.
- **Production:** rendering is not the limit (5 clips render in 3.5 s). **GitHub
  Actions minutes are:**
  - 17 hourly runs a day. Runs with nothing due stop after `mill due` (about 30 s);
    about 15 due runs take 2–3 min each (ffmpeg install, oracle, render, Pages,
    Buffer).
  - That's roughly **1,100–1,400 min/month** against the 2,000 free minutes a
    month for private repos (shared with CI).
  - If the minutes run out, Actions stop; they don't bill unless a spending limit
    above $0 is set.
  - Making this repo public removes the cap (secrets stay secret). That's Carlos's
    call.

## Carlos's one-shot checklist (minimized)

**[HUMAN IP]** = his own laptop or phone. About an hour in total; A–C unlock
everything that can post natively.

**A. Bluesky (5 min)**
1. **[HUMAN IP]** bsky.app → Sign up (hCaptcha) → `antisearch@outlook.com`, handle
   `antisearch` → confirm the email code.
2. **[HUMAN IP]** Settings → Privacy and security → App passwords → Add `publisher`
   → secrets `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`.
   Later, optional: the `antisearch.ai` handle via a Cloudflare TXT record (steps in
   Bluesky → Settings → Account → Handle).

**B. Clip host (5 min)** — needed by Instagram native and by the bridge
3. **[HUMAN IP]** GitHub:
   - create the **public** repo `everfields/antisearch-clips` with a README;
   - Settings → Pages → Deploy from branch `main` `/`;
   - create a fine-grained token with *Contents: read and write* on that repo only
     → secret `PUBLISHER_MEDIA_TOKEN`.

   CoS sets `PUBLISHER_MEDIA_REPO` and `PUBLISHER_PUBLIC_BASE_URL`, and publishes the
   privacy page there.

**C. Instagram native (≈20 min)**
4. **[HUMAN IP]** developers.facebook.com (his Facebook; Meta may ask to confirm a
   phone or card once):
   - My Apps → Create app → use case **"Manage messaging and content on Instagram"**
     (Instagram API with Instagram login);
   - API setup → **Add account** → log in as the AntiSearch Business account →
     **Generate token**.
5. Send CoS the **token** and the **Instagram user ID** shown next to it → secrets
   `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID`. No App Review.

**D. Bridge key (2 min)** — keeps LinkedIn and TikTok posting until their gates clear
6. **[HUMAN IP]** publish.buffer.com/settings/api → create the key → secret
   `BUFFER_API_KEY`. CoS runs `mill buffer-channels` and pins the channel IDs.

**E. LinkedIn native (15 min + LinkedIn's review) — only if a registered company exists**
7. **[HUMAN IP]** linkedin.com/developers/apps/new:
   - a **new** app `AntiSearch Page Publisher`, Page `antisearch` (99258814);
   - Settings → Verify, then approve it as the Page's super admin;
   - Products → **Community Management API** only → the access form:
     - the company's legal name and registered address;
     - website `https://antisearch.ai`;
     - privacy policy URL (the clips-site page);
     - business email `social@antisearch.ai` (Cloudflare Email Routing → the
       Outlook inbox, so the verification email arrives).
   - Auth: redirect `https://antisearch.ai/`.
8. After approval: CoS sends the `mill oauth linkedin url` link → Carlos approves as
   Page admin → CoS stores `LINKEDIN_ACCESS_TOKEN` (and the refresh token if issued).

**F. TikTok native drafts (15 min) — only if Carlos wants native drafts that need a tap; otherwise skip and keep the bridge**
9. **[HUMAN IP]** developers.tiktok.com:
   - an app with Login Kit (redirect `https://antisearch.ai/`) + Content Posting API
     (`video.upload`), Sandbox, target user = the AntiSearch TikTok;
   - CoS runs `mill oauth tiktok url` → Carlos approves on the phone →
     `TIKTOK_REFRESH_TOKEN`.

**Go live**
10. Carlos's yes → Variables:
    - `PUBLISHER_LIVE_NETWORKS=bluesky,instagram,linkedin,tiktok`;
    - `PUBLISHER_CADENCE` (`soul` recommended);
    - `PUBLISHER_BRIDGE=buffer` + `PUBLISHER_ROUTE_INSTAGRAM=direct`;
    - `PUBLISHER_CRON=live`.

    That day is day 1 of the trial clock.

## Env vars

| Name | Kind | Notes |
| --- | --- | --- |
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | secret | App password, no expiry |
| `BUFFER_API_KEY` | secret | Bridge only. Free plan: 1 key, 3,000 requests / 30 days |
| `BUFFER_CHANNEL_INSTAGRAM` / `_LINKEDIN` / `_TIKTOK` | variable | From `mill buffer-channels`; saves 2 requests per post |
| `PUBLISHER_MEDIA_TOKEN` | secret | Fine-grained, contents write on the clips repo only |
| `PUBLISHER_MEDIA_REPO`, `PUBLISHER_PUBLIC_BASE_URL` | variable | Clips repo + its Pages URL |
| `PUBLISHER_LIVE_NETWORKS` | variable | The recorded first-of-class yes. Adding `x` freezes Bluesky |
| `PUBLISHER_CRON` | variable | unset = off; `dry-run`; `live` |
| `PUBLISHER_CADENCE` | variable | `carlos` (default, 5 everywhere) or `soul` (TikTok 5, X 5, Bluesky 3, IG 3, LinkedIn 1) |
| `PUBLISHER_SLOTS_<NETWORK>` | variable, optional | `HH:07,...` ET, max 5, ≥90 min apart, or `off` |
| `PUBLISHER_TREND_NETWORKS`, `PUBLISHER_TREND_CAP` | variable, optional | Trend lane: networks + rows per network per day (default 1, max 3). See `TREND_AND_REPLY_LANES.md` |
| `PUBLISHER_WINNER_NETWORKS`, `PUBLISHER_WINNER_CAP` | variable, optional | Winner lane: networks + posts per day across networks (default 2, max 3); handles in `queue/winners/handles.json` |
| `PUBLISHER_REPLY_NETWORKS`, `PUBLISHER_REPLY_CAP`, `PUBLISHER_WATCH_BLUESKY` | variable, optional | Reply lane (Bluesky): `bluesky` to go live, ≤3 a day, handles to watch |
| `PUBLISHER_LANGUAGE` | variable, optional | `en` (default, Carlos's lock); anything else lifts the English check |
| `PUBLISHER_BRIDGE` | variable, optional | `buffer` = Instagram, LinkedIn and TikTok via Buffer free. Unset = Buffer gone, all native |
| `PUBLISHER_ROUTE_<NETWORK>` | variable, optional | `direct` (native, the default) or `buffer`; overrides the bridge for one network |
| `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID` | secret | From the Meta app's Instagram login token generator; refresh within 60 days |
| `LINKEDIN_ACCESS_TOKEN` (+ `LINKEDIN_REFRESH_TOKEN`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`) | secret | After Community Management approval |
| `LINKEDIN_ORGANIZATION_ID` | variable, optional | Default `99258814` (the antisearch Page) |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` | secret | Native drafts only (section F) |
| `PUBLISHER_QUEUE` | variable, optional | Default `queue/bluesky_trial.csv queue/tiktok_trial.csv` |

## Other adapters (built, tested, not routed)

`mill networks` prints each one's status and gate:
- **Threads:** the same Meta developer account as Instagram (its own use case).
- **Reddit:** the API is closed to new apps.
- **Mastodon:** small reach.

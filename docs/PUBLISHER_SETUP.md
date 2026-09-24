# Publisher: cadence, routes, and the one-sitting checklist

Updated 2026-09-24 (Carlos: volume cadence on US Eastern time, IG/LinkedIn/TikTok
through Buffer from his phone; everything public in English. Soul's taste review is
folded in as a preset).

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

## Routes (decided)

| Network | Route | Why |
| --- | --- | --- |
| **Bluesky** | **Our publisher → Bluesky API** | Open API; the adapter is built and tested |
| **Instagram** | **Our publisher → Buffer API → Instagram** | Buffer already holds Meta's approval. Our own route needs a Meta developer account on Carlos's Facebook plus the Graph setup |
| **LinkedIn Page** | **Our publisher → Buffer API → LinkedIn** | The Page API needs Community Management approval, which needs a registered company. Buffer's approved app posts to the Page |
| **TikTok** | **Our publisher → Buffer API → TikTok** | Buffer's audited app posts **publicly**. Our sandbox app can only make inbox drafts (a human taps each one, max 5 pending per day), and TikTok won't audit an in-house tool |

**Our code keeps everything that matters:** slots, the one honest oracle run, frozen
verdicts, captions, the post log. Buffer is only the pipe, driven by its API, never
its web UI.
- Each post is created at its slot with `shareNow`, so Buffer's 10-post queue limit
  never applies.
- Usage stays well inside the free plan's 3,000 requests per 30 days: about 450
  posts a month, 3 requests each.
- Switching a network back to its own adapter is one variable
  (`PUBLISHER_ROUTE_<NETWORK>=direct`).

Buffer only accepts media by public URL, so each clip is committed to a public repo
(`everfields/antisearch-clips`) and served by GitHub Pages. That's free, needs no
card, and stays first-party.

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

## One-sitting checklist (what changed: Buffer + clips repo replace the TikTok developer app)

**Bluesky** (unchanged)
1. **[HUMAN IP]** bsky.app → Sign up (hCaptcha) → `antisearch@outlook.com`, handle `antisearch` → confirm the email code.
2. **[HUMAN IP]** Settings → Privacy and security → App passwords → Add `publisher` → secrets `BLUESKY_HANDLE` = `antisearch.bsky.social`, `BLUESKY_APP_PASSWORD`.
3. **[HUMAN IP]** Settings → Account → Handle → "I have my own domain" → `antisearch.ai` → Cloudflare DNS: `TXT` `_atproto` = the `did=…` value → Verify → set `BLUESKY_HANDLE` = `antisearch.ai`.
4. **[HUMAN IP]** Profile:
   - avatar [`docs/assets/bluesky-avatar.png`](assets/bluesky-avatar.png);
   - name `antisearch.ai`;
   - bio `ai chooses the best. nothing else.`

**Buffer** (Instagram, LinkedIn Page, TikTok)

5. **[HUMAN IP]** Buffer (signed in as `antisearch@outlook.com`) → connect:
   - **Instagram**, as a Business or Creator account;
   - the **LinkedIn Page**, as its admin;
   - **TikTok**.

   Check that each channel shows automatic publishing. If one only offers reminders,
   switch that account to Business in its app.
6. **[HUMAN IP]** publish.buffer.com/settings/api → create the API key (the org owner
   only) → secret `BUFFER_API_KEY`.
7. CoS: `mill buffer-channels` → set the variables `BUFFER_CHANNEL_INSTAGRAM`,
   `BUFFER_CHANNEL_LINKEDIN`, `BUFFER_CHANNEL_TIKTOK`.

**Clip hosting**

8. **[HUMAN IP]** GitHub:
   - create the **public** repo `everfields/antisearch-clips` (with a README);
   - Settings → Pages → Deploy from branch `main`, folder `/`;
   - create a fine-grained token with *Contents: read and write* on that repo only
     → secret `PUBLISHER_MEDIA_TOKEN`.
9. Variables: `PUBLISHER_MEDIA_REPO` = `everfields/antisearch-clips`,
   `PUBLISHER_PUBLIC_BASE_URL` = `https://everfields.github.io/antisearch-clips`.

**Go live**

10. CoS: Actions → publisher → Run workflow (dry-run; never calls the oracle), then
    `mill networks` for slots and runway.
11. Carlos's yes → Variables:
    - `PUBLISHER_LIVE_NETWORKS` = `bluesky,instagram,linkedin,tiktok`;
    - `PUBLISHER_CADENCE` = `carlos` or `soul`, plus any slot overrides;
    - `PUBLISHER_CRON` = `live`.

The next open slot posts, and that day is **day 1 of the trial clock**. Recurring: CoS sets tags on held rows and keeps the pools
stocked. Nobody taps anything.

## Env vars

| Name | Kind | Notes |
| --- | --- | --- |
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | secret | App password, no expiry |
| `BUFFER_API_KEY` | secret | Free plan: 1 key, 3,000 requests / 30 days |
| `BUFFER_CHANNEL_INSTAGRAM` / `_LINKEDIN` / `_TIKTOK` | variable | From `mill buffer-channels`; saves 2 requests per post |
| `PUBLISHER_MEDIA_TOKEN` | secret | Fine-grained, contents write on the clips repo only |
| `PUBLISHER_MEDIA_REPO`, `PUBLISHER_PUBLIC_BASE_URL` | variable | Clips repo + its Pages URL |
| `PUBLISHER_LIVE_NETWORKS` | variable | The recorded first-of-class yes. Adding `x` freezes Bluesky |
| `PUBLISHER_CRON` | variable | unset = off; `dry-run`; `live` |
| `PUBLISHER_CADENCE` | variable | `carlos` (default, 5 everywhere) or `soul` (TikTok 5, X 5, Bluesky 3, IG 3, LinkedIn 1) |
| `PUBLISHER_SLOTS_<NETWORK>` | variable, optional | `HH:07,...` ET, max 5, ≥90 min apart, or `off` |
| `PUBLISHER_LANGUAGE` | variable, optional | `en` (default, Carlos's lock); anything else lifts the English check |
| `PUBLISHER_ROUTE_<NETWORK>` | variable, optional | `buffer` (default for instagram, linkedin, tiktok) or `direct` |
| `PUBLISHER_QUEUE` | variable, optional | Default `queue/bluesky_trial.csv queue/tiktok_trial.csv` |

## Other adapters (built, tested, not routed)

`mill networks` prints each one's status:
- **Direct Instagram, LinkedIn and TikTok:** fallbacks behind
  `PUBLISHER_ROUTE_<NETWORK>=direct`, with the walls listed there.
- **Threads:** a Meta developer account on Carlos's Facebook.
- **Reddit:** the API is closed to new apps.
- **Mastodon:** small reach.

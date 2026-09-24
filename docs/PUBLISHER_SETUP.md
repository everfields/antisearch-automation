# Publisher: cadence, routes, and the one-sitting checklist

Updated 2026-09-24 (Carlos: 5 posts a day per network, US Eastern time,
IG/LinkedIn/TikTok through Buffer from his phone).

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

## Slots (decided): America/New_York, DST from the tz database

- A posting day runs **09:00 ET → 09:00 ET**; a 00:00 slot belongs to the day that
  started at 09:00.
- ≤ 5 per network per day, one per network per run.
- A missed slot stays open for 2 hours, then expires; it never piles up into a late
  burst.

| Network | Leans | ET | Madrid (summer & winter, +6h) | Madrid in transition weeks (+5h) |
| --- | --- | --- | --- | --- |
| Bluesky (X stand-in) | business, morning | 09:00 11:00 13:00 16:00 19:00 | 15:00 17:00 19:00 22:00 01:00 | 14:00 16:00 18:00 21:00 00:00 |
| LinkedIn | business, morning | 09:00 10:00 12:00 14:00 17:00 | 15:00 16:00 18:00 20:00 23:00 | 14:00 15:00 17:00 19:00 22:00 |
| Instagram | leisure, evening | 12:00 17:00 19:00 21:00 23:00 | 18:00 23:00 01:00 03:00 05:00 | 17:00 22:00 00:00 02:00 04:00 |
| TikTok | leisure, night | 14:00 18:00 20:00 22:00 00:00 | 20:00 00:00 02:00 04:00 06:00 | 19:00 23:00 01:00 03:00 05:00 |

Why these slots:
- **Business networks** open with the US workday: 09:00 ET is 06:00 in California,
  and 11:00–12:00 ET catches the West Coast morning. Three of five slots fall before
  13:00, with an end-of-day slot.
- **Leisure networks** start at lunch and stack into the US evening (17:00–00:00 ET),
  when people scroll for places, food and beauty.
- Posts from one account sit at least 1h apart (2h+ on Bluesky), so they don't
  bunch.

Timezone notes:
- **Madrid is ET +6 in both summer and winter.** It's +5 only in the transition
  weeks, when Europe and the US change clocks on different dates: 2026-10-25 → 11-01
  and 2027-03-08 → 03-28.
- **UTC** is ET +4 in summer time (EDT) and ET +5 in winter (EST).
- **Timing:** the hourly cron fires at :07 UTC, so a post goes out roughly 7–30
  minutes after its slot (GitHub delays cron at peak times).
- **Overrides:** `PUBLISHER_SLOTS_<NETWORK>` = `HH:MM,...` (ET, max 5) or `off`.

**Recommended overrides (strategy view; Carlos decides):**
- **Instagram:** ramp **1 → 3 → 5**: week 1 `19:00`; week 2 `17:00,19:00,21:00`;
  then the default. The account has just come back from a suspension and a selfie
  check, and five API reels a day from day one is the pattern that gets flagged.
- **LinkedIn:** **2 a day**, `09:00,12:00`. Page posts on the same day compete with
  each other in the feed, and five near-identical clips a day reads as noise to a
  professional audience.
- **Bluesky and TikTok:** 5 a day is fine. Each post is one silent verdict at a
  fixed hour, which is the monolith, not noise.

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
  - 4 networks × 5 = **20 inputs, 20 oracle calls, 20 clips a day** (≈ 600 a
    month): about 5 unowned words and 15 vertical inputs a day.
  - The starter pools (60 unowned; 42–44 per vertical) cover about **11 days**.
    CoS and Soul extend them; `mill networks` prints the runway.
  - A dry pool makes that network go quiet; it never repeats an input.
- **Tags:** the explicit company rows and the TikTok row carry `@?`. The honest run
  freezes the verdict and holds the row, CoS sets the verified @handle (or `-`),
  and the next slot posts it. Pool rows are untagged unless a line ends in `| @?`.
- **Cost, unknown, must be confirmed before full cadence:** 600 `/verdict` calls a
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
    - any slot overrides above;
    - `PUBLISHER_CRON` = `live`.

The next open slot posts. Recurring: CoS sets tags on held rows and keeps the pools
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
| `PUBLISHER_SLOTS_<NETWORK>` | variable, optional | `HH:MM,...` ET, max 5, or `off` |
| `PUBLISHER_ROUTE_<NETWORK>` | variable, optional | `buffer` (default for instagram, linkedin, tiktok) or `direct` |
| `PUBLISHER_QUEUE` | variable, optional | Default `queue/bluesky_trial.csv queue/tiktok_trial.csv` |

## Other adapters (built, tested, not routed)

`mill networks` prints each one's status:
- **Direct Instagram, LinkedIn and TikTok:** fallbacks behind
  `PUBLISHER_ROUTE_<NETWORK>=direct`, with the walls listed there.
- **Threads:** a Meta developer account on Carlos's Facebook.
- **Reddit:** the API is closed to new apps.
- **Mastodon:** small reach.

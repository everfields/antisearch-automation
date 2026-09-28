# Proposal: measure repetition daily (returning users, queries per user)

Founder, 2026-09-28: the key metric is now **repetition**, meaning how many people come back
and query again, and how often. It should be measured daily, within the manifesto: no login,
no personalization, no verdict memory, and nothing that adds latency or requests to the
query path. `the_best` is not changed by this page; one `SHIP:` is proposed at the end.

## What `the_best` has today (seen from outside)

- **The page is cookieless.**
  - `GET /` sets no cookie.
  - The script sends one request per query, `POST /verdict {"category": "..."}`, and nothing else.
  - There is no beacon and no client ID.
  - The service worker is a no-op fetch handler.
- **The privacy page says:** "no accounts. no login. no cookies. no tracking pixels. queries
  are logged anonymously for quality monitoring. ip addresses are hashed and cannot be reversed."
- **The server** logs each query to Supabase with an `ip_hash`, salted with
  `IP_HASH_SALT`, a fixed value in the container app's environment. There is also a
  cookieless visit counter on the server side.
- **Not visible from here:** this agent's token cannot read `everfields/the_best`, so three
  facts need one look at its code or the Supabase schema before trusting any number below:
  1. Is the hash `hash(salt + ip)`, stable across days, or does it mix in the date (a
     daily-rotating hash)?
  2. The query row's columns: timestamp, `ip_hash`, category, verdict, and whether it has a
     user agent.
  3. Does the visit counter store `ip_hash` per page load, or only a total?

## Is a daily-rotating hash enough?

No. A hash that rotates daily makes "the same person on two days" impossible by
construction. It gives queries per person *within* a day and nothing across days, which is
exactly the metric we now care about. If today's hash mixes in the date, cross-day returns
can't be measured from existing data at all.

## What we can measure today (if the hash is stable)

These run as plain SQL in the Supabase SQL editor. Table and column names are placeholders
(`queries`, `created_at`, `ip_hash`, `category`); adjust them to the real schema.

| metric | definition | SQL sketch |
| --- | --- | --- |
| people | distinct `ip_hash` with a query that day | `count(distinct ip_hash)` per `date(created_at)` |
| queries per person | queries ÷ people; also the share of people with 2 or more queries that day | `count(*)` and `count(distinct ip_hash)` per day |
| **returning** | people that day who also queried on any earlier day | `ip_hash` with `min(date) < day` |
| **D1 / D7 return** | of day d's people, the share seen again on d+1, or within d+1..d+7 | self-join on `ip_hash` |
| repetition curve | people by number of distinct days active (1, 2, 3–6, 7+) | `count(distinct date)` per `ip_hash` |
| category variety | distinct categories per person; the share of multi-query people with 2 or more distinct categories | `count(distinct lower(category))` per `ip_hash` per day |

**Excluding our own traffic.**
- **The mill.** Every oracle call the mill made is a row in
  `publisher-state/verdicts.csv`, plus the reverse-oracle runs in
  `publisher-state/reverse_oracle/`. Drop a query that matches one of those categories within
  60 s of its `fetched_at`. If the row has a user agent, also drop `antisearch-mill/0.1`.
- **Carlos, CoS and agents testing by hand.** Each device types one marker input once, for
  example `zz-team`. The `ip_hash` values of those rows go on an exclusion list. Their home
  and office IPs then drop out of every day.
- **The Capacitor app.** It calls the same `/verdict`, so it counts as users, which is correct.

**How far to trust an IP hash** (be honest about what it measures):
- **It undercounts returns.**
  - Phones change IP between cell sites.
  - iOS and Android rotate temporary IPv6 addresses about daily.
  - iCloud Private Relay changes the egress IP.
  - So one person can appear as several.
- **It overcounts returns.** Carrier-grade NAT, offices, universities and cafés put many
  people behind one IP, so several people appear as one returning person.
- **So:** the numbers are fine for the **trend** (day over day, after a post or an event),
  but not for an absolute return rate. Home Wi-Fi returns are the most reliable part.

## What needs a `the_best` change

One field on the query that already exists makes returns exact without identifying anyone.

### `SHIP:` a return bucket on the existing query

- **Client.**
  - The page keeps **one value** in `localStorage`: the UTC date of the last query, with no
    ID, no random value and no verdict.
  - With the existing `POST /verdict` it adds one field, `r`: `new` (never asked on this
    browser), `today`, `1d`, `2-7d` or `8d+`.
  - Then it overwrites the stored date.
- **Server.** It stores `r` on the query row. Nothing else changes.
- **Cost:** no extra request, and no measurable latency (a synchronous `localStorage` read,
  microseconds). There is nothing to link two visits together, so there is no personalization
  and no verdict memory.
- **What it gives, daily:**
  - the exact share of queries and of people who come back, and how long after their last
    visit, whatever their IP does;
  - combined with `ip_hash` within a day, queries per person;
  - `r = new` counts first visits.
- **Honest caveats:**
  - **ePrivacy.** Article 5(3) (and Spain's LSSI 22.2) covers *any* storage on the device,
    not only cookies. A date kept purely for aggregate audience counting may fall under the
    audience-measurement exemption (CNIL) or it may need consent, so it needs Carlos's legal
    call.
  - **Privacy page.** It would need one plain line: "your browser remembers only the day you
    last asked, so we can count how many people come back. no id."
  - **Coverage.** Private browsing, a cleared history, or a new device shows up as `new`, so
    the number is a floor.
- **If device storage is ruled out,** the server-only alternative is to also log a hash of
  the network prefix (`/24` for IPv4, `/64` for IPv6). It survives daily IPv6 rotation on home
  lines. It is still noisy on mobile.

## The Friday proxies

- **Searches per person:** queries ÷ distinct `ip_hash` per day. Report the median, p90, and
  the share of people with 2 or more.
- **Category variety:** distinct categories per person per day. Report the share of
  multi-query people who asked 2 or more *different* things, which means exploring, not
  retrying. Also report the most common next query after a first one.
- **Bounce:** a visit with no query. It needs the visit counter per `ip_hash` per day:
  (visiting hashes with 0 queries) ÷ (visiting hashes). If the counter is only a total, the
  approximation is 1 − (hashes that queried ÷ page loads).
- **URL shares:** there is no share button, by design. Every chat app fetches the page once
  to build a link preview when someone pastes the link. Counting `GET /` requests by preview
  bots per day approximates "links pasted into chats": `WhatsApp/`, `facebookexternalhit`
  (Messenger, Instagram, and iMessage previews), `TelegramBot`, `Slackbot-LinkExpanding`,
  `Discordbot`, `Twitterbot`, `LinkedInBot`. This needs the user agent on the visit-counter
  row. The request log's default uvicorn format has no user agent. It is the next change in
  line after the return bucket.
- **Screenshots:** they can't be measured directly. The proxy:
  - The result screen's only mark is the footer `antisearch.ai` (F-1), so a screenshot sends
    people who *type the domain*.
  - Watch for (a) first-time people (`r = new`, or a new `ip_hash`) whose **first query
    repeats a query someone else asked in the last 48 h**. That "echo" is someone trying what
    they saw, and rare queries make it strong.
  - Watch for (b) public mentions of "antisearch" (Bluesky search is already possible
    read-only; X and Instagram need logged-in access), and saves and shares on our own reels.

## Making it daily

- **The job.** `mill pulse` would run in this repo's metrics workflow at 06:00 Madrid. It
  reads Supabase with a **read-only** Postgres role, writes
  `publisher-state/metrics/repeat.csv` (one row per day with the metrics above), and adds a
  "Repetition" block to `metrics/summary.md`.
- **What it's blocked on.** It is the existing Pulse backlog item: it needs `SUPABASE_URL`
  plus a read-only key as a secret.
- **Until then,** Carlos (or Claude Code on his machine) can run the SQL above once a day in
  the Supabase editor.

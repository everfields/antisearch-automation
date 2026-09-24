# Trend lane and reply lane (founder order 2026-09-25)

Carlos: launch now, fail fast, bolder and more timely. Both lanes keep the ritual:
one bare English input, one lowercase verdict, nothing else.

**What this overrides.** Soul's earlier pre-kills of "news or trend reactions" and
"replying in threads" are superseded by Carlos's order. They're kept as guardrails:
- a trend becomes a *noun input* (a show, a film, a place, a product, a food), never
  a comment on the news;
- a reply is the verdict and nothing else, capped, and only to people who asked.

## Trend lane (`publisher/trends.py`, built and tested)

**Sources, all free with no key:**
- **Wikipedia most-read (en):** the only source of inputs, because each article
  carries a description we can classify.
- **Google Trends daily RSS (US)** and **Bluesky trending topics:** they only raise
  the rank of a Wikipedia candidate they also mention. Their top items are mostly
  news, so they never supply an input.
- **TikTok Creative Center:** not scraped (its terms don't allow it); design only.

**The filter** (on the live data of 2026-09-25 it dropped 37 of 44 articles):
- **unsafe:** deaths, crime, war, politics, disasters, disease, courts, named
  politicians. Checked in the title, the description *and* the extract.
- **people:** anyone described by an occupation or a birth year; people are never
  objects.
- **lists and delegations** ("List of…", "X at the Y").
- **kept:** only films, shows, games, music works, places, products, food, animals,
  events, domains.
- **Shaping:** `Resident Evil (2026 film)` → `resident evil`,
  `Big Brother 28` → `big brother`. Then the input guard applies: English, not
  serial, never "best", never used before.

**Blind order:** the day's candidates (Wikipedia views, ×2 when also trending
elsewhere) are fetched **once per posting day** and frozen in
`state/trends/<day>.json`, so nobody picks among them.

**Cap:**
- `PUBLISHER_TREND_CAP` (default 1, hard max 3) trend rows per network per posting
  day, only on the networks in `PUBLISHER_TREND_NETWORKS`.
- Trend rows sit after the explicit queue rows and before the pools. They use the
  network's normal slots and the daily cap.
- A trend input is never reused on another network.

**Try it:** `mill trends --fresh` lists every article with its keep/skip reason.
2026-09-25's list: `dancing with the stars`, `digger`, `.xyz`, `brothers`,
`modha rathri`, `primetime`.

## Reply lane (`publisher/replies.py`, Bluesky, built and tested)

**Two feeds:**
- **Watch** (`PUBLISHER_WATCH_BLUESKY`, handles; public API, no login):
  - a watched account's fresh top-level post that asks "what's the … X?" gets a
    reply first;
  - any other new post from a watched account is only an **alert** in
    `state/alerts.jsonl` for a human.
- **Search** (needs the Bluesky session): public posts asking "what's the … X?" /
  "which is the … X?", newest first.

**The reply** is the lowercase verdict for the bare X, and nothing else: no link, no
clip, no mention, no follow-up. The verdict comes from the frozen store (one honest
run; a repeated X reuses its verdict).

**Hard caps and filters:**
- **≤ 3 replies a day** (`PUBLISHER_REPLY_CAP`, hard max 3);
- one reply per author per 7 days;
- only posts under 2h old, only top-level posts, never our own, never a post we've
  already handled;
- never unsafe topics (the same filter as the trend lane);
- the oracle's `no` → no reply.

**Running it:**
- Live needs `bluesky` in `PUBLISHER_REPLY_NETWORKS`; dry-run shows what it would
  do.
- **Being first:** the workflow runs it hourly, which is free but rarely first. To
  really be first, run `mill replies --live` in a loop on an always-on machine
  (API traffic only, never a browser session). It costs nothing and is a CoS call.

**X (design only, no spend):**
- X's API is pay-per-use: a read to watch accounts, about $0.015 per reply created.
- The same design (watch list, ask extraction, verdict-only reply, ≤3 a day, safety
  filter) would port in a small adapter.
- Not built until Carlos decides X spend at unhold.

## Winner lane (`publisher/winners.py`, built and tested)

**The idea:** see `GTM_OUT_OF_THE_BOX.md` → Winner lane. Built pieces:
- **Seeds:** `queue/winners/<network>.txt` (Instagram 13, TikTok 13, LinkedIn 10,
  Bluesky 10). Curated bare inputs likely to crown an entity with a large official
  account. They pass the input guard, are unique across all queues and pools, and
  are drawn in file order.
- **Handle resolver:** `queue/winners/handles.json` maps an entity (plus aliases) to a
  handle per network.
  - A handle is used **only with `verified: true`**, set by a human who saw the
    badge (or the brand's own site linking to the account), with `checked` and `by`
    recorded.
  - The repo ships every handle as `verified: false`. `mill winners` lists what
    needs checking.
  - Unknown or unverified winners post with **no tag**. Never guessed.
- **Withheld:** entries with `sensitive: true` (today: Elon Musk, politics), and any
  verdict the safety filter flags. The post log records `withheld`, the input is
  spent, and no slot is used.
- **Per network:**
  - Instagram and TikTok take a plain `@handle`.
  - Bluesky tags only verified domain handles; anything else goes untagged.
  - **LinkedIn tags are off:** a LinkedIn mention needs the organization's URN, not
    `@text`, so LinkedIn winner posts go untagged until that is built (backlog).
- **Cap:** `PUBLISHER_WINNER_CAP` (default 2, hard max 3) winner posts per posting
  day across all networks in `PUBLISHER_WINNER_NETWORKS`. Winner rows come after the
  explicit queue and trend rows, before the pools, in the normal slots.

## Config

| Variable | Default | Meaning |
| --- | --- | --- |
| `PUBLISHER_TREND_NETWORKS` | none (off) | e.g. `tiktok,instagram,bluesky` |
| `PUBLISHER_TREND_CAP` | 1 | Trend rows per network per posting day (max 3) |
| `PUBLISHER_WINNER_NETWORKS` | none (off) | e.g. `instagram,tiktok,bluesky` |
| `PUBLISHER_WINNER_CAP` | 2 | Winner posts per posting day across networks (max 3) |
| `PUBLISHER_REPLY_NETWORKS` | none (off) | `bluesky` to allow live replies |
| `PUBLISHER_REPLY_CAP` | 3 | Replies per posting day (max 3) |
| `PUBLISHER_WATCH_BLUESKY` | none | Handles to watch, comma separated |

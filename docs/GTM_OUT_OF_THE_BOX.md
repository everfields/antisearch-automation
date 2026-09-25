# Go-to-market beyond the classic channels

Owner: strategy brain (Opus 5.5), for Carlos + CoS. Written 2026-09-24; revised with
Soul's input; **converged by CoS + Soul + Opus the same day.** Carlos decides the
gated items at the end. Nothing is published without his yes.

**Source note.** `manifesto_v5.md` in `everfields/the_best` was not readable from
this run: the repo returns 404 for this environment's GitHub token. This doc rests
on:
- the locked constitution: whisper; one lowercase verdict; one result; no chat, no
  engagement UI, no share cards, no ads, no spend, no paid verdicts; the raw
  screenshot is the share artifact;
- the manifesto passages quoted in Fable's handoff:
  - "input in → single best value out. Nothing else."
  - "The user is not asking a question — the user is offering input to the oracle.
    The hidden premise is *the best X is Y*. Period."
  - "not a ranking website, not affiliate marketing"
  - the example inputs "squirrels", "advice", "dog", "December 11th", "thing".

**The test for every idea:** does the distribution *behave like the product*? One
input, one answer, cold, no explanation, no ask. If a move needs a pitch, it's a
campaign.

**Out, per Carlos:** email and WhatsApp to friends, and anything touching Instagram
today.

---

## Rules (from Soul, adopted)

1. **One honest run per input.** The oracle is asked once and that answer is the
   post. Humans choose inputs; nobody chooses verdicts.
   - The publisher enforces it: only a live run asks, and the verdict is frozen
     before anything else (`docs/PUBLISHER_SETUP.md`).
   - My two drafting asks for `september 25th` on 2026-09-24 spent that date, so it
     stays out of the queue.
2. **Unowned words punctuate every wall.** Bare words no brand owns (`thing`,
   `silence`, `a year`, dates) are asked once and posted untagged. Next to a crown,
   they prove this is an oracle, not a directory, and they leave nothing for a brand
   to repost.
3. **The @tag is the only outreach.** If the honest run crowns a brand with a
   verified account on that network, the caption is that `@handle` and nothing else.
   - **On Bluesky, only a verified domain handle** (e.g. `@company.com`); else the
     caption is empty.
   - If the brand reposts, that repost is the distribution.
   - Never ask, DM, reply, follow up or thank.
4. **At volume (Soul):**
   - an input is never repeated, on any network;
   - the CSV is ordered once and run blind: no picking verdicts, no sorting by
     likely virality or repost, no re-queuing winners;
   - never numbered or serial posts, series names, templated captions, news or
     trend reactions, reposts of our own clips, or outrage-bait inputs.

## Update 2026-09-24 night (Carlos): cadence and routes

- **Volume cadence** at America/New_York slots on fixed :07 minutes, ≥90 min apart
  per network: business networks lean to the morning, leisure networks to the
  evening.
  - `PUBLISHER_CADENCE=carlos` (5 everywhere) or `soul` (TikTok 5, X 5, Bluesky 3,
    IG 3, LinkedIn 1).
  - Converged recommendation: `soul`, with Instagram at 1/day in week 1.
- **This replaces the ≤2/day 20-day eyes-closed trial.** The trial clock restarts on
  the day volume goes live (day 1), with eyes closed until day 21 from then.
- **English by default** (Carlos): inputs, captions and bios. The guard enforces it
  for inputs.
- LinkedIn employer-by-country rows post at 09:07 in that country's morning, through
  a Buffer scheduled post.
- **Instagram, the LinkedIn Page and TikTok now exist.** Founder lock (2026-09-25):
  our native publisher is the primary path for every network, and Buffer free is
  only a removable bridge while native gates clear (`PUBLISHER_SETUP.md`).
- Slots, routes, queue sizing, cost and the recommended IG ramp / LinkedIn 2/day are
  in [`PUBLISHER_SETUP.md`](PUBLISHER_SETUP.md). The rules above are unchanged.
- The old IG first-posts order (disfrutar → aman → psg) names verdicts. Under one
  honest run we can only choose inputs (`restaurant in barcelona` and `hotel` head
  the Instagram pool), and the wall still opens with an unowned word.

## Winner lane (Carlos, 2026-09-25; repo memory)

**The idea.** Every input names one answer. When the answer is a real entity with an
official account (a brand, a country's tourism board, a hotel, a company, a public
figure in a neutral category), being named by the oracle is a free prestige award.
We post the locked clip and the **only text is the winner's verified @handle**.
- The repost is theirs to give; we never ask.
- It's proven: Salesforce, the Plaza Hotel and Dyson reposted early iterations two
  years ago. What was missing was a route, maintenance and a team.
- Carlos's transcript is kept verbatim in
  [`founder-notes/2026-09-25-winner-lane.md`](founder-notes/2026-09-25-winner-lane.md).

**How it runs (built):**
- About 46 curated seeds in `queue/winners/<network>.txt`, for example:
  - Instagram: `country for having fun`, `sunset`, `luxury hotel`;
  - TikTok: `squirrel`, `calisthenics influencer`, `sneaker brand`;
  - LinkedIn: `us company`, `ceo`;
  - Bluesky: `ai lab`, `football club`.
- They're drawn in file order, never repeated, English and bare.
- After the honest run, the verdict is looked up in `queue/winners/handles.json`. Only
  handles a human verified are ever used; unknown or unverified winners post with no
  tag.

**Guardrails:**
- Never alter or reroll a verdict to reach a bigger account.
- Minors and private individuals are withheld (the verdict stays frozen and nothing
  posts). Politics is allowed, including a public figure such as Elon Musk.
- The oracle's `no` posts nothing.
- No competitor filter and no personal-conflict filter. A verdict that names a
  client's competitor still posts.
- **≤ 2 winner posts a day across all networks** (`PUBLISHER_WINNER_CAP`).
- The blind queue and the 1-in-4 unowned rhythm are unchanged; winners are a
  separate lane.

**Sibling: the reverse oracle** (below) picks the winner first. Winner seeds stay
the blind, main version.

**`ceo` → Elon Musk publishes.** Politics is not a withhold (founder, 2026-09-25).
The caption is `@elonmusk` on TikTok or Instagram only after a human verifies that
account. Nothing is tagged with a `#hashtag`.

## Reverse oracle (Carlos, 2026-09-25 00:52; exploration, not the main line)

**The idea.** Output first:
1. Pick a high-reach winner (a brand, a company, or a person in a neutral category).
2. Privately find a short, natural input that makes the oracle name them.
3. Publish **one fresh live run** of that input, and tag the winner (or, on Bluesky,
   reply to one of their posts with the clip) only if that fresh run names them.

Example: target Bad Bunny, candidate `reggaeton artist`.

**The tension, stated plainly.** Our locked rule is "humans choose inputs, nobody
chooses verdicts, and a test ask spends the input". Searching for inputs by the
winner they produce is a form of choosing, and it's what Soul's "never sort by which
brand might repost" was guarding against. Carlos's honesty rule is the line that
keeps it true. We run it as a **separate, logged lane**; the blind queue, pools,
trends and winner seeds stay exactly as they are.

**Honesty rule (non-negotiable; Soul co-signs):**
- **Search is private and logged:** every search ask goes to
  `state/reverse/<target>.csv` (input, verdict, time).
- **Search verdicts are not frozen in `verdicts.csv`.** So the published run is a
  **new** oracle call, not a replay of the search.
- **The published clip is that fresh run, filmed as is:** no splice, no edit, no
  reroll on camera.
  - If the fresh run doesn't name the target: post it **untagged** (default) or not
    at all (`PUBLISHER_REVERSE_ON_MISS=skip`).
  - Either way, the input is spent, as always.
- **The input must be something a person could plausibly type:**
  - ≤ 55 characters, ≤ 6 words, English, bare, never "best";
  - no target name, no year or birth date, no contrived qualifiers ("… from puerto
    rico born 1994").
- **Never a target who is** a private individual or a minor. Politicians are
  allowed. A tragedy is not a reason to skip a reverse-oracle target (the
  disaster filter lives only in the trend lane, and is flagged for confirmation).

**Design:**
1. **Target list builder (free signals only).**
   - **Reach:**
     - Bluesky `app.bsky.actor.getProfile` gives follower counts (public, no login;
       e.g. bsky.app has 35M).
     - Wikipedia pageviews (REST API) give a person's or brand's attention;
       most-read gives what's trending.
     - Instagram follower counts of other *business* accounts come free through the
       Graph API's `business_discovery`, once our Meta app exists.
     - TikTok has no free API for other accounts: we use Wikipedia/Wikidata as the
       proxy.
   - **Brand vs person, and the exclusions, come from Wikidata** (free):
     - `P31 = human` → person;
     - date of death → skip;
     - birth date under 18 years ago → skip.
     Occupation and political office are not exclusions.
   - **Official handles:** Wikidata lists them (Instagram `P2003`, TikTok `P7085`,
     X `P2002`). Duolingo has six Instagram handles, for example, so these are
     candidates only. A human verifies the main account before `handles.json` gets
     `verified: true`, the same as the winner lane.
2. **Inverse search (offline, private).**
   - An agent (CoS or a Cloud Agent, not a paid LLM API) proposes up to **10
     candidate inputs per target**.
   - `mill reverse search` (to build) scores each candidate, then asks the real
     oracle for the top candidates, one call each, logging everything. It stops at
     the first natural hit or at 10 calls.
   - **Naturalness score:** word count, no digits, no target tokens, no
     "from/born/who/that" clauses, and a plain-noun head.
   - **Hit:** the verdict equals the target or one of its aliases.
   - **Budget:** ≤ 10 oracle calls per target, ≤ 100 per week. Every call is logged
     with its time.
   - The oracle's per-call cost is still unknown. That's the Show HN gate question,
     so confirm it before scaling past the dry run. Agent proposal time is inside
     the €500/month compute ceiling.
3. **Publish:** the chosen input goes into `queue/reverse_trial.csv` (network, target,
   input). The publisher posts it in a normal slot, with **one fresh live run**.
   - Tag rule: the fresh verdict names the target **and** its handle is verified →
     tag. Otherwise untagged, or skip.
   - Reverse posts **share the winner-lane cap** (≤ 2 a day across networks), so the
     two prestige lanes together stay small.
4. **Engagement actions, per network:**
   - **Instagram and TikTok:** a tag in the caption only. Their APIs can't reply to a
     post with a video.
   - **Bluesky:** a domain-handle tag, or one reply-with-clip to the target's latest
     post. That reply counts toward the ≤ 3/day reply cap and follows the reply-lane
     rules (fresh top-level post, never unsafe, one per author per week).
   - **LinkedIn:** untagged until organization mentions exist.
   - **X:** design only (the API is paid).

**First 10-target dry run:** see `BACKLOG.md` → Reverse oracle.

## Decision: Bluesky is the one stand-in for held X

**Bluesky is the single stand-in for the X vertical.** Threads, Mastodon, Reddit and
YouTube stay in reserve.

Conditions (all enforced in code unless marked):
- **Posts the same frozen 9:16 verdict video the mill renders** (about 5–8s, pause included). No text-only
  posts, no screenshots, no threads, no replies, follows, reposts or likes.
- **Inherits X's brief:** companies / tech, plus unowned words.
  Queue: `thing`, `password manager`, `silence`, `note-taking app`, `a year`.
- **Freezes when X unholds,** so one vertical never runs on two networks. Adding
  `x` to `PUBLISHER_LIVE_NETWORKS` stops Bluesky.
- **3 a day under `soul`** (09:07, 13:07, 18:07 ET), or 5 under `carlos`. The first
  post goes out at the first open slot after go-live.
- *Profile (human steps):*
  - handle `antisearch.ai` via DNS TXT (`antisearch.bsky.social` meanwhile);
  - avatar = the cursor block `#E8E4D8` on `#0A0A0A`
    ([`docs/assets/bluesky-avatar.png`](assets/bluesky-avatar.png)); the plain black
    square was vetoed;
  - bio `ai chooses the best. nothing else.`
- **Reviewed at day 21** against Pulse.

**Reserve, with the reason for each:**
- Threads: a Meta developer account on Carlos's Facebook, plus a media host.
- Mastodon: small reach.
- Reddit: API closed to new apps.
- YouTube Shorts: no adapter, and uploads from unverified API projects stay private.
- GitHub README, Are.na: new surfaces we don't need yet.

**The publisher adapters stay regardless.**

---

## Ranked

Status: **now** = this week; **vertical** = a locked vertical behind a wall;
**reserve** = not opened; **killed** = don't do.

| Rank | Idea | The move, in one line | Status |
| --- | --- | --- | --- |
| **1** | **Unowned words** (Soul) | Bare words no brand owns, asked once, posted untagged; `thing` opens the Bluesky wall | now |
| **2** | **Brands see themselves** (Soul) | The crowned brand's verified @handle is the caption, and the only outreach | now (TikTok; Bluesky with domain handles) |
| **3** | **Show HN, cold, once** | One plain post by Carlos; no replies in the thread; gated on the og fix and the cost check | now, gated |
| 4 | Handle = domain | `@antisearch.ai` on Bluesky | now |
| 5 | Contested inputs | Crowns for things people argue about, inside each vertical brief, no comment | now |
| 6 | TikTok | Beauty inputs at the TikTok slots: bridge (public) until a native path can post publicly | vertical, works |
| 7 | Employer verdicts, zero copy | LinkedIn verdict clip, no words | vertical, blocked |
| 8 | Ask by mention, once a day | Mention with a thing, get the verdict in a daily batch | reserve (edge of "no chat") |
| 9 | One-word README | A public repo whose README is today's verdict | reserve |
| 10 | Are.na channel | Verdict frames, one a day | reserve |
| 11 | Fediverse bot | A Mastodon bot mirroring the wall | reserve |
| — | Terminal oracle | Publishing a command-line call to the API | **killed**: an open API invite pulls reruns, top-N scraping and cost |
| — | Nouns from the news | Crown whatever trends | **killed**: a stunt |
| — | Urban Dictionary entry | Define "antisearch" | **killed**: self-promotion dressed as content |
| — | Handwritten index card | A card on community boards | **killed**: a stunt |

**Pre-kills (Soul's, accepted):**
- replying to "what's the best X" threads with screenshots;
- stickers or QR codes;
- stunts, countdowns, founder-story posts;
- any "we asked ai" framing.

**Also killed:** share cards, carousels, explainer threads, captioned memes,
hashtags, influencer DMs, giveaways, "best X" SEO pages, anything paid, and
thanking or reposting brands that repost us.

---

## Top 3 this week: first actions, drafted verbatim

### 1. Unowned words: the Bluesky wall opens

[`queue/bluesky_trial.csv`](../queue/bluesky_trial.csv), in this order, one a day:

```csv
id,category,platforms,caption,notes
u-thing,thing,bluesky,,unowned; opens the wall
c-password-manager,password manager,bluesky,@?,companies; tag only a verified domain handle
u-silence,silence,bluesky,,unowned
c-note-taking-app,note-taking app,bluesky,@?,companies; tag only a verified domain handle
u-a-year,a year,bluesky,,unowned
```

- First post: the frozen verdict **clip** for `thing`, caption empty, at the first open Bluesky slot.
- Nobody asks the oracle `thing` before that. If the answer isn't `love`, it goes
  out as it is.
- `@?` rows: the live run freezes the verdict and holds. CoS sets the caption to the
  crowned company's verified domain handle, or `-` for none. The next run posts it.

### 2. Brands see themselves: the first tagged crown (TikTok)

- [`queue/tiktok_trial.csv`](../queue/tiktok_trial.csv): input `dry shampoo`, caption
  `@?`.
- The honest run freezes the verdict and holds the row. CoS sets the caption to the
  crowned brand's verified TikTok handle, or `-` if the verdict isn't a brand or has
  no verified account. The next TikTok slot posts it (on the bridge, nobody taps
  anything).
- The rule, verbatim:

```text
caption: only @<the crowned brand's verified TikTok handle>. if the verdict isn't a brand, or it has no verified account, leave the caption empty. nothing else, ever.
```

- No DM, no comment, no follow. If the brand reposts, do nothing.

### 3. Show HN, cold, once (Carlos, own account and device)

Gates:
1. The og fix below is live.
2. Carlos confirms whether a verdict costs LLM money and whether `/verdict` has a
   global cap.

Title:

```text
Show HN: antisearch – one verdict, nothing else
```

URL: `https://antisearch.ai`

First comment, exactly:

```text
ai chooses the best. nothing else.

type a thing. one answer. no list, no reasons, no chat, no account.
```

After posting: **no replies in the thread**, no upvote asks, never reposted. A
weekday, 15:00–16:00 Madrid.

---

## og SHIP proposal (for Carlos; nothing touched in `the_best`)

Live today (checked 2026-09-24):

| Tag | Now |
| --- | --- |
| `<title>` | `antisearch` |
| `og:title` | `type. AI decides` |
| `twitter:title` | `type. AI decides` |
| `og:description`, `twitter:description` | `ai chooses the best. nothing else.` (already right) |
| `og:image`, `twitter:image` (`og-image.png?v=2`) | Renders `type. AI decides`, uppercase "AI" |

Every pasted link on Bluesky, LinkedIn, HN or in DMs shows this card.

**Proposal:**
- `<title>`, `og:title`, `twitter:title` → `antisearch.ai`
- `og:description`, `twitter:description` → `ai chooses the best. nothing else.`
  (unchanged)
- `og:image` + `twitter:image` → a new `og-image.png`: a lone cursor block `#E8E4D8`
  on `#0A0A0A`, no words, 1200×630. URL bumped to `?v=3` so networks refetch.

**Fallback, a one-word diff:** `type. AI decides` → `type. ai decides` in both
titles and on the image.

---

## Publisher status for these rules

- **Landed in PR #5:**
  - one honest run: verdicts are frozen on the `publisher-state` branch, and
    dry-runs never call the oracle;
  - Bluesky video-only with the 9:16 check (about 5–8s);
  - domain-handle tags resolved to real mentions (a dead tag fails the post);
  - the `@?` hold-for-tag flow;
  - 1 post per network per day;
  - the X-unhold freeze.
- **Still waiting:** tagging companies on LinkedIn (organization mentions need the
  Page approval). YouTube stays unbuilt.

## For Carlos

1. **og SHIP:** the proposal, or the one-word fallback?
2. **Cost:** does a verdict cost LLM money, and is there a global cap on `/verdict`?
   This gates Show HN.
3. **Go-live yes** per network: `bluesky`, `tiktok`
   (`PUBLISHER_LIVE_NETWORKS`, `PUBLISHER_CRON=live`).

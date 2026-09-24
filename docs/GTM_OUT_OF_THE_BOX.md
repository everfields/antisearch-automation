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
- Politics, tragedies, minors and private individuals are withheld (the verdict
  stays frozen and nothing posts). Living public figures only in neutral categories.
- The oracle's `no` posts nothing.
- **≤ 2 winner posts a day across all networks** (`PUBLISHER_WINNER_CAP`).
- The blind queue and the 1-in-4 unowned rhythm are unchanged; winners are a
  separate lane.

**One flag for Carlos:** his own example, `ceo` → Elon Musk, would be **withheld**
under the politics guardrail (Musk is marked sensitive in the map). Lifting that is
one line in `handles.json`, and it's his call.

## Decision: Bluesky is the one stand-in for held X

**Bluesky is the single stand-in for the X vertical.** Threads, Mastodon, Reddit and
YouTube stay in reserve.

Conditions (all enforced in code unless marked):
- **Posts the same frozen ≤4s 9:16 verdict video the mill renders.** No text-only
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
  - Bluesky video-only with the ≤4s 9:16 check;
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

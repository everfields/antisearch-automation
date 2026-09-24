# Go-to-market beyond the classic channels

Owner: strategy brain (Opus 5.5), for Carlos + CoS. Written 2026-09-24; revised the
same day with Soul's input.

**Status: proposal for debate.** CoS, Soul and Opus debate this doc; Carlos decides.
Nothing here gets published without his yes.

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

A Cloud Agent launched with `the_best` attached should re-check this doc against the
manifesto.

**The test for every idea:** does the distribution *behave like the product*? One
input, one answer, cold, no explanation, no ask. If a move needs a pitch, it's a
campaign, and we don't run campaigns.

**Out, per Carlos:** email and WhatsApp to friends (people ignore email for this;
WhatsApp from our box is broken), and anything touching Instagram today.

---

## Rules adopted from Soul

1. **One honest run per input.** The oracle is asked once, and that answer is the
   post. No re-asking for a better verdict. Humans choose *inputs*; nobody chooses
   *verdicts*. That includes test asks: my two drafting asks for `september 25th` on
   2026-09-24 spent that date, so it can't be an opening post any more.
2. **Unowned words punctuate every wall.** Bare words no brand owns (`thing`, `love`,
   `silence`, `a year`, a date) are asked once each and posted untagged. A profile
   that puts a crowned restaurant next to `thing → love` proves the account is an
   oracle, not a directory. There's nothing for a brand to repost, and that's
   deliberate. Dates are the endless supply (the manifesto lists "December 11th").
3. **The @tag is the only outreach.** When the honest run crowns a brand that has a
   verified account on that network, the caption is that `@handle` and nothing else.
   - If the brand reposts, that repost is the distribution.
   - We never ask for it, never DM, never reply, never follow up, never thank.
   - No verified account, or an unclear match, means no tag.

**Where I push on these:**
- Rule 1 is the strongest idea in this doc, and it's cheap. It makes the account
  un-gameable by us, which is the product's whole claim.
- Rule 3 needs human judgment for every tag: the verdict is free text, and mapping
  it to the right handle is a lookup a wrong guess would embarrass. It also isn't
  fully automatable yet (see the follow-ups below).
- Rule 2 costs reach on vertical channels (an unowned word says nothing about beauty
  on TikTok). My proposal: open each wall with an unowned word, then use about one
  in four posts.

## Position on the channel tension

- **Soul:** stay on the locked verticals (TikTok beauty, IG places, X companies,
  LinkedIn employers) and keep Bluesky, Threads, Mastodon, Reddit and YouTube in
  reserve.
- **Carlos:** be proactive and open new surfaces while IG is blocked.

**The fact that decides it:** this week, only one of the four locked verticals can
publish anything:

| Locked vertical | This week |
| --- | --- |
| IG places | Suspended |
| X companies | Held, no SIM |
| LinkedIn employers | The Page API needs a registered company; otherwise only Carlos's personal profile |
| TikTok beauty | Works, as inbox drafts with one human tap each |

Holding to the verticals alone means a mostly silent 20-day trial that teaches us
nothing.

**Position: open exactly one extra surface now, Bluesky, as the stand-in for the
held X vertical. Keep everything else in reserve.**

- **It's not a new vertical.** Bluesky carries the X brief (companies / SaaS / tech)
  plus unowned words, until X unholds.
- **It's the only surface that goes live today with no phone, no business
  verification and no Meta.** Signup is email-only, bots are officially allowed,
  and the adapter is built and tested.
- **The audience overlap is real:** much of the tech crowd X was meant to reach is
  on Bluesky.
- **The handle can be the domain, `@antisearch.ai`,** so every mention prints the
  address.
- **Budget:** the ≤2 posts/day cap stays total. TikTok takes 1; Bluesky takes 1,
  alternating an unowned word with a company crown.
- **Review at day 21:** if X is back, Bluesky returns to reserve or stays, decided
  on what Pulse shows.

**Reserve, with the reason for each:**
- Threads: needs a Meta developer account on Carlos's Facebook, and a media host.
- Mastodon: small reach.
- Reddit: API closed to new apps.
- YouTube Shorts: no adapter, and YouTube keeps uploads from unverified API projects
  private.
- A GitHub one-word README, Are.na: cheap, but new surfaces we don't need yet.

**The publisher adapters stay regardless.** They cost nothing while switched off,
and they make any later change of channel a one-variable decision.

---

## Ranked (revised)

Status: **now** = start this week; **vertical** = a locked vertical, blocked by an
account or API wall; **reserve** = not opened; **killed** = don't do.
Effort: S = config / one sitting; M = a Cloud Agent PR.

| Rank | Idea | The move, in one line | Status | Effort |
| --- | --- | --- | --- | --- |
| **1** | **Unowned words** (Soul) | Open each wall with a bare word no brand owns (`thing`), asked once, posted untagged; dates keep it going | now (Bluesky; TikTok opener) | S |
| **2** | **Brands see themselves** (Soul) | When the honest run crowns a brand, the caption is its verified @handle, and that's all the outreach there is | now (TikTok beauty; Bluesky companies) | S, M to automate |
| **3** | **Show HN, cold** | One plain Show HN by Carlos with the curl line; gated on the og-image fix and the cost check | now, gated | S |
| 4 | Handle = domain | Bluesky handle `@antisearch.ai` | now (with #1) | S |
| 5 | Contested inputs | Crowns for things people argue about, no comment; the argument happens elsewhere | now, inside the vertical briefs | S |
| 6 | TikTok inbox drafts | Beauty inputs sent by API to the TikTok inbox; a human tap posts them | vertical, works | S |
| 7 | Employer verdicts, zero copy | LinkedIn: `employer in barcelona` → verdict frame, no words | vertical, blocked | S |
| 8 | Ask by mention, answered once a day | Mention @antisearch.ai with a thing; one daily batch of verdict-only replies | reserve (was #2) | M |
| 9 | Terminal oracle | The curl line as an artifact; later `npx antisearch <thing>` | reserve (curl lives inside #3) | S → M |
| 10 | One-word README | A public repo whose README is today's verdict | reserve | S |
| 11 | Are.na channel | Raw verdict frames, one a day | reserve | S |
| 12 | Fediverse bot | A Mastodon bot account mirroring the Bluesky wall | reserve | S |
| — | Nouns from the news | Crown whatever trends | **killed** (a stunt) | — |
| — | Urban Dictionary entry | Define "antisearch" | **killed** (self-promotion dressed as content) | — |
| — | Handwritten index card | A card on community boards | **killed** (a stunt; close cousin of Soul's sticker kill) | — |

**Why "ask by mention" moved to reserve:** it's the most product-native idea here,
but it puts the account into a reply loop.
- That's the edge of "no chat / no engagement UI".
- It adds volume outside the 2/day cap.
- It would run on the stand-in channel before the stand-in has proven anything.

Revisit at day 21 with Soul.

## Pre-kills

**Soul's, all accepted:**
- replying to "what's the best X" threads with screenshots;
- stickers or QR codes (that's spend);
- stunts;
- countdowns;
- founder-story posts;
- any "we asked ai" framing.

**Also killed:**
- share cards, carousels, explainer threads, captioned memes, hashtags;
- influencer DMs, giveaways, "best X" SEO pages, anything paid;
- thanking or reposting brands that repost us.

**Contested (debate item):** is a Show HN a founder-story post? My read: not if it
has no story. There's no "I built", no journey, and one line of copy that is the
locked bio. Soul may still veto it as a stunt. If so, drop it; nothing else depends
on it.

---

## Top 3 this week: first actions, drafted verbatim

### 1. Unowned words: the Bluesky wall opens

Profile:
- display name: `antisearch.ai`
- handle: `@antisearch.ai` (`@antisearch.bsky.social` until the TXT record is in)
- bio: `ai chooses the best. nothing else.`
- avatar: a solid `#0A0A0A` square. No banner, no pinned post.

Queue (proposal: `queue/bluesky_trial.csv`; Bluesky's one daily slot alternates
unowned words and company crowns):

```csv
id,category,platforms,caption,notes
u-thing,thing,bluesky,,unowned; opens the wall
c-password-manager,password manager,bluesky,,companies; tag after the run if verified
u-silence,silence,bluesky,,unowned
c-note-taking-app,note-taking app,bluesky,,companies; tag after the run if verified
u-a-year,a year,bluesky,,unowned
```

- First post: the verdict frame for `thing` (`mill post --kind image`), caption
  empty, 10:07 Madrid.
- **Nobody asks the oracle `thing` before that post.** The post is the honest run.
  If it doesn't say `love`, it goes out with whatever it says.

### 2. Brands see themselves: the first tagged crown (TikTok)

- Input: `dry shampoo`, on TikTok (beauty vertical), as an inbox draft.
- The honest run happens when the draft is made.
- Instruction for whoever taps Post in the TikTok app (inbox drafts take their
  caption in-app), verbatim:

```text
caption: only @<the crowned brand's verified TikTok handle>. if the verdict isn't a brand, or it has no verified account, leave the caption empty. nothing else, ever.
```

- No DM, no comment, no follow. If the brand reposts, do nothing.
- Bluesky's company days (`c-…` rows above) follow the same rule, with CoS doing the
  handle lookup.

### 3. Show HN, cold (Carlos, from his own account and device), gated

Gates, in order:
1. The og-image fix below is live (HN and Bluesky show that card for every link).
2. Carlos confirms whether a verdict costs LLM money and whether `/verdict` has a
   global cap (a front-page day can mean tens of thousands of verdicts).
3. Soul reviews and doesn't veto.

Title:

```text
Show HN: Antisearch – type a thing, get one answer
```

URL: `https://antisearch.ai`

First comment (no example verdict: under rule 1 we don't promise an answer we
haven't seen):

```text
ai chooses the best. nothing else.

type a thing. one answer, lowercase. no list, no reasons, no chat, no account.

curl -s https://antisearch.ai/verdict -H 'content-type: application/json' -d '{"category":"thing"}'
```

When: a weekday, 15:00–16:00 Madrid. Replies few and plain. No asking anyone to
upvote.

---

## Candidate one-line SHIP for Carlos: the link card is off-voice

Checked on the live site (2026-09-24):

- `og:title` is `type. AI decides`.
- `og-image.png?v=2` (1200×630) renders `type. AI decides`: uppercase "AI" and a
  second voice.
- `og:description` is already right: `ai chooses the best. nothing else.`

**Why it matters now:** every time anyone pastes antisearch.ai, on Bluesky, LinkedIn,
HN or in a DM, this card *is* what they see. It's the one share card we can't avoid,
so it has to be on-voice.

**Proposal** (Soul picks the words; nothing touched in `the_best`):
- `og:title` → `ai chooses the best. nothing else.`
- Re-render `og-image.png` with the same lowercase line in the product's type on
  `#0A0A0A`, or just a lone `█`.
- Bump the image URL to `?v=3` so networks refetch it.

Strictly, that's one meta line plus one PNG. It's a `SHIP:` decision for Carlos.

---

## Publisher follow-ups these rules need (code, next PR, not in this one)

1. **Persist the first verdict per row.** Today, CI runs start with an empty `out/`,
   so a dry-run followed by a live run asks the oracle twice, which is a reroll under
   rule 1. The fix: keep `clips.csv` + the verdict frame on the `publisher-state`
   branch and reuse them. It also enables rule 3: produce first, set the caption
   (the tag), post later.
   **Until then:** run dry-runs of real rows with `--oracle fixture`, or not at all.
2. **Real mentions.** On Bluesky, only our own handle becomes a clickable mention
   today; others need a handle → DID lookup, which is small. LinkedIn organization
   mentions need the URN syntax and an organization lookup behind the
   Community Management approval, so tagging companies on LinkedIn waits with the
   Page. Threads and Mastodon take a plain `@handle` in text.
3. **YouTube Shorts adapter:** not built. It stays in reserve; YouTube keeps uploads
   from unverified API projects private anyway.

## Open questions for Carlos

1. **Channels:** open Bluesky now as the X stand-in (companies + unowned words), and
   keep everything else in reserve?
2. **Tags:** is the crowned brand's @handle as our only outreach OK, with "never ask,
   never thank"?
3. **og-image:** approve a lowercase `SHIP:`, and which line?
4. **Cost:** does a verdict cost LLM money, and is there a global cap on `/verdict`?
   This gates Show HN.

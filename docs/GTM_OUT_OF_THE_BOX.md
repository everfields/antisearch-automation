# Go-to-market beyond the classic channels

Owner: strategy brain (Opus 5.5), for Carlos + CoS. Written 2026-09-24. Drafts only:
nothing here gets published without Carlos's yes.

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

## Ranked

Effort: S = one sitting or a few lines of config; M = a Cloud Agent PR.
"Today" = can start today without Instagram.

| Rank | Idea | The move, in one line | Effort | Today |
| --- | --- | --- | --- | --- |
| **1** | **The word for today** | Every day at the same minute, @antisearch.ai posts the verdict frame for today's date as the input (`september 25th`) | S | Yes, once Bluesky exists |
| **2** | **Ask by mention, answered once a day** | Mention @antisearch.ai with a thing; once a day the oracle replies with the verdict, nothing else | M | This week (code first) |
| **3** | **Show HN, with the terminal line** | One plain Show HN post by Carlos; the first comment is a curl one-liner that returns one word | S | Yes, after the cost check below |
| 4 | Handle = domain | The Bluesky handle is `@antisearch.ai`, so every mention and repost prints the address | S | Yes |
| 5 | Contested inputs | Second daily slot: verdicts for things people fight about (`pizza topping`, `football player`, `city`), no comment | S | Yes |
| 6 | One-word README | A public GitHub repo whose README is one lowercase word, today's verdict, replaced daily by Actions | S | Yes (needs a public repo) |
| 7 | Terminal oracle | Post the curl line as its own artifact; later an `npx antisearch <thing>` that prints the verdict | S → M | Yes (curl); npm later |
| 8 | Are.na channel | A public Are.na channel of raw verdict frames, one a day, for the anti-algorithm design crowd | S | Yes |
| 9 | Fediverse bot | A Mastodon account flagged as a bot, mirroring the word for today (adapter already built) | S | Yes |
| 10 | Employer verdicts, zero copy | LinkedIn: `employer in barcelona` → verdict frame, no commentary, the only corporate post with no words | S | Only as Carlos's profile (Page API blocked) |
| 11 | TikTok inbox drafts | Beauty inputs (`dry shampoo`, `sunscreen`) sent by API to the TikTok inbox; Carlos's tap is the only human act | S | After the TikTok sitting |
| 12 | Urban Dictionary entry | Define "antisearch" in one line in the product's voice | S | Yes |
| 13 | Nouns from the news | When a thing trends, post the verdict for the bare noun that day, no comment | S | Yes (brand-fight risk) |
| 14 | Index card | A handwritten card, `thing` above and `antisearch.ai` below, pinned where community boards allow it | S (human) | Yes |

### Why each fits, what it needs

1. **The word for today.**
   - *Fits:* the manifesto's own input list includes "December 11th". A date is the
     purest broad input: no category, no frame, and the oracle still returns one
     thing (for `september 25th` it answered `little rock nine’s school integration`).
     Same time daily is the monolith: almost boring, and that's the point.
   - *Needs:* the Bluesky account (sitting step 1), queue rows (CoS generates them),
     `mill post --kind image`. No code.
2. **Ask by mention, answered once a day.**
   - *Fits:* it is the product, living inside the network. It's not chat: one input,
     one answer, no follow-up, no thread. The daily batch keeps it cold (the oracle
     doesn't hurry) and costs one workflow run.
   - *Needs:* a `mill answer` command (Bluesky notifications → mentions only → text
     after the handle, 1–55 chars → oracle → reply with the verdict only); Bluesky
     "bot" self-label; **Carlos's yes that replies to mentions sit outside the 2
     posts/day cap** (capped separately, e.g. ≤ 50/day).
3. **Show HN, with the terminal line.**
   - *Fits:* HN rewards things that do one thing, and a `curl` that returns one
     word is the rawest possible screenshot.
   - *Needs:* Carlos's HN account, from his own device; nothing from us.
   - *Gate:* a front-page day can mean tens of thousands of verdicts. **Confirm
     whether each verdict costs LLM money, and whether there's a global cap,
     before posting.** "No spend, ever" includes surprise API bills.
4. **Handle = domain.** *Fits:* the address is the ad, and there's nothing else to
   read. *Needs:* one TXT record in Cloudflare (PUBLISHER_SETUP → Bluesky step 4).
5. **Contested inputs.** *Fits:* a flat, final verdict with no reasons invites the
   argument to happen elsewhere (quotes and replies), without us asking. *Needs:*
   queue rows; Soul picks.
6. **One-word README.** *Fits:* a repo that is only one word is the cold monolith
   in the developer's native medium; people star strange, quiet things. *Needs:* a
   public repo (Carlos or CoS), a tiny scheduled workflow. The git history holds
   past days, but the page never lists them.
7. **Terminal oracle.** *Fits:* no UI at all is the anti-fancy extreme. *Needs:*
   nothing for curl (the API is public, 30/min per IP). `npx` needs an npm account
   (email + TOTP in 1Password) and a Cloud Agent PR. Same cost gate as #3.
8. **Are.na channel.** *Fits:* Are.na is the one platform whose culture already is
   "no engagement UI". *Needs:* a signup [own device]; posting by hand or a later
   adapter (Are.na has a token API).
9. **Fediverse bot.** *Fits:* the fediverse welcomes labeled bots. *Needs:* a
   Mastodon account (PUBLISHER_SETUP #7); the adapter is done. It shares the 2/day cap.
10. **Employer verdicts.** *Fits:* the vertical lock (LinkedIn = employers), and on
    LinkedIn silence stands out most. *Needs:* Page API approval, or Carlos's yes
    to post as himself.
11. **TikTok inbox drafts.** *Fits:* the vertical lock (TikTok = beauty). *Needs:*
    the TikTok sitting steps; a human tap per post.
12. **Urban Dictionary.** *Fits:* a definition is one line, and people who search
    the word find it. *Needs:* a human submission; moderation may reject it.
13. **Nouns from the news.** *Fits:* timely without commentary. *Risk:* the verdict
    may name a competitor of the trending thing. That's attention, but Carlos
    should decide the class once.
14. **Index card.** *Fits:* a whisper in physical space. *Needs:* Carlos's hand,
    about zero cost. Low reach; do it only if it feels right.

**Won't do:** share cards, carousels, explainer threads, captioned memes, hashtags,
influencer DMs, unsolicited replies to "what's the best X" posts (that's spam, even
when it's clever), SEO pages in the "best X" shape, giveaways, anything paid.

---

## Top 3 this week: first actions, drafted verbatim

### 1. The word for today (Bluesky)

Profile:
- display name: `antisearch.ai`
- handle: `@antisearch.ai` (`@antisearch.bsky.social` until the TXT record is in)
- bio: `ai chooses the best. nothing else.`
- avatar: a solid `#0A0A0A` square. No banner, no pinned post.

Queue row to add (`queue/bluesky_daily.csv`, after the yes):

```csv
id,category,platforms,caption,notes
2026-09-25,september 25th,bluesky,september 25th,word for today
```

First post: the **verdict frame** (`mill post --kind image`) with the caption
`september 25th`, at 10:07 Madrid (the workflow's first cron slot).
- For reference, the oracle answered this input with `little rock nine’s school
  integration` on 2026-09-24 at 18:25 UTC, and `little rock nine’s integration of
  central high` five minutes later. It's asked again at post time, and whatever it
  says then is what goes out.
- Cadence: this uses 1 of the 2 daily slots; #5 takes the other.

### 2. Ask by mention, answered once a day (Bluesky)

Pinned post text, the only explanation ever given:

```text
mention @antisearch.ai and a thing. the answer comes once a day.
```

Reply format, every time: the verdict and nothing else, e.g. a mention
`@antisearch.ai dry shampoo` gets a reply that is only the lowercase verdict.

Rules for the `mill answer` PR:
- only direct mentions;
- the input is the text after the handle, 1–55 characters, otherwise no reply;
- one reply per mention, never a reply inside a reply chain;
- ≤ 50 replies a day, one batch a day;
- idempotent on the mention's URI;
- oracle `no` goes out as `no` (that is the product's answer).

**Needs Carlos's yes on replies sitting outside the 2 posts/day cap.**

### 3. Show HN (Carlos, from his own account and device)

Title:

```text
Show HN: Antisearch – type a thing, get one answer
```

URL: `https://antisearch.ai`

First comment:

```text
ai chooses the best. nothing else.

you type a thing. it answers once, in lowercase. no list, no reasons, no chat, no account.

thing → love

from a terminal:
curl -s https://antisearch.ai/verdict -H 'content-type: application/json' -d '{"category":"thing"}'
```

- **When:** a weekday, 15:00–16:00 Madrid (morning on the US East Coast). Only
  after the cost check in #3 above.
- **Replies:** few and plain, in the same voice.
- **No asking anyone to upvote** (HN penalizes it, and it's a campaign).

## Open questions for Carlos

1. Does a verdict cost LLM money, and is there a global cap on `/verdict`? This
   gates #3 and #7.
2. Replies to mentions outside the 2/day cap (≤ 50/day, once a day): yes or no?
   This gates #2.
3. OK to publish the curl line, which invites people to call the API directly?

# Growth ideas, 2026-09-25

Proposal only. Nothing in this file is built, queued, or asked of the oracle.
A product change (new route, new host on `antisearch.ai`, og tags) is `SHIP:`
and needs a founder yes. Do not merge this until Carlos reviews it.

The test is the one already in `docs/GTM_OUT_OF_THE_BOX.md`: the distribution
behaves like the product. One input, one lowercase verdict, no list, no pitch.
"best" stays the hidden premise and is never typed or posted
(`README.md` → Input shape).

---

## A. LinkedIn text posts, one line per category

**Evaluation.** LinkedIn will take the post. The brand will not.

A list of `best company in france: X` lines is the thing the constitution
refuses: "best" in the line, more than one verdict, a directory. Company vs
company-to-work-for is a real distinction (the firm vs the place employees
would pick). Putting both in one post makes a comparison, which is a list of
two. LinkedIn's feed likes that shape. That fit is the reason to skip it.
The Page already has a slot for employer verdicts, and the move on the books
is a clip with no words (`GTM` rank 7), not a text list.

One live call per line and no reroll is the right *asking* rule. It does not
make a list a legal post.

**Recommendation.** Do not post lists. Do not post the word "best". If a text
experiment is wanted later, it replaces the clip for that one slot, it is one
input, and it needs an explicit yes because the caption ritual today is empty
or an `@handle`:

```text
company in france
<one lowercase verdict>
```

Nothing else. The two France inputs would be two posts on two days, never side
by side. Asking any line below spends that input forever, so none were asked.

### Example sets (not run; verdicts left blank)

Set 1, country:

| input | verdict |
| --- | --- |
| `company in france` | |
| `company to work for in france` | |

Set 2, city:

| input | verdict |
| --- | --- |
| `company in paris` | |
| `company to work for in paris` | |

Set 3, industry:

| input | verdict |
| --- | --- |
| `airline` | |
| `airline to work for` | |

---

## B. Programmatic SEO

**Evaluation.** The old project worked because of the parts this chapter
forbids. ~500k Amazon categories, a top-3, three long-tail Q&As, affiliate
links in 12 markets, <500 EUR, then abandoned. Under the constitution a page
is one lowercase verdict: no top-3, no citations, no Q&A, no affiliate, no
chat. That page is a generative URL with nothing a searcher can use except
the word. Google's spam policy calls that scaled content abuse: many pages
generated to manipulate rankings, including generative AI pages without added
value for users
([spam policies](https://developers.google.com/search/docs/essentials/spam-policies#scaled-content),
last updated 2026-08-28 UTC). Using a model is not itself the violation. A
tree of thin verdict URLs, published to be indexed, is the pattern in the
example list.

| Risk | What it actually is |
| --- | --- |
| Scaled content abuse | The compatible page has no added value. A manual action hits the host. |
| Crawl budget | One new site with 1k–500k URLs spends Google's attention on the thinnest URL it owns. |
| Brand dilution | `antisearch.ai` is one input box. `/best/<category>` turns it into a ranking site, which the manifesto names as what this is not. |
| Oracle cost × N | The model vendor is unknown from this repo (`everfields/the_best` 404). PR [#7](https://github.com/everfields/antisearch-automation/pull/7) `docs/COST_PER_VIDEO.md` (2026-09-25): the HTTP call is $0; the vendor line is unknown; measured latency about 1.6–3.0s, and 2458 ms for `thing`. 1,000 pages = 1,000 × unknown. 500,000 = 500,000 × unknown. The old <500 EUR figure is a different prompt on a different API. It is not a forecast. |
| Hosting | Checked 2026-09-25: `GET https://antisearch.ai` is one HTML document, 10,062 bytes, `last-modified` 2026-09-20, `server: uvicorn`. DNS `20.72.112.112`, AS8075 Microsoft, Boydton VA. There is no page tree. Static files are the cheap part. Serving them from this app is a change to `the_best`. |

**Path.** Not `/best/` on the apex. A penalty or a directory URL would be the
product. A subdomain isolates the crawl and still is a directory. The path
does not make the page constitution-compatible.

**Recommendation.** Do not build it. A pilot exists only after `SHIP:` and a
founder yes, and then only as: a subdomain, **1,000 pages**, one live call
each, no reroll, one lowercase verdict, no second block of text. 500k is the
abandoned project, not a pilot.

**Success metric.** Not "pages indexed". That was the old win and it is the
abuse pattern. Success is no manual action in Search Console, plus clicks
that end with a person typing on `antisearch.ai`. Kill on a manual action, or
if indexation is the only result.

---

## C. Free channels that are not the social walls

Spend stays zero. A fee, a boost, or a bought mention is out.

### Hacker News

**Why Show HN is still blocked.** Both gates in `docs/GTM_OUT_OF_THE_BOX.md`
and `docs/BACKLOG.md` are open. Rechecked live on 2026-09-25: `<title>` is
`antisearch`, `og:title` and `twitter:title` are `type. AI decides`,
`og-image.png?v=2`. The per-verdict model cost and any global cap on
`/verdict` are still unknown (`the_best` is not readable here).

**What is allowed once both are cleared.** Carlos posts once, from his own
device, title and first comment exactly as drafted in the GTM doc, then no
replies and no upvote asks. Not before.

### Reddit

The API is closed to new apps (`docs/GTM_OUT_OF_THE_BOX.md`). A human post is
a different thing, and it is still easy to make it spam.

One sub, one post, the domain only, no tour, no "upvote", no second sub if
the first is removed. The sub that matches a site with no pitch is
`r/InternetIsBeautiful`. Skip `r/SideProject`, `r/startups`, `r/artificial`,
and `r/Entrepreneur`: those want a story. Same two lines as the HN comment,
and only after the og fix, so the card is not `type. AI decides`. It may
still be removed. Do not argue.

### Product Hunt

Free to list. The format is a campaign: tagline, gallery, maker comment.
That fails the "if it needs a pitch, it's a campaign" test. Reach on launch
day can be real and then stops. Effort is a sitting, not five minutes.

### AI tool directories

A form on someone else's directory. The traffic is people browsing tools.
The product is not a feature list, and a tour of directories is a pitch
spread thin. Skip.

### Newsletters

No outbound pitch and no spend. An unprompted mention is fine. Writing one,
or asking for one, is a campaign. Expected reach of waiting is zero until
someone writes. That is acceptable. Do not fill the silence.

### Display / CTV

No earned placement that is not a stunt or a favor from a media owner. Both
are out. We spend nothing, so this is nothing.

### X, free API tier (checked 2026-09-25)

Posting is not free. There is no free write quota.

[X API pay-per-usage pricing](https://docs.x.com/x-api/getting-started/pricing),
read 2026-09-25: pay-per-usage, no subscriptions; credits are bought up front
and deducted per request; at a zero or negative balance, requests are blocked.
Write prices on that page:

| Action | Price |
| --- | --- |
| Post: Create | $0.015 per request |
| Post: Create (with URL) | $0.200 per request |

The 3 million figure on the same page is a **cap on paid Post reads** per
monthly billing cycle, not a free allowance. Prices move; the Developer
Console is the live card. This matches the `$0.015` / `$0.20` already written
in `docs/AUTONOMY_AND_SETUP.md`. X stays held (no SIM). Unholding it is a
spend decision, which this chapter does not make. Bluesky remains the
stand-in.

---

## Ranked by expected organic reach per unit effort

Only the ideas in this note. The clips already on the walls are the
distribution; they are not re-ranked here.

| Rank | Move | Why it wins the unit of effort |
| --- | --- | --- |
| 1 | **Show HN, once, after both gates** | About five minutes of Carlos's time, from his own device, then silence. A front page is the largest honest reach available for that hour. It is blocked today. |
| 2 | **One Reddit post in `r/InternetIsBeautiful`** | Same cold text, after the og fix. Reach is smaller and more likely to be removed. Still one post, no tour. |
| 3 | **One Product Hunt listing, only if 1 and 2 are done and the listing can stay the same two lines** | Launch-day visits are real. The format pushes a gallery and a comment thread, so reach per hour is worse, and it drops off if it cannot be left alone. |

Below the line, in order of how fast they should be forgotten:

- **LinkedIn lists (A).** Feed-shaped, brand-wrong. The Page already has a clip slot.
- **Directories, newsletters, display/CTV.** A tour, a pitch, or a stunt. No free reach that behaves like the product.
- **X API.** Not free. A URL post is $0.20. Out while spend is zero.
- **Programmatic SEO (B).** The compatible page should not rank. The version that ranked is forbidden. Cost per URL is an unknown model bill, and a manual action lands on the domain. Worst reach per unit of effort and per unit of risk.

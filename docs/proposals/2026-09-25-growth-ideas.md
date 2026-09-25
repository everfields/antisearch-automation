# Growth ideas, 2026-09-25

Proposal only. Nothing in this file is built, queued, or asked of the oracle.
A product change (new route, new host on `antisearch.ai`, og tags) is `SHIP:`
and needs a founder yes. Do not merge this until Carlos reviews it.

The test is the one already in `docs/GTM_OUT_OF_THE_BOX.md`: the distribution
behaves like the product. One input, one lowercase verdict, no list, no pitch.
"best" stays the hidden premise and is never typed or posted
(`README.md` → Input shape). Politics stays allowed. This note adds no
politics filter.

---

## A. LinkedIn text posts, one pair per post

**Format lock.** Soul, 2026-09-25, approved by CoS. One post is one pair of
live calls, not a list. Lowercase. No header, no link, no hashtag, no emoji,
no colon. The input is one line and the verdict is the next. A blank line
sits between the two members of the pair. Shape only, `x` and `y` are not
verdicts:

```text
company in france
x

company to work for in france
y
```

**Evaluation.** A pair is the company, then the place to work: two honest
runs, no reroll, and it stops at two. A third line would be the list this
lock refuses. "best" stays untyped. It is still not the clip, which is one
verdict and no words (`GTM` rank 7). The Page's caption today is empty or an
`@handle`, so this text replaces that ritual only with an explicit yes.
Nothing below was asked. Asking a line spends that input forever.

**Recommendation.** If A is posted, this shape only. One pair per post. Do
not post it until Carlos reviews this note.

### Example sets (not run; verdict lines blank)

Set 1, country:

```text
company in france
<blank>

company to work for in france
<blank>
```

Set 2, city:

```text
company in paris
<blank>

company to work for in paris
<blank>
```

Set 3, industry:

```text
airline
<blank>

airline to work for
<blank>
```

`<blank>` is an empty line. It is not a verdict.

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
| Crawl budget | At 1k–500k thin URLs the quality ratio is the problem, not Google running out of crawl. See SEO plan v0. |
| Brand dilution | `antisearch.ai` is one input box. `/best/<category>` turns it into a ranking site, which the manifesto names as what this is not. |
| Oracle cost × N | The model vendor is unknown from this repo (`everfields/the_best` 404). PR [#7](https://github.com/everfields/antisearch-automation/pull/7) `docs/COST_PER_VIDEO.md` (2026-09-25): the HTTP call is $0; the vendor line is unknown; measured latency about 1.6–3.0s, and 2458 ms for `thing`. 1,000 pages = 1,000 × unknown. 500,000 = 500,000 × unknown. The old <500 EUR figure is a different prompt on a different API. It is not a forecast. |
| Hosting | Checked 2026-09-25: `GET https://antisearch.ai` is one HTML document, 10,062 bytes, `last-modified` 2026-09-20, `server: uvicorn`. DNS `20.72.112.112`, AS8075 Microsoft, Boydton VA. There is no page tree. Static files are the cheap part. Serving them from this app is a change to `the_best`. |

**Path.** Not `/best/` on the apex. Host choice, and the fact that a subdomain
does not fence off a penalty, are in SEO plan v0. The path does not make the
page constitution-compatible.

**Recommendation.** Do not build it. The pilot shape and the go / not now /
never call are in SEO plan v0. 500k is the abandoned project, not a pilot.

**Success metric.** Not "pages indexed". That was the old win and it is the
abuse pattern. Success is no manual action in Search Console, plus clicks
that end with a person typing on `antisearch.ai`. Kill on a manual action, or
if indexation is the only result.

---

## SEO plan v0

The old Amazon-category tree indexed fast (100k+ pages) and Google then
deindexed it. The founder's guess: identical HTML, and the same title / meta
pattern with the category swapped in. He still likes the scale. This is the
tweezers pass. No pages and no oracle calls. A build is `SHIP:` plus a yes.
We cannot buy a domain.

### 1. Likely causes of that deindexation

Fast indexing is not approval. Google crawls new URLs, then drops spam.
Most of that is automatic. A manual action is the extra case, and it is
visible in Search Console
([manual actions](https://support.google.com/webmasters/answer/9044175)).

The title-pattern guess is a real mechanism. It is not the whole cause.
Rewriting titles and leaving the tree would still be the same violation.

| Cause | What it was on that project | Source |
| --- | --- | --- |
| Scaled content abuse | Many pages generated to rank. One template, a model filling the slot, little value beyond the swap. | [Spam policies](https://developers.google.com/search/docs/essentials/spam-policies#scaled-content), updated 2026-08-28. [Gen-AI guidance](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content), updated 2025-12-10: generating many pages without added value can be that policy, and it names titles and meta descriptions as part of the content. It points at rater guidelines 4.6.5 and 4.6.6 (low effort, low originality, no added value). |
| Doorway pages | Substantially similar pages, one per query, closer to a result list than to a site. Identical HTML with a swapped category is that. | [Doorway abuse](https://developers.google.com/search/docs/essentials/spam-policies#doorways) |
| Thin duplicate template | Cookie-cutter pages. The old ones also had affiliate links, which is the thin-affiliation pattern. The thin-content manual action names doorways and pages with little or no added value even as a separate item. | [Thin affiliation](https://developers.google.com/search/docs/essentials/spam-policies#thin-affiliate-pages). [Manual actions](https://support.google.com/webmasters/answer/9044175), thin content with little or no added value. |
| Crawl-to-quality ratio | 100k thin URLs and no other inventory. Google tries to crawl URLs it knows about. Duplicates and unimportant URLs waste that crawl. Demand also depends on page quality. | [Crawl budget](https://developers.google.com/search/docs/crawling-indexing/large-site-managing-crawl-budget), updated 2026-07-22. That doc's "you have a crawl-budget problem" bar is about 1M pages, or 10k that change daily. The deindex was quality, not running out of crawl. |

### 2. Blast radius

No second domain is available. This plan does not assume one can be bought.

| Host | Isolation |
| --- | --- |
| Apex, `/best/<category>` | None. Same site as the app. A partial action can name a directory. "Affects all pages" takes the app with it. |
| Subdomain | A separate Search Console property, so the tree can be watched apart from the homepage. Not a penalty fence. Google's caution, written for moving problematic content: a subdomain or subdirectory can be read as circumventing the spam policy and can widen the action against the site ([manual actions](https://support.google.com/webmasters/answer/9044175)). A subdomain **can** hurt `antisearch.ai`. It only lowers the chance that a partial pattern is the homepage. It does not stop a site-wide action or a quality demotion of the brand. |
| Separate domain | The only real cut. Closed, because we cannot buy one. Do not put the tree on someone else's established domain. That exports the problem onto their reputation. |

### 3. Worth indexing, still constitution-compatible

One lowercase verdict. No top-3, no citations, no Q&A, no affiliate, no chat.
"best" stays out of the title, the meta description, and the URL.

The page is the product frame with one frozen answer. The only unique strings
are the input and the verdict. A title of `best {category}` is the pattern
from the deindexed tree, not added value.

The constitution and "worth indexing" conflict. The old pages had substance
because of the top-3 and the three Q&As, and those are forbidden. A paragraph
added so Google has something to index is a different product. If the page
needs that paragraph, it is not this one.

A URL is worth an index slot only if a stranger would rather land on it than
open the homepage and type. That is a handful of inputs, not a category tree.

### 4. Staged pilot

Not started until this note is accepted and there is a `SHIP:` yes. One live
call per page, no reroll. The model bill is still unknown per call
([PR #7](https://github.com/everfields/antisearch-automation/pull/7)), so
100 pages = 100 × unknown. Do not spend the calls before the host and the
noindex gate are accepted.

0. No URLs. This section.
1. **100 pages, `noindex`, no sitemap, not linked from the apex.** Read a sample. One shared template with a slot is a stop. Do not lift `noindex` to see if Google likes it.
2. **Lift `noindex` on those 100 only** if the sample is the product frame and the founder still wants the test. Own Search Console property. Then watch, and add nothing:
   - Manual actions stays clear on that property and on the apex.
   - Page indexing is not a pile of "Crawled – currently not indexed" or "Discovered – currently not indexed."
   - Apex impressions do not drop.
   - "URL is on Google" is not a success. That is how the old tree started.
3. **1,000** only if those 100 stay indexed, get impressions for the input rather than the brand, and the apex is flat. Same gates. Then stop. 100k is not a later stage.

Kill on any manual action on either property, a dip on the apex, most URLs crawled and not indexed or indexed and then dropped, or the only number that moved being "pages indexed."

### 5. Recommendation

**Not now.**

Never rebuild the category tree, the shared template, or the index-first
100k. **Go** would mean publishing pages this plan cannot make worth indexing
without breaking the constitution. The tweezers version is the 100-page
`noindex` sample, and even that waits for a yes. Until then, nothing is
generated.

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

- **LinkedIn pairs (A).** The locked shape is one pair, not a list. Two verdicts in a company-page text post are still less reach per hour than Show HN, and they are not the clip. Not posted.
- **Directories, newsletters, display/CTV.** A tour, a pitch, or a stunt. No free reach that behaves like the product.
- **X API.** Not free. A URL post is $0.20. Out while spend is zero.
- **Programmatic SEO (B, SEO plan v0).** Not now. The tree that indexed was deindexed, and a constitution-compatible page cannot grow the substance that was removed. A subdomain does not fence the brand off from that.

# TikTok reach pack (proposal, 2026-09-27)

The creative alternatives are mockups, described with their reasoning in
[`docs/CREATIVE_DIRECTION.md`](../CREATIVE_DIRECTION.md). The current clip stays the main
creative, and nothing here is wired to publishing.

## TikTok reach pack (proposal; not implemented)

**Today's rule to change:** TikTok captions are empty or the bare input, and hashtags are
refused (`guard.caption_problem`). The pack needs a switch such as
`PUBLISHER_TT_CAPTION=seo`, the same approach as Instagram's `PUBLISHER_IG_CAPTION`.

**Per post:**
1. **Line 1, the pair:** `<input> → <verdict>`, lowercase, for example `travel → japan`. That is the whole message; no question, no call to action.
2. **Line 2, one search phrase:** 2–5 words someone would type into TikTok search for this input, for example `where to travel next` or `japan travel`.
   - Source it with no spend: TikTok's own search autocomplete and "others searched for", and the free keyword/hashtag view in TikTok Creative Center.
   - One phrase per post, recorded in `posts.csv`, so the metrics can compare phrases.
3. **Hashtags, 3 to 5, in this order:**
   - `#<input>` and `#<verdict>`, made the same way as `igcaption` (accents kept, spaces removed);
   - one vertical tag (`#traveltok`, `#skincare`, `#fashiontok` …);
   - `#ai`.
   - Never `#fyp`/`#foryou` spam, `#antisearch` or `#best`.
4. **On-screen text** already carries the keywords: TikTok reads the typed input and the verdict from the frames. Keep both lowercase and on screen for at least one second (already true).
5. **Cover:** the verdict frame. Today the Buffer thumbnail offset is fixed at 3.5 s; it should become the clip's verdict time.
6. **Sound:** when a music creative runs, post it as an original sound named `antisearch — <verdict>`, so other creators can reuse it. This works because the bed is ours: no library licence, so business-account rules don't bite.
7. **Hook:** typing starts in the first second. No text intro and no logo sting.

**Brand posts never comment-bait:** no "comment yours", "agree?", "tag someone", "part 2?",
questions to the viewer or pinned-comment prompts. Replies stay with the existing reply
lane and its rules.

**Examples:**

| input → verdict | line 2 (search) | hashtags |
| --- | --- | --- |
| travel → japan | `where to travel next` | `#travel #japan #traveltok #ai` |
| overrated → fame | `what is overrated` | `#overrated #fame #philosophytok #ai` |
| paradise → bora bora | `most beautiful island` | `#paradise #borabora #traveltok #ai` |
| fashion → hermès | `luxury fashion brand` | `#fashion #hermès #fashiontok #ai` |

**Still to confirm before building:** the exact phrase per post comes from TikTok search on
the day. Autocomplete and Creative Center change, so nothing in the table above has been
checked against live TikTok search data.

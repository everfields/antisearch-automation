# X: mentions from a new account, and an X reverse-oracle pass

**Update, 2026-09-28 evening:** the founder decided, explicitly, to turn automated mentions
on. An X post carries at most one mention, only for the verdict's own verified account,
never the same account within 14 days (AGENTS.md, "X rule"). The risk in "Bottom line" below
still stands: X's automation rules forbid unsolicited automated mentions.

Status (morning): research and a draft only. No posting changes: Soul and GTM are defining the X
strategy first. X stays live on purpose (`PUBLISHER_LIVE_NETWORKS` untouched), 2 plain-text
posts a day, `input` then `verdict`, no mention, no link, no hashtag.

## Bottom line

- **Automated mentions are against X's rules, not just a reach risk.**
  - Our X posts go out through Buffer's API, so X treats them as automated.
  - X's automation rules say automated mentions to accounts that haven't opted in are "an
    abuse of the feature, and is not permitted". Opted in means the account replied to us
    or messaged us first.
  - The stated enforcement is "removal of your posts from Search or the suspension of your
    app or account".
  - Our code already blocks any `@` on X (`caption_problem`, `x_text_problem`). Keep it.
- **Several mentions per post from a new, zero-follower account** is the textbook pattern of
  X's spam policy: "bulk, aggressive, high-volume unsolicited … mentions". It is a known
  trigger for search bans and suspensions. The practitioner reports below agree, and add
  reply-deboosting for new, low-reputation accounts.
- **If mentions happen at all, they are manual and rare.** A person writes and posts them in
  the X app, with at most one mention, and only when the mentioned account is the verdict
  itself. The rest of the rules are in the next section.

## What X says (primary sources)

1. **Automation rules, "Posting automated mentions and replies"**
   ([help.x.com/en/rules-and-policies/x-automation](https://help.x.com/en/rules-and-policies/x-automation),
   archived [2026-08-03](https://web.archive.org/web/20260803124103/https://help.x.com/en/rules-and-policies/x-automation)):
   - The rule: "Automating these actions to reach many users on an unsolicited basis is an
     abuse of the feature, and is not permitted. … Spammy or duplicative use of mentions and
     replies may result in enforcement action, such as the removal of your posts from Search
     or the suspension of your app or account."
   - The exception: automated mentions are allowed only if the mentioned user opted in
     beforehand (by replying to us or sending a DM), can opt out, and gets at most "one
     automated reply or mention per user interaction".
   - "Note that a user following your account is not on its own a sufficient indication of
     user intent."
   - "Advertisers, publishers, and brands using auto-response campaigns must request
     approval from X."
2. **Authenticity, platform manipulation and spam**
   ([help.x.com/en/rules-and-policies/authenticity](https://help.x.com/en/rules-and-policies/authenticity),
   archived [2026-09-23](https://web.archive.org/web/20260923091044/https://help.x.com/en/rules-and-policies/authenticity)).
   These are "not allowed":
   - "sending bulk, aggressive, high-volume unsolicited replies, mentions, or direct messages";
   - "posting with excessive, unrelated hashtags";
   - "repeatedly posting identical or nearly identical posts";
   - "promoting content by replying with content that is irrelevant to the topic of the
     original post".
3. **X Premium** ([About X Premium](https://archive.ph/AqTHt)): "people on X will see a slight
   preference for replies from verified accounts over other replies". Reply prioritization
   is a paid feature on every tier, so a free new account's replies rank below Premium ones
   by design.

## What the ranking code and practitioners add (secondary; treat as indicative)

- **Reputation (the 2023 open-sourced code).** X published its 2023 recommendation code.
  - Its `tweepcred` reputation score reduces the rank of accounts with few followers
    compared with how many they follow
    ([tweepcred README](https://github.com/twitter/the-algorithm/blob/main/src/scala/com/twitter/graph/batch/job/tweepcred/README),
    [ExtractTweepcred.scala](https://github.com/twitter/the-algorithm/blob/main/src/scala/com/twitter/graph/batch/job/tweepcred/ExtractTweepcred.scala)).
  - Third-party readings of that code report that accounts under a reputation of 65 have
    only about 3 posts considered per ranking cycle
    ([Steven Tey](https://steventey.com/blog/twitter-algorithm)).
  - This is 2023 code; today's ranking may differ.
- **Restriction types (practitioner guides).** They describe four kinds: search suggestion
  ban, search ban, "ghost" reply ban, and reply deboosting (replies sorted to the bottom or
  behind "Show more replies"). They name spam-like automation, mass low-quality replies,
  high block and report rates, and aggressive activity from brand-new accounts as the main
  triggers, and recommend a slow ramp for new accounts over 2–4 weeks
  ([Sorsa](https://api.sorsa.io/blog/twitter-shadowban-test),
  [OpenTweet](https://opentweet.io/blog/twitter-shadowban-check-fix-avoid-2026),
  [XEngageAI](https://xengageai.com/blog/ghost-ban-on-x-twitter-2026)).
  - None of this is official; X does not confirm "shadowban" as a term.

## What's safe for `@antisearch_ai`

| practice | rule for us | why |
| --- | --- | --- |
| mentions in automated posts | **none** (current code) | X automation rules: unsolicited automated mentions are not permitted |
| mentions in manual posts | at most **1 per post**, only when the account **is the verdict**, at most 1 post in 3, never the same account within 14 days | X spam policy targets bulk and unsolicited mentions; relevance is the line X draws |
| several mentions in one post | never | the "bulk, aggressive" pattern |
| replies to brands' posts | none automated; manual only if genuinely on topic, a few a day at most | "promoting content by replying with content that is irrelevant"; reply-deboosting on new accounts |
| hashtags | none (current) | "excessive, unrelated hashtags"; they add nothing to our format |
| links | none in the post (current) | "links shared without commentary" as the bulk of activity |
| near-duplicate posts | never (current `near_caption` guard) | "identical or nearly identical posts" |
| volume | 2 a day, 90+ minutes apart (current) | a slow ramp for a new account |
| profile | complete (avatar, bio, site) | new, empty accounts get flagged faster (practitioners) |
| check | weekly logged-out search for our own post text | the only way to see a search ban |

**Honest risk:** a single on-topic mention in a manual post is ordinary use of X. The real
risks come from automation plus mentions, and from many mentions (per post, or across posts)
from a new account.

## Draft: an X reverse-oracle pass

It works the same way as the Instagram reverse oracle (`src/antisearch_mill/reverse_oracle.py`,
`queue/reverse_oracle/README.md`). The aim: find short inputs whose **real** verdict *is*
an X account with real reach.

1. **Targets.** A file, `queue/reverse_oracle/x-targets.csv`, with the same columns
   (`vertical,name,handle,market,site,followers_approx,aliases`), and the X handle in
   `handle`.
   - **Who:** brands, products, places, teams, institutions and media. No person as a target:
     a person is never tagged. Never amika or any Bansk brand.
   - **Reach:** 100k+ followers, and a post in the last 7 days.
   - **Evidence:** web evidence, never model knowledge (the Instagram pass measured a 30%
     error rate on model-remembered handles):
     - Wikidata `P2002` (X username) for the entity, or its official site linking
       `x.com/<handle>` or `twitter.com/<handle>` (the rule in `scripts/verify_handles.py`);
     - a follower count from a public tracker (X hides counts when logged out).
   - **Verticals that fit X:** tech, games, cars, sports teams, media, finance, cities and
     countries. AI companies only while `PUBLISHER_AI_INPUTS=on` and the oracle's
     self-bias fix holds.
2. **Generator: the oracle run backwards.** This is unchanged. It uses the product's model,
   system prompt and settings, read only, and asks reverse questions ("category topped by
   {winner}", "what {winner} is the answer to"). Inputs are at most 3 words, bare English,
   and never the target's own name.
3. **Verification.** One `LiveOracle` call per input, with a budget of 100. Every verdict
   is frozen. An input already frozen or already tried is never asked again.
4. **Match.** An `exact` or `prefix` match on the target's aliases, ranked the same way.
   - The input and verdict must pass X's text rules (`x_text_problem`: no `@`, `#`, link
     or emoji, and at most 280 characters) as `input\nverdict`.
5. **Output.** `publisher-state/reverse_oracle/<run>-x-{candidates.json,results.csv,matches.csv}`.
   Nothing is posted or scheduled.
6. **Use, once Soul and GTM decide.**
   - Matched inputs could join `queue/pools/x.txt` as normal posts with **no mention**. The
     verdict names the account in plain text, which X search and the account's own mention
     searches can surface.
   - If a manual one-mention format is approved, only these rows qualify, under the rules
     in the table above.
7. **Code needed** (one small PR, when asked):
   - a `--network x` switch in `reverse_oracle.py`, so `--check-sites` looks for
     `x.com`/`twitter.com` links instead of `instagram.com`;
   - `scripts/verify_handles.py` reading Wikidata `P2002` alongside `P2003`.
   - It runs locally, like the Instagram pass, because it needs the product's source and
     model key.

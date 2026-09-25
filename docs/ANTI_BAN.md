# Anti-ban

Founder, 2026-09-25: earlier X accounts were banned, most likely for a repeated
structure (same template, same pixels, same file metadata). TikTok may have
done the same. Instagram and LinkedIn did not. That history is not a promise.
The written rules on all four still punish repetitive, unoriginal, automated
posting. This file is what the publisher does about it. The clip's pictures
do not change.

Checked 2026-09-25.

## What the platforms say

**X.** [Developer Policy](https://docs.x.com/developer-terms/policy), section
"Spam, bots, and automation": never post identical or substantially similar
content across multiple accounts, and never do bulk, aggressive, or spammy
actions. [Developer guidelines](https://docs.x.com/developer-guidelines): an
automated account has to be labeled, has to use the official API, has to stay
inside rate limits, and may not post identical content across accounts or
send unsolicited mentions. Those guidelines link the automation rules at
`https://help.x.com/en/rules-and-policies/x-automation`. That help page
returned 403 from this environment, so it is not quoted here.

**TikTok.** Community Guidelines, 2026 H2, Integrity and Authenticity
([text](https://www.tiktok.com/community-guidelines/en/integrity-authenticity)):
spam includes using automation to run many accounts or to send repetitive
content. A hit can limit posting, search, and the For You feed.
[FYF standards](https://www.tiktok.com/safety/en/policies-and-engagement/fyf-standards):
content is ineligible for the For You feed if it includes unoriginal or reused
material without anything new.

**Meta.** [Original-content note, March 2026](https://about.fb.com/news/2026/03/rewarding-original-creators-on-facebook/):
duplicative video, or a minor edit such as a border, burned-in captions, or a
speed change, is unoriginal and deprioritized in Feed and Reels. An account
that keeps posting mostly unoriginal video can be made non-recommendable.
The spam standard is
[transparency.meta.com/.../spam](https://transparency.meta.com/policies/community-standards/spam/);
that page did not render its body here, so it is cited and not quoted.

**LinkedIn.** [Professional Community Policies](https://www.linkedin.com/legal/professional-community-policies):
do not spam members or the platform. Untargeted, unwanted, promotional, or
gratuitously repetitive messages are not allowed.

## What the publisher does

1. **Warm-up.** A network with no first-post date starts at 1 post/day
   (`PUBLISHER_RAMP_START`, 1 or 2) and reaches its cadence over
   `PUBLISHER_RAMP_DAYS` (default 14, allowed 1–60). Those posts are the
   earliest slots of that cadence. A missed slot still expires after the
   2 hour grace; a later slot does not fill it. The date is `first_post`
   in `<state>/antiban.json`, written on the first post that actually goes
   out. `PUBLISHER_RAMP=off` posts the full cadence immediately.
2. **Jitter.** Each slot gets a seeded offset of ±9 minutes. The resulting
   minute is never :00 or :30. The same slot keeps the same offset, so a
   retry agrees. The cron still wakes at :07. If the offset is still ahead,
   that one post waits (at most 9 minutes) inside the job. If the offset is
   already past, the post goes out on the wake. `PUBLISHER_JITTER=off`
   disables the wait. The wait is billed Actions time; see `docs/COST_PER_VIDEO.md`.
3. **Dedupe.** On one network, the same clip id is not posted twice and the
   same non-empty caption is not posted twice. An empty caption is the
   video-only ritual and may repeat. An input is not repeated within
   `PUBLISHER_INPUT_COOLDOWN_DAYS` (default 30), and it is still never
   repeated at all after that. One honest run stays one honest run.
4. **Captions.** Empty, the bare input, or one `@handle`, under the winner
   rules. A second `@` is rejected. A `#` is rejected. No hashtag stuffing,
   no repeated identical caption (see 3).
5. **Replies.** Still at most 3 a day on Bluesky, and not the same author
   twice in 7 days. The cap cannot be raised with `PUBLISHER_REPLY_CAP`.
6. **Brake.** A spam, rate-limit, or HTTP 429 error, or a day-over-day reach
   drop to half or less when yesterday was at least 100
   (`<state>/metrics.csv`, columns `date,network,reach`), halves that
   network's posts for 72 hours. The same drop does not extend the window.
   A network whose target is 1 goes to 0 for those 72 hours. The flag is `<state>/flags/<network>.txt`, addressed to
   CoS. No metrics file means no reach brake. This environment cannot open
   a GitHub issue; the flag file is the issue.
7. **Files.** The master stays the deterministic picture (no extra frame, no
   pixel noise). At upload, a real mp4 is remuxed with `-c copy`: new
   `creation_time`, new `comment=upload=...`, same frames, different file
   hash. A test fixture that is not an mp4 is posted as-is.
8. **X.** A queue row for `x` is `skipped_x_off`. It is not auto-posted.
   Putting `x` in `PUBLISHER_LIVE_NETWORKS` still freezes Bluesky, because
   Bluesky is only the stand-in, and it still does not post to X. Leave `x`
   out of that list until there is a separate decision to unhold it.

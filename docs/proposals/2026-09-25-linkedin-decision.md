# LinkedIn decision

Opus, 2026-09-25. Soul and GTM have not replied. Their notes go in the section at the bottom. This call does not wait on them. Carlos can override it.

The Page is `99258814`, the old company page renamed to antisearch, administered from Carlos's personal profile. He works full time at Havas Spain. Many of his connections are coworkers. He works on antisearch in the evening in Spain, not during the Havas day. LinkedIn is not in `PUBLISHER_LIVE_NETWORKS`. Nothing has been auto-posted.

Madrid is ET+6, except the DST-gap weeks (2026-10-25 → 11-01, and the March pair), when it is ET+5. The current Soul slot `09:07` ET is 15:07 Madrid. That is inside the Spanish workday. On the `carlos` preset the LinkedIn slots are 15:07, 17:07, 19:07, 21:07 and 23:07 Madrid, so the first three sit in or on the edge of that day.

## Options

1. **Keep the Page. Post only after 19:00 Madrid, including weekends. One a day or fewer.**
2. **Detach the Page from his personal profile** by adding another admin and leaving his profile.
3. **Open a new Page** that is not the renamed company page.
4. **Pause LinkedIn.** `PUBLISHER_SLOTS_LINKEDIN=off`. Leave it out of the live set.
5. **Text pairs only, posted by hand.** One pair per post, lowercase, no header. Not built. Not this channel's current clip.

## Risks

- A post at 15:07 Madrid, from a Page he admins on the profile his coworkers already have, reads as side work at his desk. That is the risk he named. It is about the clock, not the clip.
- Another admin, or a new Page, does not fix the clock. A new Page also drops `99258814`, which the publisher already uses. Both are extra human setup. He may not have a second admin.
- Pausing drops the one network, with Instagram, that did not ban the earlier accounts. The ban history was X, and maybe TikTok.
- Hand-posting text pairs from his own session is more visible to those connections than one Page post late in the evening.
- The evening slot does not cover place rows. On the Buffer bridge, `employer in madrid` is scheduled for 09:07 Madrid no matter what `PUBLISHER_SLOTS_LINKEDIN` says. 09:07 New York is 15:07 Madrid. Any city whose local 09:07 falls between 09:00 and 19:00 Madrid has the same problem.

## Decision

Keep Page `99258814`. One automated clip a day, after the Spanish workday. Do not open a new Page. Do not pause the channel. Do not switch LinkedIn to manual text pairs.

Set this before LinkedIn is added to `PUBLISHER_LIVE_NETWORKS`:

```
PUBLISHER_SLOTS_LINKEDIN=15:07
```

`15:07` ET is 21:07 Madrid (20:07 Madrid in a DST-gap week). Both are after 19:00. The cron already wakes at that UTC hour. One slot is one post a day on either cadence preset. `13:07` ET is 19:07 Madrid most of the year and 18:07 Madrid in the gap week, so it is not the slot.

Until that variable is set, LinkedIn stays out of `PUBLISHER_LIVE_NETWORKS`.

Do not enqueue LinkedIn place rows (`employer in madrid`, and the rest of `publisher/places.py`) while the bridge still schedules them for 09:07 local. The slot above does not move those.

Adding another admin can happen later. It is not required for this.

## Soul

_(blank. Carlos adds this when Soul replies.)_

## GTM

_(blank. Carlos adds this when GTM replies.)_

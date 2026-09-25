# LinkedIn decision

Opus, 2026-09-25, after Soul and GTM. Carlos can override it.

The Page is `99258814`, the old company page renamed to antisearch, administered from Carlos's personal profile. He works full time at Havas Spain. Many of his connections are coworkers. He works on antisearch in the evening in Spain, not during the Havas day. LinkedIn is not in `PUBLISHER_LIVE_NETWORKS`. Nothing has been auto-posted.

X is idle. There is no paid API, so nothing posts there. The whisper currently lives on TikTok and Instagram, and on Bluesky once that account exists.

Madrid is ET+6, except the DST-gap weeks (2026-10-25 → 11-01, and the March pair), when it is ET+5. The current Soul slot `09:07` ET is 15:07 Madrid, inside the Spanish workday. On the `carlos` preset the LinkedIn slots are 15:07, 17:07, 19:07, 21:07 and 23:07 Madrid.

## Options

1. **Keep the Page. Post only after 19:00 Madrid, including weekends. One a day or fewer.**
2. **Detach the Page from his personal profile** by adding another admin and leaving his profile.
3. **Open a new Page** that is not the renamed company page.
4. **Pause LinkedIn.** `PUBLISHER_SLOTS_LINKEDIN=off`. Leave it out of the live set.
5. **Text pairs only, posted from the Page.** One pair per post, lowercase, no header, no video. Not built.

## Soul

Pause LinkedIn. The audience there is coworkers, and the Page has a past from the earlier pivot. If it is kept: only after 19:00 Madrid, plus weekends, 1 a day at most, text pairs only with no video, never Spain, media, advertising, Havas, or Havas clients as inputs, and posted from the Page only. A new clean Page is better. Park that for now.

## GTM

Keep it at 19:07 Madrid (`13:07` ET), plus weekends, 1 a day at most. A new Page does not fix the worry: it would still be administered from his profile, and it would have zero followers. Text-only does not help, because coworkers see the timestamp, not the format. LinkedIn is the weakest reach channel, so pausing costs almost nothing. Pause is the fallback.

## Decision

Pause LinkedIn.

```
PUBLISHER_SLOTS_LINKEDIN=off
```

Leave `linkedin` out of `PUBLISHER_LIVE_NETWORKS`. The `soul` preset still has a 09:07 ET LinkedIn slot. Without `off`, adding LinkedIn to the live set would post at 15:07 Madrid.

Soul's reason is the one that decides it. The people who will see the Page are coworkers, and the Page is a renamed company page from the last pivot. An evening timestamp does not change either fact. GTM's keep is the timestamp fix, and GTM also says the reach cost of pausing is almost nothing. That cost is smaller still while X is idle and the whisper is already on TikTok, Instagram, and soon Bluesky.

`13:07` ET is not an acceptable keep. It is 19:07 Madrid most of the year and 18:07 Madrid in a DST-gap week, which is inside the Havas day. A daily slot also cannot mean "evenings on weekdays and daytime on weekends." The publisher has no day-of-week slots. Pausing posts on no day, weekend included.

Do not open a new Page. Soul wants one later and says park it. GTM is right that a new Page, still administered from his profile, does not answer the worry, and it would start with no followers. Parked.

Do not build LinkedIn text pairs for this. GTM is right that coworkers read the clock. Soul's text-only rule would matter only if the Page were turned back on.

If Carlos turns LinkedIn back on later, all of these hold, or it stays off:

- `PUBLISHER_SLOTS_LINKEDIN=15:07` (21:07 Madrid, 20:07 in a DST-gap week). Not `13:07`. Not `09:07`.
- One slot, so one post a day. That daily evening slot is also the weekend post.
- From the Page only. No personal-profile posts.
- No video on LinkedIn. Text pairs only, once that path exists. Until it exists, LinkedIn stays off.
- No input about Spain, media, advertising, Havas, or a Havas client.
- No place rows. The bridge still schedules those for 09:07 local, and 09:07 Madrid is the middle of the Havas day.

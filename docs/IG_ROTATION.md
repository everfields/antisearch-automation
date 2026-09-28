# Instagram: creative rotation, 7 reels a day, Stories

Founder, 2026-09-28: v2 of the creative mockups is approved (PR #30). This page covers
what went live with it. TikTok and X are unchanged, and `PUBLISHER_LIVE_NETWORKS` is untouched.

## 1. Four creatives, one fixed template each

| creative | what it is | length | render on CPU (4 cores) |
| --- | --- | --- | --- |
| `0-current` | the current clip: phone on stone, keys | 5–7 s | ~4 s |
| `1-short-score` | the same picture, with the keys plus the template score (felt piano, strings, bell; resolves on C major and releases to silence) | 5–7 s | ~6 s |
| `2-medium-monolith` | the camera dives onto the typed input, re-frames on the verdict, releases to the monolith, then the verdict alone in large type | ~8.6 s | ~45 s |
| `3-computation` | the monolith, with the wait shown as a huge model computing (tokens, layers, one point of light where the verdict lands) | ~8.6 s | ~45 s |

- **One template each, no per-verdict work.** Every frame and note is a function of three
  things: the input, the frozen verdict, and the clip's own timeline. There is no model call
  per post and nothing is authored per verdict. The verdict is drawn exactly as the oracle
  returned it, lowercase.
- **Code.** The templates are in `src/antisearch_mill/creatives/`, moved from PR #30's
  `scripts/mockups/` with no change to the look. `produce_one(..., creative=...)` renders the
  current clip first, then finishes it as the creative. The creative is part of the clip id.
  `0-current` keeps the id it always had.
- **Cover.** The monolith and computation creatives end on dark, so the loop can join. Their
  reel cover (`thumbnailOffset`) is therefore the moment the verdict stands alone in large
  type, not the last frame.
- **Samples.** `python scripts/render_samples.py --verdicts <verdicts.csv> --out <dir>` renders
  them through the same pipeline call.

### The rotation rule

The creative is `IG_ROTATION[(posting day + slot index) mod 4]`: a Latin square.

- Over any 4 days, each of the 7 daily slots sees each creative once.
- Each creative gets 7 posts in those 4 days.
- The time of day never favours a creative.
- The rule is deterministic and needs no state: the same slot on the same day always gets
  the same creative.
- A manual row scheduled in Buffer takes the creative of the slot its send time falls in.

### What gets logged

- `posts.csv` has a new column, `creative`, set on every Instagram row. Rows from before the
  rotation are blank, which means `0-current`. TikTok and X rows stay blank.
- `mill metrics` prints an **IG creative** table under Instagram's last 7 days: posts, and the
  mean views, likes, shares, saves and engagement rate per creative.
- A fair first read comes after about 7 days: roughly 12 posts per creative.

### The switch

`PUBLISHER_IG_ROTATION=off` sends `0-current` only. The rotation is on by default.

## 2. Frequency: 7 reels a day

- **Slots.** `reach` Instagram slots: **10:07, 12:07, 14:07, 16:07, 18:07, 20:07, 22:07 ET**.
  That is 16:07 to 04:07 Madrid, or 07:07 to 19:07 on the US West Coast.
- **Cap.** Instagram's own cap is `IG_MAX_PER_DAY = 8`. `PUBLISHER_SLOTS_INSTAGRAM` can add an
  eighth slot, for example `00:07`. Every other network stays capped at 5, and X at 2.
- **Jitter.** Unchanged: 0–40 minutes after :07, seeded, never two networks on one minute,
  never on :00 or :30. New: two slots of one network stay 90 minutes apart after the jitter
  as well. This only binds on Instagram, whose slots are 2 hours apart.
- **Gap (a), fixed.** A Buffer schedule holds the slot its send time falls in. A 22:07 reel
  holds 22:07 and no longer takes the day's first slot.
- **Gap (b), fixed.** The 90-minute gap is measured between send times, past and future:
  - a Buffer schedule counts at the minute Buffer sends it, not when it was queued;
  - an auto post within 90 minutes of an upcoming Buffer reel is skipped.
- **Also fixed, found by the dry run.** Every post, sent now or scheduled, fills the latest
  free slot whose window holds its send time.
  - Before this, posts filled slots earliest-first by count. With 2-hour slots and 3-hour
    windows, one missed slot made every later post drift, and a late evening could serve the
    22:07 slot twice (the second time at 01:00 ET).
  - Now a missed slot is dropped once the next one is served.
- **Dry run.** `python scripts/ig_rotation_dry_run.py --state <dir> --hours 48` steps through
  every 15-minute cron wake with the real runner against a copy of the post log.
- **Supply.**
  - At 7 a day the Instagram pool (`queue/pools/instagram.txt`) lasts about a week: on
    28 Sep it had 35 vertical inputs left, plus 52 unowned words shared with TikTok.
  - The pool needs a refill before about 5 Oct.
  - Instagram also draws the shared unowned words faster, so TikTok's supply of them shrinks.

## 3. Buffer limits (free plan, checked 2026-09-28)

| limit | value | our use at 7 IG + 4 TikTok + 2 X a day |
| --- | --- | --- |
| API requests per 15 minutes (rolling) | 100 | at most ~10 in one run |
| API requests per 24 hours (rolling) | 250 | ~50 |
| API requests per 30 days (rolling) | 3,000 | ~1,500 (~2,250 without the channel cache) |
| Instagram posts per 24 h through Buffer (reels **and** stories together) | 50 | 7 (8 with Stories on) |
| Meta's own Content Publishing limit | 100 API posts per 24 h | 7–8 |
| Scheduled posts waiting per channel | 10 | auto posts go out at once (`shareNow`) and never wait; manual rows do (5 Instagram concept reels as of 28 Sep) |

How the request estimate works:

- **Per post.** A post costs up to 3 requests: create, then up to 2 status reads.
- **Channel lookup.** Looking up the channel costs 2 more requests. A live run now caches the
  channel ids in `publisher-state/buffer_channels.json`, so the lookup happens once. Pinning
  `BUFFER_CHANNEL_*` does the same. A failed create drops the cached id, so a reconnected
  channel is looked up again.
- **Metrics.** The metrics job reads Buffer at most every 20 hours: 1 to 5 requests.
- **Headroom.** 13 posts a day × 3 requests, plus metrics, comes to ~50 a day, or about half
  of the 30-day budget.
- **Where it gets tight.** Going to 8 Instagram reels plus Stories adds about 6 a day. The
  budget only gets tight without the cache. A 429 from Buffer trips the existing brake.

Sources:
- [Buffer API rate limits](https://developers.buffer.com/guides/api-limits.html)
- [Buffer daily posting limits](https://support.buffer.com/article/646-daily-posting-limits)
- [Buffer scheduled-post limits](https://support.buffer.com/en-us/articles/how-many-posts-can-i-schedule-in-advance-Kmy2IEecqm)

## 4. Stories

**The template** is `creatives/story.py`, `creative = "story"`:

- 1080×1920, 5 s, cold monochrome on near-black;
- the input small in stone grey, and a hairline that fills while the model thinks;
- at 1.45 s the verdict lands in large lowercase type exactly as returned, with one cold bloom;
- `antisearch.ai` on screen from the first frame;
- everything inside the Stories safe area (clear of the top 250 px and bottom 340 px);
- scored by the same template score.

Mockups: `creative/stories/story-{travel,zoo,restaurant-in-barcelona}.mp4`, each with a
key-frame sheet.

**Buffer supports it.** `createPost` takes `metadata.instagram.type: story`, and Buffer
auto-publishes a Story from a Business or Creator account when it is clean media: one 9:16
video, with no music, stickers, link or text added in Buffer. Anything else turns into a
phone reminder. Our reels already auto-publish from the same channel, so the account type is
right.

**On by default since 2026-09-28** (founder: go for it).

- One Stories card a posting day, right after the first Instagram reel of that day that is
  sent now (not a Buffer-scheduled manual row). `PUBLISHER_IG_STORIES=off` stops it.
- A failed story is not retried after every later reel; the next posting day tries again.
- The card carries the same frozen verdict, so there is never a second oracle run.
- It goes through `BufferInstagramStory`: the same channel, `type: story`, and no caption,
  since a Story has none.
- It is logged as `<job>-story` on network `instagram_story`, `creative = story`. It never
  takes a reel slot.
- With `PUBLISHER_IG_STORIES=off`, nothing changes.

## Not changed

- TikTok, X, `PUBLISHER_LIVE_NETWORKS`.
- `the_best` and its prompt.
- The one-oracle-run-per-input rule.
- The tag allowlist and its guards.

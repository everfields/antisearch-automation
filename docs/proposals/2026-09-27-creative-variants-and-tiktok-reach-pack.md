# Creative variants and a TikTok reach pack (proposal, 2026-09-27)

Founder criterion: we start from zero, and everything is trial and error. We must be ready
to change the creative completely to find the one that ignites reach. Nothing here is
live: `PUBLISHER_CREATIVE` defaults to `classic` and is not passed by any workflow, so
turning a variant on is its own reviewed change.

## 1. Creatives (`PUBLISHER_CREATIVE`, `src/antisearch_mill/creative.py`)

| value | what it is | length |
| --- | --- | --- |
| `classic` (default) | today's clip, unchanged (same bytes, same clip ids) | 5–6 s |
| `music_classical` | classic picture plus a soft felt-piano bed. Broken A-minor chords under the typing, the harmony held on F then G through the wait, a rolled C major (add9) on the verdict frame. About −18 LUFS, keys on top. | same |
| `music_upbeat` | classic picture plus a 120 bpm bed. Hats and filtered plucks under the typing, a snare roll and a noise rise through the wait, and the drop (kick, clap, bass, chord stabs) on the verdict frame. About −13 LUFS. | same |
| `motion` | the cinematic monolith, scored by `monolith_score`. The motion-first direction, the camera grammar and the music decision are in `docs/CREATIVE_DIRECTION.md`, which supersedes this row. | 8.5 s |

**How it's built:**
- **Sound:** every bed is original synthesis (`music.py`): no samples, loops, stock tracks or licences, and no spend. Music is muxed only where the clip already carries audio (Instagram and TikTok).
- **Picture:** the music variants keep the classic frames bit for bit (a test compares the video md5).
- **Clip ids:** each creative gets its own clip id; `classic` keeps every existing id.
- **Samples:** `scripts/render_creatives.py` renders every creative from frozen verdicts, without asking the oracle.

**Suggested test, with no spend:**
- Rotate one creative per day on TikTok only, for example classic, music_upbeat, motion, music_classical, and so on, keeping the same inputs pool.
- Judge after 10 or more posts per variant, on the metrics collector's 3-hour snapshots: 2-second view rate, average watch time, completion rate and shares per view. Views alone is too noisy at our size.
- Keep the winner. If the motion piece wins on completion, try a 7–8 s cut.

## 2. TikTok reach pack (proposal; not implemented)

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

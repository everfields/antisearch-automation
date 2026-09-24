# First 100 humans

Owner: strategy brain (Opus 5.5), for Carlos + CoS, to converge with Soul and GTM.
Written 2026-09-24. No code. Nothing here gets published without Carlos's yes.

**The bet.** antisearch.ai needs no install, no login and no explanation: one input,
one lowercase verdict. Its friction is a phone held out at arm's length, so the first
100 humans come fastest **in person**, from a screen that is already open. Social
posting builds the wall; it won't hand the product to a stranger. Every idea below
puts the blinking cursor in front of a person and then gets out of the way.

**The one rule for Carlos in person: say almost nothing.**
- The words he may use: "type anything", "antisearch.ai", "try".
- Never "AI", never "best", never "I built this" (if asked who made it: "me").
- Never explain a verdict.

---

## Measuring without telemetry (7 days)

Pulse is still blocked on the Supabase secrets. Three signals are enough, from
cheapest to best:

1. **Carlos's tally (in person, zero setup).** A note on his phone, one line per
   person:
   `date · place · typed (y/n) · typed again unprompted (y/n) · asked the address or photographed the screen (y/n)`.
   - *Typed again unprompted* is the return in miniature.
   - *Asked the address or photographed it* is the screenshot signal.
2. **Daily and hourly verdict counts (server side).** Carlos opens the Supabase
   telemetry table once a day (1 minute) and notes: verdicts per day, and verdicts
   in the hour after each timed idea. Better: add the Supabase secrets to Cursor so
   Pulse does it.
   - Exclude the mill's own calls (user agent `antisearch-mill/0.1`, or the
     publisher's post log times).
   - Record 1–2 quiet days first as a baseline.
3. **Returns (only if the telemetry row has any client or IP hash).** Distinct hashes
   seen on 2+ days. If there is no such field, the proxy is verdict volume on days
   with no event, against the baseline.

**Mentions:** a bot can search public Bluesky posts for "antisearch" once a day
through the API (read-only). That's the only screenshot signal we can see online.

**Before day 1:**
- **Try one Spanish input yourself** (e.g. `tortilla`). Strangers in Madrid will type
  Spanish. The English lock covers our public posts, not what people type. That's a
  product check, not a queued input, so it doesn't break the one-honest-run rule.
- **Ship the og fix if you can.** Any link pasted in Slack, Teams or WhatsApp unfurls
  the off-voice `type. AI decides` card.
- **Confirm the cost.** Is there a per-verdict LLM cost or a global cap? 100 humans ×
  ~5 inputs ≈ 500 verdicts is small, but the Slack drop and Show HN can spike.

---

## Pre-kills, revisited honestly

| Pre-kill | Now | Why |
| --- | --- | --- |
| Stunts | **Allowed if whisper-true** | Handing a stranger a phone *is* a stunt. It's allowed because it's one person, no audience, no pitch, and the product does all the talking. Still killed: anything staged for a camera, crowds, costumes, "watch this". |
| Stickers / QR codes | **Still killed** | Printing is spend, QR says "download our app", and street stickers are litter. The only allowance is a handwritten card carrying just the address (raw idea 11), and it's weak. |
| Founder-story posts | **Still killed** | In person the founder is unavoidably there. The rule is he doesn't narrate. "Who made this?" → "me." |
| "We asked ai" framing | **Still killed** | The person asks, not us. |
| Share cards | **Still killed** | Except the og card, which exists whether we like it or not; fix it (see above). |
| Countdowns, hashtags, replying in threads | **Still killed** | Nothing Carlos pushed changes these. |

---

## Raw ideas (14; 6 in person)

"Who" is Carlos (C), Havas colleagues (H), or bots via API (B).

| # | Idea | The move | In person | Who | Minimal signal |
| --- | --- | --- | --- | --- | --- |
| 1 | **Queue handoff** | Phone open on the cursor, held out to the person behind in a queue: "type anything" | yes | C | Tally |
| 2 | **Table handoff** | Phone face-up in the middle of a lunch or dinner table, slid across: "type anything" | yes | C | Tally (inputs per table) |
| 3 | **Office monolith** | A spare laptop in full screen on antisearch.ai, keyboard in front, at the Havas coffee point. No note | yes | C | Hourly count on that day + glances |
| 4 | **Channel drop** | In one informal Havas Slack/Teams channel, a message that is only `antisearch.ai`. No reply, ever | no | C | Count in the following hour |
| 5 | **Show HN, cold, once** | Already drafted in `GTM_OUT_OF_THE_BOX.md` | no | C | HN points, count spike |
| 6 | **Meetup last slide** | At a Madrid AI or marketing meetup: one slide, the live site; ask the room for a word, type it, sit down | yes | C | Count in the 30 minutes after |
| 7 | **Screen-share opener** | Carlos's browser opens on the antisearch.ai tab, so every screen share starts on the cursor for a few seconds | semi | C | None reliable (ambient) |
| 8 | **WhatsApp Status clip** | A mill verdict clip as Carlos's WhatsApp Status, no text. It's ambient, not a message | no | C | Status viewers + next-day count |
| 9 | **Colleague relay** | Five Havas colleagues who liked it leave it open in a tab on their own desks | yes-ish | H | Count trend on office days |
| 10 | **Barber / hairdresser chair** | Beauty vertical, in real life: while waiting, hand the phone to the stylist | yes | C | Tally |
| 11 | **Handwritten card** | Just `antisearch.ai`, handwritten, on a café or university board where allowed | yes | C | Weak: count drift |
| 12 | **Bluesky wall** | The publisher's clips (already built) | no | B | Mentions search, count |
| 13 | **AI-tool directories** | A one-line listing ("ai chooses the best. nothing else.") on free directories | no | C | Weak (no referrer data) |
| 14 | **Mention oracle** | Answer Bluesky mentions once a day (reserve) | no | B | Replies; doesn't bring typing on the site |

Dropped on sight:
- chalk on pavements (city rules; a stunt for a camera);
- pitching it to Havas clients (a verdict could crown a client's competitor in front
  of the client: a real professional risk);
- mass personal messages (Carlos says people ignore them).

---

## Top 5, ranked

Ranked by humans reached in 7 days per minute of Carlos's time, and by how clean the
signal is.

### 1. Queue handoff

- **Script:**
  - Phone unlocked, antisearch.ai open, cursor blinking. Turn to the person behind
    you and hold the phone out: **"type anything."**
  - If asked what it is: **"antisearch.ai."** If asked what it does: **"try."**
  - When they hand it back, take it, say "thanks", and turn around.
- **Where:** Madrid café queues at the morning rush, a bakery, the Havas building
  café or lift lobby. Anywhere people are stuck for 2–5 minutes and already holding
  their phones.
- **Effort:** 5 minutes a day, 2–4 people per queue, about 10 a day → about 50 in
  the week.
- **Success:** of the people who type, **≥ 40% type a second input without being
  asked, and ≥ 20% ask the address or photograph the screen.**
- **Kill:** after 20 handoffs, under 20% type again and nobody asks the address. The
  magic doesn't carry in ten seconds; stop and rethink before scaling anything.

### 2. Table handoff

- **Script:** at a lunch or dinner table (colleagues, friends), put the phone
  face-up in the middle with the cursor blinking and slide it over: **"type
  anything."** Then say nothing. Let the table argue about the verdicts.
- **Where:** Havas lunches, after-work drinks, family dinners. Groups of 3–6.
- **Effort:** 2 minutes per table; 3–4 tables in the week, about 15 people.
- **Success:** **≥ 5 inputs per table** (the phone travels on its own) and **at least
  one person per table asks the address.** An argument about a verdict is the
  screenshot moment.
- **Kill:** three tables in a row where the phone comes back after one input.

### 3. Channel drop

- **Script:** in one informal Havas channel (random / AI / general chatter; not a
  client channel), post a message that is exactly **`antisearch.ai`**. Nothing
  else. Don't reply to the thread; react to nothing.
- **Where:** Havas Slack or Teams, a Tuesday–Thursday around 11:00 Madrid. Once.
- **Effort:** 1 minute. Prerequisite: the og fix, or the unfurl says
  `type. AI decides`.
- **Success:** **≥ 20 verdicts in the hour after the post**, above the baseline, plus
  someone asking about it outside the channel.
- **Kill:** under 10 verdicts in that hour. Don't post in a second channel.

### 4. Office monolith

- **Script:** a spare laptop at the coffee point (or Carlos's own desk, if company
  policy is unclear) with the browser in full screen on antisearch.ai, cursor
  blinking, keyboard in front. **No note, no sign.** If anyone asks: **"type
  anything."**
- **Where:** the Havas Madrid office, one full working day. Carlos's call on whether
  a personal project may sit in a shared space.
- **Effort:** 10 minutes of setup; check it at lunch and at the end of the day.
- **Success:** **≥ 15 verdicts during office hours** on that day above the baseline
  (from the count), and people mentioning it to Carlos unprompted.
- **Kill:** fewer than 5 people type in the whole day. Take it down; the office
  already has its answer.

### 5. Show HN, cold, once (gated)

- **Script:** exactly as drafted in `GTM_OUT_OF_THE_BOX.md`: title
  `Show HN: antisearch – one verdict, nothing else`, the two-line first comment, then
  no replies and no upvote asks.
- **Where:** news.ycombinator.com, a weekday, 15:00–16:00 Madrid, from Carlos's
  own account and device.
- **Effort:** 5 minutes.
- **Gates:** the og fix is live, and the per-verdict cost / global cap is confirmed.
- **Success:** the front page, or **≥ 100 verdicts above the baseline** within 6 hours.
- **Kill:** under 5 points after 2 hours. It was the one shot; never repost.

**Runner-up: meetup last slide (6).** It's strong: a room of 50+ gives a clean
30-minute spike. It only makes the list if a Madrid meetup has a slot this week.

---

## The 7 days, concretely

| Day | Carlos | Signal to note |
| --- | --- | --- |
| 1 | Try one Spanish input himself. Note a baseline count. Queue handoff ×1 | Tally, count |
| 2 | Queue ×1, table ×1 | Tally |
| 3 | Channel drop at 11:00 (if og is fixed), queue ×1 | Count in the following hour |
| 4 | Office monolith, all day | Count during office hours |
| 5 | Queue ×1, table ×1; Show HN if both gates are cleared | HN points, count |
| 6–7 | Queue or table as it comes naturally | Tally; the non-event-day count (the return proxy) |

**Target:** about 100 humans typed (tally + counts above baseline). **The
question it answers:** do people type a second time without being asked, and do they
ask for the address? If yes, the product carries itself and social volume has
something to amplify. If not, no amount of posting will fix it; go back to the
product.

## Questions for Carlos

1. Is a personal project on a shared Havas screen and in a Havas channel OK
   (ideas 3 and 4)? If not, keep them to his own desk and his own screen.
2. Does the telemetry table have any per-client or IP hash? It decides whether
   returns can be measured at all, or only through the daily-volume proxy.

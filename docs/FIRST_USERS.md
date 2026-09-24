# First 100 humans

Owner: strategy brain (Opus 5.5), for Carlos + CoS, to converge with Soul and GTM.
Written 2026-09-24; revised the same day with Soul's input. No code. Nothing here
gets published without Carlos's yes.

**The bet.** antisearch.ai needs no install, no login and no explanation: one input,
one lowercase verdict. Its friction is a phone held out at arm's length, so the first
100 humans come fastest **in person**, from a screen that is already open. Social
posting builds the wall; it won't hand the product to a stranger. Every idea below
puts the blinking cursor in front of a person and then gets out of the way.

**The line (Soul's, adopted):**
- **On-voice:** one person at a time, **at most 3 spoken words**
  ("antisearch.ai. type anything."), no feedback asks, no filming.
- **Campaign (don't):** crowds, scripts, props, flyers, explaining that it's AI,
  share or feedback asks, filming strangers, incentives, group demos.
- Also: never "best", never "I built this" (if asked who made it: "me"), never
  explain a verdict.
- The one place I differ: Carlos **glances** at two facts (did they type again? did
  they ask the address?). Without that, the week measures nothing. He never
  comments and never asks.

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
| Stunts | **Allowed only if whisper-true** | Handing one stranger a phone is technically a stunt. It's allowed because it's one person, 3 words, no audience, and the product does all the talking. Still killed: anything staged, filmed, crowded or scripted |
| Stickers / QR codes | **Still killed** | Printing is spend, QR says "download our app", and stickers are litter |
| Handwritten card | **Revived, Soul's version only** | One card, handwritten `antisearch.ai`, **handed to one person**. No QR, no stack, no print run, never pinned on boards |
| Founder-story posts | **Still killed** | In person the founder is unavoidably there. The rule is he doesn't narrate |
| "We asked ai" framing | **Still killed** | The person asks, not us |
| Share cards | **Still killed** | Except the og card, which exists whether we like it or not; fix it |
| Countdowns, hashtags, replying in threads | **Still killed** | Nothing Carlos pushed changes these |
| Meetup slide (was a runner-up) | **Moved to reserve** | Agree with Soul: a crowd plus a scripted moment is a campaign |

---

## Raw ideas (18; 11 in person or ambient). (S) = Soul's

"Who" is Carlos (C), Havas colleagues (H), or bots via API (B).

| # | Idea | The move | Where it sits on Soul's line | Minimal signal |
| --- | --- | --- | --- | --- |
| 1 | **Say the domain and leave** (S) | To one person in a queue: "antisearch.ai. type anything." They type it on their own phone. Carlos leaves | On-voice | Count drift only (no tally), but the site is now in *their* browser history, which is the only way a return is possible |
| 2 | **Queue handoff** | Phone open on the cursor, held out to the person behind: "type anything" | On-voice | Tally |
| 3 | **The answer instead of an opinion** (S) | When anyone asks Carlos "what's the best X?", he types their bare words (no "best") and turns the screen to them. Silent | On-voice | Tally |
| 4 | **Idle screens** (S, merged with my office monolith) | antisearch.ai as the idle page on Carlos's laptop, the Havas meeting-room screen before calls, and a spare laptop at the coffee point. If asked: "type anything" | On-voice | Count during office hours; tally of who types |
| 5 | **Channel drop** | In one informal Havas channel, a message that is only `antisearch.ai`; never reply | Soul: a crowd. Me: on-voice (see disagreements) | Count in the following hour |
| 6 | **Show HN, cold, once** | As drafted in the GTM doc | Accepted earlier | HN points, count spike |
| 7 | **Device names** (S) | Phone hotspot, Bluetooth and AirDrop named `antisearch.ai`. They show up in café wifi lists and meeting rooms | On-voice | None (ambient) |
| 8 | **Status and signature** (S) | Slack/Teams status `antisearch.ai`; an email signature only if Havas policy allows | On-voice; policy-dependent | None (ambient) |
| 9 | **Handwritten card** (S revival) | One handwritten card handed to one person | On-voice | Tally |
| 10 | **Table handoff** | Phone face-up among friends, slid across: "type anything" | Soul: a group demo. Me: fine when it's natural | Tally (inputs per table) |
| 11 | **Barber / hairdresser chair** | Hand the phone to the stylist while waiting | On-voice | Tally |
| 12 | **WhatsApp Status clip** | A mill verdict clip as Carlos's WhatsApp Status, no text | Ambient | Status viewers + next-day count |
| 13 | **Colleague relay** | Colleagues who liked it leave it open in a tab | Ambient | Count trend on office days |
| 14 | **Meetup last slide** | One slide, the live site, a word from the room | Campaign (moved to reserve) | Count in the 30 minutes after |
| 15 | **Screen-share opener** | Every screen share starts on the cursor for a few seconds | Ambient (covered by 4) | None |
| 16 | **Bluesky wall** | The publisher's clips (already built) | — | Mentions search, count |
| 17 | **AI-tool directories** | A one-line listing | Borderline campaign | Weak |
| 18 | **Mention oracle** | Answer Bluesky mentions once a day (reserve) | Edge of "no chat" | Replies |

Dropped on sight:
- chalk on pavements;
- pitching it to Havas clients (a verdict could crown a client's competitor in front
  of the client);
- mass personal messages (Carlos says people ignore them);
- filming anyone's reaction.

### Where I disagree with Soul (one line each)

- **"Nobody watches the result":** for the first 20 handoffs Carlos must glance at
  two facts (a second input, the address asked), or the week proves nothing. He
  never comments and never asks.
- **Channel drop as a "crowd":** it's one message that is only the domain, with no
  script and no follow-up. It's the digital version of Soul's handed card, and our
  cleanest measurable test of a warm audience.
- **Table handoff as a "group demo":** nobody presents. I agree it must never be
  engineered, so it only happens when the phone is already out among friends. It's
  demoted to runner-up.
- **Email signature:** keep it to the internal Slack/Teams status. A signature
  travels into client threads, and that is ambient pitching to clients, which we
  both rule out.
- **Hotspot name:** agree, with one guard. Keep the hotspot password-protected, so
  the name is only a whisper and never an open network (a domain-named open hotspot
  reads as phishing).

---

## Top 5, ranked

Ranked by humans reached in 7 days per minute of Carlos's time, whether a return is
possible, and how clean the signal is.

### 1. Queue: say the domain; hold out the phone only if needed (Soul's "say the domain and leave" + my handoff)

- **Script:**
  - To one person in a queue: **"antisearch.ai. type anything."**
  - If they take out their own phone: say nothing more and turn back. This is the
    better outcome: the site is now in their browser history, so they can come
    back.
  - If they don't: hold out your phone, already open on the cursor. Take it back
    when it's handed back.
  - If asked what it is: **"try."**
- **Where:** Madrid café queues at the morning rush, bakeries, the Havas building
  café. One person per queue.
- **Effort:** 5 minutes a day, about 5–10 people a day → about 40 in the week.
- **Tally, from a glance only:**
  - own phone (y/n);
  - on Carlos's phone: typed again unprompted (y/n);
  - asked the address or photographed the screen (y/n).
- **Success:** **≥ 30% type on their own phone**; of the handed-phone ones,
  **≥ 40% type a second input unprompted.**
- **Kill:** after 20 people, under 15% use their own phone and under 20% type again.
  The product doesn't carry in ten seconds; stop and go back to the product.

### 2. The answer instead of an opinion (Soul's)

- **Script:** someone asks Carlos "what's the best X?" (a restaurant, a laptop, a
  gift). He types **X**, their bare words without "best", turns the screen to them,
  and says nothing. If asked: **"antisearch.ai."**
- **Where:** anywhere: Havas corridors, lunch, friends, family. It happens when it
  happens.
- **Effort:** 0 minutes; about 3–6 occurrences a week.
- **Success:** **≥ 1 in 2 ask the address** or type a second input themselves. These
  are the highest-intent humans in the whole plan: they came with a question.
- **Kill:** it costs nothing, so it never stops. After 6 occurrences with nobody
  asking the address, though, it's a charming habit, not a channel.

### 3. Idle screens (Soul's 4, merged with my office monolith)

- **Script:**
  - Set antisearch.ai, in full screen, as the idle page on Carlos's laptop and on
    the Havas meeting-room screen before calls (and a spare laptop at the coffee
    point, if policy allows).
  - No note, no sign. If asked: **"type anything."**
- **Where:** the Havas Madrid office for one working week; Carlos checks policy for
  shared screens.
- **Effort:** 10 minutes, once.
- **Success:** **≥ 15 verdicts during office hours** on a screen day above the
  baseline, and people mentioning it to Carlos unprompted.
- **Kill:** fewer than 5 people type across two office days.

### 4. Channel drop (mine; Soul disagrees, see above)

- **Script:** in one informal Havas channel (not a client channel), a message that is
  exactly **`antisearch.ai`**. Never reply; react to nothing.
- **Where:** Havas Slack or Teams, Tuesday–Thursday around 11:00 Madrid. Once.
- **Effort:** 1 minute. Prerequisite: the og fix, or the unfurl says
  `type. AI decides`.
- **Success:** **≥ 20 verdicts in the following hour** above the baseline.
- **Kill:** under 10 verdicts in that hour. Never post in a second channel.

### 5. Show HN, cold, once (gated)

- **Script:** exactly as drafted in `GTM_OUT_OF_THE_BOX.md`: the title, the two-line
  first comment, no replies, no upvote asks.
- **Effort:** 5 minutes. **Gates:** the og fix is live, and the per-verdict cost /
  global cap is confirmed.
- **Success:** the front page, or **≥ 100 verdicts above the baseline** within 6 hours.
- **Kill:** under 5 points after 2 hours; never repost.

**Always on, free, not ranked (they can't be measured):** device names (7) and the
Slack/Teams status (8). Set them on day 1 and forget them. The handwritten card (9)
is for the moment someone says "what was that called?" and has no phone at hand.
**Runners-up:** table handoff (only when natural) and the barber chair.

---

## The 7 days, concretely

| Day | Carlos | Signal to note |
| --- | --- | --- |
| 1 | Try one Spanish input himself. Note a baseline count. Set the device names, the Slack/Teams status and the idle screens. Queue ×1 | Tally, count |
| 2 | Queue ×1 | Tally |
| 3 | Channel drop at 11:00 (if og is fixed); queue ×1 | Count in the following hour |
| 4 | Queue ×1 | Tally, office-hours count (idle screens) |
| 5 | Queue ×1; Show HN if both gates are cleared | HN points, count |
| 6–7 | Queue when natural | Tally; the non-event-day count (the return proxy) |
| Any day | "The answer instead of an opinion" whenever someone asks | Tally |

**Target:** about 100 humans typed (tally + counts above baseline). **The
question it answers:** do people type the domain on their own phone, and type a
second time without being asked? If yes, the product carries itself and social
volume has something to amplify. If not, no amount of posting will fix it; go back
to the product.

## Questions for Carlos

1. Is a personal project OK on a shared Havas screen, in a Havas channel and in a
   Slack/Teams status (ideas 4, 5, 8)? If not, keep them to his own laptop and
   screen.
2. Does the telemetry table have any per-client or IP hash? It decides whether
   returns can be measured at all, or only through the daily-volume proxy.

# Surprising inputs (Part C, founder order 2026-09-25)

Funny, trendy, surprising, and still the product: one bare English input, one
lowercase verdict, full stop.
- No "best" in the input, no caption, no explanation.
- Each input gets one honest run: nobody test-asks them before they post.
- The joke is the gap between a silly input and a flat, final answer. We never
  write the joke; the oracle's deadpan is the joke.

| # | Input | Why it's funny or timely |
| --- | --- | --- |
| 1 | `monday` | Everyone has a view; the oracle ends the debate |
| 2 | `excuse` | The universal need, answered with authority |
| 3 | `red flag` | Dating-internet vocabulary |
| 4 | `green flag` | The pair to 3, posted on another network |
| 5 | `the ick` | Gen-Z slang; a verdict on the ick is absurd and shareable |
| 6 | `situationship` | Trending relationship word; a verdict *is* a take |
| 7 | `rizz` | Slang the oracle takes completely seriously |
| 8 | `aura` | "Aura points" culture |
| 9 | `breakup text` | Painfully specific |
| 10 | `apology` | One word, a thousand stories |
| 11 | `hangover cure` | A real question, answered in one line |
| 12 | `first date` | Everyone screenshots dating advice |
| 13 | `karaoke song` | A contested choice with a flat answer |
| 14 | `dad joke` | The oracle picking one is itself a dad joke |
| 15 | `plot twist` | Meta: the verdict is the twist |
| 16 | `guilty pleasure` | Confessional, but the oracle's, not ours |
| 17 | `pet peeve` | Relatable, argument-starting |
| 18 | `reason to stay in bed` | Deadpan as a service |
| 19 | `office snack` | LinkedIn-native silliness |
| 20 | `villain` | Pop-culture bait with a single name |

All 20 pass the input guard: bare, English, not serial, never "best", unique
against the pools.

## Self-run test (we run it; no need to ask Carlos)

**What goes out:** six of them, from `queue/surprise_trial.csv`, at the normal slots
(explicit queue rows go before the pools):

| Network | Inputs |
| --- | --- |
| TikTok | `red flag`, `the ick` |
| Instagram | `situationship`, `hangover cure` |
| LinkedIn | `monday` |
| Bluesky | `excuse` (when the account exists) |

**Signal, at 48h per post:**
- **shares + saves** (TikTok and Instagram insights in the apps or Buffer); reposts
  + likes on Bluesky (API); reactions on LinkedIn;
- compared with the **median of that network's pool posts** from the same week;
- plus antisearch.ai verdicts in the 2 hours after each post, above the baseline,
  once Pulse or the Supabase count is available.

**Keep rule:** 2 or more of the 6 beat the median by **2×** on shares + saves (or
views on TikTok). Then the other 14 go into the pools at about 1 in 5 posts. The
unowned-word rhythm (1 in 4) stays as it is.

**Kill rule:**
- None of the 6 beats the median by **1.5×**: drop the lane; the pools are enough.
- **Any** post draws mostly hostile or "cringe" comments, or a platform warning:
  stop the lane that day.
- Never re-run a surprise input: one honest run, and a winner is never re-queued.

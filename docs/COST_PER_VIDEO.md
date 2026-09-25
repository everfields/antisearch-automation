# Cost per video

Marginal cost of producing and publishing **one** clip, and of a month at the soul
cadence the founder named on 2026-09-25: TikTok 5/day, Bluesky 3/day, Instagram
1/day, LinkedIn 1/day. That is **10 clips/day, 300 clips in a 30-day month**.

The code preset `PUBLISHER_CADENCE=soul` still has Instagram at 3/day (12 clips/day).
The table below uses the founder's 1/day. The cron does not get busier just
because a number in the table changes; see the minutes section.

Prices were read on **2026-09-25**.

## The line

**Above this line: one-off build cost. It is not part of a video.**

Writing this mill (Cloud Agent runs, including this one) is a build cost. It does
not run again when a clip is published. It is not on the per-video bill, and it
is not given a dollar figure here: there is no public rate card for that compute
the way there is for GitHub Actions.

**Below this line: what it costs to make and post one more clip.**

The per-video path is only this, inside `.github/workflows/publisher.yml`:

1. one `POST https://antisearch.ai/verdict` (the product's oracle);
2. ffmpeg, on the Actions runner;
3. the network's official API, or Buffer's free API (`createPost`).

That path uses **zero LLM agent compute**: no Grok Bot agent, no Cloud Agent, no
browser, no one driving Buffer's website. If the Buffer API fails, the post is
`failed` in the log. It is not uploaded by hand.

## Oracle call

The live response does not name a model. The single call made for this change,
2026-09-25T11:34:16Z, `{"category":"thing"}`, returned HTTP 200 in **2458 ms**
with body `{"verdict":"love"}` and no model header (`server: uvicorn` only).
The same shape is what `LiveOracle` already stores: a short lowercase string.

`everfields/the_best` (the product repo that chooses the provider, the model,
and the system prompt) returns 404 to this environment's GitHub token, so this
document does not invent a provider or a token count. A price computed from a
guessed model would be a false number. The output side is observable and small
(`love` is one word; the frozen verdicts are one to four words). The input side
is the system prompt plus the bare category, and the prompt is not in this repo.

What this repo pays for the call: **$0**. The HTTP request is free. Whatever the
product pays its model vendor is a cost of antisearch.ai, not of the Actions
bill, and it is **unknown until `the_best` is readable**.

There is still no published global cap on `/verdict` in this repo.

## ffmpeg

Measured on this machine while rendering the 2026-09-25 masters (1080×1920,
5.0s, silent AAC, libx264 crf 18): **0.73–0.93 seconds** wall clock per clip.
The 1080×1080 variant was 0.48s, the 600px GIF 0.48s, the 600px loop mp4 0.54s.
A master file is about **40–64 KB**.

ffmpeg is free software. Its time is part of the Actions minute below, not a
second invoice.

## GitHub Actions minutes

Workflow: `.github/workflows/publisher.yml`, `runs-on: ubuntu-24.04` (standard
Linux 2-core). Cron `7 0-5,13-23 * * *` wakes **17 times a day**. GitHub rounds
each job up to the next whole minute
([runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing),
read 2026-09-25).

No publish run has completed yet: the scheduled runs on 2026-09-25 were
`skipped` in under a second because `PUBLISHER_CRON` is unset (runs
[36108837842](https://github.com/everfields/antisearch-automation/actions/runs/36108837842)
and
[36081892889](https://github.com/everfields/antisearch-automation/actions/runs/36081892889)).
The durations below are from the steps that do exist, on CI run
[36071405664](https://github.com/everfields/antisearch-automation/actions/runs/36071405664)
(2026-09-24, same `ubuntu-24.04`):

| step | measured |
| --- | --- |
| checkout + setup-python | ~2s |
| `pip install` | 5s |
| `apt-get install ffmpeg fonts-inter` | 31s |

An idle wake (nothing due) stops after `mill due` and does **not** install
ffmpeg. Wall clock about 10s, billed as **1 minute**.

A wake that posts also installs ffmpeg (31s), asks the oracle (~2.5s, measured),
and renders (~1s here; a few seconds on the 2-core runner). Without waiting on
GitHub Pages that is about 50s, billed as **1 minute**. If the bridge or
Instagram native has to wait for Pages, add the time Pages takes to publish the
file; that was not measured. Call that case **2 minutes**.

At the founder's 10 posts/day the slot clock (EDT, September 2026) puts work in
**8** of the 17 hours (09:07 carries LinkedIn and Bluesky together; 18:07 carries
TikTok and Bluesky). The other **9** hours are idle.

| | per day | per 30-day month |
| --- | --- | --- |
| Lower (1 min every wake) | 17 min | 510 min |
| Upper (idle 1 min, busy 2 min) | 25 min | 750 min |

Both sit inside the **2,000 minutes/month** included for a private repo on
GitHub Free
([Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
read 2026-09-25). CI on this repo shares that quota. One CI job on 2026-09-24
ran 2m11s and so bills as 3 minutes. That is not a per-video cost.

List price **after** the free minutes are gone, Linux 2-core `actions_linux`:
**$0.006 per minute** (same pricing page). If a spending limit above $0 is not
set, Actions stops instead of billing.

## Buffer

Already the free API, not the website. The switch:

1. Secret `BUFFER_API_KEY` (publish.buffer.com → Settings → API).
2. Variable `PUBLISHER_BRIDGE=buffer`.
3. Optional `BUFFER_CHANNEL_INSTAGRAM`, `BUFFER_CHANNEL_LINKEDIN`, `BUFFER_CHANNEL_TIKTOK`, `BUFFER_CHANNEL_X`.

`.github/workflows/publisher.yml` passes the secret into `mill post`.
`publisher/buffer.py` posts to `https://api.buffer.com` (`createPost`,
`shareNow`). Each post is one create plus up to two status reads
(`STATUS_POLLS = 3`). At 300 posts/month that is about **900 requests**, under
the free plan's 3,000 requests / 30 days (checked in `PUBLISHER_SETUP.md` on
2026-09-24). **$0.** Delete `PUBLISHER_BRIDGE` and Buffer is gone.

## Storage

A master is ~50 KB. 300 of them are ~15 MB in git (the public clips repo and
`publisher-state`). That is not Actions artifact storage.

The workflow uploads logs, kept 7 days. GitHub Free includes **500 MB** of
artifact storage; overage is **$0.25 per GB-month** (same Actions billing page).
At this size the overage is **$0**.

## The numbers

Known marginal cost, oracle vendor excluded because the model is not visible
from here:

| | per video | per month (300 videos) |
| --- | --- | --- |
| Oracle HTTP from Actions | $0 | $0 |
| Oracle model vendor | unknown | unknown |
| ffmpeg license | $0 | $0 |
| Actions minutes, inside the 2,000 free | $0 | $0 |
| Actions minutes, if the free quota is already used (lower–upper) | $0.010–$0.015 | $3.06–$4.50 |
| Buffer free API | $0 | $0 |
| Artifact storage | $0 | $0 |
| **Known total, inside the free minutes** | **$0** | **$0** |
| **Known total, if Actions minutes are billed** | **$0.010–$0.015** | **$3.06–$4.50** |

The unknown line is one model call per clip, paid by antisearch.ai, with a
measured latency of about 1.6–3.0s on the four frozen runs and 2.458s for
`thing`. It is not an agent, and this pipeline must not grow one.

A live post whose jittered minute is still ahead waits up to 9 minutes inside
the same Actions job (`docs/ANTI_BAN.md`). That wait is billed. A negative
offset does not wait. At the founder's 10 posts/day the extra is a few
minutes each on the posts that land after :07, on top of the minute table
above, and it stays inside the 2,000 free minutes unless most offsets are
near the +9 cap and the idle wakes are already at the upper estimate. Set
`PUBLISHER_JITTER=off` to drop the wait.

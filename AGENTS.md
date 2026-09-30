# AGENTS.md

Context for every coding agent working in this repo (Cursor, Claude Code, others).

## North star (founder, Carlos, 2026-09-28)

- **Social networks are an instrument to bring people to antisearch.ai, not the product.**
- **The web and user repetition decide everything.** Repetition (people who come back and
  query again, and how often) is the #1 metric, measured daily. It is the go signal for
  Android.
- **We play brand, meaning and cultural reference** (the AI's single answer to any input),
  not performance marketing.
- **The odds are very low; we try anyway**, with out-of-the-box ideas.
- **Radical simplicity and brutal honesty.**

How to measure repetition: `docs/proposals/2026-09-28-repetition-metric.md`.

## Inputs are bare (founder, 2026-09-29; the root error)

- An input **never** contains "best", "top", "greatest", "what's the" or any superlative. It is
  bare: `80s horror movie`, `university to study electrical engineering`.
- "The best" is invisible and behind the scenes. The user infers the pattern of excellence from
  the results. The result is the product and the pattern.
- The settle media made from question inputs ("what's the best horror movie in the 80s") were a
  serious brand mistake.
- Every lane (settle, the IG/TikTok/X queues and pools, trend, reply, winner, reverse oracle)
  runs `bare_input.superlative_problem`. The oracles and `produce` refuse a ranked input.
- Another person's question is reduced to its bare noun phrase by `bare_input.from_question`
  ("what's the best 80s horror movie?" becomes `80s horror movie`). If no clean noun is left,
  the thread is skipped.
- Soul, 2026-09-29: no "-est" superlative and no "#1" in inputs, captions or tags
  (`bare_input.ranked_word`). An Instagram hashtag that would carry one is left out; a tag handle
  with one is never used.

## X rule (founder, 2026-09-28 evening; replaces the morning's no-mention rule)

- An X post is **plain text only**, never media (founder, 2026-09-29): `input`, then `verdict`, lowercase. When the verdict **is** an account, a third
  line carries its `@handle` (`search engine` / `kagi` / `@KagiHQ`).
- **At most 1 mention per post.** The account must be the verdict itself, never its maker or
  owner. It must be in `queue/tags/allowlist.json` with a verified `x` block (evidence, checked
  within 30 days). Never a person, never amika or any Bansk brand.
- **Never the same account within 14 days**, tracked in publisher-state `tags.csv`.
- **Unchanged:** X cadence and random offset, no hashtags, links or emoji, no trend-lane,
  winner-lane or reply posts, and the near-duplicate guard.
- `PUBLISHER_X_MENTIONS=off` stops mentions; they are on by default.

## settle it: a text-only list, no agent

- Carlos posts on Reddit himself. The `settle-pack` workflow runs every 2 days and writes
  `settle/threads-YYYY-MM-DD.md`, with up to 20 rows of thread URL, bare input and frozen
  output (one internal run each).
- No images, GIFs, video or captions. The old settle media are deprecated: never regenerate
  them.
- Never re-ask a frozen input. See the README section "settle it thread list".

## Instagram creative (founder, 2026-09-29)

- Only `0-current-cover`: the first, clean creative (the keys, then silence, and the verdict
  appears in the silence), with the output-only cover as its frame 0.
- The cover is the monolith's last frame, output only, with the same font and size. It is only
  the grid thumbnail and never an added still: it replaces frame 0 (1/30 s), and Buffer's
  `thumbnailOffset` points there. Buffer accepts no cover image for a reel.
- The rotation is off until Carlos says otherwise (`PUBLISHER_IG_ROTATION=on` brings it back).
  Every Instagram creative carries that cover, so every grid tile is the big output.
- Peers in excellence side by side is what Carlos values most on the grid.
  `PUBLISHER_IG_CLUSTER=on` (a proposal, off by default) draws the pool by family, by fixed
  rules.
- X and TikTok are unchanged.

## Publishing reliability

- GitHub's schedule drops most wakes. The next run sends the most recently missed slot
  (one, within 6 h), with the 90-minute gap and the random offset kept.
- An external pinger wakes the publisher like the cron: `workflow_dispatch` with `tick=true`
  (Carlos's box, :11/:26/:41/:56), or a `publisher-tick` `repository_dispatch`
  (docs/PUBLISHER_SETUP.md, "Reliable wakes"). A dispatch without `tick` is a manual run.
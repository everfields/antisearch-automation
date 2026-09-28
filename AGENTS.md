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

## X rule (founder, 2026-09-28 evening; replaces the morning's no-mention rule)

- An X post is `input`, then `verdict`, lowercase. When the verdict **is** an account, a third
  line carries its `@handle` (`search engine` / `kagi` / `@KagiHQ`).
- **At most 1 mention per post.** The account must be the verdict itself, never its maker or
  owner. It must be in `queue/tags/allowlist.json` with a verified `x` block (evidence, checked
  within 30 days). Never a person, never amika or any Bansk brand.
- **Never the same account within 14 days**, tracked in publisher-state `tags.csv`.
- **Unchanged:** X cadence and random offset, no hashtags, links or emoji, no trend-lane,
  winner-lane or reply posts, and the near-duplicate guard.
- `PUBLISHER_X_MENTIONS=off` stops mentions; they are on by default.

## settle it packs need no agent

Building a settle-it pack is scripted and needs zero LLM or Cursor credits. See the README
section "settle it packs".
- **Find:** the `settle-pack` workflow drafts a pack daily, or on dispatch with `step: find`.
- **Review:** a human deletes rows.
- **Shoot:** dispatch `settle-pack` with `step: shoot` for one live run per row (frozen), the
  screenshot, and the media.
- **Media:** `settle-media` renders any missing card PNG, GIF or MP4 hourly. The card is square
  big type with no phone frame, so it stays legible in a Reddit comment thumbnail; don't go
  back to 9:16 or a phone frame.

Don't rebuild packs by hand in an agent session. Never re-ask a frozen input.

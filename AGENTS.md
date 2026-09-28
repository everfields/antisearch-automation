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

## settle it packs need no agent

Building a settle-it pack is scripted and needs zero LLM or Cursor credits. See the README
section "settle it packs".
- **Find:** the `settle-pack` workflow drafts a pack daily, or on dispatch with `step: find`.
- **Review:** a human deletes rows.
- **Shoot:** dispatch `settle-pack` with `step: shoot` for one live run per row (frozen), the
  screenshot, and the GIF and MP4.
- **Media:** `settle-media` renders missing GIF and MP4 files hourly.

Don't rebuild packs by hand in an agent session. Never re-ask a frozen input.

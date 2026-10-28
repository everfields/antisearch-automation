"""TikTok celebrity lane (founder, Carlos, 2026-10-26).

Reverse-engineered inputs: bare inputs (no superlative, never the person's name) whose real
oracle verdict, in a one-call dry run, was a mega account (a person, group or entity with a
verified official TikTok). The lane posts them so the caption can tag that account, exactly
like a brand: `<input> → <verdict> @handle` or `<input> @handle`, alternating as today.

- Pools: `queue/pools/tiktok_celeb.txt` (English) and `queue/pools/tiktok_es_celeb.txt` (Spanish).
- One celebrity post a day, about 1 in 5 TikTok posts. The slot rotates by posting day over the
  non-trend slots: 16:07 en, 13:07 es, 00:07 en (slot indexes 1, 0, 3). The trend slots (20:07 es,
  05:07 en) are untouched, and the language of every slot is unchanged (3 English + 2 Spanish).
- The lane waits for the midtype creative test (PR #68): it starts at PUBLISHER_TT_CELEB_START
  (default 2026-10-29) and only once the midtype window is complete, so no celebrity input ever
  sits in a midtype comparison slot while the test runs.
- The publisher asks the oracle again at post time (one honest run, then frozen). If that verdict
  has no allowlisted TikTok handle, the celebrity input is skipped (`skipped_celeb_untagged`),
  never posted untagged; the brand guard still covers brand-looking verdicts.
- `PUBLISHER_TT_CELEB=off` stops the lane.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

from . import midtype

CELEB_NOTE = "pool:celeb"
CELEB_SLOT_CYCLE = (1, 0, 3)
DEFAULT_START = date(2026, 10, 29)
# One-off early turns (founder, Carlos, 2026-10-28 00:01 Madrid: "Let's try some famous people
# tonight in US", "uno o dos"): posting day -> slot indexes whose regular input is replaced by a
# celebrity input, regardless of the start date and the midtype window. Slot 3 is the 00:07 en
# slot and slot 4 the 05:07 en slot. Posting day 2026-10-27 never posted one (00:07 went before the
# merge, 05:07 never ran), so it moves to posting day 2026-10-28: 00:07 and 05:07 Madrid on Oct 29
# (19:07 and 00:07 New York). Only the input changes; the midtype creative of each slot is unchanged.
FORCED_TURNS: dict[date, tuple[int, ...]] = {date(2026, 10, 28): (3, 4)}


def enabled(env: Mapping[str, str]) -> bool:
    return (env.get("PUBLISHER_TT_CELEB") or "on").strip().lower() not in ("off", "0", "false", "no")


def start(env: Mapping[str, str]) -> date:
    raw = (env.get("PUBLISHER_TT_CELEB_START") or "").strip()
    return date.fromisoformat(raw) if raw else DEFAULT_START


def is_celeb(notes: str) -> bool:
    return (notes or "").startswith(CELEB_NOTE)


def midtype_done(env: Mapping[str, str], rows: Iterable[Mapping[str, str]]) -> bool:
    return not midtype.enabled(env) or midtype.midtype_posts(rows) >= midtype.window(env)


def celeb_slot(day: date, env: Mapping[str, str]) -> int | None:
    """The slot index that carries today's celebrity input, or None before the lane starts."""
    offset = (day - start(env)).days
    if offset < 0:
        return None
    return CELEB_SLOT_CYCLE[offset % len(CELEB_SLOT_CYCLE)]


def is_celeb_turn(day: date, slot_index: int, env: Mapping[str, str], rows: Iterable[Mapping[str, str]]) -> bool:
    if not enabled(env):
        return False
    if slot_index in FORCED_TURNS.get(day, ()):
        return True
    slot = celeb_slot(day, env)
    return slot is not None and slot == slot_index and midtype_done(env, list(rows))


def order_celeb(jobs: list, turn: bool) -> list:
    """On the celebrity slot, celebrity jobs go first (in their slot-language order); elsewhere they are dropped."""
    celeb = [j for j in jobs if tuple(j.platforms) == ("tiktok",) and is_celeb(j.notes)]
    if not celeb:
        return jobs
    rest = [j for j in jobs if j not in celeb]
    if not turn:
        return rest
    first = next((i for i, j in enumerate(rest) if tuple(j.platforms) == ("tiktok",)), len(rest))
    return rest[:first] + celeb + rest[first:]

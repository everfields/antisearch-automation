"""TikTok debate lane (founder, Carlos, approved 2026-11-04).

One of the five daily TikTok posts uses a debate-style input: a bare, neutral input whose single
verdict people will want to argue with ("tennis player", "pizza topping"). The lane only changes
which input fills one slot; cadence, the 5-per-24h cap, spacing, jitter and captions are unchanged.

- Pool: `queue/pools/tiktok_debate.txt` (English).
- Slot: 16:07 Madrid, English (slot index 1), every posting day from PUBLISHER_TT_DEBATE_START
  (default 2026-11-05). On the days the celebrity lane rotates onto 16:07 (celeb.CELEB_SLOT_CYCLE),
  the celebrity input goes first and the debate input is its fallback.
- One honest oracle run per input, as everywhere: whatever verdict comes out is posted (the brand
  guard and @handle captions still apply). Never re-run to fish for a better verdict.
- `PUBLISHER_TT_DEBATE=off` stops the lane; the slot then draws from the regular pools.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

DEBATE_NOTE = "pool:debate"
DEBATE_SLOT = 1  # 16:07 Madrid, English
DEFAULT_START = date(2026, 11, 5)


def enabled(env: Mapping[str, str]) -> bool:
    return (env.get("PUBLISHER_TT_DEBATE") or "on").strip().lower() not in ("off", "0", "false", "no")


def start(env: Mapping[str, str]) -> date:
    raw = (env.get("PUBLISHER_TT_DEBATE_START") or "").strip()
    return date.fromisoformat(raw) if raw else DEFAULT_START


def is_debate(notes: str) -> bool:
    return (notes or "").startswith(DEBATE_NOTE)


def is_debate_turn(day: date, slot_index: int, env: Mapping[str, str]) -> bool:
    return enabled(env) and day >= start(env) and slot_index == DEBATE_SLOT


def order_debate(jobs: list, turn: bool) -> list:
    """On the debate slot, debate jobs go first among the TikTok jobs; elsewhere they are dropped."""
    debate = [j for j in jobs if tuple(j.platforms) == ("tiktok",) and is_debate(j.notes)]
    if not debate:
        return jobs
    rest = [j for j in jobs if j not in debate]
    if not turn:
        return rest
    first = next((i for i, j in enumerate(rest) if tuple(j.platforms) == ("tiktok",)), len(rest))
    return rest[:first] + debate + rest[first:]

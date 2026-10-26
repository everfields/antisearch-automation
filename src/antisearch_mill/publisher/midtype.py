"""TikTok creative test: `midtype` (the clip opens mid-typing) against the original clip.

Carlos approved it on 2026-10-23 and Soul agreed. The original format keeps running, and the
formula/calc creative stays deprecated on TikTok.

Allocation is a fair, fixed window. Plain day parity (every slot on day N is midtype) would put
5 variant posts on one day, which is more than the 4-post window, so the test pairs slots
across two days instead:

  test day 0 (PUBLISHER_TT_MIDTYPE_START): slots 0 and 1 (13:07 es, 16:07 en Madrid) are midtype,
                                           slots 2 and 3 (20:07 es, 00:07 en) are original
  test day 1:                              slots 0 and 1 are original, slots 2 and 3 are midtype
  slot 4 (05:07 en, the US trend slot) is always original and stays out of the comparison.

Each of the four test slots therefore has one midtype and one original post, a day apart, in
the same slot and language: 4 variant posts and 4 matched originals over 2 posting days. The
cycle repeats while fewer than PUBLISHER_TT_MIDTYPE_POSTS (default 4) midtype posts have gone
out (posts.csv `creative_variant`), so a skipped slot is made up later. After that, every
TikTok post is original again, with no deploy needed.

A "day" is the publisher's posting day, which matches the Madrid calendar day of the
13:07-20:07 slots. The 00:07 and 05:07 Madrid slots fall after midnight but belong to that
posting day.

Env:
  PUBLISHER_TT_MIDTYPE        on (default) | off: off means original only
  PUBLISHER_TT_MIDTYPE_POSTS  window size in midtype posts (default 4); raise it to extend the test
  PUBLISHER_TT_MIDTYPE_START  first test posting day, YYYY-MM-DD (default 2026-10-27)
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

from ..creatives import MIDTYPE

ORIGINAL = "original"
VARIANTS = (ORIGINAL, MIDTYPE)
DEFAULT_POSTS = 4
DEFAULT_START = date(2026, 10, 27)
TEST_SLOTS = (0, 1, 2, 3)
_DONE = ("published", "drafted", "scheduled")


def enabled(env: Mapping[str, str]) -> bool:
    return (env.get("PUBLISHER_TT_MIDTYPE") or "on").strip().lower() not in ("off", "0", "false", "no")


def window(env: Mapping[str, str]) -> int:
    raw = (env.get("PUBLISHER_TT_MIDTYPE_POSTS") or "").strip()
    return int(raw) if raw else DEFAULT_POSTS


def start(env: Mapping[str, str]) -> date:
    raw = (env.get("PUBLISHER_TT_MIDTYPE_START") or "").strip()
    return date.fromisoformat(raw) if raw else DEFAULT_START


def midtype_posts(rows: Iterable[Mapping[str, str]]) -> int:
    """TikTok midtype posts that went out, one per job."""
    return len({r.get("job_id", "") for r in rows if r.get("network") == "tiktok"
                and r.get("creative_variant") == MIDTYPE and r.get("status") in _DONE})


def scheduled_variant(day: date, slot_index: int, first: date = DEFAULT_START) -> str:
    """The two-day pattern alone, without the window: which format slot `slot_index` gets on `day`."""
    offset = (day - first).days
    if offset < 0 or slot_index not in TEST_SLOTS:
        return ORIGINAL
    early = slot_index < 2
    return MIDTYPE if early == (offset % 2 == 0) else ORIGINAL


def tiktok_creative(day: date, slot_index: int, env: Mapping[str, str], rows: Iterable[Mapping[str, str]]) -> str:
    """`midtype` or `original` for the TikTok post filling slot `slot_index` on posting day `day`."""
    if not enabled(env):
        return ORIGINAL
    if scheduled_variant(day, slot_index, start(env)) != MIDTYPE:
        return ORIGINAL
    return MIDTYPE if midtype_posts(rows) < window(env) else ORIGINAL

"""Instagram creatives: one fixed template each, rendered on CPU from the clip's timeline and text.

Founder, 2026-09-29: until Carlos says otherwise every Instagram reel is `0-current-cover`, the
first, clean creative (the keys, then silence, and the verdict appears in the silence) with the
cover still appended (creatives/cover.py). The rotation is off by default; `PUBLISHER_IG_ROTATION=on`
brings back the four-creative Latin square (docs/IG_ROTATION.md):
  0-current           the current clip, unchanged (TikTok's too)
  1-short-score       the current picture, the keys plus the template score
  2-medium-monolith   the monolith: the camera dives onto the input, then the verdict alone
  3-computation       the monolith, the wait shown as a huge model computing
and `story`, the 1080x1920 Stories card (PUBLISHER_IG_STORIES, on by default since 2026-09-28).

Nothing is authored per verdict and no model is called: every creative is a function of the
input, the frozen verdict, and the timeline.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Mapping

from ..phone import PhoneSpec, geometry
from ..render import Layout, render_clip
from ..timeline import Timeline

CURRENT = "0-current"
SHORT_SCORE = "1-short-score"
MONOLITH = "2-medium-monolith"
COMPUTATION = "3-computation"
STORY = "story"
CLEAN_COVER = "0-current-cover"
IG_ROTATION = (CURRENT, SHORT_SCORE, MONOLITH, COMPUTATION)
CREATIVES = (*IG_ROTATION, CLEAN_COVER, STORY)
MOTION = (MONOLITH, COMPUTATION)


def rotation_enabled(env: Mapping[str, str]) -> bool:
    """Off by default (founder, 2026-09-29): Instagram posts CLEAN_COVER only. `on` restores the rotation."""
    return (env.get("PUBLISHER_IG_ROTATION") or "off").strip().lower() in ("on", "1", "true", "yes")


def ig_creative(day: date, slot_index: int) -> str:
    """The creative of slot `slot_index` (0-based, posting-day order) on posting day `day`."""
    return IG_ROTATION[(day.toordinal() + slot_index) % len(IG_ROTATION)]


def id_tag(creative: str) -> str:
    """What the creative adds to the clip id: nothing for the current clip, so its id never changes."""
    return "" if creative in ("", CURRENT) else creative


def finish(creative: str, classic: Path, timeline: Timeline, out: Path, *, category: str, verdict: str,
           font_path: str, layout: Layout, phone: PhoneSpec | None,
           metadata: dict[str, str] | None = None) -> float | None:
    """Write `creative` to `out` from the classic clip (the current creative, keys audio included).

    Returns the cover time in seconds when it is not the default (the verdict's last frames)."""
    if creative in ("", CURRENT):
        if classic != out:
            shutil.move(str(classic), out)
        return None
    if creative == CLEAN_COVER:
        from .cover import append_cover

        return append_cover(classic, out, verdict, duration_s=timeline.duration_s, font_path=font_path,
                            layout=layout, metadata=metadata)
    from .monolith import add_score, cover_s, render_motion

    if creative == SHORT_SCORE:
        add_score(classic, timeline, out, category=category, verdict=verdict, metadata=metadata)
        return None
    if creative not in MOTION:
        raise ValueError(f"unknown creative {creative!r}; choose one of {', '.join(IG_ROTATION)}")
    big = Layout(layout.width * 2, layout.height * 2, layout.fps)
    source = out.with_name(out.stem + "-source2x.mp4")
    try:
        render_clip(timeline, source, font_path=font_path, layout=big, phone=phone)
        if phone is not None:
            g = geometry(phone, big.width, big.height)
            screen = (g.screen_x, g.screen_y, g.screen_w, g.screen_h)
        else:
            screen = (0, 0, big.width, big.height)
        overlay, ticks = None, False
        if creative == COMPUTATION:
            from .computation import Computation

            overlay, ticks = (lambda mono: Computation(mono, category=category, font_path=font_path)), True
        render_motion(classic, source, screen, timeline, out, category=category, verdict=verdict,
                      font_path=font_path, layout=layout, overlay=overlay, ticks=ticks, metadata=metadata)
    finally:
        source.unlink(missing_ok=True)
    return cover_s(timeline)

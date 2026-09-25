"""Pure clip timeline: empty cursor -> typing -> still pause -> verdict.

Frame-indexed and deterministic: the typing jitter is seeded from the
category, so the same (category, verdict, pause) always renders the same clip.

Soul lock, 2026-09-25, approved by CoS: the thinking pause is blank time
with the typed input and a blinking caret only. No spinner, no dots, no
"thinking" text. This does not follow antisearch.ai. If the site adds any of
those, the clip still does not. The site fetched that day hides `.mirror` on
submit and leaves `#cursor` blinking; the clip keeps the completed input up,
because a blank caret for the whole wait does not read as a question.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

MIN_SECONDS = 5.0  # about 5s; the visible wait is the point of the clip
MAX_SECONDS = 8.0  # about 8s; the old <=4s cap is lifted
MIN_PAUSE_S = 1.2
MAX_PAUSE_S = 3.5
DEFAULT_PAUSE_S = 2.0  # used only when the oracle call's latency was not recorded

LEAD_S = 0.30
CHAR_BASE_S = 0.065
CHAR_JITTER = 0.35
TYPING_CAP_S = 1.5
HOLD_AFTER_TYPING_S = 0.22
MIN_RESULT_S = 1.0


@dataclass(frozen=True)
class State:
    start: int  # first frame, inclusive
    end: int  # last frame, exclusive
    kind: str  # "typing" | "loading" | "result"
    text: str
    cursor: bool


@dataclass(frozen=True)
class Timeline:
    fps: int
    total_frames: int
    states: tuple[State, ...]
    submit_frame: int
    verdict_frame: int
    pause_s: float

    @property
    def duration_s(self) -> float:
        return self.total_frames / self.fps


def clamp_pause(seconds: float) -> float:
    """Wall-clock oracle latency, held inside the visible-wait window."""
    return min(MAX_PAUSE_S, max(MIN_PAUSE_S, seconds))


def pause_from_latency_ms(latency_ms: int | None, *, recorded: bool = True) -> float:
    """Pause length for one honest run. Unrecorded latency uses the 2.0s note, not a guess from a neighbour."""
    if not recorded or latency_ms is None:
        return DEFAULT_PAUSE_S
    return clamp_pause(latency_ms / 1000.0)


def _seed(category: str) -> int:
    return int.from_bytes(hashlib.sha256(category.encode("utf-8")).digest()[:8], "big")


def char_intervals(category: str, fps: int, budget_s: float) -> list[int]:
    """Per-character delay in frames (>=1), jittered, squeezed to fit budget_s."""
    rng = random.Random(_seed(category))
    raw = [CHAR_BASE_S * (1 + rng.uniform(-CHAR_JITTER, CHAR_JITTER)) for _ in category]
    if category:
        # a beat before the first word lands, like a thumb finding the keyboard
        raw[0] *= 1.4
    total = sum(raw)
    cap = min(TYPING_CAP_S, budget_s)
    if total > cap:
        raw = [r * cap / total for r in raw]
    frames = [max(1, round(r * fps)) for r in raw]
    budget_frames = max(len(category), int(budget_s * fps))
    while sum(frames) > budget_frames and max(frames, default=1) > 1:
        i = frames.index(max(frames))
        frames[i] -= 1
    return frames


def build_timeline(
    category: str,
    verdict: str,
    *,
    fps: int = 30,
    pause_s: float = DEFAULT_PAUSE_S,
) -> Timeline:
    if not category:
        raise ValueError("category is empty")
    if not verdict:
        raise ValueError("verdict is empty")
    pause_s = clamp_pause(pause_s)

    lead = round(LEAD_S * fps)
    hold = round(HOLD_AFTER_TYPING_S * fps)
    pause = max(1, round(pause_s * fps))
    min_result = round(MIN_RESULT_S * fps)
    intervals = char_intervals(category, fps, TYPING_CAP_S)
    typing_frames = sum(intervals)

    natural = lead + typing_frames + hold + pause + min_result
    total = max(natural, round(MIN_SECONDS * fps))
    cap = round(MAX_SECONDS * fps)
    if total > cap:
        # the verdict hold is the only slack; the pause is the measured wait and stays
        slack = total - cap
        min_result = max(1, min_result - slack)
        total = lead + typing_frames + hold + pause + min_result
    if total > cap:
        raise ValueError(f"category too long to type within {MAX_SECONDS}s: {len(category)} chars")

    appear: list[int] = []
    t = lead
    for step in intervals:
        t += step
        appear.append(t)
    submit = appear[-1] + hold  # the completed word holds, then the pause begins

    states: list[State] = [State(0, appear[0], "typing", "", True)]
    for k in range(1, len(category) + 1):
        until = appear[k] if k < len(appear) else submit
        states.append(State(appear[k - 1], until, "typing", category[:k], True))
    verdict_at = submit + pause
    # Pause lock: the completed input and the caret. No spinner, dots, or status word.
    states.append(State(submit, verdict_at, "loading", category, True))
    states.append(State(verdict_at, total, "result", verdict, False))

    return Timeline(
        fps=fps,
        total_frames=total,
        states=tuple(s for s in states if s.end > s.start),
        submit_frame=submit,
        verdict_frame=verdict_at,
        pause_s=pause / fps,
    )

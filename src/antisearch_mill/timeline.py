"""Pure clip timeline: empty cursor -> typing -> submit (cursor alone) -> verdict.

Frame-indexed and deterministic: the typing jitter is seeded from the
category, so the same (category, verdict) always renders the same clip.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

MIN_SECONDS = 3.0  # LinkedIn and Instagram Reels reject clips under 3s
MAX_SECONDS = 4.0  # constitution: <=4s

LEAD_S = 0.30
CHAR_BASE_S = 0.065
CHAR_JITTER = 0.35
TYPING_CAP_S = 1.5
HOLD_AFTER_TYPING_S = 0.22
LOADING_S = 0.45
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

    @property
    def duration_s(self) -> float:
        return self.total_frames / self.fps


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


def build_timeline(category: str, verdict: str, *, fps: int = 30, seconds: float = 3.8) -> Timeline:
    if not category:
        raise ValueError("category is empty")
    if not verdict:
        raise ValueError("verdict is empty")
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ValueError(f"clip length must be within [{MIN_SECONDS}, {MAX_SECONDS}]s, got {seconds}")

    total = round(seconds * fps)
    lead = round(LEAD_S * fps)
    hold = round(HOLD_AFTER_TYPING_S * fps)
    loading = round(LOADING_S * fps)
    min_result = round(MIN_RESULT_S * fps)
    typing_budget_frames = total - lead - hold - loading - min_result
    if typing_budget_frames < len(category):
        raise ValueError(f"category too long to type within {seconds}s: {len(category)} chars")

    intervals = char_intervals(category, fps, typing_budget_frames / fps)

    appear: list[int] = []
    t = lead
    for step in intervals:
        t += step
        appear.append(t)
    submit = appear[-1] + hold

    states: list[State] = [State(0, appear[0], "typing", "", True)]
    for k in range(1, len(category) + 1):
        until = appear[k] if k < len(appear) else submit
        states.append(State(appear[k - 1], until, "typing", category[:k], True))
    verdict_at = submit + loading
    states.append(State(submit, verdict_at, "loading", "", True))
    states.append(State(verdict_at, total, "result", verdict, False))

    return Timeline(
        fps=fps,
        total_frames=total,
        states=tuple(s for s in states if s.end > s.start),
        submit_frame=submit,
        verdict_frame=verdict_at,
    )

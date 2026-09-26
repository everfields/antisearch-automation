"""Pure clip timeline.

`word` (default): empty cursor, typing, a still pause that keeps the typed
word, then the verdict.

`app` (`PUBLISHER_CLIP_STYLE=app`): a near-recording of the live screen.
The keyboard slides in, the word is typed, Enter clears the word and the
keyboard, the line moves once from 38% of the keyboard-shortened height to
38% of the full height, the pause is only the blinking caret, then the verdict.

Frame-indexed and deterministic: the typing jitter is seeded from the
category, so the same (category, verdict, pause, style) always renders the same clip.

Soul lock, 2026-09-25, approved by CoS, still in force for `word`: the thinking
pause is blank time with the typed input and a blinking caret only. No spinner,
no dots, no "thinking" text. This does not follow antisearch.ai. If the site adds
any of those, the `word` clip still does not. The site fetched that day hides
`.mirror` on submit and leaves `#cursor` blinking; the `word` clip keeps the
completed input up, because a blank caret for the whole wait does not read as
a question.

The word-stays lock is withdrawn for the `app` style (2026-09-26, Soul + Carlos).
On Enter the typed word vanishes with the keyboard, and the pause is only the
centered blinking caret. The pause length is still the measured oracle latency
and is not replaced with a fixed second.

Fixed wait (founder, 2026-09-26), `wait="fixed"`: the template clip. The
blinking-caret wait is WAIT_BLINKS whole caret blinks in every clip, whatever
the input, the verdict, or the real oracle latency. Only the typing and the
verdict may vary with length. This overrides the latency pause above, and only
for clips rendered with the fixed wait (phone frame or heartbeat audio).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import random
from collections.abc import Mapping
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)

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

# `app` style. Target <=4s when the pause is short. Hard cap 5s: trim typing
# speed first, then the pre-typing keyboard slide. Never trim the pause.
# If the pause alone still blows the cap, the clip runs long and that is logged.
APP_TARGET_S = 4.0
APP_HARD_CAP_S = 5.0
APP_HOLD_S = 0.50  # the finished word holds still at least this long before Enter
APP_MIN_RESULT_S = 1.50
APP_SLIDE_IN_S = 0.30  # keyboard in, one linear move; trimmable down to nothing
APP_SLIDE_OUT_S = 0.30  # Enter: keyboard out and the line's one linear move
# Keyboard body on the 640 CSS-px phone: four key rows, no suggestion bar, no emoji row.
APP_KEYBOARD_CSS_H = 182
APP_KEYBOARD_FRAC = APP_KEYBOARD_CSS_H / 640

DEFAULT_CLIP_STYLE = "word"
CLIP_STYLES = ("word", "app")

# The product caret: CSS `blink 1.05s steps(1)`, 51% on.
BLINK_PERIOD_S = 1.05
BLINK_ON_FRACTION = 0.51

# Three blinks, 3.15s. A little longer than the slowest recorded live verdict
# (3.0s), so the clip is never faster than the product. Two blinks (2.1s) reads
# as a glitch; four (4.2s) drags on short-form feeds. Three heartbeats count.
WAIT_BLINKS = 3
WAIT_S = WAIT_BLINKS * BLINK_PERIOD_S
WAITS = ("latency", "fixed")


def wait_frames(fps: int) -> int:
    """Frames of the fixed wait. Rounded up so the last blink's off phase is whole."""
    return math.ceil(round(WAIT_S * fps, 6))


@dataclass(frozen=True)
class State:
    start: int  # first frame, inclusive
    end: int  # last frame, exclusive
    kind: str  # "typing" | "dismiss" | "loading" | "result"
    text: str
    cursor: bool


@dataclass(frozen=True)
class KeySegment:
    """Linear keyboard visibility over [start, end). 0 is offscreen, 1 is fully in."""

    start: int
    end: int
    k0: float
    k1: float


@dataclass(frozen=True)
class Timeline:
    fps: int
    total_frames: int
    states: tuple[State, ...]
    submit_frame: int
    verdict_frame: int
    pause_s: float
    style: str = DEFAULT_CLIP_STYLE
    keyboard: tuple[KeySegment, ...] = ()
    exceeded_cap: bool = False
    fixed_wait: bool = False

    @property
    def duration_s(self) -> float:
        return self.total_frames / self.fps

    @property
    def typed(self) -> str:
        return next((s.text for s in reversed(self.states) if s.kind == "typing"), "")

    def keystroke_frames(self) -> list[int]:
        """The frame each typed character first appears on."""
        return [s.start for s in self.states if s.kind == "typing" and s.text]

    def segments(self) -> dict[str, int]:
        """Frames per part. `typing` runs to Enter and includes the slide-in and the hold."""
        loading = next(s for s in self.states if s.kind == "loading")
        return {
            "typing": self.submit_frame,
            "enter": loading.start - self.submit_frame,
            "wait": loading.end - loading.start,
            "verdict": self.total_frames - self.verdict_frame,
        }

    def keyboard_at(self, frame: int) -> float:
        """Visibility at one frame. Matches the renderer's linear expression."""
        for seg in self.keyboard:
            if seg.start <= frame < seg.end:
                return _segment_k(seg, frame)
        return 0.0


def _segment_k(seg: KeySegment, frame: int) -> float:
    span = seg.end - seg.start
    if span <= 1:
        return seg.k1
    return seg.k0 + (seg.k1 - seg.k0) * (frame - seg.start) / (span - 1)


def clip_style(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_STYLE`: `word` (default) or `app`. Blank means `word`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_STYLE") or "").strip().lower()
    if not raw:
        return DEFAULT_CLIP_STYLE
    if raw not in CLIP_STYLES:
        raise ValueError(f"PUBLISHER_CLIP_STYLE={raw!r}; use word or app")
    return raw


def clamp_pause(seconds: float) -> float:
    """Wall-clock oracle latency, held inside the visible-wait window."""
    return min(MAX_PAUSE_S, max(MIN_PAUSE_S, seconds))


def pause_from_latency_ms(latency_ms: int | None, *, recorded: bool = True) -> float:
    """Pause length for one honest run. Unrecorded latency uses the 2.0s note, not a guess from a neighbour."""
    if not recorded or latency_ms is None:
        return DEFAULT_PAUSE_S
    return clamp_pause(latency_ms / 1000.0)


def pause_for_style(
    latency_ms: int | None,
    *,
    recorded: bool = True,
    style: str = DEFAULT_CLIP_STYLE,
    explicit: float | None = None,
) -> float:
    """Pause seconds for a style. `word` clamps; `app` keeps the measured latency."""
    if explicit is not None:
        return explicit
    if style == "app":
        if not recorded or latency_ms is None:
            return DEFAULT_PAUSE_S
        return max(0.0, latency_ms / 1000.0)
    return pause_from_latency_ms(latency_ms, recorded=recorded)


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


def _human_char_frames(category: str, fps: int) -> list[int]:
    """Uncapped human keystrokes. The `app` hard cap trims these later if it must."""
    rng = random.Random(_seed(category))
    raw = [CHAR_BASE_S * (1 + rng.uniform(-CHAR_JITTER, CHAR_JITTER)) for _ in category]
    if category:
        raw[0] *= 1.4
    return [max(1, round(r * fps)) for r in raw]


def _word_timeline(category: str, verdict: str, *, fps: int, pause_s: float) -> Timeline:
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
        style="word",
    )


def _fit_app(slide_in: int, intervals: list[int], fixed: int, cap: int) -> tuple[int, list[int]]:
    """Trim typing frames first, then the keyboard slide-in, down to the hard cap."""
    intervals = list(intervals)
    while slide_in + sum(intervals) + fixed > cap and max(intervals, default=1) > 1:
        i = intervals.index(max(intervals))
        intervals[i] -= 1
    while slide_in + sum(intervals) + fixed > cap and slide_in > 0:
        slide_in -= 1
    return slide_in, intervals


def _app_timeline(category: str, verdict: str, *, fps: int, pause_s: float) -> Timeline:
    # The measured wait is sacred. Do not clamp it into the word-style window.
    pause = max(1, round(max(0.0, pause_s) * fps))
    hold = max(1, round(APP_HOLD_S * fps))
    slide_out = max(1, round(APP_SLIDE_OUT_S * fps))
    result = max(1, round(APP_MIN_RESULT_S * fps))
    slide_in = max(0, round(APP_SLIDE_IN_S * fps))
    intervals = _human_char_frames(category, fps)
    fixed = hold + slide_out + pause + result
    cap = round(APP_HARD_CAP_S * fps)
    slide_in, intervals = _fit_app(slide_in, intervals, fixed, cap)
    total = slide_in + sum(intervals) + fixed
    exceeded = total > cap
    if exceeded:
        logger.warning(
            "app clip for %r is %.3fs, over the %.1fs cap (target %.1fs), after trimming typing "
            "and the keyboard slide; the %.3fs oracle pause was not cut",
            category,
            total / fps,
            APP_HARD_CAP_S,
            APP_TARGET_S,
            pause / fps,
        )
    return _app_states(
        category, verdict, fps=fps, slide_in=slide_in, intervals=intervals, hold=hold,
        slide_out=slide_out, pause=pause, result=result, exceeded=exceeded,
    )


def _app_fixed_timeline(category: str, verdict: str, *, fps: int) -> Timeline:
    """The template: the wait is always `wait_frames`, so there is no cap to trim toward."""
    intervals = char_intervals(category, fps, TYPING_CAP_S)
    return _app_states(
        category, verdict, fps=fps,
        slide_in=max(0, round(APP_SLIDE_IN_S * fps)),
        intervals=intervals,
        hold=max(1, round(APP_HOLD_S * fps)),
        slide_out=max(1, round(APP_SLIDE_OUT_S * fps)),
        pause=wait_frames(fps),
        result=max(1, round(APP_MIN_RESULT_S * fps)),
        exceeded=False,
        fixed=True,
    )


def _app_states(
    category: str,
    verdict: str,
    *,
    fps: int,
    slide_in: int,
    intervals: list[int],
    hold: int,
    slide_out: int,
    pause: int,
    result: int,
    exceeded: bool,
    fixed: bool = False,
) -> Timeline:
    total = slide_in + sum(intervals) + hold + slide_out + pause + result
    appear: list[int] = []
    t = slide_in
    for step in intervals:
        t += step
        appear.append(t)
    submit = appear[-1] + hold  # full word holds, then Enter
    pause_at = submit + slide_out
    verdict_at = pause_at + pause

    states: list[State] = [State(0, appear[0], "typing", "", True)]
    for k in range(1, len(category) + 1):
        until = appear[k] if k < len(appear) else submit
        states.append(State(appear[k - 1], until, "typing", category[:k], True))
    # Enter: the word is gone. The keyboard and the line move during `dismiss`.
    # With the fixed wait the caret is also off here, so its first blink and the
    # first heartbeat land together on the first wait frame.
    states.append(State(submit, pause_at, "dismiss", "", not fixed))
    # Pause lock for `app`: the caret only. The typed word does not stay.
    states.append(State(pause_at, verdict_at, "loading", "", True))
    states.append(State(verdict_at, total, "result", verdict, False))

    if slide_in > 0:
        keyboard = (
            KeySegment(0, slide_in, 0.0, 1.0),
            KeySegment(slide_in, submit, 1.0, 1.0),
        )
    else:
        keyboard = (KeySegment(0, submit, 1.0, 1.0),)
    keyboard += (
        KeySegment(submit, pause_at, 1.0, 0.0),
        KeySegment(pause_at, total, 0.0, 0.0),
    )

    return Timeline(
        fps=fps,
        total_frames=total,
        states=tuple(s for s in states if s.end > s.start),
        submit_frame=submit,
        verdict_frame=verdict_at,
        pause_s=pause / fps,
        style="app",
        keyboard=keyboard,
        exceeded_cap=exceeded,
        fixed_wait=fixed,
    )


def build_timeline(
    category: str,
    verdict: str,
    *,
    fps: int = 30,
    pause_s: float = DEFAULT_PAUSE_S,
    style: str = DEFAULT_CLIP_STYLE,
    wait: str = "latency",
) -> Timeline:
    """`wait="fixed"` ignores `pause_s`: the wait is WAIT_BLINKS blinks in every clip."""
    if not category:
        raise ValueError("category is empty")
    if not verdict:
        raise ValueError("verdict is empty")
    if wait not in WAITS:
        raise ValueError(f"unknown wait {wait!r}; use latency or fixed")
    if style == "word":
        if wait == "fixed":
            tl = _word_timeline(category, verdict, fps=fps, pause_s=wait_frames(fps) / fps)
            return replace(tl, fixed_wait=True)
        return _word_timeline(category, verdict, fps=fps, pause_s=pause_s)
    if style == "app":
        if wait == "fixed":
            return _app_fixed_timeline(category, verdict, fps=fps)
        return _app_timeline(category, verdict, fps=fps, pause_s=pause_s)
    raise ValueError(f"unknown clip style {style!r}; use word or app")

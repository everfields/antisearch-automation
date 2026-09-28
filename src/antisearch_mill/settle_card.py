"""The settle-it card: big type, no phone frame, sized for a Reddit mobile comment thumbnail.

Reddit shows comment media at a fixed height (about 238 dp on a phone; measured 28 Sep), so a tall
9:16 frame becomes a strip about 110 dp wide and the words shrink with it. The card is square
by default and fills its width with type:
- typing: the question, typed with a solid caret, at the place it will stay;
- the thinking pause: the full question and the blinking caret (the product caret, 1.05 s);
- the verdict: the question stays above, dimmer, and the verdict appears below it in large type.
`antisearch.ai` sits small at the bottom. Word wrap, never mid-word. Font sizes are fitted per
card so the longest question (55 chars) and a long verdict both fit. Frames come from the same
deterministic timeline as before (settle.drop_timeline); no model is called.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .render import RenderError
from .timeline import BLINK_ON_FRACTION, BLINK_PERIOD_S, Timeline

BG = (10, 10, 10)
FG = (232, 228, 216)  # the site's --fg
DIM = (150, 147, 140)  # the question once the verdict is up
MARK = (92, 90, 86)  # the footer, dimmer than the text


@dataclass(frozen=True)
class CardSize:
    name: str
    width: int
    height: int


CARDS = {
    "1x1": CardSize("1x1", 1080, 1080),
    "4x5": CardSize("4x5", 1080, 1350),
    "9x16": CardSize("9x16", 1080, 1920),
}
DEFAULT_CARD = "1x1"


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _heavier(path: str) -> str:
    """Inter SemiBold next to Inter Regular if installed, else the same file (weight is a nicety)."""
    p = Path(path)
    for name in ("SemiBold", "Medium"):
        cand = p.with_name(p.name.replace("Regular", name))
        if cand != p and cand.is_file():
            return str(cand)
    return path


def _words(text: str) -> list[str]:
    """Words, with a dash kept on the word before it, so no line starts with a dash."""
    out: list[str] = []
    for w in text.split():
        if out and w in ("—", "–", "-"):
            out[-1] += f" {w}"
        else:
            out.append(w)
    return out


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[str]:
    lines, cur = [], ""
    for word in _words(text):
        cand = f"{cur} {word}" if cur else word
        if draw.textlength(cand, font=font) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def _balanced(draw, text: str, font, max_w: float) -> list[str]:
    """The greedy wrap's line count, with the narrowest width that keeps it (no lone short word)."""
    lines = _wrap(draw, text, font, max_w)
    if any(ln.endswith(("—", "–")) for ln in lines[:-1]):
        return lines  # already breaks at the dash, the phrase's own break
    lo, hi = 0.0, max_w
    for _ in range(14):
        mid = (lo + hi) / 2
        cand = _wrap(draw, text, font, mid)
        if len(cand) <= len(lines) and all(draw.textlength(ln, font=font) <= mid for ln in cand):
            hi = mid
        else:
            lo = mid
    return _wrap(draw, text, font, hi)


def _fit(draw, text: str, path: str, max_w: float, tops: tuple[int, ...], floor: int):
    """The largest size at which `text` wraps within max_w into n lines, n <= len(tops), with the
    size at most tops[n-1]: more lines must mean smaller type, so a short phrase doesn't
    become a stack of single words."""
    size = tops[0]
    while size > floor:
        font = _font(path, size)
        lines = _wrap(draw, text, font, max_w)
        n = len(lines)
        if n <= len(tops) and size <= tops[n - 1] and all(draw.textlength(ln, font=font) <= max_w for ln in lines):
            return font, _balanced(draw, text, font, max_w)
        size -= 2
    font = _font(path, floor)
    return font, _balanced(draw, text, font, max_w)


@dataclass
class Layout:
    card: CardSize
    q_font: ImageFont.FreeTypeFont
    q_lines: list[str]
    v_font: ImageFont.FreeTypeFont
    v_lines: list[str]
    q_top: int
    v_top: int
    q_line_h: int
    v_line_h: int
    mark_font: ImageFont.FreeTypeFont


def layout(question: str, verdict: str, *, font_path: str, card: CardSize) -> Layout:
    W, H = card.width, card.height
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_w = W * 0.86
    q_font, q_lines = _fit(probe, question, font_path, max_w, (round(W * 0.075),) * 3, round(W * 0.040))
    v_font, v_lines = _fit(probe, verdict, _heavier(font_path), max_w,
                           (round(W * 0.14), round(W * 0.13), round(W * 0.105)), round(W * 0.060))
    q_lh, v_lh = round(q_font.size * 1.25), round(v_font.size * 1.18)
    gap = round(W * 0.06)
    block = len(q_lines) * q_lh + gap + len(v_lines) * v_lh
    top = round(H * 0.47 - block / 2)
    return Layout(card, q_font, q_lines, v_font, v_lines, top, top + len(q_lines) * q_lh + gap, q_lh, v_lh,
                  _font(font_path, round(W * 0.032)))


def _draw_lines(d, lines: list[str], shown: int, font, top: int, line_h: int, width: int, fill) -> tuple[float, int]:
    """Draw the first `shown` characters of the laid-out lines (each line keeps its final centred x).
    Returns where the caret goes (x, line top)."""
    left, y, x_end, caret_top = 0, top, width / 2, top
    for ln in lines:
        full_w = d.textlength(ln, font=font)
        left = (width - full_w) / 2
        take = max(0, min(len(ln), shown))
        part = ln[:take]
        if part:
            d.text((left, y), part, font=font, fill=fill)
        x_end, caret_top = left + d.textlength(part, font=font), y
        shown -= len(ln) + 1  # the space the wrap consumed
        if shown < 0:
            break
        y += line_h
    return x_end, caret_top


def frame(lay: Layout, timeline: Timeline, i: int) -> Image.Image:
    W, H = lay.card.width, lay.card.height
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    state = next(s for s in timeline.states if s.start <= i < s.end) if i < timeline.total_frames else timeline.states[-1]
    if state.kind == "result":
        _draw_lines(d, lay.q_lines, 10 ** 6, lay.q_font, lay.q_top, lay.q_line_h, W, DIM)
        _draw_lines(d, lay.v_lines, 10 ** 6, lay.v_font, lay.v_top, lay.v_line_h, W, FG)
    else:
        typed = len(state.text) if state.kind == "typing" else 10 ** 6
        x, y = _draw_lines(d, lay.q_lines, typed, lay.q_font, lay.q_top, lay.q_line_h, W, FG)
        on = True
        if state.kind == "loading":
            t = (i - state.start) / timeline.fps
            on = (t % BLINK_PERIOD_S) < BLINK_PERIOD_S * BLINK_ON_FRACTION
        if state.cursor and on:
            em = lay.q_font.size
            cw = max(2, round(0.55 * em * 0.6))
            gap = round(em * 0.06) if typed else 0
            d.rectangle([x + gap, y + round(em * 0.10), x + gap + cw, y + round(em * 1.12)], fill=FG)
    mark = "antisearch.ai"
    mw = d.textlength(mark, font=lay.mark_font)
    d.text(((W - mw) / 2, H - round(H * 0.045) - lay.mark_font.size), mark, font=lay.mark_font, fill=MARK)
    return img


def render_master(question: str, verdict: str, timeline: Timeline, out: Path, *, font_path: str,
                  card: CardSize) -> Image.Image:
    """Every frame through ffmpeg into a lossless-ish H.264 master; returns the last frame (the PNG)."""
    lay = layout(question, verdict, font_path=font_path, card=card)
    W, H = card.width, card.height
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(timeline.fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14",
         "-pix_fmt", "yuv420p", "-an", str(out)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last = None
    try:
        for i in range(timeline.total_frames):
            last = frame(lay, timeline, i)
            enc.stdin.write(last.tobytes())
    finally:
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
    if code != 0:
        raise RenderError(f"ffmpeg (card master) failed:\n{err[-1200:]}")
    return last

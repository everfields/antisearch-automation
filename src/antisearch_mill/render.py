"""Synthetic monolith renderer: recreates the antisearch.ai screen in ffmpeg.

Geometry is the product CSS evaluated on a 360x640 CSS-px phone viewport and
scaled 3x to 1080x1920 (exact 9:16):

  body       bg #0A0A0A, fg #E8E4D8, 18px system sans, line-height 1.5, padding 20px
  .terminal  centered at 38% of viewport height, width 100% - 40px, text-align center
  .cursor    inline-block 0.6ch x 1.05em, translateY(0.18em), blink 1.05s steps(1), 51% on
  .footer    "antisearch.ai", 11px, fg at 30% alpha, 14px from the bottom

`word` (default) draws that screen with the typed word held through the pause.
`app` adds a plain generic dark keyboard (near #0A0A0A, no brand, no suggestion
bar, no emoji/mic row, no key popups, no status bar) and, on Enter, clears the
word. The keyboard slides out while the line moves once, linearly, from 38% of
the keyboard-shortened height to 38% of the full height (`repositionTerminal`).

No captions, no branding beyond the product's own footer: caption work is GTM's.
Audio is the silent track unless a procedural bed is asked for (see `audio.py`).

`phone` (`PUBLISHER_CLIP_FRAME=phone`) lays the `app` screen out at the phone
screen's own pixel size and composites it under a code-drawn mockup (`phone.py`).
The output is still the full 1080x1920 frame.

Soul lock, 2026-09-25, still in force for `word`: the pause draws the typed
input and a blinking caret only. No spinner, no dots, no "thinking" text.
The word-stays lock is withdrawn for the `app` style (2026-09-26, Soul + Carlos):
the pause is the centered caret alone.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .fonts import FontMetrics, metrics
from .phone import PhoneSpec, draw_phone, geometry
from .timeline import APP_KEYBOARD_CSS_H, BLINK_ON_FRACTION, BLINK_PERIOD_S, Timeline

BG = "0x0A0A0A"
FG = "0xE8E4D8"
DIM = "0xE8E4D8@0.30"

CSS_VIEWPORT_W = 360


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    width: int = 1080
    height: int = 1920
    fps: int = 30

    @property
    def scale(self) -> float:
        return self.width / CSS_VIEWPORT_W

    def px(self, css: float) -> int:
        return round(css * self.scale)

    @property
    def font_px(self) -> int:
        return self.px(18)

    @property
    def line_h(self) -> float:
        return 1.5 * self.font_px

    @property
    def max_text_w(self) -> int:
        return self.width - 2 * self.px(20)

    @property
    def center_y(self) -> float:
        return 0.38 * self.height

    @property
    def footer_px(self) -> int:
        return self.px(11)

    @property
    def footer_bottom(self) -> int:
        return self.px(14)


@dataclass(frozen=True)
class Placed:
    text: str
    x: int
    baseline: int


@dataclass(frozen=True)
class CursorBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Frame:
    lines: tuple[Placed, ...]
    cursor: CursorBox | None


def wrap_chars(text: str, fm: FontMetrics, max_w: float) -> list[str]:
    """`white-space: pre-wrap; word-break: break-all` for the typed mirror."""
    lines, cur = [], ""
    for ch in text:
        if cur and fm.width(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


def wrap_words(text: str, fm: FontMetrics, max_w: float) -> list[str]:
    """Normal word wrapping for the verdict; overlong single words break by char."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        candidate = f"{cur} {word}" if cur else word
        if fm.width(candidate) <= max_w:
            cur = candidate
            continue
        if cur:
            lines.append(cur)
        if fm.width(word) <= max_w:
            cur = word
        else:
            pieces = wrap_chars(word, fm, max_w)
            lines.extend(pieces[:-1])
            cur = pieces[-1]
    lines.append(cur)
    return lines


def keyboard_height(lay: Layout) -> int:
    """Output-pixel height of the `app` keyboard when it is fully in.

    182 CSS px at the layout's scale. On the 360x640 viewport this is the same
    546 px as before; on the taller phone screen the keys keep their size.
    """
    return lay.px(APP_KEYBOARD_CSS_H)


def terminal_center_y(height: float, keyboard_h: float, k: float) -> float:
    """38% of the height still visible above a keyboard that is `k` of the way in."""
    return 0.38 * (height - k * keyboard_h)


def layout_frame(
    text: str,
    kind: str,
    cursor: bool,
    fm: FontMetrics,
    lay: Layout,
    center_y: float | None = None,
) -> Frame:
    cursor_w = 0.6 * fm.ch
    if kind == "result":
        rows = wrap_words(text, fm, lay.max_text_w)
    else:
        rows = wrap_chars(text, fm, lay.max_text_w) if text else [""]
    cursor_row_extra = cursor and fm.width(rows[-1]) + cursor_w > lay.max_text_w
    n_rows = len(rows) + (1 if cursor_row_extra else 0)

    cy = lay.center_y if center_y is None else center_y
    top = cy - n_rows * lay.line_h / 2
    half_leading = (lay.line_h - (fm.ascent + fm.descent)) / 2

    def baseline(i: int) -> float:
        return top + i * lay.line_h + half_leading + fm.ascent

    placed: list[Placed] = []
    cursor_box: CursorBox | None = None
    for i, row in enumerate(rows):
        row_w = fm.width(row)
        is_last = i == len(rows) - 1
        if cursor and is_last and not cursor_row_extra:
            row_w += cursor_w
        x = (lay.width - row_w) / 2
        if row:
            placed.append(Placed(row, round(x), round(baseline(i))))
        if cursor and is_last and not cursor_row_extra:
            cursor_box = _cursor_box(x + fm.width(row), baseline(i), cursor_w, fm)
    if cursor_row_extra:
        cursor_box = _cursor_box((lay.width - cursor_w) / 2, baseline(len(rows)), cursor_w, fm)
    return Frame(tuple(placed), cursor_box)


def _cursor_box(x: float, baseline: float, w: float, fm: FontMetrics) -> CursorBox:
    em = fm.size
    top = baseline - 1.05 * em + 0.18 * em
    return CursorBox(round(x), round(top), max(1, round(w)), round(1.05 * em))


def footer_placement(lay: Layout, fm: FontMetrics) -> Placed:
    text = "antisearch.ai"
    line_h = 1.5 * fm.size
    line_top = lay.height - lay.footer_bottom - line_h
    base = line_top + (line_h - (fm.ascent + fm.descent)) / 2 + fm.ascent
    return Placed(text, round((lay.width - fm.width(text)) / 2), round(base))


def _q(value: str) -> str:
    """Quote a filter option value for the filtergraph parser."""
    return "'" + value.replace("\\", "\\\\").replace("'", "'\\''") + "'"


def _ranges_expr(ranges: list[tuple[int, int]]) -> str:
    return "+".join(f"between(n,{a},{b - 1})" for a, b in ranges)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# Flat system-dark keys. The panel itself is the app background, so only the keys read.
_KEY = (58, 58, 60, 255)
_KEY_SPECIAL = (36, 36, 38, 255)
_KEY_LABEL = (236, 236, 236, 255)


def _key_label(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.FreeTypeFont) -> None:
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (x0 + (x1 - x0 - tw) / 2 - bbox[0], y0 + (y1 - y0 - th) / 2 - bbox[1]),
        text,
        font=font,
        fill=_KEY_LABEL,
    )


def _draw_shift(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = (x1 - x0) * 0.16, (y1 - y0) * 0.22
    draw.polygon(
        [
            (cx, cy - h),
            (cx + w, cy + h * 0.05),
            (cx + w * 0.42, cy + h * 0.05),
            (cx + w * 0.42, cy + h),
            (cx - w * 0.42, cy + h),
            (cx - w * 0.42, cy + h * 0.05),
            (cx - w, cy + h * 0.05),
        ],
        fill=_KEY_LABEL,
    )


def _draw_backspace(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = (x1 - x0) * 0.20, (y1 - y0) * 0.16
    draw.polygon(
        [(cx - w, cy), (cx - w * 0.25, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w * 0.25, cy + h)],
        fill=_KEY_LABEL,
    )


def draw_keyboard(path: Path, lay: Layout, font_path: str) -> None:
    """A generic dark QWERTY. No brand, suggestion bar, emoji/mic row, or status chrome."""
    scale = lay.scale
    w, h = lay.width, keyboard_height(lay)
    img = Image.new("RGBA", (w, h), (0x0A, 0x0A, 0x0A, 255))
    draw = ImageDraw.Draw(img)
    pad_x = round(3 * scale)
    gap_x = round(5 * scale)
    gap_y = round(8 * scale)
    key_h = round(36 * scale)
    pad_top = round(6 * scale)
    radius = round(5 * scale)
    inner = w - 2 * pad_x
    key_w = (inner - 9 * gap_x) // 10
    row_used = 10 * key_w + 9 * gap_x
    x_row1 = pad_x + (inner - row_used) // 2
    letter_font = ImageFont.truetype(font_path, round(20 * scale))
    small_font = ImageFont.truetype(font_path, round(13 * scale))

    def key(x: int, y: int, kw: int, special: bool = False) -> tuple[int, int, int, int]:
        box = (x, y, x + kw, y + key_h)
        draw.rounded_rectangle(box, radius=radius, fill=_KEY_SPECIAL if special else _KEY)
        return box

    def row_y(i: int) -> int:
        return pad_top + i * (key_h + gap_y)

    y = row_y(0)
    for i, ch in enumerate("qwertyuiop"):
        box = key(x_row1 + i * (key_w + gap_x), y, key_w)
        _key_label(draw, box, ch, letter_font)

    y = row_y(1)
    row2 = 9 * key_w + 8 * gap_x
    x = (w - row2) // 2
    for i, ch in enumerate("asdfghjkl"):
        box = key(x + i * (key_w + gap_x), y, key_w)
        _key_label(draw, box, ch, letter_font)

    y = row_y(2)
    special_w = round(key_w * 1.45)
    letters = "zxcvbnm"
    row3 = 2 * special_w + len(letters) * key_w + (len(letters) + 1) * gap_x
    x = (w - row3) // 2
    shift = key(x, y, special_w, special=True)
    _draw_shift(draw, shift)
    x += special_w + gap_x
    for ch in letters:
        box = key(x, y, key_w)
        _key_label(draw, box, ch, letter_font)
        x += key_w + gap_x
    back = key(x, y, special_w, special=True)
    _draw_backspace(draw, back)

    y = row_y(3)
    num_w = round(key_w * 1.55)
    ret_w = round(key_w * 2.15)
    space_w = inner - num_w - ret_w - 2 * gap_x
    x = pad_x
    num = key(x, y, num_w, special=True)
    _key_label(draw, num, "123", small_font)
    x += num_w + gap_x
    key(x, y, space_w, special=True)
    x += space_w + gap_x
    ret = key(x, y, ret_w, special=True)
    _key_label(draw, ret, "return", small_font)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _k_expr(timeline: Timeline) -> str:
    """ffmpeg expression for keyboard visibility. Same arithmetic as Timeline.keyboard_at."""
    expr = "0"
    for seg in reversed(timeline.keyboard):
        if seg.end <= seg.start:
            continue
        if seg.end - seg.start <= 1:
            piece = f"{seg.k1:.6f}"
        else:
            denom = seg.end - seg.start - 1
            piece = f"{seg.k0:.6f}+({seg.k1 - seg.k0:.6f})*(n-{seg.start})/{denom}"
        expr = f"if(between(n,{seg.start},{seg.end - 1}),{piece},{expr})"
    return expr


def _app_filtergraph(timeline: Timeline, font_path: str, lay: Layout, workdir: Path) -> str:
    """`app` screen. Input 1 is the keyboard still; input 0 stays the silent audio."""
    fm = metrics(font_path, lay.font_px)
    fm_footer = metrics(font_path, lay.footer_px)
    kb_h = keyboard_height(lay)
    k_expr = _k_expr(timeline)

    text_ranges: dict[Placed, list[tuple[int, int]]] = {}
    cursor_ranges: dict[CursorBox, list[tuple[int, int]]] = {}
    moving: list[tuple[int, int]] = []
    for st in timeline.states:
        k0 = timeline.keyboard_at(st.start)
        k1 = timeline.keyboard_at(st.end - 1)
        if abs(k0 - k1) > 1e-4:
            if st.cursor:
                moving.append((st.start, st.end))
            continue
        frame = layout_frame(
            st.text, st.kind, st.cursor, fm, lay,
            center_y=terminal_center_y(lay.height, kb_h, k0),
        )
        for p in frame.lines:
            text_ranges.setdefault(p, []).append((st.start, st.end))
        if frame.cursor:
            cursor_ranges.setdefault(frame.cursor, []).append((st.start, st.end))

    font = _q(font_path)
    filters: list[str] = []

    def drawtext(p: Placed, size: int, color: str, enable: str | None, idx: int) -> str:
        tf = workdir / f"t{idx:04d}.txt"
        tf.write_text(p.text, encoding="utf-8")
        opts = [
            f"fontfile={font}",
            f"textfile={_q(str(tf))}",
            "expansion=none",
            f"fontsize={size}",
            f"fontcolor={color}",
            f"x={p.x}",
            f"y={p.baseline}",
            "y_align=baseline",
        ]
        if enable:
            opts.append(f"enable={_q(enable)}")
        return "drawtext=" + ":".join(opts)

    # Footer sits under the keyboard, so the slide covers it the way the phone does.
    filters.append(drawtext(footer_placement(lay, fm_footer), lay.footer_px, DIM, None, 0))
    y_kb = f"H-overlay_h*({k_expr})"
    head = (
        f"[1:v]format=rgba[kb];"
        f"color=c={BG}:s={lay.width}x{lay.height}:r={timeline.fps}:d={timeline.total_frames / timeline.fps:.4f},"
        f"format=yuv420p,{filters[0]}[bg];"
        f"[bg][kb]overlay=x=0:y={_q(y_kb)}:format=auto:eof_action=repeat:eval=frame"
    )
    filters = []
    for idx, (p, ranges) in enumerate(text_ranges.items(), start=1):
        filters.append(drawtext(p, lay.font_px, FG, _ranges_expr(_merge(ranges)), idx))

    # Blink restarts on each keystroke and when the pause begins, same caret as `word`.
    # `app` withdraws the word-stays lock (2026-09-26): once Enter lands, this caret
    # is the only thing on the line until the verdict. Period is the app CSS, 1.05s.
    period_f = BLINK_PERIOD_S * timeline.fps
    on_f = period_f * BLINK_ON_FRACTION

    def blink(ranges: list[tuple[int, int]]) -> str:
        return "+".join(
            f"between(n,{a},{b - 1})*lt(mod(n-{a},{period_f:g}),{on_f:g})" for a, b in sorted(ranges)
        )

    for box, ranges in cursor_ranges.items():
        filters.append(
            f"drawbox=x={box.x}:y={box.y}:w={box.w}:h={box.h}:color={FG}:t=fill:enable={_q(blink(ranges))}"
        )
    # drawbox's y expression has no frame number, so each frame of a slide is its own box.
    # The caret stays on through a 0.30s slide: the on-phase of the 1.05s blink is longer.
    for a, b in moving:
        for n in range(a, b):
            if (n - a) % period_f >= on_f:
                continue
            cy = terminal_center_y(lay.height, kb_h, timeline.keyboard_at(n))
            box = layout_frame("", "loading", True, fm, lay, center_y=cy).cursor
            assert box is not None
            filters.append(
                f"drawbox=x={box.x}:y={box.y}:w={box.w}:h={box.h}:color={FG}:t=fill:enable={_q(f'eq(n,{n})')}"
            )

    tail = ",".join(filters)
    body = f",{tail}" if tail else ""
    return f"{head}{body},format=yuv420p[v]"


def screen_layout(phone: PhoneSpec, canvas: Layout) -> Layout:
    """The app screen inside the phone, laid out at its own pixel size (no rescale blur)."""
    geom = geometry(phone, canvas.width, canvas.height)
    return Layout(width=geom.screen_w, height=geom.screen_h, fps=canvas.fps)


def phone_input_index(timeline: Timeline) -> int:
    """ffmpeg input of the phone overlay: after the audio, and after the keyboard for `app`."""
    return 2 if timeline.style == "app" else 1


def build_filtergraph(
    timeline: Timeline,
    font_path: str,
    lay: Layout,
    workdir: Path,
    phone: PhoneSpec | None = None,
) -> str:
    if phone is not None:
        geom = geometry(phone, lay.width, lay.height)
        inner = build_filtergraph(timeline, font_path, screen_layout(phone, lay), workdir)
        inner = inner[: -len("[v]")] + "[scr]"
        idx = phone_input_index(timeline)
        # Composite in planar RGB so the rounded screen edge blends without chroma fringes.
        return (
            f"{inner};"
            f"[scr]pad={lay.width}:{lay.height}:{geom.screen_x}:{geom.screen_y}:color=black,format=gbrp[base];"
            f"[{idx}:v]format=gbrap[ph];"
            f"[base][ph]overlay=x=0:y=0:format=gbrp:eof_action=repeat,format=yuv420p[v]"
        )
    if timeline.style == "app":
        return _app_filtergraph(timeline, font_path, lay, workdir)
    fm = metrics(font_path, lay.font_px)
    fm_footer = metrics(font_path, lay.footer_px)

    text_ranges: dict[Placed, list[tuple[int, int]]] = {}
    cursor_ranges: dict[CursorBox, list[tuple[int, int]]] = {}
    for st in timeline.states:
        frame = layout_frame(st.text, st.kind, st.cursor, fm, lay)
        for p in frame.lines:
            text_ranges.setdefault(p, []).append((st.start, st.end))
        if frame.cursor:
            cursor_ranges.setdefault(frame.cursor, []).append((st.start, st.end))

    font = _q(font_path)
    filters: list[str] = []

    def drawtext(p: Placed, size: int, color: str, enable: str | None, idx: int) -> str:
        tf = workdir / f"t{idx:04d}.txt"
        tf.write_text(p.text, encoding="utf-8")
        opts = [
            f"fontfile={font}",
            f"textfile={_q(str(tf))}",
            "expansion=none",
            f"fontsize={size}",
            f"fontcolor={color}",
            f"x={p.x}",
            f"y={p.baseline}",
            "y_align=baseline",
        ]
        if enable:
            opts.append(f"enable={_q(enable)}")
        return "drawtext=" + ":".join(opts)

    for idx, (p, ranges) in enumerate(text_ranges.items()):
        filters.append(drawtext(p, lay.font_px, FG, _ranges_expr(_merge(ranges)), idx))

    # Blink phase restarts at every keystroke and when the pause begins (native caret
    # behaviour). The product's free-running CSS blink is 1.05s, 51% on. During the
    # pause the completed input stays, so a blink-off frame is never an empty screen.
    # Soul lock, still in force for `word`: that pause draws the input and this caret
    # only. No spinner, dots, or "thinking" text, even if the live site adds them.
    # The word-stays lock is withdrawn for the `app` style (2026-09-26, Soul + Carlos).
    # Integer frame arithmetic: a rounded float anchor can make t-anchor slightly
    # negative, and ffmpeg's floor-based mod() then wraps it into the off phase.
    period_f = BLINK_PERIOD_S * timeline.fps
    on_f = period_f * BLINK_ON_FRACTION
    for box, ranges in cursor_ranges.items():
        enable = "+".join(
            f"between(n,{a},{b - 1})*lt(mod(n-{a},{period_f:g}),{on_f:g})" for a, b in sorted(ranges)
        )
        filters.append(
            f"drawbox=x={box.x}:y={box.y}:w={box.w}:h={box.h}:color={FG}:t=fill:enable={_q(enable)}"
        )

    filters.append(drawtext(footer_placement(lay, fm_footer), lay.footer_px, DIM, None, len(text_ranges)))

    dur = timeline.total_frames / timeline.fps
    src = f"color=c={BG}:s={lay.width}x{lay.height}:r={timeline.fps}:d={dur:.4f}"
    return f"{src},format=yuv420p," + ",".join(filters) + ",format=yuv420p[v]"


@dataclass(frozen=True)
class ClipInfo:
    duration_s: float
    width: int
    height: int
    fps: float
    vcodec: str
    pix_fmt: str
    acodec: str
    size_bytes: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RenderError(f"{tool} not found on PATH (apt install ffmpeg)")


def probe(path: Path) -> ClipInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise RenderError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RenderError(f"{path} has no video stream")
    num, _, den = video.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return ClipInfo(
        duration_s=round(float(data["format"].get("duration", 0.0)), 3),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=round(fps, 3),
        vcodec=video.get("codec_name", ""),
        pix_fmt=video.get("pix_fmt", ""),
        acodec=audio.get("codec_name", "") if audio else "",
        size_bytes=int(data["format"].get("size", 0)),
    )


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RenderError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def render_clip(
    timeline: Timeline,
    out_path: Path,
    *,
    font_path: str,
    layout: Layout | None = None,
    metadata: dict[str, str] | None = None,
    keep_graph: Path | None = None,
    pulse: str | None = None,
    heartbeat: bool = False,
    bed: bool = False,
    phone: PhoneSpec | None = None,
) -> ClipInfo:
    """`pulse` is a pulse variant; `heartbeat` (with an optional `bed`) replaces it.

    `phone` draws the screen inside the phone mockup. The output stays the
    layout's full 9:16 frame either way.
    """
    require_tools()
    lay = layout or Layout(fps=timeline.fps)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".partial.mp4")
    dur = timeline.total_frames / timeline.fps
    with tempfile.TemporaryDirectory(prefix="mill-") as td:
        work = Path(td)
        graph = build_filtergraph(timeline, font_path, lay, work, phone=phone)
        if keep_graph:
            keep_graph.parent.mkdir(parents=True, exist_ok=True)
            keep_graph.write_text(graph, encoding="utf-8")
        still = ["-loop", "1", "-framerate", str(timeline.fps), "-t", f"{dur:.4f}", "-i"]
        extra: list[str] = []
        if timeline.style == "app":
            kb = work / "keyboard.png"
            draw_keyboard(kb, screen_layout(phone, lay) if phone else lay, font_path)
            # Bounded still: overlay repeats the last frame, and -t stops the encode.
            extra += [*still, str(kb)]
        if phone is not None:
            frame_png = work / "phone.png"
            draw_phone(frame_png, phone, geometry(phone, lay.width, lay.height))
            extra += [*still, str(frame_png)]
        if heartbeat:
            from .audio import write_heartbeat_wav
            wav = work / "heartbeat.wav"
            write_heartbeat_wav(timeline, wav, bed=bed, work=work)
            audio_in = ["-i", str(wav)]
            audio_codec = ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"]
        elif pulse:
            from .audio import write_pulse_wav
            wav = work / "pulse.wav"
            write_pulse_wav(timeline, pulse, wav, work=work)
            # Input 0 stays the audio, so the app keyboard remains input 1.
            audio_in = ["-i", str(wav)]
            audio_codec = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
        else:
            audio_in = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            audio_codec = ["-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2"]
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *audio_in,
            *extra,
            "-filter_complex", graph,
            "-map", "[v]", "-map", "0:a",
            "-t", f"{dur:.4f}",
            "-r", str(timeline.fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1",
            "-g", str(timeline.fps), "-bf", "2",
            *audio_codec,
            "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart",
        ]
        for k, v in (metadata or {}).items():
            cmd += ["-metadata", f"{k}={v}"]
        cmd.append(str(tmp_out))
        _run(cmd)
    tmp_out.replace(out_path)
    return probe(out_path)


def extract_poster(clip: Path, poster: Path, at_s: float) -> None:
    poster.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, at_s):.3f}", "-i", str(clip), "-frames:v", "1", "-update", "1", str(poster),
    ])
    if not poster.is_file():
        raise RenderError(f"no frame at {at_s:.3f}s in {clip}; poster not written")


def contact_sheet(clip: Path, out_png: Path, *, every_s: float = 0.4, cols: int = 5, rows: int = 2) -> None:
    """Proof image: a grid of frames sampled across the clip."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip),
        "-vf", f"fps=1/{every_s},scale=270:-2,tile={cols}x{rows}:padding=6:color=0x333333",
        "-frames:v", "1", "-update", "1", str(out_png),
    ])


def render_gif(src: Path, dst: Path, *, width: int = 600, max_bytes: int = 3 * 1024 * 1024) -> int:
    """Looping GIF of a rendered clip. Width is `width` px; height keeps the source aspect.

    Palette is generated from the frames, which are only #0A0A0A and #E8E4D8.
    fps drops until the file is at most 3 MB.
    """
    require_tools()
    dst.parent.mkdir(parents=True, exist_ok=True)
    last_size = 0
    for fps in (12, 10, 8, 6, 4):
        _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-vf", (
                f"fps={fps},scale={width}:-2:flags=lanczos,"
                "split[s0][s1];[s0]palettegen=max_colors=16:stats_mode=diff[p];"
                "[s1][p]paletteuse=dither=none"
            ),
            "-loop", "0", str(dst),
        ])
        last_size = dst.stat().st_size
        if last_size <= max_bytes:
            return last_size
    raise RenderError(f"gif {dst} is {last_size} bytes, over the {max_bytes} byte cap")


def render_loop_mp4(src: Path, dst: Path, *, width: int = 600) -> ClipInfo:
    """Silent looping-source mp4 at `width` px wide, same aspect as `src`. Players loop the file."""
    require_tools()
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-vf", f"scale={width}:-2:flags=lanczos,format=yuv420p",
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-metadata", "comment=loop=1;capture=synthetic-oracle",
        str(dst),
    ])
    return probe(dst)


def derive_variant(src: Path, dst: Path, width: int, height: int) -> ClipInfo:
    """Platform-safe downscale of the master (same timing, same audio)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-c:a", "copy", "-movflags", "+faststart", "-map_metadata", "0", str(dst),
    ])
    return probe(dst)

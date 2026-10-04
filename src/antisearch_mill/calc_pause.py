"""Calc pause: one accelerating formula line during the oracle wait."""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .fonts import _font, metrics
from .render import Layout, footer_placement

CALC_PAUSE = "calc"
DEFAULT_PAUSE = "blink"
ALTERNATE_PAUSE = "alternate"
PAUSE_MODES = (DEFAULT_PAUSE, CALC_PAUSE, ALTERNATE_PAUSE)
REEL_NETWORKS = frozenset({"instagram", "tiktok"})
IG_NETWORK = "instagram"
TIKTOK_NETWORK = "tiktok"
CALC_PRE_HOLD_S = 0.8
CALC_POST_HOLD_S = 0.25
# Kill switch (2026-10-04 hotfix): True makes produce render blink instead of calc everywhere.
# Off again since calc renders input -> formula -> verdict -> outro on one row (frame-verified).
CALC_KILL_SWITCH = False


def calc_hold_frames(fps: int) -> tuple[int, int]:
    """Pre- and post-formula hold frames (input+cursor, then empty+cursor)."""
    return max(1, round(CALC_PRE_HOLD_S * fps)), max(1, round(CALC_POST_HOLD_S * fps))

BG_RGB = (10, 10, 10)
FG_RGB = (232, 228, 216)
DIM_RGB = (77, 75, 72)  # FG at 30% over BG, as the ffmpeg footer (0xE8E4D8@0.30)

MATH_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansMath-Regular.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

_DIGITS = "0123456789"
_SUBS = "ᵢⱼₙₖₘₜₚₗₛ₀₁₂₃₄₅₆₇₈₉"
_VARS = "xyzabctuvw"
_SUPS = "⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ⁻⁺"
_MAIN_ASCII = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 =+(),.[]/|")

# Complete formulas: Unicode superscripts/subscripts only, no raw LaTeX.
FORMULAS: tuple[str, ...] = (
    "∫₀¹ x² dx = 1/3",
    "∂f/∂x = limₕ→₀ (f(x+h) − f(x))/h",
    "∑ᵢ₌₁ⁿ i = n(n+1)/2",
    "E[X] = ∑ᵢ xᵢ P(xᵢ)",
    "Var(X) = E[X²] − (E[X])²",
    "softmax(zᵢ) = exp(zᵢ) / ∑ⱼ exp(zⱼ)",
    "∇f = (∂f/∂x₁, …, ∂f/∂xₙ)",
    "det([[a,b],[c,d]]) = ad − bc",
    "Av = λv",
    "f(x) = f(a) + f'(a)(x−a) + f''(a)(x−a)²/2",
    "θₜ₊₁ = θₜ − η∇L(θₜ)",
    "∂L/∂w = (1/m) ∑ᵢ ∇Lᵢ",
    "σ² = (1/n) ∑ᵢ (xᵢ − μ)²",
    "(AB)ᵢⱼ = ∑ₖ AᵢₖBₖⱼ",
    "‖x‖₂ = √(∑ᵢ xᵢ²)",
    "P(A∩B) = P(A)P(B|A)",
    "∫₋∞…∞ e⁻ˣ² dx = √π",
    "Cov(X,Y) = E[XY] − E[X]E[Y]",
    "P(A|B) = P(B|A)P(A) / P(B)",
    "∂²f/∂x∂y = ∂²f/∂y∂x",
    "∫ₐᵇ f'(x)dx = f(b) − f(a)",
    "∑ₖ₌₀…∞ a·rᵏ = a/(1−r)",
    "sin²θ + cos²θ = 1",
    "∇·(∇φ) = ∇²φ",
    "β = (X⊤X)⁻¹X⊤y",
    "‖A‖₂ = √(∑ᵢⱼ Aᵢⱼ²)",
    "KL(p‖q) = ∑ᵢ pᵢ log(pᵢ/qᵢ)",
    "det(A) = ∏ᵢ λᵢ",
    "∑ᵢ₌₁ⁿ 1/i² = π²/6",
    "∂L/∂z = ŷ − y",
    "A = UΣV⊤",
    "Hᵢⱼ = ∂²L / ∂θᵢ ∂θⱼ",
    "⟨a,b⟩ = ∑ᵢ aᵢbᵢ = ‖a‖‖b‖cos θ",
    "∑ᵢ₌₁ⁿ aᵢbᵢ − (∑ᵢ aᵢ)(∑ᵢ bᵢ)/n",
    "∂/∂xᵢ (½ x⊤Ax) = Ax",
    "∫ sin(x)cos(x)dx = sin²(x)/2 + C",
    "z = (x−μ)/σ",
    "r = ∑ᵢ(xᵢ−x̄)(yᵢ−ȳ) / √(∑ᵢ(xᵢ−x̄)² ∑ᵢ(yᵢ−ȳ)²)",
    "log(ab) = log a + log b",
    "dy/dx + P(x)y = Q(x)",
    "E[aX+b] = aE[X] + b",
    "∑ᵢⱼ Aᵢⱼ = tr(A)",
    "x⊤Ax = ∑ᵢⱼ xᵢAᵢⱼxⱼ",
    "∇θ J(θ) = ∂J/∂θ",
)


def clip_pause(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_PAUSE") or "").strip().lower()
    if not raw:
        return DEFAULT_PAUSE
    if raw not in PAUSE_MODES:
        raise ValueError(f"PUBLISHER_CLIP_PAUSE={raw!r}; use blink, calc, or alternate")
    return raw


def pause_from_clip_sidecar(clip_id: str, clips_dir: Path | None) -> str:
    """Whether a posted clip used calc, from its sidecar. Missing sidecar means blink."""
    if not clip_id or not clips_dir:
        return DEFAULT_PAUSE
    path = clips_dir / f"{clip_id}.json"
    if not path.is_file():
        return DEFAULT_PAUSE
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("timeline", {}).get("pause") == CALC_PAUSE:
        return CALC_PAUSE
    return DEFAULT_PAUSE


def last_single_clip_pause(post_log, clips_dir: Path | None = None) -> str | None:
    """Pause style of the latest published TikTok single-verdict clip, or None with no such post.

    The post log on `publisher-state` is the memory that survives runs (CI clips are
    ephemeral): its `pause` column is read first. A last post without a recorded style
    falls back to its local sidecar, then to lifetime parity: the k-th TikTok single
    (1-based) was blink when k is odd (the first posts predate calc). Instagram reels
    always use calc; alternation reads TikTok only, and sagas are skipped."""
    from datetime import datetime

    from .publisher.guard import DONE, FAILED, WITHHELD
    from .saga import SAGA_ID_PREFIX

    if post_log is None:
        return None
    candidates: list[tuple[datetime, str, str]] = []
    for job_id, row in post_log.latest_by_job().items():
        if job_id.startswith(SAGA_ID_PREFIX):
            continue
        if (row.get("network") or "").strip().lower() != TIKTOK_NETWORK:
            continue
        if row.get("status") in (FAILED, WITHHELD, "reopened"):
            continue
        if row.get("status") not in DONE:
            continue
        if (row.get("format") or "").strip().lower() == "text":
            continue
        clip_id = (row.get("clip_id") or "").strip()
        if not clip_id:
            continue
        try:
            when = datetime.fromisoformat(row["at"])
        except (KeyError, ValueError):
            continue
        candidates.append((when, clip_id, (row.get("pause") or "").strip().lower()))
    if not candidates:
        return None
    _, clip_id, recorded = max(candidates, key=lambda x: x[0])
    if recorded in (CALC_PAUSE, DEFAULT_PAUSE):
        return recorded
    if clips_dir and (clips_dir / f"{clip_id}.json").is_file():
        return pause_from_clip_sidecar(clip_id, clips_dir)
    return DEFAULT_PAUSE if len(candidates) % 2 == 1 else CALC_PAUSE


def next_single_pause(last: str | None, parity_clip_id: str) -> str:
    """Alternate calc/blink from the previous single clip, or clip-id parity when there is no log."""
    if last == CALC_PAUSE:
        return DEFAULT_PAUSE
    if last == DEFAULT_PAUSE:
        return CALC_PAUSE
    tag = parity_clip_id.rsplit("-", 1)[-1] if parity_clip_id else "0"
    try:
        even = int(tag, 16) % 2 == 0
    except ValueError:
        even = int(hashlib.sha256(parity_clip_id.encode()).hexdigest(), 16) % 2 == 0
    return CALC_PAUSE if even else DEFAULT_PAUSE


def resolve_pause_mode(
    env: Mapping[str, str] | None = None,
    *,
    job_id: str,
    post_log=None,
    clips_dir: Path | None = None,
    is_saga: bool = False,
    parity_clip_id: str = "",
    network: str = "",
) -> str:
    """Effective pause for one clip: blink, calc, or alternate resolved to blink/calc.

    Instagram reels always use calc (founder, 2026-10-03); TikTok follows the env flag."""
    if is_saga:
        return DEFAULT_PAUSE
    if (network or "").strip().lower() == IG_NETWORK:
        return CALC_PAUSE
    raw = clip_pause(env)
    if raw != ALTERNATE_PAUSE:
        return raw
    last = last_single_clip_pause(post_log, clips_dir)
    pid = parity_clip_id or hashlib.sha256(job_id.encode()).hexdigest()[:8]
    return next_single_pause(last, pid)


@dataclass(frozen=True)
class IgPalette:
    """Visibly distinct reel background (founder, 2026-10-03)."""

    name: str
    bg: tuple[int, int, int]
    fg: tuple[int, int, int]
    dim: tuple[int, int, int]


IG_PALETTES: tuple[IgPalette, ...] = (
    IgPalette("stone", (42, 40, 36), (232, 228, 216), (120, 115, 108)),
    IgPalette("ink", (18, 28, 48), (210, 220, 245), (90, 110, 150)),
    IgPalette("paper", (228, 222, 208), (28, 26, 24), (100, 95, 88)),
    IgPalette("graphite", (48, 50, 54), (235, 230, 220), (130, 128, 122)),
    IgPalette("slate", (32, 38, 44), (220, 228, 235), (100, 115, 130)),
    IgPalette("moss", (34, 42, 32), (218, 232, 210), (95, 120, 88)),
)
IG_LAYOUT_Y = (0.30, 0.38, 0.46)  # top third, center, lower third
IG_OPENING_S = 0.5


@dataclass(frozen=True)
class CalcVariant:
    """Per-post calc look, seeded by job id (Instagram reels only)."""

    seed: int
    palette: IgPalette
    layout_y_frac: float
    formula_offset: int
    curve_power: float
    hop_scale: float
    intro_idx: int


def calc_variant(job_id: str) -> CalcVariant:
    """Deterministic calc variation for one post id."""
    raw = hashlib.sha256(f"ig-calc|{job_id}".encode()).digest()
    seed = int.from_bytes(raw[:8], "big")
    rng = random.Random(seed)
    return CalcVariant(
        seed=seed,
        palette=IG_PALETTES[rng.randrange(len(IG_PALETTES))],
        layout_y_frac=IG_LAYOUT_Y[rng.randrange(len(IG_LAYOUT_Y))],
        formula_offset=rng.randint(0, len(FORMULAS) - 1),
        curve_power=round(2.2 + rng.random() * 1.4, 3),
        hop_scale=round(0.75 + rng.random() * 0.6, 3),
        intro_idx=(seed + rng.randint(0, 999)) % len(FORMULAS),
    )


def ig_opening_frames(fps: int) -> int:
    return max(1, round(IG_OPENING_S * fps))


def variant_id_tag(variant: CalcVariant | None) -> str:
    if variant is None:
        return ""
    return hashlib.sha256(
        f"{variant.seed}\0{variant.palette.name}\0{variant.layout_y_frac}\0{variant.formula_offset}\0"
        f"{variant.curve_power}\0{variant.hop_scale}\0{variant.intro_idx}".encode(),
    ).hexdigest()[:8]


_GRAIN_TILE = 128


@lru_cache(maxsize=16)
def _grain_tile(palette_name: str, seed: int) -> Image.Image:
    """One static grain tile per palette+seed; tiled across each frame (not re-rolled per frame)."""
    palette = next(p for p in IG_PALETTES if p.name == palette_name)
    rng = random.Random(seed + 17)
    tile = Image.new("RGB", (_GRAIN_TILE, _GRAIN_TILE), palette.bg)
    px = tile.load()
    r0, g0, b0 = palette.bg
    for y in range(_GRAIN_TILE):
        for x in range(_GRAIN_TILE):
            n = rng.randint(-8, 8)
            px[x, y] = (max(0, min(255, r0 + n)), max(0, min(255, g0 + n)), max(0, min(255, b0 + n)))
    return tile


def _fill_palette(width: int, height: int, palette: IgPalette, seed: int) -> Image.Image:
    """Tiled grain surface: distinct per reel, cheap to draw and to encode."""
    tile = _grain_tile(palette.name, seed)
    img = Image.new("RGB", (width, height))
    tw, th = tile.size
    for y in range(0, height, th):
        for x in range(0, width, tw):
            img.paste(tile, (x, y))
    return img


def frame_mean_diff(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute RGB difference between two same-size images."""
    pa, pb = a.convert("RGB").getdata(), b.convert("RGB").getdata()
    total = 0.0
    n = 0
    for ca, cb in zip(pa, pb, strict=True):
        total += abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])
        n += 3
    return total / max(1, n)


def frame_is_uniform(img: Image.Image, *, spread: float = 12.0) -> bool:
    """True when the frame is nearly a flat field (e.g. empty black + cursor)."""
    px = list(img.convert("RGB").getdata())
    rs = [p[0] for p in px]
    gs = [p[1] for p in px]
    bs = [p[2] for p in px]
    return max(rs) - min(rs) < spread and max(gs) - min(gs) < spread and max(bs) - min(bs) < spread


def calc_seed(category: str, variant: CalcVariant | None = None) -> int:
    base = int.from_bytes(hashlib.sha256(f"calc|{category}".encode()).digest()[:8], "big")
    return (base ^ variant.seed) if variant else base


def formula_fragments() -> tuple[str, ...]:
    return FORMULAS


@lru_cache(maxsize=8)
def _cmap(path: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont

    return frozenset(TTFont(path).getBestCmap().keys())


def resolve_math_font() -> str:
    for candidate in MATH_FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("no math font found; install fonts-noto-extra or fonts-dejavu")


def missing_glyphs(main_path: str, math_path: str, formulas: tuple[str, ...] = FORMULAS) -> list[str]:
    main_cmap = _cmap(main_path)
    math_cmap = _cmap(math_path)
    missing: list[str] = []
    for formula in formulas:
        for ch in formula:
            if ord(ch) in main_cmap or ord(ch) in math_cmap:
                continue
            if ch not in missing:
                missing.append(ch)
    return missing


def _use_math_font(ch: str, main_cmap: frozenset[int], math_cmap: frozenset[int]) -> bool:
    cp = ord(ch)
    if ch in _MAIN_ASCII and cp in main_cmap:
        return False
    if cp in math_cmap:
        return True
    return cp not in main_cmap


def _mutate(formula: str, rng: random.Random, intensity: float) -> str:
    """Change operands/indices/variables only; structure stays intact."""
    out: list[str] = []
    for ch in formula:
        r = rng.random()
        if ch in _DIGITS and r < 0.2 * intensity:
            out.append(rng.choice(_DIGITS))
        elif ch in _SUBS and r < 0.16 * intensity:
            out.append(rng.choice(_SUBS))
        elif ch in _VARS and r < 0.14 * intensity:
            out.append(rng.choice(_VARS))
        elif ch in _SUPS and r < 0.14 * intensity:
            out.append(rng.choice(_SUPS))
        else:
            out.append(ch)
    return "".join(out)


def _mixed_width(
    text: str,
    main_font: ImageFont.FreeTypeFont,
    math_font: ImageFont.FreeTypeFont,
    main_cmap: frozenset[int],
    math_cmap: frozenset[int],
) -> float:
    """Drawn width of a formula line (per-glyph font fallback, as `_draw_mixed` draws it)."""
    return sum(
        (math_font if _use_math_font(ch, main_cmap, math_cmap) else main_font).getlength(ch) for ch in text
    )


def _formula_line(
    seed: int,
    frame: int,
    total: int,
    width_of,
    max_w: float,
    variant: CalcVariant | None = None,
) -> str:
    """One wide line of mutating formulas. ``width_of`` measures the line as drawn."""
    t = frame / max(1, total - 1)
    rng = random.Random(seed + frame * 9973 + int(t * 80000))
    power = variant.curve_power if variant else 2.8
    hop_scale = variant.hop_scale if variant else 1.0
    offset = variant.formula_offset if variant else 0
    intensity = min(10.0, 0.35 + 18 * t ** (power * 0.35 + 0.65))
    target = max_w * 0.88
    # Accelerating identity changes: many distinct formulas per second near the end.
    hop = max(1, int((1 + 22 * t ** power) * hop_scale))
    if frame == 0 and variant is not None:
        base_idx = variant.intro_idx
        intro_rng = random.Random(variant.seed + 41)
        return _mutate(FORMULAS[base_idx], intro_rng, max(0.55, intensity))
    base_idx = (seed + offset + (frame // hop) * 17) % len(FORMULAS)
    parts = [_mutate(FORMULAS[base_idx], rng, intensity)]
    for j in range(3):
        if width_of(" · ".join(parts)) >= target * 0.85:
            break
        idx = (seed + offset + frame * (j + 3) + rng.randint(0, 9999)) % len(FORMULAS)
        nxt = _mutate(FORMULAS[idx], random.Random(seed + frame + idx * 31), intensity)
        trial = " · ".join(parts + [nxt])
        if width_of(trial) > max_w:
            break
        parts.append(nxt)
    return " · ".join(parts)


def _baseline_y(fm, lay: Layout, center_frac: float | None = None) -> int:
    cy = (center_frac if center_frac is not None else 0.38) * lay.height
    top = cy - lay.line_h / 2
    half_leading = (lay.line_h - (fm.ascent + fm.descent)) / 2
    return round(top + half_leading + fm.ascent)


def _draw_mixed(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: int,
    text: str,
    main_font: ImageFont.FreeTypeFont,
    math_font: ImageFont.FreeTypeFont,
    main_cmap: frozenset[int],
    math_cmap: frozenset[int],
    fill: tuple[int, int, int],
) -> None:
    cx = x
    for ch in text:
        font = math_font if _use_math_font(ch, main_cmap, math_cmap) else main_font
        draw.text((cx, y), ch, font=font, fill=fill, anchor="ls")
        cx += font.getlength(ch)


MIN_FORMULA_SCALE = 0.45


@dataclass(frozen=True)
class FormulaPlacement:
    """Where one formula frame lands: always centered, always inside the side margins."""

    text: str
    x: float
    baseline: int
    size: int
    width: float


def place_formula(
    text: str, baseline: int, font_path: str, math_path: str, lay: Layout,
) -> FormulaPlacement:
    """Center the line; shrink the font (never scroll) until it fits ``lay.max_text_w``."""
    main_cmap, math_cmap = _cmap(font_path), _cmap(math_path)
    size = lay.font_px
    floor = max(1, int(lay.font_px * MIN_FORMULA_SCALE))
    while True:
        w = _mixed_width(text, _font(font_path, size), _font(math_path, size), main_cmap, math_cmap)
        if w <= lay.max_text_w or size <= floor:
            break
        size = max(floor, min(size - 1, int(size * lay.max_text_w / w)))
    if w > lay.max_text_w:  # still too wide at the floor size: drop trailing formulas
        parts = text.split(" · ")
        while len(parts) > 1 and w > lay.max_text_w:
            parts.pop()
            text = " · ".join(parts)
            w = _mixed_width(text, _font(font_path, size), _font(math_path, size), main_cmap, math_cmap)
    return FormulaPlacement(text, (lay.width - w) / 2, baseline, size, w)


def input_layout(category: str, font_path: str, lay: Layout, center_y: float):
    """The input exactly as the ffmpeg screens place it (centered rows around ``center_y``)."""
    from .render import layout_frame

    return layout_frame(category, "loading", False, metrics(font_path, lay.font_px), lay, center_y=center_y)


def formula_baseline(font_path: str, lay: Layout, center_y: float) -> int:
    """Baseline of a single row centered on ``center_y``: the input's own row when it fits one line."""
    from .render import layout_frame

    frame = layout_frame("x", "loading", False, metrics(font_path, lay.font_px), lay, center_y=center_y)
    return frame.lines[0].baseline


@dataclass(frozen=True)
class CalcLook:
    """Surface, ink and the row the input / formula / verdict share."""

    bg: tuple[int, int, int]
    fg: tuple[int, int, int]
    dim: tuple[int, int, int]
    center_y: float
    surface: Image.Image | None = None  # palette grain; flat ``bg`` when None


def app_look(lay: Layout) -> CalcLook:
    return CalcLook(BG_RGB, FG_RGB, DIM_RGB, lay.center_y)


def ig_look(lay: Layout, variant: CalcVariant) -> CalcLook:
    p = variant.palette
    return CalcLook(p.bg, p.fg, p.dim, variant.layout_y_frac * lay.height,
                    _fill_palette(lay.width, lay.height, p, variant.seed))


def _surface(lay: Layout, look: CalcLook) -> Image.Image:
    if look.surface is not None:
        return look.surface.copy()
    return Image.new("RGB", (lay.width, lay.height), look.bg)


def _draw_footer(draw: ImageDraw.ImageDraw, font_path: str, lay: Layout, fill) -> None:
    ff = metrics(font_path, lay.footer_px)
    fp = footer_placement(lay, ff)
    draw.text((fp.x, fp.baseline), fp.text, font=_font(font_path, lay.footer_px), fill=fill, anchor="ls")


def draw_text_frame(text: str, kind: str, font_path: str, lay: Layout, look: CalcLook) -> Image.Image:
    """Input or verdict alone, placed like the ffmpeg screens (same rows, same center)."""
    from .render import layout_frame

    img = _surface(lay, look)
    draw = ImageDraw.Draw(img)
    if text:
        frame = layout_frame(text, kind, False, metrics(font_path, lay.font_px), lay, center_y=look.center_y)
        font = _font(font_path, lay.font_px)
        for p in frame.lines:
            draw.text((p.x, p.baseline), p.text, font=font, fill=look.fg, anchor="ls")
    _draw_footer(draw, font_path, lay, look.dim)
    return img


def draw_formula_frame(
    category: str,
    frame: int,
    total: int,
    font_path: str,
    math_path: str,
    lay: Layout,
    look: CalcLook,
    variant: CalcVariant | None = None,
) -> Image.Image:
    """Formula line alone, on the input's row. The input is never drawn on this frame."""
    img = _surface(lay, look)
    draw = ImageDraw.Draw(img)
    main_cmap, math_cmap = _cmap(font_path), _cmap(math_path)
    main_font = _font(font_path, lay.font_px)
    math_font = _font(math_path, lay.font_px)

    def width_of(text: str) -> float:
        return _mixed_width(text, main_font, math_font, main_cmap, math_cmap)

    line = _formula_line(calc_seed(category, variant), frame, total, width_of, lay.max_text_w, variant)
    fp = place_formula(line, formula_baseline(font_path, lay, look.center_y), font_path, math_path, lay)
    _draw_mixed(draw, fp.x, fp.baseline, fp.text, _font(font_path, fp.size), _font(math_path, fp.size),
                main_cmap, math_cmap, look.fg)
    _draw_footer(draw, font_path, lay, look.dim)
    return img


def formula_placements(
    category: str, total: int, font_path: str, lay: Layout, look: CalcLook,
    variant: CalcVariant | None = None,
) -> list[FormulaPlacement]:
    """Placement of every formula frame (for checks: centered, inside the margins)."""
    math_path = resolve_math_font()
    main_cmap, math_cmap = _cmap(font_path), _cmap(math_path)
    main_font = _font(font_path, lay.font_px)
    math_font = _font(math_path, lay.font_px)
    base = formula_baseline(font_path, lay, look.center_y)
    out = []
    for i in range(total):
        line = _formula_line(
            calc_seed(category, variant), i, total,
            lambda t: _mixed_width(t, main_font, math_font, main_cmap, math_cmap), lay.max_text_w, variant,
        )
        out.append(place_formula(line, base, font_path, math_path, lay))
    return out


def render_ig_opening_frame(
    category: str,
    job_id: str,
    *,
    font_path: str,
    layout: Layout | None = None,
) -> Image.Image:
    """Frame 0 of an Instagram word-style reel body: the typed input alone on its palette."""
    lay = layout or Layout()
    variant = calc_variant(job_id)
    return draw_text_frame(category, "loading", font_path, lay, ig_look(lay, variant))


def render_calc_frames(
    category: str,
    out_dir: Path,
    *,
    frame_count: int,
    font_path: str,
    width: int = 1080,
    height: int = 1920,
    layout: Layout | None = None,
    variant: CalcVariant | None = None,
    look: CalcLook | None = None,
    input_frames: int = 0,
    empty_frames: int = 0,
) -> list[Path]:
    """``input_frames`` of input alone, then the formula line alone, then ``empty_frames`` of
    bare surface. Input and formula never share a frame; both sit on ``look.center_y``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lay = layout or Layout(width=width, height=height)
    look = look or (ig_look(lay, variant) if variant is not None else app_look(lay))
    math_path = resolve_math_font()
    formula_n = frame_count - input_frames - empty_frames
    if formula_n < 1:
        raise ValueError("calc span too short for its input and empty holds")
    paths: list[Path] = []
    input_png = out_dir / "input.png"
    empty_png = out_dir / "empty.png"
    if input_frames:
        draw_text_frame(category, "loading", font_path, lay, look).save(input_png)
    if empty_frames:
        draw_text_frame("", "loading", font_path, lay, look).save(empty_png)
    for i in range(frame_count):
        path = out_dir / f"frame_{i:04d}.png"
        if i < input_frames:
            shutil.copyfile(input_png, path)
        elif i >= input_frames + formula_n:
            shutil.copyfile(empty_png, path)
        else:
            draw_formula_frame(category, i - input_frames, formula_n, font_path, math_path, lay, look,
                               variant).save(path)
        paths.append(path)
    return paths


def render_still_frames(img: Image.Image, out_dir: Path, frame_count: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    first = out_dir / "frame_0000.png"
    img.save(first)
    for i in range(1, frame_count):
        shutil.copyfile(first, out_dir / f"frame_{i:04d}.png")


def frames_to_video(frames_dir: Path, dest: Path, *, fps: int) -> None:
    pattern = str(frames_dir / "frame_%04d.png")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-start_number", "0", "-i", pattern,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            str(dest),
        ],
        check=True,
        capture_output=True,
    )


def frame_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def playwright_available() -> bool:
    return bool(shutil.which("ffmpeg"))

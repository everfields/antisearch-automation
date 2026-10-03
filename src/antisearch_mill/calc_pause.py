"""Calc pause: one accelerating formula line during the oracle wait."""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .fonts import _font, metrics
from .render import Layout, footer_placement

CALC_PAUSE = "calc"
DEFAULT_PAUSE = "blink"
PAUSE_MODES = (DEFAULT_PAUSE, CALC_PAUSE)

BG_RGB = (10, 10, 10)
FG_RGB = (232, 228, 216)
DIM_RGB = (70, 68, 65)

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
        raise ValueError(f"PUBLISHER_CLIP_PAUSE={raw!r}; use blink or calc")
    return raw


def calc_seed(category: str) -> int:
    return int.from_bytes(hashlib.sha256(f"calc|{category}".encode()).digest()[:8], "big")


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


def _formula_line(seed: int, frame: int, total: int, fm, lay: Layout) -> str:
    t = frame / max(1, total - 1)
    rng = random.Random(seed + frame * 9973 + int(t * 80000))
    intensity = min(10.0, 0.4 + 18 * t * t)
    target = lay.max_text_w * 0.88
    # Accelerating identity changes: many distinct formulas per second near the end.
    hop = max(1, int(1 + 22 * t ** 2.8))
    base_idx = (seed + (frame // hop) * 17) % len(FORMULAS)
    parts = [_mutate(FORMULAS[base_idx], rng, intensity)]
    for j in range(3):
        if fm.width(" · ".join(parts)) >= target * 0.85:
            break
        idx = (seed + frame * (j + 3) + rng.randint(0, 9999)) % len(FORMULAS)
        nxt = _mutate(FORMULAS[idx], random.Random(seed + frame + idx * 31), intensity)
        trial = " · ".join(parts + [nxt])
        if fm.width(trial) > lay.max_text_w:
            break
        parts.append(nxt)
    return " · ".join(parts)


def _baseline_y(fm, lay: Layout) -> int:
    cy = lay.center_y
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


def _draw_calc_frame(
    category: str,
    frame: int,
    total: int,
    font_path: str,
    math_path: str,
    lay: Layout,
) -> Image.Image:
    img = Image.new("RGB", (lay.width, lay.height), BG_RGB)
    draw = ImageDraw.Draw(img)
    fm = metrics(font_path, lay.font_px)
    main_font = _font(font_path, lay.font_px)
    math_font = _font(math_path, lay.font_px)
    main_cmap, math_cmap = _cmap(font_path), _cmap(math_path)
    formula = _formula_line(calc_seed(category), frame, total, fm, lay)
    baseline = _baseline_y(fm, lay)
    text_w = sum(
        (math_font if _use_math_font(ch, main_cmap, math_cmap) else main_font).getlength(ch)
        for ch in formula
    )
    margin = lay.px(20)
    max_w = lay.max_text_w
    t = frame / max(1, total - 1)
    if text_w <= max_w:
        x = (lay.width - text_w) / 2
    else:
        scroll = int((t ** 1.5) * (text_w - max_w + 40))
        x = margin - scroll
    _draw_mixed(draw, x, baseline, formula, main_font, math_font, main_cmap, math_cmap, FG_RGB)
    ff = metrics(font_path, lay.footer_px)
    fp = footer_placement(lay, ff)
    draw.text((fp.x, fp.baseline), fp.text, font=_font(font_path, lay.footer_px), fill=DIM_RGB, anchor="ls")
    return img


def render_calc_frames(
    category: str,
    out_dir: Path,
    *,
    frame_count: int,
    font_path: str,
    width: int = 1080,
    height: int = 1920,
    layout: Layout | None = None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lay = layout or Layout(width=width, height=height)
    math_path = resolve_math_font()
    paths: list[Path] = []
    for i in range(frame_count):
        path = out_dir / f"frame_{i:04d}.png"
        _draw_calc_frame(category, i, frame_count, font_path, math_path, lay).save(path)
        paths.append(path)
    return paths


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

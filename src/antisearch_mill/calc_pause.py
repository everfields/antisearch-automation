"""Calc pause: one accelerating formula line during the oracle wait.

When ``PUBLISHER_CLIP_PAUSE=calc``, the blinking-caret pause is replaced by a
single line of real mathematical formulas at the same position and size as the
typed input and verdict. The line mutates faster and faster, spans most of the
screen width, then the verdict appears on that same line. Deterministic from the
input; rendered with Pillow to match the monolith layout exactly.
"""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, ImageDraw

from .fonts import _font, metrics
from .render import Layout, footer_placement

CALC_PAUSE = "calc"
DEFAULT_PAUSE = "blink"
PAUSE_MODES = (DEFAULT_PAUSE, CALC_PAUSE)

BG_RGB = (10, 10, 10)
FG_RGB = (232, 228, 216)
DIM_RGB = (70, 68, 65)  # E8E4D8 at 30%

# Complete formulas only: calculus, algebra, linear algebra, statistics.
FORMULAS: tuple[str, ...] = (
    "∫₀¹ x² dx = 1/3",
    "∂f/∂x = lim_{h→0} (f(x+h) − f(x))/h",
    "∑_{i=1}^n i = n(n+1)/2",
    "E[X] = ∑_i x_i P(x_i)",
    "Var(X) = E[X²] − (E[X])²",
    "softmax(z_i) = exp(z_i) / ∑_j exp(z_j)",
    "∇f(x) = (∂f/∂x_1, …, ∂f/∂x_n)",
    "Ax = b",
    "det([[a,b],[c,d]]) = ad − bc",
    "Av = λv",
    "f(x) = f(a) + f'(a)(x−a) + f''(a)(x−a)²/2",
    "θ_{t+1} = θ_t − η ∇L(θ_t)",
    "∂L/∂w = (1/m) ∑_i ∇L_i",
    "σ² = (1/n) ∑_i (x_i − μ)²",
    "(AB)_{ij} = ∑_k A_{ik} B_{kj}",
    "‖x‖₂ = √(∑_i x_i²)",
    "P(A∩B) = P(A)P(B|A)",
    "∫_{−∞}^{∞} e^{−x²} dx = √π",
    "dy/dx + P(x)y = Q(x)",
    "Cov(X,Y) = E[XY] − E[X]E[Y]",
    "P(A|B) = P(B|A)P(A) / P(B)",
    "∂²f/∂x∂y = ∂²f/∂y∂x",
    "∫_a^b f'(x)dx = f(b) − f(a)",
    "∑_{k=0}^∞ ar^k = a/(1−r), |r|<1",
    "log(ab) = log a + log b",
    "sin²θ + cos²θ = 1",
    "∇·(∇φ) = ∇²φ",
    "z = (x−μ)/σ",
    "r = ∑(x_i−x̄)(y_i−ȳ) / √(∑(x_i−x̄)² ∑(y_i−ȳ)²)",
    "∫ sin(x)cos(x)dx = sin²(x)/2 + C",
    "∂/∂x (x^n) = n x^{n−1}",
    "E[aX+b] = aE[X] + b",
    "∑_{i,j} A_{ij} = tr(A)",
    "x^T A x = ∑_{i,j} x_i A_{ij} x_j",
    "∇_θ J(θ) = ∂J/∂θ",
    "H_{ij} = ∂²L / ∂θ_i ∂θ_j",
    "∫_0^{2π} sin(x)dx = 0",
    "P(X=k) = e^{−λ} λ^k / k!",
    "β = (X^T X)^{−1} X^T y",
    "SVD: A = UΣV^T",
    "‖A‖_F = √(∑_{i,j} A_{ij}²)",
    "∂L/∂z = ŷ − y",
    "KL(p‖q) = ∑_i p_i log(p_i/q_i)",
    "∫_0^1 (1−x)^n dx = 1/(n+1)",
    "det(A) = ∏_i λ_i",
    "∑_{i=1}^n 1/i² = π²/6",
)


def clip_pause(env: Mapping[str, str] | None = None) -> str:
    """``PUBLISHER_CLIP_PAUSE``: ``blink`` (default) or ``calc``. Blank means ``blink``."""
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
    """The programmed formula set (for tests)."""
    return FORMULAS


def _formula_at(seed: int, frame: int, total: int) -> str:
    """One complete formula, mutating faster as the pause progresses."""
    t = frame / max(1, total - 1)
    rng = random.Random(seed + frame * 9973)
    base = FORMULAS[(seed + int(t * len(FORMULAS) * 4)) % len(FORMULAS)]
    if t > 0.9:
        return base
    rate = 1.0 + 14.0 * t * t
    chars = list(base)
    digits = "0123456789"
    subs = "ᵢⱼₙₖₘₜₚₗₛ"
    n = max(1, int(rate * len(chars) * 0.14))
    for _ in range(n):
        i = rng.randrange(len(chars))
        c = chars[i]
        if c in digits:
            chars[i] = rng.choice(digits)
        elif c in subs:
            chars[i] = rng.choice(subs)
        elif c in "xyzabctuvw":
            chars[i] = rng.choice("xyzabctuvw")
        elif c in "+−×/=<>[]()":
            chars[i] = rng.choice("+−×/=<>[]()")
    if t > 0.1 and rng.random() < 0.1 * t:
        return FORMULAS[rng.randrange(len(FORMULAS))]
    return "".join(chars)


def _baseline_y(fm, lay: Layout) -> int:
    """Same vertical position as a single-line input or verdict."""
    cy = lay.center_y
    top = cy - lay.line_h / 2
    half_leading = (lay.line_h - (fm.ascent + fm.descent)) / 2
    return round(top + half_leading + fm.ascent)


def _draw_calc_frame(category: str, frame: int, total: int, font_path: str, lay: Layout) -> Image.Image:
    img = Image.new("RGB", (lay.width, lay.height), BG_RGB)
    draw = ImageDraw.Draw(img)
    fm = metrics(font_path, lay.font_px)
    font = _font(font_path, lay.font_px)
    formula = _formula_at(calc_seed(category), frame, total)
    baseline = _baseline_y(fm, lay)
    text_w = fm.width(formula)
    margin = lay.px(20)
    max_w = lay.max_text_w
    if text_w <= max_w:
        x = (lay.width - text_w) / 2
    else:
        t = frame / max(1, total - 1)
        scroll = int((t ** 1.7) * (text_w - max_w + 60))
        x = margin - scroll
    draw.text((x, baseline), formula, font=font, fill=FG_RGB, anchor="ls")
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
    """Render ``frame_count`` PNG frames into ``out_dir``. Deterministic from ``category``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lay = layout or Layout(width=width, height=height)
    paths: list[Path] = []
    for i in range(frame_count):
        path = out_dir / f"frame_{i:04d}.png"
        _draw_calc_frame(category, i, frame_count, font_path, lay).save(path)
        paths.append(path)
    return paths


def frames_to_video(frames_dir: Path, dest: Path, *, fps: int) -> None:
    """Encode a PNG sequence as a short h264 clip."""
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
    """Calc frames render with Pillow; only ffmpeg is required for the full pipeline."""
    return bool(shutil.which("ffmpeg"))

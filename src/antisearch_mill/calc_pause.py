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


def calc_hold_frames(fps: int) -> tuple[int, int]:
    """Pre- and post-formula hold frames (input+cursor, then empty+cursor)."""
    return max(1, round(CALC_PRE_HOLD_S * fps)), max(1, round(CALC_POST_HOLD_S * fps))

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
    """Pause mode of the latest TikTok single-verdict clip in the post log, or None.

    Instagram reels always use calc; alternation reads TikTok only."""
    from datetime import datetime

    from .publisher.guard import DONE, FAILED, WITHHELD
    from .saga import SAGA_ID_PREFIX

    if post_log is None:
        return None
    candidates: list[tuple[datetime, str]] = []
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
        candidates.append((when, clip_id))
    if not candidates:
        return None
    _, clip_id = max(candidates, key=lambda x: x[0])
    return pause_from_clip_sidecar(clip_id, clips_dir)


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
class CalcVariant:
    """Per-post calc look, seeded by job id (Instagram reels only)."""

    seed: int
    bg_rgb: tuple[int, int, int]
    formula_offset: int
    curve_power: float
    hop_scale: float
    intro_idx: int


def calc_variant(job_id: str) -> CalcVariant:
    """Deterministic calc variation for one post id."""
    raw = hashlib.sha256(f"ig-calc|{job_id}".encode()).digest()
    seed = int.from_bytes(raw[:8], "big")
    rng = random.Random(seed)
    tone = rng.randint(-18, 22)
    bg = tuple(max(0, min(255, BG_RGB[i] + tone + (i - 1) * rng.randint(-4, 4))) for i in range(3))
    return CalcVariant(
        seed=seed,
        bg_rgb=bg,
        formula_offset=rng.randint(0, len(FORMULAS) - 1),
        curve_power=round(2.2 + rng.random() * 1.4, 3),
        hop_scale=round(0.75 + rng.random() * 0.6, 3),
        intro_idx=(seed + rng.randint(0, 999)) % len(FORMULAS),
    )


def variant_id_tag(variant: CalcVariant | None) -> str:
    if variant is None:
        return ""
    return hashlib.sha256(
        f"{variant.seed}\0{variant.bg_rgb}\0{variant.formula_offset}\0"
        f"{variant.curve_power}\0{variant.hop_scale}\0{variant.intro_idx}".encode(),
    ).hexdigest()[:8]


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


def _formula_line(
    seed: int,
    frame: int,
    total: int,
    fm,
    lay: Layout,
    variant: CalcVariant | None = None,
) -> str:
    t = frame / max(1, total - 1)
    rng = random.Random(seed + frame * 9973 + int(t * 80000))
    power = variant.curve_power if variant else 2.8
    hop_scale = variant.hop_scale if variant else 1.0
    offset = variant.formula_offset if variant else 0
    intensity = min(10.0, 0.35 + 18 * t ** (power * 0.35 + 0.65))
    target = lay.max_text_w * 0.88
    # Accelerating identity changes: many distinct formulas per second near the end.
    hop = max(1, int((1 + 22 * t ** power) * hop_scale))
    if frame == 0 and variant is not None:
        base_idx = variant.intro_idx
        intro_rng = random.Random(variant.seed + 41)
        return _mutate(FORMULAS[base_idx], intro_rng, max(0.55, intensity))
    base_idx = (seed + offset + (frame // hop) * 17) % len(FORMULAS)
    parts = [_mutate(FORMULAS[base_idx], rng, intensity)]
    for j in range(3):
        if fm.width(" · ".join(parts)) >= target * 0.85:
            break
        idx = (seed + offset + frame * (j + 3) + rng.randint(0, 9999)) % len(FORMULAS)
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
    variant: CalcVariant | None = None,
) -> Image.Image:
    bg = variant.bg_rgb if variant else BG_RGB
    img = Image.new("RGB", (lay.width, lay.height), bg)
    draw = ImageDraw.Draw(img)
    fm = metrics(font_path, lay.font_px)
    main_font = _font(font_path, lay.font_px)
    math_font = _font(math_path, lay.font_px)
    main_cmap, math_cmap = _cmap(font_path), _cmap(math_path)
    formula = _formula_line(calc_seed(category, variant), frame, total, fm, lay, variant)
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
    variant: CalcVariant | None = None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lay = layout or Layout(width=width, height=height)
    math_path = resolve_math_font()
    paths: list[Path] = []
    for i in range(frame_count):
        path = out_dir / f"frame_{i:04d}.png"
        _draw_calc_frame(category, i, frame_count, font_path, math_path, lay, variant).save(path)
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

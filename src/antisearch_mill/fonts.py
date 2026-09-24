"""Font resolution + metrics.

The product renders in the platform system sans (-apple-system / Roboto).
Inter is the closest freely-installable match; the chain falls back to
whatever sans the host has. Widths are measured with Pillow (HarfBuzz via
raqm when available), the same shaper ffmpeg 6.1+ drawtext uses, so the
cursor lands flush against the typed text.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont, features

CANDIDATE_FILES = (
    "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
    "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
    "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/croscore/Arimo-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    "/Library/Fonts/Arial.ttf",
)
FC_PATTERNS = ("Inter:style=Regular", "Roboto:style=Regular", "sans-serif")


class FontNotFound(RuntimeError):
    pass


def _fc_match(pattern: str) -> str | None:
    if not shutil.which("fc-match"):
        return None
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out and Path(out).is_file() else None


def resolve_font(explicit: str = "") -> str:
    if explicit:
        if Path(explicit).is_file():
            return explicit
        raise FontNotFound(f"MILL_FONT does not exist: {explicit}")
    for candidate in CANDIDATE_FILES:
        if Path(candidate).is_file():
            return candidate
    for pattern in FC_PATTERNS:
        found = _fc_match(pattern)
        if found:
            return found
    raise FontNotFound("no usable sans font found; install fonts-inter or set MILL_FONT")


@dataclass(frozen=True)
class FontMetrics:
    path: str
    size: int
    ascent: int
    descent: int
    ch: float  # advance of "0", the CSS `ch` unit

    def width(self, text: str) -> float:
        return _font(self.path, self.size).getlength(text) if text else 0.0


@lru_cache(maxsize=32)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    engine = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size, layout_engine=engine)


@lru_cache(maxsize=32)
def metrics(path: str, size: int) -> FontMetrics:
    font = _font(path, size)
    ascent, descent = font.getmetrics()
    return FontMetrics(path=path, size=size, ascent=ascent, descent=descent, ch=font.getlength("0"))

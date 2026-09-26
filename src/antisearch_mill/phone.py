"""Generic smartphone mockup around the `app` screen, drawn in code.

Founder, 2026-09-26: the clip plays inside a phone so it reads as the app
being used. Anti-fancy, cold, dark. A modern slab: thin even bezels, rounded
corners, an optional centered punch-hole camera, and plain side buttons. No
logo, no notch or island shape, no brand silhouette, no status bar, no glare,
no hand, no caption. The only text on screen is what the app itself shows.

`PUBLISHER_CLIP_FRAME=none` (the default) renders exactly as before. `phone`
draws the mockup at `PUBLISHER_CLIP_PHONE_SCALE` of the 9:16 height (0.80 by
default) on `PUBLISHER_CLIP_PHONE_BG`.

Founder, 2026-09-26, second pass: on black or the dark gradient the phone
disappears. The feed has to read "a phone" at a glance, so the calm surfaces
are lighter than the phone: `stone` (mid warm grey), `bone` (off-white), and
`sage` (a muted grey-green mid-tone). The phone stays a near-black slab with a
graphite rim line, a pure-black bezel, and a soft contact shadow. `stone` is
the default. `black` and `gradient` still work.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

FRAME_NONE = "none"
FRAME_PHONE = "phone"
CLIP_FRAMES = (FRAME_NONE, FRAME_PHONE)
# Flat, calm surfaces. No saturated colour.
SURFACES = {
    "stone": (138, 133, 125),
    "bone": (224, 219, 207),
    "sage": (128, 134, 122),
}
PHONE_BACKGROUNDS = ("black", "gradient", *SURFACES)
DEFAULT_PHONE_SCALE = 0.80
MIN_PHONE_SCALE = 0.60
MAX_PHONE_SCALE = 0.95
# Screen aspect of a current slab phone (19.5:9), not the 9:16 video.
SCREEN_ASPECT = 9 / 19.5

BEZEL = (0, 0, 0)
RIM = (74, 74, 78)
BUTTON = (27, 27, 29)
CAMERA = (0, 0, 0)
CAMERA_RING = (20, 20, 22)
_SS = 2  # supersampling for clean curves


@dataclass(frozen=True)
class PhoneSpec:
    scale: float = DEFAULT_PHONE_SCALE
    background: str = "stone"
    punch_hole: bool = True
    buttons: bool = True

    @property
    def tag(self) -> str:
        return f"phone:{self.scale:.2f}:{self.background}"


@dataclass(frozen=True)
class PhoneGeometry:
    canvas_w: int
    canvas_h: int
    body_x: int
    body_y: int
    body_w: int
    body_h: int
    bezel: int
    radius: int
    screen_x: int
    screen_y: int
    screen_w: int
    screen_h: int
    screen_radius: int


def clip_frame(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_FRAME`: `none` (default) or `phone`. Blank means `none`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_FRAME") or "").strip().lower()
    if not raw:
        return FRAME_NONE
    if raw not in CLIP_FRAMES:
        raise ValueError(f"PUBLISHER_CLIP_FRAME={raw!r}; use none or phone")
    return raw


def phone_scale(env: Mapping[str, str] | None = None) -> float:
    """`PUBLISHER_CLIP_PHONE_SCALE`: phone height over video height. `0.8` and `80` both mean 80%."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_PHONE_SCALE") or "").strip().rstrip("%")
    if not raw:
        return DEFAULT_PHONE_SCALE
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"PUBLISHER_CLIP_PHONE_SCALE={raw!r}; use a fraction like 0.80") from None
    if value > 1.0:
        value /= 100.0
    if not MIN_PHONE_SCALE <= value <= MAX_PHONE_SCALE:
        raise ValueError(
            f"PUBLISHER_CLIP_PHONE_SCALE={raw!r}; use {MIN_PHONE_SCALE:.2f} to {MAX_PHONE_SCALE:.2f}"
        )
    return round(value, 4)


def phone_background(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_PHONE_BG`: `stone` (default), `bone`, `sage`, `black`, or `gradient`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_PHONE_BG") or "").strip().lower()
    if not raw:
        return "stone"
    if raw not in PHONE_BACKGROUNDS:
        raise ValueError(f"PUBLISHER_CLIP_PHONE_BG={raw!r}; use {', '.join(PHONE_BACKGROUNDS)}")
    return raw


def phone_spec(env: Mapping[str, str] | None = None) -> PhoneSpec | None:
    """The phone to draw, or None when the frame is off. Scale and bg are checked only when it is on."""
    if clip_frame(env) != FRAME_PHONE:
        return None
    return PhoneSpec(scale=phone_scale(env), background=phone_background(env))


def _even(v: float) -> int:
    return 2 * round(v / 2)


def geometry(spec: PhoneSpec, canvas_w: int = 1080, canvas_h: int = 1920) -> PhoneGeometry:
    """Even-pixel placement, so the yuv420p screen sits on whole chroma samples."""
    body_h = _even(spec.scale * canvas_h)
    bezel = max(4, _even(body_h * 0.011))
    screen_h = body_h - 2 * bezel
    screen_w = _even(screen_h * SCREEN_ASPECT)
    body_w = screen_w + 2 * bezel
    body_x = _even((canvas_w - body_w) / 2)
    body_y = _even((canvas_h - body_h) / 2)
    radius = round(body_w * 0.125)
    return PhoneGeometry(
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        body_x=body_x,
        body_y=body_y,
        body_w=body_w,
        body_h=body_h,
        bezel=bezel,
        radius=radius,
        screen_x=body_x + bezel,
        screen_y=body_y + bezel,
        screen_w=screen_w,
        screen_h=screen_h,
        screen_radius=max(1, radius - bezel),
    )


def _background(w: int, h: int, kind: str) -> Image.Image:
    if kind == "black":
        return Image.new("RGB", (w, h), (0, 0, 0))
    if kind in SURFACES:
        return Image.new("RGB", (w, h), SURFACES[kind])
    # Radial falloff from just above center: about #161616 to #050505. Computed
    # in float, then an ordered dither, so the 8-bit steps do not band.
    lo, hi = 5.0, 22.0
    cx, cy = w / 2, h * 0.46
    rx, ry = w * 0.62, h * 0.52
    bayer = [(b + 0.5) / 16.0 for b in (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)]
    xs = [((x - cx) / rx) ** 2 for x in range(w)]
    pixels = bytearray(w * h)
    for y in range(h):
        row = bayer[(y & 3) * 4:(y & 3) * 4 + 4]
        dy = ((y - cy) / ry) ** 2
        base = y * w
        for x in range(w):
            t = 1.0 - (xs[x] + dy) ** 0.5
            v = lo + (hi - lo) * (t * t * (3 - 2 * t) if t > 0 else 0.0)
            pixels[base + x] = min(255, int(v + row[x & 3]))
    gray = Image.frombytes("L", (w, h), bytes(pixels))
    return Image.merge("RGB", (gray, gray, gray))


def draw_phone(path: Path, spec: PhoneSpec, geom: PhoneGeometry) -> None:
    """RGBA overlay for the whole 9:16 frame. The screen is a transparent rounded hole."""
    s = _SS
    w, h = geom.canvas_w * s, geom.canvas_h * s
    bx, by, bw, bh = geom.body_x * s, geom.body_y * s, geom.body_w * s, geom.body_h * s
    sx, sy, sw, sh = geom.screen_x * s, geom.screen_y * s, geom.screen_w * s, geom.screen_h * s
    radius, sradius = geom.radius * s, geom.screen_radius * s

    phone = Image.new("RGBA", (w, h), (*BEZEL, 0))
    draw = ImageDraw.Draw(phone)
    if spec.buttons:
        out = round(bw * 0.009)
        thick = round(bw * 0.022)
        rr = thick // 2

        def button(side: str, top: float, length: float) -> None:
            y0 = by + round(bh * top)
            y1 = y0 + round(bh * length)
            if side == "right":
                box = (bx + bw - thick + out, y0, bx + bw + out, y1)
            else:
                box = (bx - out, y0, bx + thick - out, y1)
            draw.rounded_rectangle(box, radius=rr, fill=(*BUTTON, 255))

        button("left", 0.175, 0.062)
        button("left", 0.250, 0.062)
        button("right", 0.215, 0.095)
    rim = max(2, round(bw * 0.005))
    draw.rounded_rectangle((bx, by, bx + bw - 1, by + bh - 1), radius=radius, fill=(*RIM, 255))
    draw.rounded_rectangle(
        (bx + rim, by + rim, bx + bw - 1 - rim, by + bh - 1 - rim),
        radius=max(1, radius - rim), fill=(*BEZEL, 255),
    )

    hole = Image.new("L", (w, h), 0)
    hdraw = ImageDraw.Draw(hole)
    hdraw.rounded_rectangle((sx, sy, sx + sw - 1, sy + sh - 1), radius=sradius, fill=255)
    if spec.punch_hole:
        d = round(sw * 0.034)
        cx = sx + sw / 2
        cy = sy + round(sh * 0.021) + d / 2
        ring = max(1, round(d * 0.14))
        box = (cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2)
        hdraw.ellipse(box, fill=0)
        draw.ellipse(box, fill=(*CAMERA_RING, 255))
        draw.ellipse((box[0] + ring, box[1] + ring, box[2] - ring, box[3] - ring), fill=(*CAMERA, 255))

    phone = phone.resize((geom.canvas_w, geom.canvas_h), Image.LANCZOS)
    hole = hole.resize((geom.canvas_w, geom.canvas_h), Image.LANCZOS)

    base = _background(geom.canvas_w, geom.canvas_h, spec.background).convert("RGBA")
    if spec.background != "black":
        # A faint contact shadow, only where there is a surface to cast it on.
        shadow = Image.new("L", (geom.canvas_w, geom.canvas_h), 0)
        ImageDraw.Draw(shadow).rounded_rectangle(
            (geom.body_x, geom.body_y + 14, geom.body_x + geom.body_w, geom.body_y + geom.body_h + 14),
            radius=geom.radius, fill=110 if spec.background in SURFACES else 150,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(28))
        dark = Image.new("RGBA", base.size, (0, 0, 0, 255))
        base = Image.composite(dark, base, shadow)
    frame = Image.alpha_composite(base, phone)
    frame.putalpha(ImageChops.invert(hole))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(path)

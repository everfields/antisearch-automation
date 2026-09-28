"""Mockup 3, "computation": the wait between Enter and the verdict, shown as a huge model thinking.

One deterministic template: every value comes from the clip's own timeline (the length of the
wait) and a seed from the typed input. Nothing is authored per verdict. Screen space, over the
monolith's zoom:

1. tokens: the typed input splits into token boxes, each with an id, which drop into the model.
2. training: a faint loss curve descends behind everything (what made the model possible).
3. the forward pass: the camera flies through a deep stack of layers, each a grid of weights
   receding to a vanishing point where the caret waits. A pulse of activation travels through
   them, lighting weights and the connections between layers. Lowercase instrument labels.
4. collapse: everything rushes into one cold point of light, exactly where the verdict appears.
   The layer is zero from the verdict frame on: the verdict itself is untouched.

Cold palette on black (ice white and steel blue), thin lines, no colour noise, and no chat.
Labels are generic ("weights", "attention", "forward pass"), not a spec of the production model.
"""

from __future__ import annotations

import hashlib
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ICE = (214, 226, 255)
STEEL = (96, 116, 150)
LABEL = (132, 142, 162)
LAYERS = 30
GRID_X, GRID_Y = 26, 14  # even: no row sits exactly on the horizon line
SPACING = 0.3  # layer spacing (world units)
AHEAD = 1.3  # the activation front runs this far ahead of the camera


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def tokens_of(text: str) -> list[str]:
    """A visual tokenization: words, long words in chunks of about four letters."""
    out: list[str] = []
    for word in text.split():
        while len(word) > 5:
            out.append(word[:4])
            word = word[4:]
        out.append(word)
    return out


class Computation:
    """`layer = Computation(mono)(i)`: an RGB light layer to add over frame i, or None."""

    def __init__(self, mono, *, category: str, font_path: str):
        self.W, self.H = mono.W, mono.H
        self.fps = mono.fps
        self.start, self.end = mono.submit_i, mono.verdict_i
        seed = int.from_bytes(hashlib.sha256(f"computation|{category}".encode()).digest()[:8], "big")
        rng = random.Random(seed)
        self.tokens = [(t, int(hashlib.sha256(t.encode()).hexdigest()[:5], 16) % 100000) for t in tokens_of(category)]
        self.weights = [[[rng.random() ** 2 for _ in range(GRID_Y)] for _ in range(GRID_X)] for _ in range(LAYERS)]
        self.links = [[(gx, gy, max(0, min(GRID_X - 1, gx + rng.choice((-1, 0, 1)))),
                        max(0, min(GRID_Y - 1, gy + rng.choice((-1, 0, 1)))))
                       for gx, gy in {(rng.randrange(GRID_X), rng.randrange(GRID_Y)) for _ in range(90)}]
                      for _ in range(LAYERS)]
        self.micro = [((rng.random() - 0.5) * 2.2, (rng.random() - 0.5) * 1.3) for _ in range(2600)]
        self.loss = [math.exp(-3.2 * x / 60) * (0.85 + 0.3 * rng.random()) for x in range(61)]
        self.hw, self.hh = self.W // 2, self.H // 2
        self.label = ImageFont.truetype(font_path, 26)
        self.token_font = ImageFont.truetype(font_path, 44)
        self.id_font = ImageFont.truetype(font_path, 20)
        flare = Image.new("L", (self.hw, self.hh), 0)
        d = ImageDraw.Draw(flare)
        cx, cy = self.hw / 2, self.hh / 2
        for r in range(160, 0, -4):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=round(255 * (1 - r / 160) ** 3))
        self.flare = flare.filter(ImageFilter.GaussianBlur(6))

    def __call__(self, i: int) -> Image.Image | None:
        if not self.start <= i < self.end:
            return None
        p = (i - self.start) / max(1, self.end - self.start)
        env = _ease(p / 0.08) * (1 - _ease((p - 0.94) / 0.06))  # zero on the verdict frame
        if env <= 0:
            return None
        low = Image.new("RGB", (self.hw, self.hh))
        d = ImageDraw.Draw(low)
        self._field(d, p)
        glow = low.filter(ImageFilter.GaussianBlur(3))
        low = ImageChops.add(low, glow)
        if p > 0.78:  # the collapse: one point of light where the verdict will be
            q = _ease((p - 0.78) / 0.16) * (1 - _ease((p - 0.93) / 0.07))
            low = ImageChops.add(low, Image.merge("RGB", [self.flare.point(lambda v, q=q, c=c: round(v * q * c / 255))
                                                          for c in ICE]))
        layer = low.resize((self.W, self.H), Image.BICUBIC)
        hud = Image.new("RGB", (self.W, self.H))
        self._hud(ImageDraw.Draw(hud), p)
        layer = ImageChops.add(layer, hud)
        if env < 1:
            layer = Image.blend(Image.new("RGB", layer.size), layer, env)
        return layer

    def _field(self, d: ImageDraw.ImageDraw, p: float) -> None:
        cx, cy, f = self.hw / 2, self.hh / 2, self.hw * 0.9
        depth = LAYERS * SPACING
        fly = (depth - AHEAD - 1.2) * _ease((p - 0.04) / 0.8) + 30.0 * max(0.0, p - 0.8) ** 2  # through, then the rush
        front = fly + AHEAD  # the activation front, always just ahead of the camera
        for z_far in (depth + 0.6, depth + 1.4):  # the far micro-field: scale beyond counting
            z = z_far - fly
            if z > 0.3:
                v = round(34 * min(1.0, 3.0 / z))
                d.point([(cx + f * x / z, cy + f * y / z) for x, y in self.micro], fill=(round(v * 0.8), round(v * 0.9), v))
        pts: list[dict[tuple[int, int], tuple[float, float, float]]] = []
        for k in range(LAYERS):
            zw = 1.0 + k * SPACING
            z = zw - fly
            if z < 0.22:
                pts.append({})
                continue
            fog = max(0.0, 1 - (z - 0.22) / depth) ** 1.3
            act_layer = math.exp(-((zw - front) / 0.42) ** 2)
            r = min(2.2, max(0.45, 1.1 / z))
            row: dict[tuple[int, int], tuple[float, float, float]] = {}
            dim: list[tuple[float, float]] = []
            for gx in range(GRID_X):
                x = (gx / (GRID_X - 1) - 0.5) * 2.2
                sx = cx + f * x / z
                if not -6 < sx < self.hw + 6:
                    continue
                for gy in range(GRID_Y):
                    y = (gy / (GRID_Y - 1) - 0.5) * 1.3
                    sy = cy + f * y / z
                    if not -6 < sy < self.hh + 6:
                        continue
                    lit = act_layer * self.weights[k][gx][gy]
                    row[(gx, gy)] = (sx, sy, lit)
                    if lit < 0.08:
                        dim.append((sx, sy))
                        continue
                    a = min(1.0, fog * (0.3 + 1.6 * lit))
                    col = tuple(round(c * a) for c in ICE)
                    rr = r * (1 + 0.8 * lit)
                    d.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], fill=col)
            base = tuple(round(c * fog * 0.5) for c in STEEL)
            if r < 0.8:
                d.point(dim, fill=base)
            else:
                for sx, sy in dim:
                    d.ellipse([sx - r * 0.7, sy - r * 0.7, sx + r * 0.7, sy + r * 0.7], fill=base)
            pts.append(row)
        for k in range(LAYERS - 1):  # the weights between layers, lit around the activation front
            a_row, b_row = pts[k], pts[k + 1]
            if not a_row or not b_row:
                continue
            strength = math.exp(-((1.0 + k * SPACING - front) / 0.5) ** 2)
            if strength < 0.06:
                continue
            for ax, ay, bx, by in self.links[k]:
                a, b = a_row.get((ax, ay)), b_row.get((bx, by))
                if a is None or b is None:
                    continue
                v = round(190 * strength * (0.35 + max(a[2], b[2])))
                if v > 8:
                    d.line([a[0], a[1], b[0], b[1]], fill=(round(v * 0.72), round(v * 0.84), min(255, v)), width=1)
        if p < 0.5:  # training: a faint loss curve, descending, behind the pass
            show = _ease(p / 0.32)
            a = 0.55 * (1 - _ease((p - 0.32) / 0.18))
            n = max(2, round(len(self.loss) * show))
            x0, x1, y0, y1 = self.hw * 0.1, self.hw * 0.9, self.hh * 0.62, self.hh * 0.86
            line = [(x0 + (x1 - x0) * j / (len(self.loss) - 1), y0 + (y1 - y0) * (1 - self.loss[j])) for j in range(n)]
            d.line(line, fill=tuple(round(c * a) for c in STEEL), width=1)
        if p < 0.3:  # the tokens' beams into the model
            q = _ease(p / 0.3)
            beam = round(90 * (1 - q) * min(1.0, p / 0.06))
            n = len(self.tokens)
            for j in range(n):
                tx = cx + (j - (n - 1) / 2) * self.hw * 0.16
                d.line([(tx, cy - self.hh * 0.13 + self.hh * 0.09 * q * q), (cx, cy)],
                       fill=(round(beam * 0.75), round(beam * 0.85), beam), width=1)

    def _hud(self, d: ImageDraw.ImageDraw, p: float) -> None:
        W, H = self.W, self.H
        a = _ease(p / 0.12)
        col = tuple(round(c * a) for c in LABEL)
        layer = 1 + round(95 * _ease((p - 0.12) / 0.7))
        d.text((72, 150), "forward pass", font=self.label, fill=col)
        d.text((72, 186), f"layer {layer:02d}", font=self.label, fill=col)
        right = "attention"
        d.text((W - 72 - d.textlength(right, font=self.label), 150), right, font=self.label, fill=col)
        d.text((72, H - 210), "weights", font=self.label, fill=col)
        if p < 0.5:
            ta = 1 - _ease((p - 0.32) / 0.18)
            d.text((W - 72 - d.textlength("training", font=self.label), H - 210), "training", font=self.label,
                   fill=tuple(round(c * a * ta) for c in LABEL))
        bar = 72 + (W - 144) * _ease(p / 0.94)  # a hairline of progress
        d.line([(72, H - 160), (bar, H - 160)], fill=tuple(round(c * a * 0.8) for c in STEEL), width=2)
        if p < 0.32:  # tokens: the input, split, dropping into the model
            q = _ease(p / 0.32)
            fade = 1 - _ease((p - 0.18) / 0.14)
            widths = [d.textlength(t, font=self.token_font) + 36 for t, _ in self.tokens]
            x = W / 2 - (sum(widths) + 14 * (len(widths) - 1)) / 2
            y = H / 2 - 250 + 180 * q * q
            for (t, tid), w in zip(self.tokens, widths):
                c = tuple(round(v * fade * min(1.0, p / 0.05)) for v in ICE)
                d.rounded_rectangle([x, y, x + w, y + 64], radius=8, outline=tuple(round(v * 0.5) for v in c), width=2)
                d.text((x + 18, y + 6), t, font=self.token_font, fill=c)
                d.text((x + 4, y - 26), f"{tid:05d}", font=self.id_font, fill=tuple(round(v * 0.55) for v in c))
                x += w + 14

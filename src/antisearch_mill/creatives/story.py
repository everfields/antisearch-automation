"""The Instagram Stories card: one fixed 5 s template, the verdict as the hero.

1080x1920, cold monochrome on near-black. The input sits small in stone grey; a hairline
fills while the model "thinks"; the verdict lands in large lowercase type exactly as the
oracle returned it, with one cold bloom behind it; `antisearch.ai` stays on screen from the
first frame. Everything sits inside Instagram's Stories safe area (the top 250 px and the
bottom 340 px carry the app's own bars). Scored by `score.template_score`, trimmed to the card.
Same input, same bytes: nothing is drawn at random except from seeds of the input and verdict.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ..render import Layout, RenderError
from .monolith import _background, _encode_tail, _font, _meta, _tracked, _vignette
from .score import _rng, template_score

INK = (236, 238, 242)
STONE = (128, 132, 140)
MARK_GREY = (160, 165, 174)
STEEL = (96, 116, 150)
ICE = (214, 226, 255)
MARK = "antisearch.ai"
TOTAL_S = 5.0
INPUT_IN_S = (0.10, 0.45)
THINK_S = (0.45, 1.45)  # the hairline fills: the wait, compressed
VERDICT_S = 1.45
RISE_S = 0.5
SAFE_TOP, SAFE_BOTTOM = 250, 340


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _fit(font_path: str, text: str, start: int, max_w: float, tracking: float) -> ImageFont.FreeTypeFont:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    size = start
    while size > 56 and probe.textlength(text, font=_font(font_path, size)) + tracking * len(text) > max_w:
        size -= 4
    return _font(font_path, size)


def _text_layer(w: int, h: int, y: float, text: str, font, fill, tracking: float) -> Image.Image:
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _tracked(ImageDraw.Draw(layer), w / 2, y, text, font, (*fill, 255), tracking)
    return layer


def _with_alpha(layer: Image.Image, a: float) -> Image.Image:
    if a >= 1:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda v: round(v * a)))
    return out


class StoryCard:
    """Precomputed layers; `frame(i)` is frame i of the card."""

    def __init__(self, category: str, verdict: str, *, font_path: str, layout: Layout):
        W, H, self.fps = layout.width, layout.height, layout.fps
        self.W, self.H = W, H
        self.total = round(TOTAL_S * self.fps)
        self.verdict_i = round(VERDICT_S * self.fps)
        bg = _background(W, H)
        base = ImageChops.multiply(bg, _vignette(W, H)).convert("RGBA")
        mark = ImageFont.truetype(font_path, 42)
        base.alpha_composite(_text_layer(W, H, H - SAFE_BOTTOM - 160, MARK, mark, MARK_GREY, 6))
        self.base = base
        self.input_y = H * 0.40
        self.verdict_y = H * 0.40 + 150
        self.input = _text_layer(W, H, self.input_y, category, _fit(font_path, category, 52, W * 0.8, 6), STONE, 6)
        big = _fit(font_path, verdict, 200, W * 0.84, 5)
        self.verdict = _text_layer(W, H, self.verdict_y, verdict, big, INK, 5)
        box = self.verdict.getbbox() or (0, 0, W, H)
        bloom = Image.new("L", (W, H), 0)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        rx, ry = max(160, (box[2] - box[0]) * 0.62), max(120, (box[3] - box[1]) * 1.6)
        ImageDraw.Draw(bloom).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
        self.bloom = bloom.filter(ImageFilter.GaussianBlur(90))
        self.line_y = round(self.input_y + 96)
        self.line_w = round(W * 0.34)
        rng = _rng(f"story|{category}|{verdict}")
        self.grains = [Image.merge("RGB", [Image.effect_noise((W // 2, H // 2), 2.4)] * 3).resize((W, H), Image.BICUBIC)
                       for _ in range(3)]
        self.phase = rng.random()

    def frame(self, i: int) -> Image.Image:
        W, H = self.W, self.H
        t = i / self.fps
        frame = self.base.copy()
        a_in = _ease((t - INPUT_IN_S[0]) / (INPUT_IN_S[1] - INPUT_IN_S[0]))
        if a_in > 0:
            frame.alpha_composite(_with_alpha(self.input, a_in))
        d = ImageDraw.Draw(frame)
        x0 = (W - self.line_w) / 2
        think = (t - THINK_S[0]) / (THINK_S[1] - THINK_S[0])
        if 0 <= think < 1.25:
            p = _ease(min(1.0, think))
            fade = 1 - _ease((think - 1.0) / 0.25) if think > 1 else 1.0
            d.line([(x0, self.line_y), (x0 + self.line_w, self.line_y)],
                   fill=(*tuple(round(c * 0.35 * fade) for c in STEEL), 255), width=2)
            head = 0.55 + 0.45 * math.sin(math.pi * 2 * (t * 1.6 + self.phase))
            d.line([(x0, self.line_y), (x0 + self.line_w * p, self.line_y)],
                   fill=(*tuple(round(c * fade * (0.7 + 0.3 * head)) for c in ICE), 255), width=2)
        dv = t - VERDICT_S
        if dv >= 0:
            glow = 0.07 + 0.11 * math.exp(-dv / 0.55)
            lit = Image.merge("RGB", [self.bloom.point(lambda v, c=c: round(v * glow * c / 255)) for c in ICE])
            frame = Image.alpha_composite(frame, ImageChops.add(frame.convert("RGB"), lit).convert("RGBA"))
            rise = _ease_out(dv / RISE_S)
            layer = _with_alpha(self.verdict, rise)
            shift = round(26 * (1 - rise))
            if shift:
                moved = Image.new("RGBA", layer.size, (0, 0, 0, 0))
                moved.alpha_composite(layer, (0, shift))
                layer = moved
            frame.alpha_composite(layer)
        rgb = frame.convert("RGB")
        return ImageChops.add(rgb, self.grains[(i // 2) % len(self.grains)], 1.0, -128)


def render_story(category: str, verdict: str, out: Path, *, font_path: str, layout: Layout | None = None,
                 metadata: dict[str, str] | None = None) -> None:
    lay = layout or Layout()
    card = StoryCard(category, verdict, font_path=font_path, layout=lay)
    total_s = card.total / card.fps
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="story-") as td:
        wav = Path(td) / "story.wav"
        template_score(f"story|{category}|{verdict}", total_s, 0.05, THINK_S[0], VERDICT_S).write(wav)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{lay.width}x{lay.height}", "-r", str(lay.fps), "-i", "-",
             "-i", str(wav), "-filter_complex", "[1:a]loudnorm=I=-17:TP=-1.5:LRA=11,aresample=44100[a]",
             "-map", "0:v", "-map", "[a]", "-t", f"{total_s:.4f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "6M", "-bufsize", "12M",
             "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1", "-g", str(lay.fps), "-bf", "2",
             *_meta(metadata), *_encode_tail(out)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for i in range(card.total):
                enc.stdin.write(card.frame(i).tobytes())
        finally:
            enc.stdin.close()
            err = enc.stderr.read().decode(errors="replace")
            code = enc.wait()
    if code != 0:
        raise RenderError(f"ffmpeg (story encode) failed:\n{err[-1500:]}")

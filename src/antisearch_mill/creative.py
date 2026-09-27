"""Alternative creatives, behind `PUBLISHER_CREATIVE` (founder, 2026-09-27: start from zero,
be ready to change the creative completely to find what ignites reach).

- `classic` (default): the clip exactly as it is. Nothing here runs.
- `music_classical`: the classic clip, plus a soft felt-piano bed that resolves on the verdict.
- `music_upbeat`: the classic clip, plus a 120 bpm bed whose drop lands on the verdict.
- `motion`: a 10 s composition around the same typing-to-verdict moment. A cold monolith rises
  out of a hairline of light; the app screen plays inside it; a slow light sweep and a breath
  of push-in on the verdict; then the monolith recedes and the verdict stands alone in large
  lowercase type, the input small above it; fade to black. No chat, one verdict, no share card.

Every bed is original synthesis (`music.py`), so there is nothing to license. Music is muxed
only where the clip carries audio (Instagram and TikTok); elsewhere the track stays silent.
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .music import classical_bed, motion_bed, upbeat_bed
from .render import ClipInfo, Layout, RenderError, probe
from .timeline import Timeline

CLASSIC = "classic"
CREATIVES = (CLASSIC, "music_classical", "music_upbeat", "motion")

INK = (232, 229, 224)
STONE = (122, 118, 112)
SCREEN_BG = (11, 11, 11)
INTRO_S = 1.2
OUTRO_CROSS_S = 0.8
OUTRO_HOLD_S = 2.2
FADE_S = 0.5


def clip_creative(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CREATIVE`: classic (default), music_classical, music_upbeat, or motion."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CREATIVE") or "").strip().lower() or CLASSIC
    if raw not in CREATIVES:
        raise ValueError(f"PUBLISHER_CREATIVE={raw!r}; use {', '.join(CREATIVES)}")
    return raw


def _run(cmd: list[str], stdin=None) -> None:
    proc = subprocess.run(cmd, capture_output=True, input=stdin)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.decode(errors="replace").strip().splitlines()[-12:])
        raise RenderError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def _encode_tail(out: Path) -> list[str]:
    return ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart", str(out)]


def apply_creative(creative: str, clip: Path, timeline: Timeline, *, category: str, verdict: str, font_path: str,
                   layout: Layout, screen: tuple[int, int, int, int] | None, audio: bool,
                   metadata: Mapping[str, str]) -> ClipInfo:
    """Rewrite `clip` (the classic master) in place as `creative`. `screen` is the phone screen
    (x, y, w, h) inside the frame, or None for a full-frame clip."""
    if creative == CLASSIC:
        return probe(clip)
    tmp = clip.with_suffix(".creative.mp4")
    meta = [a for k, v in metadata.items() for a in ("-metadata", f"{k}={v}")]
    fps = timeline.fps
    total = timeline.total_frames / fps
    submit, verdict_s = timeline.submit_frame / fps, timeline.verdict_frame / fps
    seed = f"{category}|{verdict}"
    with tempfile.TemporaryDirectory(prefix="creative-") as td:
        work = Path(td)
        if creative in ("music_classical", "music_upbeat"):
            if not audio:
                return probe(clip)
            make = classical_bed if creative == "music_classical" else upbeat_bed
            wav = work / "bed.wav"
            make(seed, total, submit, verdict_s).write(wav)
            # soft: a quiet bed under the keys; upbeat: TikTok-level, the keys still on top
            weight, lufs = ("0.55", "-20") if creative == "music_classical" else ("0.9", "-14")
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip), "-i", str(wav),
                  "-filter_complex", f"[0:a][1:a]amix=inputs=2:normalize=0:weights='1 {weight}':duration=first,"
                                     f"loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=44100[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy", *meta, *_encode_tail(tmp)])
        elif creative == "motion":
            _motion(clip, timeline, tmp, work, category=category, verdict=verdict, font_path=font_path,
                    layout=layout, screen=screen, audio=audio, meta=meta)
        else:
            raise ValueError(f"unknown creative {creative!r}")
    tmp.replace(clip)
    return probe(clip)


# --- motion -------------------------------------------------------------------------

def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


@dataclass(frozen=True)
class MotionPlan:
    fps: int
    intro: int  # frames before the app screen starts
    classic: int  # frames of the classic clip
    cross: int  # monolith recedes, verdict rises
    hold: int
    fade: int

    @property
    def total(self) -> int:
        return self.intro + self.classic + self.cross + self.hold

    @property
    def outro_start(self) -> int:
        return self.intro + self.classic

    def verdict_at(self, timeline: Timeline) -> int:
        return self.intro + timeline.verdict_frame


def motion_plan(timeline: Timeline) -> MotionPlan:
    f = timeline.fps
    return MotionPlan(f, round(INTRO_S * f), timeline.total_frames, round(OUTRO_CROSS_S * f), round(OUTRO_HOLD_S * f),
                      round(FADE_S * f))


def _font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    light = Path(font_path).with_name(Path(font_path).name.replace("Regular", "Light"))
    return ImageFont.truetype(str(light if light.is_file() else font_path), size)


def _tracked(draw: ImageDraw.ImageDraw, center_x: float, y: float, text: str, font, fill, tracking: float) -> None:
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x = center_x - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


def _background(w: int, h: int) -> Image.Image:
    top, bottom = (9, 10, 12), (20, 21, 24)
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        p = y / (h - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * p) for a, b in zip(top, bottom)))
    return grad.resize((w, h))


def _vignette(w: int, h: int) -> Image.Image:
    small = Image.new("L", (w // 8, h // 8))
    cx, cy = small.width / 2, small.height * 0.46
    for y in range(small.height):
        for x in range(small.width):
            d = math.hypot((x - cx) / (small.width * 0.62), (y - cy) / (small.height * 0.62))
            small.putpixel((x, y), round(255 * (1 - 0.55 * min(1.0, d) ** 2.2)))
    return small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6)).convert("RGB")


def _sweep_band(w: int, h: int) -> Image.Image:
    """A soft diagonal band of light, long enough that its ends never cross the slab."""
    length = int(math.hypot(w, h) * 2.2)
    band = Image.new("L", (length, 320), 0)
    d = ImageDraw.Draw(band)
    for y in range(320):
        a = math.exp(-((y - 160) / 62) ** 2) * 30
        d.line([(0, y), (length, y)], fill=round(a))
    band = band.rotate(-24, expand=True, resample=Image.BICUBIC)
    white = Image.new("RGBA", band.size, (235, 240, 248, 0))
    white.putalpha(band)
    return white


def _slab_mask(w: int, h: int, radius: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return m


class _Monolith:
    """Precomputed layers for the motion piece, and the frame at index i."""

    def __init__(self, plan: MotionPlan, timeline: Timeline, *, category: str, verdict: str, font_path: str,
                 layout: Layout, screen: tuple[int, int, int, int] | None):
        self.plan, self.fps = plan, timeline.fps
        self.W, self.H = layout.width, layout.height
        self.screen = screen or (0, 0, self.W, self.H)
        sx, sy, sw, sh = self.screen
        self.base_h = round(self.H * 0.70)
        self.base_w = round(self.base_h * sw / sh)
        self.cy = self.H * 0.47
        self.bg = _background(self.W, self.H)
        self.vig = _vignette(self.W, self.H)
        self.band = _sweep_band(self.base_w, self.base_h)
        # Fine grain, drawn at half size and changing every other frame: texture without a
        # bitrate explosion (per-frame full-resolution noise made a 10 s clip ~100 MB).
        self.grains = [Image.merge("RGB", [Image.effect_noise((self.W // 2, self.H // 2), 2.6)] * 3)
                       .resize((self.W, self.H), Image.BICUBIC) for _ in range(4)]
        shadow = Image.new("L", (self.W, self.H), 0)
        ImageDraw.Draw(shadow).ellipse([self.W / 2 - self.base_w * 0.6, self.cy + self.base_h / 2 - 18,
                                        self.W / 2 + self.base_w * 0.6, self.cy + self.base_h / 2 + 46], fill=150)
        self.shadow = shadow.filter(ImageFilter.GaussianBlur(28))
        self.category, self.verdict = category, verdict
        self.small = _font(font_path, 44)
        size, probe_draw = 150, ImageDraw.Draw(Image.new("RGB", (8, 8)))
        while size > 60 and probe_draw.textlength(verdict, font=_font(font_path, size)) + 5 * len(verdict) > self.W * 0.82:
            size -= 6
        self.big = _font(font_path, size)
        self.verdict_i = plan.verdict_at(timeline)
        self.black = Image.new("RGB", (self.W, self.H))
        self.lift = Image.new("RGB", (self.W, self.H), (26, 28, 32))

    def frame(self, i: int, classic: Image.Image) -> Image.Image:
        W, H, plan = self.W, self.H, self.plan
        sx, sy, sw, sh = self.screen
        face = classic.crop((sx, sy, sx + sw, sy + sh))
        ImageDraw.Draw(face).rectangle([sw * 0.44, 0, sw * 0.56, sh * 0.045], fill=SCREEN_BG)  # no camera dot
        t = i / self.fps
        dv = (i - self.verdict_i) / self.fps
        push = 1.0 + 0.045 * _ease(i / plan.total)
        if dv >= 0:
            push += 0.014 * math.exp(-dv / 0.6) * math.sin(min(math.pi, dv * math.pi / 0.9))
        w, h = round(self.base_w * push), round(self.base_h * push)
        radius = round(10 * push)
        reveal = _ease_out(t / INTRO_S)
        frame = self.bg.copy()
        out_i = i - plan.outro_start
        recede = _ease(out_i / plan.cross) if out_i >= 0 else 0.0
        frame.paste((0, 0, 0), mask=self.shadow.point(lambda v: round(v * reveal * (1 - recede))))
        slab = face.resize((w, h), Image.BICUBIC).convert("RGBA")
        if 0 <= dv < 1.3:  # a slow light sweep over the verdict
            p = _ease(dv / 1.3)
            bw, bh = self.band.size
            ox = round(w / 2 - bw / 2)
            oy = round(-bh / 2 - h * 0.1 + p * (h * 1.2))
            layer = Image.new("RGBA", slab.size, (0, 0, 0, 0))
            layer.alpha_composite(self.band, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy), bw, bh))
            slab.alpha_composite(layer)
        glow = 44 + (round(40 * math.exp(-dv / 0.7)) if dv >= 0 else 0)
        ImageDraw.Draw(slab).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(glow, glow, glow + 6),
                                               width=2)
        mask = _slab_mask(w, h, radius)
        if t < INTRO_S:  # a hairline of light opens into the slab
            opening = _ease_out(t / INTRO_S)
            wcut = max(2, round(w * opening))
            cut = Image.new("L", (w, h), 0)
            ImageDraw.Draw(cut).rectangle([(w - wcut) / 2, 0, (w + wcut) / 2, h], fill=255)
            mask = ImageChops.multiply(mask, cut)
            slab = Image.blend(Image.new("RGBA", slab.size, (8, 8, 9, 255)), slab, _ease((t - 0.5) / 0.7))
            if t < INTRO_S * 0.3:
                edge = round(255 * (1 - t / (INTRO_S * 0.3)))
                ImageDraw.Draw(slab).line([(w / 2, 0), (w / 2, h)], fill=(210, 220, 235, edge), width=2)
        slab_left = 1 - _ease(min(1.0, recede * 2))  # the slab is gone before the type arrives
        if recede > 0:
            mask = mask.point(lambda v: round(v * slab_left))
        frame.paste(slab.convert("RGB"), (round(W / 2 - w / 2), round(self.cy - h / 2)), mask)
        if dv >= 0:  # the room lifts a little when the verdict lands
            frame = Image.blend(frame, ImageChops.screen(frame, self.lift), 0.06 * math.exp(-dv / 1.2) * slab_left)
        type_in = _ease((recede - 0.4) / 0.6)
        if type_in > 0:
            txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(txt)
            rise = round(30 * (1 - type_in))
            alpha = round(255 * type_in)
            _tracked(d, W / 2, H * 0.44 - 150 + rise, self.category, self.small, (*STONE, alpha), 6)
            _tracked(d, W / 2, H * 0.44 - 40 + rise, self.verdict, self.big, (*INK, alpha), 5)
            frame = Image.alpha_composite(frame.convert("RGBA"), txt).convert("RGB")
        frame = ImageChops.multiply(frame, self.vig)
        frame = ImageChops.add(frame, self.grains[(i // 2) % len(self.grains)], 1.0, -128)
        left = plan.total - i
        if left <= plan.fade:
            frame = Image.blend(self.black, frame, _ease((left - 1) / plan.fade))
        return frame


def _motion(clip: Path, timeline: Timeline, out: Path, work: Path, *, category: str, verdict: str, font_path: str,
            layout: Layout, screen: tuple[int, int, int, int] | None, audio: bool, meta: list[str]) -> None:
    W, H, fps = layout.width, layout.height, timeline.fps
    plan = motion_plan(timeline)
    mono = _Monolith(plan, timeline, category=category, verdict=verdict, font_path=font_path, layout=layout,
                     screen=screen)
    total_s = plan.total / fps
    inputs = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if audio:
        wav = work / "motion.wav"
        motion_bed(f"{category}|{verdict}", total_s, INTRO_S, mono.verdict_i / fps, plan.outro_start / fps).write(wav)
        delay = round(INTRO_S * 1000)
        inputs += ["-i", str(clip), "-i", str(wav)]
        amap = ["-filter_complex", f"[1:a]adelay={delay}|{delay},apad[k];[k][2:a]amix=inputs=2:normalize=0:"
                                   f"weights='1 0.8':duration=shortest,atrim=0:{total_s:.3f},"
                                   "loudnorm=I=-18:TP=-2:LRA=11,aresample=44100[a]", "-map", "0:v", "-map", "[a]"]
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = ["-map", "0:v", "-map", "1:a"]
    enc = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, *amap,
                            "-t", f"{total_s:.4f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                            "-maxrate", "6M", "-bufsize", "12M",
                            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1", "-g", str(fps),
                            "-bf", "2", *meta, *_encode_tail(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    dec = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(clip), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = W * H * 3
    cur = None
    read = 0
    try:
        for i in range(plan.total):
            j = min(max(0, i - plan.intro), plan.classic - 1)
            while read <= j:
                raw = dec.stdout.read(size)
                if len(raw) < size:
                    break
                cur = Image.frombytes("RGB", (W, H), raw)
                read += 1
            if cur is None:
                raise RenderError("motion: the classic clip has no frames")
            enc.stdin.write(mono.frame(i, cur).tobytes())
    finally:
        dec.stdout.close()
        dec.wait()
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
    if code != 0:
        raise RenderError(f"ffmpeg (motion encode) failed:\n{err[-1500:]}")

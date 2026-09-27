"""Alternative creatives, behind `PUBLISHER_CREATIVE` (founder, 2026-09-27: start from zero,
be ready to change the creative completely to find what ignites reach).

- `classic` (default): the clip exactly as it is. Nothing here runs.
- `music_classical`: the classic clip, plus a soft felt-piano bed that resolves on the verdict.
- `music_upbeat`: the classic clip, plus a 120 bpm bed whose drop lands on the verdict.
- `motion`: an 8 s cinematic piece around the same moment (docs/CREATIVE_DIRECTION.md). Motion
  from frame 0: the monolith's rim traces in light while the camera is already close on the
  input line; through the wait the camera pushes in faster and the room darkens (held breath);
  on the verdict the camera releases to reveal the monolith, one soft light sweep, the rim
  blooms (exhale); the monolith dissolves and the verdict stands alone in large lowercase type,
  the input small above; it sinks back to the darkness of frame 0, so a loop joins. Scored by
  `music.monolith_score`. No chat, one verdict, no share card.

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

from .music import _rng, classical_bed, monolith_score, upbeat_bed
from .render import ClipInfo, Layout, RenderError, probe
from .timeline import Timeline

CLASSIC = "classic"
CREATIVES = (CLASSIC, "music_classical", "music_upbeat", "motion")

INK = (232, 229, 224)
STONE = (122, 118, 112)
SCREEN_BG = (11, 11, 11)
INTRO_S = 0.4  # motion from frame 0: the typing starts almost at once
OUTRO_CROSS_S = 0.5
OUTRO_HOLD_S = 1.9  # includes the sink back to frame 0
FADE_S = 0.6
INPUT_LINE = 0.29  # the typed line, as a fraction of the screen height (measured)
VERDICT_LINE = 0.38  # where the caret waits and the verdict appears (measured)
REFRAME_S = 0.35  # after Enter the camera re-frames from the input line to the verdict line
DIVE_S = 0.9  # frame 0 shows the whole monolith; the camera dives onto the input line by then
CAMERA_WIDE = 1.1
CAMERA_CLOSE, CAMERA_PEAK = 1.9, 2.05  # close enough that the typed words read in a muted feed


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
                   metadata: Mapping[str, str], source: Path | None = None,
                   source_screen: tuple[int, int, int, int] | None = None) -> ClipInfo:
    """Rewrite `clip` (the classic master) in place as `creative`. `screen` is the phone screen
    (x, y, w, h) inside the frame, or None for a full-frame clip. `motion` can take a sharper
    `source` render of the same timeline (e.g. at 2x) and its `source_screen`, for close-ups."""
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
                    layout=layout, screen=source_screen if source else screen, audio=audio, meta=meta,
                    source=source)
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


def _ease_out_expo(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


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


def _sweep_band(w: int, h: int, angle: float = -24.0) -> Image.Image:
    """A soft diagonal band of light, long enough that its ends never cross the slab."""
    length = int(math.hypot(w, h) * 2.2)
    band = Image.new("L", (length, 320), 0)
    d = ImageDraw.Draw(band)
    for y in range(320):
        a = math.exp(-((y - 160) / 62) ** 2) * 30
        d.line([(0, y), (length, y)], fill=round(a))
    band = band.rotate(angle, expand=True, resample=Image.BICUBIC)
    white = Image.new("RGBA", band.size, (235, 240, 248, 0))
    white.putalpha(band)
    return white


def _slab_mask(w: int, h: int, radius: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return m


class _Monolith:
    """Precomputed layers for the motion piece, and the frame at index i.

    The camera works in scene space: the slab is drawn at the camera's zoom straight from the
    (sharper) source, so a close-up never upscales text; the background stays put (depth).
    """

    def __init__(self, plan: MotionPlan, timeline: Timeline, *, category: str, verdict: str, font_path: str,
                 layout: Layout, screen: tuple[int, int, int, int], source_size: tuple[int, int]):
        self.plan, self.fps = plan, timeline.fps
        self.W, self.H = layout.width, layout.height
        self.screen, self.source_size = screen, source_size
        sx, sy, sw, sh = screen
        self.base_h = round(self.H * 0.72)
        self.base_w = round(self.base_h * sw / sh)
        rng = _rng(f"camera|{category}|{verdict}")  # per-input variation, one system
        self.drift = 18 * (1 if rng.random() < 0.5 else -1)
        self.bg = _background(self.W, self.H)
        self.vig = _vignette(self.W, self.H)
        self.band = _sweep_band(self.base_w * 2, self.base_h * 2, -18 - 12 * rng.random())
        self.grains = [Image.merge("RGB", [Image.effect_noise((self.W // 2, self.H // 2), 2.6)] * 3)
                       .resize((self.W, self.H), Image.BICUBIC) for _ in range(4)]  # dither, not a 100 MB clip
        sh_w, sh_h = round(self.base_w * 1.4), 140
        shadow = Image.new("L", (sh_w, sh_h), 0)
        ImageDraw.Draw(shadow).ellipse([sh_w * 0.07, 40, sh_w * 0.93, 100], fill=150)
        self.shadow = shadow.filter(ImageFilter.GaussianBlur(24))
        fade = Image.new("L", (1, 256))
        for y in range(256):
            fade.putpixel((0, y), round(30 * (1 - y / 255) ** 2))
        self.reflect_fade = fade
        self.category, self.verdict = category, verdict
        self.small = _font(font_path, 44)
        size, probe_draw = 150, ImageDraw.Draw(Image.new("RGB", (8, 8)))
        while size > 60 and probe_draw.textlength(verdict, font=_font(font_path, size)) + 5 * len(verdict) > self.W * 0.82:
            size -= 6
        self.big = _font(font_path, size)
        self.submit_i = plan.intro + timeline.submit_frame
        self.verdict_i = plan.verdict_at(timeline)
        self.black = Image.new("RGB", (self.W, self.H))
        self.lift = Image.new("RGB", (self.W, self.H), (26, 28, 32))

    def camera(self, i: int) -> tuple[float, float]:
        """(zoom, focus): the zoom, and which fraction of the slab's height sits at the frame's centre.

        Wide on the monolith at frame 0, diving onto the input line; after Enter re-framing onto
        the verdict line and pushing in faster (held breath); on the verdict released to the
        whole slab."""
        plan = self.plan
        dive_end = round(DIVE_S * self.fps)
        if i < min(dive_end, self.submit_i):  # the hook
            p = _ease(i / dive_end)
            return CAMERA_WIDE + (CAMERA_CLOSE - CAMERA_WIDE) * p, 0.5 + (INPUT_LINE - 0.5) * p
        if i < self.submit_i:
            return CAMERA_CLOSE + 0.04 * _ease((i - dive_end) / max(1, self.submit_i - dive_end)), INPUT_LINE
        if i < self.verdict_i:
            p = (i - self.submit_i) / max(1, self.verdict_i - self.submit_i)
            focus = INPUT_LINE + (VERDICT_LINE - INPUT_LINE) * _ease((i - self.submit_i) / (REFRAME_S * self.fps))
            return CAMERA_CLOSE + 0.04 + (CAMERA_PEAK - CAMERA_CLOSE - 0.04) * p * p, focus
        release = _ease_out_expo((i - self.verdict_i) / (0.9 * self.fps))
        zoom = CAMERA_PEAK + (1.0 - CAMERA_PEAK) * release
        if i >= plan.outro_start:
            zoom = 1.0 + 0.025 * _ease((i - plan.outro_start) / max(1, plan.total - plan.outro_start))
        return zoom, VERDICT_LINE + (0.5 - VERDICT_LINE) * release

    def frame(self, i: int, source: Image.Image) -> Image.Image:
        W, H, plan = self.W, self.H, self.plan
        sx, sy, sw, sh = self.screen
        face = source.crop((sx, sy, sx + sw, sy + sh))
        ImageDraw.Draw(face).rectangle([sw * 0.44, 0, sw * 0.56, sh * 0.045], fill=SCREEN_BG)  # no camera dot
        t = i / self.fps
        dv = (i - self.verdict_i) / self.fps
        zoom, focus = self.camera(i)
        if dv >= 0:
            zoom *= 1.0 + 0.012 * math.exp(-dv / 0.6) * math.sin(min(math.pi, dv * math.pi / 0.9))  # a breath
        w, h = round(self.base_w * zoom), round(self.base_h * zoom)
        radius = round(10 * zoom)
        drift = self.drift * math.sin(math.pi * i / plan.total)
        x0 = round(W / 2 - w / 2 + drift)
        y0 = round(H / 2 - focus * h)
        out_i = i - plan.outro_start
        recede = _ease(out_i / plan.cross) if out_i >= 0 else 0.0
        slab_left = (1 - _ease(min(1.0, recede * 2))) * _ease(t / 0.15)  # dark frame 0 (the loop), then present
        frame = self.bg.copy()
        if slab_left > 0:
            shw, shh = round(self.shadow.width * zoom), round(self.shadow.height * zoom)
            shadow = self.shadow.resize((shw, shh)).point(lambda v: round(v * slab_left))
            frame.paste((0, 0, 0), (round(W / 2 - shw / 2 + drift), y0 + h - round(40 * zoom)), shadow)
        slab = face.resize((w, h), Image.BICUBIC).convert("RGBA")
        if 0 <= dv < 1.1:  # one soft light sweep over the verdict
            p = _ease(dv / 1.1)
            bw, bh = self.band.size
            ox, oy = round(w / 2 - bw / 2), round(-bh / 2 - h * 0.1 + p * (h * 1.2))
            layer = Image.new("RGBA", slab.size, (0, 0, 0, 0))
            layer.alpha_composite(self.band, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy), bw, bh))
            slab.alpha_composite(layer)
        if t < INTRO_S:  # the rim traces in light
            glow = round(44 + 150 * (1 - _ease(t / INTRO_S)))
        else:
            glow = 44 + (round(40 * math.exp(-dv / 0.7)) if dv >= 0 else 0)
        ImageDraw.Draw(slab).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(glow, glow, glow + 6),
                                               width=max(2, round(2 * zoom)))
        mask = _slab_mask(w, h, radius)
        if slab_left < 1:
            mask = mask.point(lambda v: round(v * slab_left))
        if slab_left > 0 and y0 + h < H:  # a faint reflection on the stone floor
            depth = min(round(h * 0.22), H - (y0 + h))
            if depth > 4:
                refl = slab.crop((0, h - depth, w, h)).transpose(Image.FLIP_TOP_BOTTOM).convert("RGB")
                ra = self.reflect_fade.resize((w, depth)).point(lambda v: round(v * slab_left))
                frame.paste(refl, (x0, y0 + h + 4), ra)
        frame.paste(slab.convert("RGB"), (x0, y0), mask)
        if dv >= 0:  # the room lifts a little when the verdict lands
            frame = Image.blend(frame, ImageChops.screen(frame, self.lift), 0.06 * math.exp(-dv / 1.2) * slab_left)
        left = plan.total - i
        sink = _ease((left - 1) / plan.fade) if left <= plan.fade else 1.0  # back to frame 0's darkness
        type_in = _ease((recede - 0.4) / 0.6) * sink
        if type_in > 0:
            txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(txt)
            rise = round(30 * (1 - _ease((recede - 0.4) / 0.6)))
            alpha = round(255 * type_in)
            _tracked(d, W / 2, H * 0.44 - 150 + rise, self.category, self.small, (*STONE, alpha), 6)
            _tracked(d, W / 2, H * 0.44 - 40 + rise, self.verdict, self.big, (*INK, alpha), 5)
            frame = Image.alpha_composite(frame.convert("RGBA"), txt).convert("RGB")
        if self.submit_i <= i < self.verdict_i + 0.35 * self.fps:  # the room darkens through the wait
            p = min(1.0, (i - self.submit_i) / max(1, self.verdict_i - self.submit_i))
            dark = 0.14 * _ease(p) if i < self.verdict_i else 0.14 * (1 - (i - self.verdict_i) / (0.35 * self.fps))
            frame = Image.blend(frame, self.black, dark)
        frame = ImageChops.multiply(frame, self.vig)
        return ImageChops.add(frame, self.grains[(i // 2) % len(self.grains)], 1.0, -128)


def _motion(clip: Path, timeline: Timeline, out: Path, work: Path, *, category: str, verdict: str, font_path: str,
            layout: Layout, screen: tuple[int, int, int, int] | None, audio: bool, meta: list[str],
            source: Path | None = None) -> None:
    W, H, fps = layout.width, layout.height, timeline.fps
    plan = motion_plan(timeline)
    src = source or clip
    src_info = probe(src)
    SW, SH = src_info.width, src_info.height
    mono = _Monolith(plan, timeline, category=category, verdict=verdict, font_path=font_path, layout=layout,
                     screen=screen or (0, 0, SW, SH), source_size=(SW, SH))
    total_s = plan.total / fps
    inputs = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if audio:
        wav = work / "motion.wav"
        monolith_score(f"{category}|{verdict}", total_s, INTRO_S, mono.submit_i / fps, mono.verdict_i / fps,
                       plan.outro_start / fps).write(wav)
        delay = round(INTRO_S * 1000)
        inputs += ["-i", str(clip), "-i", str(wav)]
        amap = ["-filter_complex", f"[1:a]adelay={delay}|{delay},apad[k];[k][2:a]amix=inputs=2:normalize=0:"
                                   f"weights='0.8 1':duration=shortest,atrim=0:{total_s:.3f},"
                                   "loudnorm=I=-17:TP=-1.5:LRA=11,aresample=44100[a]", "-map", "0:v", "-map", "[a]"]
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = ["-map", "0:v", "-map", "1:a"]
    enc = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, *amap,
                            "-t", f"{total_s:.4f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                            "-maxrate", "6M", "-bufsize", "12M",
                            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1", "-g", str(fps),
                            "-bf", "2", *meta, *_encode_tail(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    dec = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = SW * SH * 3
    cur = None
    read = 0
    try:
        for i in range(plan.total):
            j = min(max(0, i - plan.intro), plan.classic - 1)
            while read <= j:
                raw = dec.stdout.read(size)
                if len(raw) < size:
                    break
                cur = Image.frombytes("RGB", (SW, SH), raw)
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
